"""Source selections constrain candidates, prompt evidence and retained history."""
from copy import deepcopy
from itertools import product

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api.main as api_main
import orchestration.unified as unified
from api.schemas import ChatRequest
from orchestration.evidence_scope import context_matches_source_scope
from orchestration.edna_aggregation import plan_aggregation, render_answer
from retrieval.local_retriever import LocalRetriever
from retrieval.source_scope import EvidenceScope, FAMILIES, document_matches, scope_sql
from tests.test_edna_aggregation import bundle


def scope(*enabled):
    return {'version': 1, 'sources': {family: {'enabled': family in enabled, 'filters': {}} for family in FAMILIES}}


@pytest.mark.parametrize('bits', list(product((False, True), repeat=4)))
def test_all_sixteen_subsets_constrain_local_candidates_and_sql(bits):
    selected = [family for family, bit in zip(FAMILIES, bits) if bit]
    envelope = EvidenceScope.model_validate(scope(*selected)).canonical()
    retriever = LocalRetriever()
    retriever.documents = [{'doc_id': family, 'source_type': family, 'text': 'temperature'} for family in FAMILIES]
    retriever.bm25.fit([row['text'] for row in retriever.documents])
    results = retriever.search('temperature', k=25, evidence_scope=envelope, vector_weight=0, fts_weight=1)
    assert {row['source_type'] for row in results} == set(selected)
    statement, params = scope_sql(envelope)
    assert {value for key, value in params.items() if key.endswith('_family')} == set(selected)
    if not selected:
        assert statement == 'FALSE'


def test_source_filters_are_independent_and_applied_before_top_k():
    envelope = scope('ctd', 'metagenome', 'remote_sensing', 'edna_metabarcoding')
    envelope['sources']['ctd']['filters'] = {'bay': 'O', 'station': 's1', 'time_to': '2026-01-01'}
    envelope['sources']['metagenome']['filters'] = {'bay': 'I'}
    envelope['sources']['remote_sensing']['filters'] = {'lat_min': 0, 'lon_max': 0}
    envelope['sources']['edna_metabarcoding']['filters'] = {'provider_project_id': 'p', 'is_control': False}
    documents = [
        {'doc_id': 'bad', 'source_type': 'ctd', 'bay': 'I', 'station': 's1', 'time': '2026-01-01', 'text': 'temperature '*100},
        {'doc_id': 'c', 'source_type': 'ctd', 'bay': 'O', 'station': 's1', 'time': '2026-01-01T23:00:00Z', 'text': 'temperature'},
        {'doc_id': 'm', 'source_type': 'metagenome', 'bay': 'I', 'text': 'temperature'},
        {'doc_id': 's', 'source_type': 'remote_sensing', 'lat': 0, 'lon': 0, 'text': 'temperature'},
        {'doc_id': 'e', 'source_type': 'edna_metabarcoding', 'provider_project_id': 'p', 'is_control': False, 'text': 'temperature'},
        {'doc_id': 'unknown', 'source_type': 'edna_metabarcoding', 'provider_project_id': 'p', 'is_control': None, 'text': 'temperature'},
    ]
    local = LocalRetriever()
    local.documents = documents
    local.bm25.fit([row['text'] for row in documents])
    rows = local.search('temperature', evidence_scope=envelope, k=1, vector_weight=0, fts_weight=1)
    assert rows[0]['doc_id'] != 'bad' and rows[0]['rank_sources'] == {'fts': 1}
    assert {row['doc_id'] for row in local.search('temperature', evidence_scope=envelope, k=25, vector_weight=0, fts_weight=1)} == {'c', 'm', 's', 'e'}
    statement, params = scope_sql(envelope, alias='rd', sample_ids=['e'], assignment_methods=['qcauto_target'])
    assert ' OR ' in statement and 'rd.station = :scope_0_station' in statement
    assert params['scope_2_lat_min'] == 0 and params['scope_3_is_control'] is False
    assert statement.count('allowed_sample_id') == 1


