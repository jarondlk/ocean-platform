"""Render and verify a one-execution outbox observer override offline."""

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from deploy.gcp.beta.b4 import outbox_health as health
from scripts import beta_b0_preflight as guard


SOURCES = ('scripts/beta_b1_diagnostic.py', 'deploy/gcp/beta/b4/outbox_health.py')
EXECUTION_PROOF = 'ocean-beta-b4-outbox-execution-plan-v1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def arguments(binding, health):
    # The existing diagnostics image supplies Python, psycopg2 and SQLAlchemy.
    # Embed only these two reviewed sources. The shared binding is an import,
    # so its historical single-question diagnostic never runs.
    payload = json.dumps([binding, health], separators=(',', ':'))
    bootstrap = f'''import hashlib,json,sys,types
if len(sys.argv)!=2 or hashlib.sha256(sys.argv[1].encode()).hexdigest()!={digest(payload.encode())!r}:
    print('{{"state":"outbox_observer_source_rejected"}}');sys.exit(2)
binding,health=json.loads(sys.argv[1]);sys.argv=['outbox_health.py']
package=types.ModuleType('scripts');base=types.ModuleType('scripts.beta_b1_diagnostic')
package.beta_b1_diagnostic=base;sys.modules['scripts']=package;sys.modules[base.__name__]=base
exec(compile(binding,'beta_b1_diagnostic.py','exec'),base.__dict__)
exec(compile(health,'outbox_health.py','exec'),{{'__name__':'__main__'}})
'''
    return [bootstrap, payload]


def committed(revision, path):
    return subprocess.check_output(['git', 'show', f'{revision}:{path}'], cwd=guard.ROOT)


def plan(revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Use a full source revision')
    paths = (*SOURCES, Path(__file__).relative_to(guard.ROOT).as_posix(),
             guard.CONTRACT.relative_to(guard.ROOT).as_posix())
    pins = {path: committed(revision, path) for path in paths}
    if any((guard.ROOT / path).read_bytes() != raw for path, raw in pins.items()):
        raise ValueError('The checkout must match all selected source bytes')
    base = guard.document(pins[paths[-1]])
    args = arguments(*(pins[path].decode('utf-8') for path in SOURCES))
    if len(args[1].encode()) >= 16384:
        raise ValueError('Override source exceeds the observer argument bound')
    override = {'overrides': {'containerOverrides': [{'name': 'diagnostics', 'args': args}]}}
    return {'version': EXECUTION_PROOF, 'source_revision': revision, 'job': base['job_name'],
            'source_sha256': {path: digest(raw) for path, raw in pins.items()}, 'request': override}


def verify_execution(execution, base_contract, request, **kwargs):
    # Change only the accepted diagnostics arguments for the execution.
    # Everything else, including the proxy platform, must still qualify.
    guard.require(set(request) == {'overrides'} and set(request['overrides']) == {'containerOverrides'})
    contract = deepcopy(base_contract)
    override, = request['overrides']['containerOverrides']
    guard.require(set(override) == {'name', 'args'} and override['name'] == 'diagnostics'
                  and len(override['args']) == 2)
    container = contract['execution_spec']['template']['spec']['containers'][0]
    container['args'] = [{'sha256': digest(value.encode()), 'bytes': len(value.encode())}
                         for value in override['args']]
    return guard.verify_execution(execution, contract, **kwargs)


def verify_report(report, proof, *, now):
    expected = {'version', 'project', 'state', 'counts_only', 'counts', 'pending_threshold_seconds',
                'sent_threshold_seconds', 'captured_utc', 'transaction_read_only_verified', 'proxy_shutdown_verified'}
    guard.require(set(report) == expected and report['version'] == health.VERSION
                  and report['project'] == health.observer.PROJECT)
    guard.require(all(report[key] is True for key in ('counts_only', 'transaction_read_only_verified', 'proxy_shutdown_verified'))
                  and report['pending_threshold_seconds'] == health.PENDING_SECONDS
                  and report['sent_threshold_seconds'] == health.SENT_SECONDS)
    counts = report['counts']
    guard.require(type(counts) is dict and set(counts) == set(health.TABLES))
    flagged = False
    for group in counts.values():
        guard.require(type(group) is dict and set(group) == set(health.FIELDS)
                      and all(type(value) is int and 0 <= value < 2**53 for value in group.values()))
        issues = sum(group[key] for key in health.FIELDS[1:])
        guard.require(issues <= group['active'])
        flagged = flagged or issues > 0
    guard.require(report['state'] == ('review_required' if flagged else 'clear'))
    captured = guard.timestamp(report['captured_utc'])
    guard.require(guard.timestamp(proof['start_utc']) <= captured <= guard.timestamp(proof['completion_utc']) <= now
                  and now - captured <= guard.MAX_AGE)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    opts = parser.parse_args()
    if opts.output.resolve().is_relative_to(guard.ROOT):
        parser.error('Write the execution plan to a private directory outside the checkout')
    result = plan(opts.revision)
    os.umask(0o077)
    with opts.output.open('x') as file:
        json.dump(result, file, sort_keys=True, indent=2)
        file.write('\n')
