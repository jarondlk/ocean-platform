from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from db import backup


def test_postgres_tools_use_cloud_sql_query_socket_path():
    url = make_url(
        "postgresql://ocean_app:secret@/ocean_platform"
        "?host=/cloudsql/project:region:instance"
    )

    assert backup._connection_args(
        url,
        inside_database_container=False,
    ) == [
        "--host",
        "/cloudsql/project:region:instance",
        "--username",
        "ocean_app",
        "--dbname",
        "ocean_platform",
    ]
    assert backup._maintenance_connection_args(
        url,
        inside_database_container=False,
    ) == [
        "--host",
        "/cloudsql/project:region:instance",
        "--username",
        "ocean_app",
        "--maintenance-db",
        "postgres",
    ]
    assert backup._database_identity(url) == (
        "/cloudsql/project:region:instance/ocean_platform"
    )


def test_create_backup_is_atomic_hashed_and_structurally_verified(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        backup,
        "resolve_toolchain",
        lambda **_kwargs: backup.BackupToolchain(mode="native"),
    )
    monkeypatch.setattr(
        backup,
        "_table_counts",
        lambda _url: {"app_user": 2, "retrieval_document": 3},
    )
    monkeypatch.setattr(backup, "_archive_toc_entries", lambda *_args, **_kwargs: 9)

    def fake_run(_toolchain, tool, _args, **kwargs):
        assert tool == "pg_dump"
        kwargs["stdout"].write(b"custom-postgres-archive")
        return subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(backup, "_run_tool", fake_run)

    result = backup.create_backup(
        database_url="postgresql://user:secret@db:5432/onagawa",
        output_dir=tmp_path,
        label="before reset",
    )

    archive = Path(result.archive_path)
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert archive.read_bytes() == b"custom-postgres-archive"
    assert manifest["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert manifest["table_counts"] == {
        "app_user": 2,
        "retrieval_document": 3,
    }
    assert manifest["toc_entries"] == 9
    assert not list(tmp_path.glob("*.tmp"))


def test_verify_backup_rejects_digest_mismatch(tmp_path, monkeypatch):
    archive = tmp_path / "backup.dump"
    archive.write_bytes(b"archive")
    archive.with_suffix(".dump.json").write_text(
        json.dumps({"sha256": "0" * 64}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        backup,
        "resolve_toolchain",
        lambda **_kwargs: backup.BackupToolchain(mode="native"),
    )
    monkeypatch.setattr(backup, "_archive_toc_entries", lambda *_args, **_kwargs: 1)

    with pytest.raises(backup.BackupError, match="SHA-256 mismatch"):
        backup.verify_backup(
            archive,
            database_url="postgresql://user:secret@db/onagawa",
        )


def test_backup_capability_never_exposes_database_credentials(monkeypatch):
    monkeypatch.setattr(
        backup,
        "resolve_toolchain",
        lambda **_kwargs: backup.BackupToolchain(
            mode="container",
            runtime="/usr/bin/podman",
            container="postgres",
        ),
    )

    capability = backup.backup_capability()

    assert capability["available"] is True
    assert capability["detail"] == "podman exec postgres"
