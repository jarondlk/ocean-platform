"""
Local retriever (no PostgreSQL required).

Loads retrieval_documents.jsonl and uses:
  - BM25 for keyword search
  - Ollama for vector search (in-memory numpy cosine)
  - RRF fusion

This is the fallback when PostgreSQL is not available.
"""
from __future__ import annotations

import json
import hashlib
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

import config
from schema.time_range import matches_time
from retrieval.edna_publication import retrieval_path

logger = logging.getLogger(__name__)

BAY_BY_LOCATION = {
    "Onagawa Bay": "O",
    "Ishinomaki Bay": "I",
    "Mutsu Bay": "M",
}


# =====================================================================
# BM25 (adapted from existing engines/rag_engine.py)
# =====================================================================
class BM25:
    """Simple in-memory BM25 scorer."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._corpus: List[List[str]] = []
        self._doc_len: List[int] = []
        self._avgdl: float = 0.0
        self._df: Counter = Counter()
        self._N: int = 0

    def fit(self, documents: List[str]) -> None:
        self._corpus = [self._tokenize(d) for d in documents]
        self._N = len(self._corpus)
        self._doc_len = [len(d) for d in self._corpus]
        self._avgdl = sum(self._doc_len) / max(self._N, 1)
        self._df = Counter()
        for doc in self._corpus:
            for term in set(doc):
                self._df[term] += 1

    def score(self, query: str) -> List[float]:
        q_tokens = self._tokenize(query)
        scores = []
        for i, doc in enumerate(self._corpus):
            s = 0.0
            dl = self._doc_len[i]
            tf_map = Counter(doc)
            for qt in q_tokens:
                tf = tf_map.get(qt, 0)
                df = self._df.get(qt, 0)
                idf = math.log((self._N - df + 0.5) / (df + 0.5) + 1.0)
                num = tf * (self.k1 + 1)
                den = tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                s += idf * num / den
            scores.append(s)
        return scores

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", text.lower())


# =====================================================================
# Local retriever
# =====================================================================
class LocalRetriever:
    """
    In-memory hybrid retriever using BM25 + optional Ollama embeddings.
    """

    def __init__(self) -> None:
        self.documents: List[dict] = []
        self.bm25 = BM25()
        self._embeddings: Optional[np.ndarray] = None
        self._embed_available: bool = False

    def load(self, jsonl_path: Path | None = None) -> None:
        """Load documents from JSONL."""
        self.documents = []
        self._embeddings = None
        self._embed_available = False
        paths = (
            [jsonl_path]
            if jsonl_path is not None
            else [
                config.SERVING_DIR / "retrieval_documents.jsonl",
                retrieval_path("jsonl"),
            ]
        )
        existing_paths = [path for path in paths if path.exists()]
        if not existing_paths:
            logger.warning("Document files not found: %s", paths)
            return

        documents: dict[str, dict] = {}
        for path in existing_paths:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    document = self._normalize_document(json.loads(line))
                    if document.get("active", True) is False:
                        continue
                    doc_id = str(document.get("doc_id") or "")
                    if doc_id:
                        documents[doc_id] = document
        self.documents = [documents[key] for key in sorted(documents)]

        # Fit BM25
        texts = [d.get("text", "") for d in self.documents]
        self.bm25.fit(texts)

        logger.info("Loaded %d documents for local retrieval", len(self.documents))

    @staticmethod
    def _normalize_document(doc: dict) -> dict:
        """Normalize legacy JSONL aliases to the canonical retrieval schema."""
        normalized = doc.copy()

        doc_id = normalized.get("doc_id") or normalized.get("id")
        if doc_id:
            normalized["doc_id"] = doc_id
            normalized.setdefault("id", doc_id)

        time_value = normalized.get("time") or normalized.get("date")
        if time_value:
            normalized["time"] = time_value
            normalized.setdefault("date", time_value)

        sample_id = normalized.get("sample_id")
        if sample_id:
            parts = str(sample_id).split("-")
            if len(parts) >= 3 and not normalized.get("bay"):
                normalized["bay"] = parts[2]
            if len(parts) >= 4 and not normalized.get("station"):
                normalized["station"] = parts[3]
        elif not normalized.get("bay"):
            location = normalized.get("location")
            if normalized.get("source_type") != "remote_sensing":
                normalized["bay"] = BAY_BY_LOCATION.get(location)

        return normalized

    def ensure_embeddings(self) -> bool:
        """
        Try to compute embeddings via Ollama.
        Returns True if embeddings are available.
        """
        if self._embeddings is not None:
            return True
        if not self.documents:
            return False

        fingerprint = hashlib.sha256(json.dumps({
            "provider": config.MODEL_PROVIDER,
            "model": config.EMBEDDING_MODEL,
            "dimension": config.EMBEDDING_DIM,
            "documents": [(doc.get("doc_id"), doc.get("text")) for doc in self.documents],
        }, sort_keys=True).encode()).hexdigest()

        # Try loading cached embeddings
        cache_path = config.SERVING_DIR / "retrieval_embeddings.npy"
        metadata_path = config.SERVING_DIR / "retrieval_embeddings.meta.json"
        if cache_path.exists() and metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("fingerprint") == fingerprint:
                    cached = np.load(str(cache_path), allow_pickle=False)
                    if cached.shape == (len(self.documents), config.EMBEDDING_DIM):
                        self._embeddings = cached
                        self._embed_available = True
                        logger.info("Loaded cached embeddings: %s", cached.shape)
                        return True
            except (ValueError, OSError):
                logger.warning("Ignoring invalid local embedding cache")

        # Try computing via Ollama
        try:
            from db.vector_store import embed_batch

            texts = [d.get("text", "") for d in self.documents]
            batch_size = 32
            all_embs = []

            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                embs = embed_batch(batch)
                all_embs.extend(embs)
                logger.info("  Embedded %d/%d", min(i + batch_size, len(texts)), len(texts))

            self._embeddings = np.array(all_embs, dtype="float32")
            np.save(str(cache_path), self._embeddings)
            metadata_path.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
            self._embed_available = True
            logger.info("Computed and cached embeddings: %s", self._embeddings.shape)
            return True

        except Exception as e:
            logger.warning("Could not compute embeddings: %s", e)
            return False

    def search(
        self,
        query: str,
        k: int = 8,
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
    ) -> List[dict]:
        """
        Hybrid search: BM25 + (optional) vector, fused with RRF.
        """
        if not self.documents:
            return []

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

        # Apply filters
        members = None if sample_ids is None else set(sample_ids)
        methods = None if assignment_methods is None else set(assignment_methods)
        valid_indices = []
        for i, doc in enumerate(self.documents):
            if members is not None and doc.get('sample_id') not in members:
                continue
            if methods is not None and doc.get('assignment_method') not in methods:
                continue
            if doc.get("active", True) is False:
                continue
            if source_type and doc.get("source_type") != source_type:
                continue
            if sample_id and doc.get("sample_id") != sample_id:
                continue
            if bay and doc.get("bay") != bay:
                continue
            if not matches_time(doc.get("time"), time_from, time_to):
                continue
            if provider and doc.get("provider") != provider:
                continue
            if provider_project_id and doc.get("provider_project_id") != provider_project_id:
                continue
            if provider_run_id and doc.get("provider_run_id") != provider_run_id:
                continue
            if assignment_method and doc.get("assignment_method") != assignment_method:
                continue
            if sample_kind and doc.get("sample_kind") != sample_kind:
                continue
            if is_control is not None and doc.get("is_control") is not is_control:
                continue
            if lat_min is not None and (doc.get("lat") is None or float(doc["lat"]) < lat_min):
                continue
            if lat_max is not None and (doc.get("lat") is None or float(doc["lat"]) > lat_max):
                continue
            if lon_min is not None and (doc.get("lon") is None or float(doc["lon"]) < lon_min):
                continue
            if lon_max is not None and (doc.get("lon") is None or float(doc["lon"]) > lon_max):
                continue
            if taxon:
                metadata = doc.get("metadata") or {}
                terms = metadata.get("taxon_terms") if isinstance(metadata, dict) else []
                if taxon.casefold() not in {
                    str(value).casefold() for value in (terms or [])
                }:
                    continue
            valid_indices.append(i)

        if not valid_indices:
            return []

        # BM25 scores
        all_bm25 = self.bm25.score(query)
        bm25_scored = [(i, all_bm25[i]) for i in valid_indices]
        bm25_scored.sort(key=lambda x: x[1], reverse=True)
        bm25_ranks = {idx: rank + 1 for rank, (idx, _) in enumerate(bm25_scored)}

        # Vector scores
        vector_ranks: Dict[int, int] = {}
        if self._embed_available and self._embeddings is not None:
            try:
                from db.vector_store import embed_text
                q_emb = np.array(embed_text(query), dtype="float32")
                valid_embs = self._embeddings[valid_indices]
                # Cosine similarity
                norms = np.linalg.norm(valid_embs, axis=1) * np.linalg.norm(q_emb)
                norms[norms == 0] = 1e-10
                sims = valid_embs @ q_emb / norms
                sim_order = np.argsort(-sims)
                for rank, pos in enumerate(sim_order):
                    vector_ranks[valid_indices[pos]] = rank + 1
            except Exception as e:
                logger.warning("Vector search failed: %s", e)

        # RRF fusion
        rrf_k = 60
        v_weight = 0.6 if vector_ranks else 0.0
        b_weight = 1.0 - v_weight

        scored = []
        for idx in valid_indices:
            br = bm25_ranks.get(idx, len(valid_indices) + 1)
            vr = vector_ranks.get(idx, len(valid_indices) + 1)
            score = b_weight / (rrf_k + br) + v_weight / (rrf_k + vr)
            scored.append((idx, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_k = scored[:k]

        results = []
        for idx, score in top_k:
            doc = self.documents[idx].copy()
            doc["score"] = score
            results.append(doc)

        return results


# Global singleton
_retriever: Optional[LocalRetriever] = None
_corpus_signature: tuple = ()


def get_local_retriever() -> LocalRetriever:
    """Get or create the global local retriever instance."""
    global _retriever, _corpus_signature
    paths = [config.SERVING_DIR / "retrieval_documents.jsonl", retrieval_path("jsonl")]
    signature = tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        if path.exists() else (str(path), None, None)
        for path in paths
    )
    if _retriever is None or signature != _corpus_signature:
        _retriever = LocalRetriever()
        _retriever.load()
        _retriever.ensure_embeddings()
        _corpus_signature = signature
    return _retriever
