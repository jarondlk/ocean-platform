"""Coordinate immutable corpus publication generations."""
from alembic import op

revision = "20260902_0007"
down_revision = "20260902_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TABLE IF NOT EXISTS corpus_publication (channel VARCHAR(64) PRIMARY KEY, generation_id VARCHAR(64) NOT NULL, manifest_sha256 VARCHAR(64) NOT NULL)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS corpus_publication")
