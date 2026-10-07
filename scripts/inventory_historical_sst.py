"""Inventory all ANEMONE locations/years from verified metadata; no data writes."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json
from ingestion.research_readiness import read_candidate_metadata
from ingestion.sst_inventory import build_inventory, read_production_census


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--candidate-root", type=Path)
    source.add_argument("--production-read-only", action="store_true")
    parser.add_argument("--halo-degrees", type=float, default=0.02)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.production_read_only:
        from db.connection import get_engine

        samples, provenance = read_production_census(get_engine())
    else:
        source, provenance = read_candidate_metadata(args.candidate_root)
        samples = source["edna_sample"]
        provenance = {"basis": "verified_retained_candidate", **provenance}
    inventory = build_inventory(samples, provenance, halo_degrees=args.halo_degrees)
    atomic_json(args.output, inventory)
    print(
        f"Inventory {inventory['inventory_id']}: {inventory['counts']}; years {inventory['sampling_years']}"
    )


if __name__ == "__main__":
    main()
