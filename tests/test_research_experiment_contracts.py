"""C22 adversarial pure DTO/canonical contracts; synthetic values, never execution."""
from copy import deepcopy
import hashlib
import json

import pytest
from pydantic import ValidationError

from schema.research_experiments import (
    EXPERIMENT_REQUEST_MODELS, EXPERIMENT_RESPONSE_MODELS, EXPERIMENT_VERSION,
    MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, EnvironmentDescriptor, ExperimentApprovalRequest,
    ExperimentApprovalSnapshot, ExperimentContextBinding, ExperimentDispatchSnapshot,
    ExperimentEventsResponse, ExperimentOperationSnapshot, ExperimentProposal,
    ExperimentResources, ExperimentResponse, ExperimentSnapshot, FrozenCohortSpec,
    content_sha256,
)

U = '00000000-0000-0000-0000-000000000001'
V = '00000000-0000-0000-0000-000000000002'
BINDING = {'investigation_id': U, 'conversation_id': V, 'context_revision_id': U,
           'snapshot_id': 'a' * 64, 'context_payload_sha256': 'b' * 64}


def environment():
    return EnvironmentDescriptor(kind='c22-fake', test_only=True, python_version='not-executed',
        description='Synthetic contract descriptor; no Python environment is claimed')


def real_descriptor():
    # Schema fixture only: these synthetic digests do not claim a deployed image.
    return {'kind': 'linux-gvisor', 'test_only': False, 'python_version': '3.12.7',
        'image_digest': 'sha256:' + 'a' * 64, 'lockfile_sha256': 'b' * 64,
        'packages': {'numpy': '2.1.3', 'pandas': '2.2.3', 'pyarrow': '18.1.0',
                     'scipy': '1.14.1', 'statsmodels': '0.14.4', 'matplotlib': '3.9.2'},
        'description': 'Synthetic schema fixture; not provisioned or approved'}


def proposal():
    return {'question': 'Describe temperature in this exact frozen cohort / 水温',
        'cohort': {'selections': [{'kind': 'dataset', 'target_id': 'dataset:ctd',
                                 'table': 'measurements', 'columns': ['temperature']}]},
        'method': 'Descriptive mean of retained measurements, no causal inference',
        'assumptions': ['Missing measurements remain missing'], 'python_code': 'result = 1\n',
        'expected_outputs': [{'name': 'summary.csv', 'kind': 'table', 'description': 'Descriptive summary only'}],
        'environment_id': environment().identity_sha256,
        'limitations': ['Synthetic contract values, no scientific approval'], 'seeds': {'numpy': 42}}


def snapshot():
    parsed = ExperimentProposal.model_validate(proposal()).model_dump(mode='json')
    manifest = {'version': 'test-only-manifest', 'files': [{'name': 'ctd.json', 'sha256': 'c' * 64}],
                'qualifications': ['Complete-cohort export is verified by a separate actual exporter gate']}
    return {'id': U, 'binding': dict(BINDING), 'version': 1, 'proposal_revision_id': V,
        'proposal': parsed, 'manifest': manifest, 'environment': environment().model_dump(mode='json'),
        'hashes': {'proposal_sha256': content_sha256(parsed),
                   'code_sha256': hashlib.sha256(parsed['python_code'].encode()).hexdigest(),
                   'input_manifest_sha256': content_sha256(manifest),
                   'environment_sha256': environment().identity_sha256,
                   'resources_sha256': content_sha256(parsed['resources'])},
        'approval': {'status': 'none', 'proposal_revision_id': None, 'approved_at': None},
        'dispatch': {'eligible': False, 'reason': 'Approval required', 'reservation_id': None,
                     'status': 'unavailable'},
        'event_cursor': 0, 'latest_event_cursor': 2, 'authority': 'experimental',
        'scientific_approval': 'not_independently_verified', 'execution_performed': False}


