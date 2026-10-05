"""Regression for #105: selected families survive ranking and prompt budgets."""
from itertools import product

import pytest
from fastapi.testclient import TestClient

import api.main as api
import orchestration.unified as unified
from retrieval.contract import RetrievalBackendError
from retrieval.source_scope import FAMILIES, enabled_sources
from tests.test_chat_source_scope import scope


def document(family, number=0, text='Sampling observation with temperature metadata.'):
    return {'doc_id': f'{family}-{number}', 'source_type': family, 'title': family,
            'text': text, 'score': 1.0 if family == 'remote_sensing' else 0.01}


def setup_retrieval(monkeypatch, rows, failures=()):
    calls = []
    monkeypatch.setattr(unified, '_pg_available', lambda: False)
    monkeypatch.setattr(unified, 'publication_status', lambda: 'ready')

    def retrieve(query, **kwargs):
        families = enabled_sources(kwargs['evidence_scope'])
        calls.append((families, kwargs))
        if any(f in failures for f in families):
            raise RetrievalBackendError('private database details must not reach diagnostics')
        # Model the old global ranking, which prefers every SST document.
        candidates = [r for family in families for r in rows.get(family, [])]
        return sorted(candidates, key=lambda r: -r['score'])[:kwargs['k']]

    monkeypatch.setattr(unified, 'retrieve', retrieve)
    return calls


def test_dominant_sst_cannot_starve_enabled_edna(monkeypatch):
    rows = {f: [document(f, n) for n in range(8)] for f in ('remote_sensing', 'edna_metabarcoding')}
    calls = setup_retrieval(monkeypatch, rows)
    result = unified.retrieve_with_expansion('ANEMONE and SST evidence', k=8,
        evidence_scope=scope(*rows), expand_evidence=False)
    assert {f: sum(r['source_type'] == f for r in result['primary']) for f in rows} == {
        'remote_sensing': 4, 'edna_metabarcoding': 4}
    assert [families for families, _ in calls] == [['remote_sensing'], ['edna_metabarcoding']]
    assert result['diagnostics']['strategy'] == 'per_source_round_robin_v1'


@pytest.mark.parametrize('bits', list(product((False, True), repeat=4)))
def test_each_enabled_family_searched_with_its_original_filters(monkeypatch, bits):
    chosen = [f for f, bit in zip(FAMILIES, bits) if bit]
    rows = {f: [document(f)] for f in chosen}
    calls = setup_retrieval(monkeypatch, rows)
    envelope = scope(*chosen)
    envelope['sources']['ctd']['filters'] = {'bay': 'O'}
    envelope['sources']['edna_metabarcoding']['filters'] = {'provider': 'anemone'}
    for family, candidates in rows.items():
        candidates[0].update(envelope['sources'][family]['filters'])
    result = unified.retrieve_with_expansion('observations', k=8, evidence_scope=envelope,
                                             expand_evidence=False, sample_ids=['reviewed'])
    assert len(result['primary']) == len(chosen)
    assert [families for families, _ in calls] == [[f] for f in chosen]
    for (families, kwargs) in calls:
        f = families[0]
        assert kwargs['evidence_scope']['sources'][f]['filters'] == envelope['sources'][f]['filters']
        assert kwargs['sample_ids'] == ['reviewed']


def test_source_failure_is_not_empty_and_other_source_survives(monkeypatch):
    setup_retrieval(monkeypatch, {'remote_sensing': [document('remote_sensing')]}, ['edna_metabarcoding'])
    result = unified.retrieve_with_expansion('ANEMONE and SST', evidence_scope=scope('remote_sensing', 'edna_metabarcoding'), expand_evidence=False)
    assert [r['source_type'] for r in result['primary']] == ['remote_sensing']
    assert result['diagnostics']['per_source']['edna_metabarcoding']['state'] == 'backend_failed'
    assert 'private database' not in str(result['diagnostics'])


def test_all_source_failures_preserve_service_error(monkeypatch):
    setup_retrieval(monkeypatch, {}, ['remote_sensing', 'edna_metabarcoding'])
    with pytest.raises(RetrievalBackendError):
        unified.retrieve_with_expansion('ANEMONE and SST', evidence_scope=scope('remote_sensing', 'edna_metabarcoding'), expand_evidence=False)


def test_linked_failure_diagnostics_do_not_expose_backend_details(monkeypatch):
    setup_retrieval(monkeypatch, {'remote_sensing': [document('remote_sensing')]})
    monkeypatch.setattr(unified, '_pg_available', lambda: True)

    def failed_expansion(*args):
        raise RuntimeError('private SQL and connection credentials')

    monkeypatch.setattr(unified, '_expand_linked_evidence', failed_expansion)
    result = unified.retrieve_with_expansion('SST observations', evidence_scope=scope('remote_sensing'))
    assert result['primary'] and not result['linked']
    assert result['diagnostics']['expansion_error'] == 'linked_evidence_expansion_failed'
    assert 'private SQL' not in str(result['diagnostics'])


