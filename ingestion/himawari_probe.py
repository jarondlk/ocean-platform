"""Bounded, operator-only encrypted JAXA historical SST access probes.

This is not a bulk downloader or a scientific publication/quality definition.
Remote paths are explicitly selected from archive listings, never guessed from
the observation year. Credentials stay outside plans, receipts and error text.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import ftplib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import ssl
import stat
import tempfile

from ingestion.anemone_catalogue import file_sha256
from ingestion.immutable_bundle import atomic_json, digest

HOST = "ftp.ptree.jaxa.jp"
PORT = 990
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_FILES = 4
MAX_LISTING_LINES = 500
DIRECTORY = re.compile(
    r"/pub/himawari/L3/SST(?:/v\d{3}_nc4_normal_std(?:_daily)?"
    r"(?:/\d{6}(?:/\d{2})?)?)?"
)
FILENAME = re.compile(
    r"(?P<stamp>\d{14})-JAXA-L3C_GHRSST-SSTskin-"
    r"(?P<satellite>H0[89])_AHI-v(?P<algorithm>\d\.\d)"
    r"(?P<daily>_daily)?-v02\.0-fv(?P<file_version>\d{2}\.\d)\.nc"
)


def validate_directory(path):
    if not isinstance(path, str) or not DIRECTORY.fullmatch(path):
        raise ValueError("Invalid Himawari archive directory")
    return path


def parse_remote_file(path):
    if not isinstance(path, str):
        raise ValueError("Invalid Himawari archive file")
    value = PurePosixPath(path)
    validate_directory(str(value.parent))
    match = FILENAME.fullmatch(value.name)
    if not match:
        raise ValueError("Invalid Himawari SST filename")
    fields = match.groupdict()
    stamp = datetime.strptime(fields["stamp"], "%Y%m%d%H%M%S")
    daily = bool(fields["daily"])
    if stamp.minute or stamp.second or (daily and stamp.hour):
        raise ValueError("Invalid Himawari nominal time")
    expected_suffix = "/" + stamp.strftime("%Y%m/%d")
    if not str(value.parent).endswith(expected_suffix):
        raise ValueError("Himawari file date/directory mismatch")
    if ("_daily/" in path) != daily:
        raise ValueError("Himawari file statistic/directory mismatch")
    return {
        "remote_path": path,
        "filename": value.name,
        "nominal_time_utc": stamp.isoformat() + "Z",
        "satellite": fields["satellite"],
        "algorithm_version": fields["algorithm"],
        "file_version": fields["file_version"],
        "temporal_basis": "daily_file_statistics_require_inspection"
        if daily
        else "hourly_retrieval_window",
        "measurement_type": "satellite_skin_retrieval",
    }


def read_credentials(path):
    """Require a private regular file; never return values in public receipts."""
    path = Path(path)
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_size > 8192
        or metadata.st_uid != os.getuid()
    ):
        raise ValueError("Credentials require an owned private regular file (0600)")
    with path.open("rb") as handle:
        data = handle.read(8193)
    if len(data) > 8192:
        raise ValueError("Credential file limit exceeded")
    value = json.loads(data)
    if not isinstance(value, dict) or set(value) != {"username", "password"}:
        raise ValueError("Invalid credential file contract")
    for key in value:
        if (
            not isinstance(value[key], str)
            or not 1 <= len(value[key]) <= 256
            or any(ord(c) < 32 for c in value[key])
        ):
            raise ValueError("Invalid credential field")
    return value


@contextmanager
def connect(credentials):
    """Implicit FTPS: verify control TLS before login and encrypt data too."""
    client = ftplib.FTP_TLS(context=ssl.create_default_context(), timeout=30)
    client.host = HOST
    try:
        raw = socket.create_connection((HOST, PORT), timeout=30)
        try:
            client.sock = client.context.wrap_socket(raw, server_hostname=HOST)
        except BaseException:
            raw.close()
            raise
        client.af = client.sock.family
        client.file = client.sock.makefile("r", encoding=client.encoding)
        client.welcome = client.getresp()
        client.login(credentials["username"], credentials["password"])
        client.prot_p()
        yield client
    finally:
        client.close()


def list_directory(client, remote_directory):
    """Keep bounded MLSD facts for explicit version/path selection."""
    validate_directory(remote_directory)
    lines = []

    def receive(line):
        if len(lines) >= MAX_LISTING_LINES or len(line) > 4096:
            raise ValueError("Himawari directory listing limit exceeded")
        lines.append(line)

    client.retrlines("MLSD " + remote_directory, receive)
    entries = []
    for line in lines:
        facts_text, name = line.split(" ", 1)
        if not name or PurePosixPath(name).name != name or name in {".", ".."}:
            continue
        facts = dict(field.split("=", 1) for field in facts_text.rstrip(";").split(";"))
        if facts.get("type", "").lower() not in {"file", "dir"}:
            continue
        # Some servers expose the logged-in account in UNIX.ownername. Keep
        # only acquisition facts, never provider account/permission metadata.
        facts = {
            key: value
            for key, value in facts.items()
            if key in {"type", "size", "modify"}
        }
        entries.append({"name": name, "facts": facts})
    report = {
        "schema_version": 1,
        "host": HOST,
        "protocol": "implicit_ftps",
        "port": PORT,
        "remote_directory": remote_directory,
        "listed_at_utc": datetime.now(timezone.utc).isoformat(),
        "entries": sorted(entries, key=lambda entry: entry["name"]),
        "binary_verified": False,
    }
    report["receipt_id"] = digest(report)
    return report


def _provider_md5(client, remote_path):
    data = bytearray()

    def receive(block):
        if len(data) + len(block) > 1024:
            raise ValueError("Himawari checksum sidecar limit exceeded")
        data.extend(block)

    client.retrbinary("RETR " + remote_path + ".md5", receive, blocksize=1024)
    # The authenticated sidecar checks transport/container integrity, not an
    # independent scientific validation or a signature from another authority.
    match = re.fullmatch(
        r"([a-fA-F0-9]{32})\s+\*?"
        + re.escape(PurePosixPath(remote_path).name)
        + r"\s*",
        data.decode("ascii"),
    )
    if not match:
        raise ValueError("Invalid Himawari provider checksum sidecar")
    return match[1].lower()


def download_probe(client, remote_path, output_dir):
    """One full-disk raw file, atomic completion and hash-verified reuse.

    No partial-range resume: an interrupted temporary file is discarded. A later
    successful provider revision creates a new content-addressed generation.
    """
    identity = parse_remote_file(remote_path)
    directory = Path(output_dir)
    if directory.is_symlink():
        raise ValueError("Invalid Himawari probe destination")
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".himawari-probe.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    temporary = None
    try:
        client.voidcmd("TYPE I")
        size = client.size(remote_path)
        if not isinstance(size, int) or not 8 <= size <= MAX_FILE_BYTES:
            raise ValueError("Himawari full-file byte limit exceeded")
        md5 = _provider_md5(client, remote_path)
        pointer = directory / (digest(remote_path) + ".json")
        if pointer.exists():
            if pointer.is_symlink() or pointer.stat().st_size > 8192:
                raise ValueError("Invalid Himawari probe receipt")
            previous = json.loads(pointer.read_bytes())
            name = previous.get("local_filename", "")
            if not re.fullmatch(r"[a-f0-9]{64}\.nc", name):
                raise ValueError("Invalid Himawari probe receipt filename")
            existing = directory / name
            if (
                existing.is_symlink()
                or existing.stat().st_size != previous["byte_count"]
                or file_sha256(existing) != previous["raw_sha256"]
                or previous.get("remote_path") != remote_path
            ):
                raise ValueError("Himawari immutable raw integrity failure")
            if previous["provider_md5"] == md5 and previous["byte_count"] == size:
                return {**previous, "reused_verified_raw": True}
        descriptor, name = tempfile.mkstemp(prefix=".himawari-", dir=directory)
        temporary = Path(name)
        sha, transport_hash = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
        total = 0
        with os.fdopen(descriptor, "wb") as handle:

            def receive(block):
                nonlocal total
                total += len(block)
                if total > size or total > MAX_FILE_BYTES:
                    raise ValueError("Himawari transfer exceeded expected bytes")
                sha.update(block)
                transport_hash.update(block)
                handle.write(block)

            client.retrbinary("RETR " + remote_path, receive, blocksize=65536)
            handle.flush()
            os.fsync(handle.fileno())
        if total != size or transport_hash.hexdigest() != md5:
            raise ValueError("Himawari provider checksum/size mismatch")
        with temporary.open("rb") as handle:
            if handle.read(8) != b"\x89HDF\r\n\x1a\n":
                raise ValueError(
                    "Himawari probe requires an uncompressed NetCDF4 container"
                )
        raw_hash = sha.hexdigest()
        destination = directory / (raw_hash + ".nc")
        if destination.exists():
            if destination.is_symlink() or file_sha256(destination) != raw_hash:
                raise ValueError("Himawari raw generation conflict")
            temporary.unlink()
        else:
            temporary.rename(destination)
        report = {
            "schema_version": 1,
            **identity,
            "host": HOST,
            "port": PORT,
            "protocol": "implicit_ftps",
            "source_uri": "ftps://" + HOST + ":990" + remote_path,
            "byte_count": total,
            "raw_sha256": raw_hash,
            "provider_md5": md5,
            "checksum_basis": "authenticated_provider_sidecar_and_local_sha256",
            "local_filename": destination.name,
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
            "scientific_validation": "pending",
            "reused_verified_raw": False,
        }
        atomic_json(pointer, report)
        return report
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink()
