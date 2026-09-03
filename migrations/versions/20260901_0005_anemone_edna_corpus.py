"""Add external-source provenance and canonical eDNA corpus tables.

Revision ID: 20260901_0005
Revises: 20260825_0004
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260901_0005"
down_revision: Union[str, None] = "20260825_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _hash_columns() -> list[sa.Column]:
    return [
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("last_seen_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("scientific_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
    ]


def _source_foreign_keys() -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["external_source_snapshot.snapshot_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["external_source_file.source_file_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_snapshot_id"],
            ["external_source_snapshot.snapshot_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_snapshot_id"],
            ["external_source_snapshot.snapshot_id"],
            ondelete="RESTRICT",
        ),
    ]


def upgrade() -> None:
    # Existing deployments already have the regenerable anchor table. Fresh
    # databases create it after Alembic through CorpusBase.metadata.create_all.
    op.execute(
        sa.text(
            """
            ALTER TABLE IF EXISTS anchor_event
            ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF to_regclass('anchor_event') IS NOT NULL THEN
                    CREATE INDEX IF NOT EXISTS ix_anchor_event_active
                    ON anchor_event (active);
                END IF;
            END
            $$
            """
        )
    )
    op.create_table(
        "external_source_snapshot",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("scope_url", sa.Text(), nullable=False),
        sa.Column("scope_level", sa.String(length=32), nullable=False),
        sa.Column("source_collection_sha256", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("contract_sha256", sa.String(length=64), nullable=False),
        sa.Column("selection_policy", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("selected_file_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_summary_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "scope_level IN ('sample', 'run')",
            name="ck_external_source_snapshot_scope_level",
        ),
        sa.CheckConstraint(
            "status = 'complete'",
            name="ck_external_source_snapshot_status",
        ),
        sa.CheckConstraint(
            "file_count >= 0 AND selected_file_count >= 0 AND total_bytes >= 0",
            name="ck_external_source_snapshot_counts",
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index(
        "ix_external_source_snapshot_provider",
        "external_source_snapshot",
        ["provider"],
    )
    op.create_index(
        "ix_external_source_snapshot_source_family",
        "external_source_snapshot",
        ["source_family"],
    )

    op.create_table(
        "external_source_file",
        sa.Column("source_file_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("sample_name", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("selection_status", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("etag", sa.Text()),
        sa.Column("last_modified", sa.Text()),
        sa.Column("sha256", sa.String(length=64)),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("row_count", sa.Integer()),
        sa.CheckConstraint(
            "selection_status IN ('selected', 'metadata_only', 'unknown')",
            name="ck_external_source_file_selection",
        ),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_external_source_file_size",
        ),
        sa.CheckConstraint(
            "selection_status <> 'selected' OR "
            "(sha256 IS NOT NULL AND validation_status = 'valid')",
            name="ck_external_source_file_selected_valid",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["external_source_snapshot.snapshot_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("source_file_id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "relative_path",
            name="uq_external_source_file_snapshot_path",
        ),
    )
    for column in ("snapshot_id", "sample_name", "role", "sha256"):
        op.create_index(
            f"ix_external_source_file_{column}",
            "external_source_file",
            [column],
        )

    op.create_table(
        "edna_sample",
        sa.Column("sample_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_sample_id", sa.Text(), nullable=False),
        sa.Column("provider_project_id", sa.String(length=255), nullable=False),
        sa.Column("provider_run_id", sa.String(length=255), nullable=False),
        sa.Column("project_name", sa.Text(), nullable=False),
        sa.Column("original_sample_label", sa.Text(), nullable=False),
        sa.Column("sample_kind", sa.String(length=32), nullable=False),
        sa.Column("is_control", sa.Boolean()),
        sa.Column("classification_basis", sa.Text(), nullable=False),
        sa.Column("collection_date_utc", sa.String(length=40)),
        sa.Column("temporal_precision", sa.String(length=16)),
        sa.Column("lat", sa.Float()),
        sa.Column("lon", sa.Float()),
        sa.Column("raw_metadata_json", sa.Text(), nullable=False),
        sa.Column("anchor_event_id", sa.String(length=128)),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("source_file_id", sa.String(length=64), nullable=False),
        sa.Column("source_row_numbers_json", sa.Text(), nullable=False),
        *_hash_columns(),
        sa.CheckConstraint(
            "sample_kind IN ('environmental', 'negative_control', "
            "'positive_control', 'mock_community', 'unknown')",
            name="ck_edna_sample_kind",
        ),
        sa.CheckConstraint(
            "lat IS NULL OR (lat >= -90 AND lat <= 90)",
            name="ck_edna_sample_lat",
        ),
        sa.CheckConstraint(
            "lon IS NULL OR (lon >= -180 AND lon <= 180)",
            name="ck_edna_sample_lon",
        ),
        *_source_foreign_keys(),
        sa.PrimaryKeyConstraint("sample_id"),
        sa.UniqueConstraint(
            "provider",
            "provider_sample_id",
            name="uq_edna_sample_provider_identity",
        ),
    )
    for column in (
        "provider",
        "provider_project_id",
        "provider_run_id",
        "sample_kind",
        "is_control",
        "collection_date_utc",
        "lat",
        "lon",
        "anchor_event_id",
        "active",
        "scientific_content_sha256",
        "source_row_hash",
    ):
        op.create_index(f"ix_edna_sample_{column}", "edna_sample", [column])

    op.create_table(
        "edna_assay",
        sa.Column("assay_id", sa.String(length=64), nullable=False),
        sa.Column("sample_id", sa.String(length=64), nullable=False),
        sa.Column("target_gene", sa.Text(), nullable=False),
        sa.Column("primer_set", sa.Text(), nullable=False),
        sa.Column("sequencing_method", sa.Text(), nullable=False),
        sa.Column("library_layout", sa.Text()),
        sa.Column("instrument_model", sa.Text()),
        sa.Column("raw_metadata_json", sa.Text(), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("source_file_id", sa.String(length=64), nullable=False),
        sa.Column("source_row_numbers_json", sa.Text(), nullable=False),
        *_hash_columns(),
        sa.ForeignKeyConstraint(
            ["sample_id"], ["edna_sample.sample_id"], ondelete="RESTRICT"
        ),
        *_source_foreign_keys(),
        sa.PrimaryKeyConstraint("assay_id"),
    )
    for column in (
        "sample_id",
        "active",
        "scientific_content_sha256",
        "source_row_hash",
    ):
        op.create_index(f"ix_edna_assay_{column}", "edna_assay", [column])

    op.create_table(
        "edna_detection",
        sa.Column("detection_id", sa.String(length=64), nullable=False),
        sa.Column("assay_id", sa.String(length=64), nullable=False),
        sa.Column("assignment_method", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Text(), nullable=False),
        sa.Column("sequence_sha256", sa.String(length=64), nullable=False),
        sa.Column("read_count", sa.BigInteger(), nullable=False),
        sa.Column("copies_per_ml", sa.Float()),
        sa.Column("superkingdom", sa.Text()),
        sa.Column("kingdom", sa.Text()),
        sa.Column("phylum", sa.Text()),
        sa.Column("class", sa.Text()),
        sa.Column("order", sa.Text()),
        sa.Column("family", sa.Text()),
        sa.Column("genus", sa.Text()),
        sa.Column("species", sa.Text()),
        sa.Column("subspecies", sa.Text()),
        sa.Column("assigned_taxon_name", sa.Text()),
        sa.Column("assigned_taxon_rank", sa.String(length=32)),
        sa.Column("taxonomy_json", sa.Text(), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("source_file_id", sa.String(length=64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        *_hash_columns(),
        sa.CheckConstraint(
            "assignment_method IN "
            "('qcauto_target', 'qcauto_95pct_3nn_target')",
            name="ck_edna_detection_assignment_method",
        ),
        sa.CheckConstraint("read_count >= 0", name="ck_edna_detection_read_count"),
        sa.CheckConstraint(
            "copies_per_ml IS NULL OR copies_per_ml >= 0",
            name="ck_edna_detection_copies",
        ),
        sa.CheckConstraint(
            "source_row_number >= 2",
            name="ck_edna_detection_source_row",
        ),
        sa.ForeignKeyConstraint(
            ["assay_id"], ["edna_assay.assay_id"], ondelete="RESTRICT"
        ),
        *_source_foreign_keys(),
        sa.PrimaryKeyConstraint("detection_id"),
        sa.UniqueConstraint(
            "assay_id",
            "assignment_method",
            "sequence_sha256",
            name="uq_edna_detection_identity",
        ),
    )
    for column in (
        "assay_id",
        "assignment_method",
        "sequence_sha256",
        "superkingdom",
        "kingdom",
        "phylum",
        "class",
        "order",
        "family",
        "genus",
        "species",
        "subspecies",
        "assigned_taxon_name",
        "assigned_taxon_rank",
        "active",
        "scientific_content_sha256",
        "source_row_hash",
    ):
        op.create_index(
            f"ix_edna_detection_{column}",
            "edna_detection",
            [column],
        )

    op.create_table(
        "edna_internal_standard",
        sa.Column("internal_standard_id", sa.String(length=64), nullable=False),
        sa.Column("assay_id", sa.String(length=64), nullable=False),
        sa.Column("standard_name", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Text(), nullable=False),
        sa.Column("sequence_sha256", sa.String(length=64), nullable=False),
        sa.Column("read_count", sa.BigInteger(), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("source_file_id", sa.String(length=64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        *_hash_columns(),
        sa.CheckConstraint(
            "read_count >= 0",
            name="ck_edna_internal_standard_read_count",
        ),
        sa.CheckConstraint(
            "source_row_number >= 2",
            name="ck_edna_internal_standard_source_row",
        ),
        sa.ForeignKeyConstraint(
            ["assay_id"], ["edna_assay.assay_id"], ondelete="RESTRICT"
        ),
        *_source_foreign_keys(),
        sa.PrimaryKeyConstraint("internal_standard_id"),
        sa.UniqueConstraint(
            "assay_id",
            "standard_name",
            "sequence_sha256",
            name="uq_edna_internal_standard_identity",
        ),
    )
    for column in (
        "assay_id",
        "sequence_sha256",
        "active",
        "scientific_content_sha256",
        "source_row_hash",
    ):
        op.create_index(
            f"ix_edna_internal_standard_{column}",
            "edna_internal_standard",
            [column],
        )


def downgrade() -> None:
    op.drop_table("edna_internal_standard")
    op.drop_table("edna_detection")
    op.drop_table("edna_assay")
    op.drop_table("edna_sample")
    op.drop_table("external_source_file")
    op.drop_table("external_source_snapshot")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_anchor_event_active"))
    op.execute(
        sa.text(
            """
            ALTER TABLE IF EXISTS anchor_event
            DROP COLUMN IF EXISTS active
            """
        )
    )
