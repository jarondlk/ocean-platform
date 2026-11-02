"""Only committed finite transport adapter atop the accepted frontend image."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
IMAGE = ('asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/frontend@sha256:'
    'adb5bc75dbc56d146bdf6e63f83a3dc8b3867b0318de0c2c02ba6fc56023e9dc')


def prepare(revision, output):
    if not re.fullmatch(r'[a-f0-9]{40}', revision) or output.exists() or output.is_symlink():
        raise ValueError('Full committed source and new context directory required')
    sources = {}
    for name in ['Dockerfile', 'forwarded-adapter.cjs', 'prepare_context.py']:
        path = HERE / name
        accepted = subprocess.check_output(['git', 'show', revision + ':' + path.relative_to(ROOT).as_posix()], cwd=ROOT)
        if path.is_symlink() or path.read_bytes() != accepted:
            raise ValueError('Adapter package must equal the explicit source commit')
        sources[name] = accepted
    manifest = {'version': 'beta-serving-frontend-transport-v1',
        'project_id': 'ocean-v1-beta-20261101', 'service_id': 'ocean-v1-beta-serving',
        'revision': revision, 'frontend_source_revision': '7924a28e919b1fb751890c694f7b1f9b26b104ff',
        'frontend_base_image': IMAGE, 'source_pins': {name: hashlib.sha256(value).hexdigest()
            for name, value in sorted(sources.items())},
        'application_or_auth_source_changed': False, 'image_built_or_deployed': False}
    output.mkdir(parents=True)
    for name in ['Dockerfile', 'forwarded-adapter.cjs']:
        (output / name).write_bytes(sources[name])
    (output / 'serving-frontend-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {'state': 'source_context_prepared', 'revision': revision,
        'frontend_base_image': IMAGE, 'credentials_included': False, 'cloud_calls': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.revision, args.output)))
