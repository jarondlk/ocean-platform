"""Record deterministic chat abstention outcomes."""

from alembic import op

revision = "20260905_0009"
down_revision = "20260903_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE chat_interaction "
        "ADD COLUMN IF NOT EXISTS outcome VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE chat_interaction "
        "ADD COLUMN IF NOT EXISTS abstention_reason VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE chat_interaction DROP CONSTRAINT IF EXISTS "
        "ck_chat_interaction_outcome"
    )
    op.execute(
        "ALTER TABLE chat_interaction ADD CONSTRAINT "
        "ck_chat_interaction_outcome CHECK "
        "(outcome IS NULL OR outcome IN ('answered', 'abstained'))"
    )
    op.execute(
        "ALTER TABLE chat_interaction DROP CONSTRAINT IF EXISTS "
        "ck_chat_interaction_abstention_reason"
    )
    op.execute(
        "ALTER TABLE chat_interaction ADD CONSTRAINT "
        "ck_chat_interaction_abstention_reason CHECK "
        "(abstention_reason IS NULL OR abstention_reason IN "
        "('no_matching_evidence', 'empty_analysis_cohort', "
        "'publication_pending'))"
    )
    op.execute(
        "ALTER TABLE chat_interaction DROP CONSTRAINT IF EXISTS "
        "ck_chat_interaction_outcome_reason"
    )
    op.execute(
        "ALTER TABLE chat_interaction ADD CONSTRAINT "
        "ck_chat_interaction_outcome_reason CHECK "
        "((outcome IS NULL AND abstention_reason IS NULL) OR "
        "(outcome = 'answered' AND abstention_reason IS NULL) OR "
        "(outcome = 'abstained' AND abstention_reason IS NOT NULL))"
    )


def downgrade():
    op.execute(
        "ALTER TABLE chat_interaction DROP CONSTRAINT IF EXISTS "
        "ck_chat_interaction_outcome_reason"
    )
    op.execute(
        "ALTER TABLE chat_interaction DROP CONSTRAINT IF EXISTS "
        "ck_chat_interaction_abstention_reason"
    )
    op.execute(
        "ALTER TABLE chat_interaction DROP CONSTRAINT IF EXISTS "
        "ck_chat_interaction_outcome"
    )
    op.execute(
        "ALTER TABLE chat_interaction "
        "DROP COLUMN IF EXISTS abstention_reason"
    )
    op.execute(
        "ALTER TABLE chat_interaction DROP COLUMN IF EXISTS outcome"
    )
