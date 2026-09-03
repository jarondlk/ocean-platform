"""Bounded, explicit researcher attestations tied to immutable source rows.

This validates evidence identity, not the scientific truth of a review or the
reviewer's identity. Only a trusted operator may submit an approved review.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_REVIEW_BYTES = 1024 * 1024
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, Field(min_length=1, max_length=4000)]


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
        "environmental", "negative_control", "positive_control", "mock_community"
    ]
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


def parse_review(data: bytes) -> dict:
    if len(data) > MAX_REVIEW_BYTES:
        raise ReviewError("Classification review exceeds the 1 MiB limit.")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReviewError("Classification review contains duplicate JSON keys.")
            result[key] = value
        return result

    try:
        payload = json.loads(data, object_pairs_hook=unique_object)
        review = ClassificationReview.model_validate(payload).model_dump()
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
