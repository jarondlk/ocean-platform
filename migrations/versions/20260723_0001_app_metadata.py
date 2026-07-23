"""Create durable application metadata tables.

Revision ID: 20260723_0001
Revises:
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("auth_provider", sa.String(length=64), nullable=False),
        sa.Column("auth_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "account_type IN ('research', 'commercial', 'internal')",
            name="ck_app_user_account_type",
        ),
        sa.CheckConstraint(
            "role IN ('viewer', 'researcher', 'admin')",
            name="ck_app_user_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_app_user_status",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["app_user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "auth_provider",
            "auth_subject",
            name="uq_app_user_provider_subject",
        ),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_app_user_email"), "app_user", ["email"], unique=False)

    op.create_table(
        "user_invitation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "account_type IN ('research', 'commercial', 'internal')",
            name="ck_user_invitation_account_type",
        ),
        sa.CheckConstraint(
            "role IN ('viewer', 'researcher', 'admin')",
            name="ck_user_invitation_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_user_invitation_status",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["app_user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(
        op.f("ix_user_invitation_email"),
        "user_invitation",
        ["email"],
        unique=False,
    )

    op.create_table(
        "chat_interaction",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("request_options", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("answer_audit_snapshot", sa.JSON(), nullable=True),
        sa.Column("corpus_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_chat_interaction_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_interaction_user_id"),
        "chat_interaction",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_audit_event_action"),
        "audit_event",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_audit_event_created_at",
        "audit_event",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_event_actor_user_id"),
        "audit_event",
        ["actor_user_id"],
        unique=False,
    )

    op.create_table(
        "chat_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interaction_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating IN (-1, 1)",
            name="ck_chat_feedback_rating",
        ),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["chat_interaction.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "interaction_id",
            "user_id",
            name="uq_chat_feedback_interaction_user",
        ),
    )
    op.create_index(
        op.f("ix_chat_feedback_user_id"),
        "chat_feedback",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_feedback_user_id"), table_name="chat_feedback")
    op.drop_table("chat_feedback")
    op.drop_index(
        op.f("ix_audit_event_actor_user_id"),
        table_name="audit_event",
    )
    op.drop_index("ix_audit_event_created_at", table_name="audit_event")
    op.drop_index(op.f("ix_audit_event_action"), table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index(
        op.f("ix_chat_interaction_user_id"),
        table_name="chat_interaction",
    )
    op.drop_table("chat_interaction")
    op.drop_index(
        op.f("ix_user_invitation_email"),
        table_name="user_invitation",
    )
    op.drop_table("user_invitation")
    op.drop_index(op.f("ix_app_user_email"), table_name="app_user")
    op.drop_table("app_user")
