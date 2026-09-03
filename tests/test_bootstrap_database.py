from __future__ import annotations

import importlib

import scripts.bootstrap_database as bootstrap
from db.models import CorpusBase


def test_bootstrap_runs_migrations_before_corpus_initialization(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        bootstrap.command,
        "upgrade",
        lambda _configuration, revision: calls.append(f"alembic:{revision}"),
    )
    monkeypatch.setattr(
        bootstrap,
        "init_db",
        lambda: calls.append("init_db"),
    )
    monkeypatch.setattr(
        bootstrap,
        "database_status",
        lambda: {
            "ready": True,
            "vector_extension": True,
            "missing_tables": [],
            "table_count": len(bootstrap.REQUIRED_TABLES),
        },
    )

    status = bootstrap.bootstrap_database()

    assert calls == ["alembic:head", "init_db"]
    assert status["ready"] is True


def test_anemone_tables_are_required_and_defined_by_corpus_metadata():
    expected = {
        "external_source_snapshot",
        "external_source_file",
        "edna_sample",
        "edna_assay",
        "edna_detection",
        "edna_internal_standard",
    }

    assert expected.issubset(bootstrap.REQUIRED_TABLES)
    assert expected.issubset(CorpusBase.metadata.tables)
    assert "active" in CorpusBase.metadata.tables["anchor_event"].columns


def test_anemone_migration_extends_the_single_alembic_head():
    migration = importlib.import_module(
        "migrations.versions.20260901_0005_anemone_edna_corpus"
    )

    assert migration.revision == "20260901_0005"
    assert migration.down_revision == "20260825_0004"
