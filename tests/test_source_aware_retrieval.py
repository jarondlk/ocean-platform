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
    rows.append(document('edna_metabarcoding', text='ANEMONE collection at recorded coordinates.'))
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
    assert [r['doc_id'] for r in captured['evidence_snapshot']['sources']] == [r['doc_id'] for r in data['sources']]
    assert captured['evidence_snapshot']['retrieval_diagnostics']['coverage_status'] != 'complete'
