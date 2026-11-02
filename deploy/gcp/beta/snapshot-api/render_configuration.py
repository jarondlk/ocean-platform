"""Render only an opaque beta source binding from an explicitly frozen input.

Reads one operator-selected activation document outside Git, checks its exact
SHA256 and bounded structural contract, and writes no dataset IDs, policies,
registrations, labels, qualifications or data rows to the generated config.
It performs no cloud, credential, database, data acquisition or approval action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[4]
PROJECT = 'ocean-v1-beta-20261101'
BUCKET = PROJECT + '-snapshots'
PREFIX = 'v1/catalogue'
MAX_ACTIVATION_BYTES = 256 * 1024
SHA = re.compile('[a-f0-9]{64}')
IDENTIFIER = re.compile('[A-Za-z0-9][A-Za-z0-9._:-]{0,255}')
FAMILIES = {'ctd', 'metagenome', 'remote_sensing', 'edna_metabarcoding'}


def require(condition):
    if not condition:
        raise ValueError('Selected bounded beta activation metadata rejected')


def canonical(document):
    return (json.dumps(document, indent=2, sort_keys=True) + '\n').encode()


def wire(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def unique(pairs):
    document = {}
    for key, value in pairs:
        require(key not in document)
        document[key] = value
    return document


def exact_keys(document, keys):
    require(type(document) is dict and set(document) == set(keys))


def identity(value):
    require(type(value) is str and IDENTIFIER.fullmatch(value) is not None)


def sha(value):
    require(type(value) is str and SHA.fullmatch(value) is not None)


def text(value):
    require(type(value) is str and 1 <= len(value) <= 4000 and bool(value.strip()))


def validate_activation(data, *, expected_sha256):
    sha(expected_sha256)
    require(0 < len(data) <= MAX_ACTIVATION_BYTES and hashlib.sha256(data).hexdigest() == expected_sha256)
    document = json.loads(data.decode('utf-8'), object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite activation value')))
    exact_keys(document, {'version', 'project_id', 'site_id', 'policy_revision',
        'authorization_ref', 'access', 'scientific_mode', 'scientific_approval',
        'research_enabled', 'snapshots', 'qualifications'})
    require(document['version'] == 'ocean-v1-catalogue-activation-v1'
        and document['project_id'] == PROJECT and document['site_id'] == 'v1:' + PROJECT
        and document['scientific_mode'] == 'datasets_only'
        and document['scientific_approval'] is False and document['research_enabled'] is False)
    identity(document['policy_revision'])
    require(document['authorization_ref'] in {
        'chat-20261102-all-eligible-existing-data',
        'chat-20261103-all-beta-deployment-and-scientific-data',
    })
    exact_keys(document['access'], {'roles', 'account_types'})
    require(document['access']['roles'] == ['admin'] and document['access']['account_types'] == ['internal'])
    qualifications = document['qualifications']
    require(type(qualifications) is list and 1 <= len(qualifications) <= 32)
    for qualification in qualifications:
        text(qualification)
    snapshots = document['snapshots']
    require(type(snapshots) is list and 1 <= len(snapshots) <= 128)
    snapshot_ids, registration_ids = set(), set()
    for snapshot in snapshots:
        exact_keys(snapshot, {'descriptor', 'registration', 'datasets'})
        descriptor, registration = snapshot['descriptor'], snapshot['registration']
        exact_keys(descriptor, {'snapshot_id', 'label'})
        sha(descriptor['snapshot_id'])
        require(descriptor['snapshot_id'] not in snapshot_ids)
        snapshot_ids.add(descriptor['snapshot_id'])
        exact_keys(descriptor['label'], {'en', 'ja'})
        for label in descriptor['label'].values():
            text(label)
        exact_keys(registration, {'snapshot_id', 'child_snapshot_ids', 'references', 'registration_id'})
        require(registration['snapshot_id'] == descriptor['snapshot_id'])
        identity(registration['registration_id'])
        require(registration['registration_id'] not in registration_ids)
        registration_ids.add(registration['registration_id'])
        children = registration['child_snapshot_ids']
        require(type(children) is list and 1 <= len(children) <= 128)
        for child in children:
            sha(child)
        require(children == sorted(set(children)) and descriptor['snapshot_id'] not in children)
        expected_references = [['c14:dependency:' + hashlib.sha256(wire([
            registration['registration_id'], descriptor['snapshot_id'], child])).hexdigest(), child]
            for child in [descriptor['snapshot_id'], *children]]
        require(registration['references'] == expected_references)
        datasets = snapshot['datasets']
        require(type(datasets) is list and 1 <= len(datasets) <= 4000)
        dataset_ids, bound_children = set(), set()
        for dataset in datasets:
            exact_keys(dataset, {'dataset_id', 'source_family', 'source_id', 'snapshot_id'})
            identity(dataset['dataset_id'])
            identity(dataset['source_id'])
            require(dataset['source_family'] in FAMILIES and dataset['snapshot_id'] in children
                and dataset['dataset_id'] not in dataset_ids)
            dataset_ids.add(dataset['dataset_id'])
            bound_children.add(dataset['snapshot_id'])
        require(bound_children == set(children))
    return document


def read_activation(path, *, expected_sha256):
    path = path.absolute()
    require(not path.is_relative_to(ROOT) and not path.is_symlink()
        and all(not parent.is_symlink() for parent in path.parents))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_nlink == 1
            and stat.S_IMODE(before.st_mode) in {0o400, 0o600} and 0 < before.st_size <= MAX_ACTIVATION_BYTES)
        data = os.read(descriptor, MAX_ACTIVATION_BYTES + 1)
        after = os.fstat(descriptor)
        require(len(data) == before.st_size and
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns))
    finally:
        os.close(descriptor)
    validate_activation(data, expected_sha256=expected_sha256)
    return data


def binding_document(activation_sha256):
    sha(activation_sha256)
    return {
        'version': 'ocean-v1-gcs-catalogue-host-v1', 'project_id': PROJECT,
        'site_id': 'v1:' + PROJECT, 'bucket': BUCKET, 'prefix': PREFIX,
        'activation_object': PREFIX + '/activations/' + activation_sha256 + '.json',
        'activation_sha256': activation_sha256,
    }


def render(*, activation, activation_sha256, output):
    output = output.absolute()
    require(not output.is_relative_to(ROOT) and not output.exists() and not output.is_symlink()
        and all(not parent.is_symlink() for parent in output.parents))
    read_activation(activation, expected_sha256=activation_sha256)
    data = canonical(binding_document(activation_sha256))
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())
    return {'state': 'opaque_beta_source_binding_rendered',
        'activation_sha256': activation_sha256, 'binding_sha256': hashlib.sha256(data).hexdigest(),
        'binding_bytes': len(data), 'dataset_ids_rows_policy_or_credentials_in_output': False,
        'cloud_calls': False, 'scientific_approval_claimed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activation', type=Path, required=True)
    parser.add_argument('--activation-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(render(activation=args.activation,
            activation_sha256=args.activation_sha256, output=args.output), indent=2))
    except Exception:
        print(json.dumps({'state': 'rejected', 'error': 'Selected activation metadata or output rejected', 'cloud_calls': False}))
        raise SystemExit(2) from None
