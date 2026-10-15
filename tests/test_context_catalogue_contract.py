"""C08 wire, scientific meaning and local pagination-binding contract checks."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from orchestration.publication_scope import ScopeCompatibility, ScopeEvidence
from retrieval.source_scope import ALIASES, EvidenceScope
from schema.context_catalogue import (
    CatalogueCount, CatalogueListing, CatalogueNode, DATASET_SECTIONS, EDNADescriptor,
    ListingRequest, OperationReceipt, OperationRequest, QueryResult, ROOTS,
    SCHEMA_VERSION, TransferOrigin, canonical_source_family, cursor_context,
    make_cursor, validate_cursor,
)

ROOT = Path(__file__).resolve().parents[1]


def scope(family=None):
    return {'version': 1, 'sources': {
        name: {'enabled': family is None or name == family, 'filters': {}}
        for name in ('ctd', 'metagenome', 'remote_sensing', 'edna_metabarcoding')
    }}


def descriptor(family):
    return {
        'ctd': {'family': 'ctd', 'sampling_contract': 'One retained cast/depth observation',
                'observation_entity': 'depth_observation', 'measurement': 'temperature',
                'unit': 'degC', 'depth_unit': 'dbar'},
        'remote_sensing': {'family': 'remote_sensing', 'product_id': 'synthetic-mur',
                           'product_version': 'v1', 'spatial_resolution': 0.01,
                           'spatial_resolution_unit': 'degree', 'temporal_resolution': 'daily',
                           'measurement': 'sea_surface_temperature', 'unit': 'K', 'spatial_role': 'native_grid'},
        'metagenome': {'family': 'metagenome', 'measurement': 'relative_abundance',
                       'abundance_unit': 'proportion', 'abundance_denominator': 'all retained classified reads',
                       'method': 'synthetic-taxonomy-v1', 'taxonomic_rank': 'genus',
                       'omitted_taxa': 'unknown'},
        'edna_metabarcoding': {'family': 'edna_metabarcoding', 'protocol_id': 'synthetic-mifish',
                               'protocol': 'Synthetic MiFish sequencing protocol',
                               'assignment_method': 'qcauto_target', 'sample_kind': 'environmental',
                               'is_control': False, 'measurement': 'assigned_reads', 'unit': 'reads'},
    }[family]


def node(family='ctd', identity='dataset:synthetic-001'):
    return {
        'schema_version': SCHEMA_VERSION, 'snapshot_id': 'snapshot:synthetic-v1',
        'scope': scope(family), 'id': identity, 'kind': 'dataset', 'root': 'data',
        'parent_id': 'root:data', 'title': {'en': 'Synthetic dataset', 'ja': '合成データセット'},
        'purpose': {'en': 'Contract acceptance fixture', 'ja': '契約の受入用フィクスチャ'},
        'availability': {'status': 'available'}, 'authority': 'descriptive',
        'lifecycle': {'ingestion': 'complete', 'publication': 'unpublished',
                      'scientific_approval': 'not_reviewed', 'query_readiness': 'ready',
                      'embedding_readiness': 'not_ready'},
        'provenance': {'source_generation': 'synthetic-generation-v1', 'content_sha256': 'a' * 64},
        'source_family': family, 'descriptor': descriptor(family), 'sections': list(DATASET_SECTIONS),
    }


def request(**overrides):
    return ListingRequest.model_validate({
        'snapshot_id': 'snapshot:synthetic-v1', 'scope': scope(),
        'access_revision': 'access:1', 'access_binding': 'principal:researcher-001',
        **overrides,
    })


def listing(**overrides):
    return {
        'request': request().model_dump(mode='json'), 'items': [node()],
        'total': {'state': 'known', 'entity': 'canonical_objects', 'denominator': 'all permitted qualifying canonical descendants', 'value': 1},
        'returned_count': 1, 'next_cursor': None, 'preview_truncated': False,
        'source_completeness': 'partial', 'query_completion': 'complete',
        'availability': {'status': 'available'}, **overrides,
    }


def receipt(**overrides):
    return {
        'snapshot_id': 'snapshot:synthetic-v1', 'scope': scope('ctd'), 'receipt_id': 'receipt:synthetic-001',
        'operation_id': 'operation:table', 'operation_version': 'v1',
        'inputs': [{'object_id': 'dataset:synthetic-001', 'content_sha256': 'a' * 64,
                    'source_generation': 'synthetic-generation-v1'}],
        'parameters': {'include_controls': False, 'limit': 1}, 'authority': 'descriptive',
        'availability': {'status': 'available'}, 'provenance': {'content_sha256': 'b' * 64},
        'total_rows': {'state': 'known', 'entity': 'observations', 'denominator': 'all retained cast observations in exact source scope', 'value': 1},
        'returned_count': 1, 'preview_truncated': False, 'source_completeness': 'partial',
        'query_completion': 'complete', 'content_sha256': 'c' * 64, **overrides,
    }


@pytest.mark.parametrize('family', ['ctd', 'metagenome', 'remote_sensing', 'edna_metabarcoding'])
def test_source_scientific_descriptors_and_six_sections(family):
    value = CatalogueNode.model_validate(node(family))
    assert value.id == 'dataset:synthetic-001'
    assert value.descriptor.family == family
    assert value.scope.canonical() == EvidenceScope.model_validate(scope(family)).canonical()
    assert value.sections == list(DATASET_SECTIONS)
    # Structured query readiness is independent of embeddings and publication.
    assert value.lifecycle.query_readiness == 'ready'
    assert value.lifecycle.embedding_readiness == 'not_ready'
    assert value.lifecycle.publication == 'unpublished'
    assert value.lifecycle.scientific_approval == 'not_reviewed'
    assert CatalogueNode.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize('root', ROOTS)
def test_fixed_roots_have_canonical_identity_independent_of_names(root):
    value = node()
    value.update(id=f'root:{root}', kind='root', root=root, parent_id=None, source_family=None, descriptor=None, sections=[])
    first = CatalogueNode.model_validate(value)
    value['title'] = {'en': 'Renamed', 'ja': '名称変更'}
    second = CatalogueNode.model_validate(value)
    assert first.id == second.id == f'root:{root}'


@pytest.mark.parametrize('alias,canonical', sorted(ALIASES.items()))
def test_legacy_source_aliases_preserved_in_explicit_adapter(alias, canonical):
    assert canonical_source_family(alias.upper()) == canonical


@pytest.mark.parametrize('value', ['new_source', '', None, True, 1])
def test_unregistered_source_aliases_are_not_inferred(value):
    with pytest.raises(ValueError):
        canonical_source_family(value)


@pytest.mark.parametrize('patch', [
    {'extra': True}, {'schema_version': 'context-catalogue-v2'}, {'id': 'path/to/item'},
    {'id': ''}, {'id': 1}, {'parent_id': None}, {'parent_id': 'dataset:synthetic-001'},
    {'related_ids': ['dataset:synthetic-001']}, {'related_ids': ['other:1', 'other:1']},
    {'sections': ['overview']}, {'sections': list(reversed(DATASET_SECTIONS))},
    {'descriptor': None}, {'source_family': None}, {'root': 'analyses'},
    {'source_family': 'sst'}, {'source_family': 'remote_sensing'},
    {'title': {'en': 'One language'}}, {'title': {'en': ' ', 'ja': '有'}},
    {'availability': {'status': 'unknown'}}, {'authority': 'published'},
    {'membership': 'private'}, {'owner_id': 'principal:1'},
])
def test_nodes_reject_ambiguous_or_contradictory_identity_and_scientific_fields(patch):
    value = node()
    value.update(patch)
    with pytest.raises(ValidationError):
        CatalogueNode.model_validate(value)


def test_experiments_do_not_implicitly_become_global_published_analyses():
    value = node()
    value.update(root='analyses', kind='analysis', descriptor=None, sections=[], authority='experimental')
    with pytest.raises(ValidationError, match='Experimental'):
        CatalogueNode.model_validate(value)
    value.update(membership='private', owner_id='principal:researcher-001')
    result = CatalogueNode.model_validate(value)
    assert result.authority == 'experimental'
    assert result.lifecycle.scientific_approval == 'not_reviewed'
    assert result.lifecycle.publication == 'unpublished'


@pytest.mark.parametrize('kind,control,valid', [
    ('environmental', False, True), ('environmental', True, False), ('environmental', None, False),
    ('negative_control', True, True), ('negative_control', False, False), ('negative_control', None, False),
    ('positive_control', True, True), ('mock_community', True, True), ('unknown', None, True),
    ('unknown', False, True), ('unknown', True, True), ('unknown', 'false', False), ('unknown', 0, False),
])
def test_edna_protocol_controls_preserve_explicit_unknown(kind, control, valid):
    value = {**descriptor('edna_metabarcoding'), 'sample_kind': kind, 'is_control': control}
    if valid:
        assert EDNADescriptor.model_validate(value).is_control is control
    else:
        with pytest.raises(ValidationError):
            EDNADescriptor.model_validate(value)


@pytest.mark.parametrize('value', [True, False, '1', -1, 0.5, float('nan'), float('inf'), 9007199254740992])
def test_counts_reject_boolean_fractional_negative_nonfinite_or_unsafe_values(value):
    with pytest.raises(ValidationError):
        CatalogueCount(state='known', entity='datasets', denominator='all qualifying datasets', value=value)


@pytest.mark.parametrize('value', [0, 1, 1.0, 100000, 9007199254740991])
def test_exact_counts_are_global_and_json_safe(value):
    count = CatalogueCount(state='known', entity='datasets', denominator='all qualifying datasets', value=value)
    assert type(count.value) is int
    assert count.basis == 'complete_scope'


@pytest.mark.parametrize('patch', [
    {'state': 'known', 'value': None}, {'state': 'unknown', 'value': 0},
    {'state': 'unknown', 'value': None}, {'denominator': ''}, {'basis': 'displayed_page'},
    {'entity': 'samples_without_definition'},
])
def test_unknown_never_becomes_zero_and_counts_require_entity_denominator(patch):
    value = {'state': 'known', 'entity': 'datasets', 'denominator': 'all qualifying dataset identities', 'value': 0, **patch}
    with pytest.raises(ValidationError):
        CatalogueCount.model_validate(value)


def test_unknown_available_coverage_differs_from_unavailable_or_zero():
    unknown = CatalogueCount(state='unknown', entity='observations', denominator='expected observations in exact source scope', reason='Source inventory not reconciled')
    assert unknown.value is None
    zero = CatalogueListing.model_validate(listing(items=[], returned_count=0, total={'state': 'known', 'entity': 'canonical_objects', 'denominator': 'all permitted qualifying descendants', 'value': 0}))
    assert zero.total.value == 0
    unavailable = CatalogueListing.model_validate(listing(items=[], returned_count=0, total={'state': 'unknown', 'entity': 'canonical_objects', 'denominator': 'all permitted qualifying descendants', 'reason': 'Snapshot unavailable'}, availability={'status': 'unavailable', 'reason': 'Snapshot unavailable'}, query_completion='failed'))
    assert unavailable.total.value is None
    assert unavailable.availability.status == 'unavailable'


@pytest.mark.parametrize('family,field,value', [
    ('ctd', 'time_from', '2026-02-30'), ('ctd', 'time_to', 'not-a-date'),
    ('ctd', 'time_from', '2026-01-01T12'), ('ctd', 'time_from', '2026-01-01 12:00:00'),
    ('ctd', 'time_from', '2026-01-01T12:00:00+00:99'),
    ('ctd', 'time_from', '2026-01-01T12:00:00.1234567Z'),
    ('ctd', 'station', True), ('ctd', 'station', ' station:1 '), ('ctd', 'bay', ' O '),
    ('remote_sensing', 'lat_min', True), ('remote_sensing', 'lat_min', '1.5'),
    ('remote_sensing', 'lat_min', 91), ('remote_sensing', 'lon_max', -181),
    ('remote_sensing', 'lat_min', float('inf')), ('remote_sensing', 'lat_min', float('nan')),
    ('edna_metabarcoding', 'is_control', 0), ('edna_metabarcoding', 'assignment_method', 'guessed'),
    ('ctd', 'assignment_method', 'qcauto_target'),
])
def test_existing_source_scope_reused_behind_strict_catalogue_wire_boundary(family, field, value):
    selected = scope(family)
    selected['sources'][family]['filters'][field] = value
    with pytest.raises(ValidationError):
        request(scope=selected)


@pytest.mark.parametrize('value', [None, [], True, 'not-an-object'])
def test_malformed_scope_containers_return_validation_errors(value):
    selected = scope()
    selected['sources'] = value
    with pytest.raises(ValidationError):
        request(scope=selected)
    selected = scope()
    selected['sources']['ctd']['filters'] = value
    with pytest.raises(ValidationError):
        request(scope=selected)


def test_date_and_coordinate_boundaries_reuse_source_scope_semantics():
    selected = scope('remote_sensing')
    selected['sources']['remote_sensing']['filters'] = {
        'time_from': '2026-01-01T00:00:00.123456Z', 'time_to': '2026-01-01T09:00:00.123456+09:00',
        'lat_min': -90, 'lat_max': 90, 'lon_min': -180, 'lon_max': 180,
    }
    parsed = request(scope=selected)
    assert parsed.scope.canonical() == EvidenceScope.model_validate(selected).canonical()
    bad = deepcopy(selected)
    bad['sources']['remote_sensing']['filters']['lat_min'] = 91
    with pytest.raises(ValidationError):
        request(scope=bad)
    bad = deepcopy(selected)
    bad['sources']['remote_sensing']['filters']['time_to'] = '2025-12-31'
    with pytest.raises(ValidationError):
        request(scope=bad)


def test_integral_coordinate_cursor_binding_is_stable_across_json_number_spelling():
    one = scope('remote_sensing')
    one['sources']['remote_sensing']['filters']['lat_min'] = 1
    two = deepcopy(one)
    two['sources']['remote_sensing']['filters']['lat_min'] = 1.0
    assert cursor_context(request(scope=one)) == cursor_context(request(scope=two))
    assert request(scope={**scope(), 'version': 1.0}).scope.version == 1
    with pytest.raises(ValidationError):
        EvidenceScope.model_validate({**scope(), 'version': 1.0})


@pytest.mark.parametrize('patch', [
    {'snapshot_id': 'snapshot:other'}, {'access_revision': 'access:2'},
    {'access_binding': 'principal:other'}, {'limit': 99}, {'parent_id': 'root:data'},
    {'filters': {'search': 'renamed'}}, {'filters': {'roots': ['metadata']}},
    {'ordering': [{'field': 'id', 'direction': 'desc'}]}, {'scope': scope('ctd')},
])
def test_cursor_rejects_stale_snapshot_scope_order_filter_or_access_context(patch):
    first = request()
    token = make_cursor(first, 100)
    assert validate_cursor(first, token) == 100
    assert validate_cursor(request(cursor=token)) == 100
    with pytest.raises(ValidationError, match='cursor'):
        request(cursor=token, **patch)


@pytest.mark.parametrize('token', ['', 'not_base64!', 'W10', 'bnVsbA', 'e30', 'x' * 2049])
def test_malformed_cursors_fail_closed(token):
    with pytest.raises((ValidationError, ValueError)):
        request(cursor=token)


@pytest.mark.parametrize('offset', [True, False, '1', 0, -1, 1.5, float('inf'), 9007199254740992])
def test_cursor_offsets_are_positive_safe_integer_numbers(offset):
    with pytest.raises(ValueError):
        make_cursor(request(), offset)


@pytest.mark.parametrize('ordering', [[], [{'field': 'title'}], [{'field': 'id'}, {'field': 'id'}], [{'field': 'rank'}]])
def test_listing_order_always_has_canonical_identity_tiebreaker(ordering):
    with pytest.raises(ValidationError):
        request(ordering=ordering)


@pytest.mark.parametrize('patch', [
    {'returned_count': 0}, {'returned_count': True}, {'items': [node(), node()], 'returned_count': 2},
    {'total': {'state': 'known', 'entity': 'datasets', 'denominator': 'all objects', 'value': 1}},
    {'total': {'state': 'known', 'entity': 'canonical_objects', 'denominator': 'all objects', 'value': 0}},
    {'preview_truncated': True},
    {'availability': {'status': 'unavailable', 'reason': 'Source unavailable'}},
])
def test_listing_counts_duplicates_truncation_and_unavailable_states_reconcile(patch):
    with pytest.raises(ValidationError):
        CatalogueListing.model_validate(listing(**patch))


def test_page_preview_source_and_query_completion_are_independent():
    first = request(limit=1)
    value = CatalogueListing.model_validate(listing(
        request=first.model_dump(mode='json'), next_cursor=make_cursor(first, 1), preview_truncated=True,
        total={'state': 'known', 'entity': 'canonical_objects', 'denominator': 'all permitted canonical descendants', 'value': 100000},
    ))
    assert value.source_completeness == 'partial'
    assert value.query_completion == 'complete'
    assert value.preview_truncated is True
    assert value.total.value == 100000
    bad = value.model_dump(mode='json')
    bad['next_cursor'] = make_cursor(first, 2)
    with pytest.raises(ValidationError, match='continue immediately'):
        CatalogueListing.model_validate(bad)


def test_transfer_provenance_retains_origin_without_granting_live_dependency():
    value = {'origin_system': 'legacy-ocean', 'origin_object_id': 'original/source/object',
             'source_snapshot_id': 'snapshot:legacy-frozen', 'source_generation': 'generation-001',
             'schema_version': 'legacy-v1', 'operation_version': 'export-v1', 'content_sha256': 'a' * 64,
             'scientific_qualification': 'Published; independent scientific approval remains unknown',
             'access_conditions': 'Synthetic imported copy only', 'transfer_authorization_ref': 'approval:synthetic-001'}
    parsed = TransferOrigin.model_validate(value)
    assert parsed.origin_object_id == 'original/source/object'
    assert parsed.live_dependency is False
    for dependency in (True, 0, 1, 'false'):
        with pytest.raises(ValidationError):
            TransferOrigin.model_validate({**value, 'live_dependency': dependency})


def test_operation_request_preserves_input_identity_scope_and_parameters_without_authorizing_science():
    value = {'snapshot_id': 'snapshot:synthetic-v1', 'scope': scope('ctd'), 'operation_id': 'operation:table',
             'operation_version': 'v1', 'input_ids': ['dataset:synthetic-001'],
             'parameters': {'include_controls': False, 'threshold': -1.5},
             'access_revision': 'access:1', 'access_binding': 'principal:researcher-001'}
    parsed = OperationRequest.model_validate(value)
    assert parsed.model_dump(mode='json')['parameters'] == value['parameters']
    for patch in ({'input_ids': ['same', 'same']}, {'parameters': {'threshold': float('nan')}}, {'scope_compatibility': {'outcome': 'compatible'}}):
        with pytest.raises(ValidationError):
            OperationRequest.model_validate({**value, **patch})


def test_query_receipt_retains_c01_contract_and_original_content_identity():
    compatibility = ScopeCompatibility('compatible', 'All registered scope matches', 'published_synthesis', 'a' * 64,
                                       (ScopeEvidence('source', 'compatible', 'ctd', 'ctd', 'ctd', 'selection', 'Registered selection'),))
    output = receipt(scope_compatibility=compatibility.as_dict())
    parsed = OperationReceipt.model_validate(output)
    assert parsed.scope_compatibility == compatibility
    assert parsed.scope_compatibility.as_dict() == compatibility.as_dict()
    query = QueryResult.model_validate({'snapshot_id': output['snapshot_id'], 'scope': output['scope'],
                                      'columns': [{'key': 'temperature', 'title': {'en': 'Temperature', 'ja': '温度'}, 'unit': 'degC'}],
                                      'rows': [{'temperature': -1.5}], 'receipt': output})
    assert query.rows == [{'temperature': -1.5}]
    assert query.receipt.inputs[0].content_sha256 == 'a' * 64
    assert query.receipt.inputs[0].source_generation == 'synthetic-generation-v1'
    assert QueryResult.model_validate_json(query.model_dump_json()) == query


@pytest.mark.parametrize('outcome', ['incompatible', 'unresolved'])
def test_query_readiness_does_not_override_c01_scope_rejection(outcome):
    compatibility = ScopeCompatibility(outcome, 'Scope not proven', 'published_synthesis', 'a' * 64, ())
    with pytest.raises(ValidationError, match='C01'):
        OperationReceipt.model_validate(receipt(scope_compatibility=compatibility.as_dict()))
    assert OperationReceipt.model_validate(receipt(scope_compatibility=compatibility.as_dict(), query_completion='failed')).scope_compatibility.outcome == outcome


@pytest.mark.parametrize('patch', [
    {'returned_count': 2}, {'preview_truncated': True},
    {'scope_compatibility': {'version': 'publication-scope-v2', 'outcome': 'compatible'}},
    {'parameters': {'threshold': float('inf')}},
])
def test_receipt_rejects_inconsistent_or_nonfinite_metadata(patch):
    with pytest.raises(ValidationError):
        OperationReceipt.model_validate(receipt(**patch))


def test_query_result_rows_cannot_lose_metadata_or_change_scope():
    base = {'snapshot_id': 'snapshot:synthetic-v1', 'scope': scope('ctd'),
            'columns': [{'key': 'temperature', 'title': {'en': 'Temperature', 'ja': '温度'}, 'unit': 'degC'}],
            'rows': [{'temperature': -1.5}], 'receipt': receipt()}
    for patch in ({'snapshot_id': 'snapshot:other'}, {'scope': scope()}, {'rows': []},
                  {'rows': [{'other': -1.5}]}, {'rows': [{'temperature': float('nan')}]},
                  {'columns': base['columns'] * 2}):
        with pytest.raises(ValidationError):
            QueryResult.model_validate({**base, **patch})


def test_combined_json_schema_is_deterministic_current_and_closed():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/export_context_catalogue.py'), '--check'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    generated = json.loads((ROOT / 'schema/context_catalogue.v1.schema.json').read_text())
    assert generated['$schema'] == 'https://json-schema.org/draft/2020-12/schema'
    assert generated['x-source-aliases'] == ALIASES
    assert generated['x-dataset-sections'] == list(DATASET_SECTIONS)
    assert generated['$defs']['CatalogueNode']['additionalProperties'] is False
    assert generated['$defs']['ScopeCompatibility']['additionalProperties'] is False
    assert 'version' in generated['$defs']['ScopeCompatibility']['required']


def test_private_experiment_is_retained_for_workspace_but_excluded_from_global_listing():
    private = node()
    private.update(id='experiment:private-1', root='analyses', kind='analysis', sections=[], descriptor=None,
                   authority='experimental', membership='private', owner_id='principal:researcher-001')
    assert CatalogueNode.model_validate(private).membership == 'private'
    with pytest.raises(ValidationError, match='not global'):
        CatalogueListing.model_validate(listing(items=[private]))


def test_listing_validates_declared_direction_and_title_id_tiebreaker():
    first, second = node(identity='dataset:001'), node(identity='dataset:002')
    value = listing(items=[second, first], returned_count=2,
                    total={'state': 'known', 'entity': 'canonical_objects', 'denominator': 'all qualifying canonical descendants', 'value': 2})
    with pytest.raises(ValidationError, match='ordering'):
        CatalogueListing.model_validate(value)
    value['request'] = request(ordering=[{'field': 'id', 'direction': 'desc'}]).model_dump(mode='json')
    assert CatalogueListing.model_validate(value).items[0].id == 'dataset:002'
    value['request'] = request(ordering=[{'field': 'title', 'direction': 'asc'}, {'field': 'id', 'direction': 'asc'}]).model_dump(mode='json')
    with pytest.raises(ValidationError, match='ordering'):
        CatalogueListing.model_validate(value)
    second['title']['en'] = 'A title that sorts first'
    assert CatalogueListing.model_validate(value).items[0].id == 'dataset:002'


def test_wire_parameters_reject_cyclic_or_excessively_nested_producer_values():
    cycle = {}
    cycle['cycle'] = cycle
    with pytest.raises(ValidationError, match='Cyclic'):
        OperationReceipt.model_validate(receipt(parameters=cycle))
    deep = {}
    for _ in range(129):
        deep = {'child': deep}
    with pytest.raises(ValidationError, match='depth'):
        OperationReceipt.model_validate(receipt(parameters=deep))
    child = {'threshold': 1}
    assert OperationReceipt.model_validate(receipt(parameters={'left': child, 'right': child})).parameters['left'] == child


def test_schema_uses_standard_integer_bounds_and_factory_defaults():
    generated = json.loads((ROOT / 'schema/context_catalogue.v1.schema.json').read_text())
    count = generated['$defs']['CatalogueCount']['properties']['value']['anyOf'][0]
    assert count['minimum'] == 0
    assert count['maximum'] == 9007199254740991
    assert 'ge' not in count and 'le' not in count
    limit = generated['$defs']['ListingRequest']['properties']['limit']
    assert limit['minimum'] == 1 and limit['maximum'] == 500
    assert generated['$defs']['ListingRequest']['properties']['filters']['default'] == {
        'roots': [], 'source_families': [], 'kinds': [], 'search': None, 'authorities': [],
    }
    assert generated['$defs']['ListingRequest']['properties']['ordering']['default'] == [{'field': 'id', 'direction': 'asc'}]
