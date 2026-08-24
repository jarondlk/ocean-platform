"""Track the provider identity of retrieval embeddings.

Revision ID: 20260820_0003
Revises: 20260726_0002
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0003"
down_revision: Union[str, None] = "20260726_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The regenerable corpus may be created either before or after Alembic.
    # db.models covers fresh databases; this migration upgrades existing ones.
    for column in (
        "embedding_provider VARCHAR(32)",
        "embedding_model VARCHAR(128)",
        "embedding_dim INTEGER",
        "embedded_at TIMESTAMPTZ",
    ):
        op.execute(
            sa.text(
                f"""
                ALTER TABLE IF EXISTS retrieval_document
                ADD COLUMN IF NOT EXISTS {column}
                """
            )
        )


def downgrade() -> None:
    for column in (
        "embedded_at",
        "embedding_dim",
        "embedding_model",
        "embedding_provider",
    ):
        op.execute(
            sa.text(
                f"""
                ALTER TABLE IF EXISTS retrieval_document
                DROP COLUMN IF EXISTS {column}
                """
            )
        )
