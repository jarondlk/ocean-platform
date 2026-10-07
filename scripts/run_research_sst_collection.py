"""Preflight/publish a bounded SST collection against current applied DB reviews."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from api.research_registry_service import read_registry
from db.app_models import ResearchRegistryHead
from db.connection import get_engine
from ingestion.immutable_bundle import atomic_json, digest, validate_id
from ingestion.research_sst_collection import (
    MAX_CHILDREN,
    build_collection,
    publish_collection,
)
from ingestion.research_sst_panel import load_panel
from ingestion.sst_acquisition import _read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection",
        type=Path,
        required=True,
        help='JSON: {"children":[{"panel_id":"…","area_ids":["reviewed-area"]}]}',
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    selected = _read_json(args.selection, 256 * 1024)
    if (
        set(selected) != {"children"}
        or not 1 <= len(selected["children"]) <= MAX_CHILDREN
    ):
        raise ValueError("A bounded explicit child selection is required")
    for child in selected["children"]:
        if set(child) != {"panel_id", "area_ids"}:
            raise ValueError("Invalid child selection contract")
        validate_id(child["panel_id"])

    def children():
        for child in selected["children"]:
            yield load_panel(child["panel_id"]), child["area_ids"]

    identity, definition, observations, files = build_collection(children())
    with get_engine().connect() as connection, connection.begin():
        connection.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        with Session(bind=connection) as session:
            for key in ("product_registry", "sampling_registry"):
                payload = definition[key]
                registry_id = digest(payload)
                current = read_registry(session, registry_id)
                head = session.get(ResearchRegistryHead, payload["registry_key"])
                if current != payload or not head or head.registry_id != registry_id:
                    raise ValueError(
                        "SST collection requires current applied product and area reviews"
                    )
    if args.execute and publish_collection(children()) != identity:
        raise ValueError("SST collection inputs changed after preflight")
    report = {
        "collection_id": identity,
        "recipe_sst_panel_id": identity,
        "children": len(definition["children"]),
        "observations": len(observations),
        "artifact_bytes": sum(map(len, files.values())),
        "published": args.execute,
        "scope": definition["children"],
        "integrity_basis": definition["integrity_basis"],
    }
    atomic_json(args.output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