def requests():
    approval = {**BINDING, 'experiment_id': U, 'expected_version': 1, 'expected_proposal_revision_id': V,
                'expected_hashes': snapshot()['hashes'], 'idempotency_key': V}
    create = {**BINDING, 'proposal': proposal(), 'idempotency_key': U}
    return {'create': create, 'revise': {**create, 'experiment_id': U, 'expected_version': 1,
                                       'expected_proposal_revision_id': V},
            'get': {'experiment_id': U, 'proposal_revision_id': V},
            'status': {'experiment_id': U}, 'approve': approval, 'dispatch': deepcopy(approval),
            'list': {'investigation_id': U, 'conversation_id': V, 'limit': 25, 'after_id': U},
            'events': {'experiment_id': U, 'after_cursor': 0, 'limit': 100},
            'retry': {'operation_id': U}}


def event_page():
    return {'version': EXPERIMENT_VERSION, 'experiment_id': U, 'after_cursor': 0,
        'items': [{'cursor': 1, 'kind': 'proposal_ready',
                   'summary': {'en': 'Proposal retained', 'ja': '提案を保存しました'}}],
        'next_cursor': 1, 'latest_event_cursor': 2, 'has_more': True}


def test_all_nine_actions_have_explicit_strict_request_and_response_models():
    assert set(EXPERIMENT_REQUEST_MODELS) == set(requests()) == set(EXPERIMENT_RESPONSE_MODELS)
    for name, data in requests().items():
        assert EXPERIMENT_REQUEST_MODELS[name].model_validate(data)
        with pytest.raises(ValidationError):
            EXPERIMENT_REQUEST_MODELS[name].model_validate({**data, 'owner_id': U})


@pytest.mark.parametrize('field,value', [('user_id', U), ('role', 'admin'), ('authority', 'published'),
    ('scientific_approval', True), ('publication_witness', {}), ('environment', real_descriptor()),
    ('executor', 'host-python'), ('scope', {}), ('approved', True), ('reservation_id', U)])
def test_public_create_cannot_supply_trusted_ownership_eligibility_or_execution_authority(field, value):
    with pytest.raises(ValidationError):
        EXPERIMENT_REQUEST_MODELS['create'].model_validate({**requests()['create'], field: value})


@pytest.mark.parametrize('field', list(BINDING))
@pytest.mark.parametrize('value', [True, '', '../other', 'not-a-retained-identity'])
def test_context_binding_has_five_explicit_hash_or_uuid_fields(field, value):
    data = dict(BINDING)
    data[field] = value
    with pytest.raises(ValidationError):
        ExperimentContextBinding.model_validate(data)


@pytest.mark.parametrize('field', ['proposal_sha256', 'code_sha256', 'input_manifest_sha256',
                                  'environment_sha256', 'resources_sha256'])
def test_each_approval_hash_is_required_and_must_remain_an_exact_sha256(field):
    data = requests()['approve']
    del data['expected_hashes'][field]
    with pytest.raises(ValidationError):
        ExperimentApprovalRequest.model_validate(data)
    data['expected_hashes'][field] = 'invented-approval'
    with pytest.raises(ValidationError):
        ExperimentApprovalRequest.model_validate(data)


@pytest.mark.parametrize('action', ['approve', 'dispatch'])
@pytest.mark.parametrize('field', list(BINDING))
def test_approval_and_dispatch_cannot_omit_any_part_of_the_exact_context_binding(action, field):
    data = requests()[action]
    del data[field]
    with pytest.raises(ValidationError):
        EXPERIMENT_REQUEST_MODELS[action].model_validate(data)


@pytest.mark.parametrize('change', [
    lambda x: x['proposal'].update(question='Different cohort question'),
    lambda x: x['proposal'].update(python_code='result = 2\n'),
    lambda x: x['proposal']['resources'].update(wall_seconds=300),
    lambda x: x['manifest']['files'][0].update(sha256='d' * 64),
    lambda x: x['environment'].update(description='Another configured descriptor'),
    lambda x: x['proposal'].update(environment_id='e' * 64),
    *[lambda x, field=field: x['hashes'].update({field: 'f' * 64}) for field in
      ['proposal_sha256', 'code_sha256', 'input_manifest_sha256', 'environment_sha256', 'resources_sha256']],
])
def test_snapshot_rejects_each_independently_changed_proposal_code_manifest_environment_resource_identity(change):
    data = snapshot()
    change(data)
    with pytest.raises(ValidationError):
        ExperimentSnapshot.model_validate(data)


