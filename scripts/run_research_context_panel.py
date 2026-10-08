"""Preflight/publish a verified context month using current applied reviews.

Unapproved staging is an input, never an approval. The real registry ledger must
independently contain both applied sampling and regional-context product reviews.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from api.research_registry_service import read_registry
from db.app_models import ResearchRegistryHead
from db.connection import get_engine
from ingestion.immutable_bundle import atomic_json, validate_id
from ingestion.research_sst_panel import applied_definition, build_panel, publish_panel
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json
from preprocessing.research_sst import GranuleInput
from preprocessing.sst_context_review import load_context_review


def context_granules(plan, report, staging, product_registry):
    """Require exact reviewed delivery identity and actual verified final bytes."""
    product = applied_definition(product_registry, "sst_product")
    context = product.regional_context
    if not context or context.source_plan_sha256 != plan["plan_sha256"]:
        raise ValueError(
            "The applied product must review this exact context delivery plan"
        )
    _, _, entries = load_context_review(plan, report, staging)
    root = Path(staging["package_path"])
    return [
        (
            root / entry["filename"],
            GranuleInput.model_validate(
                {
                    key: entry[key]
                    for key in (
                        "granule_id",
                        "raw_sha256",
                        "source_url",
                        "expected_time_utc",
                    )
                }
            ),
        )
        for entry, _, _ in entries
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--staging-receipt", type=Path, required=True)
    parser.add_argument("--product-registry-id", required=True)
    parser.add_argument("--sampling-registry-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    output = args.output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)) or any(
        output.resolve() == p.resolve()
        for p in (args.context_plan, args.reconciliation, args.staging_receipt)
    ):
        parser.error("output must be a separate non-symlink path")
    plan = _read_json(args.context_plan, MAX_PLAN_BYTES)
    report = _read_json(args.reconciliation, 4 * 1024**2)
    report = report.get("result", report)
    staging = _read_json(args.staging_receipt, 64 * 1024)
    package = Path(staging["package_path"])
    if output.resolve() == package or package in output.resolve().parents:
        parser.error("output cannot alter the sealed source package")
    with get_engine().connect() as connection, connection.begin():
        connection.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        with Session(bind=connection) as session:
            records = []
            for identity in (args.product_registry_id, args.sampling_registry_id):
                value = read_registry(session, validate_id(identity))
                head = session.get(ResearchRegistryHead, value["registry_key"])
                if not head or head.registry_id != identity:
                    raise ValueError(
                        "Context publication requires current applied reviews"
                    )
                records.append(value)
    granules = context_granules(plan, report, staging, records[0])
    identity, _, observations, files = build_panel(*records, granules)
    if args.execute and publish_panel(*records, granules) != identity:
        raise ValueError("Context panel inputs changed after preflight")
    result = {
        "panel_id": identity,
        "granules": len(granules),
        "observations": len(observations),
        "valid_observations": sum(r["status"] == "valid" for r in observations),
        "artifact_bytes": sum(map(len, files.values())),
        "published": args.execute,
        "evidence_role": "regional_context",
        "native_sample_area_evidence": False,
        "provider_downloads": False,
    }
    atomic_json(output, result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
