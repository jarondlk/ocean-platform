"""Targeted create-request regression; synthetic inputs, no cloud or credentials."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent
PACKAGE = ROOT / 'deploy/gcp/beta/setup'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    sys.path.insert(0, str(PACKAGE))
    try:
        current = load('create_request_current', PACKAGE / 'render_jobs.py')
        prior = load('create_request_prior', HERE / 'render_jobs.before.py')
    finally:
        sys.path.pop(0)
    assert current.OPERATOR_REVISION == prior.OPERATOR_REVISION == '8b06a1b993cbca53ded0a9e79e1acb5ba58f3089'
    image = ('asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/'
        'ocean-v1-beta/operator@sha256:' + '0' * 64)
    fixture = {'version': 'beta-private-credentials-execution-v1', 'state': 'credentials_installed',
        'project_id': current.PROJECT, 'project_number': current.NUMBER,
        'instance': current.INSTANCE, 'database': current.DATABASE,
        'secret_versions': {identifier: {'name': 'projects/' + current.NUMBER + '/secrets/'
            + identifier + '/versions/1', 'state': 'ENABLED'} for identifier in current.IDS}}
    original = prior.render(image=image, receipt=fixture)
    actual = current.render(image=image, receipt=fixture)
    expected_names = {'ocean-v1-beta-db-' + stage for stage in ['bootstrap', 'migrate', 'finalize', 'readback']}
    assert set(actual) == set(original) == expected_names
    checks = []
    for name, body in actual.items():
        assert 'name' not in body
        assert original[name]['name'] == ('projects/' + current.PROJECT + '/locations/'
            + current.REGION + '/jobs/' + name)
        expected = {key: value for key, value in original[name].items() if key != 'name'}
        assert body == expected
        task = body['template']['template']
        assert task['containers'][0]['args'][0] == name.removeprefix('ocean-v1-beta-db-')
        assert json.loads(json.dumps(body)) == body
        checks.append({'job_id': name, 'create_body_name_absent': True,
            'all_other_policy_and_stage_fields_unchanged': True})
    with tempfile.TemporaryDirectory(prefix='ocean-beta-create-body-check-') as directory:
        temporary = Path(directory)
        receipt = temporary / 'synthetic-metadata.json'
        receipt.write_text(json.dumps(fixture))
        output = temporary / 'rendered-new'
        child = subprocess.run([sys.executable, str(PACKAGE / 'render_jobs.py'),
            '--operator-image', image, '--credentials-receipt', str(receipt), '--output', str(output)],
            capture_output=True, text=True, timeout=10, check=True)
        summary = json.loads(child.stdout)
        assert summary['state'] == 'rendered_only' and summary['cloud_calls'] is False
        assert {p.name for p in output.iterdir()} == {name + '.json' for name in expected_names}
        for name in expected_names:
            assert json.loads((output / (name + '.json')).read_text()) == actual[name]
    return {'version': 'beta-create-request-regression-v1', 'stage_checks_passed': 4,
        'checks': checks, 'actual_cli_serialization_passed': True,
        'operator_revision_unchanged': current.OPERATOR_REVISION,
        'synthetic_input_qualification': 'Zero image digest and numeric version1 are invented fixture inputs only',
        'cloud_calls': False, 'secret_generation': False, 'provider_revalidation_claimed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run()
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'stage_checks_passed': 4, 'actual_cli_serialization_passed': True,
        'cloud_calls': False, 'secret_generation': False}))
