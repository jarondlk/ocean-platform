from __future__ import annotations

import json
import lzma
import socket
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from ingestion.anemone import (
    AnemoneCredentials,
    AnemoneError,
    inventory_anemone,
    load_contract,
    resolve_credentials,
    sync_anemone,
    validate_scope_url,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "anemone"
PROJECT = "ProjectA"
RUN = "Run01"
SAMPLE = "Run01__20240101T0000-TEST-Surface__MiFish"
USERNAME = "fixture-user"
PASSWORD = "fixture-password"


def _tsv_xz(header: list[str], rows: list[list[str]]) -> bytes:
    text = "\n".join("\t".join(row) for row in [header, *rows]) + "\n"
    return lzma.compress(text.encode("utf-8"))


def _sample_payloads(contract: dict) -> dict[str, bytes]:
    prefix = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/"
    run_prefix = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/"
    sample_listing = (FIXTURE_ROOT / "sample_listing.html").read_text(
        encoding="utf-8"
    ).replace("{{SAMPLE}}", SAMPLE)
    run_listing = (FIXTURE_ROOT / "run_listing.html").read_text(
        encoding="utf-8"
    ).replace("{{SAMPLE}}", SAMPLE)

    community_header = contract["tables"]["community"]["columns"]
    community_row = [""] * len(community_header)
    community_row[0] = SAMPLE
    community_row[community_header.index("species")] = "Fixture fish"
    community_row[community_header.index("sequence")] = "ACGTACGT"
    community_row[community_header.index("nreads")] = "17"
    community_row[community_header.index("ncopiesperml")] = "2.5"

    standard_header = contract["tables"]["standard"]["columns"]
    standard_row = [SAMPLE, "MiFish-U", "ACGT", "4"]
    sample_header = contract["tables"]["key_value_sample"]["columns"]
    sample_rows = [
        [SAMPLE, "samp_name", SAMPLE],
        [SAMPLE, "project_name", PROJECT],
        [SAMPLE, "lat_lon", "38.4 141.5"],
        [SAMPLE, "collection_date_utc", "2024-01-01"],
        [SAMPLE, "sample_type", "environmental"],
    ]
    experiment_header = contract["tables"]["key_value_experiment"]["columns"]
    experiment_rows = [
        [SAMPLE, "target_gene", "12S"],
        [SAMPLE, "pcr_primers", "MiFish-U"],
        [SAMPLE, "seq_meth", "Illumina MiSeq"],
    ]

    payloads = {
        run_prefix: run_listing.encode(),
        prefix: sample_listing.encode(),
        prefix + f"{SAMPLE}.forward.fastq.xz": b"synthetic-forward-fastq",
        prefix + f"{SAMPLE}.reverse.fastq.xz": b"synthetic-reverse-fastq",
        prefix + "community_qc_target.tsv.xz": _tsv_xz(
            community_header, [community_row]
        ),
        prefix + "community_qc3nn_target.tsv.xz": _tsv_xz(
            community_header, [community_row]
        ),
        prefix + "community_standard.tsv.xz": _tsv_xz(
            standard_header, [standard_row]
        ),
        prefix + "sample.tsv.xz": _tsv_xz(sample_header, sample_rows),
        prefix + "experiment.tsv.xz": _tsv_xz(
            experiment_header, experiment_rows
        ),
    }
    for rank in ("phylum", "class", "order", "family", "genus", "species"):
        payloads[prefix + f"wordcloud.{rank}.png"] = b"synthetic-png"
    return payloads


class _AnemoneFixtureHandler(BaseHTTPRequestHandler):
    server_version = "ANEMONEFixture/1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _authorized(self) -> bool:
        if self.headers.get("Authorization") == self.server.expected_authorization:
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="fixture"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _serve(self, *, head_only: bool) -> None:
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        redirect = self.server.redirects.get(path)
        if redirect:
            self.send_response(302)
            self.send_header("Location", redirect)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = self.server.payloads.get(path)
        if body is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        method = "HEAD" if head_only else "GET"
        self.server.requests.append((method, path, self.headers.get("Range")))
        range_header = self.headers.get("Range")
        etag = (
            self.server.range_etags.get(path)
            if range_header
            else None
        ) or self.server.etags.get(path, '"fixture-v1"')
        start = 0
        status = 200
        if range_header:
            start = int(range_header.removeprefix("bytes=").split("-", 1)[0])
            status = 206
        response_body = body[start:]
        self.send_response(status)
        self.send_header("Content-Type", "text/html" if path.endswith("/") else "application/octet-stream")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", "Tue, 01 Sep 2026 00:00:00 GMT")
        self.send_header("Content-Length", str(len(response_body)))
        if status == 206:
            self.send_header(
                "Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}"
            )
        self.end_headers()
        if head_only:
            return
        if path == self.server.interrupt_once and not self.server.interrupt_used:
            self.server.interrupt_used = True
            midpoint = max(1, len(response_body) // 2)
            self.wfile.write(response_body[:midpoint])
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_WR)
            self.close_connection = True
            return
        self.wfile.write(response_body)

    def do_HEAD(self) -> None:
        self._serve(head_only=True)

    def do_GET(self) -> None:
        self._serve(head_only=False)


@contextmanager
def _fixture_server(
    contract: dict,
    *,
    interrupt_once: str | None = None,
) -> Iterator[tuple[str, dict[str, bytes], ThreadingHTTPServer]]:
    payloads = _sample_payloads(contract)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AnemoneFixtureHandler)
    token = AnemoneCredentials(USERNAME, PASSWORD).authorization_header()
    server.payloads = payloads  # type: ignore[attr-defined]
    server.etags = {}  # type: ignore[attr-defined]
    server.range_etags = {}  # type: ignore[attr-defined]
    server.requests = []  # type: ignore[attr-defined]
    server.redirects = {}  # type: ignore[attr-defined]
    server.expected_authorization = token  # type: ignore[attr-defined]
    server.interrupt_once = interrupt_once  # type: ignore[attr-defined]
    server.interrupt_used = False  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/dist/MiFish/ANEMONE/", payloads, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _credentials() -> AnemoneCredentials:
    return AnemoneCredentials(USERNAME, PASSWORD)


