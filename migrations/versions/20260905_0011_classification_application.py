"""Add resumable controlled classification applications."""

from alembic import op
import sqlalchemy as sa


revision = "20260905_0011"
down_revision = "20260905_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "classification_application",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.String(length=100), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("review_version", sa.Integer(), nullable=False),
        sa.Column("review_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("sample_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("rollback_of_application_id", sa.Uuid()),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_identity_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_stage", sa.String(length=32)),
        sa.Column("completed_stages_json", sa.JSON(), nullable=False),
        sa.Column("artifacts_json", sa.JSON(), nullable=False),
        sa.Column("results_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("recovery_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mode IN ('apply', 'rollback')", name="ck_classification_application_mode"),
        sa.CheckConstraint("review_version >= 1", name="ck_classification_application_review_version"),
        sa.CheckConstraint("status IN ('running', 'failed', 'applied', 'rolled_back')", name="ck_classification_application_status"),
        sa.CheckConstraint("current_stage IS NULL OR current_stage IN ('register_review', 'normalize', 'import', 'materialize', 'analyze', 'embed', 'provenance', 'finalize')", name="ck_classification_application_current_stage"),
        sa.CheckConstraint("(mode = 'rollback' AND rollback_of_application_id IS NOT NULL) OR (mode = 'apply' AND rollback_of_application_id IS NULL)", name="ck_classification_application_rollback_target"),
        sa.CheckConstraint("(status IN ('applied', 'rolled_back') AND finished_at IS NOT NULL AND error_code IS NULL) OR status NOT IN ('applied', 'rolled_back')", name="ck_classification_application_completion"),
        sa.CheckConstraint("(status = 'failed' AND error_code IS NOT NULL AND current_stage IS NOT NULL) OR status <> 'failed'", name="ck_classification_application_failure"),
        sa.ForeignKeyConstraint(["review_id"], ["classification_review.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rollback_of_application_id"], ["classification_application.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", name="uq_classification_application_operation_id"),
    )
    for column in ("operation_id", "review_id", "sample_id", "actor_user_id", "status"):
        op.create_index(f"ix_classification_application_{column}", "classification_application", [column])
    op.create_index(
        "uq_classification_application_running_review",
        "classification_application",
        ["review_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
        sqlite_where=sa.text("status = 'running'"),
    )

    op.create_table(
        "classification_application_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("recovery_json", sa.JSON(), nullable=False),
        sa.Column("event_sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint("event_type IN ('run_started', 'run_resumed', 'stage_started', 'stage_completed', 'stage_failed', 'run_applied', 'run_rolled_back', 'run_failed')", name="ck_classification_application_event_type"),
        sa.CheckConstraint("stage IS NULL OR stage IN ('register_review', 'normalize', 'import', 'materialize', 'analyze', 'embed', 'provenance', 'finalize')", name="ck_classification_application_event_stage"),
        sa.CheckConstraint("(event_type IN ('run_started', 'run_resumed', 'run_applied', 'run_rolled_back') AND stage IS NULL) OR (event_type IN ('stage_started', 'stage_completed', 'stage_failed', 'run_failed') AND stage IS NOT NULL)", name="ck_classification_application_event_stage_shape"),
        sa.CheckConstraint("sequence >= 1", name="ck_classification_application_event_sequence"),
        sa.ForeignKeyConstraint(["application_id"], ["classification_application.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "sequence", name="uq_classification_application_event_sequence"),
    )
    op.create_index("ix_classification_application_event_application_id", "classification_application_event", ["application_id"])
    op.execute(
        """
        CREATE TRIGGER classification_application_event_append_only
        BEFORE UPDATE OR DELETE ON classification_application_event
        FOR EACH ROW EXECUTE FUNCTION ocean_block_classification_review_event_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS classification_application_event_append_only ON classification_application_event")
    op.drop_table("classification_application_event")
    op.drop_table("classification_application")
