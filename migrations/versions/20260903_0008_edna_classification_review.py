"""Retain reviewed sample classification separately from provider metadata."""

from alembic import op

revision = "20260903_0008"
down_revision = "20260902_0007"
branch_labels = None
depends_on = None


def upgrade():
    # The bootstrap path may already have created the current ORM schema.
    op.execute(
        "ALTER TABLE edna_sample ADD COLUMN IF NOT EXISTS classification_review_json TEXT"
    )


def downgrade():
    op.execute(
        "ALTER TABLE edna_sample DROP COLUMN IF EXISTS classification_review_json"
    )
