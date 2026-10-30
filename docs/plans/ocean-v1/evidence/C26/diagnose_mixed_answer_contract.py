"""Explicit actual-service C26 mixed-context response reproduction; no providers.

Emit exact API response text for the real frontend parser, without changing
production contracts or the accepted browser harness. All inputs are synthetic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import uuid

if os.environ.get('DEPLOYMENT_ENV') != 'test' or os.environ.get('AUTH_MODE') != 'disabled':
    raise RuntimeError('Explicit isolated test settings required')
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
# ruff: noqa: E402
from sqlalchemy import create_engine, event
from api.research_evidence_routes import research_evidence_response
from db.app_models import AppBase
from tests.system_acceptance_support import make_system_acceptance_fixture, seed_integrated_browser, source_revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(Path('/private/tmp')) or output.exists():
        parser.error('Choose a new private/tmp synthetic response capture')
    for name in ('CATALOGUE', 'INVESTIGATIONS', 'RESEARCH_CONTROLLER', 'RESEARCH_RUNS',
            'RESEARCH_DISPATCH', 'EVIDENCE', 'SYNTHESIS', 'EXPERIMENTS',
            'EXPERIMENT_DISPATCH', 'EXPERIMENT_WORKSPACE'):
        os.environ['ENABLE_V1_' + name] = 'true'
    with TemporaryDirectory(prefix='ocean-c26-mixed-contract-') as directory:
        engine = create_engine('sqlite+pysqlite:///' + str(Path(directory) / 'owned-app.sqlite'))

        @event.listens_for(engine, 'connect')
        def keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')

        AppBase.metadata.create_all(engine)
        fixture = make_system_acceptance_fixture(engine, Path(directory))
        seed = seed_integrated_browser(fixture)
        revision, files = source_revision()
        cases = []

        def capture(name, run):
            request = {**fixture.runs.address(run), 'cursor': None, 'limit': 25}
            response = research_evidence_response(fixture.user, fixture.evidence, fixture.answers,
                fixture.retained.service, 'answers', 'list', request)
            text = response.body.decode()
            cases.append({'id': name, 'request': request, 'status': response.status_code,
                'response_text': text, 'response_sha256': hashlib.sha256(response.body).hexdigest()})

        capture('initial-context', seed['run'])
        context = seed['context']
        for reference in (seed['receipts'][0]['attachment_reference'],
                seed['execution']['artifacts'][0]['attachment_reference']):
            result = fixture.retained.service.invoke('context/change', {
                'investigation_id': context['investigation']['id'],
                'expected_revision_id': context['context']['id'],
                'idempotency_key': str(uuid.uuid4()),
                'change': {'op': 'attach', 'reference': reference}}, fixture.user)
            context = {**context, **result}
        _, run = fixture.finish_run(context)
        capture('mixed-native-experimental-context', run)
        payload = {'version': 'c26-mixed-answer-contract-diagnostic-v1',
            'classification': 'synthetic-local-actual-services', 'live_calls_performed': False,
            'source_revision': revision, 'source_files': files, 'cases': cases}
        with output.open('x') as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
        engine.dispose()
        print(json.dumps({'cases': [{'id': item['id'], 'status': item['status'],
            'sha256': item['response_sha256']} for item in cases], 'output': str(output)}))


if __name__ == '__main__':
    main()
