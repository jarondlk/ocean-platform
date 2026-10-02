"""Allow explicit source-selection and freshness abstentions in chat history."""
from alembic import op
import sqlalchemy as sa

revision = "20261001_0014"
down_revision = "20260925_0013"
branch_labels = None
depends_on = None

OLD_REASONS = "'no_matching_evidence','empty_analysis_cohort','publication_pending','aggregate_scope_required','aggregate_unavailable'"
NEW_REASONS = "'no_sources_selected','source_disabled','freshness_unavailable'"


def _constraint(reasons):
    op.drop_constraint("ck_chat_interaction_abstention_reason", "chat_interaction", type_="check")
    op.create_check_constraint("ck_chat_interaction_abstention_reason", "chat_interaction",
                               f"abstention_reason IS NULL OR abstention_reason IN ({reasons})")


def upgrade():
    _constraint(OLD_REASONS + ',' + NEW_REASONS)


def downgrade():
    if op.get_bind().execute(sa.text(
        f"SELECT EXISTS (SELECT 1 FROM chat_interaction WHERE abstention_reason IN ({NEW_REASONS}))"
    )).scalar():
        raise RuntimeError("Retain source-settings chat history before downgrading")
    _constraint(OLD_REASONS)
