"""Add structured metadata for ANEMONE retrieval documents.

Revision ID: 20260902_0006
Revises: 20260901_0005
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260902_0006"
down_revision: Union[str, None] = "20260901_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Regenerable corpus tables may be created before or after Alembic. The
    # ORM covers fresh databases; these statements upgrade existing tables.
    columns = (
        "active BOOLEAN NOT NULL DEFAULT TRUE",
        "provider VARCHAR(64)",
        "provider_project_id VARCHAR(128)",
        "provider_run_id VARCHAR(128)",
        "assay_id VARCHAR(64)",
        "assignment_method VARCHAR(64)",
        "sample_kind VARCHAR(32)",
        "is_control BOOLEAN",
        "source_snapshot_id VARCHAR(64)",
        "metadata_json TEXT NOT NULL DEFAULT '{}'",
    )
    for definition in columns:
        op.execute(
            sa.text(
                "ALTER TABLE IF EXISTS retrieval_document "
                f"ADD COLUMN IF NOT EXISTS {definition}"
            )
        )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF to_regclass('retrieval_document') IS NOT NULL THEN
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_active
                    ON retrieval_document (active);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_provider
                    ON retrieval_document (provider);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_provider_project_id
                    ON retrieval_document (provider_project_id);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_provider_run_id
                    ON retrieval_document (provider_run_id);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_assay_id
                    ON retrieval_document (assay_id);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_assignment_method
                    ON retrieval_document (assignment_method);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_sample_kind
                    ON retrieval_document (sample_kind);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_is_control
                    ON retrieval_document (is_control);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_document_source_snapshot_id
                    ON retrieval_document (source_snapshot_id);
                    CREATE INDEX IF NOT EXISTS ix_retrieval_doc_edna_scope
                    ON retrieval_document (
                        source_type,
                        active,
                        provider_project_id,
                        provider_run_id
                    );
                END IF;
            END
            $$
            """
        )
    )


def downgrade() -> None:
    for index_name in (
        "ix_retrieval_doc_edna_scope",
        "ix_retrieval_document_source_snapshot_id",
        "ix_retrieval_document_is_control",
        "ix_retrieval_document_sample_kind",
        "ix_retrieval_document_assignment_method",
        "ix_retrieval_document_assay_id",
        "ix_retrieval_document_provider_run_id",
        "ix_retrieval_document_provider_project_id",
        "ix_retrieval_document_provider",
        "ix_retrieval_document_active",
    ):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
    for column_name in (
        "metadata_json",
        "source_snapshot_id",
        "is_control",
        "sample_kind",
        "assignment_method",
        "assay_id",
        "provider_run_id",
        "provider_project_id",
        "provider",
        "active",
    ):
        op.execute(
            sa.text(
                "ALTER TABLE IF EXISTS retrieval_document "
                f"DROP COLUMN IF EXISTS {column_name}"
            )
        )
