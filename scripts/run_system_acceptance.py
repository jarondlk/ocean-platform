#!/usr/bin/env python3
"""C26 local acceptance runner: actual services, synthetic data, no live providers.

Use a NEW output directory. Receipts are immutable. Live gates are never run or
promoted by this tool. Browser observations must be captured separately through
the development-only loopback harness and carry exact source pins.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.system_acceptance import content_sha256, parse_acceptance_json  # noqa: E402
from evaluation.system_acceptance_isolation import run_isolation_acceptance  # noqa: E402
from evaluation.system_acceptance_matrix import build_matrix  # noqa: E402
from tests.system_acceptance_comparison_support import run_publication_comparison  # noqa: E402

START = ROOT / 'docs/plans/ocean-v1/evidence/C26/implementation-20261029/start.json'
REGRESSIONS = {
    'regression-auth': ('test_auth.py',),
    'regression-retention': ('test_retention.py',),
    'regression-model': ('test_model_runtime.py', 'test_metagenome_document_contract.py', 'test_hybrid_retrieval_contract.py', 'test_generation_contract.py'),
    'regression-csv': ('test_csv_serialization.py',),
    'regression-scope': ('test_chat_source_scope.py', 'test_research_controller_scope.py'),
    'regression-publication': ('test_publication_scope_contract.py',),
    'regression-catalogue': ('test_catalogue_service.py',),
    'regression-frozen': ('test_frozen_catalogue_adapters.py', 'test_frozen_sst_catalogue.py', 'test_frozen_edna_catalogue.py', 'test_frozen_scientific_catalogue.py'),
    'regression-browser': ('test_catalogue_browser.py', 'test_catalogue_browser_api.py'),
    'regression-controller': ('test_research_controller.py', 'test_research_controller_scope.py', 'test_research_controller_contracts.py'),
    'regression-runs': ('test_research_runs.py',),
    'regression-evidence': ('test_research_evidence_store.py', 'test_research_evidence_runtime.py', 'test_research_evidence_api.py', 'test_research_answers.py'),
    'regression-experiments': ('test_research_experiments.py', 'test_experiment_workspace.py', 'test_experimental_artifact_integration.py'),
    'regression-legacy': ('test_research_chat.py', 'test_chat_source_scope.py', 'test_generation_contract.py'),
    'regression-framework': ('test_system_acceptance.py', 'test_system_acceptance_matrix.py', 'test_system_acceptance_integration.py'),
}
EXTRA_TESTS = ('test_system_acceptance.py', 'test_system_acceptance_matrix.py',
    'test_system_acceptance_integration.py')
AUTHORIZED_SUPERSESSIONS = {
    '.github/workflows/tests.yml': 'C26 isolated scale and native retained-artifact CI selection',
    'orchestration/investigations.py': 'User-approved C17 foreign retained-artifact composition and same-session resolution',
    'orchestration/research_evidence.py': 'User-approved C21 foreign retained-artifact durable protection/current authority',
    'orchestration/research_runs.py': 'User-approved C20 same-session artifact context resolution',
    'orchestration/research_answers.py': 'User-approved C21 mixed-artifact workflow repair: bound event pages to their captured high-water cursor',
    'orchestration/research_experiments.py': 'User-approved C22 same-session artifact context resolution',
    'orchestration/experiment_workspace.py': 'User-approved C25 exact artifact resolution without recursive availability lookup',
    'tests/experiment_workspace_support.py': 'Explicit synthetic durable retention-port reference journal',
    'orchestration/catalogue_service.py': 'User-approved C14 memory optimization preserving complete membership/authorization',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def source_manifest():
    start = json.loads(START.read_text())
    paths = set(start['prerequisite_source_files'])
    paths.update(('docs/plans/ocean-v1/ACCEPTANCE_MAP.md',
        'docs/plans/ocean-v1/SITE_SEPARATION.md', 'docs/plans/ocean-v1/C26_LIVE_EVALUATION_PROTOCOL.md'))
    for pattern in ('api/**/*.py', 'orchestration/**/*.py', 'schema/**/*.py', 'db/**/*.py',
            'frontend-v1/src/**/*', 'frontend-v1/app/**/*',
            'evaluation/system_acceptance*.py', 'schema/system_acceptance*.py',
            'orchestration/experiment_artifacts.py', 'orchestration/retained_artifacts.py',
            'tests/*system_acceptance*.py', 'tests/*experimental_artifact*.py',
            'tests/test_catalogue_service_materialization.py',
            'tests/integration/*experimental_artifact*.py',
            'scripts/run_system_acceptance.py',
            'docs/plans/ocean-v1/evidence/C26/serve_acceptance_qa.py',
            'frontend-v1/development/c26/app/**/*', 'frontend-v1/development/c26/next.config.mjs'):
        paths.update(str(path.relative_to(ROOT)) for path in ROOT.glob(pattern) if path.is_file())
    return {path: sha(ROOT / path) for path in sorted(paths)}


def audit_originals():
    start = json.loads(START.read_text())
    mismatched = [path for path, expected in start['protected_sha256'].items()
        if not (ROOT / path).is_file() or sha(ROOT / path) != expected]
    changed = {path: {'original': expected, 'current': sha(ROOT / path),
        'authorization': AUTHORIZED_SUPERSESSIONS.get(path)}
        for path, expected in start['prerequisite_source_files'].items()
        if sha(ROOT / path) != expected}
    unauthorized = [path for path, item in changed.items() if not item['authorization']]
    # Hash every old evidence file at its original Git object, including unmodified
    # ones. New C26 files do not alter the immutable original receipt set.
    tree = subprocess.check_output(['git', 'ls-tree', '-r', '-z', start['prior_evidence_tree']], cwd=ROOT)
    entries = []
    for entry in tree.split(b'\0'):
        if not entry:
            continue
        metadata, raw_path = entry.split(b'\t', 1)
        path = ROOT / 'docs/plans/ocean-v1/evidence' / raw_path.decode()
        entries.append((path, metadata.decode().split()[2]))
    if any('\n' in str(path) for path, _ in entries):
        raise ValueError('Unexpected newline in original receipt path')
    actuals = subprocess.check_output(['git', 'hash-object', '--stdin-paths'],
        input=''.join(str(path) + '\n' for path, _ in entries).encode(), cwd=ROOT).decode().splitlines()
    if len(actuals) != len(entries):
        raise ValueError('Original receipt hash accounting mismatch')
    failures, checked = [], len(entries)
    for (path, expected), actual in zip(entries, actuals):
        if actual != expected:
            failures.append(str(path.relative_to(ROOT)))
    return {'id': 'planning-and-original-receipts',
        'status': 'failed' if mismatched or unauthorized or failures else 'passed',
        'reason': 'Protected files, original receipts or unauthorized source changed' if mismatched or unauthorized or failures else None,
        'expected': {'protected_paths': len(start['protected_sha256']), 'original_evidence_unchanged': True,
            'source_supersessions_explicitly_authorized': True},
        'observed': {'protected_mismatches': mismatched, 'original_evidence_checked': checked,
            'original_evidence_mismatches': failures, 'unauthorized_changes': unauthorized},
        'source_supersessions': changed, 'original_tree': start['prior_evidence_tree']}


def junit_checks(path):
    tree = ET.parse(path)
    cases = list(tree.iter('testcase'))
    if not cases:
        raise ValueError('No actual test cases in JUnit capture')
    output = []
    for identity, names in REGRESSIONS.items():
        selected = [case for case in cases if any(
            Path(name).stem in case.attrib.get('classname', '').split('.') for name in names)]
        observed = {name: sum(Path(name).stem in case.attrib.get('classname', '').split('.') for case in selected) for name in names}
        failures = [case.attrib.get('classname', '') + ':' + case.attrib.get('name', '')
            for case in selected if case.find('failure') is not None or case.find('error') is not None]
        skipped = [case.attrib.get('name', '') for case in selected if case.find('skipped') is not None]
        status = 'failed' if failures else 'not_run' if skipped or not all(observed.values()) else 'passed'
        output.append({'id': identity, 'status': status,
            'reason': None if status == 'passed' else 'Failures, skipped or missing requested regression cases',
            'expected': {'files': list(names), 'all_requested_cases_pass': True},
            'observed': {'cases_by_file': observed, 'failures': failures, 'skipped': skipped},
            'capture_sha256': sha(path)})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser', type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.browser:
        args.browser = args.browser.resolve()
    # Do not discover a production DB or credentials through .env/application main.
    if os.environ.get('DEPLOYMENT_ENV') != 'test' or os.environ.get('AUTH_MODE') != 'disabled':
        parser.error('Explicit DEPLOYMENT_ENV=test AUTH_MODE=disabled required')
    os.environ.update(ENABLE_V1_CATALOGUE='true', ENABLE_V1_INVESTIGATIONS='true', ENABLE_V1_RESEARCH_CONTROLLER='true')
    args.output.mkdir(parents=False, exist_ok=False)
    before = source_manifest()
    revision = 'sha256:' + content_sha256(before)
    write(args.output / 'source-manifest.json', {'source_revision': revision, 'source_files': before})
    checks = {}
    def capture(name, value):
        write(args.output / name, value)
        digest = sha(args.output / name)
        for item in value.get('checks', []):
            if item['id'] in checks:
                raise ValueError('Duplicate acceptance observation')
            checks[item['id']] = {**item, 'sha256': digest, 'source_revision': revision}
    original = audit_originals()
    capture('originals-audit.json', {'checks': [original]})
    integrated = args.output / 'integrated.json'
    paths = sorted({name for names in REGRESSIONS.values() for name in names} | set(EXTRA_TESTS))
    for name in paths:
        if not (ROOT / 'tests' / name).is_file():
            raise ValueError('Missing requested actual regression file: ' + name)
    command = [sys.executable, '-m', 'pytest', *['tests/' + name for name in paths],
        '-q', '--tb=short', '--junitxml=' + str(args.output / 'regressions.xml')]
    # Test cases enable their own explicit services. Do not leak the runner's
    # enabled integration settings into default-disabled/security regressions.
    environment = {key: value for key, value in os.environ.items() if not key.startswith('ENABLE_V1_')}
    environment.update(C26_INTEGRATED_CAPTURE=str(integrated), PYTEST_ADDOPTS='')
    with (args.output / 'regressions.txt').open('x') as stream:
        completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=1800, check=False)
    regression_checks = junit_checks(args.output / 'regressions.xml')
    regression_checks.append({'id': 'regression-command',
        'status': 'passed' if completed.returncode == 0 else 'failed',
        'reason': None if completed.returncode == 0 else 'The actual requested regression process returned nonzero',
        'expected': {'returncode': 0}, 'observed': {'returncode': completed.returncode}})
    capture('regression-checks.json', {'command': command, 'returncode': completed.returncode,
        'checks': regression_checks})
    if integrated.exists():
        value = parse_acceptance_json(integrated.read_bytes())
        # Preserve the original inner source identity; validate its selected pins
        # against the broader frozen runner manifest rather than rewriting it.
        pins = value['fixture']['source_files']
        if not pins:
            raise ValueError('Integrated capture has no selected source pins')
        for path, digest in pins.items():
            if before.get(path) != digest:
                raise ValueError('Integrated capture source mismatch: ' + path)
        for item in value['checks']:
            checks[item['id']] = {**item, 'sha256': sha(integrated), 'source_revision': revision}
    capture('isolation.json', run_isolation_acceptance(args.output / 'isolation-fixture'))
    scale = args.output / 'scale.json'
    scale_environment = {**environment, 'ENABLE_V1_CATALOGUE': 'true', 'ENABLE_V1_RESEARCH_CONTROLLER': 'true'}
    subprocess.run([sys.executable, '-m', 'tests.system_acceptance_scale_support', '--output', str(scale)],
        cwd=ROOT, env=scale_environment, check=True, timeout=240)
    for item in parse_acceptance_json(scale.read_bytes())['checks']:
        checks[item['id']] = {**item, 'sha256': sha(scale), 'source_revision': revision}
    comparison = run_publication_comparison(args.output / 'comparison-fixture', source_revision=revision)
    capture('comparison.json', comparison)
    checks['matched-controller-comparison'] = {'id': 'matched-controller-comparison',
        'status': comparison['comparison']['status'], 'reason': comparison['comparison']['reason'],
        'sha256': sha(args.output / 'comparison.json'), 'source_revision': revision}
    physical_path = ROOT / 'docs/plans/ocean-v1/evidence/C23/completion-20261028.json'
    physical = json.loads(physical_path.read_text())
    checks['original-c23-physical-evidence'] = {'id': 'original-c23-physical-evidence',
        'status': 'passed' if physical['status'] == 'Complete' and original['status'] == 'passed' else 'blocked',
        'reason': None if original['status'] == 'passed' else 'Original physical receipt integrity audit failed',
        'sha256': sha(physical_path), 'source_revision': physical['actual_run_source_commit'],
        'qualification': physical['qualifications']}
    if args.browser:
        browser = parse_acceptance_json(args.browser.read_bytes())
        pins = browser.get('source_files', {})
        if not pins or any(before.get(path) != digest for path, digest in pins.items()):
            raise ValueError('Browser observations require matching exact source pins')
        capture('browser.json', browser)
    if source_manifest() != before:
        raise ValueError('Source changed during acceptance; retain this interrupted capture and use a new output directory')
    report = build_matrix(master_text=(ROOT / 'docs/plans/ocean-v1/ACCEPTANCE_MAP.md').read_text(),
        source_revision=revision, checks=checks, comparisons=[comparison['comparison']])
    write(args.output / 'checks.json', checks)
    write(args.output / 'report.json', report)
    write(args.output / 'run.json', {'version': 'c26-local-acceptance-run-v1', 'source_revision': revision,
        'recorded_at': datetime.now(timezone.utc).isoformat(), 'runtime': platform.platform(),
        'python': sys.version, 'live_calls_performed': False, 'regression_returncode': completed.returncode,
        'preparation_complete': report['acceptance_report']['preparation_complete'],
        'release_accepted': report['acceptance_report']['release_accepted']})
    print(json.dumps({'source_revision': revision,
        'preparation_status': report['acceptance_report']['preparation_status'],
        'release_status': report['acceptance_report']['release_status'], 'output': str(args.output)}))
    return 0 if report['acceptance_report']['preparation_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
