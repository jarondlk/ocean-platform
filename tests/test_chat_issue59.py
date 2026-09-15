"""Acceptance regressions for the eight issue #59 findings."""
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api.main as api
from api.schemas import ChatRequest
from orchestration.answer_audit import audit_answer
from orchestration.citation_syntax import canonical_tokens
from orchestration.citations import CitedPrompt, InvalidCitationAlias, prepare_citations
from orchestration.evidence_scope import context_matches_scope
from orchestration.unified import build_prompt_with_context
from retrieval.edna_document_builder import build_edna_documents, document_source_row_hash
from tests.test_edna_document_builder import _frames

ROW = {'doc_id': 'ctd_qa', 'text': 'The measured temperature was 12 C.', 'source_type': 'ctd'}


def audit(answer, rows, **diagnostics):
    return audit_answer(query='What was the temperature?', answer=answer, primary_sources=rows,
                        linked_sources=[], analysis_context=[], reliability_context=[], retrieval_diagnostics=diagnostics)


@pytest.mark.parametrize('dash', ['-', '–', '—'])
def test_ranges_expand_and_every_label_must_exist(dash):
    cited = CitedPrompt('', {f'S{i}': f'ctd_{i}' for i in range(1, 9)})
    assert cited.resolve(f'[S1, S3{dash}S8]') == '[ctd_1, ctd_3, ctd_4, ctd_5, ctd_6, ctd_7, ctd_8]'
    for bad in (f'[S8{dash}S1]', f'[S1{dash}S9]', f'[S1{dash}S100000000]', f'[S01{dash}S8]'):
        with pytest.raises(InvalidCitationAlias):
            cited.resolve(bad)
    with pytest.raises(InvalidCitationAlias):
        CitedPrompt('', {'S1': 'one', 'S3': 'three'}).resolve(f'[S1{dash}S3]')


def test_markdown_contract_matches_frontend_fixture():
    for case in json.loads(Path('tests/fixtures/citation_contract.json').read_text()):
        assert [item['citation_id'] for item in canonical_tokens(case['answer'])] == case['ids'], case['name']
    cited = CitedPrompt('', {'S1': 'ctd_qa'})
    assert cited.resolve('`[S999]` [S1](https://example.org) [S1]') == '`[S999]` [S1](https://example.org) [ctd_qa]'


@pytest.mark.parametrize('scope', [
    {'source_type': 'ctd'}, {'bay': 'O'}, {'sample_id': 'one'},
    {'time_from': '2099-01-01', 'time_to': '2099-12-31'},
    {'provider': 'anemone'}, {'is_control': False}, {'lat_min': 0},
])
def test_unknown_context_scope_cannot_satisfy_explicit_filter(monkeypatch, scope):
    monkeypatch.setattr('orchestration.unified.analysis_context_documents', lambda q: [{'id': 'analysis_old', 'text': 'Temperature rose in 2024.'}])
    monkeypatch.setattr('orchestration.unified.reliability_context_documents', lambda q: [])
    prompt, context = build_prompt_with_context('CTD seasonal trend', [], evidence_scope=scope)
    assert not context['analysis']
    assert 'Temperature rose in 2024' not in prompt
    assert 'APPLIED EVIDENCE SCOPE' in prompt


def test_aggregate_scope_requires_containment_and_metadata():
    row = {'source_type': 'ctd', 'bay': 'O', 'time_from': '2024-01-01', 'time_to': '2024-12-31'}
    assert context_matches_scope(row, {'source_type': 'ctd', 'bay': 'O', 'time_from': '2024-01-01', 'time_to': '2024-12-31'})
    assert not context_matches_scope(row, {'time_from': '2024-06-01'})
    assert not context_matches_scope(row, {'bay': 'I'})
    assert not context_matches_scope({**row, 'covered_source_types': ['ctd', 'remote_sensing']}, {'source_type': 'ctd'})


def test_prompt_manifest_excludes_omitted_sources_and_preserves_inputs():
    rows = [{**ROW, 'doc_id': f'ctd_{i}', 'text': 'x' * 10000} for i in range(8)]
    before = json.dumps(rows)
    prompt, context = build_prompt_with_context('temperature', rows, inject_analysis=False, inject_reliability=False)
    assert json.dumps(rows) == before
    assert 0 < len(context['primary']) < len(rows)
    assert all(len(row['text']) == 8000 for row in context['primary'])
    assert any(row['reason'] == 'text_truncated' for row in context['omitted'])
    assert any(row['reason'] == 'prompt_budget' for row in context['omitted'])
    labels = prepare_citations(prompt, context['primary'])
    assert set(labels.aliases.values()) == {row['doc_id'] for row in context['primary']}
    result = audit('999 C [ctd_7].', context['primary'])
    assert result['invalid_citation_count'] == 1
    assert result['citation_check_status'] == 'failed'


def test_checks_never_claim_scientific_verification():
    wrong = audit('999 C [ctd_qa].', [ROW])
    assert wrong['citation_check_status'] == 'passed'
    assert wrong['claim_verification'] == 'not_performed'
    assert wrong['trust_level'] == 'not_assessed'
    invalid = audit('12 C [ctd_qa, invented].', [ROW])
    assert invalid['citation_check_status'] == 'failed'
    assert invalid['trust_score'] < 0.55
    assert audit('12 C [ctd_qa].', [ROW], scope_violations=['date'])['citation_check_status'] == 'failed'