def _scope(base_url: str, *, level: str = "sample") -> str:
    run = f"{base_url}{PROJECT}/{RUN}/"
    return f"{run}{SAMPLE}/" if level == "sample" else run


def _local_contract(base_url: str) -> dict:
    contract = load_contract()
    contract["base_url"] = base_url
    return contract


def test_scope_accepts_only_exact_sample_or_run_directories() -> None:
    base = "https://db.anemone.bio/dist/MiFish/ANEMONE/"
    assert validate_scope_url(f"{base}{PROJECT}/{RUN}/").level == "run"
    assert validate_scope_url(f"{base}{PROJECT}/{RUN}/{SAMPLE}/").level == "sample"
    rejected = [
        base,
        f"{base}{PROJECT}/",
        f"{base}{PROJECT}/{RUN}/{SAMPLE}",
        f"{base}{PROJECT}/{RUN}/{SAMPLE}/?all=true",
        f"{base}{PROJECT}/{RUN}/../Other/",
        "https://example.org/dist/MiFish/ANEMONE/ProjectA/Run01/",
        "http://db.anemone.bio/dist/MiFish/ANEMONE/ProjectA/Run01/",
    ]
    for candidate in rejected:
        with pytest.raises(AnemoneError):
            validate_scope_url(candidate)


