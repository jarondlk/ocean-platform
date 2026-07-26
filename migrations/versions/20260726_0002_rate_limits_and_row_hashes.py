"""Add shared rate-limit counters and corpus row hashes.

Revision ID: 20260726_0002
Revises: 20260723_0001
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0002"
down_revision: Union[str, None] = "20260723_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CORPUS_TABLES = (
    "anchor_event",
    "ctd_profile",
    "ctd_summary",
    "metagenome_sample",
    "sst_point_observation",
    "sst_daily_summary",
    "retrieval_document",
    "cross_source_link",
)


def upgrade() -> None:
    op.create_table(
        "rate_limit_bucket",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "window_started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "request_count >= 0",
            name="ck_rate_limit_bucket_request_count",
        ),
        sa.PrimaryKeyConstraint("scope", "subject_hash"),
    )
    op.create_index(
        "ix_rate_limit_bucket_updated_at",
        "rate_limit_bucket",
        ["updated_at"],
        unique=False,
    )

    # Alembic owns the application-metadata tables, while the regenerable
    # scientific corpus tables are created by ``db.connection.init_db``.
    # Existing deployments may already have the corpus tables when this
    # revision runs, but a fresh CI/production database does not.
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in CORPUS_TABLES:
        if table_name not in existing_tables:
            continue
        op.execute(
            sa.text(
                f"""
                ALTER TABLE IF EXISTS {table_name}
                ADD COLUMN IF NOT EXISTS source_row_hash VARCHAR(64)
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table_name}_source_row_hash
                ON {table_name} (source_row_hash)
                """
            )
        )


def downgrade() -> None:
    for table_name in reversed(CORPUS_TABLES):
        op.execute(
            sa.text(
                f"""
                DROP INDEX IF EXISTS ix_{table_name}_source_row_hash
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                ALTER TABLE IF EXISTS {table_name}
                DROP COLUMN IF EXISTS source_row_hash
                """
            )
        )
    op.drop_index(
        "ix_rate_limit_bucket_updated_at",
        table_name="rate_limit_bucket",
    )
    op.drop_table("rate_limit_bucket")
