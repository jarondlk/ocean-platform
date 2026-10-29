"""C26 readiness only: reconcile retained prerequisites/current software evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[6]
BASE = ROOT / 'docs/plans/ocean-v1'
OUT = Path(__file__).resolve().parent
SOFTWARE = 'd8825322dd700247313d4a926e365430d8aea8e1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


class GitBytes:
    def __init__(self):
        self.process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.cache = {}

    def sha(self, commit, name):
        key = (commit, name)
        if key not in self.cache:
            self.process.stdin.write((commit + ':' + name + '\n').encode())
            self.process.stdin.flush()
            header = self.process.stdout.readline().decode().strip().split()
            assert header and header[-1] != 'missing', key
            raw = self.process.stdout.read(int(header[-1]))
            assert self.process.stdout.read(1) == b'\n'
            self.cache[key] = hashlib.sha256(raw).hexdigest()
        return self.cache[key]

    def close(self):
        self.process.stdin.close()
        self.process.wait()


def references(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            yield value['path'], value['sha256']
        for item in value.values():
            yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


def verify():
    baseline = read(OUT / 'baseline.json')
    assert git('branch', '--show-current') == 'overhaul'
    assert baseline['accepted_software_source'] == SOFTWARE
    remote = read(OUT / 'remote-verification.json')
    assert remote['branch'] == 'overhaul' and remote['commit'] == baseline['base_commit']
    assert remote['checked_run']['id'] == 40799302862 and remote['checked_run']['head_sha'] == SOFTWARE
    assert remote['checked_run']['status'] == 'completed' and remote['checked_run']['conclusion'] == 'success'
    required_jobs = [j for j in remote['jobs'] if j['name'] != 'Dependency review']
    assert len(required_jobs) == 4 and all(j['conclusion'] == 'success' for j in required_jobs)
    for name, expected in baseline['protected_sha256'].items():
        assert sha(ROOT / name) == expected, name
    # Original evidence remains immutable; this audit adds only its own C26 records.
    for line in git('diff', '--name-status', baseline['base_commit'], '--', 'docs/plans/ocean-v1/evidence').splitlines():
        assert line.startswith('A\tdocs/plans/ocean-v1/evidence/C26/'), line
    prepared = read(BASE / 'evidence/C25/c26-preparation-20261029.json')
    assert len(prepared['predecessors']) == 25
    objects = GitBytes()
    entries, current, changes, receipts = {}, {}, {}, {}
    checked_references = {}
    try:
        for component, record in prepared['predecessors'].items():
            for name, expected in references(record):
                assert sha(ROOT / name) == expected == objects.sha(baseline['base_commit'], name), name
                checked_references[name] = expected
            path = ROOT / record['accepted_receipt']['path']
            delivery = read(path)
            commit = record['accepted_source_commit']
            subprocess.run(['git', 'merge-base', '--is-ancestor', commit, SOFTWARE], cwd=ROOT, check=True)
            local = read(ROOT / record['local_or_supporting_receipt']['path'])
            files = dict(local.get('tested_transitive_source_files', {}))
            for key in ['C05_source_files', 'tested_transitive_source_files', 'files', 'source_files']:
                if isinstance(delivery.get(key), dict):
                    files.update(delivery[key])
            supplemental = None
            if component in ['C16', 'C17']:
                supplemental = BASE / f'evidence/{component}/accepted-source.json'
            elif component == 'C19':
                supplemental = BASE / 'evidence/C19/ci-budget-amendment/accepted-source.json'
            elif component == 'C23':
                supplemental = BASE / 'evidence/C23/operator-hosted-f6f823b/receipt.json'
            if supplemental:
                retained = read(supplemental)
                files.update(retained.get('source_files', retained.get('files', {})))
                checked_references[str(supplemental.relative_to(ROOT))] = sha(supplemental)
                assert sha(supplemental) == objects.sha(baseline['base_commit'], str(supplemental.relative_to(ROOT)))
            superseded = {}
            for name, original in files.items():
                assert isinstance(original, str) and re.fullmatch('[a-f0-9]{64}', original)
                assert objects.sha(commit, name) == original, (component, name)
                actual = sha(ROOT / name)
                assert actual == objects.sha(SOFTWARE, name), ('unaccepted current software', component, name)
                current[name] = actual
                if actual != original:
                    superseded[name] = {'original_sha256': original, 'current_accepted_sha256': actual}
                    changes.setdefault(name, []).append(component)
            entries[component] = len(files)
            receipts[component] = {'state': 'Complete within documented boundary',
                'accepted_source': commit, 'receipt': record['accepted_receipt'],
                'handoff': record['handoff'], 'source_entries': len(files),
                'source_supersessions': superseded, 'qualifications': record.get('qualifications', [])}
            if component == 'P00':
                for name, expected in delivery['screenshots'].items():
                    assert sha(BASE / 'mockups/p00' / name) == expected
        c25_path = BASE / 'evidence/C25/delivery.json'
        c25 = read(c25_path)
        assert c25['state'].startswith('Complete') and c25['source_commit'] == SOFTWARE
        assert all(value == 'success' for value in c25['required_job_results'].values())
        for name, expected in c25['source_files'].items():
            assert sha(ROOT / name) == expected == objects.sha(SOFTWARE, name), name
            current[name] = expected
        entries['C25'] = len(c25['source_files'])
        receipts['C25'] = {'state': c25['state'], 'accepted_source': SOFTWARE,
            'receipt': {'path': str(c25_path.relative_to(ROOT)), 'sha256': sha(c25_path)},
            'handoff': {'path': 'docs/plans/ocean-v1/handoffs/C25.md', 'sha256': sha(BASE / 'handoffs/C25.md')},
            'source_entries': entries['C25'], 'source_supersessions': {},
            'qualifications': c25['qualifications']}
        assert sha(c25_path) == objects.sha(baseline['base_commit'], str(c25_path.relative_to(ROOT)))
        assert sha(BASE / 'handoffs/C25.md') == objects.sha(baseline['base_commit'], 'docs/plans/ocean-v1/handoffs/C25.md')
    finally:
        objects.close()
    last_changes = {name: {'components_superseded': components,
        'last_accepted_change': git('log', '-1', '--format=%H %s', SOFTWARE, '--', name),
        'qualification': 'Intentional later overhaul source; current bytes equal accepted C25 software. Original receipts remain immutable.'}
        for name, components in changes.items()}
    acceptance_map = (BASE / 'ACCEPTANCE_MAP.md').read_text()
    requirements = sorted({int(n) for n in re.findall(r'\|\s*R(\d+)\s*\|', acceptance_map)})
    assert requirements == list(range(1, 34))
    gates = sorted(set(re.findall(r'G[0-9](?=\s*[—-])', acceptance_map)))
    assert gates == [f'G{n}' for n in range(10)]
    c24 = read(BASE / 'evidence/C24/delivery.json')
    assert len(c24['live_gates']) == 11 and c24['provider_schema_validated'] is False
    assert c25['production_execution_enabled'] is False and c25['beta_deployed'] is False
    probe = read(OUT / 'source-probe.json')
    assert probe['current_files'] == current and not probe['bad_original_pins']
    return {'version': 'c26-readiness-v1', 'date': baseline['date'],
        'base_commit': baseline['base_commit'], 'accepted_software_source': SOFTWARE,
        'verdict': 'Ready to begin local deterministic C26 acceptance preparation',
        'C26_implementation': 'Not started; current request is readiness only',
        'live_acceptance': 'Not ready; external integration, target and real-world validation gates remain',
        'required_prerequisites': len(receipts), 'receipt_source_entries': sum(entries.values()),
        'unique_current_source_paths': len(current), 'intentional_superseded_paths': len(changes),
        'source_files': dict(sorted(current.items())), 'prerequisites': receipts,
        'supersession_ownership': last_changes, 'verified_prior_receipt_references': checked_references,
        'protected_unrelated_paths': len(baseline['protected_sha256']),
        'original_evidence_immutable': True, 'hosted_ci': remote['checked_run'],
        'reused_hosted_statistics': c25['hosted_statistics'], 'new_application_tests_run': False,
        'C26_requirements_to_map': requirements, 'C26_gates_to_assess': gates,
        'C24_live_gates_still_not_run': c24['live_gates'],
        'physical_runtime_qualification': 'C23 physical evidence remains bound to its original tested source/host. Later serving/C22 supersessions are software-verified, not fresh physical containment acceptance.',
        'next_action': 'On C26 implementation selection, build R01–R33/G0–G9 requirement-to-fixture/owner/status matrix, then integrated deterministic and adversarial checks and a separate live-evaluation protocol. Route predecessor defects to their owners.',
        'boundary': 'No C26 application implementation, cloud/provider/model/data operation, deployment, legacy change or scheduler resume.',
        'evidence_files': {p.name: sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'verification.json'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    value = verify()
    target = OUT / 'verification.json'
    if args.verify_only:
        saved = read(target)
        for field in ['source_files', 'prerequisites', 'supersession_ownership', 'verified_prior_receipt_references']:
            assert saved[field] == value[field], field
        for name, expected in saved['evidence_files'].items():
            assert sha(OUT / name) == expected, name
    else:
        with target.open('x') as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
    print(f'C26 ready for local preparation: {value["required_prerequisites"]} prerequisites; {value["receipt_source_entries"]} entries/{value["unique_current_source_paths"]} source paths; live gates unrun')


if __name__ == '__main__':
    main()
