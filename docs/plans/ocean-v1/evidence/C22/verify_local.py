"""Source-pinned C22 local gates; outputs are exclusive and prior receipts immutable."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PREFIXES = ('api', 'db', 'schema', 'orchestration', 'ingestion', 'preprocessing',
            'retrieval', 'evaluation', 'scripts', 'tests', 'migrations', 'frontend-v1', 'frontend',
            'config.py', 'model_runtime.py', '.github/workflows/tests.yml', 'requirements')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_pins():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--',
                                     *PREFIXES], cwd=ROOT).decode().split('\0')
    return {name: sha(ROOT / name) for name in sorted(set(names)) if name and (ROOT / name).is_file()}


def save(directory, name, value):
    with (directory / name).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def preservation():
    start = json.loads((HERE / 'start-snapshot.json').read_text())
    groups = {**start['preservation'], 'prior_evidence_files': start['prior_evidence_files']}
    changed = {kind: [name for name, digest in paths.items()
                      if not (ROOT / name).is_file() or sha(ROOT / name) != digest]
               for kind, paths in groups.items()}
    assert not any(changed.values()), changed
    return {'counts': {kind: len(paths) for kind, paths in groups.items()}, 'changed': changed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=('focused', 'static', 'backend', 'frontend'), required=True)
    parser.add_argument('--output-subdir', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.output_subdir):
        parser.error('Expected one new lowercase output directory')
    output = HERE / args.output_subdir
    output.mkdir(exist_ok=False)
    before = source_pins()
    protected = preservation()
    save(output, 'source-before.json', before)
    environment = dict(os.environ, AUTH_MODE='disabled', DEPLOYMENT_ENV='test', ENABLE_MOCK_LOGIN='false',
        PERSIST_LOCAL_CHAT='false', ENABLE_V1_SHELL='false', ENABLE_V1_CATALOGUE='false',
        ENABLE_V1_CATALOGUE_BROWSER='false', ENABLE_V1_INVESTIGATIONS='false', ENABLE_V1_RESEARCH_CONTROLLER='false',
        ENABLE_V1_RESEARCH_RUNS='false', ENABLE_V1_RESEARCH_DISPATCH='false', ENABLE_V1_EVIDENCE='false',
        ENABLE_V1_SYNTHESIS='false', ENABLE_V1_EXPERIMENTS='false', ENABLE_V1_EXPERIMENT_DISPATCH='false', RUN_POSTGRES_INTEGRATION='0',
        DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/ocean_c22_unused',
        MODEL_PROVIDER='ollama', OLLAMA_BASE_URL='http://127.0.0.1:1')
    commands = []
    if args.group == 'backend':
        commands = [('backend', [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=short',
                     *[f'--cov={name}' for name in ('api', 'config', 'db', 'preprocessing', 'ingestion',
                                                   'orchestration', 'schema', 'evaluation')],
                     '--cov-report=term-missing', '--cov-fail-under=70'], ROOT, 3600)]
    elif args.group == 'focused':
        commands = [('focused', [sys.executable, '-m', 'pytest', 'tests/test_research_experiment_contracts.py',
            'tests/test_research_experiment_security.py', 'tests/test_research_experiment_api.py',
            'tests/test_frozen_experiment_export.py', 'tests/test_research_experiments.py',
            'tests/test_research_analysis_bundle.py', 'tests/test_research_registry.py', 'tests/test_auth.py',
            'tests/test_bootstrap_database.py', '-q', '--tb=short'], ROOT, 600)]
    elif args.group == 'static':
        commands = [('ruff', [sys.executable, '-m', 'ruff', 'check', 'api', 'config.py', 'db', 'evaluation',
            'ingestion', 'orchestration', 'preprocessing', 'retrieval', 'schema', 'scripts', 'tests',
            'migrations/versions/20261020_0020_research_experiments.py'], ROOT, 120)]
        commands.extend((path.stem, [sys.executable, str(path.relative_to(ROOT)), '--check'], ROOT, 120)
                        for path in sorted((ROOT / 'scripts').glob('export_*.py')))
        commands.append(('evidence-contract', [sys.executable, 'docs/plans/ocean-v1/evidence/C21/frontend-export-contract.py',
                                               '--check'], ROOT, 120))
    else:
        node_bin = Path('/Users/jaronchai/.nvm/versions/node/v22.14.0/bin')
        assert (node_bin / 'npm').is_file()
        environment['PATH'] = str(node_bin) + os.pathsep + environment.get('PATH', '')
        commands = [(name, ['npm', *command], ROOT / 'frontend-v1', 600) for name, command in (
            ('test', ['test']), ('typecheck', ['run', 'typecheck']), ('build', ['run', 'build']),
            ('audit', ['audit', '--omit=dev', '--audit-level=moderate', '--json']))]
    results = []
    for name, command, cwd, timeout in commands:
        started = time.monotonic()
        print('Starting ' + name, flush=True)
        with (output / (name + '.txt')).open('x') as log:
            result = subprocess.run(command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        row = {'name': name, 'command': command, 'cwd': str(cwd.relative_to(ROOT)),
               'exit_code': result.returncode, 'seconds': round(time.monotonic() - started, 2),
               'log': name + '.txt', 'log_sha256': sha(output / (name + '.txt'))}
        results.append(row)
        print(json.dumps(row), flush=True)
        if result.returncode:
            break
    after = source_pins()
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    save(output, 'source-after.json', after)
    receipt = {'component': 'C22', 'group': args.group, 'created_at': datetime.now(timezone.utc).isoformat(),
               'commands': results, 'source_changed_during_run': changed, 'preservation': preservation(),
               'protected_before': protected, 'success': not changed and len(results) == len(commands)
                    and all(row['exit_code'] == 0 for row in results)}
    save(output, 'result.json', receipt)
    print(json.dumps({'success': receipt['success'], 'changed': changed}), flush=True)
    return 0 if receipt['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
