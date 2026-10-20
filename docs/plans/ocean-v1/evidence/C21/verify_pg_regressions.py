"""Run unchanged C20/C17 disposable-cluster driver against the C21 migration head.

The historical driver remains immutable. Its C20/C17 database identity guards,
owned-cluster lifecycle, tests, and cleanup checks are reused verbatim; this wrapper
redirects new regression receipts to C21 and additionally pins the C21 sources.
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
historical = HERE.parent / 'C20' / 'verify_postgres.py'
spec = importlib.util.spec_from_file_location('c21_historical_pg_regression_driver', historical)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
driver.EVIDENCE = HERE
driver.SOURCE_FILES = (*driver.SOURCE_FILES,
    'migrations/versions/20261019_0019_research_evidence.py',
    'orchestration/research_answers.py', 'orchestration/research_evidence.py',
    'orchestration/research_evidence_projection.py', 'orchestration/research_synthesis.py',
    'orchestration/frozen_documentary.py', 'schema/research_evidence.py',
    'docs/plans/ocean-v1/evidence/C21/verify_pg_regressions.py')

if __name__ == '__main__':
    raise SystemExit(driver.main())
