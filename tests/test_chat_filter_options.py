"""Available selections track active evidence without changing the requested scope."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
import config
from api.auth import route_permission
from retrieval import filter_options as choices
from tests.test_chat_source_scope import scope


def install_corpus(monkeypatch, tmp_path, documents):
    import json
    monkeypatch.setattr(config, 'SERVING_DIR', tmp_path)
    monkeypatch.setattr(config, 'EDNA_ARTIFACT_URI', '')
    (tmp_path / 'retrieval_documents.jsonl').write_text('\n'.join(json.dumps(d) for d in documents))


def test_choices_are_source_owned_cascade_and_replace_their_own_selection(monkeypatch, tmp_path):
    install_corpus(monkeypatch, tmp_path, [
        {'doc_id': 'c1', 'source_type': 'ctd', 'sample_id': '2024-04-O-s1', 'time': '2024-04-01'},
        {'doc_id': 'c2', 'source_type': 'ctd', 'sample_id': '2024-05-O-s2', 'time': '2024-05-01'},
        {'doc_id': 'c3', 'source_type': 'ctd', 'sample_id': '2024-04-I-s3', 'time': '2024-04-01'},
        {'doc_id': 'inactive', 'source_type': 'ctd', 'station': 'hidden', 'active': False},
        {'doc_id': 'm', 'source_type': 'metagenome', 'station': 'meta-station', 'bay': 'M'},
    ])
    envelope = scope()  # Unchecked sources can still show their filter choices.
    envelope['sources']['ctd']['filters'] = {'bay': 'O', 'station': 's1'}
    original = deepcopy(envelope)
    response = choices.filter_options(envelope, pg_available=False)
    ctd = response['sources']['ctd']['fields']
    assert ctd['station']['values'] == ['s1', 's2']
    assert ctd['sample_id']['values'] == ['2024-04-O-s1']
    assert response['sources']['metagenome']['fields']['station']['values'] == ['meta-station']
    assert response['sources']['edna_metabarcoding']['available'] is False
    assert envelope == original
    envelope['sources']['ctd']['filters']['time_to'] = '2024-04-30'
    assert choices.filter_options(envelope, pg_available=False)['sources']['ctd']['fields']['station']['values'] == ['s1']


def test_edna_choices_include_canonical_taxonomy_false_and_pinned_members(monkeypatch, tmp_path):
    install_corpus(monkeypatch, tmp_path, [
        {'doc_id': 'e1', 'source_type': 'edna_metabarcoding', 'sample_id': 'one', 'assignment_method': 'qcauto_target',
         'provider': 'ANEMONE', 'is_control': False, 'metadata': {'taxon_terms': ['Rare fish', 'Animalia']}},
        {'doc_id': 'e2', 'source_type': 'edna_metabarcoding', 'sample_id': 'two', 'assignment_method': 'qcauto_target',
         'provider': 'OTHER', 'is_control': True, 'metadata': {'taxon_terms': ['Outside']}},
        {'doc_id': 'e3', 'source_type': 'edna_metabarcoding', 'sample_id': 'one', 'assignment_method': 'qcauto_95pct_3nn_target',
         'provider': 'ANEMONE', 'is_control': False, 'metadata': {'taxon_terms': ['Other method']}},
    ])
    response = choices.filter_options(scope(), pg_available=False, family='edna_metabarcoding',
                                      members=['one'], methods=['qcauto_target'])
    fields = response['sources']['edna_metabarcoding']['fields']
    assert fields['taxon']['values'] == ['Animalia', 'Rare fish']
    assert fields['is_control']['values'] == ['false']
    assert fields['provider']['values'] == ['ANEMONE']


def test_long_lists_are_bounded_and_search_can_reach_values_beyond_the_first_page(monkeypatch, tmp_path):
    install_corpus(monkeypatch, tmp_path, [
        {'doc_id': str(i), 'source_type': 'ctd', 'sample_id': f'sample-{i:03d}'} for i in range(120)
    ])
    first = choices.filter_options(scope(), pg_available=False, family='ctd', field='sample_id')['sources']['ctd']['fields']['sample_id']
    assert len(first['values']) == 100 and first['truncated'] is True
    last = choices.filter_options(scope(), pg_available=False, family='ctd', field='sample_id', search='SAMPLE-119')['sources']['ctd']['fields']['sample_id']
    assert last == {'values': ['sample-119'], 'truncated': False}
    with pytest.raises(ValueError):
        choices.filter_options(scope(), pg_available=False, family='ctd', field='station; DROP TABLE users')


def test_route_validates_scope_and_requires_chat_permission(monkeypatch, tmp_path):
    install_corpus(monkeypatch, tmp_path, [{'doc_id': 'c', 'source_type': 'ctd', 'station': 's1'}])
    monkeypatch.setattr('orchestration.unified._pg_available', lambda: False)
    client = TestClient(api_main.app)
    assert route_permission('POST', '/chat/filter-options') == 'chat:use'
    assert route_permission('GET', '/chat/filter-options') is None
    response = client.post('/chat/filter-options', json={'evidence_scope': scope(), 'family': 'ctd'})
    assert response.status_code == 200 and response.json()['sources']['ctd']['fields']['station']['values'] == ['s1']
    for body in [
        {'evidence_scope': scope(), 'field': 'station'},
        {'evidence_scope': scope(), 'family': 'remote_sensing', 'field': 'bay'},
        {'evidence_scope': scope(), 'family': 'ctd', 'search': 'x' * 201},
        {'evidence_scope': {'version': 2, 'sources': {}}},
    ]:
        assert client.post('/chat/filter-options', json=body).status_code == 422
    monkeypatch.setattr(api_main, '_resolve_analysis_request', lambda request: (request, ['pinned'], ['qcauto_target']))
    monkeypatch.setattr(choices, 'filter_options', lambda *args, **kwargs: {'members': kwargs['members'], 'methods': kwargs['methods']})
    assert client.post('/chat/filter-options', json={'evidence_scope': scope()}).json()['members'] == ['pinned']
