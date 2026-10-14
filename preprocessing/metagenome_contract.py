"""Named method fields and a strict adapter for retained metagenome contexts.

The historical producer merged Kraken first and MetaEuk second. Pandas therefore
assigned `_x` to Kraken and `_y` to MetaEuk. A lone unsuffixed summary is usable
only with explicit, exclusive method coverage; the names are never interchangeable.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from typing import Any

import pandas as pd


KRAKEN_TOP_COLUMN = "top_kraken_genera_json"
METAEUK_TOP_COLUMN = "top_metaeuk_genera_json"
KRAKEN_UPPER_COLUMN = "top_kraken_upper_groups_json"
METAGENOME_FIELD_MAPPING_VERSION = "metagenome-fields-v2"
_VERSION_COLUMNS = {"metagenome_source_version", "metagenome_mapping_version"}
_LEGACY_GENUS_COLUMNS = {"top_genus_10_json", "top_genus_10_json_x", "top_genus_10_json_y"}


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return _json_value(value.item())
    return value


def stable_metagenome_hash(value: Any) -> str:
    serialized = json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _coverage(value: Any) -> bool:
    """Unknown coverage stays false; arbitrary nonempty strings are not truth."""
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        raise ValueError("metagenome coverage flags must be booleans, not strings")
    if value not in (True, False):
        raise ValueError("metagenome coverage flags must be booleans")
    return bool(value)


def _summary_json(value: Any, column: str) -> str | None:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{column}: invalid taxa JSON") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{column}: taxa JSON must be a list of records")
    taxon_key = "upper_group" if column == KRAKEN_UPPER_COLUMN else "genus"
    for item in value:
        abundance = item.get("abundance_value")
        if (not isinstance(item.get(taxon_key), str) or not item[taxon_key].strip()
                or isinstance(abundance, bool) or not isinstance(abundance, (int, float))
                or not math.isfinite(abundance)):
            raise ValueError(f"{column}: each taxon requires {taxon_key} and finite numeric abundance_value")
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def adapt_legacy_metagenome_context(frame: pd.DataFrame) -> pd.DataFrame:
    """Return canonical fields plus deterministic row-source/mapping versions.

    Accepted layouts: named v2 fields; the complete retained `_x`/`_y` pair;
    unsuffixed genus JSON with exactly one explicit method flag; or missing
    summary fields. Mixed named/legacy genus fields and incomplete merge pairs
    fail closed so no consumer can silently assign taxa to another method.
    """
    canonical = {KRAKEN_TOP_COLUMN, METAEUK_TOP_COLUMN}
    legacy = _LEGACY_GENUS_COLUMNS.intersection(frame.columns)
    if canonical.intersection(frame.columns) and legacy:
        raise ValueError("mixed canonical and legacy metagenome genus fields")
    if "top_genus_10_json" in legacy and len(legacy) > 1:
        raise ValueError("ambiguous unsuffixed and suffixed legacy metagenome fields")
    suffixed = legacy.intersection({"top_genus_10_json_x", "top_genus_10_json_y"})
    if suffixed and len(suffixed) != 2:
        raise ValueError("incomplete legacy metagenome merge pair")
    if KRAKEN_UPPER_COLUMN in frame and "top_upper_group_10_json" in frame:
        raise ValueError("mixed canonical and legacy Kraken upper-group fields")

    output = frame.copy()
    for column in ("has_kraken", "has_metaeuk", "has_ctd", "has_kraken_upper_group"):
        if column in output:
            output[column] = output[column].map(_coverage)
        elif column in {"has_kraken", "has_metaeuk"}:
            output[column] = False
    if suffixed:
        output = output.rename(columns={"top_genus_10_json_x": KRAKEN_TOP_COLUMN,
                                        "top_genus_10_json_y": METAEUK_TOP_COLUMN})
    elif "top_genus_10_json" in legacy:
        kraken, metaeuk = [], []
        for _, row in output.iterrows():
            if row["has_kraken"] == row["has_metaeuk"]:
                raise ValueError("ambiguous unsuffixed metagenome genus summary: explicit single method required")
            kraken.append(row["top_genus_10_json"] if row["has_kraken"] else None)
            metaeuk.append(row["top_genus_10_json"] if row["has_metaeuk"] else None)
        output[KRAKEN_TOP_COLUMN] = kraken
        output[METAEUK_TOP_COLUMN] = metaeuk
        output = output.drop(columns=["top_genus_10_json"])
    if "top_upper_group_10_json" in output:
        output = output.rename(columns={"top_upper_group_10_json": KRAKEN_UPPER_COLUMN})
    for column in (KRAKEN_TOP_COLUMN, METAEUK_TOP_COLUMN, KRAKEN_UPPER_COLUMN):
        if column not in output:
            output[column] = None
        output[column] = output[column].map(lambda value: _summary_json(value, column))
    for column, coverage in ((KRAKEN_TOP_COLUMN, "has_kraken"),
                             (METAEUK_TOP_COLUMN, "has_metaeuk")):
        inconsistent = (~output[coverage]) & output[column].map(
            lambda value: value is not None and bool(json.loads(value))
        )
        if inconsistent.any():
            raise ValueError(f"{column}: nonempty summary contradicts false or unknown {coverage} coverage")
    source_columns = sorted(set(output.columns) - _VERSION_COLUMNS)
    versions = [stable_metagenome_hash({column: row[column] for column in source_columns})
                for _, row in output.iterrows()]
    if "metagenome_source_version" in output:
        for supplied, expected in zip(output["metagenome_source_version"], versions):
            if supplied is not None and pd.notna(supplied) and supplied != expected:
                raise ValueError("metagenome source version does not match canonical source row")
    if "metagenome_mapping_version" in output:
        supplied = output["metagenome_mapping_version"].dropna()
        if not supplied.eq(METAGENOME_FIELD_MAPPING_VERSION).all():
            raise ValueError("unsupported metagenome field mapping version")
    output["metagenome_source_version"] = versions
    output["metagenome_mapping_version"] = METAGENOME_FIELD_MAPPING_VERSION
    return output


def metagenome_document_id(sample_id: str, generation_hash: str) -> str:
    """Keep IDs within the existing 128-character database field."""
    return f"meta_{sample_id}_v2_{generation_hash[:32]}"


def metagenome_document_generation_hash(row: Any, metadata: dict[str, Any]) -> str:
    """Bind complete generated evidence; mutable runtime state stays independent."""
    scientific_fields = (
        "source_type", "sample_id", "event_id", "time", "lat", "lon", "bay", "station",
        "title", "text", "provider", "provider_project_id", "provider_run_id", "assay_id",
        "assignment_method", "sample_kind", "is_control", "source_snapshot_id",
    )
    return stable_metagenome_hash({
        "document": {column: row.get(column) for column in scientific_fields},
        "metadata": {key: value for key, value in metadata.items() if key != "generation_hash"},
    })


def metagenome_replacement_scope(frame: pd.DataFrame) -> dict[str, str]:
    """Validate v2 replacements and identify the samples whose old docs retire.

    Other document families and retained unversioned rows do not authorize any
    metagenome retirement. Each represented sample has exactly one active v2
    document. Hash validation prevents in-place edits under a retained identity.
    """
    replacements: dict[str, str] = {}
    for _, row in frame.iterrows():
        doc_id = row.get("doc_id")
        versioned_id = isinstance(doc_id, str) and re.fullmatch(r"meta_.+_v2_[0-9a-f]{32}", doc_id) is not None
        if row.get("source_type") != "metagenome":
            if versioned_id:
                raise ValueError("versioned metagenome identity requires metagenome source_type")
            continue
        raw_metadata = row.get("metadata_json", row.get("metadata"))
        if isinstance(raw_metadata, dict):
            metadata = raw_metadata
        elif isinstance(raw_metadata, str) and raw_metadata:
            metadata = json.loads(raw_metadata)
        else:
            if versioned_id:
                raise ValueError("versioned metagenome identity requires v2 generation metadata")
            continue
        if not isinstance(metadata, dict) or metadata.get("document_version") != "metagenome-document-v2":
            if versioned_id:
                raise ValueError("versioned metagenome identity requires v2 generation metadata")
            continue
        source_version = metadata.get("source_version")
        if not isinstance(source_version, str) or len(source_version) != 64:
            raise ValueError("metagenome replacement requires a SHA-256 source version")
        try:
            int(source_version, 16)
        except ValueError as exc:
            raise ValueError("metagenome replacement requires a SHA-256 source version") from exc
        content_hash = stable_metagenome_hash({"title": row.get("title"), "text": row.get("text")})
        if (metadata.get("content_hash") != content_hash
                or metadata.get("field_mapping_version") != METAGENOME_FIELD_MAPPING_VERSION):
            raise ValueError("metagenome replacement content or mapping hash evidence is invalid")
        generation_hash = metagenome_document_generation_hash(row, metadata)
        sample_id = row.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id or len(sample_id) > 64:
            raise ValueError("metagenome replacement requires a valid sample identity")
        if (metadata.get("generation_hash") != generation_hash
                or row.get("doc_id") != metagenome_document_id(sample_id, generation_hash)):
            raise ValueError("metagenome replacement generation identity is invalid")
        if not _coverage(row.get("active", True)):
            continue
        if sample_id in replacements:
            raise ValueError("multiple active metagenome replacements for one sample")
        replacements[sample_id] = row["doc_id"]
    return replacements
