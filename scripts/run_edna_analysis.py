#!/usr/bin/env python3
"""Manually generate a bounded, reproducible eDNA analysis; dry-run by default."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingestion.edna_analysis_bundle import run_analysis
from preprocessing.edna_recipe import AnalysisRecipe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', type=Path, required=True)
    parser.add_argument('--environment', type=Path, help='Reviewed environmental observation JSON array; no automatic matching defaults')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.recipe.stat().st_size > 1024 * 1024 or (args.environment and args.environment.stat().st_size > 16 * 1024 * 1024):
        parser.error('Recipe/environment file exceeds the input size limit (1 MiB / 16 MiB)')
    recipe = AnalysisRecipe.model_validate_json(args.recipe.read_text())
    environment = json.loads(args.environment.read_text()) if args.environment else []
    if not isinstance(environment, list):
        parser.error('Environmental observations must be a JSON array')
    print(json.dumps(run_analysis(recipe, execute=args.execute, environment=environment), indent=2))


if __name__ == '__main__':
    main()
