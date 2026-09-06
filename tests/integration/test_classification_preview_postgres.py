from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

import config
from api.classification_review_service import create_draft, preview_review
from api.schemas import (
    ClassificationReviewDraftCreate,
    ClassificationReviewPreviewRequest,
)
from db.app_models import ClassificationReview, ClassificationReviewEvent
from db.models import EdnaSample
from tests import test_classification_review_domain as review_fixture


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires the disposable PostgreSQL integration service",
)


def test_preview_uses_repeatable_read_and_keeps_canonical_state(monkeypatch):
    identifiers = {
        "SNAPSHOT_ID": "e1" * 32,
        "OTHER_SNAPSHOT_ID": "e2" * 32,
        "SAMPLE_FILE_ID": "e3" * 32,
        "SAMPLE_FILE_SHA": "e4" * 32,
        "EXPERIMENT_FILE_ID": "e5" * 32,
        "EXPERIMENT_FILE_SHA": "e6" * 32,
        "SAMPLE_ID": "e7" * 32,
        "ASSAY_ID": "e8" * 32,
        "QC_FILE_ID": "e9" * 32,
        "QC_FILE_SHA": "ea" * 32,
        "THREE_NN_FILE_ID": "eb" * 32,
        "THREE_NN_FILE_SHA": "ec" * 32,
        "PROVIDER_SAMPLE_ID": "ANEMONE-PR3-INTEGRATION",
    }
    for name, value in identifiers.items():
        monkeypatch.setattr(review_fixture, name, value)

    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    connection = engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    )
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        users = review_fixture._seed(factory, detection_prefixes=("0", "1"))
        with factory() as session:
            review = create_draft(
                session,
                request=ClassificationReviewDraftCreate.model_validate(
                    review_fixture._draft_payload(sample_kind="environmental")
                ),
                actor=users["researcher"],
            )
            session.commit()

        with factory() as session:
            preview = preview_review(
                session,
                review_id=review.id,
                request=ClassificationReviewPreviewRequest(
                    expected_version=review.version,
                    rank="genus",
                    min_read_count=2,
                ),
                actor=users["admin"],
            )
            assert (
                session.scalar(text("SHOW transaction_isolation"))
                == "repeatable read"
            )
            assert preview.baseline.eligibility == "excluded"
            assert preview.proposed.eligibility == "included"
            assert preview.table_count_delta["diversity"] == 2
            assert session.scalar(
                select(func.count(ClassificationReviewEvent.id)).where(
                    ClassificationReviewEvent.review_id == review.id
                )
            ) == 1
            stored = session.get(ClassificationReview, review.id)
            sample = session.get(EdnaSample, review_fixture.SAMPLE_ID)
            assert stored.state == "draft"
            assert stored.version == 1
            assert sample.sample_kind == "unknown"
            assert sample.is_control is None
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
