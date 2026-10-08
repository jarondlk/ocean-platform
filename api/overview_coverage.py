"""Read-only, source-level temporal coverage for the Overview dashboard."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import re
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq
from pydantic import BaseModel, Field
from sqlalchemy import text

import config
from db.connection import get_engine


CALENDAR = "Asia/Tokyo"
MAX_RECORDS = 100_000
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_MISSING_DATES = 366
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SOURCE_DEFINITIONS = (
    ("ctd", "CTD casts", "casts", "day", "ctd_date", "Normalized CTD casts"),
    ("metagenome", "Metagenome samples", "samples", "month", "sample_year_month", "Samples with Kraken or MetaEuk data"),
    ("edna_metabarcoding", "ANEMONE eDNA", "occurrences", "mixed", "collection_date_utc", "All active provider occurrences, including controls and unknown classifications"),
    ("remote_sensing", "Satellite SST", "days", "day", "date_jst", "Daily summaries with usable mean SST"),
)


class CoverageBin(BaseModel):
    month: str
    count: int
    observed_days: int | None = None
    expected_days: int | None = None
    missing_days: int | None = None


class CoverageSource(BaseModel):
    id: str
    label: str
    count_unit: str
    temporal_precision: str
    date_basis: str
    scope: str
    status: Literal["available", "empty", "unavailable"] = "unavailable"
    reason: str | None = None
    observed_start: str | None = None
    observed_end: str | None = None
    total_count: int | None = None
    undated_count: int | None = None
    excluded_count: int | None = None
    source_binding: dict[str, str] = Field(default_factory=dict)
    categories: dict[str, int] = Field(default_factory=dict)
    bins: list[CoverageBin] = Field(default_factory=list)
    missing_dates_within_extent: list[str] = Field(default_factory=list)
    missing_day_count: int | None = None
    missing_dates_truncated: bool = False


class OverviewCoverage(BaseModel):
    calendar: str = CALENDAR
    resolution: str = "month"
    generated_at: str
    sources: list[CoverageSource]


def source_definition(identity: str) -> CoverageSource:
    for source_id, label, unit, precision, basis, scope in SOURCE_DEFINITIONS:
        if source_id == identity:
            return CoverageSource(id=identity, label=label, count_unit=unit,
                                  temporal_precision=precision, date_basis=basis, scope=scope)
    raise ValueError("Unknown coverage source")


def calendar_value(value, precision: str) -> str | None:
    """Keep coarse dates coarse; only zoned instants are converted to JST."""
    if value is None or pd.isna(value):
        return None
    raw = str(value)
    try:
        if precision == "month":
            if not re.fullmatch(r"\d{4}-\d{2}", raw):
                return None
            parsed = date.fromisoformat(raw + "-01")
            result = raw
        elif precision == "date":
            # Parquet may represent a calendar date as a naive midnight Timestamp.
            # Only that lossless date representation is accepted; other instants
            # require their original datetime precision and timezone.
            if isinstance(value, datetime):
                if value.tzinfo is not None or value.time() != datetime.min.time():
                    return None
                raw = value.date().isoformat()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                return None
            parsed = date.fromisoformat(raw)
            result = parsed.isoformat()
        elif precision == "datetime":
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                return None
            parsed = stamp.astimezone(ZoneInfo(CALENDAR)).date()
            result = parsed.isoformat()
        else:
            return None
        return result if 1900 <= parsed.year <= 2100 else None
    except (ValueError, TypeError):
        return None


def aggregate_source(identity: str, records: list[tuple[str, str | None]], *,
                     binding=None, categories=None, excluded=0, expected_windows=None) -> CoverageSource:
    """Count source units once; contradictory dates fail rather than picking one."""
    source = source_definition(identity)
    unique: dict[str, str | None] = {}
    for record_id, when in records:
        if not record_id:
            raise ValueError("Missing source identity")
        if record_id in unique and unique[record_id] != when:
            raise ValueError("Conflicting source dates")
        unique[record_id] = when
    dates = sorted(value for value in unique.values() if value is not None)
    months = Counter(value[:7] for value in dates)
    days: dict[str, set[str]] = {}
    for value in dates:
        if len(value) == 10:
            days.setdefault(value[:7], set()).add(value)
    source.status = "available" if dates else "empty"
    source.total_count = len(unique)
    source.undated_count = sum(value is None for value in unique.values())
    source.excluded_count = excluded
    source.source_binding = binding or {}
    source.categories = categories or {}
    source.observed_start = dates[0] if dates else None
    source.observed_end = dates[-1] if dates else None
    source.bins = [CoverageBin(month=month, count=count,
                              observed_days=len(days[month]) if month in days else None)
                   for month, count in sorted(months.items())]
    if identity == "remote_sensing":
        source.missing_day_count = 0
        if dates:
            available = set(dates)
            expected = Counter()
            expected_dates = set()
            for first, last in expected_windows or [(dates[0], dates[-1])]:
                cursor, end = date.fromisoformat(first), date.fromisoformat(last)
                if cursor > end or (end - cursor).days > 3660:
                    raise ValueError('Invalid SST coverage window')
                while cursor <= end:
                    expected_dates.add(cursor.isoformat())
                    cursor += timedelta(days=1)
            for day in sorted(expected_dates):
                expected[day[:7]] += 1
                if day not in available:
                    source.missing_day_count += 1
                    if len(source.missing_dates_within_extent) < MAX_MISSING_DATES:
                        source.missing_dates_within_extent.append(day)
            source.missing_dates_truncated = source.missing_day_count > MAX_MISSING_DATES
            source.bins = [CoverageBin(month=month, count=months.get(month, 0),
                                      observed_days=len(days.get(month, set())), expected_days=count,
                                      missing_days=count - len(days.get(month, set())))
                           for month, count in sorted(expected.items())]
    return source


def _revision(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def read_artifact(path: Path, columns: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    """Bounded projection with revision checking, including atomic replacements."""
    for _ in range(2):
        before = _revision(path)
        if before[1] > MAX_ARTIFACT_BYTES:
            raise ValueError("Coverage artifact exceeds bound")
        parquet = pq.ParquetFile(path)
        if parquet.metadata.num_rows > MAX_RECORDS:
            raise ValueError("Coverage artifact exceeds row bound")
        frame = parquet.read(columns=columns).to_pandas()
        if any(column not in frame for column in columns):
            raise ValueError("Coverage columns missing")
        if before == _revision(path):
            token = hashlib.sha256(str(before).encode()).hexdigest()
            return frame, {"artifact_revision": token}
    raise ValueError("Coverage artifact changed during read")


def artifact_source(identity: str) -> CoverageSource:
    if identity == "ctd":
        frame, binding = read_artifact(config.NORMALIZED_DIR / "ctd_summary.parquet", ["sample_id", "ctd_date"])
        records = [(str(row.sample_id), calendar_value(row.ctd_date, "date"))
                   for row in frame.itertuples(index=False)]
    elif identity == "metagenome":
        frame, binding = read_artifact(config.SERVING_DIR / "sample_registry.parquet",
                                       ["sample_id", "sample_year_month", "has_kraken", "has_metaeuk"])
        frame = frame[frame.has_kraken.eq(True) | frame.has_metaeuk.eq(True)]
        records = [(str(row.sample_id), calendar_value(row.sample_year_month, "month"))
                   for row in frame.itertuples(index=False)]
    elif identity == "remote_sensing":
        frame, binding = read_artifact(config.NORMALIZED_DIR / "sst_daily_summary.parquet", ["date_jst", "mean_sst"])
        valid = pd.to_numeric(frame.mean_sst, errors="coerce").map(
            lambda value: pd.notna(value) and math.isfinite(float(value)))
        excluded = int((~valid).sum())
        records = [(str(row.date_jst), calendar_value(row.date_jst, "date"))
                   for row in frame[valid].itertuples(index=False)]
        from ingestion.regional_publication import current_publication, daily_rows
        publication = current_publication()
        windows = [(min(when for _, when in records if when), max(when for _, when in records if when))] if any(when for _, when in records) else []
        if publication:
            records.extend((r['date_jst'], r['date_jst']) for r in daily_rows(publication))
            binding['regional_publication_id'] = publication['publication_id']
            windows.append(('2020-01-01', '2023-12-31'))
        source = aggregate_source(identity, records, binding=binding, excluded=excluded, expected_windows=windows)
        if publication:
            source.scope = 'Published current SST and Miyagi MUR regional context, 2020–2023. Products remain separate; gaps are counted only within their coverage windows.'
        return source
    else:
        raise ValueError("Unknown artifact source")
    if frame.sample_id.isna().any():
        raise ValueError("Missing sample identity")
    return aggregate_source(identity, records, binding=binding)


def read_edna_snapshot() -> tuple[list[dict], dict[str, str]]:
    """No detections, raw metadata, accounts or acquisition storage are read."""
    with get_engine().connect() as connection, connection.begin():
        connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.exec_driver_sql("SET LOCAL statement_timeout='5s'")
        publications = {
            row["channel"]: (row["generation_id"], row["manifest_sha256"])
            for row in connection.execute(text(
                "SELECT channel,generation_id,manifest_sha256 FROM corpus_publication "
                "WHERE channel IN ('anemone-canonical','edna-canonical')"
            )).mappings()
        }
        binding = publications.get("anemone-canonical")
        if not binding or binding != publications.get("edna-canonical") or not all(
            isinstance(value, str) and SHA256.fullmatch(value) for value in binding
        ):
            raise ValueError("Canonical publication unavailable")
        rows = [dict(row) for row in connection.execute(text(
            "SELECT sample_id,collection_date_utc,temporal_precision,sample_kind,is_control "
            "FROM edna_sample WHERE provider='anemone' AND active IS TRUE "
            "ORDER BY sample_id LIMIT :limit"
        ), {"limit": MAX_RECORDS + 1}).mappings()]
        if len(rows) > MAX_RECORDS:
            raise ValueError("Coverage occurrence bound exceeded")
        return rows, {"generation_id": binding[0], "manifest_sha256": binding[1]}


def edna_source() -> CoverageSource:
    rows, binding = read_edna_snapshot()
    categories = Counter()
    records = []
    for row in rows:
        if row["is_control"] is True:
            categories["controls"] += 1
        elif row["is_control"] is False and row["sample_kind"] == "environmental":
            categories["environmental"] += 1
        else:
            categories["unknown_or_other"] += 1
        records.append((row["sample_id"], calendar_value(row["collection_date_utc"], row["temporal_precision"])))
    return aggregate_source("edna_metabarcoding", records, binding=binding, categories=dict(categories))


def overview_coverage() -> OverviewCoverage:
    sources = []
    for identity, *_ in SOURCE_DEFINITIONS:
        try:
            source = edna_source() if identity == "edna_metabarcoding" else artifact_source(identity)
        except Exception:
            # Each dependency can fail independently. Never return private paths or SQL.
            source = source_definition(identity)
            source.reason = "Source coverage is unavailable."
        sources.append(source)
    return OverviewCoverage(generated_at=datetime.now(timezone.utc).isoformat(), sources=sources)
