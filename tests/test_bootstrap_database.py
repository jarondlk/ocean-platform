from __future__ import annotations

import importlib
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

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


def test_classification_review_extends_schema_without_changing_raw_metadata():
    migration = importlib.import_module(
        "migrations.versions.20260903_0008_edna_classification_review"
    )
    assert migration.revision == "20260903_0008"
    assert migration.down_revision == "20260902_0007"
    table = CorpusBase.metadata.tables["edna_sample"]
    assert table.columns["classification_review_json"].nullable
    assert "raw_metadata_json" in table.columns


def test_chat_outcome_migration_extends_the_single_alembic_head():
    migration = importlib.import_module(
        "migrations.versions.20260905_0009_chat_outcome"
    )
    assert migration.revision == "20260905_0009"
    assert migration.down_revision == "20260903_0008"


def test_authenticated_classification_review_extends_the_single_alembic_head():
    migration = importlib.import_module(
        "migrations.versions.20260905_0010_classification_review_domain"
    )
    assert migration.revision == "20260905_0010"
    assert migration.down_revision == "20260905_0009"
    assert {
        "classification_review",
        "classification_review_event",
    }.issubset(bootstrap.REQUIRED_TABLES)


def test_controlled_application_extends_the_single_alembic_head():
    migration = importlib.import_module(
        "migrations.versions.20260905_0011_classification_application"
    )
    assert migration.revision == "20260905_0011"
    assert migration.down_revision == "20260905_0010"
    assert {
        "classification_application",
        "classification_application_event",
    }.issubset(bootstrap.REQUIRED_TABLES)


@pytest.mark.parametrize("column_present", [True, False])
def test_readiness_requires_review_column(monkeypatch, column_present):
    def columns(table_name):
        if table_name == "edna_sample":
            return ([{"name": "classification_review_json"}] if column_present else [])
        if table_name == "chat_interaction":
            return [{"name": "outcome"}, {"name": "abstention_reason"}]
        return []

    inspector = SimpleNamespace(
        get_table_names=lambda: list(bootstrap.REQUIRED_TABLES),
        get_columns=columns,
    )
    connection = SimpleNamespace(execute=lambda _: SimpleNamespace(scalar=lambda: True))
    monkeypatch.setattr(bootstrap, "get_engine", lambda: SimpleNamespace(connect=lambda: nullcontext(connection)))
    monkeypatch.setattr(bootstrap, "inspect", lambda _: inspector)
    status = bootstrap.database_status()
    assert status["ready"] is column_present
    assert status["missing_columns"] == ([] if column_present else ["edna_sample.classification_review_json"])


def test_readiness_requires_chat_outcome_columns(monkeypatch):
    def columns(table_name):
        if table_name == "edna_sample":
            return [{"name": "classification_review_json"}]
        if table_name == "chat_interaction":
            return [{"name": "outcome"}]
        return []

    inspector = SimpleNamespace(
        get_table_names=lambda: list(bootstrap.REQUIRED_TABLES),
        get_columns=columns,
    )
    connection = SimpleNamespace(execute=lambda _: SimpleNamespace(scalar=lambda: True))
    monkeypatch.setattr(bootstrap, "get_engine", lambda: SimpleNamespace(connect=lambda: nullcontext(connection)))
    monkeypatch.setattr(bootstrap, "inspect", lambda _: inspector)

    status = bootstrap.database_status()

    assert status["ready"] is False
    assert status["missing_columns"] == ["chat_interaction.abstention_reason"]
