"""Prepare the serving-only B3 API overlay on the accepted B2 image."""

import argparse
import json
import os
from pathlib import Path
import re

from deploy.gcp.beta.b2 import prepare_api_context as b2


LIVE_RECEIPT = b2.RECEIPTS + 'b2-20261116/discovery-live-20261122.json'
BASE_REVISION = '0994e9de7684025d5bf94ec8ad6a96e21edd1526'
BASE_IMAGE = b2.REGISTRY + '@sha256:64f99fceba741b5ab781466c45191ea190d241cb9fe745fa342d2d53beeb574e'
BASE_SOURCE_DIGEST = '44bedc906bec71ca6ddcc9189036c1f9bf2006e498cfa76238f3ec5666fa2caf'
SUPERSEDED = (
    'api/v1_beta_question_entry.py',
    'api/v1_beta_question_services.py',
    'api/v1_host.py',
    'api/v1_research_controller_host.py',
    'api/v1_runtime_routes.py',
    'ingestion/artifact_store.py',
    'orchestration/experiment_workspace.py',
    'orchestration/research_experiments.py',
    'schema/experiment_workspace.py',
)
ADDED = (
    'api/v1_beta_experiment_reads.py',
    'db/experiment_execution_models.py',
    'orchestration/experiment_sandbox/execution_store.py',
    'orchestration/experiment_sandbox/ledger_reader.py',
    'orchestration/experiment_sandbox/operator_inspection.py',
    'orchestration/experiment_sandbox/proofs.py',
    'orchestration/experiment_sandbox/retained_bridge.py',
    'orchestration/experiment_sandbox/retained_output_store.py',
    'orchestration/experiment_sandbox/workspace_projection.py',
    'schema/experiment_execution.py',
)

OFFLINE_PROOF = '''
import hashlib
import json
import os
from pathlib import Path
import stat

from api.v1_beta_experiment_reads import load_beta_experiment_reads
from api.v1_beta_question_entry import main
from api.v1_research_controller_host import create_from_environment

root = Path('/opt/ocean')
assert (os.geteuid(), os.getegid()) == (10001, 10001)
assert callable(load_beta_experiment_reads) and callable(main) and callable(create_from_environment)
package = json.loads((root / 'b3-read-package.json').read_text())
manifest = json.loads((root / 'source-manifest.json').read_text())
pins = manifest['sources']
assert manifest['revision'] == package['runtime_revision']
source_digest = hashlib.sha256(json.dumps(pins, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
assert source_digest == manifest['source_manifest_sha256'] == package['source_manifest_sha256']
build_only = {'requirements/runtime.txt', 'deploy/gcp/beta/api/Dockerfile', 'deploy/gcp/beta/api/prepare_context.py'}
overrides = set(package['superseded_sources']) | set(package['added_sources'])
for name, digest in pins.items():
    if name in build_only:
        continue
    path = root / ('beta_entry.py' if name == 'deploy/gcp/beta/api/entry.py' else name)
    if name in overrides:
        assert not path.is_symlink() and path.stat().st_uid == 0 and stat.S_IMODE(path.stat().st_mode) == 0o444, name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
host = root / 'beta-host-config.json'
assert hashlib.sha256(host.read_bytes()).hexdigest() == package['host_configuration_sha256']
assert json.loads(host.read_text())['revision'] == manifest['revision']
assert not {'OCEAN_V1_EXPERIMENT_READ_CONFIG', 'OCEAN_V1_EXPERIMENT_LEDGER_URL'} & os.environ.keys()
assert not (root / 'data').exists()
print('Verified the B3 serving overlay, inherited source pins and offline read-port imports')
'''


