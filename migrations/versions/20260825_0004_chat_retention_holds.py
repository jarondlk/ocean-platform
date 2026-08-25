"""Add explicit legal holds for retained chat interactions.

Revision ID: 20260825_0004
Revises: 20260820_0003
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0004"
down_revision: Union[str, None] = "20260820_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_interaction",
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_chat_interaction_retention",
        "chat_interaction",
        ["created_at", "legal_hold", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_interaction_retention", table_name="chat_interaction")
    op.drop_column("chat_interaction", "legal_hold")
