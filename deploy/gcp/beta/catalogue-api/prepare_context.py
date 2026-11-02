"""Export a committed, source-bound catalogue API overlay; no cloud or data IO.

The immutable base contains the accepted 7924a28 API. Exactly one API module is
superseded and one is added. Every other base source, dependency lock, migration,
and entrypoint must still match that base in both the selected commit and checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PROJECT = 'ocean-v1-beta-20261101'
BASE_REVISION = '7924a28e919b1fb751890c694f7b1f9b26b104ff'
BASE_IMAGE = ('asia-northeast1-docker.pkg.dev/' + PROJECT + '/ocean-v1-beta/serving-api@sha256:'
    '28f769ee6b44cb46b10c936f045e609bb83ad9d9bc8ccefa98603801a52157ab')
BASE_SOURCE_DIGEST = '7ed5d6609d974dc1456ee774a2db57deef00a6930164cb3470f0f0678ba8619c'
OVERLAYS = ('api/v1_host.py', 'api/v1_catalogue_host.py')
PACKAGE_SOURCES = ('Dockerfile', 'empty-catalogue.json', 'base-api-source-manifest.json', 'prepare_context.py')
EMPTY_CONFIG = {
    'version': 'ocean-v1-empty-catalogue-v1', 'project_id': PROJECT,
    'site_id': 'v1:' + PROJECT, 'revision': 'beta-empty-registry-v1', 'snapshots': [],
}
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
        raise ValueError('Exact committed catalogue package source is unavailable')
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
        raise ValueError('Exact immutable base API source identity required')
    sources = document.get('sources')
    if (not isinstance(sources, dict) or len(sources) != 171
            or digest(json.dumps(sources, sort_keys=True, separators=(',', ':')).encode()) != BASE_SOURCE_DIGEST
            or not all(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value)
                for value in sources.values())
            or OVERLAYS[0] not in sources or OVERLAYS[1] in sources):
        raise ValueError('Exact reviewed base source pins required')
    return document


def validate_empty_config(data):
    if len(data) > 4096 or parse(data) != EMPTY_CONFIG or data != canonical(EMPTY_CONFIG):
        raise ValueError('Exact empty beta registry required; data import is a separate operation')


def validate_dockerfile(data):
    expected = [
        'FROM ' + BASE_IMAGE,
        'COPY --chown=0:0 --chmod=0444 application/api/v1_host.py /opt/ocean/api/v1_host.py',
        'COPY --chown=0:0 --chmod=0444 application/api/v1_catalogue_host.py /opt/ocean/api/v1_catalogue_host.py',
        'COPY --chown=0:0 --chmod=0444 source-manifest.json /opt/ocean/source-manifest.json',
        'COPY --chown=0:0 --chmod=0444 beta-host-config.json /opt/ocean/beta-host-config.json',
        'COPY --chown=0:0 --chmod=0444 empty-catalogue.json /opt/ocean/beta-empty-catalogue.json',
        'COPY --chown=0:0 --chmod=0444 catalogue-serving-manifest.json /opt/ocean/catalogue-serving-manifest.json',
        'ENV OCEAN_V1_HOST_CONFIG=/opt/ocean/beta-host-config.json OCEAN_V1_CATALOGUE_CONFIG=/opt/ocean/beta-empty-catalogue.json',
    ]
    actual = [line.strip() for line in data.decode().splitlines()
        if line.strip() and not line.lstrip().startswith('#')]
    if actual != expected:
        raise ValueError('Only the pinned base and exact read-only catalogue overlay are allowed')


def validate_closure(pins):
    # Reuse the accepted static import selector; it does not import the app,
    # connect databases, read configuration, or discover any data source.
    specification = importlib.util.spec_from_file_location('beta_api_static_selector',
        ROOT / 'deploy/gcp/beta/api/prepare_context.py')
    selector = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(selector)
    selected = {path.relative_to(ROOT).as_posix() for path in selector.selected_sources()}
    if not selected <= set(pins):
        raise ValueError('New local import is absent from the pinned image or explicit overlay')


def prepare(*, revision, output):
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
    validate_empty_config(values['empty-catalogue.json'])
    base = validate_base_manifest(values['base-api-source-manifest.json'])
    pins = dict(base['sources'])
    for relative, expected in base['sources'].items():
        original = git('show', BASE_REVISION + ':' + relative)
        if digest(original) != expected:
            raise ValueError('Base source receipt does not match the original Git object')
        current = committed_bytes(revision, relative)
        if relative != OVERLAYS[0] and current != original:
            raise ValueError('Unselected base source changed: ' + relative)
    overlays = {relative: committed_bytes(revision, relative) for relative in OVERLAYS}
    pins.update({relative: digest(data) for relative, data in overlays.items()})
    validate_closure(pins)
    source_manifest = {
        'version': 'ocean-v1-beta-api-context-v1', 'project_id': PROJECT, 'revision': revision,
        'sources': pins,
        'source_manifest_sha256': digest(json.dumps(pins, sort_keys=True, separators=(',', ':')).encode()),
        'selection': '171 pinned base sources, explicit host supersession and catalogue-host addition',
        'composition': {'base_revision': BASE_REVISION, 'base_serving_image': BASE_IMAGE,
            'base_source_manifest_sha256': BASE_SOURCE_DIGEST,
            'superseded_sources': [OVERLAYS[0]], 'added_sources': [OVERLAYS[1]]},
        'cloud_build_performed': False,
    }
    host_config = {**HOST_CONFIG, 'revision': revision}
    manifest = {
        'version': 'ocean-v1-beta-catalogue-serving-context-v1', 'project_id': PROJECT,
        'revision': revision, 'base_api_revision': BASE_REVISION, 'base_serving_image': BASE_IMAGE,
        'base_source_manifest_sha256': BASE_SOURCE_DIGEST,
        'source_pins': {**{name: digest(data) for name, data in values.items()},
            **{relative: digest(data) for relative, data in overlays.items()}},
        'composed_api_source_manifest_sha256': source_manifest['source_manifest_sha256'],
        'host_configuration_sha256': digest(canonical(host_config)),
        'empty_registry_sha256': digest(values['empty-catalogue.json']),
        'empty_registry_only': True, 'scientific_data_or_credentials_included': False,
        'unchanged_base_source_count': 170, 'superseded_sources': [OVERLAYS[0]],
        'added_sources': [OVERLAYS[1]], 'base_entrypoint_and_user_preserved': True,
        'inherited_runtime_user': '10001:10001', 'cloud_build_performed': False,
    }
    files = {'Dockerfile': values['Dockerfile'], 'empty-catalogue.json': values['empty-catalogue.json'],
        'source-manifest.json': canonical(source_manifest), 'beta-host-config.json': canonical(host_config),
        'catalogue-serving-manifest.json': canonical(manifest)}
    files.update({'application/' + name: data for name, data in overlays.items()})
    # Every check finishes before creating any output; no incomplete context is
    # left on source drift or an unauthorized/nonempty catalogue configuration.
    output.mkdir(parents=True)
    for name, data in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return {'revision': revision, 'base_serving_image': BASE_IMAGE,
        'context_files': sorted(files), 'unchanged_base_sources': 170,
        'composed_api_sources': len(pins), 'empty_registry_only': True,
        'manifest_sha256': digest(files['catalogue-serving-manifest.json'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(revision=args.revision, output=args.output), indent=2))
