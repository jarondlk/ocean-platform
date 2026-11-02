"""Reconcile this catalogue overlay with immutable accepted software/evidence."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TARGET = 'abcdff79d8695be2e493efa29dc92c454d5b6dfe'


def read(path):
    return json.loads(path.read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify():
    previous = HERE.parent / 'checkpoint-20261102'
    old_overlay = read(previous / 'source-supersession.json')
    release = read(ROOT / 'docs/plans/ocean-v1/evidence/C27/release-manifest.json')
    expected = dict(release['source']['source_files'])
    expected.update({v['path']: v['to_sha256'] for v in old_overlay['supersessions']})
    expected.update(old_overlay['additive_app_sha256'])
    assert len(expected) == 880
    overlay = read(HERE / 'source-supersession.json')
    for name, value in overlay['changes'].items():
        assert expected[name] == value['from_sha256']
        expected[name] = value['to_sha256']
    assert not set(overlay['additions']).intersection(expected)
    expected.update(overlay['additions'])
    data = subprocess.check_output(['git', '--literal-pathspecs', 'archive', TARGET, '--',
        *sorted(expected)], cwd=ROOT)
    observed = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for entry in archive:
            if entry.isfile():
                observed[entry.name] = sha(archive.extractfile(entry).read())
    assert observed == expected, 'Committed candidate has an undeclared source change'
    preservation = read(previous / 'preservation.json')
    for name, digest in preservation['protected_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    pins = preservation['predecessor_sources']
    for item in pins.values():
        assert sha((ROOT / item['path']).read_bytes()) == item['sha256']
    start = read(ROOT / pins['c27_readiness_start']['path'])
    for name, item in start['prior_evidence_files'].items():
        path = ROOT / 'docs/plans/ocean-v1/evidence' / name
        data = os.readlink(path).encode() if item['mode'] == '120000' else path.read_bytes()
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == item['git_blob'], name
    package = read(ROOT / pins['c27_package_manifest']['path'])['sha256']
    for name, digest in package.items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    build = read(HERE / 'build-final.json')
    assert build['status'] == 'SUCCESS' and len(build['steps']) == 2
    assert all(s['status'] == 'SUCCESS' for s in build['steps'])
    assert build['results']['images'][0]['digest'] == 'sha256:0de4842308efeef1b64c3e51b9c225d2ce0dbdd5b4b321ea4c65c1b6e37de13d'
    return {'state': 'catalogue_source_and_preservation_verified', 'source_commit': TARGET,
        'composed_source_paths': len(expected), 'intentional_supersessions': len(overlay['changes']),
        'additions': len(overlay['additions']), 'preserved_prior_receipts': len(start['prior_evidence_files']),
        'preserved_c27_artifacts': len(package), 'protected_paths': len(preservation['protected_sha256']),
        'source_bound_linux_image_build': 'SUCCESS', 'broader_full_ci': 'deferred',
        'research_or_scientific_release_accepted': False}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
