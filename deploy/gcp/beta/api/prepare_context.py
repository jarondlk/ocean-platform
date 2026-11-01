"""Produce a source-only API build context; no upload, image build or deploy.

Every selected checkout byte must equal its object at the explicit source commit.
Unrelated dirty files are neither copied nor required to be discarded.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
PACKAGE = Path(__file__).resolve().parent
LOCAL_ROOTS = frozenset({'api', 'db', 'orchestration', 'schema', 'retrieval',
    'ingestion', 'preprocessing', 'sandbox', 'config', 'model_runtime'})


def module_path(name):
    path = ROOT.joinpath(*name.split('.'))
    if path.with_suffix('.py').is_file():
        return path.with_suffix('.py')
    if (path / '__init__.py').is_file():
        return path / '__init__.py'
    return None


def selected_sources():
    selected, todo = set(), ['api.v1_host', 'db.app_models']
    while todo:
        name = todo.pop()
        if name.split('.')[0] not in LOCAL_ROOTS:
            continue
        path = module_path(name)
        if path is None or path in selected:
            continue
        selected.add(path)
        package_name = name if path.name == '__init__.py' else name.rpartition('.')[0]
        parts = name.split('.')
        todo.extend('.'.join(parts[:i]) for i in range(1, len(parts)))
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Import):
                todo.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package_name.split('.')
                    if node.level > len(base):
                        raise ValueError('Unsupported relative import in source closure')
                    base = base[:len(base) - node.level + 1]
                    prefix = '.'.join(base + ([node.module] if node.module else []))
                else:
                    prefix = node.module or ''
                if prefix:
                    todo.append(prefix)
                    todo.extend(prefix + '.' + alias.name for alias in node.names if alias.name != '*')
    selected.update(ROOT.glob('migrations/**/*.py'))
    selected.update({ROOT / 'migrations/script.py.mako', ROOT / 'alembic.ini'})
    for path in selected:
        relative = path.relative_to(ROOT)
        if (path.is_symlink() or not path.resolve().is_relative_to(ROOT)
                or any(parent.is_symlink() for parent in path.parents if parent != ROOT and parent.is_relative_to(ROOT))
                or relative == Path('api/main.py')
                or any('fixture' in part.lower() or part in {'tests', 'data'} for part in relative.parts)):
            raise ValueError('Forbidden source in build closure: ' + str(relative))
    return sorted(selected)


def prepare(output, revision):
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Explicit full source commit required')
    if output.exists() or output.is_symlink():
        raise ValueError('Build context output must not already exist')
    # Complete all checks before making the output directory.
    sources = selected_sources()
    additional = [ROOT / 'requirements/runtime.txt', PACKAGE / 'Dockerfile', PACKAGE / 'entry.py',
        PACKAGE / 'prepare_context.py']
    values = {}
    for path in sources + additional:
        relative = path.relative_to(ROOT).as_posix()
        accepted = subprocess.run(['git', 'show', revision + ':' + relative], cwd=ROOT,
            check=True, capture_output=True).stdout
        if path.is_symlink() or path.read_bytes() != accepted:
            raise ValueError('Selected source does not equal the explicit commit: ' + relative)
        values[relative] = accepted
    pins = {name: hashlib.sha256(value).hexdigest() for name, value in sorted(values.items())}
    manifest = {'version': 'ocean-v1-beta-api-context-v1', 'revision': revision,
        'project_id': 'ocean-v1-beta-20261101', 'sources': pins,
        'source_manifest_sha256': hashlib.sha256(json.dumps(pins, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest(),
        'selection': 'transitive static local imports plus reviewed migration files; no scientific data or fixtures',
        'cloud_build_performed': False}
    output.mkdir(parents=True)
    for path in sources:
        target = output / 'application' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(values[path.relative_to(ROOT).as_posix()])
    for relative, target in [('requirements/runtime.txt', 'requirements/runtime.txt'),
            ('deploy/gcp/beta/api/Dockerfile', 'Dockerfile'), ('deploy/gcp/beta/api/entry.py', 'entry.py')]:
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(values[relative])
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'revision': revision, 'source_count': len(pins),
        'source_manifest_sha256': manifest['source_manifest_sha256']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    arguments = parser.parse_args()
    prepare(arguments.output.absolute(), arguments.revision)
