"""
Vector store – embed documents through the model runtime and search pgvector.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

import config
from model_runtime import get_model_runtime
from .connection import get_session

logger = logging.getLogger(__name__)


def embed_text(text_input: str, model: str = None) -> List[float]:
    """
    Get an embedding vector from the configured model runtime.
    """
    model = model or config.EMBEDDING_MODEL
    return get_model_runtime().embed(text_input, model=model)


def embed_batch(texts: List[str], model: str = None) -> List[List[float]]:
    """
    Embed a batch of texts through the configured runtime. Fall back to
    sequential calls if the provider cannot complete a batch request.
    """
    model = model or config.EMBEDDING_MODEL

    try:
        return get_model_runtime().embed_batch(texts, model=model)
    except Exception as e:
        logger.warning("Batch embedding failed, falling back to sequential: %s", e)

    # Sequential fallback
    return [embed_text(t, model) for t in texts]


def update_document_embeddings(batch_size: int = 32) -> int:
    """
    Find retrieval documents without embeddings and compute them.
    Returns the number of documents updated.
    """
    from .models import RetrievalDocument

    count = 0

    with get_session() as session:
        docs = (
            session.query(RetrievalDocument)
            .filter(RetrievalDocument.embedding.is_(None))
            .all()
        )

        if not docs:
            logger.info("All documents already have embeddings")
            return 0

        logger.info("Embedding %d documents...", len(docs))

        for i in range(0, len(docs), batch_size):
            batch = docs[i : i + batch_size]
            texts = [d.text for d in batch]

            try:
                embeddings = embed_batch(texts)
                for doc, emb in zip(batch, embeddings):
                    doc.embedding = emb
                    count += 1
                session.flush()
                logger.info("  Embedded batch %d-%d", i, i + len(batch))
            except Exception as e:
                logger.error("  Failed batch %d-%d: %s", i, i + len(batch), e)

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
