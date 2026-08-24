"""
Vector store – embed documents through the model runtime and search pgvector.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, text

import config
from model_runtime import RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY, get_model_runtime
from .connection import get_session

logger = logging.getLogger(__name__)


def embed_text(
    text_input: str,
    model: str = None,
    *,
    task_type: str = RETRIEVAL_QUERY,
) -> List[float]:
    """
    Get an embedding vector from the configured model runtime.
    """
    model = model or config.EMBEDDING_MODEL
    return get_model_runtime().embed(
        text_input,
        model=model,
        task_type=task_type,
    )


def embed_batch(
    texts: List[str],
    model: str = None,
    *,
    task_type: str = RETRIEVAL_DOCUMENT,
) -> List[List[float]]:
    """
    Embed a batch of texts through the configured runtime.

    Provider errors deliberately propagate. Retrying every item after a failed
    batch can duplicate billable calls and conceal a partial provider outage.
    """
    model = model or config.EMBEDDING_MODEL

    return get_model_runtime().embed_batch(
        texts,
        model=model,
        task_type=task_type,
    )


def _embedding_refresh_query(session: Any) -> Any:
    from .models import RetrievalDocument

    return session.query(RetrievalDocument).filter(
        or_(
            RetrievalDocument.embedding.is_(None),
            RetrievalDocument.embedding_provider != config.MODEL_PROVIDER,
            RetrievalDocument.embedding_provider.is_(None),
            RetrievalDocument.embedding_model != config.EMBEDDING_MODEL,
            RetrievalDocument.embedding_model.is_(None),
            RetrievalDocument.embedding_dim != config.EMBEDDING_DIM,
            RetrievalDocument.embedding_dim.is_(None),
        )
    )


def embedding_refresh_candidate_count(limit: Optional[int] = None) -> int:
    """Count documents needing the configured embedding identity."""
    with get_session() as session:
        count = _embedding_refresh_query(session).count()
    return min(count, limit) if limit is not None else count


def update_document_embeddings(
    batch_size: int = 32,
    *,
    limit: Optional[int] = None,
) -> int:
    """
    Find retrieval documents without embeddings and compute them.
    Returns the number of documents updated.
    """
    from .models import RetrievalDocument

    count = 0

    with get_session() as session:
        query = _embedding_refresh_query(session).order_by(RetrievalDocument.doc_id)
        if limit is not None:
            query = query.limit(limit)
        docs = query.all()

        if not docs:
            logger.info("All documents already have embeddings")
            return 0

        logger.info("Embedding %d documents...", len(docs))

        for i in range(0, len(docs), batch_size):
            batch = docs[i : i + batch_size]
            texts = [d.text for d in batch]

            embeddings = embed_batch(texts, task_type=RETRIEVAL_DOCUMENT)
            if len(embeddings) != len(batch):
                raise ValueError(
                    f"Embedding runtime returned {len(embeddings)} vectors "
                    f"for {len(batch)} documents"
                )
            embedded_at = datetime.now(timezone.utc)
            for doc, embedding in zip(batch, embeddings):
                if len(embedding) != config.EMBEDDING_DIM:
                    raise ValueError(
                        f"Embedding dimension {len(embedding)} does not match "
                        f"configured dimension {config.EMBEDDING_DIM}"
                    )
                doc.embedding = embedding
                doc.embedding_provider = config.MODEL_PROVIDER
                doc.embedding_model = config.EMBEDDING_MODEL
                doc.embedding_dim = config.EMBEDDING_DIM
                doc.embedded_at = embedded_at
                count += 1
            session.flush()
            logger.info("  Embedded batch %d-%d", i, i + len(batch))

    logger.info("Updated %d document embeddings", count)
    return count


def search_similar(
    query: str,
    k: int = 5,
    source_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search for documents similar to *query* using pgvector cosine distance.
    """
    query_emb = embed_text(query)

    with get_session() as session:
        emb_str = "[" + ",".join(str(x) for x in query_emb) + "]"

        where_clause = ""
        params: Dict[str, Any] = {"emb": emb_str, "k": k}
        if source_type:
            where_clause = "AND source_type = :source_type"
            params["source_type"] = source_type

        sql = text(f"""
            SELECT doc_id, source_type, sample_id, event_id, time,
                   lat, lon, bay, station, title, text,
                   embedding <=> :emb AS distance
            FROM retrieval_document
            WHERE embedding IS NOT NULL {where_clause}
            ORDER BY embedding <=> :emb
            LIMIT :k
        """)

        rows = session.execute(sql, params).fetchall()

    return [
        {
            "doc_id": r.doc_id,
            "source_type": r.source_type,
            "sample_id": r.sample_id,
            "event_id": r.event_id,
            "time": r.time,
            "lat": r.lat,
            "lon": r.lon,
            "bay": r.bay,
            "station": r.station,
            "title": r.title,
            "text": r.text,
            "distance": float(r.distance),
            "score": 1.0 - float(r.distance),  # cosine similarity
        }
        for r in rows
    ]
