"""Retain immutable exact-count evidence with application history."""

from alembic import op
import sqlalchemy as sa

revision = "20260925_0013"
down_revision = "20260924_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_chat_interaction_abstention_reason", "chat_interaction", type_="check"
    )
    op.create_check_constraint(
        "ck_chat_interaction_abstention_reason",
        "chat_interaction",
        "abstention_reason IS NULL OR abstention_reason IN ('no_matching_evidence','empty_analysis_cohort','publication_pending','aggregate_scope_required','aggregate_unavailable')",
    )
    op.create_table(
        "edna_aggregate_evidence",
        sa.Column("aggregate_id", sa.String(64), primary_key=True),
        sa.Column("algorithm_version", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM edna_aggregate_evidence)"))
        .scalar()
    ):
        raise RuntimeError(
            "Retain an application-history backup before downgrading aggregate evidence"
        )
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM chat_interaction WHERE abstention_reason IN ('aggregate_scope_required','aggregate_unavailable'))"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Retain aggregate chat history before downgrading")
    op.drop_constraint(
        "ck_chat_interaction_abstention_reason", "chat_interaction", type_="check"
    )
    op.create_check_constraint(
        "ck_chat_interaction_abstention_reason",
        "chat_interaction",
        "abstention_reason IS NULL OR abstention_reason IN ('no_matching_evidence','empty_analysis_cohort','publication_pending')",
    )
    op.drop_table("edna_aggregate_evidence")
