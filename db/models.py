"""
SQLAlchemy ORM models for all canonical tables, retrieval documents,
and cross-source links.

Uses pgvector for embedding storage and PostgreSQL tsvector for
full-text search.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None  # graceful fallback if pgvector not installed yet

import config


class CorpusBase(DeclarativeBase):
    pass


# Backward-compatible alias for modules that import the corpus metadata as
# ``Base``. Application identity/audit data deliberately lives on AppBase in
# db.app_models so a corpus rebuild can never drop it.
Base = CorpusBase


class CorpusPublication(CorpusBase):
    __tablename__ = "corpus_publication"
    channel = Column(String(64), primary_key=True)
    generation_id = Column(String(64), nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)


# -----------------------------------------------------------------------
# Layer 1: Provenance
# -----------------------------------------------------------------------
class ProvenanceRecord(CorpusBase):
    __tablename__ = "provenance_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_dataset = Column(String(64), nullable=False, index=True)
    source_file = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True)
    file_size_bytes = Column(Integer)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    processing_run = Column(String(64), index=True)
    notes = Column(Text)


# -----------------------------------------------------------------------
# Layer 3: Anchor events
# -----------------------------------------------------------------------
class AnchorEvent(CorpusBase):
    __tablename__ = "anchor_event"

    event_id = Column(String(128), primary_key=True)
    time_start = Column(String(32), index=True)
    time_end = Column(String(32))
    lat = Column(Float)
    lon = Column(Float)
    depth_min = Column(Float)
    depth_max = Column(Float)
    station_id = Column(String(32), index=True)
    sample_id = Column(String(64), index=True)
    bay_code = Column(String(4), index=True)
    source_types = Column(String(128))
    active = Column(Boolean, nullable=False, default=True, index=True)
    source_row_hash = Column(String(64), index=True)


# -----------------------------------------------------------------------
# Layer 3: CTD tables
# -----------------------------------------------------------------------
class CtdProfile(CorpusBase):
    __tablename__ = "ctd_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(String(64), nullable=False, index=True)
    ctd_date = Column(DateTime)
    depth_m = Column(Float)
    temperature = Column(Float)
    salinity = Column(Float)
    sigma_t = Column(Float)
    chl_a = Column(Float)
    chl_flu = Column(Float)
    do_percent = Column(Float)
    do_mg_l = Column(Float)
    turbidity = Column(Float)
    ec = Column(Float)
    ec25 = Column(Float)
    density = Column(Float)
    voltage = Column(Float)
    orp = Column(Float)
    ph = Column(Float)
    par = Column(Float)
    source_row_hash = Column(String(64), index=True)


class CtdSummary(CorpusBase):
    __tablename__ = "ctd_summary"

    sample_id = Column(String(64), primary_key=True)
    ctd_date = Column(DateTime)
    n_depth_points = Column(Integer)
    min_depth_m = Column(Float)
    max_depth_m = Column(Float)
    surface_temperature = Column(Float)
    bottom_temperature = Column(Float)
    mean_temperature = Column(Float)
    surface_salinity = Column(Float)
    bottom_salinity = Column(Float)
    mean_salinity = Column(Float)
    surface_do_percent = Column(Float)
    bottom_do_percent = Column(Float)
    mean_do_percent = Column(Float)
    surface_chl_a = Column(Float)
    bottom_chl_a = Column(Float)
    mean_chl_a = Column(Float)
    source_row_hash = Column(String(64), index=True)


# -----------------------------------------------------------------------
# Layer 3: Metagenome tables
# -----------------------------------------------------------------------
class MetagenomeSample(CorpusBase):
    __tablename__ = "metagenome_sample"

    sample_id = Column(String(64), primary_key=True)
    bay = Column(String(4), index=True)
    station_code = Column(String(16))
    sample_year_month = Column(String(8))
    n_runs = Column(Integer)
    first_run_date = Column(DateTime)
    last_run_date = Column(DateTime)
    sum_reads_gt1kb = Column(Float)
    sum_bases_gt1kb = Column(Float)
    has_kraken = Column(Boolean)
    has_metaeuk = Column(Boolean)
    has_ctd = Column(Boolean)
    top_kraken_genera_json = Column(Text)
    top_metaeuk_genera_json = Column(Text)
    top_upper_groups_json = Column(Text)
    source_row_hash = Column(String(64), index=True)


# -----------------------------------------------------------------------
# Layer 3: External source provenance and eDNA metabarcoding
# -----------------------------------------------------------------------
class ExternalSourceSnapshot(CorpusBase):
    __tablename__ = "external_source_snapshot"

    snapshot_id = Column(String(64), primary_key=True)
    provider = Column(String(64), nullable=False, index=True)
    source_family = Column(String(64), nullable=False, index=True)
    scope_url = Column(Text, nullable=False)
    scope_level = Column(String(32), nullable=False)
    source_collection_sha256 = Column(String(64), nullable=False)
    contract_version = Column(Integer, nullable=False)
    contract_sha256 = Column(String(64), nullable=False)
    selection_policy = Column(String(64), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False)
    file_count = Column(Integer, nullable=False)
    selected_file_count = Column(Integer, nullable=False)
    total_bytes = Column(BigInteger, nullable=False)
    status = Column(String(32), nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)
    manifest_summary_json = Column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "scope_level IN ('sample', 'run')",
            name="ck_external_source_snapshot_scope_level",
        ),
        CheckConstraint(
            "status = 'complete'",
            name="ck_external_source_snapshot_status",
        ),
        CheckConstraint(
            "file_count >= 0 AND selected_file_count >= 0 AND total_bytes >= 0",
            name="ck_external_source_snapshot_counts",
        ),
    )


class ExternalSourceFile(CorpusBase):
    __tablename__ = "external_source_file"

    source_file_id = Column(String(64), primary_key=True)
    snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    relative_path = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    sample_name = Column(Text, nullable=False, index=True)
    role = Column(String(64), nullable=False, index=True)
    selection_status = Column(String(32), nullable=False)
    size_bytes = Column(BigInteger)
    etag = Column(Text)
    last_modified = Column(Text)
    sha256 = Column(String(64), index=True)
    validation_status = Column(String(32), nullable=False)
    row_count = Column(Integer)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "relative_path",
            name="uq_external_source_file_snapshot_path",
        ),
        CheckConstraint(
            "selection_status IN ('selected', 'metadata_only', 'unknown')",
            name="ck_external_source_file_selection",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_external_source_file_size",
        ),
        CheckConstraint(
            "selection_status <> 'selected' OR "
            "(sha256 IS NOT NULL AND validation_status = 'valid')",
            name="ck_external_source_file_selected_valid",
        ),
    )


class EdnaSample(CorpusBase):
    __tablename__ = "edna_sample"

    sample_id = Column(String(64), primary_key=True)
    provider = Column(String(64), nullable=False, index=True)
    provider_sample_id = Column(Text, nullable=False)
    provider_project_id = Column(String(255), nullable=False, index=True)
    provider_run_id = Column(String(255), nullable=False, index=True)
    project_name = Column(Text, nullable=False)
    original_sample_label = Column(Text, nullable=False)
    sample_kind = Column(String(32), nullable=False, index=True)
    is_control = Column(Boolean, index=True)
    classification_basis = Column(Text, nullable=False)
    collection_date_utc = Column(String(40), index=True)
    temporal_precision = Column(String(16))
    lat = Column(Float, index=True)
    lon = Column(Float, index=True)
    raw_metadata_json = Column(Text, nullable=False)
    anchor_event_id = Column(String(128), index=True)
    source_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_file_id = Column(
        String(64),
        ForeignKey("external_source_file.source_file_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_row_numbers_json = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True, index=True)
    first_seen_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_seen_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scientific_content_sha256 = Column(String(64), nullable=False, index=True)
    source_row_hash = Column(String(64), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_sample_id",
            name="uq_edna_sample_provider_identity",
        ),
        CheckConstraint(
            "sample_kind IN ('environmental', 'negative_control', "
            "'positive_control', 'mock_community', 'unknown')",
            name="ck_edna_sample_kind",
        ),
        CheckConstraint(
            "lat IS NULL OR (lat >= -90 AND lat <= 90)",
            name="ck_edna_sample_lat",
        ),
        CheckConstraint(
            "lon IS NULL OR (lon >= -180 AND lon <= 180)",
            name="ck_edna_sample_lon",
        ),
    )


class EdnaAssay(CorpusBase):
    __tablename__ = "edna_assay"

    assay_id = Column(String(64), primary_key=True)
    sample_id = Column(
        String(64),
        ForeignKey("edna_sample.sample_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_gene = Column(Text, nullable=False)
    primer_set = Column(Text, nullable=False)
    sequencing_method = Column(Text, nullable=False)
    library_layout = Column(Text)
    instrument_model = Column(Text)
    raw_metadata_json = Column(Text, nullable=False)
    source_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_file_id = Column(
        String(64),
        ForeignKey("external_source_file.source_file_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_row_numbers_json = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True, index=True)
    first_seen_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_seen_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scientific_content_sha256 = Column(String(64), nullable=False, index=True)
    source_row_hash = Column(String(64), nullable=False, index=True)


class EdnaDetection(CorpusBase):
    __tablename__ = "edna_detection"

    detection_id = Column(String(64), primary_key=True)
    assay_id = Column(
        String(64),
        ForeignKey("edna_assay.assay_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assignment_method = Column(String(64), nullable=False, index=True)
    sequence = Column(Text, nullable=False)
    sequence_sha256 = Column(String(64), nullable=False, index=True)
    read_count = Column(BigInteger, nullable=False)
    copies_per_ml = Column(Float)
    superkingdom = Column(Text, index=True)
    kingdom = Column(Text, index=True)
    phylum = Column(Text, index=True)
    class_ = Column("class", Text, index=True)
    order = Column(Text, index=True)
    family = Column(Text, index=True)
    genus = Column(Text, index=True)
    species = Column(Text, index=True)
    subspecies = Column(Text, index=True)
    assigned_taxon_name = Column(Text, index=True)
    assigned_taxon_rank = Column(String(32), index=True)
    taxonomy_json = Column(Text, nullable=False)
    source_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_file_id = Column(
        String(64),
        ForeignKey("external_source_file.source_file_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_row_number = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=True, index=True)
    first_seen_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_seen_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scientific_content_sha256 = Column(String(64), nullable=False, index=True)
    source_row_hash = Column(String(64), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "assay_id",
            "assignment_method",
            "sequence_sha256",
            name="uq_edna_detection_identity",
        ),
        CheckConstraint(
            "assignment_method IN "
            "('qcauto_target', 'qcauto_95pct_3nn_target')",
            name="ck_edna_detection_assignment_method",
        ),
        CheckConstraint(
            "read_count >= 0",
            name="ck_edna_detection_read_count",
        ),
        CheckConstraint(
            "copies_per_ml IS NULL OR copies_per_ml >= 0",
            name="ck_edna_detection_copies",
        ),
        CheckConstraint(
            "source_row_number >= 2",
            name="ck_edna_detection_source_row",
        ),
    )


class EdnaInternalStandard(CorpusBase):
    __tablename__ = "edna_internal_standard"

    internal_standard_id = Column(String(64), primary_key=True)
    assay_id = Column(
        String(64),
        ForeignKey("edna_assay.assay_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    standard_name = Column(Text, nullable=False)
    sequence = Column(Text, nullable=False)
    sequence_sha256 = Column(String(64), nullable=False, index=True)
    read_count = Column(BigInteger, nullable=False)
    source_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_file_id = Column(
        String(64),
        ForeignKey("external_source_file.source_file_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_row_number = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=True, index=True)
    first_seen_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_seen_snapshot_id = Column(
        String(64),
        ForeignKey("external_source_snapshot.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scientific_content_sha256 = Column(String(64), nullable=False, index=True)
    source_row_hash = Column(String(64), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "assay_id",
            "standard_name",
            "sequence_sha256",
            name="uq_edna_internal_standard_identity",
        ),
        CheckConstraint(
            "read_count >= 0",
            name="ck_edna_internal_standard_read_count",
        ),
        CheckConstraint(
            "source_row_number >= 2",
            name="ck_edna_internal_standard_source_row",
        ),
    )


# -----------------------------------------------------------------------
# Layer 3: Remote sensing tables
# -----------------------------------------------------------------------
class SstPointObservation(CorpusBase):
    __tablename__ = "sst_point_observation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file = Column(String(128))
    time_utc = Column(DateTime, index=True)
    time_jst = Column(DateTime)
    sst = Column(Float)
    nearest_lat = Column(Float)
    nearest_lon = Column(Float)
    source_row_hash = Column(String(64), index=True)


class SstDailySummary(CorpusBase):
    __tablename__ = "sst_daily_summary"

    date_jst = Column(String(16), primary_key=True)
    mean_sst = Column(Float)
    min_sst = Column(Float)
    max_sst = Column(Float)
    std_sst = Column(Float)
    n_files = Column(Integer)
    source_row_hash = Column(String(64), index=True)


# -----------------------------------------------------------------------
# Layer 4: Retrieval documents
# -----------------------------------------------------------------------
class RetrievalDocument(CorpusBase):
    __tablename__ = "retrieval_document"

    doc_id = Column(String(128), primary_key=True)
    source_type = Column(String(32), nullable=False, index=True)
    sample_id = Column(String(64), index=True)
    event_id = Column(String(128), index=True)
    time = Column(String(32), index=True)
    lat = Column(Float)
    lon = Column(Float)
    bay = Column(String(4), index=True)
    station = Column(String(32))
    title = Column(Text, nullable=False)
    text = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    provider = Column(String(64), index=True)
    provider_project_id = Column(String(128), index=True)
    provider_run_id = Column(String(128), index=True)
    assay_id = Column(String(64), index=True)
    assignment_method = Column(String(64), index=True)
    sample_kind = Column(String(32), index=True)
    is_control = Column(Boolean, index=True)
    source_snapshot_id = Column(String(64), index=True)
    metadata_json = Column(Text, nullable=False, default="{}", server_default="{}")
    text_tsv = Column(TSVECTOR)  # full-text search vector
    source_row_hash = Column(String(64), index=True)
    embedding_provider = Column(String(32))
    embedding_model = Column(String(128))
    embedding_dim = Column(Integer)
    embedded_at = Column(DateTime(timezone=True))

    if Vector is not None:
        embedding = Column(Vector(config.EMBEDDING_DIM))

    __table_args__ = (
        Index("ix_retrieval_doc_text_fts", "text_tsv", postgresql_using="gin"),
        Index(
            "ix_retrieval_doc_edna_scope",
            "source_type",
            "active",
            "provider_project_id",
            "provider_run_id",
        ),
    )


# -----------------------------------------------------------------------
# Layer 4: Cross-source links
# -----------------------------------------------------------------------
class CrossSourceLink(CorpusBase):
    __tablename__ = "cross_source_link"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_event_id = Column(String(128), nullable=False, index=True)
    target_event_id = Column(String(128), nullable=False, index=True)
    link_type = Column(String(32), nullable=False)
    distance_km = Column(Float)
    time_delta_days = Column(Float)
    source_row_hash = Column(String(64), index=True)