def test_credentials_resolve_from_files_or_environment_without_repr_leak(
    tmp_path: Path,
) -> None:
    username_file = tmp_path / "username"
    password_file = tmp_path / "password"
    username_file.write_text(USERNAME)
    password_file.write_text(PASSWORD)
    credentials = resolve_credentials(
        username_file=username_file,
        password_file=password_file,
        environ={},
        prompt=False,
    )
    assert credentials == _credentials()
    assert USERNAME not in repr(credentials)
    assert PASSWORD not in repr(credentials)
    assert resolve_credentials(
        environ={
            "ANEMONE_DOWNLOAD_USERNAME": USERNAME,
            "ANEMONE_DOWNLOAD_PASSWORD": PASSWORD,
        },
        prompt=False,
    ) == _credentials()
    with pytest.raises(AnemoneError, match="credentials are required"):
        resolve_credentials(environ={}, prompt=False)
    with pytest.raises(AnemoneError) as unsafe:
        resolve_credentials(
            username_file=Path(__file__),
            password_file=password_file,
            environ={},
            prompt=False,
        )
    assert unsafe.value.code == "credential_path_unsafe"


def test_inventory_is_bounded_deterministic_and_downloads_no_source_files(
    tmp_path: Path,
) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, _, server):
        local = _local_contract(base)
        first = sync_anemone(
            _scope(base),
            credentials=_credentials(),
            output_root=tmp_path,
            contract=local,
            allow_insecure_http=True,
            generated_at="2026-09-01T00:00:00+00:00",
        )
        second = sync_anemone(
            _scope(base),
            credentials=_credentials(),
            output_root=tmp_path,
            contract=local,
            allow_insecure_http=True,
            generated_at="2026-09-02T00:00:00+00:00",
        )

    assert first["ok"] is True
    assert first["file_count"] == 13
    assert first["selected_file_count"] == 5
    assert first["source_collection_sha256"] == second["source_collection_sha256"]
    assert list((tmp_path / "inventory").glob("*.json"))
    assert not (tmp_path / "snapshots").exists()
    assert all(method != "GET" for method, path, _ in server.requests if not path.endswith("/"))
    serialized = json.dumps(first)
    assert USERNAME not in serialized
    assert PASSWORD not in serialized
    assert "Authorization" not in serialized


def test_execute_validates_five_tsvs_and_never_downloads_fastq(
    tmp_path: Path,
) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, _, server):
        result = sync_anemone(
            _scope(base),
            credentials=_credentials(),
            execute=True,
            output_root=tmp_path,
            contract=_local_contract(base),
            allow_insecure_http=True,
        )

    snapshot = Path(result["snapshot_path"])
    data_files = sorted(path.name for path in snapshot.iterdir() if path.is_file())
    assert result["status"] == "complete"
    assert result["reused_snapshot"] is False
    assert len([item for item in result["files"] if item["validation_status"] == "valid"]) == 5
    assert data_files == [
        "community_qc3nn_target.tsv.xz",
        "community_qc_target.tsv.xz",
        "community_standard.tsv.xz",
        "experiment.tsv.xz",
        "manifest.json",
        "sample.tsv.xz",
    ]
    source_gets = [path for method, path, _ in server.requests if method == "GET"]
    assert not any("fastq" in path for path in source_gets)
    on_disk = json.loads((snapshot / "manifest.json").read_text())
    assert on_disk["collection_sha256"] == result["collection_sha256"]


def test_unchanged_source_reuses_snapshot_without_redownload(tmp_path: Path) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, _, server):
        arguments = {
            "credentials": _credentials(),
            "execute": True,
            "output_root": tmp_path,
            "contract": _local_contract(base),
            "allow_insecure_http": True,
        }
        first = sync_anemone(_scope(base), **arguments)
        downloads_before = len(
            [request for request in server.requests if request[0] == "GET" and not request[1].endswith("/")]
        )
        second = sync_anemone(_scope(base), **arguments)
        downloads_after = len(
            [request for request in server.requests if request[0] == "GET" and not request[1].endswith("/")]
        )

    assert first["snapshot_id"] == second["snapshot_id"]
    assert second["reused_snapshot"] is True
    assert downloads_after == downloads_before


