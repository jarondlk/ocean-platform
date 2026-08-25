#!/usr/bin/env python3
"""
Manual batch pipeline orchestrator.

This script intentionally does not schedule, watch, or automatically ingest
data. It runs only when an operator invokes it, and it writes the same durable
manifest/log/status files used by the FastAPI `/pipeline` endpoints.

Examples:
    python scripts/run_pipeline.py --validate-only
    python scripts/run_pipeline.py --stages ingest,build_retrieval_docs --dry-run
    python scripts/run_pipeline.py --execute --tag 2026-07-refresh --embed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.main import (  # noqa: E402
    PIPELINE_DEFAULT_STAGES,
    PIPELINE_STAGE_IDS,
    build_pipeline_preflight,
    run_pipeline_sync,
)
from api.schemas import PipelineRunRequest  # noqa: E402


def _parse_stages(value: str, *, validate_only: bool) -> list[str]:
    if validate_only:
        return ["validate_raw"]
    cleaned = value.strip()
    if not cleaned or cleaned == "full":
        return list(PIPELINE_DEFAULT_STAGES)
    stages = [part.strip() for part in cleaned.split(",") if part.strip()]
    unknown = [stage for stage in stages if stage not in PIPELINE_STAGE_IDS]
    if unknown:
        known = ", ".join(sorted(PIPELINE_STAGE_IDS))
        raise SystemExit(f"Unknown stage '{unknown[0]}'. Known stages: {known}")
    return stages


def _request_from_args(args: argparse.Namespace) -> PipelineRunRequest:
    stages = _parse_stages(args.stages, validate_only=args.validate_only)
    if "load_db" in stages and "backup_database" not in stages:
        stages.insert(stages.index("load_db"), "backup_database")
    execute = args.execute
    if execute is None:
        execute = args.validate_only
    return PipelineRunRequest(
        stages=stages,
        tag=args.tag,
        dry_run=not execute,
        skip_sst=args.skip_sst,
        reset_database=args.reset_db,
        embed_after_load=args.embed,
        embedding_model=args.embedding_model,
        embedding_batch_size=args.embedding_batch_size,
        notes=args.notes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the manual OCEAN Platform batch pipeline")
    parser.add_argument(
        "--stages",
        default="full",
        help="Comma-separated stage IDs, or 'full' for validation, ingestion, analysis, verified database backup, and database loading.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run only safe raw-file checks. Executes by default unless --dry-run is also set.",
    )
    parser.add_argument(
        "--execute",
        dest="execute",
        action="store_true",
        help="Execute commands. Without this, normal pipeline stages write a dry-run manifest only.",
    )
    parser.add_argument(
        "--dry-run",
        dest="execute",
        action="store_false",
        help="Plan commands without executing them. This is the default for non-validation stages.",
    )
    parser.set_defaults(execute=None)
    parser.add_argument("--tag", help="Optional run tag stored in the manifest.")
    parser.add_argument("--notes", help="Optional operator notes stored in the manifest.")
    parser.add_argument("--skip-sst", action="store_true", help="Skip SST preprocessing during ingest.")
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Replace corpus tables instead of the default transactional upsert.",
    )
    parser.add_argument("--embed", dest="embed", action="store_true", default=True, help="Run load_db with --embed when load_db is selected.")
    parser.add_argument("--no-embed", dest="embed", action="store_false", help="Run load_db without --embed.")
    parser.add_argument("--embedding-model", help="Override EMBEDDING_MODEL for embedding stages.")
    parser.add_argument("--embedding-batch-size", type=int, default=32, help="Batch size for standalone embedding refresh.")
    parser.add_argument("--preflight-only", action="store_true", help="Print preflight JSON and do not create a run.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    args = parser.parse_args()

    request = _request_from_args(args)
    preflight = build_pipeline_preflight(request)

    if args.preflight_only:
        payload = preflight.model_dump() if hasattr(preflight, "model_dump") else preflight.dict()
        print(json.dumps(payload, indent=2, default=str))
        return 0 if preflight.ok else 2

    if request.dry_run:
        print("Dry-run mode: commands will be planned but not executed. Add --execute to run them.")
    elif preflight.blockers:
        print("Preflight failed:")
        for blocker in preflight.blockers:
            print(f"  - {blocker}")
        return 2

    status = run_pipeline_sync(request)
    payload = status.model_dump() if hasattr(status, "model_dump") else status.dict()
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"status={status.status}")
        print(f"run_id={status.run_id}")
        print(f"manifest={Path(status.output_dir or '') / 'manifest.json'}")
        print(f"log={status.log_path}")
        if status.error:
            print(f"error={status.error}")
    return 0 if status.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
