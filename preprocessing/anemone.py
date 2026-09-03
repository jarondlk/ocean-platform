"""Deterministic normalization of completed ANEMONE MiFish snapshots."""
from __future__ import annotations

import csv
import hashlib
import json
import lzma
import math
import re
import shutil
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

import pandas as pd

import config
from ingestion.anemone import load_contract


SNAPSHOT_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SEQUENCE_PATTERN = re.compile(r"^[ACGTN]+$")
ASSIGNMENT_METHODS = {
    "community_qc": "qcauto_target",
    "community_qc3nn": "qcauto_95pct_3nn_target",
}
REQUIRED_ROLES = {
    "sample_metadata",
    "experiment_metadata",
    "community_standard",
    "community_qc",
    "community_qc3nn",
}
SAMPLE_KINDS = {
    "environmental",
    "negative_control",
    "positive_control",
    "mock_community",
    "unknown",
}
CLASSIFICATION_KEYS = ("sample_type", "sample_category", "control_type")
CLASSIFICATION_VALUES = {
    "environmental": ("environmental", False),
    "environmental_sample": ("environmental", False),
    "field_sample": ("environmental", False),
    "negative_control": ("negative_control", True),
    "blank": ("negative_control", True),
    "field_blank": ("negative_control", True),
    "extraction_blank": ("negative_control", True),
    "pcr_blank": ("negative_control", True),
    "positive_control": ("positive_control", True),
    "mock_community": ("mock_community", True),
}


