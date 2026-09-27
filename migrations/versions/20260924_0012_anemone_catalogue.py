"""ANEMONE catalogue namespaces and source evidence; preserve pilot IDs."""

from alembic import op
import sqlalchemy as sa

revision = "20260924_0012"
down_revision = "20260905_0011"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column(
            "provider_locus", sa.String(128), nullable=False, server_default="MiFish"
        ),
        sa.Column(
            "provider_team", sa.String(128), nullable=False, server_default="ANEMONE"
        ),
        sa.Column("source_occurrence_id", sa.String(64)),
        sa.Column("physical_sample_id", sa.String(64)),
        sa.Column(
            "identity_status",
            sa.String(64),
            nullable=False,
            server_default="unresolved_physical_sample",
        ),
        sa.Column(
            "coordinate_precision",
            sa.String(64),
            nullable=False,
            server_default="unspecified",
        ),
        sa.Column("raw_metadata_rows_json", sa.Text()),
        sa.Column("provider_note_json", sa.Text()),
    ):
        op.add_column("edna_sample", column)
    op.drop_constraint(
        "uq_edna_sample_provider_identity", "edna_sample", type_="unique"
    )
    op.create_unique_constraint(
        "uq_edna_sample_provider_identity",
        "edna_sample",
        [
            "provider",
            "provider_locus",
            "provider_team",
            "provider_project_id",
            "provider_run_id",
            "provider_sample_id",
        ],
    )
    op.create_unique_constraint(
        "uq_edna_sample_source_occurrence", "edna_sample", ["source_occurrence_id"]
    )
    op.create_index(
        "ix_edna_sample_physical_sample_id", "edna_sample", ["physical_sample_id"]
    )
    op.create_index(
        "ix_edna_sample_namespace",
        "edna_sample",
        [
            "provider",
            "provider_locus",
            "provider_team",
            "provider_project_id",
            "provider_run_id",
        ],
    )
    for name in ("raw_metadata_rows_json", "community_availability_json"):
        op.add_column("edna_assay", sa.Column(name, sa.Text()))
    op.add_column("edna_detection", sa.Column("assignment_algorithm", sa.String(32)))
    op.add_column(
        "edna_detection",
        sa.Column(
            "target_status", sa.String(16), nullable=False, server_default="target"
        ),
    )
    op.add_column("edna_detection", sa.Column("concentration_status", sa.String(32)))
    op.execute(
        "UPDATE edna_detection SET assignment_algorithm = CASE WHEN assignment_method = 'qcauto_target' THEN 'qcauto' ELSE 'qcauto_95pct_3nn' END"
    )
    op.drop_constraint(
        "ck_edna_detection_assignment_method", "edna_detection", type_="check"
    )
    op.create_check_constraint(
        "ck_edna_detection_assignment_method",
        "edna_detection",
        "assignment_method IN ('qcauto_target', 'qcauto_95pct_3nn_target', 'qcauto_nontarget', 'qcauto_95pct_3nn_nontarget')",
    )
    op.create_check_constraint(
        "ck_edna_detection_target_status",
        "edna_detection",
        "target_status IN ('target', 'nontarget') AND ((target_status = 'target' AND assignment_method IN ('qcauto_target', 'qcauto_95pct_3nn_target')) OR (target_status = 'nontarget' AND assignment_method IN ('qcauto_nontarget', 'qcauto_95pct_3nn_nontarget')))",
    )
    op.create_index(
        "ix_edna_detection_assignment_algorithm",
        "edna_detection",
        ["assignment_algorithm"],
    )
    op.create_index(
        "ix_edna_detection_target_status", "edna_detection", ["target_status"]
    )
    op.create_index(
        "ix_edna_detection_active_assay_method",
        "edna_detection",
        ["assay_id", "assignment_method", "detection_id"],
        postgresql_where=sa.text("active IS TRUE"),
    )


def downgrade():
    # Do not discard non-target data or merge newly distinguished namespaces.
    bind = op.get_bind()
    if bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM edna_detection WHERE target_status <> 'target') OR EXISTS (SELECT 1 FROM edna_sample GROUP BY provider, provider_sample_id HAVING count(*) > 1)"
        )
    ).scalar():
        raise RuntimeError(
            "Restore a compatible pre-catalogue backup before downgrading"
        )
    for name in (
        "ix_edna_detection_active_assay_method",
        "ix_edna_detection_target_status",
        "ix_edna_detection_assignment_algorithm",
    ):
        op.drop_index(name, table_name="edna_detection")
    op.drop_constraint(
        "ck_edna_detection_target_status", "edna_detection", type_="check"
    )
    op.drop_constraint(
        "ck_edna_detection_assignment_method", "edna_detection", type_="check"
    )
    op.create_check_constraint(
        "ck_edna_detection_assignment_method",
        "edna_detection",
        "assignment_method IN ('qcauto_target', 'qcauto_95pct_3nn_target')",
    )
    for name in ("concentration_status", "target_status", "assignment_algorithm"):
        op.drop_column("edna_detection", name)
    for name in ("community_availability_json", "raw_metadata_rows_json"):
        op.drop_column("edna_assay", name)
    op.drop_index("ix_edna_sample_namespace", table_name="edna_sample")
    op.drop_index("ix_edna_sample_physical_sample_id", table_name="edna_sample")
    op.drop_constraint(
        "uq_edna_sample_source_occurrence", "edna_sample", type_="unique"
    )
    op.drop_constraint(
        "uq_edna_sample_provider_identity", "edna_sample", type_="unique"
    )
    op.create_unique_constraint(
        "uq_edna_sample_provider_identity",
        "edna_sample",
        ["provider", "provider_sample_id"],
    )
    for name in (
        "provider_note_json",
        "raw_metadata_rows_json",
        "coordinate_precision",
        "identity_status",
        "physical_sample_id",
        "source_occurrence_id",
        "provider_team",
        "provider_locus",
    ):
        op.drop_column("edna_sample", name)
