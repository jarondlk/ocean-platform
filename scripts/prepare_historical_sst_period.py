"""Process retained context into a full regional preview; no provider download.

Execution reads the private archive, caches sealed local monthly packages, and
applies explicit provisional rules. It never accesses a database or publishes.
"""

import argparse
import fcntl
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import atomic_json, digest
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json
from ingestion.sst_context_integration import stage_context_batch
from preprocessing.historical_sst_period import build_period_preview, period_batches
from preprocessing.sst_context_review import (
    ContextQualityProposal,
    _bounds,
    build_context_diagnostics,
)


def prepare_period(
    plan,
    report,
    archive_uri,
    output_root,
    *,
    area_id,
    first_year,
    last_year,
    bounds,
    quality,
    store_factory=ArtifactStore,
    notify=None,
):
    integration, batches, gaps = period_batches(plan, report, first_year, last_year)
    rectangle = _bounds(bounds, integration["context_footprint"])
    proposal = ContextQualityProposal.model_validate(quality).model_dump(mode="json")
    if not isinstance(area_id, str) or not area_id or len(area_id) > 128:
        raise ValueError("An explicit region label is required")
    output_root = Path(output_root)
    if not output_root.is_absolute() or any(
        p.is_symlink() for p in (output_root, *output_root.parents)
    ):
        raise ValueError("A separate absolute non-symlink output directory is required")
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".worker.lock"
    if lock_path.is_symlink():
        raise ValueError("Worker lock symlinks are forbidden")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        settings = {
            "source_plan_sha256": plan["plan_sha256"],
            "source_report_id": report["report_id"],
            "archive_uri": archive_uri,
            "area_id": area_id,
            "first_year": first_year,
            "last_year": last_year,
            "bounds": rectangle,
            "quality": proposal,
        }
        run = output_root / digest(settings)
        if run.is_symlink():
            raise ValueError("Run directory symlinks are forbidden")
        run.mkdir(exist_ok=True)
        atomic_json(run / "settings.json", settings)
        diagnostics = []
        for n, batch in enumerate(batches, 1):
            receipt_path = run / (batch["batch_id"] + ".staging.json")
            if receipt_path.exists():
                staging = _read_json(receipt_path, 64 * 1024)
                if Path(staging["package_path"]).parent != output_root / "packages":
                    raise ValueError(
                        "Cached staging receipt escaped the designated package root"
                    )
            else:
                staging = stage_context_batch(
                    plan,
                    report,
                    integration,
                    archive_uri,
                    batch["batch_id"],
                    output_root / "packages",
                    store_factory=store_factory,
                )
                atomic_json(receipt_path, staging)
            # Reverify retained raw/source bindings even when local staging is reused.
            diagnostic = build_context_diagnostics(
                plan, report, staging, bounds=rectangle, proposed_quality=proposal
            )
            atomic_json(run / (batch["batch_id"] + ".diagnostics.json"), diagnostic)
            diagnostics.append(diagnostic)
            progress = {
                "status": "processing_retained_context",
                "month": batch["month"],
                "completed_batches": n,
                "total_batches": len(batches),
                "processed_final_days": sum(len(d["daily"]) for d in diagnostics),
                "final_series_gaps": len(gaps),
                "provider_downloads": False,
                "scientific_publication": False,
                "run_path": str(run),
            }
            atomic_json(run / "progress.json", progress)
            if notify:
                notify(progress)
        result = build_period_preview(
            plan, report, diagnostics, area_id, first_year, last_year
        )
        atomic_json(run / "period-preview.json", result)
        return {
            "status": result["status"],
            "period_preview_id": result["period_preview_id"],
            "output": str(run / "period-preview.json"),
            "final_days": len(result["observations"]),
            "final_series_gaps": len(gaps),
            "scientific_publication": False,
            "provider_downloads": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--first-year", type=int, required=True)
    parser.add_argument("--last-year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--archive-uri")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--area-id")
    parser.add_argument("--bounds", type=Path)
    parser.add_argument("--quality", type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)) or any(
        p and output.resolve() == p.resolve()
        for p in (args.context_plan, args.reconciliation, args.bounds, args.quality)
    ):
        parser.error("output must be a separate non-symlink path")
    if args.output_root and output.resolve().is_relative_to(args.output_root.resolve()):
        parser.error("summary output must be outside the worker directory")
    plan = _read_json(args.context_plan, MAX_PLAN_BYTES)
    report = _read_json(args.reconciliation, 4 * 1024**2)
    report = report.get("result", report)
    integration, batches, gaps = period_batches(
        plan, report, args.first_year, args.last_year
    )
    if args.execute:
        if not all(
            (
                args.archive_uri,
                args.output_root,
                args.area_id,
                args.bounds,
                args.quality,
            )
        ):
            parser.error(
                "execution requires archive, output root, region label, bounds and quality"
            )
        result = prepare_period(
            plan,
            report,
            args.archive_uri,
            args.output_root,
            area_id=args.area_id,
            first_year=args.first_year,
            last_year=args.last_year,
            bounds=_read_json(args.bounds, 4096),
            quality=_read_json(args.quality, 4096),
            notify=lambda p: print(json.dumps(p), flush=True),
        )
    else:
        result = {
            "status": "retained_context_processing_preflight",
            "integration_plan_id": integration["integration_plan_id"],
            "batches": len(batches),
            "final_days": sum(len(b["days"]) for b in batches),
            "final_series_gaps": gaps,
            "raw_bytes": sum(b["raw_bytes"] for b in batches),
            "scientific_publication": False,
            "provider_downloads": False,
        }
    atomic_json(output, result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
