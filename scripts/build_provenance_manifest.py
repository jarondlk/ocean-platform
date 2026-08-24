#!/usr/bin/env python3
"""
Build the traceability manifest for raw sources, artifacts, documents, and embeddings.

Examples:
    python scripts/build_provenance_manifest.py --json
    python scripts/build_provenance_manifest.py --write --run-id 2026-07-lineage-baseline
    python scripts/build_provenance_manifest.py --no-embeddings --limit-documents 100
    python scripts/build_provenance_manifest.py --validate-only --run-id 2026-08-snapshot-check
    python scripts/build_provenance_manifest.py --publish --run-id 2026-08-pipeline --pipeline-run-id 2026-08-pipeline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.lineage import build_provenance_manifest, write_provenance_manifest  # noqa: E402
from ingestion.provenance_snapshot import (  # noqa: E402
    SnapshotError,
    canonical_json_bytes,
    prepare_snapshot,
    publish_snapshot,
    sha256_bytes,
    snapshot_store_from_uri,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Onagawa traceability manifest")
    parser.add_argument("--limit-documents", type=int, default=500, help="Maximum retrieval-document traces to include.")
    parser.add_argument("--no-embeddings", action="store_true", help="Skip database embedding-status inspection.")
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument("--write", action="store_true", help="Write the legacy local manifest under data/provenance/manifests/ and update latest.")
    output_mode.add_argument("--publish", action="store_true", help="Publish a validated immutable snapshot and atomically advance its latest pointer.")
    output_mode.add_argument("--validate-only", action="store_true", help="Build and validate a complete schema-v2 snapshot without writing it.")
    parser.add_argument("--run-id", help="Unique manifest ID used by --write, --publish, or --validate-only.")
    parser.add_argument("--pipeline-run-id", help="Pipeline execution associated with the snapshot.")
    parser.add_argument("--snapshot-uri", help="Snapshot root, for example gs://bucket/provenance or file:///tmp/provenance.")
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

    if args.publish or args.validate_only:
        if not args.run_id:
            parser.error("--run-id is required with --publish or --validate-only")
        manifest = build_provenance_manifest(
            limit_documents=None,
            include_embeddings=not args.no_embeddings,
        )
        try:
            snapshot = prepare_snapshot(
                manifest,
                manifest_id=args.run_id,
                pipeline_run_id=args.pipeline_run_id,
                require_embedding_capture=args.publish,
            )
            snapshot_data = canonical_json_bytes(snapshot.model_dump(mode="json"))
            payload = {
                "ok": True,
                "mode": "validate" if args.validate_only else "publish",
                "manifest_id": snapshot.manifest_id,
                "schema_version": snapshot.schema_version,
                "documents": len(snapshot.documents),
                "embeddings": len(snapshot.embeddings),
                "size_bytes": len(snapshot_data),
                "sha256": sha256_bytes(snapshot_data),
            }
            if args.publish:
                published = publish_snapshot(
                    snapshot,
                    store=snapshot_store_from_uri(args.snapshot_uri),
                )
                payload.update(
                    {
                        "object_path": published.pointer.object_path,
                        "pointer_generation": published.pointer_generation,
                    }
                )
        except SnapshotError as exc:
            print(f"snapshot_error={exc}", file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2, sort_keys=True))
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
