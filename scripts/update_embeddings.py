#!/usr/bin/env python3
"""
Refresh missing retrieval-document embeddings without reloading database rows.

Usage:
    python scripts/update_embeddings.py
    python scripts/update_embeddings.py --batch-size 16
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from db.vector_store import update_document_embeddings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_embeddings")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update missing retrieval-document embeddings")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Embedding refresh")
    logger.info("=" * 60)
    logger.info("Model: %s", config.EMBEDDING_MODEL)
    logger.info("Ollama URL: %s", config.OLLAMA_BASE_URL)
    logger.info("Batch size: %d", args.batch_size)
    n_updated = update_document_embeddings(batch_size=args.batch_size)
    logger.info("Embedding refresh complete: %d documents updated", n_updated)


if __name__ == "__main__":
    main()
