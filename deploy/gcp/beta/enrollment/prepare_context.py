"""Export committed first-account helper only; no credentials or cloud calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
API_REVISION = '7924a28e919b1fb751890c694f7b1f9b26b104ff'
API_IMAGE = ('asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:'
    'f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f')


def prepare(revision, output):
    if not re.fullmatch(r'[a-f0-9]{40}', revision) or output.exists() or output.is_symlink():
        raise ValueError('Explicit full commit and new context directory required')
    sources = {}
    for name in ['Dockerfile', 'enroll.py', 'prepare_context.py']:
        path = HERE / name
        relative = path.relative_to(ROOT).as_posix()
        accepted = subprocess.check_output(['git', 'show', revision + ':' + relative], cwd=ROOT)
        if path.is_symlink() or path.read_bytes() != accepted:
            raise ValueError('Enrollment source must equal the explicit Git commit')
        sources[name] = accepted
    manifest = {'version': 'ocean-beta-first-account-package-v1',
        'project_id': 'ocean-v1-beta-20261101', 'revision': revision,
        'api_revision': API_REVISION, 'api_image': API_IMAGE,
        'source_pins': {name: hashlib.sha256(value).hexdigest() for name, value in sorted(sources.items())},
        'image_build_performed': False, 'identity_or_credential_values_included': False}
    output.mkdir(parents=True)
    for name in ['Dockerfile', 'enroll.py']:
        (output / name).write_bytes(sources[name])
    (output / 'enrollment-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {'state': 'source_context_prepared', 'revision': revision, 'api_image': API_IMAGE,
        'credentials_included': False, 'cloud_calls': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.revision, args.output)))
