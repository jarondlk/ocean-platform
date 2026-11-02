"""Offline source-package boundary probes; no cloud, config, data or key IO."""
from __future__ import annotations

import importlib.util
import json
import copy
import hashlib
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('snapshot_packaging', HERE / 'prepare_context.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
renderer_spec = importlib.util.spec_from_file_location('snapshot_configuration', HERE / 'render_configuration.py')
renderer = importlib.util.module_from_spec(renderer_spec)
renderer_spec.loader.exec_module(renderer)
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
    check('original172basepins_valid', lambda: package.validate_base_manifest(base))
    check('exactpinned_readonlyDockerfile_valid', lambda: package.validate_dockerfile(dockerfile))
    check('image_mutation_refused', lambda: package.validate_dockerfile(dockerfile.replace(
        package.BASE_IMAGE.encode(), package.BASE_IMAGE.replace('0de48423', '0de48424').encode())), rejects=True)
    for name, extra in [
        ('entrypoint_mutation_refused', b'ENTRYPOINT ["sh"]\n'),
        ('run_instruction_refused', b'RUN echo unexpected\n'),
        ('activation_document_copy_refused', b'COPY activation.json /opt/ocean/activation.json\n'),
        ('private_config_copy_refused', b'COPY catalogue.json /opt/ocean/catalogue-config/catalogue.json\n'),
        ('credential_env_refused', b'ENV GOOGLE_APPLICATION_CREDENTIALS=/tmp/key.json\n'),
    ]:
        check(name, lambda extra=extra: package.validate_dockerfile(dockerfile + extra), rejects=True)
    check('writable_source_mode_refused', lambda: package.validate_dockerfile(
        dockerfile.replace(b'--chmod=0444', b'--chmod=0644', 1)), rejects=True)
    modified = json.loads(base)
    modified['sources']['config.py'] = '0' * 64
    check('alteredbasepins_refused', lambda: package.validate_base_manifest(json.dumps(modified).encode()), rejects=True)
    check('basecommit_mismatch_refused', lambda: package.validate_base_manifest(
        json.dumps({**document, 'revision': '0' * 40}).encode()), rejects=True)
    check('foreign_base_project_refused', lambda: package.validate_base_manifest(
        json.dumps({**document, 'project_id': 'data-infra-infobio'}).encode()), rejects=True)
    check('checkout_path_escape_refused', lambda: package.committed_bytes(package.BASE_REVISION, '../config.py'), rejects=True)
    pins = {**document['sources'], **{name: '0' * 64 for name in package.ADDED}}
    package.validate_closure(pins)
    CHECKS.append('current_static_import_closure_present_in_base_or_overlay')
    activation_id, child_id = 'a' * 64, 'b' * 64
    registration_id = 'offline-test-registration'
    activation = {
        'version': 'ocean-v1-catalogue-activation-v1', 'project_id': package.PROJECT,
        'site_id': 'v1:' + package.PROJECT, 'policy_revision': 'offline-test-v1',
        'authorization_ref': 'chat-20261102-all-eligible-existing-data',
        'access': {'roles': ['admin'], 'account_types': ['internal']},
        'scientific_mode': 'datasets_only', 'scientific_approval': False, 'research_enabled': False,
        'snapshots': [{'descriptor': {'snapshot_id': activation_id,
            'label': {'en': 'Offline metadata test only', 'ja': 'Offline metadata test only'}},
            'registration': {'snapshot_id': activation_id, 'child_snapshot_ids': [child_id],
                'registration_id': registration_id,
                'references': [['c14:dependency:' + hashlib.sha256(renderer.wire([
                    registration_id, activation_id, item])).hexdigest(), item]
                    for item in [activation_id, child_id]]},
            'datasets': [{'dataset_id': 'offline-test-dataset', 'source_id': 'offline-test-source',
                'source_family': 'ctd', 'snapshot_id': child_id}]}],
        'qualifications': ['Synthetic metadata boundary probe only; no dataset rows or scientific approval.'],
    }
    def validate(value):
        data = renderer.canonical(value)
        return renderer.validate_activation(data, expected_sha256=hashlib.sha256(data).hexdigest())
    check('bounded_metadata_activation_valid', lambda: validate(activation))
    check('current_explicit_user_authorization_valid', lambda: validate({**activation,
        'authorization_ref': 'chat-20261103-all-beta-deployment-and-scientific-data'}))
    check('unrecognized_authorization_ref_refused', lambda: validate({**activation,
        'authorization_ref': 'unrecognized-authorization'}), rejects=True)
    for name, key, value in [
        ('scientific_approval_claim_refused', 'scientific_approval', True),
        ('research_enablement_refused', 'research_enabled', True),
        ('broader_role_policy_refused', 'access', {'roles': ['admin', 'researcher'], 'account_types': ['internal']}),
        ('foreign_activation_project_refused', 'project_id', 'data-infra-infobio'),
        ('activation_secret_field_refused', 'token', 'offline-test-not-a-token'),
    ]:
        mutated = copy.deepcopy(activation)
        mutated[key] = value
        check(name, lambda mutated=mutated: validate(mutated), rejects=True)
    mutated = copy.deepcopy(activation)
    mutated['snapshots'][0]['datasets'][0]['rows'] = []
    check('dataset_rows_refused', lambda: validate(mutated), rejects=True)
    mutated = copy.deepcopy(activation)
    mutated['snapshots'][0]['registration']['references'][0][0] = 'c14:dependency:' + '0' * 64
    check('registration_reference_forgery_refused', lambda: validate(mutated), rejects=True)
    check('activation_hash_mismatch_refused', lambda: renderer.validate_activation(
        renderer.canonical(activation), expected_sha256='0' * 64), rejects=True)
    binding = renderer.binding_document(activation_id)
    def validate_binding(value):
        data = renderer.canonical(value)
        return package.validate_binding(data, expected_sha256=hashlib.sha256(data).hexdigest(),
            activation_sha256=activation_id)
    check('opaque_binding_valid', lambda: validate_binding(binding))
    for name, key, value in [
        ('foreign_binding_bucket_refused', 'bucket', 'data-infra-infobio-ocean-data'),
        ('binding_object_hash_mismatch_refused', 'activation_object', 'v1/catalogue/activations/' + '0' * 64 + '.json'),
        ('binding_object_prefix_refused', 'activation_object', 'raw/' + activation_id + '.json'),
        ('binding_private_dataset_ids_refused', 'datasets', [{'dataset_id': 'offline-test-dataset'}]),
        ('binding_activation_document_refused', 'activation', activation),
    ]:
        mutated = {**binding, key: value}
        check(name, lambda mutated=mutated: validate_binding(mutated), rejects=True)
    with tempfile.TemporaryDirectory(prefix='ocean-beta-snapshot-package-', dir='/private/tmp') as directory:
        private = Path(directory)
        selected, target = private / 'selected.json', private / 'binding.json'
        activation_data = renderer.canonical(activation)
        selected.write_bytes(activation_data)
        selected.chmod(0o600)
        activation_hash = hashlib.sha256(activation_data).hexdigest()
        result = renderer.render(activation=selected, activation_sha256=activation_hash, output=target)
        generated = json.loads(target.read_bytes())
        assert set(generated) == {'version', 'project_id', 'site_id', 'bucket', 'prefix',
            'activation_object', 'activation_sha256'}
        assert target.stat().st_mode & 0o777 == 0o600
        assert 'offline-test-dataset' not in target.read_text() and 'offline-test-source' not in target.read_text()
        package.read_binding(target, expected_sha256=result['binding_sha256'], activation_sha256=activation_hash)
        CHECKS.append('selected_private_activation_renders_only_hash_binding0600')
        link = private / 'link.json'
        link.symlink_to(target)
        check('symlink_binding_refused', lambda: package.read_binding(link,
            expected_sha256=result['binding_sha256'], activation_sha256=activation_hash), rejects=True)
        selected.chmod(0o644)
        check('public_activation_input_refused', lambda: renderer.read_activation(selected,
            expected_sha256=activation_hash), rejects=True)
    print(json.dumps({'state': 'snapshot_packaging_boundary_checks_passed', 'count': len(CHECKS),
        'checks': CHECKS, 'cloud_calls': False, 'real_runtime_authority_or_data_read': False,
        'synthetic_metadata_only_projection_test': True}, indent=2))


if __name__ == '__main__':
    main()