def test_new_revision_cannot_inherit_current_approval_but_retains_explicit_stale_history():
    data = snapshot()
    data['approval'] = {'status': 'current', 'proposal_revision_id': U, 'approved_at': '2026-10-21T00:00:00Z'}
    with pytest.raises(ValidationError):
        ExperimentSnapshot.model_validate(data)
    data['approval']['status'] = 'stale'
    assert ExperimentSnapshot.model_validate(data).approval.status == 'stale'


@pytest.mark.parametrize('status,revision,time', [
    ('none', U, None), ('none', None, '2026-10-21T00:00:00Z'),
    ('current', None, '2026-10-21T00:00:00Z'), ('current', U, None),
    ('stale', None, '2026-10-21T00:00:00Z'), ('stale', U, None),
])
def test_approval_status_cannot_invent_or_discard_its_retained_decision_identity(status, revision, time):
    with pytest.raises(ValidationError):
        ExperimentApprovalSnapshot(status=status, proposal_revision_id=revision, approved_at=time)


@pytest.mark.parametrize('state', [
    {'eligible': True, 'reason': 'Unavailable', 'reservation_id': None, 'status': 'unavailable'},
    {'eligible': False, 'reason': None, 'reservation_id': None, 'status': 'unavailable'},
    {'eligible': False, 'reason': 'Unavailable', 'reservation_id': U, 'status': 'unavailable'},
    {'eligible': False, 'reason': None, 'reservation_id': None, 'status': 'ready'},
    {'eligible': True, 'reason': 'Approval needed', 'reservation_id': None, 'status': 'ready'},
    {'eligible': True, 'reason': None, 'reservation_id': U, 'status': 'ready'},
    {'eligible': True, 'reason': 'Reserved', 'reservation_id': U, 'status': 'reserved'},
    {'eligible': False, 'reason': 'Uncertain', 'reservation_id': None, 'status': 'uncertain'},
    {'eligible': False, 'reason': 'Accepted', 'reservation_id': None, 'status': 'accepted'},
])
def test_dispatch_cannot_offer_new_capacity_or_lose_the_identity_of_an_existing_reservation(state):
    with pytest.raises(ValidationError):
        ExperimentDispatchSnapshot.model_validate(state)


def test_snapshot_dispatch_eligibility_requires_current_approval_for_this_revision():
    data = snapshot()
    data['dispatch'] = {'eligible': True, 'reason': None, 'reservation_id': None, 'status': 'ready'}
    with pytest.raises(ValidationError):
        ExperimentSnapshot.model_validate(data)
    data['approval'] = {'status': 'current', 'proposal_revision_id': V, 'approved_at': '2026-10-21T00:00:00Z'}
    assert ExperimentSnapshot.model_validate(data).dispatch.eligible
    # An uncertain physical acknowledgement remains a reservation, not new
    # eligibility. This DTO assertion does not claim real worker termination.
    data['dispatch'] = {'eligible': False, 'reason': 'Acknowledgement uncertain', 'reservation_id': U, 'status': 'uncertain'}
    assert ExperimentSnapshot.model_validate(data).dispatch.reservation_id == U


@pytest.mark.parametrize('field,value', [('cpus', 3), ('cpus', True), ('memory_bytes', 4 * 1024**3 + 1),
    ('memory_bytes', 1), ('wall_seconds', 601), ('wall_seconds', 0), ('wall_seconds', 1.0),
    ('max_input_bytes', MAX_INPUT_BYTES + 1), ('max_input_bytes', 0),
    ('max_output_bytes', MAX_OUTPUT_BYTES + 1), ('max_output_bytes', False)])
def test_resource_bounds_and_types_cannot_be_raised_or_coerced(field, value):
    with pytest.raises(ValidationError):
        ExperimentResources.model_validate({field: value})


