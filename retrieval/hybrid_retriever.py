"""
Hybrid retriever combining:
  1. pgvector cosine similarity  (semantic)
  2. PostgreSQL tsvector FTS     (keyword)
  3. Structured SQL filters      (bay, time range, source_type)

Results are fused using Reciprocal Rank Fusion (RRF).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import text
import config

from db.connection import get_session
from db.vector_store import embed_text
from schema.time_range import sql_time_conditions

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """One ranked search result."""
    doc_id: str
    source_type: str
    sample_id: Optional[str]
    event_id: Optional[str]
    time: Optional[str]
    bay: Optional[str]
    station: Optional[str]
    title: str
    text: str
    score: float
    provider: Optional[str] = None
    provider_project_id: Optional[str] = None
    provider_run_id: Optional[str] = None
    assay_id: Optional[str] = None
    assignment_method: Optional[str] = None
    sample_kind: Optional[str] = None
    is_control: Optional[bool] = None
    source_snapshot_id: Optional[str] = None
    rank_sources: Dict[str, int] = field(default_factory=dict)


def hybrid_search(
    query: str,
    *,
    k: int = 10,
    sample_ids: Optional[list[str]] = None,
    assignment_methods: Optional[list[str]] = None,
    source_type: Optional[str] = None,
    sample_id: Optional[str] = None,
    bay: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    provider: Optional[str] = None,
    provider_project_id: Optional[str] = None,
    provider_run_id: Optional[str] = None,
    assignment_method: Optional[str] = None,
    taxon: Optional[str] = None,
    sample_kind: Optional[str] = None,
    is_control: Optional[bool] = None,
    lat_min: Optional[float] = None,
    lat_max: Optional[float] = None,
    lon_min: Optional[float] = None,
    lon_max: Optional[float] = None,
    vector_weight: float = 0.6,
    fts_weight: float = 0.4,
    rrf_k: int = 60,
) -> List[RetrievalResult]:
    """
    Run a hybrid search combining vector similarity and full-text search.

    Results are merged using Reciprocal Rank Fusion (RRF).
    """
    # Build filter clause
    filters = ["active IS TRUE"]
    params: Dict[str, Any] = {"k": k * 2}  # over-fetch for fusion
    if config.EDNA_ARTIFACT_URI:
        from ingestion.artifact_store import ArtifactStore
        pointer, _ = ArtifactStore(config.EDNA_ARTIFACT_URI).pointer('retrieval/current.json')
        if not pointer or pointer.get('status') != 'ready':
            filters.append("source_type <> 'edna_metabarcoding'")
        else:
            # Canonical import marks publication pending before committing;
            # serving resumes only for the exact committed retrieval generation.
            filters.append("(source_type <> 'edna_metabarcoding' OR EXISTS (SELECT 1 FROM corpus_publication AS publication WHERE publication.channel = 'edna' AND publication.generation_id = :published_generation AND publication.manifest_sha256 = :published_manifest))")
            params['published_generation'] = pointer.get('generation_id')
            params['published_manifest'] = pointer.get('manifest_sha256')

    edna_only = any(
        value is not None
        for value in (
            provider,
            provider_project_id,
            provider_run_id,
            assignment_method,
            taxon,
            sample_kind,
            is_control,
        )
    )
    if edna_only and source_type is None:
        source_type = "edna_metabarcoding"

    if source_type:
        filters.append("source_type = :source_type")
        params["source_type"] = source_type
    if sample_id:
        filters.append("sample_id = :sample_id")
        params["sample_id"] = sample_id
    for column, values in (("sample_id", sample_ids), ("assignment_method", assignment_methods)):
        if values is not None:
            filters.append(f"{column} = ANY(:allowed_{column})")
            params[f"allowed_{column}"] = sorted(set(values))
    if bay:
        filters.append("bay = :bay")
        params["bay"] = bay
    times, values = sql_time_conditions("time", time_from, time_to)
    filters.extend(times)
    params.update(values)
    for column, value in (
        ("provider", provider),
        ("provider_project_id", provider_project_id),
        ("provider_run_id", provider_run_id),
        ("assignment_method", assignment_method),
        ("sample_kind", sample_kind),
    ):
        if value is not None:
            filters.append(f"{column} = :{column}")
            params[column] = value
    if is_control is not None:
        filters.append("is_control IS NOT DISTINCT FROM :is_control")
        params["is_control"] = is_control
    for column, operator, name, value in (
        ("lat", ">=", "lat_min", lat_min),
        ("lat", "<=", "lat_max", lat_max),
        ("lon", ">=", "lon_min", lon_min),
        ("lon", "<=", "lon_max", lon_max),
    ):
        if value is not None:
            filters.append(f"{column} {operator} :{name}")
            params[name] = value
    if taxon is not None:
        filters.append(
            "EXISTS ("
            "SELECT 1 FROM edna_detection AS detection "
            "WHERE detection.assay_id = retrieval_document.assay_id "
            "AND detection.assignment_method = retrieval_document.assignment_method "
            "AND detection.active IS TRUE AND ("
            "lower(detection.assigned_taxon_name) = lower(:taxon) OR "
            "lower(detection.superkingdom) = lower(:taxon) OR "
            "lower(detection.kingdom) = lower(:taxon) OR "
            "lower(detection.phylum) = lower(:taxon) OR "
            "lower(detection.\"class\") = lower(:taxon) OR "
            "lower(detection.\"order\") = lower(:taxon) OR "
            "lower(detection.family) = lower(:taxon) OR "
            "lower(detection.genus) = lower(:taxon) OR "
            "lower(detection.species) = lower(:taxon) OR "
            "lower(detection.subspecies) = lower(:taxon)))"
        )
        params["taxon"] = taxon

    where = "WHERE " + " AND ".join(filters)

    vector_results: Dict[str, int] = {}
    fts_results: Dict[str, int] = {}
    doc_map: Dict[str, dict] = {}

    with get_session() as session:
        # --- Vector search ---
        try:
            query_emb = embed_text(query)
            emb_str = "[" + ",".join(str(x) for x in query_emb) + "]"
            params["emb"] = emb_str

            vector_where = where
            if vector_where:
                vector_where += " AND embedding IS NOT NULL"
            else:
                vector_where = "WHERE embedding IS NOT NULL"

            sql = text(f"""
                SELECT doc_id, source_type, sample_id, event_id, time,
                       bay, station, title, text, provider,
                       provider_project_id, provider_run_id, assay_id,
                       assignment_method, sample_kind, is_control,
                       source_snapshot_id
                FROM retrieval_document
                {vector_where}
                ORDER BY embedding <=> :emb
                LIMIT :k
            """)
            rows = session.execute(sql, params).fetchall()
            for rank, r in enumerate(rows):
                vector_results[r.doc_id] = rank + 1
                doc_map[r.doc_id] = {
                    "doc_id": r.doc_id,
                    "source_type": r.source_type,
                    "sample_id": r.sample_id,
                    "event_id": r.event_id,
                    "time": r.time,
                    "bay": r.bay,
                    "station": r.station,
                    "title": r.title,
                    "text": r.text,
                    "provider": r.provider,
                    "provider_project_id": r.provider_project_id,
                    "provider_run_id": r.provider_run_id,
                    "assay_id": r.assay_id,
                    "assignment_method": r.assignment_method,
                    "sample_kind": r.sample_kind,
                    "is_control": r.is_control,
                    "source_snapshot_id": r.source_snapshot_id,
                }
        except Exception as e:
            logger.warning("Vector search failed: %s", e)

        # --- Full-text search ---
        try:
            fts_where = where
            if fts_where:
                fts_where += " AND text_tsv @@ plainto_tsquery('english', :query)"
            else:
                fts_where = "WHERE text_tsv @@ plainto_tsquery('english', :query)"

            fts_params = {**params, "query": query}

            sql = text(f"""
                SELECT doc_id, source_type, sample_id, event_id, time,
                       bay, station, title, text, provider,
                       provider_project_id, provider_run_id, assay_id,
                       assignment_method, sample_kind, is_control,
                       source_snapshot_id,
                       ts_rank_cd(text_tsv, plainto_tsquery('english', :query)) AS fts_rank
                FROM retrieval_document
                {fts_where}
                ORDER BY fts_rank DESC
                LIMIT :k
            """)
            rows = session.execute(sql, fts_params).fetchall()
            for rank, r in enumerate(rows):
                fts_results[r.doc_id] = rank + 1
                if r.doc_id not in doc_map:
                    doc_map[r.doc_id] = {
                        "doc_id": r.doc_id,
                        "source_type": r.source_type,
                        "sample_id": r.sample_id,
                        "event_id": r.event_id,
                        "time": r.time,
                        "bay": r.bay,
                        "station": r.station,
                        "title": r.title,
                        "text": r.text,
                        "provider": r.provider,
                        "provider_project_id": r.provider_project_id,
                        "provider_run_id": r.provider_run_id,
                        "assay_id": r.assay_id,
                        "assignment_method": r.assignment_method,
                        "sample_kind": r.sample_kind,
                        "is_control": r.is_control,
                        "source_snapshot_id": r.source_snapshot_id,
                    }
        except Exception as e:
            logger.warning("FTS search failed: %s", e)

    # --- RRF fusion ---
    all_doc_ids = set(vector_results.keys()) | set(fts_results.keys())
    scored: List[RetrievalResult] = []

    for doc_id in all_doc_ids:
        v_rank = vector_results.get(doc_id, k * 2 + 1)
        f_rank = fts_results.get(doc_id, k * 2 + 1)

        rrf_score = (
            vector_weight * (1.0 / (rrf_k + v_rank))
            + fts_weight * (1.0 / (rrf_k + f_rank))
        )

        info = doc_map[doc_id]
        scored.append(RetrievalResult(
            doc_id=doc_id,
            source_type=info["source_type"],
            sample_id=info["sample_id"],
            event_id=info["event_id"],
            time=info["time"],
            bay=info["bay"],
            station=info["station"],
            title=info["title"],
            text=info["text"],
            score=rrf_score,
            provider=info["provider"],
            provider_project_id=info["provider_project_id"],
            provider_run_id=info["provider_run_id"],
            assay_id=info["assay_id"],
            assignment_method=info["assignment_method"],
            sample_kind=info["sample_kind"],
            is_control=info["is_control"],
            source_snapshot_id=info["source_snapshot_id"],
            rank_sources={"vector": v_rank, "fts": f_rank},
        ))

    scored.sort(key=lambda r: r.score, reverse=True)
    results = scored[:k]

    logger.info(
        "Hybrid search: query=%r  vector=%d  fts=%d  fused=%d",
        query[:60], len(vector_results), len(fts_results), len(results),
    )
    return results