class AnemoneNormalizationError(RuntimeError):
    """A normalized, credential-free PR2 validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class NormalizationIssue:
    severity: str
    code: str
    message: str
    sample_id: Optional[str] = None
    source_file_id: Optional[str] = None


@dataclass
class AnemoneNormalizedBundle:
    normalization_id: str
    source_snapshot_id: str
    source_scope_level: str
    source_scope_url: str
    frames: dict[str, pd.DataFrame]
    issues: list[NormalizationIssue]
    input_manifest_sha256: str
    contract_sha256: str
    generated_at: str
    classification_review: Optional[dict[str, Any]] = None


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_value,
    )


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def stable_edna_id(kind: str, *parts: Any) -> str:
    normalized = [
        unicodedata.normalize("NFC", str(part)).strip()
        for part in parts
    ]
    return stable_sha256([kind, *normalized])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_snapshot_file(snapshot_root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise AnemoneNormalizationError(
            "source_path_invalid",
            "ANEMONE snapshot contains an unsafe source path.",
        )
    destination = snapshot_root.joinpath(*relative.parts)
    if destination.is_symlink():
        raise AnemoneNormalizationError(
            "source_symlink_invalid",
            "ANEMONE snapshot source files cannot be symlinks.",
        )
    resolved_root = snapshot_root.resolve()
    resolved = destination.resolve()
    if resolved_root not in resolved.parents:
        raise AnemoneNormalizationError(
            "source_path_invalid",
            "ANEMONE snapshot source file escapes its snapshot directory.",
        )
    return destination


def _read_xz_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    try:
        with lzma.open(path, "rt", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))
    except (OSError, UnicodeError, lzma.LZMAError) as exc:
        raise AnemoneNormalizationError(
            "source_tsv_unreadable",
            "ANEMONE interpreted source file is unreadable.",
        ) from exc
    if not rows:
        raise AnemoneNormalizationError(
            "source_tsv_empty",
            "ANEMONE interpreted source file is empty.",
        )
    width = len(rows[0])
    if any(len(row) != width for row in rows[1:]):
        raise AnemoneNormalizationError(
            "source_tsv_width_invalid",
            "ANEMONE interpreted source contains a malformed row.",
        )
    return rows[0], rows[1:]


def _source_segments(scope_url: str, scope_level: str) -> tuple[str, str]:
    parts = [part for part in urlsplit(scope_url).path.split("/") if part]
    try:
        marker = parts.index("ANEMONE")
    except ValueError as exc:
        raise AnemoneNormalizationError(
            "source_scope_invalid",
            "ANEMONE source scope does not contain the approved provider path.",
        ) from exc
    tail = parts[marker + 1 :]
    expected = 3 if scope_level == "sample" else 2
    if len(tail) != expected:
        raise AnemoneNormalizationError(
            "source_scope_invalid",
            "ANEMONE source scope does not match its declared level.",
        )
    return tail[0], tail[1]


def _source_file_id(snapshot_id: str, item: dict[str, Any]) -> str:
    identity = item.get("sha256") or {
        "etag": item.get("etag"),
        "last_modified": item.get("last_modified"),
        "size_bytes": item.get("size_bytes"),
    }
    return stable_edna_id(
        "source_file",
        "anemone",
        snapshot_id,
        item.get("relative_path"),
        _canonical_json(identity),
    )


def _metadata_map(
    header: list[str],
    rows: list[list[str]],
    *,
    expected_sample: str,
) -> tuple[dict[str, str], list[int]]:
    if header != ["samplename", "key", "value"]:
        raise AnemoneNormalizationError(
            "metadata_columns_invalid",
            "ANEMONE metadata columns do not match the PR2 contract.",
        )
    values: dict[str, str] = {}
    row_numbers: list[int] = []
    for row_number, row in enumerate(rows, start=2):
        if row[0].strip() != expected_sample:
            raise AnemoneNormalizationError(
                "metadata_sample_mismatch",
                "ANEMONE metadata sample does not match its source directory.",
            )
        key = row[1].strip()
        if not key or key in values:
            raise AnemoneNormalizationError(
                "metadata_key_invalid",
                "ANEMONE metadata contains a blank or duplicate key.",
            )
        values[key] = row[2].strip()
        row_numbers.append(row_number)
    return values, row_numbers


def _nullable_text(value: Any) -> Optional[str]:
    cleaned = str(value or "").strip()
    return None if cleaned.upper() in {"", "NA", "N/A", "NULL"} else cleaned


def _parse_lat_lon(value: Any) -> tuple[Optional[float], Optional[float]]:
    cleaned = _nullable_text(value)
    if cleaned is None:
        return None, None
    parts = [part for part in re.split(r"[\s,]+", cleaned) if part]
    if len(parts) != 2:
        raise AnemoneNormalizationError(
            "coordinate_invalid",
            "ANEMONE lat_lon must contain exactly latitude and longitude.",
        )
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise AnemoneNormalizationError(
            "coordinate_invalid",
            "ANEMONE lat_lon contains a non-numeric coordinate.",
        ) from exc
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise AnemoneNormalizationError(
            "coordinate_out_of_range",
            "ANEMONE coordinates fall outside valid latitude/longitude ranges.",
        )
    return lat, lon


def _parse_collection_date(value: Any) -> tuple[Optional[str], Optional[str]]:
    cleaned = _nullable_text(value)
    if cleaned is None:
        return None, None
    try:
        if len(cleaned) == 10:
            return date.fromisoformat(cleaned).isoformat(), "date"
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnemoneNormalizationError(
            "collection_date_invalid",
            "ANEMONE collection_date_utc is not a valid ISO date or timestamp.",
        ) from exc
    if parsed.tzinfo is None:
        raise AnemoneNormalizationError(
            "collection_timezone_missing",
            "ANEMONE UTC collection timestamp must include a timezone.",
        )
    return parsed.astimezone(timezone.utc).isoformat(), "datetime"


def _classification(metadata: dict[str, str]) -> tuple[str, Optional[bool], str]:
    for key in CLASSIFICATION_KEYS:
        value = _nullable_text(metadata.get(key))
        if not value:
            continue
        normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        mapped = CLASSIFICATION_VALUES.get(normalized)
        if mapped:
            return mapped[0], mapped[1], f"metadata:{key}"
        return "unknown", None, f"unrecognized_metadata:{key}"
    return "unknown", None, "no_reviewed_classification_metadata"


def _integer(value: str, *, field: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise AnemoneNormalizationError(
            f"{field}_invalid",
            f"ANEMONE {field} must be an integer.",
        ) from exc
    if parsed < 0:
        raise AnemoneNormalizationError(
            f"{field}_negative",
            f"ANEMONE {field} cannot be negative.",
        )
    return parsed


def _copies_per_ml(value: str) -> Optional[float]:
    cleaned = _nullable_text(value)
    if cleaned is None:
        return None
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise AnemoneNormalizationError(
            "copies_per_ml_invalid",
            "ANEMONE copies_per_ml must be numeric or null.",
        ) from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise AnemoneNormalizationError(
            "copies_per_ml_invalid",
            "ANEMONE copies_per_ml must be finite and non-negative.",
        )
    return parsed


def _sequence(value: str) -> str:
    sequence = value.strip().upper()
    if not SEQUENCE_PATTERN.fullmatch(sequence):
        raise AnemoneNormalizationError(
            "sequence_invalid",
            "ANEMONE sequence contains unsupported symbols.",
        )
    return sequence


def _scientific_and_source_hashes(
    scientific: dict[str, Any],
    source: dict[str, Any],
) -> tuple[str, str]:
    scientific_hash = stable_sha256(scientific)
    return scientific_hash, stable_sha256(
        {"scientific_content_sha256": scientific_hash, **source}
    )


def _frame(
    rows: Iterable[dict[str, Any]],
    key: str,
    *,
    columns: Optional[list[str]] = None,
) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows), columns=columns)
    if not frame.empty:
        frame = frame.sort_values(key, kind="stable").reset_index(drop=True)
    return frame


def _verify_snapshot(
    snapshot_id: str,
    *,
    raw_root: Path,
    contract: dict[str, Any],
) -> tuple[Path, dict[str, Any], str, dict[tuple[str, str], dict[str, Any]]]:
    if not SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
        raise AnemoneNormalizationError(
            "snapshot_id_invalid",
            "ANEMONE snapshot ID must be a lowercase SHA-256 value.",
        )
    snapshot_root = raw_root / "snapshots" / snapshot_id
    if snapshot_root.is_symlink() or not snapshot_root.is_dir():
        raise AnemoneNormalizationError(
            "snapshot_missing",
            "Completed ANEMONE snapshot does not exist.",
        )
    for child in snapshot_root.rglob("*"):
        if child.is_symlink():
            raise AnemoneNormalizationError(
                "source_symlink_invalid",
                "ANEMONE snapshot cannot contain symlinks.",
            )
    manifest_path = snapshot_root / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise AnemoneNormalizationError(
            "snapshot_manifest_invalid",
            "ANEMONE snapshot manifest is unreadable.",
        ) from exc
    contract_sha = stable_sha256(contract)
    required = {
        "schema_version": 1,
        "source_provider": "anemone",
        "source_family": "edna_metabarcoding",
        "selection_policy": "interpreted_tsv_only",
        "status": "complete",
        "snapshot_id": snapshot_id,
        "contract_sha256": contract_sha,
    }
    if any(manifest.get(key) != value for key, value in required.items()):
        raise AnemoneNormalizationError(
            "snapshot_manifest_contract_invalid",
            "ANEMONE snapshot manifest does not match the PR2 input contract.",
        )
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for item in manifest.get("files") or []:
        if not isinstance(item, dict):
            raise AnemoneNormalizationError(
                "snapshot_file_record_invalid",
                "ANEMONE snapshot contains an invalid file record.",
            )
        if item.get("selection_status") != "selected":
            continue
        sample_name = str(item.get("sample_name") or "")
        role = str(item.get("role") or "")
        key = (sample_name, role)
        if not sample_name or role not in REQUIRED_ROLES or key in selected:
            raise AnemoneNormalizationError(
                "snapshot_selected_roles_invalid",
                "ANEMONE snapshot has invalid or duplicate selected roles.",
            )
        path = _safe_snapshot_file(snapshot_root, str(item.get("relative_path") or ""))
        if not path.is_file():
            raise AnemoneNormalizationError(
                "snapshot_source_missing",
                "ANEMONE selected source file is missing.",
            )
        expected_size = item.get("size_bytes")
        if expected_size is None or path.stat().st_size != int(expected_size):
            raise AnemoneNormalizationError(
                "snapshot_source_size_mismatch",
                "ANEMONE selected source size does not match its manifest.",
            )
        expected_sha = str(item.get("sha256") or "")
        if not expected_sha or _sha256_file(path) != expected_sha:
            raise AnemoneNormalizationError(
                "snapshot_source_hash_mismatch",
                "ANEMONE selected source hash does not match its manifest.",
            )
        if item.get("validation_status") != "valid":
            raise AnemoneNormalizationError(
                "snapshot_source_not_validated",
                "ANEMONE selected source was not validated by PR1.",
            )
        selected[key] = {**item, "path": path}
    samples = {sample for sample, _ in selected}
    if not samples or any(
        {role for sample_name, role in selected if sample_name == sample}
        != REQUIRED_ROLES
        for sample in samples
    ):
        raise AnemoneNormalizationError(
            "snapshot_required_roles_missing",
            "ANEMONE snapshot does not contain exactly one required role per sample.",
        )
    return (
        snapshot_root,
        manifest,
        hashlib.sha256(manifest_bytes).hexdigest(),
        selected,
    )


def build_anemone_bundle(
    snapshot_id: str,
    *,
    raw_root: Path = config.RAW_ANEMONE_DIR,
    contract: Optional[dict[str, Any]] = None,
    generated_at: Optional[str] = None,
    classification_review: Optional[dict[str, Any]] = None,
) -> AnemoneNormalizedBundle:
    source_contract = contract or load_contract()
    snapshot_root, manifest, manifest_sha, selected = _verify_snapshot(
        snapshot_id,
        raw_root=raw_root,
        contract=source_contract,
    )
    reviews = {}
    if classification_review is not None:
        from preprocessing.anemone_classification import parse_review, validate_review_evidence, ReviewError

        try:
            classification_review = parse_review(_canonical_json(classification_review).encode("utf-8"))
            validate_review_evidence(classification_review, snapshot_id, selected)
        except ReviewError as exc:
            raise AnemoneNormalizationError("classification_review_invalid", str(exc)) from exc
        reviews = {d["provider_sample_id"]: d for d in classification_review["decisions"]}
    scope_level = str(manifest.get("scope_level") or "")
    scope_url = str(manifest.get("scope_url") or "")
    project_id, run_id = _source_segments(scope_url, scope_level)
    contract_sha = stable_sha256(source_contract)
    issues: list[NormalizationIssue] = []

    external_snapshot_rows = [
        {
            "snapshot_id": snapshot_id,
            "provider": "anemone",
            "source_family": "edna_metabarcoding",
            "scope_url": scope_url,
            "scope_level": scope_level,
            "source_collection_sha256": manifest.get("source_collection_sha256"),
            "contract_version": int(manifest["contract_version"]),
            "contract_sha256": contract_sha,
            "selection_policy": manifest.get("selection_policy"),
            "generated_at": manifest.get("generated_at"),
            "file_count": int(manifest.get("file_count") or 0),
            "selected_file_count": int(manifest.get("selected_file_count") or 0),
            "total_bytes": int(manifest.get("total_bytes") or 0),
            "status": "complete",
            "manifest_sha256": manifest_sha,
            "manifest_summary_json": _canonical_json(
                {
                    "mode": manifest.get("mode"),
                    "scope_level": scope_level,
                    "selection_policy": manifest.get("selection_policy"),
                    "issues": manifest.get("issues") or [],
                }
            ),
        }
    ]
    external_file_rows: list[dict[str, Any]] = []
    source_file_ids: dict[tuple[str, str], str] = {}
    for item in manifest.get("files") or []:
        source_file_id = _source_file_id(snapshot_id, item)
        sample_name = str(item.get("sample_name") or "")
        role = str(item.get("role") or "")
        source_file_ids[(sample_name, role)] = source_file_id
        external_file_rows.append(
            {
                "source_file_id": source_file_id,
                "snapshot_id": snapshot_id,
                "relative_path": item.get("relative_path"),
                "source_url": item.get("source_url"),
                "sample_name": sample_name,
                "role": role,
                "selection_status": item.get("selection_status"),
                "size_bytes": item.get("size_bytes"),
                "etag": item.get("etag"),
                "last_modified": item.get("last_modified"),
                "sha256": item.get("sha256"),
                "validation_status": item.get("validation_status"),
                "row_count": item.get("row_count"),
            }
        )

    sample_rows: list[dict[str, Any]] = []
    assay_rows: list[dict[str, Any]] = []
    detection_rows: list[dict[str, Any]] = []
    standard_rows: list[dict[str, Any]] = []
    anchor_rows: list[dict[str, Any]] = []
    taxonomy_columns = list(source_contract["tables"]["community"]["columns"])[1:-3]
    indexed_ranks = (
        "superkingdom",
        "kingdom",
        "phylum",
        "class",
        "order",
        "family",
        "genus",
        "species",
        "subspecies",
    )

    for provider_sample_id in sorted({sample for sample, _ in selected}):
        sample_item = selected[(provider_sample_id, "sample_metadata")]
        sample_header, sample_source_rows = _read_xz_tsv(sample_item["path"])
        sample_metadata, sample_row_numbers = _metadata_map(
            sample_header,
            sample_source_rows,
            expected_sample=provider_sample_id,
        )
        experiment_item = selected[(provider_sample_id, "experiment_metadata")]
        experiment_header, experiment_source_rows = _read_xz_tsv(
            experiment_item["path"]
        )
        experiment_metadata, experiment_row_numbers = _metadata_map(
            experiment_header,
            experiment_source_rows,
            expected_sample=provider_sample_id,
        )
        for key in source_contract["tables"]["key_value_sample"]["required_keys"]:
            if not _nullable_text(sample_metadata.get(key)):
                raise AnemoneNormalizationError(
                    "sample_metadata_required_value_missing",
                    f"ANEMONE sample metadata is missing required value {key}.",
                )
        for key in source_contract["tables"]["key_value_experiment"]["required_keys"]:
            if not _nullable_text(experiment_metadata.get(key)):
                raise AnemoneNormalizationError(
                    "experiment_metadata_required_value_missing",
                    f"ANEMONE experiment metadata is missing required value {key}.",
                )

        sample_id = stable_edna_id("sample", "anemone", provider_sample_id)
        assay_id = stable_edna_id(
            "assay", "anemone", provider_sample_id, "experiment_metadata"
        )
        sample_kind, is_control, classification_basis = _classification(
            sample_metadata
        )
        review_record = None
        if provider_sample_id in reviews:
            review_record = {
                "schema_version": 1,
                "source_snapshot_id": snapshot_id,
                "review_sha256": stable_sha256(classification_review),
                "provider_classification_basis": classification_basis,
                "decision": reviews[provider_sample_id],
            }
            sample_kind = review_record["decision"]["sample_kind"]
            is_control = sample_kind != "environmental"
            classification_basis = "review:" + stable_sha256(review_record)
        if sample_kind not in SAMPLE_KINDS:
            raise AssertionError("unreachable")
        if sample_kind == "unknown":
            issues.append(
                NormalizationIssue(
                    "warning",
                    "sample_classification_unknown",
                    "ANEMONE sample has no reviewed environmental/control classification.",
                    sample_id,
                    source_file_ids[(provider_sample_id, "sample_metadata")],
                )
            )
        lat, lon = _parse_lat_lon(sample_metadata.get("lat_lon"))
        collection_value, temporal_precision = _parse_collection_date(
            sample_metadata.get("collection_date_utc")
        )
        if sample_kind == "environmental" and (
            lat is None or lon is None or collection_value is None
        ):
            raise AnemoneNormalizationError(
                "environmental_sample_anchor_missing",
                "Environmental ANEMONE sample requires coordinates and collection date.",
            )
        anchor_event_id = (
            stable_edna_id(
                "anchor_event",
                "edna_metabarcoding",
                "anemone",
                provider_sample_id,
            )
            if sample_kind == "environmental"
            else None
        )
        sample_scientific = {
            "provider": "anemone",
            "provider_sample_id": provider_sample_id,
            "provider_project_id": project_id,
            "provider_run_id": run_id,
            "project_name": sample_metadata.get("project_name"),
            "original_sample_label": sample_metadata.get("samp_name"),
            "sample_kind": sample_kind,
            "is_control": is_control,
            "classification_basis": classification_basis,
            "collection_date_utc": collection_value,
            "temporal_precision": temporal_precision,
            "lat": lat,
            "lon": lon,
            "raw_metadata_json": _canonical_json(sample_metadata),
            "anchor_event_id": anchor_event_id,
        }
        sample_source = {
            "source_snapshot_id": snapshot_id,
            "source_file_id": source_file_ids[(provider_sample_id, "sample_metadata")],
            "source_row_numbers_json": _canonical_json(sample_row_numbers),
        }
        if review_record is not None:
            sample_scientific["classification_review_json"] = _canonical_json(review_record)
        sample_scientific_hash, sample_source_hash = _scientific_and_source_hashes(
            sample_scientific,
            sample_source,
        )
        sample_rows.append(
            {
                "sample_id": sample_id,
                **sample_scientific,
                **sample_source,
                "classification_review_json": (
                    _canonical_json(review_record) if review_record else None
                ),
                "active": True,
                "first_seen_snapshot_id": snapshot_id,
                "last_seen_snapshot_id": snapshot_id,
                "scientific_content_sha256": sample_scientific_hash,
                "source_row_hash": sample_source_hash,
            }
        )
        if anchor_event_id:
            anchor_rows.append(
                {
                    "event_id": anchor_event_id,
                    "time_start": collection_value,
                    "time_end": collection_value,
                    "lat": lat,
                    "lon": lon,
                    "depth_min": None,
                    "depth_max": None,
                    "station_id": None,
                    "sample_id": sample_id,
                    "bay_code": None,
                    "source_types": "edna_metabarcoding",
                    "active": True,
                }
            )

        assay_scientific = {
            "sample_id": sample_id,
            "target_gene": experiment_metadata.get("target_gene"),
            "primer_set": experiment_metadata.get("pcr_primers"),
            "sequencing_method": experiment_metadata.get("seq_meth"),
            "library_layout": _nullable_text(
                experiment_metadata.get("lib_layout")
            ),
            "instrument_model": _nullable_text(
                experiment_metadata.get("instrument_model")
            ),
            "raw_metadata_json": _canonical_json(experiment_metadata),
        }
        assay_source = {
            "source_snapshot_id": snapshot_id,
            "source_file_id": source_file_ids[
                (provider_sample_id, "experiment_metadata")
            ],
            "source_row_numbers_json": _canonical_json(experiment_row_numbers),
        }
        assay_scientific_hash, assay_source_hash = _scientific_and_source_hashes(
            assay_scientific,
            assay_source,
        )
        assay_rows.append(
            {
                "assay_id": assay_id,
                **assay_scientific,
                **assay_source,
                "active": True,
                "first_seen_snapshot_id": snapshot_id,
                "last_seen_snapshot_id": snapshot_id,
                "scientific_content_sha256": assay_scientific_hash,
                "source_row_hash": assay_source_hash,
            }
        )

        for role, assignment_method in ASSIGNMENT_METHODS.items():
            item = selected[(provider_sample_id, role)]
            header, rows = _read_xz_tsv(item["path"])
            expected_header = source_contract["tables"]["community"]["columns"]
            if header != expected_header:
                raise AnemoneNormalizationError(
                    "community_columns_invalid",
                    "ANEMONE community columns do not match the PR2 contract.",
                )
            index = {name: position for position, name in enumerate(header)}
            observed_detection_ids: set[str] = set()
            for row_number, row in enumerate(rows, start=2):
                if row[0].strip() != provider_sample_id:
                    raise AnemoneNormalizationError(
                        "community_sample_mismatch",
                        "ANEMONE community sample does not match its source directory.",
                    )
                sequence = _sequence(row[index["sequence"]])
                sequence_sha = hashlib.sha256(sequence.encode("ascii")).hexdigest()
                detection_id = stable_edna_id(
                    "detection", assay_id, assignment_method, sequence_sha
                )
                if detection_id in observed_detection_ids:
                    raise AnemoneNormalizationError(
                        "detection_identity_duplicate",
                        "ANEMONE community contains a duplicate assay/method/sequence key.",
                    )
                observed_detection_ids.add(detection_id)
                taxonomy = {
                    rank: _nullable_text(row[index[rank]])
                    for rank in taxonomy_columns
                }
                assigned_rank = next(
                    (rank for rank in reversed(taxonomy_columns) if taxonomy[rank]),
                    None,
                )
                scientific = {
                    "assay_id": assay_id,
                    "assignment_method": assignment_method,
                    "sequence": sequence,
                    "sequence_sha256": sequence_sha,
                    "read_count": _integer(
                        row[index["nreads"]],
                        field="read_count",
                    ),
                    "copies_per_ml": _copies_per_ml(
                        row[index["ncopiesperml"]]
                    ),
                    **{rank: taxonomy.get(rank) for rank in indexed_ranks},
                    "assigned_taxon_name": taxonomy.get(assigned_rank or ""),
                    "assigned_taxon_rank": assigned_rank,
                    "taxonomy_json": _canonical_json(taxonomy),
                }
                source = {
                    "source_snapshot_id": snapshot_id,
                    "source_file_id": source_file_ids[(provider_sample_id, role)],
                    "source_row_number": row_number,
                }
                scientific_hash, source_hash = _scientific_and_source_hashes(
                    scientific,
                    source,
                )
                detection_rows.append(
                    {
                        "detection_id": detection_id,
                        **scientific,
                        **source,
                        "active": True,
                        "first_seen_snapshot_id": snapshot_id,
                        "last_seen_snapshot_id": snapshot_id,
                        "scientific_content_sha256": scientific_hash,
                        "source_row_hash": source_hash,
                    }
                )

        standard_item = selected[(provider_sample_id, "community_standard")]
        standard_header, standard_source_rows = _read_xz_tsv(standard_item["path"])
        if standard_header != source_contract["tables"]["standard"]["columns"]:
            raise AnemoneNormalizationError(
                "standard_columns_invalid",
                "ANEMONE internal-standard columns do not match the PR2 contract.",
            )
        observed_standard_ids: set[str] = set()
        for row_number, row in enumerate(standard_source_rows, start=2):
            if row[0].strip() != provider_sample_id:
                raise AnemoneNormalizationError(
                    "standard_sample_mismatch",
                    "ANEMONE internal standard does not match its source directory.",
                )
            standard_name = row[1].strip()
            sequence = _sequence(row[2])
            sequence_sha = hashlib.sha256(sequence.encode("ascii")).hexdigest()
            standard_id = stable_edna_id(
                "internal_standard", assay_id, standard_name, sequence_sha
            )
            if not standard_name or standard_id in observed_standard_ids:
                raise AnemoneNormalizationError(
                    "standard_identity_duplicate",
                    "ANEMONE internal-standard identity is blank or duplicated.",
                )
            observed_standard_ids.add(standard_id)
            scientific = {
                "assay_id": assay_id,
                "standard_name": standard_name,
                "sequence": sequence,
                "sequence_sha256": sequence_sha,
                "read_count": _integer(row[3], field="read_count"),
            }
            source = {
                "source_snapshot_id": snapshot_id,
                "source_file_id": source_file_ids[
                    (provider_sample_id, "community_standard")
                ],
                "source_row_number": row_number,
            }
            scientific_hash, source_hash = _scientific_and_source_hashes(
                scientific,
                source,
            )
            standard_rows.append(
                {
                    "internal_standard_id": standard_id,
                    **scientific,
                    **source,
                    "active": True,
                    "first_seen_snapshot_id": snapshot_id,
                    "last_seen_snapshot_id": snapshot_id,
                    "scientific_content_sha256": scientific_hash,
                    "source_row_hash": source_hash,
                }
            )

    frames = {
        "external_source_snapshot": _frame(external_snapshot_rows, "snapshot_id"),
        "external_source_file": _frame(external_file_rows, "source_file_id"),
        "edna_sample": _frame(sample_rows, "sample_id"),
        "edna_assay": _frame(assay_rows, "assay_id"),
        "edna_detection": _frame(
            detection_rows,
            "detection_id",
            columns=[
                "detection_id",
                "assay_id",
                "assignment_method",
                "sequence",
                "sequence_sha256",
                "read_count",
                "copies_per_ml",
                *indexed_ranks,
                "assigned_taxon_name",
                "assigned_taxon_rank",
                "taxonomy_json",
                "source_snapshot_id",
                "source_file_id",
                "source_row_number",
                "active",
                "first_seen_snapshot_id",
                "last_seen_snapshot_id",
                "scientific_content_sha256",
                "source_row_hash",
            ],
        ),
        "edna_internal_standard": _frame(
            standard_rows,
            "internal_standard_id",
            columns=[
                "internal_standard_id",
                "assay_id",
                "standard_name",
                "sequence",
                "sequence_sha256",
                "read_count",
                "source_snapshot_id",
                "source_file_id",
                "source_row_number",
                "active",
                "first_seen_snapshot_id",
                "last_seen_snapshot_id",
                "scientific_content_sha256",
                "source_row_hash",
            ],
        ),
        "edna_anchor_event": _frame(
            anchor_rows,
            "event_id",
            columns=[
                "event_id",
                "time_start",
                "time_end",
                "lat",
                "lon",
                "depth_min",
                "depth_max",
                "station_id",
                "sample_id",
                "bay_code",
                "source_types",
                "active",
            ],
        ),
    }
    identity_payload = {
        "source_snapshot_id": snapshot_id,
        "contract_sha256": contract_sha,
        "normalization_version": config.ANEMONE_NORMALIZATION_VERSION,
        "tables": {
            name: {
                "columns": list(frame.columns),
                "rows": [
                    stable_sha256(record)
                    for record in frame.to_dict(orient="records")
                ],
            }
            for name, frame in sorted(frames.items())
        },
    }
    if classification_review is not None:
        identity_payload["classification_review_sha256"] = stable_sha256(classification_review)
    normalization_id = stable_sha256(identity_payload)
    return AnemoneNormalizedBundle(
        normalization_id=normalization_id,
        source_snapshot_id=snapshot_id,
        source_scope_level=scope_level,
        source_scope_url=scope_url,
        frames=frames,
        issues=issues,
        input_manifest_sha256=manifest_sha,
        contract_sha256=contract_sha,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        classification_review=classification_review,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_value) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _bundle_manifest(
    bundle: AnemoneNormalizedBundle,
    *,
    artifacts: Optional[dict[str, dict[str, Any]]] = None,
    mode: str,
) -> dict[str, Any]:
    samples = bundle.frames["edna_sample"]
    detections = bundle.frames["edna_detection"]
    source_files = bundle.frames["external_source_file"]
    sample_kind_counts = (
        {
            str(key): int(value)
            for key, value in samples["sample_kind"].value_counts().items()
        }
        if not samples.empty
        else {}
    )
    assignment_method_counts = (
        {
            str(key): int(value)
            for key, value in detections["assignment_method"]
            .value_counts()
            .items()
        }
        if not detections.empty
        else {}
    )
    return {
        "schema_version": 1,
        "normalization_version": config.ANEMONE_NORMALIZATION_VERSION,
        "normalization_id": bundle.normalization_id,
        "source_provider": "anemone",
        "source_family": "edna_metabarcoding",
        "source_snapshot_id": bundle.source_snapshot_id,
        "source_scope_level": bundle.source_scope_level,
        "source_scope_url": bundle.source_scope_url,
        "input_manifest_sha256": bundle.input_manifest_sha256,
        "contract_sha256": bundle.contract_sha256,
        "generated_at": bundle.generated_at,
        "mode": mode,
        "classification_review": bundle.classification_review,
        "classification_review_sha256": (
            stable_sha256(bundle.classification_review) if bundle.classification_review else None
        ),
        "ok": True,
        "row_counts": {
            name: len(frame) for name, frame in bundle.frames.items()
        },
        "sample_kind_counts": sample_kind_counts,
        "control_count": int(
            sum(
                bool(value)
                for value in samples["is_control"]
                if pd.notna(value)
            )
        ),
        "assignment_method_counts": assignment_method_counts,
        "source_file_hashes": [
            {
                "source_file_id": row.get("source_file_id"),
                "relative_path": row.get("relative_path"),
                "selection_status": row.get("selection_status"),
                "sha256": _json_value(row.get("sha256")),
            }
            for row in source_files.to_dict(orient="records")
        ],
        "validation": {
            "errors": 0,
            "warnings": sum(
                issue.severity == "warning" for issue in bundle.issues
            ),
        },
        "artifacts": artifacts or {},
        "issues": [asdict(issue) for issue in bundle.issues],
    }


def normalize_anemone_snapshot(
    snapshot_id: str,
    *,
    execute: bool = False,
    activate: bool = False,
    raw_root: Path = config.RAW_ANEMONE_DIR,
    normalized_root: Path = config.ANEMONE_NORMALIZED_DIR,
    contract: Optional[dict[str, Any]] = None,
    generated_at: Optional[str] = None,
    classification_review: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if activate and not execute:
        raise AnemoneNormalizationError(
            "activation_requires_execute",
            "ANEMONE activation requires --execute.",
        )
    bundle = build_anemone_bundle(
        snapshot_id,
        raw_root=raw_root,
        contract=contract,
        generated_at=generated_at,
        classification_review=classification_review,
    )
    if not execute:
        return _bundle_manifest(bundle, mode="validate")

    staging = normalized_root / "staging" / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=False)
    artifacts: dict[str, dict[str, Any]] = {}
    try:
        for name, frame in bundle.frames.items():
            filename = f"{name}.parquet"
            path = staging / filename
            frame.to_parquet(path, index=False)
            artifacts[name] = {
                "path": filename,
                "sha256": _sha256_file(path),
                "row_count": len(frame),
                "columns": list(frame.columns),
                "schema_sha256": stable_sha256(
                    [(column, str(frame[column].dtype)) for column in frame.columns]
                ),
            }
        manifest = _bundle_manifest(
            bundle,
            artifacts=artifacts,
            mode="execute",
        )
        manifest["status"] = "complete"
        _write_json(staging / "normalization_manifest.json", manifest)
        final_root = normalized_root / "snapshots" / bundle.normalization_id
        final_root.parent.mkdir(parents=True, exist_ok=True)
        reused = False
        if final_root.exists():
            try:
                existing = json.loads(
                    (final_root / "normalization_manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise AnemoneNormalizationError(
                    "normalization_conflict",
                    "Existing ANEMONE normalization bundle is invalid.",
                ) from exc
            if (existing.get("artifacts") != artifacts
                or existing.get("classification_review") != bundle.classification_review):
                raise AnemoneNormalizationError(
                    "normalization_conflict",
                    "Existing ANEMONE normalization ID has different artifacts.",
                )
            shutil.rmtree(staging)
            manifest = existing
            reused = True
        else:
            staging.replace(final_root)
        if activate:
            _write_json(
                normalized_root / "current.json",
                {
                    "schema_version": 1,
                    "normalization_id": bundle.normalization_id,
                    "source_snapshot_id": bundle.source_snapshot_id,
                    "activated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        return {
            **manifest,
            "bundle_path": str(final_root),
            "reused_bundle": reused,
            "activated": activate,
        }
    except Exception:
        if staging.exists() and not any(staging.iterdir()):
            staging.rmdir()
        raise


def resolve_normalized_bundle(
    normalization_id: Optional[str] = None,
    *,
    normalized_root: Path = config.ANEMONE_NORMALIZED_DIR,
) -> tuple[Path, dict[str, Any]]:
    selected_id = normalization_id
    if selected_id is None:
        pointer_path = normalized_root / "current.json"
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AnemoneNormalizationError(
                "normalization_pointer_missing",
                "No active ANEMONE normalization bundle is configured.",
            ) from exc
        selected_id = str(pointer.get("normalization_id") or "")
    if not SNAPSHOT_ID_PATTERN.fullmatch(str(selected_id)):
        raise AnemoneNormalizationError(
            "normalization_id_invalid",
            "ANEMONE normalization ID must be a lowercase SHA-256 value.",
        )
    root = normalized_root / "snapshots" / str(selected_id)
    try:
        manifest = json.loads(
            (root / "normalization_manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise AnemoneNormalizationError(
            "normalization_bundle_missing",
            "ANEMONE normalization bundle is missing or invalid.",
        ) from exc
    if (
        manifest.get("normalization_id") != selected_id
        or manifest.get("status") != "complete"
    ):
        raise AnemoneNormalizationError(
            "normalization_manifest_invalid",
            "ANEMONE normalization manifest is not complete.",
        )
    for artifact in manifest.get("artifacts", {}).values():
        path = _safe_snapshot_file(root, str(artifact.get("path") or ""))
        if not path.is_file() or _sha256_file(path) != artifact.get("sha256"):
            raise AnemoneNormalizationError(
                "normalization_artifact_invalid",
                "ANEMONE normalized artifact is missing or has changed.",
            )
    # Retain the decision inside canonical samples as well as the manifest so
    # retrieval provenance and analysis exports remain self-contained.
    review = manifest.get("classification_review")
    try:
        sample_artifact = manifest["artifacts"]["edna_sample"]
        samples = pd.read_parquet(root / sample_artifact["path"])
        if review is not None:
            from preprocessing.anemone_classification import parse_review

            if parse_review(_canonical_json(review).encode("utf-8")) != review:
                raise ValueError("Noncanonical review")
            if (review["source_snapshot_id"] != manifest["source_snapshot_id"]
                or stable_sha256(review) != manifest.get("classification_review_sha256")):
                raise ValueError("Review identity mismatch")
        elif manifest.get("classification_review_sha256") is not None:
            raise ValueError("Review missing")
        decisions = {d["provider_sample_id"]: d for d in review["decisions"]} if review else {}
        observed = set()
        for row in samples.to_dict(orient="records"):
            raw_record = row.get("classification_review_json")
            record = json.loads(raw_record) if pd.notna(raw_record) else None
            if record is not None:
                sample = row["provider_sample_id"]
                if (sample not in decisions or record["decision"] != decisions[sample]
                    or record["source_snapshot_id"] != manifest["source_snapshot_id"]
                    or record["review_sha256"] != stable_sha256(review)
                    or row["classification_basis"] != "review:" + stable_sha256(record)
                    or row["sample_kind"] != record["decision"]["sample_kind"]
                    or bool(row["is_control"]) != (row["sample_kind"] != "environmental")):
                    raise ValueError("Review decision mismatch")
                observed.add(sample)
            elif str(row.get("classification_basis", "")).startswith("review:"):
                raise ValueError("Review record missing")
        if observed != set(decisions):
            raise ValueError("Review samples missing")
    except (ValueError, KeyError, TypeError) as exc:
        raise AnemoneNormalizationError(
            "classification_review_invalid", "Normalized classification review is inconsistent."
        ) from exc
    return root, manifest


__all__ = [
    "AnemoneNormalizationError",
    "AnemoneNormalizedBundle",
    "NormalizationIssue",
    "build_anemone_bundle",
    "normalize_anemone_snapshot",
    "resolve_normalized_bundle",
    "stable_edna_id",
    "stable_sha256",
]