def test_small_budget_reports_omission_and_empty_family_donates_slots(monkeypatch):
    setup_retrieval(monkeypatch, {f: [document(f, n) for n in range(8)] for f in FAMILIES})
    result = unified.retrieve_with_expansion('observations', k=1, evidence_scope=scope(*FAMILIES), expand_evidence=False)
    assert len(result['primary']) == 1
    assert sum(d['state'] == 'merge_budget_omitted' for d in result['diagnostics']['per_source'].values()) == 3
    setup_retrieval(monkeypatch, {'remote_sensing': [document('remote_sensing', n) for n in range(8)]})
    result = unified.retrieve_with_expansion('observations', k=8, evidence_scope=scope('remote_sensing', 'edna_metabarcoding'), expand_evidence=False)
    assert len(result['primary']) == 8
    assert result['diagnostics']['per_source']['edna_metabarcoding']['state'] == 'empty_under_scope'


def test_prompt_packing_keeps_both_families_even_with_long_sst_first():
    rows = [document('remote_sensing', n, 'SST data '*1500) for n in range(8)]
    rows.append(document('edna_metabarcoding', text='ANEMONE collection at recorded coordinates. '*300))
    prompt, manifest = unified.build_prompt_with_context('Explain ANEMONE and SST records', rows,
        evidence_scope={'evidence_scope': scope('remote_sensing', 'edna_metabarcoding')},
        inject_analysis=False, inject_reliability=False)
    assert {r['source_type'] for r in manifest['primary']} == {'remote_sensing', 'edna_metabarcoding'}
    assert 'ANEMONE collection' in prompt
    assert any(r['reason'] == 'prompt_budget' for r in manifest['omitted'])


@pytest.mark.parametrize('families,reason', [
    (['remote_sensing'], 'incomplete_source_coverage'),
    (['remote_sensing', 'edna_metabarcoding'], 'overlap_unverified'),
])
def test_overlap_never_runs_model_without_verified_matching(monkeypatch, families, reason):
    rows = [document(f) for f in families]
    monkeypatch.setattr(api, 'retrieve_with_expansion', lambda *a, **kw: {'primary': rows, 'linked': [], 'diagnostics': {}})
    monkeypatch.setattr(api, 'get_model_runtime', lambda: pytest.fail('unverified overlap must not run model'))
    captured = {}
    monkeypatch.setattr(api, 'record_chat_context', lambda **kw: captured.update(kw))
    response = TestClient(api.app).post('/chat', json={
        'query': 'Where do ANEMONE sampling dates and locations overlap with available SST observations',
        'evidence_scope': scope('remote_sensing', 'edna_metabarcoding'),
        'inject_analysis': False, 'inject_reliability': False})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['model_invoked'] is False and data['outcome'] == 'abstained'
    assert data['abstention_reason'] == reason
    assert 'does not establish' in data['answer']
    assert 'do not overlap' not in data['answer']
    assert [r.doc_id for r in captured['evidence_snapshot']['sources']] == [r['doc_id'] for r in data['sources']]
    assert captured['evidence_snapshot']['retrieval_diagnostics']['coverage_status'] != 'complete'


def test_multi_source_summary_reaches_model_and_preserves_final_coverage(monkeypatch):
    rows = [document(f) for f in ('remote_sensing', 'edna_metabarcoding')]
    monkeypatch.setattr(api, 'retrieve_with_expansion', lambda *a, **kw: {'primary': rows, 'linked': [], 'diagnostics': {}})
    calls = []

    class Runtime:
        def chat(self, **kwargs):
            calls.append(kwargs['prompt'])
            return 'Scoped source evidence [remote_sensing-0] [edna_metabarcoding-0].'

    monkeypatch.setattr(api, 'get_model_runtime', lambda: Runtime())
    response = TestClient(api.app).post('/chat', json={
        'query': 'Summarize ANEMONE eDNA and SST evidence. Include dates, locations and scientific limitations.',
        'evidence_scope': scope('remote_sensing', 'edna_metabarcoding'),
        'inject_analysis': False, 'inject_reliability': False})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(calls) == 1 and result['model_invoked'] and result['outcome'] == 'answered'
    assert {r['source_type'] for r in result['sources']} == {'remote_sensing', 'edna_metabarcoding'}


def test_four_families_survive_large_escaped_prompt_fields():
    rows = [document(f, n, '<record>Temperature & sampling</record>'*400) for f in FAMILIES for n in range(4)]
    prompt, manifest = unified.build_prompt_with_context('Explain the supplied observations', rows,
        evidence_scope={'evidence_scope': scope(*FAMILIES)}, inject_analysis=False, inject_reliability=False)
    assert {r['source_type'] for r in manifest['primary']} == set(FAMILIES)
    assert '<record>' not in prompt and '&lt;record&gt;' in prompt
    assert any(r['reason'] == 'text_truncated' for r in manifest['omitted'])


