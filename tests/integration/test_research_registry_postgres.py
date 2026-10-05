"""Run only against a disposable PostgreSQL database, never the retained candidate."""

import importlib
import json
import os
import uuid
from datetime import datetime

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

import config
from api import research_registry_service as service
from db.app_models import AppBase, AppUser
from db.models import (
    CorpusBase,
    EdnaSample,
    EdnaAssay,
    EdnaDetection,
    EdnaInternalStandard,
    ExternalSourceFile,
    ExternalSourceSnapshot,
    CorpusPublication,
)
from tests.research_fixtures import research_fixture
from tests.test_classification_review_domain import _seed, _current, SAMPLE_ID, ASSAY_ID
from tests.test_edna_analysis import fixture as legacy_fixture
from tests.test_research_analysis_bundle import publication_fixture

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires disposable PostgreSQL",
)


def seed_research_cohort(factory):
    """Synthetic full canonical records, with real review/application transitions."""
    recipe, source, registry = publication_fixture()
    _, prototype = legacy_fixture()
    models = (
        ExternalSourceSnapshot,
        ExternalSourceFile,
        EdnaSample,
        EdnaAssay,
        EdnaDetection,
    )
    with factory.begin() as session:
        actors = {}
        for role in ("viewer", "researcher", "admin"):
            actor = AppUser(
                id=uuid.uuid4(),
                email=f"{role}@mock.invalid",
                auth_provider="mock-credentials",
                auth_subject=f"mock-login:{role}",
                role=role,
                account_type="research",
                status="active",
            )
            session.add(actor)
            actors[role] = _current(actor)
        for model in models:
            name = model.__tablename__
            columns = {column.name: column for column in model.__table__.columns}
            for raw in source[name]:
                row = {**prototype[name][0], **raw}
                if name == "edna_sample":
                    row["provider_sample_id"] = row["sample_id"]
                if name == "edna_detection":
                    row["sequence_sha256"] = row["detection_id"]
                row = {k: v for k, v in row.items() if k in columns}
                for key, value in row.items():
                    if isinstance(value, (dict, list)):
                        row[key] = json.dumps(value)
                    elif columns[key].type.python_type is datetime and isinstance(
                        value, str
                    ):
                        row[key] = datetime.fromisoformat(value)
                session.execute(model.__table__.insert(), row)
        canonical = dict(
            generation_id=recipe.canonical_generation, manifest_sha256="b" * 64
        )
        for channel in ("anemone-canonical", "edna-canonical", "edna"):
            session.add(CorpusPublication(channel=channel, **canonical))
    with factory.begin() as session:
        draft = service.create_draft(
            session,
            kind="sampling",
            payload=registry["definition"],
            actor=actors["researcher"],
        )
        approved = service.decide(
            session,
            uuid.UUID(draft["review_id"]),
            approve=True,
            version=draft["version"],
            content_sha256=draft["content_sha256"],
            rationale="Hand-calculated synthetic test cohort",
            actor=actors["researcher"],
        )
        applied = service.apply(
            session,
            uuid.UUID(draft["review_id"]),
            version=approved["version"],
            content_sha256=approved["content_sha256"],
            actor=actors["admin"],
        )
    return recipe, actors, applied


