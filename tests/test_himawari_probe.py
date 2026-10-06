import hashlib
import json
from pathlib import Path
import ssl
from types import SimpleNamespace

import pytest

from ingestion.himawari_probe import (
    MAX_FILE_BYTES,
    connect,
    download_probe,
    list_directory,
    parse_remote_file,
    read_credentials,
    validate_directory,
)

REMOTE = (
    "/pub/himawari/L3/SST/v201_nc4_normal_std_daily/202307/15/"
    "20230715000000-JAXA-L3C_GHRSST-SSTskin-H09_AHI-v2.2_daily-v02.0-fv01.0.nc"
)
RAW = b"\x89HDF\r\n\x1a\n" + b"fixture"


class Provider:
    def __init__(self, raw=RAW):
        self.raw = raw
        self.reported_size = len(raw)
        self.md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest()
        self.raw_transfers = 0
        self.interrupt = False
        self.listing = [
            "type=cdir;modify=20231003000000; .",
            "type=file;size=187157807;modify=20240319000000;UNIX.ownername=private-account; "
            + Path(REMOTE).name,
        ]

    def voidcmd(self, command):
        assert command == "TYPE I"

    def size(self, path):
        assert path == REMOTE
        return self.reported_size

    def retrbinary(self, command, callback, blocksize):
        assert command in {"RETR " + REMOTE, "RETR " + REMOTE + ".md5"}
        if command.endswith(".md5"):
            callback((self.md5 + "  " + Path(REMOTE).name + "\n").encode())
        else:
            self.raw_transfers += 1
            callback(self.raw[:8])
            if self.interrupt:
                raise ConnectionError("sensitive provider text")
            callback(self.raw[8:])

    def retrlines(self, command, callback):
        for line in self.listing:
            callback(line)


def test_explicit_versions_and_statistics_are_retained_not_guessed():
    fields = parse_remote_file(REMOTE)
    assert fields["algorithm_version"] == "2.2"  # Daily directory remains v201.
    assert fields["file_version"] == "01.0"
    assert fields["temporal_basis"] == "daily_file_statistics_require_inspection"
    assert fields["nominal_time_utc"] == "2023-07-15T00:00:00Z"


@pytest.mark.parametrize(
    "value",
    [
        REMOTE.replace("202307/15", "202307/16"),
        REMOTE.replace("000000-JAXA", "090000-JAXA"),
        REMOTE.replace("_daily-v02", "-v02"),
        REMOTE.replace("/pub/", "/../pub/"),
        REMOTE + "\r\nPASS secret",
        "ftp://user:secret@somewhere/file.nc",
    ],
)
def test_invalid_file_time_paths_and_command_injection_rejected(value):
    with pytest.raises(ValueError):
        parse_remote_file(value)


def test_credentials_are_private_and_never_copied_into_plans(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"username": "fixture", "password": "private"}))
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        read_credentials(path)
    path.chmod(0o600)
    assert read_credentials(path)["username"] == "fixture"
    linked = tmp_path / "link"
    linked.symlink_to(path)
    with pytest.raises(ValueError, match="private"):
        read_credentials(linked)
    path.write_text(json.dumps({"username": "fixture\r\nPASS other", "password": "x"}))
    with pytest.raises(ValueError, match="field"):
        read_credentials(path)


def test_download_checksum_reuse_changed_generation_and_corruption(tmp_path):
    provider = Provider()
    first = download_probe(provider, REMOTE, tmp_path)
    assert first["raw_sha256"] == hashlib.sha256(RAW).hexdigest()
    assert first["scientific_validation"] == "pending"
    assert download_probe(provider, REMOTE, tmp_path)["reused_verified_raw"] is True
    assert provider.raw_transfers == 1
    provider.raw += b"revision"
    provider.reported_size = len(provider.raw)
    provider.md5 = hashlib.md5(provider.raw, usedforsecurity=False).hexdigest()
    second = download_probe(provider, REMOTE, tmp_path)
    assert second["raw_sha256"] != first["raw_sha256"]
    assert len(list(tmp_path.glob("*.nc"))) == 2
    (tmp_path / second["local_filename"]).write_bytes(b"damaged")
    with pytest.raises(ValueError, match="integrity"):
        download_probe(provider, REMOTE, tmp_path)
    assert not (tmp_path / ".himawari-probe.lock").exists()


@pytest.mark.parametrize(
    "failure", ["checksum", "truncated", "oversized", "interrupt", "magic"]
)
def test_invalid_and_interrupted_transfers_publish_no_completed_receipt(
    tmp_path, failure
):
    provider = Provider()
    if failure == "checksum":
        provider.md5 = "0" * 32
    elif failure == "truncated":
        provider.reported_size += 1
    elif failure == "oversized":
        provider.reported_size = MAX_FILE_BYTES + 1
    elif failure == "interrupt":
        provider.interrupt = True
    else:
        provider.raw = b"differentformat"
        provider.reported_size = len(provider.raw)
        provider.md5 = hashlib.md5(provider.raw, usedforsecurity=False).hexdigest()
    with pytest.raises((ValueError, ConnectionError)):
        download_probe(provider, REMOTE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_single_writer_lock_and_directory_listing_limit(tmp_path):
    (tmp_path / ".himawari-probe.lock").write_text("another writer")
    with pytest.raises(FileExistsError):
        download_probe(Provider(), REMOTE, tmp_path)
    provider = Provider()
    report = list_directory(provider, "/pub/himawari/L3/SST")
    assert len(report["entries"]) == 1
    assert "private-account" not in json.dumps(report)
    assert report["binary_verified"] is False
    provider.listing *= 300
    with pytest.raises(ValueError, match="listing limit"):
        list_directory(provider, "/pub/himawari/L3/SST")
    with pytest.raises(ValueError):
        validate_directory("/pub/himawari/L3/SST\nPASS x")


def test_certificate_failure_never_sends_account_credentials_or_falls_back(monkeypatch):
    closed = []
    login = []

    class Context:
        def wrap_socket(self, raw, *, server_hostname):
            assert server_hostname == "ftp.ptree.jaxa.jp"
            raise ssl.SSLCertVerificationError("untrusted peer")

    client = SimpleNamespace(
        context=Context(),
        close=lambda: closed.append("client"),
        login=lambda *args: login.append(args),
    )
    monkeypatch.setattr(
        "ingestion.himawari_probe.ftplib.FTP_TLS", lambda **kwargs: client
    )
    monkeypatch.setattr(
        "ingestion.himawari_probe.socket.create_connection",
        lambda *args, **kwargs: SimpleNamespace(close=lambda: closed.append("raw")),
    )
    with pytest.raises(ssl.SSLCertVerificationError):
        with connect({"username": "fixture", "password": "private"}):
            pytest.fail("Untrusted connection must never be yielded")
    assert login == []
    assert closed == ["raw", "client"]
