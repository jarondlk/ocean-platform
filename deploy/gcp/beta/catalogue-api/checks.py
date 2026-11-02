"""Offline packaging boundary probes; no cloud, credential, data or output IO."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('catalogue_packaging', HERE / 'prepare_context.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
CHECKS = []


def check(name, action, *, rejects=False):
    try:
        action()
    except (ValueError, UnicodeError):
        if not rejects:
            raise
    else:
        if rejects:
            raise AssertionError(name)
    CHECKS.append(name)


def main():
    base = (HERE / 'base-api-source-manifest.json').read_bytes()
    document = json.loads(base)
    dockerfile = (HERE / 'Dockerfile').read_bytes()
    empty = (HERE / 'empty-catalogue.json').read_bytes()
    check('original171basepins_valid', lambda: package.validate_base_manifest(base))
    check('exactemptyregistry_valid', lambda: package.validate_empty_config(empty))
    check('exactpinnedDockerfile_valid', lambda: package.validate_dockerfile(dockerfile))
    for name, value in [
        ('nonempty_registry_refused', {**package.EMPTY_CONFIG, 'snapshots': [{'snapshot_id': '0' * 64}]}),
        ('foreign_project_refused', {**package.EMPTY_CONFIG, 'project_id': 'data-infra-infobio'}),
        ('unknown_config_key_refused', {**package.EMPTY_CONFIG, 'approve_all': True}),
    ]:
        check(name, lambda value=value: package.validate_empty_config(package.canonical(value)), rejects=True)
    check('duplicate_config_key_refused', lambda: package.validate_empty_config(
        empty.replace(b'"snapshots": [],', b'"snapshots": [], "snapshots": [],')), rejects=True)
    check('image_mutation_refused', lambda: package.validate_dockerfile(dockerfile.replace(
        package.BASE_IMAGE.encode(), package.BASE_IMAGE.replace('28f769ee', '28f769ef').encode())), rejects=True)
    for name, extra in [('entrypoint_mutation_refused', b'ENTRYPOINT ["sh"]\n'),
            ('run_instruction_refused', b'RUN echo unexpected\n')]:
        check(name, lambda extra=extra: package.validate_dockerfile(dockerfile + extra), rejects=True)
    modified = json.loads(base)
    modified['sources']['config.py'] = '0' * 64
    check('alteredbasepins_refused', lambda: package.validate_base_manifest(json.dumps(modified).encode()), rejects=True)
    check('basecommit_mismatch_refused', lambda: package.validate_base_manifest(
        json.dumps({**document, 'revision': '0' * 40}).encode()), rejects=True)
    check('checkout_path_escape_refused', lambda: package.committed_bytes(package.BASE_REVISION, '../config.py'), rejects=True)
    package.validate_closure({**document['sources'], 'api/v1_catalogue_host.py': '0' * 64})
    CHECKS.append('current_static_import_closure_present_in_base_or_overlay')
    print(json.dumps({'state': 'packaging_boundary_checks_passed', 'count': len(CHECKS),
        'checks': CHECKS, 'cloud_calls': False, 'credentials_or_data_read': False}, indent=2))


if __name__ == '__main__':
    main()
