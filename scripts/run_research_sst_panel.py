"""Manually preflight/publish SST granules against current applied DB reviews."""

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
from ingestion.research_sst_panel import build_panel, publish_panel
from preprocessing.research_sst import GranuleInput


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-registry-id", required=True)
    parser.add_argument("--sampling-registry-id", required=True)
    parser.add_argument(
        "--granules",
        type=Path,
        required=True,
        help="Completed acquisition manifest with local NetCDF files",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.granules.is_symlink() or args.granules.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("SST inventory file limit exceeded")
    inventory = json.loads(args.granules.read_bytes())
    if not str(inventory.get("status", "")).startswith("complete"):
        raise ValueError("A completed acquisition manifest is required")
    files = inventory["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= 1600:
        raise ValueError("SST inventory granule limit exceeded")
    granules = []
    for entry in files:
        filename = entry["filename"]
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or filename in {".", ".."}
        ):
            raise ValueError("Invalid local SST inventory path")
        granules.append(
            (
                args.granules.parent / filename,
                GranuleInput.model_validate(
                    {
                        k: entry[k]
                        for k in (
                            "granule_id",
                            "raw_sha256",
                            "source_url",
                            "expected_time_utc",
                        )
                    }
                ),
            )
        )
    with get_engine().connect() as connection, connection.begin():
        connection.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        with Session(bind=connection) as session:
            records = []
            for identity in (args.product_registry_id, args.sampling_registry_id):
                payload = read_registry(session, validate_id(identity))
                head = session.get(ResearchRegistryHead, payload["registry_key"])
                if not head or head.registry_id != identity:
                    raise ValueError(
                        "SST preparation requires the current applied reviews"
                    )
                records.append(payload)
    identity, definition, observations, contents = build_panel(*records, granules)
    report = {
        "execute": args.execute,
        "panel_id": identity,
        "granules": len(granules),
        "observations": len(observations),
        "valid_observations": sum(row["status"] == "valid" for row in observations),
        "artifact_bytes": sum(map(len, contents.values())),
        "cloud_publication_requested": args.execute,
    }
    if args.execute:
        if publish_panel(*records, granules) != identity:
            raise ValueError("SST input changed after preflight")
    atomic_json(args.output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