def test_resource_defaults_and_narrower_explicit_limits_remain_hash_bound():
    defaults = ExperimentResources()
    assert (defaults.cpus, defaults.memory_bytes, defaults.wall_seconds,
            defaults.max_input_bytes, defaults.max_output_bytes) == (2, 4 * 1024**3, 600, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES)
    narrow = ExperimentResources(cpus=1, memory_bytes=64 * 1024**2, wall_seconds=1,
                                 max_input_bytes=1, max_output_bytes=1)
    assert content_sha256(narrow.model_dump(mode='json')) != content_sha256(defaults.model_dump(mode='json'))


@pytest.mark.parametrize('change', [
    lambda x: x['selections'][0].update(columns=['temperature', 'temperature']),
    lambda x: x['selections'].append(deepcopy(x['selections'][0])),
    lambda x: x.update(pairing={'mode': 'independent', 'relationship_ids': ['relationship:one']}),
    lambda x: x.update(pairing={'mode': 'physical_identity', 'relationship_ids': []}),
    lambda x: x.update(pairing={'mode': 'physical_identity', 'relationship_ids': ['one', 'one']}),
    lambda x: x.update(pairing={'mode': 'proximity', 'relationship_ids': ['one']}),
    lambda x: x.update(exclusions=[{'dataset_id': 'dataset:ctd', 'entity': 'physical_sample', 'ids': ['one'], 'reason': 'Ambiguous source-owned identity'}]),
    lambda x: x.update(exclusions=[{'dataset_id': 'dataset:ctd', 'entity': 'cast', 'ids': ['one', 'one'], 'reason': 'Repeated'}]),
])
def test_ambiguous_repeated_or_unqualified_cohort_pairing_and_exclusions_fail_strictly(change):
    value = deepcopy(proposal()['cohort'])
    change(value)
    with pytest.raises(ValidationError):
        FrozenCohortSpec.model_validate(value)


def test_explicit_source_entity_exclusions_and_pairing_ids_remain_literal_without_inferring_identity():
    value = deepcopy(proposal()['cohort'])
    value.update(pairing={'mode': 'physical_identity', 'relationship_ids': ['relationship:verified']},
                 exclusions=[{'dataset_id': 'dataset:ctd', 'entity': 'cast', 'ids': ['cast:one'], 'reason': 'Explicit source exclusion'}])
    parsed = FrozenCohortSpec.model_validate(value)
    assert parsed.pairing.relationship_ids == ['relationship:verified']
    assert parsed.exclusions[0].entity == 'cast'
    # Existence, C13 proof and actual FK cascade are actual exporter/service gates.


@pytest.mark.parametrize('code', ['x = (', '\x00', '\ud800', ''])
def test_python_source_requires_reviewable_finite_utf8_but_never_execution(code):
    with pytest.raises(ValidationError):
        ExperimentProposal.model_validate({**proposal(), 'python_code': code})


def test_python_execution_sentinel_is_only_parsed_and_exact_utf8_bytes_define_identity(tmp_path):
    marker = tmp_path / 'MUST_NOT_EXECUTE'
    code = f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\nraise SystemExit(9)\n# 水温 / retained source\n'
    parsed = ExperimentProposal.model_validate({**proposal(), 'python_code': code})
    assert parsed.python_code == code and not marker.exists()
    assert hashlib.sha256(code.encode()).hexdigest() != hashlib.sha256(code.replace('\n', '\r\n').encode()).hexdigest()


def test_python_multibyte_byte_bound_and_proposal_review_byte_bound_are_distinct():
    with pytest.raises(ValidationError, match='UTF-8 byte bound'):
        ExperimentProposal.model_validate({**proposal(), 'python_code': '#' + '海' * 12000})
    with pytest.raises(ValidationError, match='review byte bound'):
        ExperimentProposal.model_validate({**proposal(), 'limitations': ['x' * 4000] * 20})


@pytest.mark.parametrize('change', [lambda x: x.update(test_only=False), lambda x: x.update(python_version='3.12.7'),
    lambda x: x.update(image_digest='sha256:' + 'a' * 64), lambda x: x.update(lockfile_sha256='a' * 64),
    lambda x: x.update(packages={'numpy': '2.1.3'})])
def test_fake_environment_cannot_claim_real_execution_or_scientific_package_identity(change):
    value = environment().model_dump(mode='json')
    change(value)
    with pytest.raises(ValidationError):
        EnvironmentDescriptor.model_validate(value)


