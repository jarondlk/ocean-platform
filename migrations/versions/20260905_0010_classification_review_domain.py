"""Add authenticated classification reviews and append-only events."""

from alembic import op
import sqlalchemy as sa

revision = "20260905_0010"
down_revision = "20260905_0009"
branch_labels = None
depends_on = None


STATES = "'draft', 'approved', 'rejected', 'superseded', 'applied', 'failed'"


def upgrade():
    op.create_table(
        "classification_review",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("sample_id", sa.String(length=64), nullable=False),
        sa.Column("provider_sample_id", sa.Text(), nullable=False),
        sa.Column("sample_kind", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_review_id", sa.Uuid()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("scientific_decided_by_user_id", sa.Uuid()),
        sa.Column("scientific_decided_at", sa.DateTime(timezone=True)),
        sa.Column("operational_actor_user_id", sa.Uuid()),
        sa.Column("operational_at", sa.DateTime(timezone=True)),
        sa.Column("application_reference", sa.Text()),
        sa.Column("failure_code", sa.String(length=64)),
        sa.Column("failure_detail", sa.Text()),
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
            "sample_kind IN ('environmental', 'negative_control', "
            "'positive_control', 'mock_community', 'unknown')",
            name="ck_classification_review_sample_kind",
        ),
        sa.CheckConstraint(
            f"state IN ({STATES})",
            name="ck_classification_review_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_classification_review_version"),
        sa.CheckConstraint(
            "(state IN ('approved', 'rejected', 'superseded', 'applied', 'failed') "
            "AND scientific_decided_by_user_id IS NOT NULL "
            "AND scientific_decided_at IS NOT NULL) OR state = 'draft'",
            name="ck_classification_review_scientific_decision",
        ),
        sa.CheckConstraint(
            "(state = 'applied' AND operational_actor_user_id IS NOT NULL "
            "AND operational_at IS NOT NULL AND application_reference IS NOT NULL "
            "AND failure_code IS NULL) OR state <> 'applied'",
            name="ck_classification_review_applied",
        ),
        sa.CheckConstraint(
            "(state = 'failed' AND operational_actor_user_id IS NOT NULL "
            "AND operational_at IS NOT NULL AND failure_code IS NOT NULL) "
            "OR state <> 'failed'",
            name="ck_classification_review_failed",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_review_id"],
            ["classification_review.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["scientific_decided_by_user_id"],
            ["app_user.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operational_actor_user_id"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "source_snapshot_id",
        "sample_id",
        "content_sha256",
        "state",
        "created_by_user_id",
        "scientific_decided_by_user_id",
        "operational_actor_user_id",
    ):
        op.create_index(
            f"ix_classification_review_{column}",
            "classification_review",
            [column],
        )
    op.create_index(
        "uq_classification_review_current_sample",
        "classification_review",
        ["sample_id"],
        unique=True,
        postgresql_where=sa.text(
            "state IN ('approved', 'applied', 'failed')"
        ),
        sqlite_where=sa.text(
            "state IN ('approved', 'applied', 'failed')"
        ),
    )

    op.create_table(
        "classification_review_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_state", sa.String(length=32)),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("actor_identity_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("event_sha256", sa.String(length=64), nullable=False),
        sa.Column("review_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('created', 'draft_updated', 'approved', "
            "'rejected', 'superseded', 'applied', 'failed')",
            name="ck_classification_review_event_type",
        ),
        sa.CheckConstraint(
            f"to_state IN ({STATES})",
            name="ck_classification_review_event_state",
        ),
        sa.CheckConstraint(
            "actor_role IN ('researcher', 'admin')",
            name="ck_classification_review_event_actor_role",
        ),
        sa.CheckConstraint(
            "(event_type IN ('created', 'draft_updated', 'approved', "
            "'rejected', 'superseded') AND actor_role = 'researcher') OR "
            "(event_type IN ('applied', 'failed') AND actor_role = 'admin')",
            name="ck_classification_review_event_role",
        ),
        sa.CheckConstraint(
            "(event_type = 'created' AND from_state IS NULL "
            "AND to_state = 'draft') OR "
            "(event_type = 'draft_updated' AND from_state = 'draft' "
            "AND to_state = 'draft') OR "
            "(event_type IN ('approved', 'rejected') "
            "AND from_state = 'draft' AND to_state = event_type) OR "
            "(event_type = 'superseded' "
            "AND from_state IN ('approved', 'applied', 'failed') "
            "AND to_state = 'superseded') OR "
            "(event_type IN ('applied', 'failed') "
            "AND from_state IN ('approved', 'failed') "
            "AND to_state = event_type)",
            name="ck_classification_review_event_transition",
        ),
        sa.CheckConstraint(
            "sequence >= 1", name="ck_classification_review_event_sequence"
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["classification_review.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_id",
            "sequence",
            name="uq_classification_review_event_sequence",
        ),
    )
    op.create_index(
        "ix_classification_review_event_review_id",
        "classification_review_event",
        ["review_id"],
    )
    op.create_index(
        "ix_classification_review_event_actor_user_id",
        "classification_review_event",
        ["actor_user_id"],
    )
    op.execute(
        """
        CREATE FUNCTION ocean_block_classification_review_event_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'classification review events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER classification_review_event_append_only
        BEFORE UPDATE OR DELETE ON classification_review_event
        FOR EACH ROW EXECUTE FUNCTION ocean_block_classification_review_event_mutation()
        """
    )


def downgrade():
    op.execute(
        "DROP TRIGGER IF EXISTS classification_review_event_append_only "
        "ON classification_review_event"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS ocean_block_classification_review_event_mutation()"
    )
    op.drop_table("classification_review_event")
    op.drop_table("classification_review")
