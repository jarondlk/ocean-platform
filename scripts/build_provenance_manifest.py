#!/usr/bin/env python3
"""
Build the traceability manifest for raw sources, artifacts, documents, and embeddings.

Examples:
    python scripts/build_provenance_manifest.py --json
    python scripts/build_provenance_manifest.py --write --run-id 2026-07-lineage-baseline
    python scripts/build_provenance_manifest.py --no-embeddings --limit-documents 100
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.lineage import build_provenance_manifest, write_provenance_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Onagawa traceability manifest")
    parser.add_argument("--limit-documents", type=int, default=500, help="Maximum retrieval-document traces to include.")
    parser.add_argument("--no-embeddings", action="store_true", help="Skip database embedding-status inspection.")
    parser.add_argument("--write", action="store_true", help="Write manifest under data/provenance/manifests/ and update latest.")
    parser.add_argument("--run-id", help="Manifest ID used when --write is supplied.")
    parser.add_argument("--json", action="store_true", help="Print the full manifest JSON.")
    args = parser.parse_args()

    if args.write:
        path = write_provenance_manifest(
            run_id=args.run_id,
            limit_documents=args.limit_documents,
            include_embeddings=not args.no_embeddings,
        )
        print(f"manifest={path}")
        return 0

    manifest = build_provenance_manifest(
        limit_documents=args.limit_documents,
        include_embeddings=not args.no_embeddings,
    )
    if args.json:
        print(json.dumps(manifest, indent=2, default=str))
    else:
        summary = manifest["summary"]
        print(f"schema_version={manifest['schema_version']}")
        print(f"generated_at={manifest['generated_at']}")
        print(f"source_files={summary['source_files']}")
        print(f"registered_source_records={summary['registered_source_records']}")
        print(f"artifacts={summary['artifacts']}")
        print(f"existing_artifacts={summary['existing_artifacts']}")
        print(f"documents={summary['documents']}")
        print(f"embedded_documents_in_manifest={summary['embedded_documents_in_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
