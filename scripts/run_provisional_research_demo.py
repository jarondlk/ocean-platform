"""Manually preflight/publish an explicitly user-approved provisional demo.

Reads sealed retained inputs only. Publication requires a current read-only DB
source check, never modifies scientific classifications or review registries,
and registers under provisional-demos so older app releases remain unaffected.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.edna_analysis_bundle import publish_analysis
from ingestion.immutable_bundle import atomic_json, digest
from ingestion.provisional_research_bundle import (
    ProvisionalRecipe,
    build_demo,
    demo_status,
)


def run(recipe, inputs, *, execute=False):
    result = build_demo(ProvisionalRecipe.model_validate(recipe), inputs)
    if execute:
        status = demo_status({"inputs": inputs})
        if status != "current":
            raise ValueError(
                "Provisional publication requires current source verification: "
                + status
            )
        manifest = publish_analysis(result)
        manifest_sha256 = digest(manifest)
    else:
        manifest_sha256 = None
    return {
        "analysis_id": result["analysis_id"],
        "manifest_sha256": manifest_sha256,
        "published": execute,
        "namespace": "provisional-demos",
        "user_approved_provisional": True,
        "independent_researcher_approval": False,
        "provider_endorsement": False,
        "canonical_classification_changes": False,
        "provider_downloads": False,
        "table_counts": {k: len(v) for k, v in result["tables"].items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    for path, maximum in ((args.recipe, 16384), (args.inputs, 128 * 1024**2)):
        if (
            any(p.is_symlink() for p in (path, *path.parents))
            or path.stat().st_size > maximum
        ):
            raise ValueError("Invalid bounded input path")
    if any(
        p.is_symlink() for p in (args.output, *args.output.parents)
    ) or args.output.resolve() in {args.recipe.resolve(), args.inputs.resolve()}:
        raise ValueError("Output must be a separate non-symlink path")
    report = run(
        json.loads(args.recipe.read_bytes()),
        json.loads(args.inputs.read_bytes()),
        execute=args.execute,
    )
    atomic_json(args.output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
