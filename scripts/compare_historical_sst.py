"""Prepare representative product probes; optionally download bounded MUR cases."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json, download_batch
from ingestion.sst_comparison import build_comparison_packet, inspect_mur_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute-mur-probes", action="store_true")
    args = parser.parse_args()
    packet = build_comparison_packet(_read_json(args.inventory, MAX_PLAN_BYTES))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    diagnostics, failures = [], []

    def write_receipt():
        atomic_json(
            args.output_dir / "comparison.json",
            {
                "plan": packet,
                "mur_diagnostics": diagnostics,
                "mur_failures": failures,
                "comparison_complete": False,
            },
        )

    write_receipt()
    if args.execute_mur_probes:
        for case in packet["cases"]:
            directory = args.output_dir / case["case_id"]
            manifest = download_batch(case["mur_plan"], directory)
            for entry in manifest["files"]:
                try:
                    diagnostics.append(
                        {
                            "case_id": case["case_id"],
                            **inspect_mur_file(directory / entry["filename"], entry),
                        }
                    )
                except (ValueError, OSError) as error:
                    failures.append(
                        {
                            "case_id": case["case_id"],
                            "day": entry["day"],
                            "status": "scientific_container_validation_failed",
                            "error_type": type(error).__name__,
                        }
                    )
                write_receipt()
            if not manifest["status"].startswith("complete"):
                failures.append(
                    {"case_id": case["case_id"], "outcomes": manifest["outcomes"]}
                )
            write_receipt()
    write_receipt()
    print(
        f"Comparison {packet['comparison_id']}: {len(packet['cases'])} cases; {len(diagnostics)} MUR files verified; Himawari comparison pending"
    )
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
