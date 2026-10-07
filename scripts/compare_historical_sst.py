"""Prepare representative product probes; optionally download bounded MUR cases."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json, download_batch
from ingestion.sst_comparison import (
    build_comparison_packet,
    inspect_mur_file,
    inspect_himawari_file,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute-mur-probes", action="store_true")
    parser.add_argument(
        "--himawari-probe",
        type=Path,
        help="Completed private probe.json; reads retained raw files only",
    )
    args = parser.parse_args()
    packet = build_comparison_packet(_read_json(args.inventory, MAX_PLAN_BYTES))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    diagnostics, failures, himawari, himawari_failures = [], [], [], []

    def write_receipt():
        atomic_json(
            args.output_dir / "comparison.json",
            {
                "plan": packet,
                "mur_diagnostics": diagnostics,
                "mur_failures": failures,
                "himawari_diagnostics": himawari,
                "himawari_failures": himawari_failures,
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
    if args.himawari_probe:
        probe = _read_json(args.himawari_probe, 64 * 1024)
        entries = probe.get("files", [])
        if (
            probe.get("status") != "access_probe_complete_scientific_comparison_pending"
            or not 1 <= len(entries) <= 4
        ):
            raise ValueError(
                "Himawari comparison requires a completed bounded access probe"
            )
        for case in packet["cases"]:
            footprint = case["mur_plan"]["footprint"]
            days = {entry["day"] for entry in case["mur_plan"]["requests"]}
            for entry in entries:
                if entry["nominal_time_utc"][:10] not in days:
                    continue
                name = entry["local_filename"]
                if Path(name).name != name:
                    raise ValueError("Invalid Himawari comparison local path")
                try:
                    himawari.append(
                        {
                            "case_id": case["case_id"],
                            **inspect_himawari_file(
                                args.himawari_probe.parent / name, entry, footprint
                            ),
                        }
                    )
                except (ValueError, OSError) as error:
                    himawari_failures.append(
                        {
                            "case_id": case["case_id"],
                            "remote_path": entry["remote_path"],
                            "status": "scientific_container_validation_failed",
                            "error_type": type(error).__name__,
                        }
                    )
                write_receipt()
    write_receipt()
    print(
        f"Comparison {packet['comparison_id']}: {len(packet['cases'])} cases; {len(diagnostics)} MUR files and {len(himawari)} Himawari footprints inspected; scientific comparison/selection pending"
    )
    if failures or himawari_failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