def test_empty_ctd_scope_abstains_before_model(monkeypatch):
    monkeypatch.setattr(api, 'retrieve_with_expansion', lambda *a, **k: {'primary': [], 'linked': [], 'diagnostics': {}})
    monkeypatch.setattr('orchestration.unified.analysis_context_documents', lambda q: [{'id': 'analysis_old', 'text': '2024 seasonal CTD temperatures.'}])
    monkeypatch.setattr('orchestration.unified.reliability_context_documents', lambda q: [])
    def forbidden(**kwargs):
        raise AssertionError('Empty scope must not invoke model')
    monkeypatch.setattr(api, 'get_model_runtime', lambda: SimpleNamespace(chat=forbidden))
    response = TestClient(api.app).post('/chat', json={'query': 'CTD seasonal trend', 'source_type': 'ctd', 'time_from': '2099-01-01', 'time_to': '2099-12-31'})
    assert response.status_code == 200
    assert response.json()['outcome'] == 'abstained'
    assert response.json()['model_invoked'] is False
    assert response.json()['n_context_documents'] == 0


def test_linked_context_respects_date_and_source_scope():
    linked = [{**ROW, 'time': '2024-01-01'}]
    prompt, context = build_prompt_with_context('temperature', [], linked_results=linked,
        evidence_scope={'time_from': '2099-01-01'}, inject_analysis=False, inject_reliability=False)
    assert not context['linked']
    assert '12 C' not in prompt


def test_standard_presence_is_separate_from_calibration_and_method_counts():
    samples, assays, detections = _frames()
    standards = pd.DataFrame([
        dict(internal_standard_id='std1', assay_id='a'*64, standard_name='MiFish_STD_01', read_count=7327,
             active=True, source_file_id='stdfile', source_snapshot_id='stdsnapshot', source_row_number=7, source_row_hash='hash1'),
        dict(internal_standard_id='inactive', assay_id='a'*64, standard_name='inactive', read_count=999999, active=False),
        dict(internal_standard_id='other', assay_id='other', standard_name='unrelated', read_count=999999, active=True),
    ])
    docs = build_edna_documents(samples, assays, detections, standards)
    for doc in docs:
        assert doc.metadata['internal_standard_count'] == 1
        assert doc.metadata['calibration_status'] == 'not_established'
        assert 'calibration status remains unknown' in doc.text
        assert 'MiFish_STD_01, read count 7327' in doc.text
        assert 'inactive' not in doc.text and 'unrelated' not in doc.text
        assert 'presence alone does not establish calibrated abundance' in doc.text
        provenance = next(row for row in doc.metadata['canonical_records'] if row['entity_type'] == 'internal_standard')
        assert provenance['source_file_id'] == 'stdfile'
        assert provenance['source_row_locator'] == 7
    assert next(d for d in docs if d.assignment_method == 'qcauto_target').metadata['read_count_sum'] == 13
    standards.loc[0, 'read_count'] = 42
    changed = build_edna_documents(samples, assays, detections, standards)
    assert document_source_row_hash(docs[0]) != document_source_row_hash(changed[0])
    assert 'were not supplied' in build_edna_documents(samples, assays, detections)[0].text
    assert 'No active internal-standard records' in build_edna_documents(samples, assays, detections, pd.DataFrame())[0].text


@pytest.mark.parametrize('query', [' ', '\n\t', '\u3000'])
def test_blank_query_rejected_before_retrieval(query):
    with pytest.raises(ValidationError):
        ChatRequest(query=query)
    assert ChatRequest(query='  fish  ').query == 'fish'


def test_api_history_and_audit_share_the_bounded_evidence(monkeypatch):
    from tests.test_chat_feedback import _database, _install_database, _add_user
    from db.app_models import ChatInteraction
    import api.auth as auth
    import uuid

    factory = _database()
    user = _add_user(factory, 'manifest@example.invalid')
    _install_database(monkeypatch, factory)
    monkeypatch.setattr(auth, 'authenticate_request', lambda _: user)
    rows = [{**ROW, 'doc_id': f'ctd_{i}', 'text': 'x' * 10000} for i in range(8)]
    monkeypatch.setattr(api, 'retrieve_with_expansion', lambda *a, **k: {'primary': rows, 'linked': [], 'diagnostics': {}})
    monkeypatch.setattr(api, 'get_model_runtime', lambda: SimpleNamespace(chat=lambda **k: 'Measured value [S1].'))
    response = TestClient(api.app).post('/chat', json={'query': 'temperature', 'inject_analysis': False, 'inject_reliability': False})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload['sources']) < 8
    assert all(len(row['text']) == 8000 for row in payload['sources'])
    with factory() as session:
        saved = session.get(ChatInteraction, uuid.UUID(payload['interaction_id']))
        assert saved.evidence_snapshot['sources'] == payload['sources']
        assert saved.evidence_snapshot['prompt_diagnostics']['evidence_omissions'] == payload['prompt_diagnostics']['evidence_omissions']
        assert set(saved.evidence_snapshot['citation_aliases'].values()) == {row['doc_id'] for row in payload['sources']}
        assert saved.answer_audit_snapshot['claim_verification'] == 'not_performed'


def test_daily_aggregate_cannot_fit_inside_a_partial_day_scope():
    row = {'time_from': '2024-01-01', 'time_to': '2024-01-31'}
    assert not context_matches_scope(row, {'time_to': '2024-01-31T12:00:00Z'})
    assert context_matches_scope(row, {'time_to': '2024-01-31'})
    assert not context_matches_scope({'time': '2024-01-31'}, {'time_to': '2024-01-31T12:00:00Z'})
