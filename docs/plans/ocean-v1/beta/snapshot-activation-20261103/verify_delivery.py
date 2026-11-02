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
TARGET = 'a4923c4e41fba694f77ebb60c1d3f768390e8b1b'


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
    overlay = read(HERE.parent / 'catalogue-20261102/source-supersession.json')
    for name, value in overlay['changes'].items():
        assert expected[name] == value['from_sha256']
        expected[name] = value['to_sha256']
    assert not set(overlay['additions']).intersection(expected)
    expected.update(overlay['additions'])
    assert len(expected) == 882
    overlay = read(HERE / 'source-supersession.json')
    for name, value in overlay['changes'].items():
        assert expected[name] == value['from_sha256']
        expected[name] = value['to_sha256']
    assert not set(overlay['additions']).intersection(expected)
    expected.update(overlay['additions'])
    assert len(expected) == 885
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
    assert build['results']['images'][0]['digest'] == 'sha256:877b1b3f7db703f5a8e9fedc3cca30f4a5aa67d238201cb5e9159482561e7eb9'
    assert build['id'] == '4b8fa356-9261-4a0a-9df9-df61c88669ef'
    service = read(HERE / 'service-effective.json')
    before = read(HERE / 'service-immediately-before.json')
    assert service['terminalCondition']['state'] == 'CONDITION_SUCCEEDED'
    assert service['generation'] == service['observedGeneration'] == '8'
    assert service['latestReadyRevision'].endswith('/ocean-v1-beta-serving-00008-ngj')
    # Reconcile the exact update: only API image and two source-selection values.
    import copy
    observed_template = copy.deepcopy(service['template'])
    previous_template = copy.deepcopy(before['template'])
    for template in (observed_template, previous_template):
        # Revision is server-generated deployment identity, not configuration.
        template.pop('revision', None)
    prior_api = next(c for c in previous_template['containers'] if c['name'] == 'api')
    observed_api = next(c for c in observed_template['containers'] if c['name'] == 'api')
    assert observed_api['image'].endswith('@' + build['results']['images'][0]['digest'])
    observed_api['image'] = prior_api['image']
    names = {'OCEAN_V1_CATALOGUE_CONFIG', 'OCEAN_V1_CATALOGUE_MODE'}
    assert {e['name']: e['value'] for e in observed_api['env'] if e['name'] in names} == {
        'OCEAN_V1_CATALOGUE_CONFIG': '/opt/ocean/beta-catalogue-source.json',
        'OCEAN_V1_CATALOGUE_MODE': 'sealed-gcs-v1'}
    observed_api['env'] = [e for e in observed_api['env'] if e['name'] not in names]
    observed_api['env'] += [e for e in prior_api['env'] if e['name'] in names]
    for api in (prior_api, observed_api):
        api['env'].sort(key=lambda e: e['name'])
    assert observed_template == previous_template, 'Undeclared runtime configuration change'
    for field in ('ingress', 'invokerIamDisabled', 'defaultUriDisabled', 'scaling', 'traffic'):
        assert service.get(field) == before.get(field), field
    uploaded = read(HERE / 'data-upload-complete.json')
    assert len(uploaded['objects']) == 8
    assert all(o['download_sha256_verified'] for o in uploaded['objects'])
    assert uploaded['objects'][-1]['control_published_last']
    assert uploaded['casts'] == 162 and uploaded['depth_observations'] == 10955
    assert uploaded['scientific_approval'] is False
    grant = read(HERE / 'reader-grant-verification.json')
    assert grant['all_other_bindings_preserved'] and not grant['legacy_or_project_grant']
    return {'state': 'sealed_ctd_deployment_source_and_preservation_verified', 'source_commit': TARGET,
        'composed_source_paths': len(expected), 'intentional_supersessions': len(overlay['changes']),
        'additions': len(overlay['additions']), 'preserved_prior_receipts': len(start['prior_evidence_files']),
        'preserved_c27_artifacts': len(package), 'protected_paths': len(preservation['protected_sha256']),
        'source_bound_linux_image_build': 'SUCCESS', 'actual_revision': 'ocean-v1-beta-serving-00008-ngj', 'objects_readback_verified': 8, 'casts': 162, 'depth_observations': 10955, 'broader_full_ci': 'deferred',
        'research_or_scientific_release_accepted': False}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
