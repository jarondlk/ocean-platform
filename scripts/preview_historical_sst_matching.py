"""Preview sample-time matching and region/season SST thirds locally."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json, digest
from ingestion.sst_acquisition import _read_json
from preprocessing.historical_sst_matching import (
    preview_context_observations,
    preview_historical_matching,
    preview_relative_temperature_bins,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--members",
        required=True,
        type=Path,
        help="JSON list of explicitly assigned collection members",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--observations",
        type=Path,
        help="JSON list of content-addressed daily SST observations",
    )
    source.add_argument(
        "--context-diagnostics",
        type=Path,
        help="Hash-bound output of the verified context preview, with explicit QC rules",
    )
    parser.add_argument(
        "--preview-area-id",
        help="Diagnostic rectangle label, required with --context-diagnostics",
    )
    parser.add_argument(
        "--panel-id", required=True, help="Pinned source panel identity"
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    inputs = [args.members, args.observations, args.context_diagnostics]
    if any(p.is_symlink() for p in (output, *output.parents)) or any(
        p and output.resolve() == p.resolve() for p in inputs
    ):
        parser.error("output must be a separate non-symlink local path")
    members = _read_json(args.members, 8 * 1024**2)
    context = (
        _read_json(args.context_diagnostics, 4 * 1024**2)
        if args.context_diagnostics
        else None
    )
    observations = (
        preview_context_observations(context, args.preview_area_id)
        if context is not None
        else _read_json(args.observations, 64 * 1024**2)
    )
    if not isinstance(members, list) or not isinstance(observations, list):
        parser.error("members and observations must be JSON lists")
    result = {
        "schema_version": 1,
        "status": "provisional_local_preview",
        "matching": preview_historical_matching(members, observations, args.panel_id),
        "relative_temperature": preview_relative_temperature_bins(observations),
        "source_members_sha256": digest(members),
        "source_observations_sha256": digest(observations),
        "scientific_publication": False,
        "database_access": False,
        "cloud_writes": False,
        "context_diagnostics_used": args.context_diagnostics is not None,
    }
    if context is not None:
        result["source_context_diagnostics_id"] = context["diagnostics_id"]
        result["context_month_gaps"] = context[
            "month_dates_without_final_evidence_in_this_batch"
        ]
        result["archive_unsupported_final_dates"] = context[
            "archive_unsupported_final_dates"
        ]
    result["preview_id"] = digest(result)
    atomic_json(output.resolve(), result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "preview_id": result["preview_id"],
                "coverage": result["matching"]["coverage"],
                "scientific_publication": False,
            }
        )
    )


if __name__ == "__main__":
    main()