@pytest.mark.parametrize('change', [lambda x: x.update(python_version='3.x'), lambda x: x.update(python_version='3'),
    lambda x: x['packages'].update(numpy='latest'), lambda x: x['packages'].update(pandas='*'),
    lambda x: x.update(image_digest=None), lambda x: x.update(lockfile_sha256=None),
    lambda x: x['packages'].pop('scipy')])
def test_real_environment_descriptor_requires_actual_pinned_version_syntax(change):
    value = real_descriptor()
    change(value)
    with pytest.raises(ValidationError):
        EnvironmentDescriptor.model_validate(value)


def test_canonical_machine_identity_preserves_int64_unicode_null_and_original_strings():
    # Hash helper can preserve exact machine JSON bytes; public bounded DTOs do
    # not normalize or spreadsheet-escape the trusted private machine encoder.
    value = {'i': 9223372036854775807, 'negative': -9223372036854775808,
             'literal': '=1+1 / 水温', 'missing': None, 'float': 1.25}
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert b'9223372036854775807' in raw and content_sha256(value) == hashlib.sha256(raw).hexdigest()
    assert content_sha256(dict(reversed(list(value.items())))) == content_sha256(value)


@pytest.mark.parametrize('value', [0, 0.0, True, 'false'])
def test_snapshot_execution_flag_requires_literal_boolean_false(value):
    data = snapshot()
    data['execution_performed'] = value
    with pytest.raises(ValidationError):
        ExperimentSnapshot.model_validate(data)


@pytest.mark.parametrize('change', [lambda x: x.update(next_cursor=0), lambda x: x.update(has_more=False),
    lambda x: x['items'][0].update(cursor=2), lambda x: x.update(latest_event_cursor=0),
    lambda x: x.update(items=[], next_cursor=0), lambda x: x.update(after_cursor=True)])
def test_event_pages_cannot_skip_repeat_regress_or_claim_nonprogressing_more(change):
    value = event_page()
    change(value)
    with pytest.raises(ValidationError):
        ExperimentEventsResponse.model_validate(value)


def test_response_never_claims_empty_state_or_published_scientific_approval():
    with pytest.raises(ValidationError):
        ExperimentResponse(experiment=None, operation=None)
    for field, value in [('authority', 'published'), ('scientific_approval', 'approved')]:
        data = snapshot()
        data[field] = value
        with pytest.raises(ValidationError):
            ExperimentSnapshot.model_validate(data)
    valid = ExperimentResponse(experiment=ExperimentSnapshot.model_validate(snapshot()), operation=None)
    assert valid.version == EXPERIMENT_VERSION and not valid.experiment.execution_performed


def test_operation_recovery_keeps_original_identity_with_optional_host_reason():
    minimal = {'id': U, 'state': 'uncertain', 'result_revision_id': None}
    old = ExperimentOperationSnapshot.model_validate(minimal)
    assert old.id == U and old.error_code is None and old.reason is None
    safe = {**minimal, 'error_code': 'protection_uncertain',
            'reason': {'en': 'Preparation needs another check', 'ja': '準備を再確認する必要があります'}}
    parsed = ExperimentOperationSnapshot.model_validate(safe)
    assert parsed.id == U and parsed.state == 'uncertain' and parsed.reason.ja == safe['reason']['ja']
    # The versioned envelope can carry the retained operation even while a
    # first proposal has no published private revision to display yet.
    assert ExperimentResponse(experiment=None, operation=parsed).operation.id == U


@pytest.mark.parametrize('change', [
    {'error_code': {'raw_exception': 'source content'}},
    {'reason': {'en': 'Safe summary', 'ja': '\ud800'}},
    {'reason': {'en': 'Safe summary', 'ja': '安全な要約', 'raw_exception': 'private details'}},
    {'owner_id': V},
])
def test_operation_recovery_reason_cannot_expand_the_private_wire_contract(change):
    with pytest.raises(ValidationError):
        ExperimentOperationSnapshot.model_validate({'id': U, 'state': 'unavailable', 'result_revision_id': None, **change})
