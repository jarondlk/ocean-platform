#!/usr/bin/env python3
"""
Refresh missing retrieval-document embeddings without reloading database rows.

Usage:
    python scripts/update_embeddings.py
    python scripts/update_embeddings.py --batch-size 16
    python scripts/update_embeddings.py --dry-run --limit 16
    python scripts/update_embeddings.py --probe
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from db.vector_store import (
    embedding_refresh_candidate_count,
    update_document_embeddings,
)
from model_runtime import RETRIEVAL_DOCUMENT, get_model_runtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_embeddings")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Update missing retrieval-document embeddings")
    parser.add_argument(
        "--batch-size", type=_positive_int, default=32, help="Embedding batch size"
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        help="Maximum documents to update (use a small value for a canary)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count candidates without calling the model runtime or writing rows",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Request one embedding without reading or writing database rows",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Embedding refresh")
    logger.info("=" * 60)
    logger.info("Provider: %s", config.MODEL_PROVIDER)
    logger.info("Model: %s", config.EMBEDDING_MODEL)
    logger.info("Endpoint: %s", get_model_runtime().endpoint)
    logger.info("Dimension: %d", config.EMBEDDING_DIM)
    logger.info("Batch size: %d", args.batch_size)
    if args.probe:
        embedding = get_model_runtime().embed(
            "Onagawa Phase 6 credential and dimension probe",
            model=config.EMBEDDING_MODEL,
            task_type=RETRIEVAL_DOCUMENT,
        )
        if len(embedding) != config.EMBEDDING_DIM:
            raise ValueError(
                f"Probe returned dimension {len(embedding)}; "
                f"expected {config.EMBEDDING_DIM}"
            )
        logger.info("Probe complete: one %d-dimensional vector", len(embedding))
        return 0
    if args.dry_run:
        candidates = embedding_refresh_candidate_count(limit=args.limit)
        logger.info("Dry run complete: %d documents would be updated", candidates)
        return 0
    n_updated = update_document_embeddings(
        batch_size=args.batch_size,
        limit=args.limit,
    )
    logger.info("Embedding refresh complete: %d documents updated", n_updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
