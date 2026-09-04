#!/usr/bin/env python3
"""Explicit bounded ANEMONE batch stages; offline plan unless --execute."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import canonical_bytes, validate_id, digest
from ingestion.artifact_store import BoundedLocalStore

STAGES = (
    "inventory",
    "acquire",
    "normalize",
    "classification-review",
    "import",
    "materialize",
    "recipe",
    "analyze",
    "provenance",
)


def import_normalized(normalization_id, *, execute):
    """Only eDNA tables; dry-run executes the exact merge then rolls it back."""
    from db.connection import get_engine
    from scripts.load_db import _load_anemone_bundle_frames, _upsert_anemone_bundle

    loaded = _load_anemone_bundle_frames(normalization_id, allow_noncurrent=False)
    if loaded is None:
        raise ValueError("Explicit normalized bundle required")
    frames, manifest = loaded
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(
                "SELECT pg_advisory_xact_lock(hashtext('ocean_platform_corpus_upsert'))"
            )
            if execute and config.EDNA_ARTIFACT_URI:
                from retrieval.edna_publication import set_pending

                set_pending()
            tables, inactive = _upsert_anemone_bundle(
                connection, frames=frames, manifest=manifest
            )
            if execute:
                transaction.commit()
            else:
                transaction.rollback()
        except BaseException:
            transaction.rollback()
            raise
    return {
        "normalization_id": normalization_id,
        "tables": tables,
        "inactivated": inactive,
        "committed": execute,
    }


def restore_normalized(store, artifact_id):
    entry = store.entries("normalized").get(validate_id(artifact_id))
    if entry is None:
        raise ValueError("Unknown normalized artifact")
    # Read receipt before trusting metadata used to select local paths.
    receipt, _ = store.read("normalized", artifact_id)
    identity = validate_id(receipt["metadata"]["normalization_id"])
    store.restore(
        "normalized",
        artifact_id,
        config.ANEMONE_NORMALIZED_DIR / "snapshots" / identity,
    )
    return identity, receipt["metadata"]


def execute_stage(args):
    store = ArtifactStore(config.EDNA_ARTIFACT_URI)
    if args.stage == "classification-review":
        from preprocessing.anemone_classification import read_review

        review = read_review(args.classification_review)
        identity = digest(review)
        store.publish(
            "classification-reviews", identity,
            {"review.json": canonical_bytes(review)},
            metadata={"source_snapshot_id": review["source_snapshot_id"]},
        )
        return {"artifact_id": identity, "source_snapshot_id": review["source_snapshot_id"]}
    if args.stage in {"inventory", "acquire"}:
        from ingestion.anemone import resolve_credentials, sync_anemone

        credentials = resolve_credentials()
        result = sync_anemone(
            args.scope_url,
            credentials=credentials,
            execute=args.stage == "acquire",
            output_root=config.RAW_ANEMONE_DIR,
            max_files=args.max_files,
            max_bytes=args.max_bytes,
        )
        if args.stage == "inventory":
            return result
        receipt = store.publish_tree(
            "raw",
            config.RAW_ANEMONE_DIR / "snapshots" / result["snapshot_id"],
            metadata={"snapshot_id": result["snapshot_id"]},
        )
        return {
            "snapshot_id": result["snapshot_id"],
            "artifact_id": receipt["id"],
            "files": len(receipt["files"]),
            "bytes": sum(f["size"] for f in receipt["files"].values()),
        }
    if args.stage == "normalize":
        from preprocessing.anemone import normalize_anemone_snapshot
        from preprocessing.anemone_classification import parse_review, read_review, MAX_REVIEW_BYTES

        review = None
        review_artifact_id = getattr(args, "classification_review_artifact_id", None)
        review_path = getattr(args, "classification_review", None)
        if review_artifact_id:
            _, files = store.read("classification-reviews", review_artifact_id, max_bytes=MAX_REVIEW_BYTES)
            if set(files) != {"review.json"}:
                raise ValueError("Invalid classification review artifact contract")
            review = parse_review(files["review.json"])
            if digest(review) != review_artifact_id:
                raise ValueError("Classification review artifact identity mismatch")
        elif review_path:
            review = read_review(review_path)
        receipt, _ = store.read("raw", args.artifact_id)
        snapshot_id = validate_id(receipt["metadata"]["snapshot_id"])
        store.restore(
            "raw", args.artifact_id, config.RAW_ANEMONE_DIR / "snapshots" / snapshot_id
        )
        result = normalize_anemone_snapshot(
            snapshot_id,
            execute=True,
            activate=False,
            raw_root=config.RAW_ANEMONE_DIR,
            normalized_root=config.ANEMONE_NORMALIZED_DIR,
            classification_review=review,
        )
        normalized = store.publish_tree(
            "normalized",
            Path(result["bundle_path"]),
            metadata={
                "normalization_id": result["normalization_id"],
                "snapshot_id": snapshot_id,
                "raw_artifact_id": args.artifact_id,
                **({"classification_review_sha256": digest(review)} if review else {}),
            },
        )
        return {
            "normalization_id": result["normalization_id"],
            "artifact_id": normalized["id"],
        }
    if args.stage == "import":
        identity, _ = restore_normalized(store, args.artifact_id)
        return import_normalized(identity, execute=not args.validate_only)
    if args.stage == "materialize":
        from retrieval.edna_materializer import materialize_edna_retrieval

        return materialize_edna_retrieval(execute=not args.validate_only)
    if args.stage in {"recipe", "analyze"}:
        from ingestion.edna_analysis_bundle import run_analysis
        from preprocessing.edna_recipe import AnalysisRecipe

        if args.stage == "analyze" and args.artifact_id:
            _, files = store.read(
                "recipes", args.artifact_id, max_bytes=17 * 1024 * 1024
            )
            if set(files) != {"recipe.json", "environment.json"}:
                raise ValueError("Invalid recipe artifact contract")
            recipe_data, environment_data = (
                files["recipe.json"],
                files["environment.json"],
            )
        else:
            if args.recipe.stat().st_size > 1024 * 1024 or (
                args.environment and args.environment.stat().st_size > 16 * 1024 * 1024
            ):
                raise ValueError("Recipe/environment byte limit exceeded")
            recipe_data = args.recipe.read_bytes()
            environment_data = (
                args.environment.read_bytes() if args.environment else b"[]"
            )
        if len(recipe_data) > 1024 * 1024 or len(environment_data) > 16 * 1024 * 1024:
            raise ValueError("Recipe/environment byte limit exceeded")
        recipe = AnalysisRecipe.model_validate_json(recipe_data)
        environment = json.loads(environment_data)
        if not isinstance(environment, list):
            raise ValueError("Environmental observations must be an array")
        if args.stage == "recipe":
            files = {
                "recipe.json": canonical_bytes(recipe.model_dump()),
                "environment.json": canonical_bytes(environment),
            }
            identity = digest(
                {"recipe": recipe.model_dump(), "environment": environment}
            )
            store.publish(
                "recipes",
                identity,
                files,
                metadata={"recipe_sha256": digest(recipe.model_dump())},
            )
            return {
                "artifact_id": identity,
                "recipe_sha256": digest(recipe.model_dump()),
            }
        return run_analysis(
            recipe, execute=not args.validate_only, environment=environment
        )
    if args.stage == "provenance":
        from ingestion.lineage import build_provenance_manifest
        from ingestion.provenance_snapshot import prepare_snapshot, publish_snapshot

        # All retained pilot normalizations are required by historical source
        # traces; fail on budget overflow instead of emitting partial provenance.
        entries = store.entries("normalized")
        if len(entries) > 20:
            raise ValueError("Pilot provenance limit exceeded (20 normalized bundles)")
        total = 0
        for artifact_id in entries:
            receipt, _ = store.read("normalized", artifact_id)
            total += sum(f["size"] for f in receipt["files"].values())
            if total > 512 * 1024 * 1024:
                raise ValueError("Pilot provenance staging limit exceeded")
            restore_normalized(store, artifact_id)
        manifest = build_provenance_manifest(
            limit_documents=None, include_embeddings=True
        )
        snapshot = prepare_snapshot(
            manifest,
            manifest_id=args.operation_id,
            pipeline_run_id=args.operation_id,
            require_embedding_capture=True,
        )
        if not args.validate_only:
            published = publish_snapshot(snapshot)
            return {
                "manifest_id": snapshot.manifest_id,
                "pointer_generation": published.pointer_generation,
            }
        return {"manifest_id": snapshot.manifest_id, "validated": True}
    raise ValueError("Unknown stage")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, default="inventory")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize this stage; otherwise print offline plan",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Import rollback or materialize/analysis/provenance validation",
    )
    parser.add_argument("--scope-url")
    parser.add_argument("--artifact-id")
    parser.add_argument("--recipe", type=Path)
    parser.add_argument("--environment", type=Path)
    review_options = parser.add_mutually_exclusive_group()
    review_options.add_argument("--classification-review", type=Path)
    review_options.add_argument("--classification-review-artifact-id")
    parser.add_argument("--max-files", type=int, default=20)
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--operation-id", default="anemone-" + uuid.uuid4().hex)
    args = parser.parse_args()
    if args.classification_review and args.stage not in {"normalize", "classification-review"}:
        parser.error("--classification-review requires normalize or classification-review stage")
    if args.classification_review_artifact_id and args.stage != "normalize":
        parser.error("--classification-review-artifact-id requires normalize stage")
    if args.classification_review_artifact_id:
        validate_id(args.classification_review_artifact_id)
    if not 0 < args.max_files <= 2000 or not 0 < args.max_bytes <= 512 * 1024 * 1024:
        parser.error("Pilot limits: 1–2000 files, 1–536870912 bytes")
    if args.validate_only and args.stage not in {
        "import",
        "materialize",
        "analyze",
        "provenance",
    }:
        parser.error("--validate-only is not supported for this stage")
    if not args.operation_id.replace("-", "").isalnum() or len(args.operation_id) > 100:
        parser.error("Invalid operation ID")
    if not args.execute:
        print(
            json.dumps(
                {
                    "stage": args.stage,
                    "execute": False,
                    "max_files": args.max_files,
                    "max_bytes": args.max_bytes,
                    "requires_approved_pilot": True,
                }
            )
        )
        return 0
    if not config.EDNA_ARTIFACT_URI:
        parser.error(
            "EDNA_ARTIFACT_URI is required; local staging must not be a bucket mount"
        )
    if args.stage in {"inventory", "acquire"} and not args.scope_url:
        parser.error("An approved --scope-url is required")
    if args.stage == "classification-review" and not args.classification_review:
        parser.error("--classification-review is required")
    if args.stage in {"normalize", "import"}:
        if not args.artifact_id:
            parser.error("--artifact-id is required")
        validate_id(args.artifact_id)
    if args.stage == "recipe" and not args.recipe:
        parser.error("--recipe is required")
    if args.stage == "analyze":
        if bool(args.recipe) == bool(args.artifact_id) or (
            args.artifact_id and args.environment
        ):
            parser.error(
                "Provide either --recipe [--environment] or --artifact-id, not both"
            )
        if args.artifact_id:
            validate_id(args.artifact_id)
    report = {
        "schema_version": 1,
        "operation_id": args.operation_id,
        "stage": args.stage,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "execute": True,
        "validate_only": args.validate_only,
    }
    report["execution"] = {
        key: os.environ.get(key)
        for key in (
            "CLOUD_RUN_EXECUTION",
            "CLOUD_RUN_TASK_INDEX",
            "K_REVISION",
            "SOURCE_COMMIT",
        )
    }
    try:
        report["result"] = execute_stage(args)
        report["status"] = "complete"
    except Exception as exc:
        # No arbitrary exception/HTTP body/credential paths in structured logs.
        report.update(status="failed", error_type=type(exc).__name__)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    config.EDNA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(report)
    BoundedLocalStore(config.EDNA_CACHE_DIR / "operations").create(
        args.operation_id + ".json", data
    )
    try:
        ArtifactStore(config.EDNA_ARTIFACT_URI).publish(
            "operations",
            digest(report),
            {"report.json": data},
            metadata={"operation_id": args.operation_id, "stage": args.stage},
        )
    except Exception as exc:
        report["report_publication_error"] = type(exc).__name__
    print(json.dumps(report, sort_keys=True, default=str))
    return (
        0
        if report["status"] == "complete" and "report_publication_error" not in report
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
