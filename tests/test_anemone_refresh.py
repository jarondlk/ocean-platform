from io import BytesIO
from pathlib import Path
import hashlib
from urllib.error import HTTPError
from email.message import Message

import pytest

from ingestion.anemone import (
    AnemoneCredentials,
    AnemoneError,
    AnemoneHttpClient,
    load_contract,
)
from ingestion.anemone_catalogue import CATALOGUE_CONTRACT, prepare_catalogue
from ingestion.anemone_refresh import BudgetClient, discover, refresh_archive
from tests.test_anemone_ingestion import _sample_payloads


class Provider:
    def __init__(self):
        self.payloads = {
            f"https://db.anemone.bio{k}": v
            for k, v in _sample_payloads(load_contract(CATALOGUE_CONTRACT)).items()
            if not k.endswith("/")
        }
        self.gets = []
        self.fail = False

    def read_directory(self, url, maximum):
        if self.fail:
            raise AnemoneError("authentication_failed", "Authentication failed")
        names = set()
        for child in self.payloads:
            if child.startswith(url):
                tail = child[len(url) :]
                name = tail.split("/")[0]
                names.add(name + "/" if "/" in tail else name)
        return "".join(f'<a href="{n}">{n}</a>' for n in sorted(names))

    def metadata(self, url):
        data = self.payloads[url]
        return {
            "size_bytes": len(data),
            "etag": hashlib.sha256(data).hexdigest(),
            "last_modified": "Thu, 17 Sep 2026 00:00:00 GMT",
        }

    def open(self, url):
        self.gets.append(url)
        return BytesIO(self.payloads[url])


def test_refresh_reuses_validated_bytes_and_does_not_redownload_raw(tmp_path):
    provider = Provider()
    first = refresh_archive(provider, tmp_path / "refresh", min_interval=0)
    assert len(provider.gets) == 5 and all(u.endswith(".tsv.xz") for u in provider.gets)
    old = Path(first["archive"])
    candidate1 = prepare_catalogue(old, tmp_path / "work")
    provider.gets.clear()
    second = refresh_archive(
        provider, tmp_path / "refresh", previous=old, min_interval=0
    )
    assert (
        not provider.gets
        and second["reused_files"] == 5
        and not second["changed_selected_files"]
    )
    candidate2 = prepare_catalogue(
        Path(second["archive"]), tmp_path / "work"
    )
    assert candidate1["candidate_id"] == candidate2["candidate_id"]
    assert candidate1["units"] == candidate2["units"]
    provider.gets.clear()
    refresh_archive(
        provider, tmp_path / "refresh", previous=old, rehash=True, min_interval=0
    )
    assert len(provider.gets) == 5


def test_failed_discovery_and_withdrawal_do_not_publish_or_delete(tmp_path):
    provider = Provider()
    output = tmp_path / "refresh"
    first = refresh_archive(provider, output, min_interval=0)
    pointer = (output / "current.json").read_bytes()
    provider.fail = True
    with pytest.raises(AnemoneError):
        refresh_archive(provider, output, min_interval=0)
    assert (output / "current.json").read_bytes() == pointer
    provider.fail = False
    png = next(k for k in provider.payloads if k.endswith(".png"))
    del provider.payloads[png]
    second = refresh_archive(
        provider,
        output,
        previous=Path(first["archive"]),
        min_interval=0,
    )
    assert (
        second["withdrawal_candidates"] == [png] and not second["withdrawals_applied"]
    )


def test_request_budgets_and_mid_acquisition_change_fail_closed(tmp_path):
    provider = Provider()
    with pytest.raises(ValueError, match="budget"):
        discover(BudgetClient(provider, max_requests=1, min_interval=0))
    original = provider.open

    def changed(url):
        stream = original(url)
        provider.payloads[url] += b"changed"
        return stream

    provider.open = changed
    with pytest.raises(ValueError, match="changed during acquisition"):
        refresh_archive(provider, tmp_path, min_interval=0)
    assert not (tmp_path / "current.json").exists()


def test_retry_after_is_respected():
    waits = []
    headers = Message()
    headers["Retry-After"] = "2"

    class Retry:
        attempts = 0

        def open(self, request, timeout):
            self.attempts += 1
            if self.attempts == 1:
                raise HTTPError(request.full_url, 522, "temporary", headers, None)
            response = BytesIO(b"ok")
            response.geturl = lambda: request.full_url
            return response

    opener = Retry()
    client = AnemoneHttpClient(
        AnemoneCredentials("fixture", "fixture"),
        base_url="https://db.anemone.bio/dist/",
        opener=opener,
        sleep_fn=waits.append,
    )
    assert client.open("https://db.anemone.bio/dist/").read() == b"ok" and waits == [2]


def test_missing_required_file_does_not_advance_observation(tmp_path):
    provider = Provider()
    refresh_archive(provider, tmp_path, min_interval=0)
    pointer = (tmp_path / "current.json").read_bytes()
    del provider.payloads[next(url for url in provider.payloads if url.endswith('/community_qc_target.tsv.xz'))]
    with pytest.raises(ValueError, match="missing required"):
        refresh_archive(provider, tmp_path, min_interval=0)
    assert (tmp_path / "current.json").read_bytes() == pointer


def test_authentication_error_is_not_retried():
    class Unauthorized:
        attempts = 0
        def open(self, request, timeout):
            self.attempts += 1
            raise HTTPError(request.full_url, 401, "unauthorized", Message(), None)
    opener = Unauthorized()
    client = AnemoneHttpClient(AnemoneCredentials("fixture", "fixture"), base_url="https://db.anemone.bio/dist/", opener=opener)
    with pytest.raises(AnemoneError):
        client.open("https://db.anemone.bio/dist/")
    assert opener.attempts == 1
