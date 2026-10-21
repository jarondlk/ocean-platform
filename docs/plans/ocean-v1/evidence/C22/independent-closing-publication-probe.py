"""Actual synthetic C22 final-callback ordering probe; no code execution/server."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, event, func, select  # noqa: E402
from db.app_models import AppBase, ResearchExperimentApproval  # noqa: E402
from orchestration.frozen_experiment_export import PinnedSourcePublicationPolicy  # noqa: E402
from orchestration.research_experiments import ResearchExperimentError  # noqa: E402
from tests.research_experiment_support import make_experiment_fixture  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = ROOT / args.output
    if output.exists():
        raise FileExistsError(output)
    sources = ['orchestration/research_experiments.py', 'orchestration/frozen_experiment_export.py',
        'schema/research_experiments.py', 'tests/research_experiment_support.py']
    before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    old = {key: os.environ.get(key) for key in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS')}
    os.environ.update(ENABLE_V1_CATALOGUE='true', ENABLE_V1_INVESTIGATIONS='true')
    try:
        with tempfile.TemporaryDirectory(prefix='c22-closing-publication-') as directory:
            root = Path(directory)
            engine = create_engine('sqlite+pysqlite:///' + str(root / 'private-v1.sqlite'))

            @event.listens_for(engine, 'connect')
            def foreign_keys(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')

            try:
                AppBase.metadata.create_all(engine)
                fixture = make_experiment_fixture(engine, root)
                saved = fixture.create()
                calls = []

                def enabled():
                    # This host callback intentionally changes the independent
                    # publication authority after _public's prior verification.
                    # All scientific bytes and C14 membership stay unchanged.
                    if any(frame.function == '_public' for frame in inspect.stack()):
                        fixture.exporter.publication_policy = PinnedSourcePublicationPolicy(
                            policy_id='c22:synthetic:publication', revision='withdrawn-in-final-flag', decisions=[])
                        calls.append('publication withdrawn inside _public enabled callback')
                    return True

                fixture.service.enabled = enabled
                try:
                    response = fixture.service.invoke('approve', fixture.decision(saved), fixture.user)
                except ResearchExperimentError as exc:
                    outcome = {'observed': 'refused', 'code': exc.code, 'status_code': exc.status_code}
                else:
                    outcome = {'observed': 'accepted', 'approval_status': response['experiment']['approval']['status']}
                with fixture.factory() as session:
                    approvals = session.scalar(select(func.count()).select_from(ResearchExperimentApproval))
                result = {'version': 'c22-closing-publication-probe-v1', 'synthetic_only': True,
                    'qualification': 'Actual private service/exporter with sealed synthetic sources and separate temporary SQLite. Deliberately adversarial host flag callback; no Python/executor/server/provider/real data/cloud.',
                    'callback_calls': calls, 'expected': 'refused with no approval commit after publication withdrawal',
                    'outcome': outcome, 'persisted_approvals': approvals,
                    'passed': bool(calls) and outcome['observed'] == 'refused' and approvals == 0}
            finally:
                engine.dispose()
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    result.update(source_before_sha256=before, source_after_sha256=after, source_unchanged=before == after)
    with output.open('x') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'output': str(output.relative_to(ROOT)), 'passed': result['passed'], 'outcome': outcome, 'persisted_approvals': approvals, 'source_unchanged': before == after}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