def test_changed_remote_validator_creates_a_new_snapshot(tmp_path: Path) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, _, server):
        arguments = {
            "credentials": _credentials(),
            "execute": True,
            "output_root": tmp_path,
            "contract": _local_contract(base),
            "allow_insecure_http": True,
        }
        first = sync_anemone(_scope(base), **arguments)
        sample_path = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/sample.tsv.xz"
        server.etags[sample_path] = '"fixture-v2"'
        second = sync_anemone(_scope(base), **arguments)

    assert first["snapshot_id"] != second["snapshot_id"]
    assert len(list((tmp_path / "snapshots").iterdir())) == 2


def test_run_scope_discovers_samples_and_preserves_relative_directory(
    tmp_path: Path,
) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, _, _):
        result = sync_anemone(
            _scope(base, level="run"),
            credentials=_credentials(),
            execute=True,
            output_root=tmp_path,
            contract=_local_contract(base),
            allow_insecure_http=True,
        )
    snapshot = Path(result["snapshot_path"])
    assert (snapshot / SAMPLE / "sample.tsv.xz").exists()
    assert result["scope_level"] == "run"


def test_unknown_or_missing_roles_and_limits_block_execution(tmp_path: Path) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, payloads, _):
        prefix = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/"
        payloads[prefix] = payloads[prefix].replace(
            b"</body>", b'<a href="notes.txt">unknown</a></body>'
        )
        payloads[prefix] = payloads[prefix].replace(
            b'<a href="experiment.tsv.xz">experiment metadata</a>\n', b""
        )
        payloads[prefix + "notes.txt"] = b"not contracted"
        inventory = inventory_anemone(
            _scope(base),
            credentials=_credentials(),
            contract=_local_contract(base),
            allow_insecure_http=True,
        )
        codes = {issue.code for issue in inventory.issues}
        file_limited = inventory_anemone(
            _scope(base),
            credentials=_credentials(),
            contract=_local_contract(base),
            allow_insecure_http=True,
            max_files=1,
        )
        byte_limited = inventory_anemone(
            _scope(base),
            credentials=_credentials(),
            contract=_local_contract(base),
            allow_insecure_http=True,
            max_bytes=1,
        )
        with pytest.raises(AnemoneError, match="inventory failed validation"):
            sync_anemone(
                _scope(base),
                credentials=_credentials(),
                execute=True,
                output_root=tmp_path,
                contract=_local_contract(base),
                allow_insecure_http=True,
            )
    assert {"unknown_source_file", "required_file_missing"} <= codes
    assert "file_limit_exceeded" in {issue.code for issue in file_limited.issues}
    assert "byte_limit_exceeded" in {issue.code for issue in byte_limited.issues}
    assert not (tmp_path / "snapshots").exists()


def test_corrupt_xz_never_publishes_a_complete_snapshot(tmp_path: Path) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, payloads, _):
        path = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/community_qc3nn_target.tsv.xz"
        payloads[path] = b"not-an-xz-stream"
        with pytest.raises(AnemoneError) as failure:
            sync_anemone(
                _scope(base),
                credentials=_credentials(),
                execute=True,
                output_root=tmp_path,
                contract=_local_contract(base),
                allow_insecure_http=True,
            )
    assert failure.value.code == "xz_validation_failed"
    assert not (tmp_path / "snapshots").exists()
    assert list((tmp_path / "staging").glob("*/community_qc3nn_target.tsv.xz"))


def test_tsv_schema_drift_blocks_snapshot_publication(tmp_path: Path) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, payloads, _):
        path = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/community_qc_target.tsv.xz"
        payloads[path] = _tsv_xz(["samplename", "unexpected"], [[SAMPLE, "x"]])
        with pytest.raises(AnemoneError) as failure:
            sync_anemone(
                _scope(base),
                credentials=_credentials(),
                execute=True,
                output_root=tmp_path,
                contract=_local_contract(base),
                allow_insecure_http=True,
            )
    assert failure.value.code == "tsv_columns_invalid"
    assert not (tmp_path / "snapshots").exists()


