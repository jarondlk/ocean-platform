"""Add immutable sampling/product reviews without altering existing corpus rows."""

from alembic import op
import sqlalchemy as sa

revision = "20261004_0015"
down_revision = "20261001_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_registry_review",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("registry_key", sa.String(255), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "decided_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "applied_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
        ),
        sa.CheckConstraint(
            "kind IN ('sampling', 'sst_product')",
            name="ck_research_registry_review_kind",
        ),
        sa.CheckConstraint(
            "state IN ('draft', 'approved', 'rejected', 'applied')",
            name="ck_research_registry_review_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_research_registry_review_version"),
        sa.CheckConstraint(
            "state = 'draft' OR decided_by_user_id IS NOT NULL",
            name="ck_research_registry_review_decided",
        ),
        sa.CheckConstraint(
            "state <> 'applied' OR applied_by_user_id IS NOT NULL",
            name="ck_research_registry_review_applied",
        ),
    )
    op.create_index(
        "ix_research_registry_review_registry_key",
        "research_registry_review",
        ["registry_key"],
    )
    op.create_table(
        "research_registry_event",
        sa.Column(
            "review_id",
            sa.Uuid(),
            sa.ForeignKey("research_registry_review.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("event_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_research_registry_event_sequence"),
    )
    op.create_table(
        "research_registry_version",
        sa.Column("registry_id", sa.String(64), primary_key=True),
        sa.Column(
            "review_id",
            sa.Uuid(),
            sa.ForeignKey("research_registry_review.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("registry_key", sa.String(255), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_research_registry_version_registry_key",
        "research_registry_version",
        ["registry_key"],
    )
    op.create_table(
        "research_registry_head",
        sa.Column("registry_key", sa.String(255), primary_key=True),
        sa.Column(
            "registry_id",
            sa.String(64),
            sa.ForeignKey("research_registry_version.registry_id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_table(
        "research_physical_membership",
        sa.Column(
            "registry_id",
            sa.String(64),
            sa.ForeignKey("research_registry_version.registry_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("sample_id", sa.String(64), primary_key=True),
        sa.Column("physical_sample_id", sa.String(64), nullable=False),
        sa.Column("scientific_content_sha256", sa.String(64), nullable=False),
        sa.Column("representative_assay_id", sa.String(64), nullable=False),
        sa.Column("representative_assay_sha256", sa.String(64), nullable=False),
        sa.Column("area_id", sa.String(255), nullable=False),
        sa.Column("area_version", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_research_physical_membership_physical_sample_id",
        "research_physical_membership",
        ["physical_sample_id"],
    )
    op.create_table(
        "research_area_definition",
        sa.Column(
            "registry_id",
            sa.String(64),
            sa.ForeignKey("research_registry_version.registry_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("area_id", sa.String(255), primary_key=True),
        sa.Column("area_version", sa.String(64), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
    )
    op.execute("""CREATE FUNCTION ocean_research_immutable_record() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Research evidence records are immutable';
        END $$""")
    for table in (
        "research_registry_event",
        "research_registry_version",
        "research_physical_membership",
        "research_area_definition",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION ocean_research_immutable_record()"
        )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM research_registry_review)"))
        .scalar()
    ):
        raise RuntimeError(
            "Preserve research review history in a verified backup before downgrading"
        )
    for table in (
        "research_area_definition",
        "research_physical_membership",
        "research_registry_head",
        "research_registry_version",
        "research_registry_event",
        "research_registry_review",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION ocean_research_immutable_record()")
