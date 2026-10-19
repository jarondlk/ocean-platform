"""Freeze C20's final history repair, preserving original tested source and receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
SOURCE = 'fc46da36aa27c203357a1b5874a02378ae089847'


def read(name):
    return json.loads((HERE / name).read_text())


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def verify(files):
    changed = [path for path, digest in files.items() if sha(path) != digest]
    assert not changed, changed


def aggregate(files):
    return hashlib.sha256(''.join(f'{p}:{v}\n' for p, v in sorted(files.items())).encode()).hexdigest()


def save(name, data):
    with (HERE / name).open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


start = read('start-snapshot.json')
assert start['original_source_commit'] == SOURCE
verify(start['prior_evidence_files'])
verify(start['original_local_evidence_files'])
for files in start['preservation'].values():
    verify(files)
if (HERE / 'verification.json').exists():
    accepted = read('verification.json')
    verify(accepted['files'])
    verify(accepted['tested_transitive_source_files'])
    verify(accepted['evidence_files'])
    print(json.dumps({'state': 'read-only amended acceptance revalidation passed', 'source_sha256': accepted['source_sha256']}))
    raise SystemExit(0)

frontend = read('frontend-verification.json')
review = read('independent-review.json')
assert frontend['test_counts']['passed'] >= 781 and frontend['test_counts']['failed'] == frontend['test_counts']['skipped'] == 0
assert frontend['production_dependency_vulnerabilities']['total'] == 0
assert all(frontend[key] for key in ('frontend_source_unchanged', 'legacy_source_unchanged', 'wire_fixture_unchanged', 'dependencies_and_lockfiles_unchanged'))
assert {command['name'] for command in frontend['commands']} >= {'test', 'typecheck', 'build', 'audit'}
for command in frontend['commands']:
    assert command['exit_code'] == 0
    verify({command['log']: command['log_sha256']})
assert frontend['before'] == frontend['after']
verify(frontend['before']['frontend_source_sha256'])
verify(frontend['before']['legacy_source_sha256'])
verify(frontend['reviewed_source_sha256'])
assert not review['remaining_findings']
verify(review['reviewed_source_sha256'])

original = start['original_tested_source_files']
tested = {**original, **frontend['after']['frontend_source_sha256']}
owned = {**start['original_files'], **frontend['reviewed_source_sha256']}
verify(tested)
verify(owned)
supersessions = {path: {'before_sha256': digest, 'after_sha256': tested[path]}
                 for path, digest in original.items() if digest != tested[path]}
assert supersessions, 'The amendment must record the actual repaired source'
assert all(path.startswith('frontend-v1/') for path in supersessions)
assert set(supersessions) <= set(frontend['reviewed_source_sha256'])
assert set(supersessions) <= set(review['reviewed_source_sha256'])
new_paths = sorted(set(tested) - set(original))
assert all(path.startswith('frontend-v1/') for path in new_paths)
assert set(new_paths) <= set(review['reviewed_source_sha256'])
verify({path: digest for path, digest in original.items() if path not in supersessions})
evidence = {str(path.relative_to(ROOT)): sha(path.relative_to(ROOT)) for path in sorted(HERE.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts and path.name not in {'accepted-source.json', 'verification.json'}}
accepted = {'component': 'C20', 'amendment': 'history-pagination', 'files': owned, 'source_sha256': aggregate(owned)}
save('accepted-source.json', accepted)
record = {**accepted, 'created_at': datetime.now(timezone.utc).isoformat(),
          'state': 'Local acceptance passed; final source checkpoint and hosted delivery remain',
          'original_source_commit': SOURCE, 'original_verification_sha256': start['original_verification_sha256'],
          'intentional_source_supersessions': supersessions, 'new_tested_source_paths': new_paths,
          'tested_transitive_source_files': tested, 'evidence_files': evidence,
          'checks': {'frontend': frontend['test_counts'], 'typecheck_build_audit': 'pass', 'independent_review': 'no remaining blockers',
                     'backend_and_postgres': 'Original accepted source unchanged; reuse original acceptance, require new exact-source hosted regression'},
          'preserved_tracked_evidence_count': len(start['prior_evidence_files']),
          'protected_counts': {name: len(files) for name, files in start['preservation'].items()},
          'retained_run_bound': 'At most25 recent explicit acknowledgements per conversation; older entries remain accessible through paginated server history',
          'external_gates': ['No real providers/data/cloud/deployment/scientific approval acceptance', 'C26 assembled browser acceptance remains']}
save('verification.json', record)
print(json.dumps({'state': 'amended local acceptance frozen', 'owned_paths': len(owned), 'tested_paths': len(tested),
                  'supersessions': list(supersessions), 'new_paths': new_paths, 'source_sha256': accepted['source_sha256']}))