def test_interrupted_transfer_resumes_from_hash_addressed_staging(
    tmp_path: Path,
) -> None:
    contract = load_contract()
    interrupted_path = (
        f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/"
        "community_qc3nn_target.tsv.xz"
    )
    with _fixture_server(contract, interrupt_once=interrupted_path) as (base, _, server):
        arguments = {
            "credentials": _credentials(),
            "execute": True,
            "output_root": tmp_path,
            "contract": _local_contract(base),
            "allow_insecure_http": True,
        }
        with pytest.raises(AnemoneError) as failure:
            sync_anemone(_scope(base), **arguments)
        result = sync_anemone(_scope(base), **arguments)
    assert failure.value.code in {"download_incomplete", "download_size_mismatch"}
    assert result["status"] == "complete"
    assert any(
        method == "GET" and path == interrupted_path and range_header
        for method, path, range_header in server.requests
    )


def test_resume_fails_if_remote_validator_changes(tmp_path: Path) -> None:
    contract = load_contract()
    interrupted_path = (
        f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/"
        "community_qc3nn_target.tsv.xz"
    )
    with _fixture_server(contract, interrupt_once=interrupted_path) as (base, _, server):
        arguments = {
            "credentials": _credentials(),
            "execute": True,
            "output_root": tmp_path,
            "contract": _local_contract(base),
            "allow_insecure_http": True,
        }
        with pytest.raises(AnemoneError):
            sync_anemone(_scope(base), **arguments)
        server.range_etags[interrupted_path] = '"changed-during-resume"'
        with pytest.raises(AnemoneError) as failure:
            sync_anemone(_scope(base), **arguments)
    assert failure.value.code == "source_changed_during_resume"
    assert not (tmp_path / "snapshots").exists()


def test_authentication_error_is_sanitized(tmp_path: Path) -> None:
    contract = load_contract()
    wrong_secret = "must-not-appear"
    with _fixture_server(contract) as (base, _, _):
        with pytest.raises(AnemoneError) as failure:
            sync_anemone(
                _scope(base),
                credentials=AnemoneCredentials(USERNAME, wrong_secret),
                output_root=tmp_path,
                contract=_local_contract(base),
                allow_insecure_http=True,
            )
    assert failure.value.code == "authentication_failed"
    assert wrong_secret not in str(failure.value)


def test_cross_origin_redirect_is_rejected_before_following(tmp_path: Path) -> None:
    contract = load_contract()
    with _fixture_server(contract) as (base, _, server):
        server.redirects[
            f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/"
        ] = "https://example.org/credential-target/"
        with pytest.raises(AnemoneError) as failure:
            sync_anemone(
                _scope(base),
                credentials=_credentials(),
                output_root=tmp_path,
                contract=_local_contract(base),
                allow_insecure_http=True,
            )
    assert failure.value.code == "redirect_outside_scope"


def test_cli_defaults_to_inventory_and_does_not_serialize_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    import scripts.sync_anemone as command

    captured: dict = {}

    def fake_sync(scope_url: str, **kwargs: object) -> dict:
        captured.update({"scope_url": scope_url, **kwargs})
        return {"ok": True, "mode": "inventory"}

    monkeypatch.setattr(command, "sync_anemone", fake_sync)
    monkeypatch.setenv("ANEMONE_DOWNLOAD_USERNAME", USERNAME)
    monkeypatch.setenv("ANEMONE_DOWNLOAD_PASSWORD", PASSWORD)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_anemone.py",
            "--scope-url",
            "https://db.anemone.bio/dist/MiFish/ANEMONE/ProjectA/Run01/",
            "--output-root",
            str(tmp_path),
        ],
    )
    assert command.main() == 0
    output = capsys.readouterr().out
    assert captured["execute"] is False
    assert PASSWORD not in output
    assert USERNAME not in output
