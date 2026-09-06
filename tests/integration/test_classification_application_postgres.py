from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

import config
from api.classification_application_service import begin_application
from db.app_models import ClassificationApplicationEvent
from tests import test_classification_review_domain as review_fixture
from tests.test_classification_application import _approved


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires the disposable PostgreSQL integration service",
)


def test_application_receipts_are_append_only_and_running_review_is_unique(
    monkeypatch,
):
    identifiers = {
        "SNAPSHOT_ID": "f1" * 32,
        "OTHER_SNAPSHOT_ID": "f2" * 32,
        "SAMPLE_FILE_ID": "f3" * 32,
        "SAMPLE_FILE_SHA": "f4" * 32,
        "EXPERIMENT_FILE_ID": "f5" * 32,
        "EXPERIMENT_FILE_SHA": "f6" * 32,
        "SAMPLE_ID": "f7" * 32,
        "ASSAY_ID": "f8" * 32,
        "QC_FILE_ID": "f9" * 32,
        "QC_FILE_SHA": "fa" * 32,
        "THREE_NN_FILE_ID": "fb" * 32,
        "THREE_NN_FILE_SHA": "fc" * 32,
        "PROVIDER_SAMPLE_ID": "ANEMONE-PR4-INTEGRATION",
    }
    for name, value in identifiers.items():
        monkeypatch.setattr(review_fixture, name, value)

    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        users = review_fixture._seed(factory, detection_prefixes=("2", "3"))
        approved = _approved(factory, users)
        with factory() as session:
            application = begin_application(
                session,
                review_id=approved.id,
                operation_id="postgres-application",
                actor=users["admin"],
            )
            session.commit()
            event_id = session.scalar(
                select(ClassificationApplicationEvent.id).where(
                    ClassificationApplicationEvent.application_id == application.id
                )
            )

        for mutation in (
            "UPDATE classification_application_event "
            "SET result_json = '{}' WHERE id = :event_id",
            "DELETE FROM classification_application_event WHERE id = :event_id",
        ):
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="append-only"):
                connection.execute(text(mutation), {"event_id": event_id})
            savepoint.rollback()

        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match="running_review"):
            connection.execute(
                text(
                    """
                    INSERT INTO classification_application (
                        id, operation_id, review_id, review_version,
                        review_content_sha256, source_snapshot_id, sample_id,
                        mode, actor_user_id, actor_identity_json, status,
                        completed_stages_json, artifacts_json, results_json,
                        recovery_json, started_at
                    )
                    SELECT
                        :id, 'postgres-competing', review_id, review_version,
                        review_content_sha256, source_snapshot_id, sample_id,
                        'apply', actor_user_id, actor_identity_json, 'running',
                        '[]'::json, '{}'::json, '{}'::json, '[]'::json,
                        CURRENT_TIMESTAMP
                    FROM classification_application WHERE id = :application_id
                    """
                ),
                {"id": uuid.uuid4(), "application_id": application.id},
            )
        savepoint.rollback()
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
