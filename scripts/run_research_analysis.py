"""Manually preflight/publish a detection-frequency run from applied DB reviews."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json, validate_id
from ingestion.research_analysis_bundle import run_research_analysis
from preprocessing.research_recipe import DetectionFrequencyRecipe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--sampling-registry-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.recipe.is_symlink() or args.recipe.stat().st_size > 16384:
        raise ValueError("Research recipe file limit exceeded")
    recipe = DetectionFrequencyRecipe.model_validate_json(args.recipe.read_bytes())
    report = run_research_analysis(
        recipe, validate_id(args.sampling_registry_id), execute=args.execute
    )
    atomic_json(args.output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
