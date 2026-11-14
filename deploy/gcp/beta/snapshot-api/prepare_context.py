"""Build a committed snapshot API overlay without copying any data or authority.

Catalogue authority is a separately selected private GCS activation document.
This context carries only source modules, deployment identities and the selected
opaque activation hash/object binding, never dataset rows, activation documents,
access-policy decisions, credentials or private keys.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PROJECT = 'ocean-v1-beta-20261101'
BASE_REVISION = 'abcdff79d8695be2e493efa29dc92c454d5b6dfe'
BASE_IMAGE = ('asia-northeast1-docker.pkg.dev/' + PROJECT + '/ocean-v1-beta/catalogue-api@sha256:'
    '0de4842308efeef1b64c3e51b9c225d2ce0dbdd5b4b321ea4c65c1b6e37de13d')
BASE_SOURCE_DIGEST = 'dcf27a4644f53fe014fa4f0c3eb4fd3969a66866b0dd1ddaad1b2d1164aeaf92'
SUPERSEDED = ('api/v1_host.py', 'api/v1_catalogue_host.py',
    'orchestration/frozen_scientific_catalogue.py', 'orchestration/catalogue_service.py',
    'orchestration/frozen_catalogue.py', 'orchestration/investigations.py',
    'orchestration/research_runs.py', 'orchestration/research_answers.py',
    'orchestration/research_evidence.py',
    'api/research_run_routes.py', 'api/research_evidence_routes.py')
ADDED = ('ingestion/gcs_catalogue_snapshot.py', 'api/v1_beta_research_host.py',
    'ingestion/beta_catalogue_retention.py', 'orchestration/cloud_research_dispatch.py',
    'api/v1_beta_question_services.py', 'api/v1_research_controller_host.py',
    'orchestration/beta_vertex_research.py', 'api/v1_beta_question_entry.py')
OVERLAYS = SUPERSEDED + ADDED
PACKAGE_SOURCES = ('Dockerfile', 'base-api-source-manifest.json', 'prepare_context.py', 'render_configuration.py')
CONFIGURATION_PATH = '/opt/ocean/beta-catalogue-source.json'
BUCKET = PROJECT + '-snapshots'
PREFIX = 'v1/catalogue'
HOST_CONFIG = {
    'version': 'ocean-v1-api-host-v1', 'project_id': PROJECT,
    'site_id': 'v1:' + PROJECT, 'public_origin': 'https://beta.oceaninfobio.com',
    'database_name': 'ocean_v1_beta', 'backend_hosts': ['127.0.0.1:8000'],
    'allowed_providers': ['google'], 'internal_issuer': 'ocean-v1-frontend',
    'internal_audience': 'ocean-v1-api',
}


def canonical(document):
    return (json.dumps(document, indent=2, sort_keys=True) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*arguments):
    result = subprocess.run(['git', '-C', str(ROOT), *arguments], capture_output=True)
    if result.returncode:
        raise ValueError('Exact committed snapshot package source is unavailable')
    return result.stdout


def unique(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError('Duplicate manifest key')
        document[key] = value
    return document


def parse(data):
    return json.loads(data.decode('utf-8'), object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON value')))


def committed_bytes(revision, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or str(path) != relative:
        raise ValueError('Repository-relative regular source required')
    listing = git('ls-tree', revision, '--', relative).decode().split()
    if len(listing) != 4 or listing[0] != '100644' or listing[1] != 'blob':
        raise ValueError('Committed regular source required: ' + relative)
    current = ROOT / path
    if (current.is_symlink() or not current.is_file()
            or any(parent.is_symlink() for parent in current.parents
                if parent != ROOT and parent.is_relative_to(ROOT))):
        raise ValueError('Regular non-symlink checkout source required: ' + relative)
    accepted = git('show', revision + ':' + relative)
    if current.read_bytes() != accepted:
        raise ValueError('Checkout differs from the selected source commit: ' + relative)
    return accepted


def validate_base_manifest(data):
    document = parse(data)
    if (document.get('version') != 'ocean-v1-beta-api-context-v1'
            or document.get('project_id') != PROJECT or document.get('revision') != BASE_REVISION
            or document.get('source_manifest_sha256') != BASE_SOURCE_DIGEST):
        raise ValueError('Exact immutable catalogue API source identity required')
    sources = document.get('sources')
    if (not isinstance(sources, dict) or len(sources) != 172
            or digest(json.dumps(sources, sort_keys=True, separators=(',', ':')).encode()) != BASE_SOURCE_DIGEST
            or not all(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value)
                for value in sources.values())
            or any(path not in sources for path in SUPERSEDED)
            or any(path in sources for path in ADDED)):
        raise ValueError('Exact reviewed base source pins required')
    return document


def validate_dockerfile(data):
    expected = ['FROM ' + BASE_IMAGE]
    expected.extend('COPY --chown=0:0 --chmod=0444 application/' + name + ' /opt/ocean/' + name
        for name in OVERLAYS)
    expected.extend([
        'COPY --chown=0:0 --chmod=0444 source-manifest.json /opt/ocean/source-manifest.json',
        'COPY --chown=0:0 --chmod=0444 beta-host-config.json /opt/ocean/beta-host-config.json',
        'COPY --chown=0:0 --chmod=0444 catalogue-source.json ' + CONFIGURATION_PATH,
        'COPY --chown=0:0 --chmod=0444 snapshot-serving-manifest.json /opt/ocean/snapshot-serving-manifest.json',
        'ENV OCEAN_V1_HOST_CONFIG=/opt/ocean/beta-host-config.json OCEAN_V1_CATALOGUE_MODE=sealed-gcs-v1 OCEAN_V1_CATALOGUE_CONFIG=' + CONFIGURATION_PATH,
    ])
    actual = [line.strip() for line in data.decode().splitlines()
        if line.strip() and not line.lstrip().startswith('#')]
    if actual != expected:
        raise ValueError('Only the pinned read-only source overlay is allowed; runtime authority is excluded')


def validate_binding(data, *, expected_sha256, activation_sha256):
    if (not re.fullmatch('[a-f0-9]{64}', expected_sha256)
            or not re.fullmatch('[a-f0-9]{64}', activation_sha256)
            or not 0 < len(data) <= 4096 or digest(data) != expected_sha256):
        raise ValueError('Exact selected bounded source-binding hash required')
    expected = {
        'version': 'ocean-v1-gcs-catalogue-host-v1', 'project_id': PROJECT,
        'site_id': 'v1:' + PROJECT, 'bucket': BUCKET, 'prefix': PREFIX,
        'activation_object': PREFIX + '/activations/' + activation_sha256 + '.json',
        'activation_sha256': activation_sha256,
    }
    if parse(data) != expected or data != canonical(expected):
        raise ValueError('Only the opaque fixed-beta activation binding is allowed')
    return expected


def read_binding(path, *, expected_sha256, activation_sha256):
    path = path.absolute()
    if (path.is_relative_to(ROOT) or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError('Explicit non-symlink source binding outside the repository required')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) not in {0o400, 0o444, 0o600}
                or not 0 < before.st_size <= 4096):
            raise ValueError('Operator-owned private regular source-binding file required')
        data = os.read(descriptor, 4097)
        after = os.fstat(descriptor)
        if (len(data) != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('Source binding changed while reading')
    finally:
        os.close(descriptor)
    validate_binding(data, expected_sha256=expected_sha256, activation_sha256=activation_sha256)
    return data


def validate_closure(pins):
    specification = importlib.util.spec_from_file_location('beta_api_static_selector',
        ROOT / 'deploy/gcp/beta/api/prepare_context.py')
    selector = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(selector)
    selected = {path.relative_to(ROOT).as_posix() for path in selector.selected_sources()}
    if not selected <= set(pins):
        raise ValueError('New local import is absent from the pinned image or explicit overlay')


def prepare(*, revision, output, binding, binding_sha256, activation_sha256):
    if not re.fullmatch('[a-f0-9]{40}', revision) or revision == BASE_REVISION:
        raise ValueError('Explicit new full source commit required')
    if git('rev-parse', '--verify', revision + '^{commit}').decode().strip() != revision:
        raise ValueError('Exact source commit required')
    git('merge-base', '--is-ancestor', BASE_REVISION, revision)
    output = output.absolute()
    if output.exists() or output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        raise ValueError('New non-symlink output directory required')
    values = {name: committed_bytes(revision, (HERE / name).relative_to(ROOT).as_posix())
        for name in PACKAGE_SOURCES}
    validate_dockerfile(values['Dockerfile'])
    binding_data = read_binding(binding, expected_sha256=binding_sha256, activation_sha256=activation_sha256)
    base = validate_base_manifest(values['base-api-source-manifest.json'])
    pins = dict(base['sources'])
    for relative, expected in base['sources'].items():
        original = git('show', BASE_REVISION + ':' + relative)
        if digest(original) != expected:
            raise ValueError('Base source receipt does not match the original Git object')
        current = committed_bytes(revision, relative)
        if relative not in SUPERSEDED and current != original:
            raise ValueError('Unselected base source changed: ' + relative)
    overlays = {relative: committed_bytes(revision, relative) for relative in OVERLAYS}
    pins.update({relative: digest(data) for relative, data in overlays.items()})
    validate_closure(pins)
    source_manifest = {
        'version': 'ocean-v1-beta-api-context-v1', 'project_id': PROJECT, 'revision': revision,
        'sources': pins,
        'source_manifest_sha256': digest(json.dumps(pins, sort_keys=True, separators=(',', ':')).encode()),
        'selection': f'172 pinned catalogue base sources, {len(SUPERSEDED)} explicit supersessions and {len(ADDED)} GCS/context/research additions',
        'composition': {'base_revision': BASE_REVISION, 'base_serving_image': BASE_IMAGE,
            'base_source_manifest_sha256': BASE_SOURCE_DIGEST,
            'superseded_sources': list(SUPERSEDED), 'added_sources': list(ADDED)},
        'cloud_build_performed': False,
    }
    host_config = {**HOST_CONFIG, 'revision': revision}
    manifest = {
        'version': 'ocean-v1-beta-snapshot-serving-context-v1', 'project_id': PROJECT,
        'revision': revision, 'base_api_revision': BASE_REVISION, 'base_serving_image': BASE_IMAGE,
        'base_source_manifest_sha256': BASE_SOURCE_DIGEST,
        'source_pins': {**{name: digest(data) for name, data in values.items()},
            **{relative: digest(data) for relative, data in overlays.items()}},
        'composed_api_source_manifest_sha256': source_manifest['source_manifest_sha256'],
        'host_configuration_sha256': digest(canonical(host_config)),
        'source_binding_path': CONFIGURATION_PATH, 'opaque_source_binding_included': True,
        'source_binding_sha256': binding_sha256, 'activation_sha256': activation_sha256,
        'activation_object': PREFIX + '/activations/' + activation_sha256 + '.json',
        'runtime_activation_document_included': False, 'access_policy_or_dataset_ids_included': False,
        'scientific_data_or_credentials_included': False,
        'unchanged_base_source_count': len(base['sources']) - len(SUPERSEDED), 'superseded_sources': list(SUPERSEDED),
        'added_sources': list(ADDED), 'base_entrypoint_and_user_preserved': True,
        'inherited_runtime_user': '10001:10001', 'cloud_build_performed': False,
    }
    files = {'Dockerfile': values['Dockerfile'], 'source-manifest.json': canonical(source_manifest),
        'beta-host-config.json': canonical(host_config), 'catalogue-source.json': binding_data,
        'snapshot-serving-manifest.json': canonical(manifest)}
    files.update({'application/' + name: data for name, data in overlays.items()})
    output.mkdir(parents=True)
    for name, data in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return {'revision': revision, 'base_serving_image': BASE_IMAGE,
        'context_files': sorted(files), 'unchanged_base_sources': len(base['sources']) - len(SUPERSEDED),
        'composed_api_sources': len(pins), 'runtime_activation_document_included': False,
        'opaque_source_binding_included': True, 'source_binding_sha256': binding_sha256,
        'activation_sha256': activation_sha256,
        'manifest_sha256': digest(files['snapshot-serving-manifest.json'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--binding-sha256', required=True)
    parser.add_argument('--activation-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(revision=args.revision, output=args.output, binding=args.binding,
        binding_sha256=args.binding_sha256, activation_sha256=args.activation_sha256), indent=2))
