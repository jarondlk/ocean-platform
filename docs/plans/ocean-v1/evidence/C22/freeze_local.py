"""Create one C22 local receipt after validating explicit final source and gates.

This helper runs no checks, services, migrations or Git mutations. It only reads
already completed evidence and Git objects. Outputs are create-only. Example:

  python .../freeze_local.py --source-commit <final-sha> \
    --source-map .../accepted-source.json --backend-result .../result.json \
    --backend-passed <count> --backend-skipped <count> \
    [--amendment-map .../selection.json --baseline-source-commit <base-sha> \
     --backend-qualification .../cancellation-amendment/verification.json]

An optional amendment map must contain the full final_source_files map, the
baseline_source_sha256 aggregate, complete intentional_source_supersessions
relative to start-snapshot.json, and evidence_files. Only explicitly declared
test-only changes beyond the original map are accepted. A passed broad run may
be qualified for that sole test-source drift using a source-steady actual
three-case cancellation receipt; failed broad cases cannot be waived here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SHA = re.compile(r'^[a-f0-9]{64}$')
PROTECTED_COUNTS = {'unrelated_files': 30, 'scientific_artifacts': 7,
                    'serving_files': 2, 'legacy_frontend_files': 106}
REPLAY_PATHS = {'orchestration/research_experiments.py', 'tests/test_research_experiments.py'}
CANCELLATION_TEST = 'tests/test_catalogue_browser_api.py'
CANCELLATION_NODE = CANCELLATION_TEST + '::test_policy_and_complete_response_stay_in_worker_with_cancellation_cleanup'
COVERAGE_PACKAGES = ('api', 'config', 'db', 'preprocessing', 'ingestion', 'orchestration', 'schema', 'evaluation')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


class GateError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def path(value):
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else ROOT / candidate
    candidate = candidate.resolve()
    require(candidate.is_relative_to(ROOT), 'Evidence/source path must remain inside this repository')
    return candidate


def relative(value):
    return str(path(value).relative_to(ROOT))


def load(value):
    result = json.loads(path(value).read_text())
    require(isinstance(result, dict), f'Expected an object: {value}')
    return result


def digest(value):
    return hashlib.sha256(path(value).read_bytes()).hexdigest()


def source_map(value):
    require(isinstance(value, dict) and value, 'A nonempty source/hash map is required')
    require(all(isinstance(name, str) and not Path(name).is_absolute() and relative(name) == name
                and isinstance(checksum, str) and SHA.fullmatch(checksum)
                for name, checksum in value.items()), 'Invalid source/hash entry')
    return dict(value)


def aggregate(files):
    return hashlib.sha256(''.join(f'{name}:{checksum}\n' for name, checksum in sorted(files.items())).encode()).hexdigest()


def verify(files, *, allowed=None):
    files = source_map(files)
    allowed = allowed or {}
    changed = {}
    for name, expected in files.items():
        actual = digest(name)
        if actual != expected and allowed.get(name) != (expected, actual):
            changed[name] = {'expected': expected, 'actual': actual}
    require(not changed, f'Unqualified changed/missing files: {changed}')


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT).decode().strip()


def commit(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-fA-F0-9]{7,40}', value), 'Explicit source commit required')
    return git('rev-parse', '--verify', value + '^{commit}')


def committed(files, revision):
    for name, expected in source_map(files).items():
        raw = subprocess.check_output(['git', 'show', revision + ':' + name], cwd=ROOT)
        require(hashlib.sha256(raw).hexdigest() == expected, f'Commit/source mismatch: {name}')


def ancestry(older, newer):
    require(subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer], cwd=ROOT,
                           capture_output=True, check=False).returncode == 0, 'Source commit is not an ancestor')


def source_context(source_commit, source_map_path, amendment_map=None, baseline_source_commit=None):
    selected = load(source_map_path)
    require(selected.get('component') == 'C22', 'Source map must identify C22')
    base = source_map(selected['files'])
    require(len(base) == 24 and selected.get('source_sha256') == aggregate(base), 'Original C22 map must retain its exact24 paths')
    final, supersessions, amended, amendment = base, selected['intentional_source_supersessions'], {}, None
    final_commit = commit(source_commit)
    if amendment_map:
        require(baseline_source_commit is not None, 'An amendment requires the explicit original source commit')
        baseline_commit = commit(baseline_source_commit)
        committed(base, baseline_commit)
        ancestry(baseline_commit, final_commit)
        amendment = load(amendment_map)
        require(amendment.get('baseline_source_sha256') == aggregate(base), 'Amendment baseline map mismatch')
        require(commit(amendment['baseline_source_commit']) == baseline_commit, 'Amendment baseline commit mismatch')
        final = source_map(amendment['final_source_files'])
        require(amendment.get('source_sha256') == aggregate(final), 'Final amendment source aggregate mismatch')
        require(base.keys() <= final.keys(), 'Amendment may not drop original accepted source paths')
        supersessions = amendment['intentional_source_supersessions']
        delta = {name for name in final if final[name] != base.get(name)}
        require(delta == {CANCELLATION_TEST}, 'Only the explicit approved C16 test amendment is supported')
        for name in delta:
            old = hashlib.sha256(subprocess.check_output(['git', 'show', baseline_commit + ':' + name], cwd=ROOT)).hexdigest()
            declared = supersessions.get(name)
            require(declared == {'prior': old, 'current': final[name]}, 'Amendment test hashes are not explicitly declared')
            amended[name] = (old, final[name])
        verify(amendment['evidence_files'])
        if amendment.get('source_commit'):
            require(commit(amendment['source_commit']) == final_commit, 'Amendment commit differs from final CLI source')
    elif baseline_source_commit:
        raise GateError('A baseline source commit without an amendment is ambiguous')
    verify(final)
    committed(final, final_commit)
    require(git('branch', '--show-current') == 'overhaul', 'C22 acceptance must remain on overhaul')
    ancestry(final_commit, 'HEAD')
    return {'source_commit': final_commit, 'files': final, 'source_sha256': aggregate(final),
            'base_files': base, 'supersessions': supersessions, 'amended': amended,
            'source_map_path': relative(source_map_path),
            'amendment_map_path': relative(amendment_map) if amendment_map else None,
            'baseline_source_commit': commit(baseline_source_commit) if baseline_source_commit else None}


def preservation(context):
    start = load(HERE / 'start-snapshot.json')
    require(len(start['prior_evidence_files']) == 1204, 'The1204 historical receipts must remain in scope')
    require({key: len(files) for key, files in start['preservation'].items()} == PROTECTED_COUNTS,
            'Protected-file groups differ from the accepted start snapshot')
    verify(start['prior_evidence_files'])
    for files in start['preservation'].values():
        verify(files)
    changed = {name: {'prior': old, 'current': digest(name)} for name, old in start['prior_source_files'].items()
               if digest(name) != old}
    require(changed == context['supersessions'], 'Prior-source changes do not equal the complete declared supersessions')
    require(all(context['files'].get(name) == item['current'] for name, item in changed.items()),
            'A supersession is outside the final committed source map')
    return start, changed


def pytest_counts(text):
    rows = [line for line in ANSI.sub('', text).splitlines() if re.search(r'\b\d+ passed\b', line)]
    require(rows, 'No completed pytest summary is present')
    result = {kind: int(count) for count, kind in re.findall(r'(\d+) (passed|failed|skipped|errors|error)', rows[-1])}
    if 'error' in result:
        result['errors'] = result.pop('error')
    return result, rows[-1]


def coverage(text):
    matches = re.findall(r'\bTOTAL\s+[^\n]*?([0-9]+(?:\.[0-9]+)?)%\s*$', ANSI.sub('', text), re.M)
    require(matches and float(matches[-1]) >= 70, 'Repository-wide coverage must be at least70%')
    return float(matches[-1])


def command_logs(report, directory):
    require(isinstance(report.get('commands'), list) and report['commands'], 'Completed commands are required')
    for item in report['commands']:
        log = path(directory) / item['log']
        require(log.is_relative_to(path(directory)) and digest(log) == item['log_sha256'], 'Command log hash mismatch')
    return report['commands']


def audit_backend(context, result_path, expected_passed, expected_skipped, qualification_path=None):
    report = load(result_path)
    require(report.get('component') == 'C22' and report.get('group') == 'backend', 'Expected the actual C22 broad backend recorder')
    directory = path(result_path).parent
    commands = command_logs(report, directory)
    require(len(commands) == 1 and commands[0]['exit_code'] == 0, 'Broad backend must complete with no failed cases')
    arguments = commands[0]['command']
    require('pytest' in arguments and 'tests/' in arguments and '--cov-fail-under=70' in arguments,
            'Expected the complete backend suite with the70% gate')
    require(all('--cov=' + package in arguments for package in COVERAGE_PACKAGES), 'Broad coverage package set changed')
    text = (directory / commands[0]['log']).read_text()
    counts, summary = pytest_counts(text)
    require(counts == {'passed': expected_passed, 'skipped': expected_skipped}, 'Broad backend counts differ from the explicit accepted totals')
    percent = coverage(text)
    before, after = load(directory / 'source-before.json'), load(directory / 'source-after.json')
    actual_drift = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    require(actual_drift == report['source_changed_during_run'], 'Backend source-drift record is inconsistent')
    require(all(not group for group in report['preservation']['changed'].values()), 'Backend preservation failed')
    verify(after, allowed=context['amended'])
    qualification = None
    needs_qualification = bool(actual_drift or any(digest(name) != value for name, value in after.items()))
    if needs_qualification:
        require(qualification_path is not None and context['amended'], 'Backend source drift needs explicit test-only qualification')
        require(set(actual_drift) <= context['amended'].keys(), 'Backend changed application or unapproved test source')
        for name, (old, new) in context['amended'].items():
            require(before.get(name) == old and after.get(name) in {old, new}, 'Broad baseline does not bind the original approved test')
        qualification = load(qualification_path)
        require(qualification.get('version') == 'c22-cancellation-test-only-amendment-v1', 'Unknown test-only qualification contract')
        require(qualification.get('source_unchanged_during_verification') is True
                and qualification['source_before_sha256'] == qualification['source_after_sha256'], 'Targeted amendment source drifted')
        verify(qualification['source_after_sha256'])
        verify(qualification['reviewed_source_sha256'])
        verify(qualification['preserved_evidence_sha256'])
        require(qualification['test_counts'].get('passed') == 3 and qualification['test_counts'].get('failed') == 0,
                'All three real cancellation parameter cases must pass')
        checks = qualification['checks']
        require(checks and all(value is True for value in checks.values()), 'Test-only amendment checks are incomplete')
        tested = False
        for item in qualification['commands']:
            require(item['exit_code'] == 0 and digest(item['log']) == item['log_sha256'], 'Targeted amendment command/log failed')
            args = shlex.split(item['command']) if isinstance(item['command'], str) else item['command']
            if CANCELLATION_NODE in args:
                tested = True
                require(all('--cov=' + package in args for package in COVERAGE_PACKAGES), 'Targeted native case lost application coverage')
                targeted, _ = pytest_counts(path(item['log']).read_text())
                require(targeted == {'passed': 3}, 'Targeted cancellation test log is not a three-pass result')
        require(tested, 'The actual native cancellation pytest node was not exercised')
        require(qualification['source_after_sha256'][CANCELLATION_TEST] == context['files'][CANCELLATION_TEST],
                'Targeted test differs from final accepted source')
    else:
        require(report.get('success') is True and not actual_drift, 'Broad backend is not successful')
    for name, expected in context['files'].items():
        require(after.get(name) == expected or name in context['amended'], 'Final accepted file was not in the broad source map')
    return {'passed': expected_passed, 'skipped': expected_skipped, 'failed': 0, 'errors': 0,
            'coverage_percent': percent, 'summary': summary,
            'receipt': relative(result_path), 'receipt_sha256': digest(result_path),
            'qualification': relative(qualification_path) if qualification_path else None,
            'qualification_sha256': digest(qualification_path) if qualification_path else None}, after


def audit_static(context):
    report_path = HERE / 'static-acceptance-01/result.json'
    report = load(report_path)
    require(report.get('success') is True and report['source_changed_during_run'] == [], 'Original static checks failed')
    commands = command_logs(report, report_path.parent)
    require(len(commands) == 11 and all(item['exit_code'] == 0 for item in commands), 'Ruff plus all ten generated checks are required')
    require(sum('--check' in item['command'] for item in commands) == 10, 'Generated contract checks changed')
    label = load(HERE / 'static-harness-qualification.json')
    require(label['component'] == 'C22' and report['component'] == 'C21'
            and label['original_receipt_sha256'] == digest(report_path)
            and label['original_success'] is True and label['source_changed_during_run'] == [],
            'Copied helper label qualification is not bound to the preserved static receipt')
    later = load(HERE / 'static-later-source-qualification.json')
    require(set(later['changes']) == REPLAY_PATHS, 'Static replay qualification scope changed')
    allowed = {name: (item['tested'], item['current']) for name, item in later['changes'].items()}
    require(all(context['files'][name] == values[1] for name, values in allowed.items()), 'Static replay qualification differs from final source')
    allowed.update(context['amended'])
    verify(load(report_path.parent / 'source-after.json'), allowed=allowed)
    require('All checks passed' in (HERE / 'replay-final-ruff.txt').read_text(), 'Final affected Ruff result is missing')
    return {'commands': 11, 'generated_checks': 10, 'original_label': 'C21', 'qualified_component': 'C22',
            'receipt': relative(report_path), 'receipt_sha256': digest(report_path),
            'label_qualification': relative(HERE / 'static-harness-qualification.json'),
            'source_qualification': relative(HERE / 'static-later-source-qualification.json')}


def audit_native(context):
    store = load(HERE / 'store-verification.json')
    verify(store['owned_source_sha256'])
    verify({relative(HERE / name): value for name, value in store['evidence_sha256'].items()})
    require(set(store['postgres']['intentional_postrun_supersession']) == REPLAY_PATHS, 'C22 native supersession scope changed')
    native_paths = ((HERE / 'store-pg-final-01/postgres-result.json', 21),
                    (HERE / 'pg-c17-c20-regressions-01/postgres-result.json', 104),
                    (HERE / 'pg-c21-regressions-01/postgres-result.json', 23))
    rows = []
    for result_path, expected in native_paths:
        report = load(result_path)
        require(report['driver_exit_code'] == report['test_exit_code'] == 0
                and report['server_stopped'] is True and report['test_schemas_remaining'] == 0
                and report['existing_database_urls_used'] is False
                and report['source_changed_during_run'] == []
                and report['source_before_sha256'] == report['source_after_sha256'], 'Actual PostgreSQL acceptance/cleanup failed')
        require(report['test_counts'] == {'passed': expected}, 'Actual native case count changed')
        log_counts, _ = pytest_counts((result_path.parent / 'postgres-tests.txt').read_text())
        require(log_counts == {'passed': expected}, 'Native log and recorder counts disagree')
        verify({relative(result_path.parent / name): value for name, value in report['evidence_sha256'].items()})
        allowed = {}
        if expected == 21:
            actual = {name for name, old in report['source_after_sha256'].items() if digest(name) != old}
            require(actual == REPLAY_PATHS, 'Unexpected C22 native source supersession')
            allowed = {name: (report['source_after_sha256'][name], context['files'][name]) for name in actual}
        verify(report['source_after_sha256'], allowed={**allowed, **context['amended']})
        rows.append({'path': relative(result_path), 'sha256': digest(result_path), 'passed': expected,
                     'qualified_source_changes': sorted(allowed)})
    regression = load(HERE / 'native-regression-verification.json')
    require(regression['total_regressions'] == 127 and regression['C22_scoped_native'] == 21
            and regression['all_owned_clusters_stopped'] is True and regression['test_schemas_remaining'] == 0,
            'Native148 reconciliation is incomplete')
    for item in regression['records']:
        require(digest(item['path']) == item['sha256'], 'Native regression receipt changed')
    return {'total': 148, 'records': rows, 'qualification': store['postgres']['qualification']}


def audit_reviews_and_export():
    rows = []
    for name in ('independent-contract-api-review.json', 'independent-export-review.json'):
        report = load(HERE / name)
        require(report.get('remaining_findings') == [], 'Independent review retains a blocker')
        verify(report['reviewed_source_sha256'])
        verify(report['evidence_sha256'])
        rows.append({'path': relative(HERE / name), 'sha256': digest(HERE / name)})
    export = load(HERE / 'export-verification.json')
    verify(export['files'])
    require(export['focused_verification']['exit_code'] == 0
            and export['focused_verification']['source_unchanged'] is True and export['lint']['exit_code'] == 0,
            'Frozen exporter verification failed')
    for key in ('focused_verification', 'lint'):
        item = export[key]
        require(digest(item['log']) == item['log_sha256'], 'Frozen exporter log changed')
    require(pytest_counts(path(export['focused_verification']['log']).read_text())[0] == {'passed': 30}, 'All30 exporter cases must pass')
    wire = load(HERE / 'http-wire-current-source-verification.json')
    require(wire['exit_code'] == 0 and wire['changed'] == [] and wire['source_before_sha256'] == wire['source_after_sha256'],
            'Actual all-nine HTTP wire verification failed')
    verify(wire['source_after_sha256'])
    require(digest(HERE / 'root-http-current-source-wire.txt') == wire['log_sha256']
            and digest(HERE / 'http-wire-current-source.json') == wire['capture_sha256'], 'HTTP wire log/capture changed')
    return rows


def audit_frontend_reuse():
    receipt_path = HERE.parent / 'C21/frontend-full-verification.json'
    receipt = load(receipt_path)
    require(receipt['test_counts']['pass'] == 930 and receipt['test_counts']['fail'] == 0
            and receipt['test_counts']['cancelled'] == 0 and receipt['production_dependency_vulnerabilities']['total'] == 0,
            'C21 frontend reuse requires930 successful tests and zero production vulnerabilities')
    require(receipt['frontend_source_unchanged'] is True and receipt['legacy_source_unchanged'] is True
            and receipt['dependencies_and_lockfiles_unchanged'] is True and receipt['before'] == receipt['after'],
            'Frontend/dependency reuse source proof is incomplete')
    for files in receipt['after'].values():
        verify(files)
    verify(receipt['reviewed_source_sha256'])
    verify(receipt['supporting_receipts'])
    require({item['name'] for item in receipt['commands']} == {'test', 'typecheck', 'build', 'audit'}
            and all(item['exit_code'] == 0 and digest(item['log']) == item['log_sha256'] for item in receipt['commands']),
            'Reused frontend type/build/audit gates are incomplete')
    delivered = load(HERE.parent / 'C21/delivery.json')
    hosted = load(delivered['hosted_receipt']['path'])
    require(digest(delivered['hosted_receipt']['path']) == delivered['hosted_receipt']['sha256']
            and hosted['run']['status'] == 'completed' and hosted['run']['conclusion'] == 'success'
            and hosted['checks']['frontend_v1_passed'] == 930 and hosted['checks']['frontend_legacy_passed'] == 132
            and hosted['checks']['frontend_typechecks_builds_audits'] == 'passed', 'Previous delivered frontend acceptance is unverified')
    for item in hosted['logs'].values():
        require(digest(item['path']) == item['sha256'], 'Prior delivered hosted log changed')
    return {'path': relative(receipt_path), 'sha256': digest(receipt_path), 'v1_passed': 930,
            'legacy_passed': 132, 'source_and_dependencies_unchanged': True,
            'qualification': 'C22 changes no frontend source; complete C21 source/dependency hashes and delivery are revalidated. Final C22 hosted frontend gates remain mandatory.'}


def save_new(output, value):
    output = path(output)
    require(output.is_relative_to(HERE) and not output.exists(), 'Only a new C22 evidence output may be created')
    with output.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--source-map', required=True)
    parser.add_argument('--amendment-map')
    parser.add_argument('--baseline-source-commit')
    parser.add_argument('--backend-result', required=True)
    parser.add_argument('--backend-passed', type=int, required=True)
    parser.add_argument('--backend-skipped', type=int, required=True)
    parser.add_argument('--backend-qualification')
    parser.add_argument('--output', default=str(HERE / 'verification.json'))
    args = parser.parse_args()
    require(not path(args.output).exists(), 'Existing local receipts are immutable')
    require(args.backend_passed > 0 and args.backend_skipped >= 0, 'Explicit final backend totals are required')
    context = source_context(args.source_commit, args.source_map, args.amendment_map, args.baseline_source_commit)
    start, supersessions = preservation(context)
    backend, tested = audit_backend(context, args.backend_result, args.backend_passed, args.backend_skipped, args.backend_qualification)
    static, native = audit_static(context), audit_native(context)
    reviews, frontend = audit_reviews_and_export(), audit_frontend_reuse()
    evidence = {relative(item): digest(item) for item in sorted(HERE.rglob('*'))
                if item.is_file() and '__pycache__' not in item.parts and item.resolve() != path(args.output)}
    verify(evidence)
    tested = {name: context['files'].get(name, expected) for name, expected in tested.items()
              if name not in start['preservation']['unrelated_files']}
    verify(tested)
    record = {'component': 'C22', 'created_at': datetime.now(timezone.utc).isoformat(),
        'state': 'Local gates reconciled; final exact-source hosted CI and delivery checkpoint are required',
        'source_commit': context['source_commit'], 'files': context['files'], 'source_sha256': context['source_sha256'],
        'intentional_source_supersessions': supersessions, 'tested_transitive_source_files': tested,
        'preserved_prior_evidence_count': 1204, 'protected_counts': PROTECTED_COUNTS, 'evidence_files': evidence,
        'checks': {'backend': backend, 'actual_postgres': native, 'static': static, 'frontend_reuse': frontend,
                   'independent_reviews': reviews},
        'inputs': {'source_map': context['source_map_path'], 'amendment_map': context['amendment_map_path'],
                   'baseline_source_commit': context['baseline_source_commit'], 'backend_result': relative(args.backend_result),
                   'backend_qualification': relative(args.backend_qualification) if args.backend_qualification else None},
        'external_gates': ['C22 fake acceptance executes no Python and confers no scientific approval',
                           'C23 real Linux/gVisor containment and C24 target/configuration/live gates remain separate',
                           'No cloud provisioning/deployment or real-data/provider acquisition/transfer acceptance',
                           'C25 experiment UI and C26 assembled browser/system acceptance remain']}
    save_new(args.output, record)
    print(json.dumps({'component': 'C22', 'state': record['state'], 'source_commit': context['source_commit'],
                      'output': relative(args.output), 'sha256': digest(args.output)}))


if __name__ == '__main__':
    try:
        main()
    except (GateError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit('C22 local receipt refused: ' + str(error)) from None
