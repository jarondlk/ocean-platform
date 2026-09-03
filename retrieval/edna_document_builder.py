"""Deterministic retrieval documents for canonical eDNA metabarcoding rows."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

import pandas as pd

from retrieval.document_builder import RetrievalDocument


EDNA_SOURCE_TYPE = "edna_metabarcoding"
EDNA_RETRIEVAL_DOCUMENT_VERSION = 1
EDNA_ASSIGNMENT_METHODS = frozenset(
    {"qcauto_target", "qcauto_95pct_3nn_target"}
)
TAXON_COLUMNS = (
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
)


def _present(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value)) and str(value).strip() != ""
    except (TypeError, ValueError):
        return True


def _text(value: Any) -> str | None:
    return str(value).strip() if _present(value) else None


def _boolean(value: Any) -> bool | None:
    if not _present(value):
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        return None
    return bool(value)


def _active(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "active" not in frame.columns:
        return frame.copy()
    return frame[frame["active"].fillna(False).astype(bool)].copy()


def _taxon_terms(rows: pd.DataFrame) -> list[str]:
    terms: set[str] = set()
    for column in TAXON_COLUMNS:
        if column not in rows.columns:
            continue
        terms.update(
            str(value).strip()
            for value in rows[column].tolist()
            if _present(value)
        )
    return sorted(terms, key=lambda value: (value.casefold(), value))


def _source_ids(*rows: Iterable[Any]) -> list[str]:
    values = {
        str(value).strip()
        for sequence in rows
        for value in sequence
        if _present(value)
    }
    return sorted(values)


def _control_label(sample_kind: str | None, is_control: bool | None) -> str:
    if is_control is True:
        return f"control ({sample_kind or 'unspecified'})"
    if is_control is False:
        return sample_kind or "environmental"
    return f"{sample_kind or 'unknown'}; control status unknown"


def _method_label(method: str) -> str:
    return {
        "qcauto_target": "QCauto",
        "qcauto_95pct_3nn_target": "QCauto 95%-3NN",
    }[method]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _record_provenance(kind: str, identifier: str, row: pd.Series) -> dict[str, Any]:
    locator = row.get("source_row_number")
    if not _present(locator):
        raw = row.get("source_row_numbers_json")
        locator = json.loads(raw) if isinstance(raw, str) and raw else []
    else:
        locator = int(locator)
    return {
        "entity_type": kind,
        "entity_id": identifier,
        "source_snapshot_id": _text(row.get("source_snapshot_id")),
        "source_file_id": _text(row.get("source_file_id")),
        "source_row_locator": locator,
        "source_row_hash": _text(row.get("source_row_hash")),
    }


def document_source_row_hash(document: RetrievalDocument) -> str:
    """Hash the complete retrieval row, including provenance metadata."""
    payload = {
        "version": EDNA_RETRIEVAL_DOCUMENT_VERSION,
        "doc_id": document.doc_id,
        "source_type": document.source_type,
        "sample_id": document.sample_id,
        "event_id": document.event_id,
        "time": document.time,
        "lat": document.lat,
        "lon": document.lon,
        "title": document.title,
        "text": document.text,
        "active": document.active,
        "provider": document.provider,
        "provider_project_id": document.provider_project_id,
        "provider_run_id": document.provider_run_id,
        "assay_id": document.assay_id,
        "assignment_method": document.assignment_method,
        "sample_kind": document.sample_kind,
        "is_control": document.is_control,
        "source_snapshot_id": document.source_snapshot_id,
        "metadata": document.metadata,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_edna_documents(
    samples: pd.DataFrame,
    assays: pd.DataFrame,
    detections: pd.DataFrame,
) -> list[RetrievalDocument]:
    """Build one bounded document per active sample/assay/assignment method."""
    active_samples = _active(samples)
    active_assays = _active(assays)
    active_detections = _active(detections)
    if active_samples.empty or active_assays.empty or active_detections.empty:
        return []

    sample_by_id = {
        str(row["sample_id"]): row
        for _, row in active_samples.sort_values("sample_id").iterrows()
    }
    assay_by_id = {
        str(row["assay_id"]): row
        for _, row in active_assays.sort_values("assay_id").iterrows()
    }
    documents: list[RetrievalDocument] = []

    grouped = active_detections.groupby(
        ["assay_id", "assignment_method"],
        dropna=False,
        sort=True,
    )
    for (assay_id_value, method_value), rows in grouped:
        assay_id = _text(assay_id_value)
        method = _text(method_value)
        if not assay_id or method not in EDNA_ASSIGNMENT_METHODS:
            continue
        assay = assay_by_id.get(assay_id)
        if assay is None:
            continue
        sample_id = _text(assay.get("sample_id"))
        sample = sample_by_id.get(sample_id or "")
        if sample is None or not sample_id:
            continue

        provider = _text(sample.get("provider")) or "anemone"
        provider_sample = _text(sample.get("provider_sample_id")) or sample_id
        project = _text(sample.get("provider_project_id"))
        run = _text(sample.get("provider_run_id"))
        sample_kind = _text(sample.get("sample_kind")) or "unknown"
        is_control = _boolean(sample.get("is_control"))
        collection_time = _text(sample.get("collection_date_utc"))
        target_gene = _text(assay.get("target_gene"))
        primer_set = _text(assay.get("primer_set"))
        sequencing_method = _text(assay.get("sequencing_method"))
        ordered = rows.sort_values(
            ["read_count", "detection_id"],
            ascending=[False, True],
            kind="mergesort",
        )
        top_rows = ordered.head(10)
        total_reads = int(
            pd.to_numeric(rows["read_count"], errors="coerce").fillna(0).sum()
        )
        supplied_copies = (
            int(rows["copies_per_ml"].notna().sum())
            if "copies_per_ml" in rows.columns
            else 0
        )

        lines = [
            f"ANEMONE MiFish sample {provider_sample}.",
            f"Provider: {provider}.",
        ]
        scope = [value for value in (project, run) if value]
        if scope:
            lines.append("Provider scope: " + ", ".join(scope) + ".")
        if collection_time:
            lines.append(f"Collection time: {collection_time}.")
        lat = float(sample["lat"]) if _present(sample.get("lat")) else None
        lon = float(sample["lon"]) if _present(sample.get("lon")) else None
        if lat is not None and lon is not None:
            lines.append(f"Coordinates: {lat:.6f}, {lon:.6f}.")
        lines.append(
            "Sample classification: "
            + _control_label(sample_kind, is_control)
            + "."
        )
        assay_parts = [
            f"target gene {target_gene}" if target_gene else None,
            f"primer set {primer_set}" if primer_set else None,
            f"sequencing method {sequencing_method}" if sequencing_method else None,
        ]
        assay_text = ", ".join(part for part in assay_parts if part)
        if assay_text:
            lines.append(f"Assay: {assay_text}.")
        lines.append(
            f"Assignment method: {_method_label(method)} ({method})."
        )
        lines.append(
            f"Detection records: {len(rows)}. "
            f"Sum of source read_count values: {total_reads}. "
            f"Records with source-supplied copies/mL: {supplied_copies}."
        )

        featured: list[str] = []
        for _, detection in top_rows.iterrows():
            taxon = _text(detection.get("assigned_taxon_name")) or "unassigned"
            rank = _text(detection.get("assigned_taxon_rank")) or "rank unknown"
            count = int(detection.get("read_count") or 0)
            featured.append(f"{taxon} ({rank}), read count {count}")
        if featured:
            lines.append("Highest-read detection records: " + "; ".join(featured) + ".")
        lines.append(
            "Read counts are sequencing counts, not abundance, biomass, "
            "concentration, or organism counts. Assignment methods are not "
            "merged. A missing detection record does not establish biological absence."
        )

        snapshot_ids = _source_ids(
            [sample.get("source_snapshot_id")],
            [assay.get("source_snapshot_id")],
            rows.get("source_snapshot_id", pd.Series(dtype="string")).tolist(),
        )
        source_file_ids = _source_ids(
            [sample.get("source_file_id")],
            [assay.get("source_file_id")],
            rows.get("source_file_id", pd.Series(dtype="string")).tolist(),
        )
        featured_ids = [str(value) for value in top_rows["detection_id"].tolist()]
        canonical_records = [
            _record_provenance("sample", sample_id, sample),
            _record_provenance("assay", assay_id, assay),
            *[
                _record_provenance("detection", str(row["detection_id"]), row)
                for _, row in top_rows.iterrows()
            ],
        ]
        metadata = {
            "edna_retrieval_document_version": EDNA_RETRIEVAL_DOCUMENT_VERSION,
            "source_family": EDNA_SOURCE_TYPE,
            "source_snapshot_ids": snapshot_ids,
            "source_file_ids": source_file_ids,
            "featured_detection_ids": featured_ids,
            "canonical_records": canonical_records,
            "detection_set_sha256": hashlib.sha256(
                _canonical_json([
                    [str(row["detection_id"]), _text(row.get("source_row_hash"))]
                    for _, row in rows.sort_values("detection_id").iterrows()
                ]).encode("utf-8")
            ).hexdigest(),
            "taxon_terms": _taxon_terms(rows),
            "detection_count": int(len(rows)),
            "read_count_sum": total_reads,
            "copies_per_ml_record_count": supplied_copies,
        }
        documents.append(
            RetrievalDocument(
                doc_id=f"edna_{assay_id}_{method}",
                source_type=EDNA_SOURCE_TYPE,
                sample_id=sample_id,
                event_id=_text(sample.get("anchor_event_id")),
                time=collection_time,
                lat=lat,
                lon=lon,
                bay=None,
                station=None,
                title=(
                    f"ANEMONE MiFish {provider_sample} — {_method_label(method)}"
                ),
                text=" ".join(lines),
                provider=provider,
                provider_project_id=project,
                provider_run_id=run,
                assay_id=assay_id,
                assignment_method=method,
                sample_kind=sample_kind,
                is_control=is_control,
                source_snapshot_id=_text(sample.get("source_snapshot_id")),
                metadata=metadata,
            )
        )

    return sorted(documents, key=lambda document: document.doc_id)
