"""Verified PostgreSQL backup and restore helpers.

Backups use PostgreSQL's custom archive format, are written atomically, and
carry a sidecar manifest containing a SHA-256 digest and per-table row counts.
The helpers never place a database password on a process command line.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Optional

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, make_url

import config


RESTORE_TEST_PREFIX = "onagawa_restore_verify_"


class BackupError(RuntimeError):
    """Raised when a backup cannot be created or verified safely."""


@dataclass(frozen=True)
class BackupToolchain:
    mode: str
    runtime: Optional[str] = None
    container: Optional[str] = None


@dataclass(frozen=True)
class BackupResult:
    archive_path: str
    manifest_path: str
    sha256: str
    size_bytes: int
    table_count: int
    toc_entries: int
    created_at: str
    database: str
    toolchain: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_label(value: Optional[str]) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "backup")).strip(".-")
    return (cleaned or "backup")[:80]


def _database_url(value: Optional[str] = None) -> URL:
    url = make_url(value or config.DATABASE_URL)
    if not url.database or not url.drivername.startswith("postgresql"):
        raise BackupError("PostgreSQL DATABASE_URL with a database name is required")
    return url


def _database_identity(url: URL) -> str:
    host = _connection_host(url) or "local-socket"
    port = f":{url.port}" if url.port else ""
    return f"{host}{port}/{url.database}"


def _connection_host(url: URL) -> Optional[str]:
    """Return an authority host or PostgreSQL query-string socket path."""
    if url.host:
        return url.host
    query_host = url.query.get("host")
    return query_host if isinstance(query_host, str) and query_host else None


def resolve_toolchain(
    *,
    container: Optional[str] = None,
) -> BackupToolchain:
    if shutil.which("pg_dump") and shutil.which("pg_restore"):
        return BackupToolchain(mode="native")

    selected_container = (
        config.DATABASE_BACKUP_CONTAINER
        if container is None
        else container.strip()
    )
    runtime = shutil.which("podman") or shutil.which("docker")
    if selected_container and runtime:
        return BackupToolchain(
            mode="container",
            runtime=runtime,
            container=selected_container,
        )

    raise BackupError(
        "PostgreSQL client tools are unavailable. Install pg_dump/pg_restore "
        "or configure DATABASE_BACKUP_CONTAINER for a local database container."
    )


def backup_capability(*, container: Optional[str] = None) -> dict[str, Any]:
    try:
        toolchain = resolve_toolchain(container=container)
        return {
            "available": True,
            "mode": toolchain.mode,
            "container": toolchain.container,
            "detail": (
                "native pg_dump/pg_restore"
                if toolchain.mode == "native"
                else f"{Path(toolchain.runtime or '').name} exec {toolchain.container}"
            ),
        }
    except BackupError as exc:
        return {
            "available": False,
            "mode": None,
            "container": container,
            "detail": str(exc),
        }


def _client_environment(url: URL) -> dict[str, str]:
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    sslmode = url.query.get("sslmode")
    if sslmode:
        env["PGSSLMODE"] = sslmode
    return env


def _connection_args(url: URL, *, inside_database_container: bool) -> list[str]:
    args: list[str] = []
    if not inside_database_container:
        host = _connection_host(url)
        if host:
            args.extend(["--host", host])
        if url.port:
            args.extend(["--port", str(url.port)])
    if url.username:
        args.extend(["--username", url.username])
    args.extend(["--dbname", str(url.database)])
    return args


def _maintenance_connection_args(
    url: URL,
    *,
    inside_database_container: bool,
) -> list[str]:
    args: list[str] = []
    if not inside_database_container:
        host = _connection_host(url)
        if host:
            args.extend(["--host", host])
        if url.port:
            args.extend(["--port", str(url.port)])
    if url.username:
        args.extend(["--username", url.username])
    args.extend(["--maintenance-db", "postgres"])
    return args


def _tool_command(
    toolchain: BackupToolchain,
    tool: str,
    args: list[str],
) -> list[str]:
    if toolchain.mode == "native":
        executable = shutil.which(tool)
        if not executable:
            raise BackupError(f"Required PostgreSQL client tool is missing: {tool}")
        return [executable, *args]

    if not toolchain.runtime or not toolchain.container:
        raise BackupError("Invalid container backup toolchain")
    return [
        toolchain.runtime,
        "exec",
        "--interactive",
        "--env",
        "PGPASSWORD",
        toolchain.container,
        tool,
        *args,
    ]


def _run_tool(
    toolchain: BackupToolchain,
    tool: str,
    args: list[str],
    *,
    url: URL,
    stdin: Optional[BinaryIO] = None,
    stdout: Optional[BinaryIO | int] = subprocess.PIPE,
) -> subprocess.CompletedProcess[bytes]:
    command = _tool_command(toolchain, tool, args)
    try:
        return subprocess.run(
            command,
            env=_client_environment(url),
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as exc:
        raise BackupError(f"Backup executable is unavailable: {tool}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise BackupError(f"{tool} failed: {detail or 'no diagnostic output'}") from exc


def _table_counts(database_url: str) -> dict[str, int]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        table_names = sorted(inspector.get_table_names(schema="public"))
        preparer = engine.dialect.identifier_preparer
        counts: dict[str, int] = {}
        with engine.connect() as connection:
            for table_name in table_names:
                quoted = preparer.quote(table_name)
                count = connection.exec_driver_sql(
                    f"SELECT count(*) FROM {quoted}"
                ).scalar_one()
                counts[table_name] = int(count)
        return counts
    finally:
        engine.dispose()


def _archive_toc_entries(
    archive_path: Path,
    *,
    url: URL,
    toolchain: BackupToolchain,
) -> int:
    if toolchain.mode == "native":
        result = _run_tool(
            toolchain,
            "pg_restore",
            ["--list", str(archive_path)],
            url=url,
        )
    else:
        with archive_path.open("rb") as archive:
            result = _run_tool(
                toolchain,
                "pg_restore",
                ["--list"],
                url=url,
                stdin=archive,
            )
    output = (result.stdout or b"").decode("utf-8", errors="replace")
    entries = sum(
        1
        for line in output.splitlines()
        if line.strip() and not line.lstrip().startswith(";")
    )
    if entries == 0:
        raise BackupError("pg_restore found no entries in the backup archive")
    return entries


def create_backup(
    *,
    database_url: Optional[str] = None,
    output_dir: Optional[Path] = None,
    label: Optional[str] = None,
    container: Optional[str] = None,
) -> BackupResult:
    """Create and structurally verify an atomic PostgreSQL custom archive."""

    url = _database_url(database_url)
    url_text = url.render_as_string(hide_password=False)
    toolchain = resolve_toolchain(container=container)
    destination = Path(output_dir or config.DATABASE_BACKUP_DIR).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise BackupError(f"Backup destination is not a directory: {destination}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    database_name = _safe_label(str(url.database))
    filename = f"{timestamp}-{_safe_label(label)}-{database_name}.dump"
    archive_path = destination / filename
    temporary_path = destination / f".{filename}.{uuid.uuid4().hex}.tmp"
    manifest_path = archive_path.with_suffix(archive_path.suffix + ".json")

    table_counts = _table_counts(url_text)
    dump_args = [
        *_connection_args(
            url,
            inside_database_container=toolchain.mode == "container",
        ),
        "--format=custom",
        "--compress=6",
        "--no-owner",
        "--no-acl",
    ]
    try:
        with temporary_path.open("wb") as output:
            _run_tool(
                toolchain,
                "pg_dump",
                dump_args,
                url=url,
                stdout=output,
            )
        if temporary_path.stat().st_size == 0:
            raise BackupError("pg_dump created an empty archive")
        temporary_path.replace(archive_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    toc_entries = _archive_toc_entries(
        archive_path,
        url=url,
        toolchain=toolchain,
    )
    digest = _sha256_file(archive_path)
    result = BackupResult(
        archive_path=str(archive_path),
        manifest_path=str(manifest_path),
        sha256=digest,
        size_bytes=archive_path.stat().st_size,
        table_count=len(table_counts),
        toc_entries=toc_entries,
        created_at=_now_iso(),
        database=_database_identity(url),
        toolchain=toolchain.mode,
    )
    manifest = {
        "schema_version": 1,
        **asdict(result),
        "table_counts": table_counts,
        "restore_tested": False,
    }
    temporary_manifest = manifest_path.with_suffix(
        manifest_path.suffix + f".{uuid.uuid4().hex}.tmp"
    )
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest_path)
    return result


def verify_backup(
    archive_path: Path,
    *,
    database_url: Optional[str] = None,
    container: Optional[str] = None,
) -> dict[str, Any]:
    """Verify archive readability and its sidecar digest when available."""

    archive = archive_path.resolve()
    if not archive.is_file() or archive.stat().st_size == 0:
        raise BackupError(f"Backup archive is missing or empty: {archive}")
    url = _database_url(database_url)
    toolchain = resolve_toolchain(container=container)
    toc_entries = _archive_toc_entries(archive, url=url, toolchain=toolchain)
    digest = _sha256_file(archive)
    manifest_path = archive.with_suffix(archive.suffix + ".json")
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = str(manifest.get("sha256") or "")
        if expected and expected != digest:
            raise BackupError(
                f"Backup SHA-256 mismatch: expected {expected}, observed {digest}"
            )
    return {
        "ok": True,
        "archive_path": str(archive),
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "sha256": digest,
        "size_bytes": archive.stat().st_size,
        "toc_entries": toc_entries,
        "manifest": manifest,
    }


def _restore_archive(
    archive_path: Path,
    *,
    source_url: URL,
    target_url: URL,
    toolchain: BackupToolchain,
) -> None:
    args = [
        *_connection_args(
            target_url,
            inside_database_container=toolchain.mode == "container",
        ),
        "--exit-on-error",
        "--no-owner",
        "--no-acl",
    ]
    if toolchain.mode == "native":
        args.append(str(archive_path))
        _run_tool(
            toolchain,
            "pg_restore",
            args,
            url=target_url,
            stdout=subprocess.DEVNULL,
        )
    else:
        with archive_path.open("rb") as archive:
            _run_tool(
                toolchain,
                "pg_restore",
                args,
                url=target_url,
                stdin=archive,
                stdout=subprocess.DEVNULL,
            )


def restore_test(
    archive_path: Path,
    *,
    database_url: Optional[str] = None,
    container: Optional[str] = None,
) -> dict[str, Any]:
    """Restore into an isolated temporary database and compare table counts."""

    verification = verify_backup(
        archive_path,
        database_url=database_url,
        container=container,
    )
    source_url = _database_url(database_url)
    toolchain = resolve_toolchain(container=container)
    if toolchain.mode == "native" and (
        not shutil.which("createdb") or not shutil.which("dropdb")
    ):
        raise BackupError("createdb and dropdb are required for a restore test")

    target_name = f"{RESTORE_TEST_PREFIX}{uuid.uuid4().hex[:12]}"
    target_url = source_url.set(database=target_name)
    create_args = _maintenance_connection_args(
        source_url,
        inside_database_container=toolchain.mode == "container",
    )
    create_args.append(target_name)
    drop_args = [
        *_maintenance_connection_args(
            source_url,
            inside_database_container=toolchain.mode == "container",
        ),
        "--if-exists",
        "--force",
        target_name,
    ]

    restored_counts: dict[str, int] = {}
    try:
        _run_tool(
            toolchain,
            "createdb",
            create_args,
            url=source_url,
            stdout=subprocess.DEVNULL,
        )
        _restore_archive(
            archive_path.resolve(),
            source_url=source_url,
            target_url=target_url,
            toolchain=toolchain,
        )
        restored_counts = _table_counts(
            target_url.render_as_string(hide_password=False)
        )
        expected_counts = dict(
            verification.get("manifest", {}).get("table_counts") or {}
        )
        mismatches = {
            table: {
                "expected": expected,
                "restored": restored_counts.get(table),
            }
            for table, expected in expected_counts.items()
            if restored_counts.get(table) != expected
        }
        if mismatches:
            raise BackupError(
                "Restore row-count verification failed: "
                + json.dumps(mismatches, sort_keys=True)
            )
    finally:
        _run_tool(
            toolchain,
            "dropdb",
            drop_args,
            url=source_url,
            stdout=subprocess.DEVNULL,
        )

    manifest_path = archive_path.resolve().with_suffix(
        archive_path.suffix + ".json"
    )
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["restore_tested"] = True
        manifest["restore_tested_at"] = _now_iso()
        manifest["restored_table_counts"] = restored_counts
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return {
        "ok": True,
        "archive_path": str(archive_path.resolve()),
        "temporary_database": target_name,
        "restored_table_counts": restored_counts,
        "temporary_database_removed": True,
    }