def prepare(revision, output):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Select an exact serving runtime commit')
    b2.git('merge-base', '--is-ancestor', BASE_REVISION, revision)
    b2.committed(revision, Path(__file__).relative_to(b2.ROOT).as_posix(), current=True)
    receipt_raw = b2.committed(revision, LIVE_RECEIPT, current=True)
    receipt = json.loads(receipt_raw)
    proof = receipt['image_proof']
    if ((receipt['serving']['new_image'], proof['image'], proof['runtime_revision'], proof['source_manifest_sha256'])
            != (BASE_IMAGE, BASE_IMAGE, BASE_REVISION, BASE_SOURCE_DIGEST)
            or proof['offline_proof'] != 'success'):
        raise ValueError('Expected the accepted B2 serving image receipt')

    inventory = json.loads(b2.committed(b2.BASE_REVISION, b2.BASE_INVENTORY))['sources']
    base_pins = {name: b2.digest(b2.committed(BASE_REVISION, name)) for name in (*inventory, *b2.ADDED)}
    if (b2.source_digest(base_pins) != BASE_SOURCE_DIGEST or not set(SUPERSEDED) <= base_pins.keys()
            or set(ADDED) & base_pins.keys()):
        raise ValueError('The B2 runtime inventory differs from the accepted image')
    overlays = {name: b2.committed(revision, name, current=True) for name in (*SUPERSEDED, *ADDED)}
    for name, digest in base_pins.items():
        changed = b2.digest(b2.committed(revision, name, current=True)) != digest
        if changed != (name in SUPERSEDED):
            raise ValueError(f'Unexpected change or missing supersession: {name}')
    pins = {**base_pins, **{name: b2.digest(raw) for name, raw in overlays.items()}}
    host = b2.canonical({
        'version': 'ocean-v1-api-host-v1', 'project_id': b2.PROJECT, 'site_id': 'v1:' + b2.PROJECT,
        'public_origin': 'https://beta.oceaninfobio.com', 'database_name': 'ocean_v1_beta',
        'backend_hosts': ['127.0.0.1:8000'], 'allowed_providers': ['google'],
        'internal_issuer': 'ocean-v1-frontend', 'internal_audience': 'ocean-v1-api', 'revision': revision,
    })
    manifest = {'version': 'ocean-v1-beta-api-context-v1', 'project_id': b2.PROJECT, 'revision': revision,
        'sources': pins, 'source_manifest_sha256': b2.source_digest(pins)}
    image = b2.REGISTRY + ':b3-experiment-reads-' + revision[:12]
    package = {'version': 'ocean-beta-b3-experiment-read-package-v1', 'runtime_revision': revision,
        'base_revision': BASE_REVISION, 'base_image': BASE_IMAGE, 'base_source_manifest_sha256': BASE_SOURCE_DIGEST,
        'base_receipt_sha256': b2.digest(receipt_raw), 'source_manifest_sha256': manifest['source_manifest_sha256'],
        'host_configuration_sha256': b2.digest(host), 'superseded_sources': SUPERSEDED, 'added_sources': ADDED,
        'image_tag': image}
    files = {f'application/{name}': raw for name, raw in overlays.items()}
    files.update({'source-manifest.json': b2.canonical(manifest), 'beta-host-config.json': host,
                  'b3-read-package.json': b2.canonical(package)})
    dockerfile = ['FROM ' + BASE_IMAGE]
    dockerfile.extend(f'COPY --chown=0:0 --chmod=0444 {name} /opt/ocean/{name.removeprefix("application/")}'
                      for name in files)
    build = b2.build_config(revision, image, OFFLINE_PROOF)
    build['steps'][0]['id'] = 'build-b3-read-api'
    build['steps'][2]['id'] = 'verify-b3-read-api-offline'
    files.update({'Dockerfile': ('\n'.join(dockerfile) + '\n').encode(), 'cloudbuild.json': b2.canonical(build)})
    output = output.absolute()
    if (output.exists() or output.resolve() != output or output.is_relative_to(b2.ROOT)
            or not output.parent.is_dir()):
        raise ValueError('Select a new build context under an existing private directory outside the checkout')
    output.mkdir(mode=0o700)
    for name, raw in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
    return {'package': package, 'files': {name: b2.digest(raw) for name, raw in sorted(files.items())}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(b2.canonical(prepare(args.revision, args.output)).decode(), end='')
