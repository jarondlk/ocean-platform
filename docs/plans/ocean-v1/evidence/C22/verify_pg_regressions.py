"""Revalidate prior native PG gates after C22's additive migration.

Historical drivers and receipts remain immutable. Each invocation still owns,
identifies, cleans and stops its dedicated loopback cluster with original guards.
"""
import argparse
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__, add_help=False)
parser.add_argument('--suite', choices=('c17-c20', 'c21'), required=True)
args, remaining = parser.parse_known_args()
sys.argv = [sys.argv[0], *remaining]
historical = HERE.parent / ('C20/verify_postgres.py' if args.suite == 'c17-c20' else 'C21/store_verify_postgres.py')
spec = importlib.util.spec_from_file_location('c22_prior_pg_driver', historical)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
driver.EVIDENCE = HERE
driver.SOURCE_FILES = tuple(sorted(set((*driver.SOURCE_FILES,
    'migrations/versions/20261019_0019_research_evidence.py',
    'migrations/versions/20261020_0020_research_experiments.py',
    'orchestration/research_answers.py', 'orchestration/research_evidence.py',
    'orchestration/research_evidence_projection.py', 'orchestration/research_synthesis.py',
    'orchestration/research_experiments.py', 'orchestration/frozen_experiment_export.py',
    'schema/research_experiments.py', 'tests/integration/test_research_evidence_postgres.py',
    'docs/plans/ocean-v1/evidence/C22/verify_pg_regressions.py'))))

if __name__ == '__main__':
    raise SystemExit(driver.main())