@pytest.mark.parametrize('mutate', [
    lambda s: s.update(version=2), lambda s: s.update(version=True),
    lambda s: s['sources'].pop('ctd'), lambda s: s['sources']['ctd'].update(enabled='false'),
    lambda s: s['sources']['remote_sensing']['filters'].update(bay='O'),
    lambda s: s['sources']['ctd']['filters'].update(provider='anemone'),
    lambda s: s['sources']['ctd']['filters'].update(time_from='2026-02-30'),
    lambda s: s['sources']['ctd']['filters'].update(time_from='2026-02-01', time_to='2026-01-01'),
    lambda s: s['sources']['edna_metabarcoding']['filters'].update(lat_min=5, lat_max=0),
    lambda s: s['sources']['edna_metabarcoding']['filters'].update(sample_kind='environmental', is_control=True),
])
def test_invalid_scope_never_silently_broadens(mutate):
    envelope = scope(*FAMILIES)
    mutate(envelope)
    with pytest.raises(ValidationError):
        ChatRequest(query='temperature', evidence_scope=envelope)


def test_new_legacy_mixing_unknown_keys_and_aliases():
    with pytest.raises(ValidationError):
        ChatRequest(query='temperature', evidence_scope=scope('ctd'), bay='O')
    with pytest.raises(ValidationError):
        ChatRequest(query='temperature', source_types=['ctd'])
    assert ChatRequest(query='temperature', source_type='SST').source_type == 'remote_sensing'
    with pytest.raises(ValidationError):
        ChatRequest(query='temperature', source_type='invented')


def test_sql_values_bound_and_taxon_exact_canonical():
    envelope = scope('edna_metabarcoding')
    envelope['sources']['edna_metabarcoding']['filters'] = {'taxon': "a'; DROP TABLE x; --"}
    sql, params = scope_sql(envelope)
    assert 'DROP' not in sql and 'EXISTS' in sql and 'detection.active IS TRUE' in sql
    assert params['scope_0_taxon'] == "a'; DROP TABLE x; --"


def test_derived_context_requires_whole_coverage_and_containment():
    envelope = scope('ctd')
    envelope['sources']['ctd']['filters'] = {'time_from': '2026-01-10', 'time_to': '2026-01-20'}
    document = {'id': 'derived', 'covered_source_types': ['ctd'], 'metadata': {'time_from': '2026-01-01', 'time_to': '2026-01-15'}}
    assert not context_matches_source_scope(document, envelope)
    document['metadata']['time_from'] = '2026-01-11'
    assert context_matches_source_scope(document, envelope)
    document['covered_source_types'].append('metagenome')
    assert not context_matches_source_scope(document, envelope)
    assert not context_matches_source_scope({'text': 'unknown coverage'}, envelope)
    assert context_matches_source_scope({'text': 'legacy all'}, scope(*FAMILIES))
    envelope = scope('remote_sensing')
    envelope['sources']['remote_sensing']['filters']['lat_min'] = 0
    assert not document_matches({'source_type': 'remote_sensing', 'lat': float('nan')}, envelope)