def test_shared_query_embedding_is_computed_once_and_failure_is_reused(monkeypatch):
    from db import vector_store
    calls = []
    monkeypatch.setattr(unified, '_pg_available', lambda: False)
    monkeypatch.setattr(unified, 'publication_status', lambda: 'ready')
    monkeypatch.setattr(vector_store, 'embed_text', lambda query: calls.append(query) or [0.1, 0.2])
    def retrieve(query, **kwargs):
        assert kwargs['query_embedding']() == [0.1, 0.2]
        return [document(enabled_sources(kwargs['evidence_scope'])[0])]
    monkeypatch.setattr(unified, 'retrieve', retrieve)
    unified.retrieve_with_expansion('shared embedding', evidence_scope=scope(*FAMILIES), expand_evidence=False)
    assert calls == ['shared embedding']
    def failed(query):
        calls.append(query)
        raise ValueError('embedding failed')
    monkeypatch.setattr(vector_store, 'embed_text', failed)
    def fallback(query, **kwargs):
        with pytest.raises(ValueError):
            kwargs['query_embedding']()
        kwargs['branch_diagnostics']['failed_branches'] = ['vector']
        return [document(enabled_sources(kwargs['evidence_scope'])[0])]
    monkeypatch.setattr(unified, 'retrieve', fallback)
    result = unified.retrieve_with_expansion('failed embedding', evidence_scope=scope(*FAMILIES), expand_evidence=False)
    assert calls == ['shared embedding', 'failed embedding']
    assert all(r['failed_branches'] == ['vector'] for r in result['diagnostics']['per_source'].values())


def test_malformed_or_cross_scope_backend_rows_are_not_merged(monkeypatch):
    setup_retrieval(monkeypatch, {'ctd': [document('ctd'), document('ctd')]})
    result = unified.retrieve_with_expansion('duplicates', evidence_scope=scope('ctd'), expand_evidence=False)
    assert len(result['primary']) == 1
    envelope = scope('ctd')
    envelope['sources']['ctd']['filters'] = {'bay': 'O'}
    assert unified.retrieve_with_expansion('scope', evidence_scope=envelope, expand_evidence=False)['primary'] == []


@pytest.mark.parametrize('query', [
    'Which ANEMONE observations have matching SST data?',
    'Do eDNA sampling locations coincide with sea-surface temperature observations?',
    'Where do MiFish observations align with satellite records?',
])
def test_supported_overlap_paraphrases_require_verified_matching(query):
    from orchestration.comparison_guard import comparison_guard
    diagnostics = {'supplied_source_types': ['remote_sensing', 'edna_metabarcoding']}
    guard = comparison_guard(query, scope('remote_sensing', 'edna_metabarcoding'), diagnostics)
    assert guard[0] == 'overlap_unverified'


def test_all_enabled_does_not_make_unrelated_sources_mandatory():
    from orchestration.comparison_guard import comparison_guard
    assert comparison_guard('Explain ANEMONE sampling metadata', scope(*FAMILIES), {'supplied_source_types': ['edna_metabarcoding']}) is None


@pytest.mark.parametrize('budget', [0, -1, 26, 1.5, True])
def test_primary_budget_is_bounded_before_backend_work(monkeypatch, budget):
    calls = setup_retrieval(monkeypatch, {'ctd': [document('ctd')]})
    with pytest.raises(ValueError, match='between 1 and 25'):
        unified.retrieve_with_expansion('observations', k=budget, evidence_scope=scope('ctd'))
    assert calls == []


def test_disabled_required_source_and_ambiguous_summary_are_distinct():
    from orchestration.comparison_guard import comparison_guard
    diagnostics = {'supplied_source_types': ['remote_sensing']}
    assert comparison_guard('Compare ANEMONE and SST records', scope('remote_sensing'), diagnostics)[0] == 'source_disabled'
    assert comparison_guard('Summarize ANEMONE and SST records', scope(*FAMILIES), {}) is None


def test_final_coverage_exposes_prompt_budget_omission():
    from retrieval.source_aware import reconcile_coverage
    diagnostics = {'per_source': {'ctd': {'enabled': True, 'state': 'retrieved', 'merged_count': 1}}}
    context = {'omitted': [{'source_type': 'ctd', 'doc_id': 'ctd-0', 'reason': 'prompt_budget'}]}
    final = reconcile_coverage(diagnostics, [], [], context, scope=scope('ctd'))
    assert final['per_source']['ctd']['state'] == 'prompt_budget_omitted'
    assert final['per_source']['ctd']['prompt_count'] == 0
    assert final['coverage_stage'] == 'final_prompt'
    assert final['missing_enabled_source_types'] == ['ctd']


def test_standalone_overlap_uses_the_same_no_model_guard(monkeypatch):
    setup_retrieval(monkeypatch, {f: [document(f)] for f in ('remote_sensing', 'edna_metabarcoding')})
    monkeypatch.setattr(unified, 'get_model_runtime', lambda: pytest.fail('unverified overlap must not run model'))
    data = unified.ask('Where do ANEMONE and SST observations overlap?')
    assert data['abstention_reason'] == 'overlap_unverified'
    assert data['model_invoked'] is False
