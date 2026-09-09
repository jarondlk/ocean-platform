"""Bounded, explicit researcher attestations tied to immutable source rows.

This validates evidence identity, not the scientific truth of a review or the
reviewer's identity. Only a trusted operator may submit an approved review.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

MAX_REVIEW_BYTES = 1024 * 1024
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
SAMPLE_KINDS = frozenset(
    {
        "environmental",
        "negative_control",
        "positive_control",
        "mock_community",
        "unknown",
    }
)
CONTROL_SAMPLE_KINDS = SAMPLE_KINDS - {"environmental", "unknown"}


class ReviewError(ValueError):
    """Safe to report without serializing the supplied review."""


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class ClassificationEvidence(StrictRecord):
    source_role: Literal["sample_metadata", "experiment_metadata"]
    source_sha256: Sha256
    row_number: Annotated[int, Field(ge=2)]
    key: Text
    value: Text


class ClassificationDecision(StrictRecord):
    provider_sample_id: Annotated[str, Field(min_length=1, max_length=512)]
    sample_kind: Literal[
        "environmental",
        "negative_control",
        "positive_control",
        "mock_community",
        "unknown",
    ]
    review_id: Annotated[
        str | None,
        Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"),
    ] = None
    review_version: Annotated[int | None, Field(ge=1)] = None
    review_content_sha256: Sha256 | None = None
    reviewer: Annotated[str, Field(min_length=1, max_length=256)]
    reviewed_at: Annotated[str, Field(min_length=1, max_length=64)]
    rationale: Text
    evidence: Annotated[
        list[ClassificationEvidence], Field(min_length=1, max_length=32)
    ]

    @field_validator("reviewed_at")
    @classmethod
    def timezone_required(cls, value):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Review time requires a timezone")
        return timestamp.isoformat()

    @model_validator(mode="after")
    def complete_database_identity(self) -> "ClassificationDecision":
        identity = (
            self.review_id,
            self.review_version,
            self.review_content_sha256,
        )
        if any(value is not None for value in identity) and any(
            value is None for value in identity
        ):
            raise ValueError("Database review identity must be complete")
        return self


class ClassificationReview(StrictRecord):
    schema_version: Literal[1]
    status: Literal["approved"]
    source_snapshot_id: Sha256
    decisions: Annotated[
        list[ClassificationDecision], Field(min_length=1, max_length=200)
    ]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value


class ClassificationReviewLineage(StrictRecord):
    """Canonical sample lineage written by ANEMONE normalization."""

    schema_version: Literal[1]
    source_snapshot_id: Sha256
    review_sha256: Sha256
    provider_classification_basis: Text
    decision: ClassificationDecision

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sample_kind_control_status(sample_kind: str) -> bool | None:
    """Return the only valid tri-state control value for a sample kind."""
    if sample_kind == "environmental":
        return False
    if sample_kind == "unknown":
        return None
    if sample_kind in CONTROL_SAMPLE_KINDS:
        return True
    raise ReviewError("Invalid canonical sample classification.")


def _nullable_control_status(value: Any) -> bool | None:
    if value is None:
        return None
    if type(value) is bool:
        return value
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
        if type(value) is bool:
            return value
    if isinstance(value, float) and math.isnan(value):
        return None
    raise ReviewError("Invalid canonical control status.")


def validate_sample_classification(sample_kind: str, is_control: Any) -> bool | None:
    """Validate, without truthiness coercion, the canonical tri-state pair."""
    expected = sample_kind_control_status(sample_kind)
    observed = _nullable_control_status(is_control)
    if observed is not expected:
        raise ReviewError("Canonical sample classification is inconsistent.")
    return expected


def _unique_json(data: bytes | str, *, label: str) -> Any:
    if isinstance(data, str):
        encoded = data.encode("utf-8")
    elif isinstance(data, bytes):
        encoded = data
    else:
        raise ReviewError(f"{label} is not valid JSON.")
    if len(encoded) > MAX_REVIEW_BYTES:
        raise ReviewError(f"{label} exceeds the 1 MiB limit.")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReviewError(f"{label} contains duplicate JSON keys.")
            result[key] = value
        return result

    try:
        return json.loads(encoded, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ReviewError(f"{label} is not valid JSON.") from exc


def parse_review_lineage(data: bytes | str) -> dict[str, Any]:
    """Strictly parse one persisted ``classification_review_json`` value."""
    try:
        lineage = ClassificationReviewLineage.model_validate(
            _unique_json(data, label="Classification review lineage")
        ).model_dump(exclude_none=True)
    except (ValueError, ValidationError) as exc:
        raise ReviewError("Invalid classification review lineage.") from exc

    decision = lineage["decision"]
    sample_kind_control_status(decision["sample_kind"])
    if decision.get("review_id") is not None:
        # Database-backed reviews always produce a one-decision artifact. This
        # binds every persisted decision field, including the review content
        # digest, to the registered review artifact digest.
        artifact = {
            "schema_version": 1,
            "status": "approved",
            "source_snapshot_id": lineage["source_snapshot_id"],
            "decisions": [decision],
        }
        if canonical_sha256(artifact) != lineage["review_sha256"]:
            raise ReviewError("Classification review lineage digest mismatch.")
    return lineage


def build_review_lineage(
    review: dict[str, Any],
    decision: dict[str, Any],
    *,
    provider_classification_basis: str,
) -> dict[str, Any]:
    """Build and revalidate the canonical lineage for one review decision."""
    lineage = {
        "schema_version": 1,
        "source_snapshot_id": review["source_snapshot_id"],
        "review_sha256": canonical_sha256(review),
        "provider_classification_basis": provider_classification_basis,
        "decision": decision,
    }
    return parse_review_lineage(
        json.dumps(
            lineage,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def validate_sample_review_lineage(
    data: bytes | str | None,
    *,
    sample_kind: str,
    is_control: Any,
    classification_basis: str,
    source_snapshot_id: str,
    provider_sample_id: str,
    expected_review_id: str | None = None,
    expected_review_version: int | None = None,
    expected_review_content_sha256: str | None = None,
) -> dict[str, Any] | None:
    """Validate optional review lineage against its canonical sample row."""
    validate_sample_classification(sample_kind, is_control)
    reviewed_basis = isinstance(classification_basis, str) and classification_basis.startswith(
        "review:"
    )
    if data is None:
        if reviewed_basis:
            raise ReviewError("Canonical classification review lineage is missing.")
        return None
    if not reviewed_basis:
        raise ReviewError("Canonical classification review basis is missing.")

    lineage = parse_review_lineage(data)
    decision = lineage["decision"]
    if (
        lineage["source_snapshot_id"] != source_snapshot_id
        or decision["provider_sample_id"] != provider_sample_id
        or decision["sample_kind"] != sample_kind
        or classification_basis != "review:" + canonical_sha256(lineage)
    ):
        raise ReviewError("Canonical classification review lineage does not match the sample.")
    for field, expected in (
        ("review_id", expected_review_id),
        ("review_version", expected_review_version),
        ("review_content_sha256", expected_review_content_sha256),
    ):
        if expected is not None and decision.get(field) != expected:
            raise ReviewError("Canonical classification review identity mismatch.")
    return lineage


def parse_review(data: bytes) -> dict:
    payload = _unique_json(data, label="Classification review")
    try:
        review = ClassificationReview.model_validate(payload).model_dump(
            exclude_none=True
        )
    except (ValueError, UnicodeError, ValidationError) as exc:
        raise ReviewError("Invalid or unapproved classification review.") from exc
    samples = [item["provider_sample_id"] for item in review["decisions"]]
    if len(samples) != len(set(samples)):
        raise ReviewError("Classification review contains duplicate samples.")
    for decision in review["decisions"]:
        rows = [(e["source_role"], e["row_number"]) for e in decision["evidence"]]
        if len(rows) != len(set(rows)):
            raise ReviewError("Classification review contains duplicate evidence rows.")
        decision["evidence"].sort(key=lambda e: (e["source_role"], e["row_number"]))
    review["decisions"].sort(key=lambda d: d["provider_sample_id"])
    return review


def read_review(path: Path) -> dict:
    try:
        if path.is_symlink() or not path.is_file():
            raise ReviewError("Classification review must be a regular file.")
        with path.open("rb") as handle:
            return parse_review(handle.read(MAX_REVIEW_BYTES + 1))
    except OSError as exc:
        raise ReviewError("Classification review is unreadable.") from exc


def validate_review_evidence(review: dict, snapshot_id: str, selected: dict) -> None:
    from preprocessing.anemone import (
        CLASSIFICATION_KEYS,
        CLASSIFICATION_VALUES,
        _read_xz_tsv,
        _classification,
        _metadata_map,
    )
    import re

    if review["source_snapshot_id"] != snapshot_id:
        raise ReviewError("Classification review references a different snapshot.")
    for decision in review["decisions"]:
        sample = decision["provider_sample_id"]
        source = selected.get((sample, "sample_metadata"))
        if source is None:
            raise ReviewError("Classification review references an unknown sample.")
        header, rows = _read_xz_tsv(source["path"])
        metadata, _ = _metadata_map(header, rows, expected_sample=sample)
        evidence_rows = {"sample_metadata": rows}
        # Also reject mixed/conflicting fields even if the legacy classifier
        # returns unknown for the first unrecognized field.
        recognized = any(
            re.sub(r"[^a-z0-9]+", "_", metadata.get(key, "").lower()).strip("_")
            in CLASSIFICATION_VALUES
            for key in CLASSIFICATION_KEYS
        )
        if _classification(metadata)[0] != "unknown" or recognized:
            raise ReviewError(
                "Review cannot override a recognized provider classification."
            )
        for evidence in decision["evidence"]:
            item = selected.get((sample, evidence["source_role"]))
            if item is None or item["sha256"] != evidence["source_sha256"]:
                raise ReviewError("Classification evidence file hash does not match.")
            role = evidence["source_role"]
            if role not in evidence_rows:
                header, rows = _read_xz_tsv(item["path"])
                _metadata_map(header, rows, expected_sample=sample)
                evidence_rows[role] = rows
            rows = evidence_rows[role]
            index = evidence["row_number"] - 2
            if index >= len(rows) or [value.strip() for value in rows[index]] != [
                sample,
                evidence["key"],
                evidence["value"],
            ]:
                raise ReviewError("Classification evidence row does not match.")


def review_template(snapshot_id: str, *, raw_root: Path, contract=None) -> dict:
    """Return a non-executable draft; never choose a classification or reviewer."""
    from preprocessing.anemone import (
        _verify_snapshot,
        _read_xz_tsv,
        _classification,
        _metadata_map,
        snapshot_contract,
    )

    _, _, _, selected = _verify_snapshot(
        snapshot_id,
        raw_root=raw_root,
        contract=contract or snapshot_contract(snapshot_id, raw_root=raw_root),
    )
    decisions = []
    for sample in sorted({sample for sample, _ in selected}):
        item = selected[(sample, "sample_metadata")]
        header, rows = _read_xz_tsv(item["path"])
        metadata, _ = _metadata_map(header, rows, expected_sample=sample)
        if _classification(metadata)[0] != "unknown":
            continue
        decisions.append(
            {
                "provider_sample_id": sample,
                "sample_kind": "unknown",
                "reviewer": "",
                "reviewed_at": "",
                "rationale": "",
                # Candidates only: the reviewer must select relevant supporting rows.
                "evidence": [
                    {
                        "source_role": "sample_metadata",
                        "source_sha256": item["sha256"],
                        "row_number": number,
                        "key": row[1].strip(),
                        "value": row[2].strip(),
                    }
                    for number, row in enumerate(rows, start=2)
                    if row[2].strip()
                ][:32],
            }
        )
        if len(decisions) > 200:
            raise ReviewError(
                "Review template exceeds the 200-sample limit; use a smaller snapshot."
            )
    return {
        "schema_version": 1,
        "status": "draft",
        "source_snapshot_id": snapshot_id,
        "decisions": decisions,
    }