def test_all_off_bypasses_every_evidence_and_model_path(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail('all-off must not load evidence or run a provider')
    monkeypatch.setattr(unified, '_pg_available', forbidden)
    assert unified.retrieve_with_expansion('temperature', evidence_scope=scope())['diagnostics']['no_sources_selected']
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', forbidden)
    monkeypatch.setattr(api_main, 'get_model_runtime', forbidden)
    from ingestion import edna_aggregate
    monkeypatch.setattr(edna_aggregate, 'build_aggregate', forbidden)
    saved = {}
    monkeypatch.setattr(api_main, 'record_chat_context', lambda **kw: saved.update(kw))
    response = TestClient(api_main.app).post('/chat', json={'query': 'How many ANEMONE samples?', 'evidence_scope': scope()})
    assert response.status_code == 200
    data = response.json()
    assert data['outcome'] == 'abstained' and data['abstention_reason'] == 'no_sources_selected'
    assert data['model_invoked'] is False and saved['evidence_snapshot']['sources'] == []


def test_final_prompt_and_history_exclude_unchecked_and_unscoped_context(monkeypatch):
    def doc(family):
        return {'doc_id': family, 'source_type': family, 'text': f'EVIDENCE_{family}', 'time': '2026-01-01', 'title': family}
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', lambda *a, **kw: {'primary': [doc('ctd'), doc('metagenome')], 'linked': [doc('remote_sensing')], 'diagnostics': {}})
    monkeypatch.setattr(unified, 'analysis_context_documents', lambda q: [{'id': 'derived', 'text': 'UNSCOPED_CONTEXT'}])
    monkeypatch.setattr(unified, 'reliability_context_documents', lambda q: [])
    captured = {}
    class Runtime:
        def chat(self, **kw):
            captured['prompt'] = kw['prompt']
            return 'Temperature from CTD [ctd]'
    monkeypatch.setattr(api_main, 'get_model_runtime', lambda: Runtime())
    monkeypatch.setattr(api_main, 'record_chat_context', lambda **kw: captured.update(kw))
    response = TestClient(api_main.app).post('/chat', json={'query': 'temperature', 'evidence_scope': scope('ctd')})
    assert response.status_code == 200, response.text
    data = response.json()
    assert [r['source_type'] for r in data['sources']] == ['ctd']
    assert data['linked_sources'] == [] and data['analysis_context'] == []
    assert 'EVIDENCE_ctd' in captured['prompt']
    for excluded in ('EVIDENCE_metagenome', 'EVIDENCE_remote_sensing', 'UNSCOPED_CONTEXT'):
        assert excluded not in captured['prompt'] and excluded not in str(captured['evidence_snapshot'])


def test_scoped_aggregate_routing_and_issue70_regressions():
    envelope = scope('ctd', 'edna_metabarcoding')
    envelope['sources']['edna_metabarcoding']['filters'] = {'provider_project_id': 'p', 'is_control': False}
    plan = plan_aggregation({'query': 'Can you summarize ANEMONE samples?', 'evidence_scope': envelope})
    assert not plan.clarification and plan.filters['provider_project_id'] == 'p' and plan.filters['is_control'] is False
    assert plan_aggregation({'query': 'How many ANEMONE samples?', 'evidence_scope': scope('ctd')}) is None
    assert plan_aggregation({'query': 'Give a CTD summary', 'evidence_scope': scope(*FAMILIES)}) is None
    assert plan_aggregation({'query': 'Does higher read count mean more fish?', 'source_type': 'edna'}) is None
    assert not plan_aggregation({'query': 'ANEMONEにはアッセイが何件ありますか？'}).clarification
    assert render_answer(bundle(), 'How many physical samples?').startswith('The number of distinct physical samples is unresolved')
    assert render_answer(bundle(), 'How many unknown control statuses?').startswith('**3,155')


def test_analysis_pin_changes_only_edna_and_is_ignored_when_disabled(monkeypatch):
    from ingestion import edna_analysis_bundle
    def resolve(filters):
        assert filters['analysis_id'] == 'a'*64
        return {'provider_locus': 'MiFish', 'provider_team': 'ANEMONE', 'provider_project_id': 'p', 'sample_kind': 'environmental', 'is_control': False, 'source_type': 'edna_metabarcoding'}, {'s'}, {'qcauto_target'}
    monkeypatch.setattr(edna_analysis_bundle, 'request_scope', resolve)
    envelope = scope('ctd', 'edna_metabarcoding')
    envelope['sources']['edna_metabarcoding']['analysis_id'] = 'a'*64
    before = deepcopy(envelope['sources']['ctd'])
    request, members, methods = api_main._resolve_analysis_request(ChatRequest(query='temperature', evidence_scope=envelope))
    assert request.evidence_scope.canonical()['sources']['ctd'] == before
    assert members == {'s'} and methods == {'qcauto_target'}
    envelope['sources']['edna_metabarcoding']['enabled'] = False
    request, members, methods = api_main._resolve_analysis_request(ChatRequest(query='temperature', evidence_scope=envelope))
    assert members is None and methods is None


def test_capabilities_and_vertex_effective_generation(monkeypatch):
    import config
    from api.auth import route_permission
    assert route_permission('GET', '/chat/capabilities') == 'chat:use'
    monkeypatch.setattr(config, 'MODEL_PROVIDER', 'vertex')
    response = TestClient(api_main.app).get('/chat/capabilities')
    assert response.status_code == 200
    assert 'repeat_penalty' not in response.json()['generation_fields']
    options = api_main._ollama_options(ChatRequest(query='temperature', repeat_penalty=1.5, num_ctx=2048))
    assert 'repeat_penalty' not in options and 'num_ctx' not in options


def test_explicit_taxon_supplements_abbreviated_prose_with_exact_cited_counts(monkeypatch):
    from ingestion import edna_aggregate
    evidence = bundle()
    evidence['payload']['filters'] = {'taxon': 'RareTaxon', 'assignment_method': 'qcauto_target'}
    evidence['payload']['summary']['source_occurrences'] = 1
    evidence['payload']['summary']['assays'] = 1
    evidence['payload']['summary']['methods'][0]['assignment_rows'] = 1
    evidence['payload']['summary']['methods'][0]['read_count_sum'] = 122
    def exact(filters):
        assert filters == evidence['payload']['filters']
        return evidence
    monkeypatch.setattr(edna_aggregate, 'build_aggregate', exact)
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', lambda *a, **kw: {'primary': [{
        'doc_id': 'assay', 'source_type': 'edna_metabarcoding', 'assignment_method': 'qcauto_target',
        'metadata': {'taxon_terms': ['RareTaxon']}, 'text': 'Ten common featured taxa; requested rare taxon omitted.', 'title': 'Assay'}], 'linked': [], 'diagnostics': {}})
    captured = {}
    class Runtime:
        def chat(self, **kw):
            captured['prompt'] = kw['prompt']
            return 'One occurrence and 122 reads [aggregate_edna_'+'a'*64+']'
    monkeypatch.setattr(api_main, 'get_model_runtime', lambda: Runtime())
    monkeypatch.setattr(api_main, 'record_chat_context', lambda **kw: captured.update(kw))
    envelope = scope('edna_metabarcoding')
    envelope['sources']['edna_metabarcoding']['filters'] = evidence['payload']['filters']
    result = TestClient(api_main.app).post('/chat', json={'query': 'Explain the detection for the selected taxon.', 'evidence_scope': envelope})
    assert result.status_code == 200, result.text
    assert result.json()['options']['context']['taxon_evidence_scope'] == evidence['payload']['filters']
    assert '"read_count_sum": 122' in captured['prompt']
    assert '"taxon": "RareTaxon"' in captured['evidence_snapshot']['analysis_context'][0].text
    assert result.json()['analysis_context'][0]['doc_id'] == 'aggregate_edna_'+'a'*64


@pytest.mark.parametrize(('query', 'aggregation', 'envelope', 'reason'), [
    ('How many ANEMONE samples?', {}, scope('ctd'), 'source_disabled'),
    ('Did ANEMONE data arrive in August 2026?', None, scope('edna_metabarcoding'), 'freshness_unavailable'),
])
def test_scoped_deterministic_guards_do_not_run_model_or_aggregate(monkeypatch, query, aggregation, envelope, reason):
    from ingestion import edna_aggregate
    def forbidden(*a, **kw):
        pytest.fail('must abstain before model, retrieval or aggregation')
    monkeypatch.setattr(api_main, 'get_model_runtime', forbidden)
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', forbidden)
    monkeypatch.setattr(edna_aggregate, 'build_aggregate', forbidden)
    response = TestClient(api_main.app).post('/chat', json={'query': query, 'aggregation': aggregation, 'evidence_scope': envelope})
    assert response.status_code == 200, response.text
    assert response.json()['abstention_reason'] == reason and response.json()['model_invoked'] is False
