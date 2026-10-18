"""Add private v1 investigations and immutable context preparation history."""

from alembic import op
import sqlalchemy as sa

revision = "20261018_0017"
down_revision = "20261005_0016"
branch_labels = None
depends_on = None


def _sha256_check(column):
    remaining = column
    for character in "0123456789abcdef":
        remaining = f"replace({remaining}, '{character}', '')"
    return f"length({column}) = 64 AND {remaining} = ''"


def _created_at():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _updated_at():
    return sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade():
    op.create_table(
        "research_investigation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("metadata_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("head_revision_id", sa.Uuid()),
        sa.Column("predecessor_investigation_id", sa.Uuid()),
        sa.Column("predecessor_revision_id", sa.Uuid()),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        _created_at(), _updated_at(),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("id", "user_id", name="uq_research_investigation_owner"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 255 AND length(trim(name)) >= 1", name="ck_research_investigation_name"),
        sa.CheckConstraint("metadata_version >= 1", name="ck_research_investigation_version"),
        sa.CheckConstraint("status IN ('preparing', 'active', 'archived', 'retired')", name="ck_research_investigation_status"),
        sa.CheckConstraint(
            "(predecessor_investigation_id IS NULL AND predecessor_revision_id IS NULL) OR "
            "(predecessor_investigation_id IS NOT NULL AND predecessor_revision_id IS NOT NULL)",
            name="ck_research_investigation_predecessor_pair",
        ),
        sa.CheckConstraint("predecessor_investigation_id IS NULL OR predecessor_investigation_id <> id", name="ck_research_investigation_predecessor_other"),
        sa.ForeignKeyConstraint(
            ["predecessor_investigation_id", "user_id"],
            ["research_investigation.id", "research_investigation.user_id"],
            name="fk_research_investigation_predecessor_owner", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_research_investigation_user_id", "research_investigation", ["user_id"])
    op.create_index("ix_research_investigation_retention", "research_investigation", ["updated_at", "legal_hold", "status"])
    op.create_table(
        "research_conversation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("research_investigation.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("metadata_version", sa.Integer(), nullable=False),
        _created_at(), _updated_at(),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 255 AND length(trim(name)) >= 1", name="ck_research_conversation_name"),
        sa.CheckConstraint("metadata_version >= 1", name="ck_research_conversation_version"),
    )
    op.create_index("ix_research_conversation_investigation_id", "research_conversation", ["investigation_id"])
    op.create_table(
        "research_context_revision",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("research_investigation.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("predecessor_revision_id", sa.Uuid()),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
        _created_at(),
        sa.UniqueConstraint("investigation_id", "sequence", name="uq_research_context_revision_sequence"),
        sa.UniqueConstraint("investigation_id", "id", name="uq_research_context_revision_identity"),
        sa.CheckConstraint("sequence >= 1", name="ck_research_context_revision_sequence"),
        sa.CheckConstraint(_sha256_check("snapshot_id"), name="ck_research_context_revision_snapshot"),
        sa.CheckConstraint(_sha256_check("payload_sha256"), name="ck_research_context_revision_payload_hash"),
        sa.CheckConstraint("predecessor_revision_id IS NULL OR predecessor_revision_id <> id", name="ck_research_context_revision_predecessor_other"),
        sa.ForeignKeyConstraint(
            ["investigation_id", "created_by_user_id"],
            ["research_investigation.id", "research_investigation.user_id"],
            name="fk_research_context_revision_owner", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "predecessor_revision_id"],
            ["research_context_revision.investigation_id", "research_context_revision.id"],
            name="fk_research_context_revision_predecessor", ondelete="RESTRICT",
        ),
    )
    for name, columns in (
        ("fk_research_investigation_head", ["id", "head_revision_id"]),
        ("fk_research_investigation_predecessor_revision", ["predecessor_investigation_id", "predecessor_revision_id"]),
    ):
        op.create_foreign_key(
            name, "research_investigation", "research_context_revision", columns,
            ["investigation_id", "id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED",
        )
    op.create_table(
        "research_context_operation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("research_investigation.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("expected_head_id", sa.Uuid()),
        sa.Column("candidate_revision_id", sa.Uuid()),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("candidate_json", sa.Text(), nullable=False),
        sa.Column("references_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64)),
        _created_at(), _updated_at(),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_research_context_operation_idempotency"),
        sa.CheckConstraint("length(idempotency_key) BETWEEN 1 AND 128", name="ck_research_context_operation_key"),
        sa.CheckConstraint("length(kind) BETWEEN 1 AND 32", name="ck_research_context_operation_kind"),
        sa.CheckConstraint(_sha256_check("request_sha256"), name="ck_research_context_operation_request_hash"),
        sa.CheckConstraint("state IN ('prepared', 'committed', 'conflict', 'unavailable', 'uncertain')", name="ck_research_context_operation_state"),
        sa.CheckConstraint("error_code IS NULL OR length(error_code) BETWEEN 1 AND 64", name="ck_research_context_operation_error"),
        sa.ForeignKeyConstraint(
            ["investigation_id", "user_id"],
            ["research_investigation.id", "research_investigation.user_id"],
            name="fk_research_context_operation_owner", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "expected_head_id"],
            ["research_context_revision.investigation_id", "research_context_revision.id"],
            name="fk_research_context_operation_expected_head", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_research_context_operation_investigation_id", "research_context_operation", ["investigation_id"])
    op.execute("""CREATE FUNCTION ocean_context_revision_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Research context revisions are append-only';
        END $$""")
    op.execute("""CREATE TRIGGER research_context_revision_immutable
        BEFORE UPDATE OR DELETE ON research_context_revision
        FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable()""")
    for table in ("research_investigation", "research_conversation", "research_context_revision", "research_context_operation"):
        op.execute(f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()")
    protected = {
        "research_investigation": ("id", "user_id", "predecessor_investigation_id", "predecessor_revision_id", "created_at"),
        "research_conversation": ("id", "investigation_id", "created_at"),
        "research_context_operation": (
            "id", "user_id", "investigation_id", "idempotency_key", "kind",
            "expected_head_id", "candidate_revision_id", "request_json", "request_sha256",
            "candidate_json", "references_json", "created_at",
        ),
    }
    for table, columns in protected.items():
        changed = " OR ".join(f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in columns)
        op.execute(f"""CREATE FUNCTION ocean_{table}_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Research context records are retained';
              END IF;
              IF {changed} THEN
                RAISE EXCEPTION 'Research context identity and prepared inputs are immutable';
              END IF;
              RETURN NEW;
            END $$""")
        op.execute(f"CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION ocean_{table}_guard()")


def downgrade():
    # The rollout rollback disables capabilities; it never erases retained history.
    # Hold one transactional lock across emptiness checks and drops so a racing
    # runtime insert cannot turn a verified empty downgrade into history loss.
    op.execute("LOCK TABLE research_investigation, research_conversation, "
               "research_context_revision, research_context_operation IN ACCESS EXCLUSIVE MODE")
    for table in ("research_investigation", "research_conversation", "research_context_revision", "research_context_operation"):
        if op.get_bind().execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Retain investigation history; populated C17 storage cannot be downgraded")
    op.drop_table("research_context_operation")
    op.drop_table("research_conversation")
    op.drop_constraint("fk_research_investigation_head", "research_investigation", type_="foreignkey")
    op.drop_constraint("fk_research_investigation_predecessor_revision", "research_investigation", type_="foreignkey")
    op.drop_table("research_context_revision")
    op.drop_table("research_investigation")
    op.execute("DROP FUNCTION ocean_context_revision_immutable()")
    for table in ("research_investigation", "research_conversation", "research_context_operation"):
        op.execute(f"DROP FUNCTION ocean_{table}_guard()")