def test_consistent_snapshot_batch_publication_and_stale_sources(tmp_path, monkeypatch):
    from ingestion import research_analysis_bundle as research
    from ingestion.edna_analysis_bundle import (
        publish_analysis,
        load_analysis,
        analysis_status,
    )

    schema = "research_test_" + uuid.uuid4().hex
    admin = create_engine(config.DATABASE_URL)
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        config.DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        AppBase.metadata.create_all(engine)
        CorpusBase.metadata.create_all(
            engine,
            tables=[
                m.__table__
                for m in (
                    ExternalSourceSnapshot,
                    ExternalSourceFile,
                    EdnaSample,
                    EdnaAssay,
                    EdnaDetection,
                    EdnaInternalStandard,
                    CorpusPublication,
                )
            ],
        )
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        recipe, _, applied = seed_research_cohort(factory)
        monkeypatch.setattr(research, "get_engine", lambda: engine)
        monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
        monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
        source, registry, panel = research.read_snapshot(recipe, applied["registry_id"])
        assert len(source["edna_sample"]) == 15
        assert len(source["edna_detection"]) == 45  # One method only.
        assert panel is None
        assert (
            source["generations"]["classification_generation"]
            == recipe.classification_generation
        )
        result = research.build_research_analysis(recipe, source, registry)
        publish_analysis(result)
        bundle = load_analysis(result["analysis_id"])
        assert analysis_status(bundle) == "current"
        sardine = next(
            row
            for row in bundle["tables"]["ranking"]
            if row["species"] == "Sardinops melanostictus"
        )
        assert sardine["detected"] == 7 and sardine["eligible"] == 15
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE edna_detection SET read_count=read_count+1 WHERE read_count=0"
                )
            )
        assert analysis_status(bundle) == "historical"
        assert load_analysis(result["analysis_id"])["tables"] == bundle["tables"]
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE edna_sample SET scientific_content_sha256=:sha"),
                {"sha": "f" * 64},
            )
        assert analysis_status(bundle) == "historical"
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM corpus_publication WHERE channel='edna'")
            )
        assert analysis_status(bundle) == "current_state_unavailable"
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_additive_migration_immutable_events_and_guarded_downgrade():
    schema = "research_test_" + uuid.uuid4().hex
    admin = create_engine(config.DATABASE_URL)
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        config.DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}
    )
    migration = importlib.import_module(
        "migrations.versions.20261004_0015_research_registries"
    )
    try:
        AppBase.metadata.create_all(
            engine,
            tables=[
                table
                for table in AppBase.metadata.sorted_tables
                if not table.name.startswith("research_")
            ],
        )
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        CorpusBase.metadata.create_all(
            engine,
            tables=[
                model.__table__
                for model in (
                    ExternalSourceSnapshot,
                    ExternalSourceFile,
                    EdnaSample,
                    EdnaAssay,
                    EdnaDetection,
                    EdnaInternalStandard,
                )
            ],
        )
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        actors = _seed(factory)
        f = research_fixture()
        value = {
            "schema_version": 1,
            "region_id": "fixture-region",
            "areas": [f[2][0].model_dump(mode="json")],
            "memberships": [f[3][0].model_dump(mode="json")],
        }
        value["memberships"][0].update(
            occurrences=[dict(sample_id=SAMPLE_ID, scientific_content_sha256="8" * 64)],
            representative_assay_id=ASSAY_ID,
            representative_assay_sha256="e" * 64,
        )
        with factory.begin() as session:
            draft = service.create_draft(
                session, kind="sampling", payload=value, actor=actors["researcher"]
            )
            approved = service.decide(
                session,
                uuid.UUID(draft["review_id"]),
                approve=True,
                version=1,
                content_sha256=draft["content_sha256"],
                rationale="Synthetic evidence",
                actor=actors["researcher"],
            )
            applied = service.apply(
                session,
                uuid.UUID(draft["review_id"]),
                version=approved["version"],
                content_sha256=approved["content_sha256"],
                actor=actors["admin"],
            )
        with factory() as session:
            assert (
                service.read_registry(session, applied["registry_id"])["definition"]
                == value
            )
            assert session.get(EdnaSample, SAMPLE_ID).physical_sample_id is None
        for sql in (
            "UPDATE research_registry_event SET payload_json='{}'",
            "DELETE FROM research_registry_version",
        ):
            with pytest.raises(DBAPIError, match="immutable"):
                with engine.begin() as connection:
                    connection.execute(text(sql))
        with pytest.raises(RuntimeError, match="Preserve research review history"):
            with (
                engine.begin() as connection,
                Operations.context(MigrationContext.configure(connection)),
            ):
                migration.downgrade()
    finally:
        engine.dispose()
        # The test owns this newly created schema and all its synthetic rows.
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()
