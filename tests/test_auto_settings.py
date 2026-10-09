"""AUTO proposals must be validated before evidence or answer generation."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api.main as api_main
import config
import orchestration.settings_planner as planner
from api.schemas import ChatRequest
from orchestration.settings_plan import SettingsProposal
from retrieval.source_scope import FAMILIES
from tests.test_chat_source_scope import scope
from tests.test_regional_publication import published  # noqa: F401


def catalogue():
    return {'version': 1, 'analyses': [], 'sst_datasets': [],
            'contexts': {'analysis': [], 'reliability': []},
            'sources': {f: {'available': True, 'fields': {}} for f in FAMILIES}}


def proposal(**changes):
    value = dict(version=1, status='ready', explanation='Use CTD for this measurement.',
                 evidence_scope=scope('ctd'), required_sources=['ctd'])
    value.update(changes)
    return value


@pytest.fixture
def planning(monkeypatch):
    catalog = catalogue()
    calls = []
    output = {'value': proposal()}
    class Runtime:
        def structured_chat(self, **kwargs):
            calls.append(kwargs)
            return output['raw'] if 'raw' in output else json.dumps(output['value'])
    monkeypatch.setattr(config, 'AUTO_SETTINGS_ENABLED', True)
    monkeypatch.setattr(planner, 'planner_catalog', lambda: catalog)
    monkeypatch.setattr(planner, 'get_model_runtime', Runtime)
    return catalog, output, calls


def test_explicit_scope_is_applied_without_changing_generation_or_manual_snapshot(planning):
    _, output, calls = planning
    chosen = scope('ctd')
    chosen['sources']['ctd']['filters'] = {'bay': 'O', 'time_from': '2024-01-01', 'time_to': '2024-12-31'}
    output['value'] = proposal(evidence_scope=chosen, constraints=[
        {'family': 'ctd', 'field': field, 'quote': quote}
        for field, quote in [('bay', 'Onagawa'), ('time_from', '2024'), ('time_to', '2024')]])
    manual = scope(*FAMILIES)
    request = ChatRequest(query='Show CTD salinity in Onagawa during 2024.', settings_mode='auto',
                          evidence_scope=manual, temperature=.3, k=20)
    effective, meta = planner.plan_settings(request)
    assert effective.evidence_scope.canonical() == chosen
    assert effective.temperature == .3 and effective.k == 8 and effective.run_answer_audit
    assert request.evidence_scope.canonical() == manual and request.k == 20
    assert meta['planner_invoked'] and meta['status'] == 'applied'
    assert calls[0]['timeout'] == config.CHAT_PLANNER_TIMEOUT_SECONDS
    assert calls[0]['model'] == config.CHAT_PLANNER_MODEL


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(sql='SELECT * FROM private'),
    lambda p: p['evidence_scope']['sources']['ctd']['filters'].update(bay='invented'),
    lambda p: p['evidence_scope']['sources']['ctd']['filters'].update(station='invented'),
    lambda p: p.update(analysis_document_ids=['invented-context']),
    lambda p: p.update(required_sources=['remote_sensing']),
    lambda p: p.update(required_sources=[]),
    lambda p: p.update(unresolved_constraints=['unsupported qualifier']),
])
def test_invalid_plans_never_execute(mutation, planning):
    _, output, _ = planning
    mutation(output['value'])
    request = ChatRequest(query='Show CTD salinity', settings_mode='auto', evidence_scope=scope())
    with pytest.raises(planner.PlanningError):
        planner.plan_settings(request)


@pytest.mark.parametrize('raw', ['not JSON', '```json\n{}\n```', '{}', 'x' * (planner.MAX_PLAN_CHARS + 1)])
def test_malformed_and_oversized_plans_fail_visibly(raw, planning):
    _, output, _ = planning
    output['raw'] = raw
    with pytest.raises(planner.PlanningError, match='invalid settings'):
        planner.plan_settings(ChatRequest(query='CTD salinity', settings_mode='auto', evidence_scope=scope()))


def test_disabled_auto_does_not_call_the_planner(monkeypatch, planning):
    _, _, calls = planning
    monkeypatch.setattr(config, 'AUTO_SETTINGS_ENABLED', False)
    with pytest.raises(planner.PlanningError, match='unavailable') as error:
        planner.plan_settings(ChatRequest(query='CTD salinity', settings_mode='auto', evidence_scope=scope()))
    assert not error.value.invoked and calls == []


def test_explicit_year_and_comparison_cannot_be_dropped(planning):
    request = ChatRequest(query='Compare CTD and satellite SST in 2024', settings_mode='auto', evidence_scope=scope())
    with pytest.raises(planner.PlanningError):
        planner.plan_settings(request)
    with pytest.raises(planner.PlanningError, match='time range'):
        planner.plan_settings(request.model_copy(update={'query': 'Show CTD salinity since 2024'}))


def test_exact_calendar_dates_cannot_be_replaced_with_other_days(planning):
    _, output, _ = planning
    chosen = scope('ctd')
    chosen['sources']['ctd']['filters'] = {'time_from': '2024-01-01', 'time_to': '2024-12-31'}
    output['value'] = proposal(evidence_scope=chosen, constraints=[
        {'family': 'ctd', 'field': 'time_from', 'quote': '2024-02-01'},
        {'family': 'ctd', 'field': 'time_to', 'quote': '2024-02-29'}])
    with pytest.raises(planner.PlanningError, match='calendar date'):
        planner.plan_settings(ChatRequest(query='CTD from 2024-02-01 to 2024-02-29',
                                         settings_mode='auto', evidence_scope=scope()))


def test_pinned_dataset_analysis_and_protocol_cannot_be_changed(planning):
    catalog, output, calls = planning
    chosen = scope('edna_metabarcoding', 'remote_sensing')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = 'a' * 64
    chosen['sources']['remote_sensing']['filters']['dataset_id'] = 'mur-miyagi-2020-2023'
    catalog['analyses'] = [{'analysis_id': 'a' * 64, 'status': 'current', 'analysis_kind': 'regional_frequency',
                            'protocol_ids': ['b' * 64], 'sst_available': True}]
    output['value'] = proposal(evidence_scope=chosen, route='published_exact',
                               research_intent={'kind': 'temperature_comparison', 'protocol_id': 'b' * 64},
                               required_sources=['edna_metabarcoding', 'remote_sensing'])
    request = ChatRequest(query='Compare fish detections in high and low SST', settings_mode='auto',
                          evidence_scope=deepcopy(chosen), research_intent={'kind': 'fish_frequency', 'protocol_id': 'b' * 64})
    effective, _ = planner.plan_settings(request)
    assert effective.research_intent.kind == 'temperature_comparison'
    assert effective.research_intent.protocol_id == 'b' * 64
    planner_input = json.loads(calls[0]['prompt'].split('INPUT:\n', 1)[1])
    assert planner_input['selection_context']['verified_user_protocol_choice']['protocol_id'] == 'b' * 64
    assert planner_input['catalogue']['analyses'][0]['protocol_ids'] == ['b' * 64]
    assert catalog['analyses'][0]['protocol_ids'] == ['b' * 64]
    output['value']['research_intent']['protocol_id'] = 'c' * 64
    with pytest.raises(planner.PlanningError, match='retain.*protocol'):
        planner.plan_settings(request)
    output['value']['evidence_scope']['sources']['edna_metabarcoding']['analysis_id'] = 'c' * 64
    with pytest.raises(planner.PlanningError, match='conflicts.*analysis'):
        planner.plan_settings(request)


def test_api_runs_planner_before_retrieval_and_keeps_original_effective_history(planning, monkeypatch):
    _, _, calls = planning
    order = []
    history = []
    class Runtime:
        def chat(self, **kwargs):
            order.append('answer')
            return 'Salinity is reported in the CTD evidence [ctd-test].'
    def retrieve(*args, **kwargs):
        order.append('retrieve')
        assert calls and kwargs['evidence_scope'] == scope('ctd')
        return {'primary': [{'doc_id': 'ctd-test', 'source_type': 'ctd', 'text': 'CTD salinity 34', 'title': 'CTD'}], 'linked': []}
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', retrieve)
    monkeypatch.setattr(api_main, 'get_model_runtime', Runtime)
    monkeypatch.setattr(api_main, 'record_chat_options', lambda **kw: history.append(kw['request_options']))
    result = TestClient(api_main.app).post('/chat', json={'query': 'Show CTD salinity', 'settings_mode': 'auto', 'evidence_scope': scope()})
    assert result.status_code == 200, result.text
    payload = result.json()
    assert order == ['retrieve', 'answer'] and len(calls) == 1
    assert payload['options']['planning']['planner_invoked'] and payload['model_invoked']
    assert history[0]['requested']['evidence_scope'] == scope()
    assert history[0]['evidence_scope'] == scope('ctd')


@pytest.mark.parametrize('case', ['invalid', 'clarification', 'timeout'])
def test_api_failures_do_not_retrieve_or_run_answer_model(case, planning, monkeypatch):
    _, output, _ = planning
    if case == 'clarification':
        output['value'] = proposal(status='clarification', clarification='Which diversity dataset do you mean?')
    elif case == 'invalid':
        output['raw'] = '{not JSON}'
    else:
        class Runtime:
            def structured_chat(self, **kwargs):
                raise TimeoutError('provider diagnostic must stay private')
        monkeypatch.setattr(planner, 'get_model_runtime', Runtime)
    def forbidden(*args, **kwargs):
        pytest.fail('Planning failures must not run evidence or the answer model')
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', forbidden)
    monkeypatch.setattr(api_main, 'get_model_runtime', forbidden)
    response = TestClient(api_main.app).post('/chat', json={'query': 'Show CTD salinity', 'settings_mode': 'auto', 'evidence_scope': scope()})
    assert response.status_code == 200, response.text
    assert not response.json()['model_invoked'] and response.json()['outcome'] == 'abstained'
    assert response.json()['options']['planning']['status'] != 'applied'
    assert 'provider diagnostic' not in response.text


def test_auto_requires_versioned_scope_and_rejects_legacy_mixing():
    with pytest.raises(ValidationError):
        ChatRequest(query='CTD', settings_mode='auto')
    with pytest.raises(ValidationError):
        ChatRequest(query='CTD', settings_mode='auto', evidence_scope=scope('ctd'), bay='O')
    assert SettingsProposal.model_validate(proposal()).route == 'rag'


@pytest.mark.parametrize('published', ['known_gap'], indirect=True)
def test_sst_coverage_reconciles_calendar_and_preserves_gap_reasons(published):  # noqa: F811
    from orchestration.published_results import sst_coverage
    chosen = scope('remote_sensing')
    chosen['sources']['remote_sensing']['filters'] = {'dataset_id': 'mur-miyagi-2020-2023',
                                                    'time_from': '2021-02-01', 'time_to': '2021-02-28'}
    answer, document = sst_coverage(chosen)
    assert '27 supported days / 28 calendar days' in answer
    assert '2021-02-20: known_acquisition_exclusion' in answer
    assert '04.1nrt' in answer and '0.05-degree' in answer
    assert document['metadata']['expected_days'] == 28
    chosen['sources']['remote_sensing']['filters']['time_from'] = '2019-01-01'
    with pytest.raises(ValueError, match='2020'):
        sst_coverage(chosen)


@pytest.mark.parametrize('route', ['published_exact', 'published_synthesis'])
def test_semantic_published_results_reuse_exact_rows_without_rewriting_question(route, tmp_path, monkeypatch, planning):
    from tests.test_research_chat import research_chat_fixture
    from orchestration.statistics_catalog import analysis_choices
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    catalog, output, calls = planning
    catalog['analyses'] = analysis_choices()
    identity = bundle['manifest']['id']
    protocol_id = catalog['analyses'][0]['protocol_ids'][0]
    chosen = scope('edna_metabarcoding')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = identity
    output['value'] = proposal(evidence_scope=chosen, route=route, preset='synthesis',
                              research_intent={'kind': 'fish_frequency', 'protocol_id': protocol_id},
                              required_sources=['edna_metabarcoding'])
    captured = {}
    class Runtime:
        def chat(self, **kwargs):
            captured.update(kwargs)
            return 'The published frequencies describe detections, not abundance [S1].'
    monkeypatch.setattr(api_main, 'get_model_runtime', Runtime)
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', lambda *a, **kw: pytest.fail('Published-only routes must not retrieve raw examples'))
    query = 'Explain what the published fish detections tell us and their uncertainty.'
    result = TestClient(api_main.app).post('/chat', json={'query': query, 'settings_mode': 'auto', 'evidence_scope': chosen,
                                                       'research_intent': {'kind': 'fish_frequency', 'protocol_id': protocol_id}})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['query'] == query and data['outcome'] == 'answered'
    assert len(calls) == 1 and data['analysis_context']
    assert data['model_invoked'] is (route == 'published_synthesis')
    if route == 'published_synthesis':
        assert query in captured['prompt'] and 'total_table_rows' in captured['prompt']
        assert data['answer_audit']['claim_verification'] != 'published_result_rows_verified'
        assert data['answer_audit']['invalid_citation_count'] == 0
        assert all(len(d['result_rows']) == 1 for d in data['analysis_context'])
    else:
        assert not captured and data['answer_audit']['claim_verification'] == 'published_result_rows_verified'


@pytest.mark.parametrize('published', ['known_gap'], indirect=True)
def test_miyagi_coverage_question_uses_complete_ledger_without_answer_model(published, planning, monkeypatch):  # noqa: F811
    catalog, output, calls = planning
    dataset = 'mur-miyagi-2020-2023'
    catalog['sst_datasets'] = [{'dataset_id': dataset}]
    chosen = scope('remote_sensing')
    chosen['sources']['remote_sensing']['filters'] = {'dataset_id': dataset, 'time_from': '2020-01-01', 'time_to': '2023-12-31'}
    output['value'] = proposal(evidence_scope=chosen, route='sst_coverage', required_sources=['remote_sensing'], constraints=[
        {'family': 'remote_sensing', 'field': 'time_from', 'quote': '2020'},
        {'family': 'remote_sensing', 'field': 'time_to', 'quote': '2023'}])
    original = scope('remote_sensing')
    original['sources']['remote_sensing']['filters'] = {'dataset_id': dataset}
    def forbidden(*args, **kwargs):
        pytest.fail('Complete coverage cannot be inferred from raw examples or the answer model')
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', forbidden)
    monkeypatch.setattr(api_main, 'get_model_runtime', forbidden)
    response = TestClient(api_main.app).post('/chat', json={
        'query': 'What final MUR SST coverage is available for Miyagi from 2020 to 2023? List missing dates and explain the spatial resolution and limitations.',
        'settings_mode': 'auto', 'evidence_scope': original})
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(calls) == 1 and not data['model_invoked']
    assert '1460 supported days / 1461 calendar days' in data['answer']
    assert '2021-02-20: known_acquisition_exclusion' in data['answer']
    assert data['options']['evidence_scope'] == chosen
    assert data['answer_audit']['invalid_citation_count'] == 0
    assert data['sources'][0]['metadata']['publication_id'] == published[0]['publication_id']


def test_frequency_then_high_low_sst_retains_pinned_analysis_and_protocol(tmp_path, planning, monkeypatch):
    from tests.test_research_chat import research_chat_fixture
    from orchestration.statistics_catalog import analysis_choices
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    catalog, output, _ = planning
    catalog['analyses'] = analysis_choices()
    protocol_id = catalog['analyses'][0]['protocol_ids'][0]
    chosen = scope('edna_metabarcoding', 'remote_sensing')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = bundle['manifest']['id']
    intent = {'kind': 'fish_frequency', 'protocol_id': protocol_id}
    def forbidden(*args, **kwargs):
        pytest.fail('These exact workflows use the published rows')
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', forbidden)
    monkeypatch.setattr(api_main, 'get_model_runtime', forbidden)
    client = TestClient(api_main.app)
    for kind, query, tables in [
        ('fish_frequency', 'Show the top 10 fish by detection frequency, with yearly and seasonal changes.', {'ranking', 'series'}),
        ('temperature_comparison', 'Compare fish detection frequency in high and low SST conditions and show a representative series.', {'temperature_contrasts', 'temperature_bins', 'temperature_series'}),
    ]:
        output['value'] = proposal(evidence_scope=chosen, route='published_exact',
                                  research_intent={'kind': kind, 'protocol_id': protocol_id},
                                  required_sources=['edna_metabarcoding', *(['remote_sensing'] if kind == 'temperature_comparison' else [])])
        response = client.post('/chat', json={'query': query, 'settings_mode': 'auto', 'evidence_scope': chosen, 'research_intent': intent})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['outcome'] == 'answered' and not data['model_invoked']
        assert data['options']['evidence_scope'] == chosen
        assert {d['table'] for d in data['analysis_context']} == tables
        intent = data['options']['planning']['research_intent']
        assert intent['protocol_id'] == protocol_id


def test_unpinned_distinct_publications_still_require_selection(planning):
    catalog, output, _ = planning
    first = {'analysis_id': 'a' * 64, 'status': 'current', 'analysis_kind': 'detection_frequency',
             'protocol_ids': ['b' * 64], 'workflows': [{'kind': 'fish_frequency'}]}
    catalog['analyses'] = [first, {**first, 'analysis_id': 'c' * 64}]
    chosen = scope('edna_metabarcoding')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = first['analysis_id']
    output['value'] = proposal(evidence_scope=chosen, route='published_exact',
                              required_sources=['edna_metabarcoding'],
                              research_intent={'kind': 'fish_frequency', 'protocol_id': 'b' * 64})
    with pytest.raises(planner.PlanningError, match='Select|select'):
        planner.plan_settings(ChatRequest(query='Show the top 10 fish.', settings_mode='auto',
                                         evidence_scope=scope('edna_metabarcoding')))


def operational_choices():
    from orchestration.research_intents import QUESTIONS
    first = {'analysis_id': 'a' * 64, 'publication_id': 'd' * 64,
             'status': 'current', 'analysis_kind': 'regional_frequency', 'label': 'Miyagi QCauto',
             'time_from': '2020-01-01', 'time_to': '2023-12-31',
             'recipe_scope': {'region_id': 'miyagi-regional-demo', 'rank': 'species',
                              'time_from': '2020-01-01', 'time_to': '2023-12-31'},
             'assignment_methods': ['qcauto_target'], 'sst_available': True,
             'protocol_ids': ['b' * 64, 'c' * 64],
             'protocols': {'b' * 64: {'sequencing_method': 'NextSeq', 'library_layout': 'single', 'target_gene': '12S rRNA'},
                           'c' * 64: {'sequencing_method': 'MiSeq', 'library_layout': 'paired', 'target_gene': '12S rRNA'}},
             'protocol_labels': {'b' * 64: '12S · NextSeq single', 'c' * 64: '12S · MiSeq paired'},
             'workflows': [{'kind': kind} for kind in QUESTIONS]}
    second = {**deepcopy(first), 'analysis_id': 'e' * 64, 'label': 'Miyagi 95% 3NN',
              'assignment_methods': ['qcauto_95pct_3nn_target']}
    return [first, second]


@pytest.mark.parametrize('model_status', ['ready', 'clarification'])
@pytest.mark.parametrize('kind', ['fish_frequency', 'temperature_comparison'])
def test_fresh_auto_resolves_all_published_dropdowns_even_when_model_omits_them(planning, kind, model_status):
    from orchestration.research_intents import QUESTIONS
    catalog, output, calls = planning
    catalog['analyses'] = operational_choices()
    original = scope()
    output['value'] = proposal() if model_status == 'ready' else proposal(
        status='clarification', clarification='Please select an analysis and assay protocol.')
    request = ChatRequest(query=QUESTIONS[kind][0], settings_mode='auto', evidence_scope=original)
    effective, metadata = planner.plan_settings(request)
    assert effective.evidence_scope.sources.edna_metabarcoding.analysis_id == 'e' * 64
    assert effective.research_intent.kind == kind
    assert effective.research_intent.protocol_id == 'b' * 64
    assert effective.evidence_scope.sources.remote_sensing.enabled is (kind == 'temperature_comparison')
    assert effective.evidence_scope.sources.edna_metabarcoding.enabled
    assert metadata['route'] == 'published_exact'
    assert metadata['catalogue_selection']['analysis_defaulted']
    assert metadata['catalogue_selection']['protocol_defaulted']
    assert 'first published assay protocol' in metadata['explanation']
    assert request.evidence_scope.canonical() == original
    prompt = json.loads(calls[0]['prompt'].split('INPUT:\n')[1])
    assert prompt['selection_context']['verified_catalogue_selection']['protocol_id'] == 'b' * 64
    assert [a['analysis_id'] for a in prompt['catalogue']['analyses']] == ['e' * 64]


@pytest.mark.parametrize(('qualifier', 'expected'), [
    ('', 'b' * 64), ('using MiSeq paired protocol', 'c' * 64),
    ('using NextSeq single-end', 'b' * 64), ('using protocol ' + 'c' * 64, 'c' * 64)])
def test_protocol_defaults_follow_catalogue_order_and_explicit_requests(planning, qualifier, expected):
    catalog, output, _ = planning
    catalog['analyses'] = operational_choices()
    chosen = scope('edna_metabarcoding')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = 'e' * 64
    # The model selected the wrong instrument or omitted the protocol.
    output['value'] = proposal(evidence_scope=chosen, route='published_exact',
        required_sources=['edna_metabarcoding'], research_intent={'kind': 'fish_frequency'})
    effective, _ = planner.plan_settings(ChatRequest(query='Show published fish frequency ' + qualifier,
        settings_mode='auto', evidence_scope=scope()))
    assert effective.research_intent.protocol_id == expected


@pytest.mark.parametrize('qualifier', ['using NovaSeq', 'using MiSeq single-end', 'using MiSeq and NextSeq',
                                     'using protocol ' + 'f' * 64])
def test_unavailable_or_conflicting_protocol_request_never_defaults(planning, qualifier):
    catalog, output, _ = planning
    catalog['analyses'] = operational_choices()
    chosen = scope('edna_metabarcoding')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = 'e' * 64
    output['value'] = proposal(evidence_scope=chosen, route='published_exact',
        required_sources=['edna_metabarcoding'], research_intent={'kind': 'fish_frequency'})
    with pytest.raises(planner.PlanningError, match='No published assay protocol'):
        planner.plan_settings(ChatRequest(query='Show published fish frequency ' + qualifier,
            settings_mode='auto', evidence_scope=scope()))


def test_requested_protocol_cannot_silently_conflict_with_a_manual_pin(planning):
    catalog, output, _ = planning
    catalog['analyses'] = operational_choices()
    chosen = scope('edna_metabarcoding')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = 'e' * 64
    output['value'] = proposal(evidence_scope=chosen, route='published_exact',
        required_sources=['edna_metabarcoding'], research_intent={'kind': 'fish_frequency', 'protocol_id': 'b' * 64})
    with pytest.raises(planner.PlanningError, match='No published assay protocol'):
        planner.plan_settings(ChatRequest(query='Show published fish frequency using MiSeq paired protocol',
            settings_mode='auto', evidence_scope=chosen,
            research_intent={'kind': 'fish_frequency', 'protocol_id': 'b' * 64}))


def test_requested_assignment_method_takes_priority_over_publication_default(planning):
    catalog, output, _ = planning
    catalog['analyses'] = operational_choices()
    chosen = scope('edna_metabarcoding')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = 'e' * 64
    output['value'] = proposal(evidence_scope=chosen, route='published_exact',
        required_sources=['edna_metabarcoding'], research_intent={'kind': 'fish_frequency'})
    effective, _ = planner.plan_settings(ChatRequest(query='Show fish frequencies using qcauto_target',
        settings_mode='auto', evidence_scope=scope()))
    assert effective.evidence_scope.sources.edna_metabarcoding.analysis_id == 'a' * 64
    with pytest.raises(planner.PlanningError, match='conflicts.*method'):
        planner.plan_settings(ChatRequest(query='Show fish frequencies using qcauto_target',
            settings_mode='auto', evidence_scope=chosen))


def test_published_sst_workflow_selects_its_verified_dataset_without_a_user_pin(planning):
    catalog, output, _ = planning
    catalog['analyses'] = operational_choices()
    catalog['sst_datasets'] = [{'dataset_id': 'mur-miyagi-2020-2023', 'publication_id': 'd' * 64}]
    output['value'] = proposal()
    effective, metadata = planner.plan_settings(ChatRequest(
        query='Compare fish detection frequency in high and low SST conditions and show a representative series',
        settings_mode='auto', evidence_scope=scope()))
    assert effective.evidence_scope.sources.remote_sensing.filters.dataset_id == 'mur-miyagi-2020-2023'
    assert metadata['retained_user_pins'] == {}
    catalog['sst_datasets'][0]['publication_id'] = 'f' * 64
    effective, _ = planner.plan_settings(ChatRequest(
        query='Compare fish detection frequency in high and low SST conditions and show a representative series',
        settings_mode='auto', evidence_scope=scope()))
    assert effective.evidence_scope.sources.remote_sensing.filters.dataset_id is None


def test_fresh_mur_coverage_resolves_dataset_and_quote_without_preselected_sources(planning):
    from orchestration.statistics_catalog import CAPABILITIES
    catalog, output, _ = planning
    catalog['capabilities'] = CAPABILITIES
    catalog['sst_datasets'] = [{'dataset_id': 'mur-miyagi-2020-2023', 'publication_id': 'd' * 64}]
    query = next(c for c in CAPABILITIES if c['id'] == 'sst_coverage')['examples'][0]
    output['value'] = proposal(status='clarification', clarification='Which SST dataset?')
    effective, metadata = planner.plan_settings(ChatRequest(query=query, settings_mode='auto', evidence_scope=scope()))
    assert metadata['route'] == 'sst_coverage'
    assert effective.evidence_scope.sources.remote_sensing.filters.dataset_id == 'mur-miyagi-2020-2023'
    assert effective.evidence_scope.sources.remote_sensing.filters.time_from == '2020-01-01'
    assert effective.evidence_scope.sources.remote_sensing.filters.time_to == '2023-12-31'
    assert effective.research_intent is None
    assert [f for f,s in effective.evidence_scope.canonical()['sources'].items() if s['enabled']] == ['remote_sensing']
    for suffix in (' in Onagawa', ' excluding December', ' using interim files'):
        with pytest.raises(planner.PlanningError, match='Which SST dataset'):
            planner.plan_settings(ChatRequest(query=query + suffix, settings_mode='auto', evidence_scope=scope()))


def test_unknown_sst_dataset_cannot_pass_with_a_valid_question_quote(planning):
    catalog, output, _ = planning
    catalog['sst_datasets'] = [{'dataset_id': 'mur-miyagi-2020-2023'}]
    chosen = scope('remote_sensing')
    chosen['sources']['remote_sensing']['filters']['dataset_id'] = 'mur-unpublished'
    output['value'] = proposal(evidence_scope=chosen, route='sst_coverage', required_sources=['remote_sensing'],
        constraints=[{'family': 'remote_sensing', 'field': 'dataset_id', 'quote': 'MUR'}])
    with pytest.raises(planner.PlanningError, match='not currently published'):
        planner.plan_settings(ChatRequest(query='Show MUR coverage', settings_mode='auto', evidence_scope=scope()))


@pytest.mark.parametrize('change', ['publication_id', 'recipe_scope', 'status'])
def test_exact_workflow_does_not_default_across_different_or_stale_publications(planning, change):
    from orchestration.auto_published_settings import exact_catalogue_plan
    catalog, _, _ = planning
    choices = operational_choices()
    if change == 'publication_id':
        choices[1][change] = 'f' * 64
    elif change == 'recipe_scope':
        choices[1][change]['region_id'] = 'another-region'
    else:
        for a in choices:
            a['status'] = 'historical'
    catalog['analyses'] = choices
    request = ChatRequest(query='Show the top 10 fish by detection frequency, with yearly and seasonal changes',
                          settings_mode='auto', evidence_scope=scope())
    assert exact_catalogue_plan(request, catalog) is None


@pytest.mark.parametrize('suffix', [' excluding sardines', ' in Onagawa', ' with top 5 instead', ' during 2024'])
def test_extra_qualifiers_cannot_be_overridden_by_exact_catalogue_mapping(planning, suffix):
    catalog, output, _ = planning
    catalog['analyses'] = operational_choices()
    output['value'] = proposal(status='clarification', clarification='The publication does not match that qualifier.')
    with pytest.raises(planner.PlanningError, match='does not match'):
        planner.plan_settings(ChatRequest(query='Show the top 10 fish by detection frequency, with yearly and seasonal changes' + suffix,
            settings_mode='auto', evidence_scope=scope()))


def test_fresh_auto_api_answers_known_workflows_from_real_verified_bundles(tmp_path, monkeypatch, planning):
    from tests.test_research_chat import research_chat_fixture
    from orchestration.statistics_catalog import analysis_choices
    from orchestration.research_intents import QUESTIONS
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    catalog, output, _ = planning
    catalog['analyses'] = analysis_choices()
    output['value'] = proposal(status='clarification', clarification='Choose a protocol.')
    monkeypatch.setattr(api_main, 'get_model_runtime', lambda *a, **kw: pytest.fail('Exact results must not invoke the answer model'))
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', lambda *a, **kw: pytest.fail('Published rows must not be replaced by retrieval'))
    client = TestClient(api_main.app)
    for kind in ('fish_frequency', 'temperature_comparison'):
        result = client.post('/chat', json={'query': QUESTIONS[kind][0], 'settings_mode': 'auto', 'evidence_scope': scope()})
        assert result.status_code == 200, result.text
        data = result.json()
        assert data['outcome'] == 'answered' and not data['model_invoked']
        assert data['options']['evidence_scope']['sources']['edna_metabarcoding']['analysis_id'] == bundle['manifest']['id']
        assert data['options']['planning']['research_intent']['kind'] == kind
        assert data['options']['planning']['research_intent']['protocol_id'] == catalog['analyses'][0]['protocol_ids'][0]
        assert data['answer_audit']['invalid_citation_count'] == 0


def test_publication_disappearing_after_planning_abstains_before_answer_generation(planning, monkeypatch):
    from ingestion.provenance_snapshot import SnapshotError
    catalog, output, _ = planning
    identity, protocol_id = 'a' * 64, 'b' * 64
    catalog['analyses'] = [{'analysis_id': identity, 'status': 'current', 'analysis_kind': 'detection_frequency', 'protocol_ids': [protocol_id]}]
    chosen = scope('edna_metabarcoding')
    chosen['sources']['edna_metabarcoding']['analysis_id'] = identity
    output['value'] = proposal(evidence_scope=chosen, route='published_synthesis',
                              required_sources=['edna_metabarcoding'],
                              research_intent={'kind': 'fish_frequency', 'protocol_id': protocol_id})
    def unavailable(*args, **kwargs):
        raise SnapshotError('private storage diagnostic')
    def forbidden(*args, **kwargs):
        pytest.fail('A stale publication cannot run retrieval or answer generation')
    monkeypatch.setattr('ingestion.edna_analysis_bundle.load_analysis', unavailable)
    monkeypatch.setattr(api_main, 'get_model_runtime', forbidden)
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', forbidden)
    response = TestClient(api_main.app).post('/chat', json={'query': 'Interpret the published fish frequencies.',
                                                          'settings_mode': 'auto', 'evidence_scope': chosen})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['outcome'] == 'abstained' and not data['model_invoked']
    assert data['abstention_reason'] == 'aggregate_unavailable'
    assert 'private storage diagnostic' not in response.text


def test_large_protocol_payloads_do_not_overflow_planner_catalogue(monkeypatch):
    from ingestion.immutable_bundle import digest
    protocol_id = 'a' * 64
    metadata = {'target_gene': '12S rRNA', 'sequencing_method': 'MiSeq', 'library_layout': 'paired',
                'primer_set': 'ACGT' * 10000, 'pcr': {'pcr_notes': 'cycles' * 10000}}
    original = {**catalogue(), 'analyses': [{'analysis_id': 'b' * 64, 'status': 'current',
                'protocol_ids': [protocol_id], 'protocols': {protocol_id: metadata, 'c' * 64: metadata},
                'protocol_labels': {protocol_id: metadata['primer_set']},
                'recipe_scope': {'time_from': '2020-01-01', 'time_to': '2023-12-31'},
                'limitations': ['Occurrence proxies are not confirmed independent samples.']}]}
    import retrieval.filter_options as facets
    import orchestration.unified as unified
    monkeypatch.setattr(planner, 'statistics_catalog', lambda: original)
    monkeypatch.setattr(planner, 'context_choices', lambda: original['contexts'])
    monkeypatch.setattr(unified, '_pg_available', lambda: False)
    monkeypatch.setattr(facets, 'filter_options', lambda *args, **kwargs: {'sources': original['sources']})
    result = planner.planner_catalog()
    assert len(json.dumps(result)) < planner.MAX_CATALOG_CHARS
    analysis = result['analyses'][0]
    assert set(analysis['protocols']) == {protocol_id}
    assert analysis['protocols'][protocol_id]['sequencing_method'] == 'MiSeq'
    assert analysis['protocols'][protocol_id]['library_layout'] == 'paired'
    assert analysis['protocols'][protocol_id]['primer_set_sha256'] == digest(metadata['primer_set'])
    assert analysis['protocols'][protocol_id]['pcr_metadata_sha256'] == digest(metadata['pcr'])
    assert analysis['recipe_scope'] == original['analyses'][0]['recipe_scope']
    assert analysis['limitations'] == original['analyses'][0]['limitations']
    assert original['analyses'][0]['protocols'][protocol_id]['primer_set'] == metadata['primer_set']


def test_catalogue_only_offers_protocols_with_published_membership(tmp_path, monkeypatch):
    from tests.test_research_chat import research_chat_fixture
    from orchestration.statistics_catalog import analysis_choices
    import ingestion.edna_analysis_bundle as analyses
    from preprocessing.edna_analysis import protocol
    from ingestion.immutable_bundle import digest
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    changed = deepcopy(bundle)
    extra = deepcopy(changed['inputs']['canonical']['edna_assay'][0])
    extra['sequencing_method'] = 'Unpublished instrument'
    changed['inputs']['canonical']['edna_assay'].append(extra)
    monkeypatch.setattr(analyses, 'load_analysis', lambda identity: changed)
    choices = analysis_choices()[0]
    assert digest(protocol(extra)) not in choices['protocols']
    assert set(choices['protocols']) == set(choices['protocol_ids'])


def test_provider_schema_is_small_but_does_not_relax_filter_validation():
    from orchestration.settings_plan import planner_response_schema
    schema = planner_response_schema()
    assert len(json.dumps(schema)) < 4000
    assert '$ref' not in json.dumps(schema)
    sources = schema['properties']['evidence_scope']['properties']['sources']['properties']
    assert set(sources) == set(FAMILIES)
    assert sources['ctd']['properties']['filters'] == {'type': 'object', 'additionalProperties': True}
    invalid = proposal()
    invalid['evidence_scope']['sources']['ctd']['filters'] = {'sql': 'SELECT * FROM private'}
    with pytest.raises(ValidationError):
        SettingsProposal.model_validate(invalid)
    invalid['evidence_scope']['sources']['ctd']['filters'] = {'lat_min': 200}
    with pytest.raises(ValidationError):
        SettingsProposal.model_validate(invalid)


def test_confirmed_user_pins_are_restored_without_new_question_quotes(planning):
    catalog, output, _ = planning
    identity, protocol_id = 'a' * 64, 'b' * 64
    catalog['analyses'] = [{'analysis_id': identity, 'status': 'current', 'analysis_kind': 'regional_frequency',
                            'protocol_ids': [protocol_id], 'sst_available': True}]
    pinned = scope('edna_metabarcoding', 'remote_sensing')
    pinned['sources']['edna_metabarcoding']['analysis_id'] = identity
    pinned['sources']['remote_sensing']['filters']['dataset_id'] = 'mur-miyagi-2020-2023'
    output['value'] = proposal(evidence_scope=scope('edna_metabarcoding'), route='published_exact',
                               research_intent={'kind': 'fish_frequency'}, required_sources=['edna_metabarcoding'],
                               constraints=[{'family': 'remote_sensing', 'field': 'dataset_id', 'quote': 'Selected dataset'},
                                            {'family': 'edna_metabarcoding', 'field': 'protocol_id', 'quote': 'Selected protocol'}])
    effective, metadata = planner.plan_settings(ChatRequest(query='Show the top 10 fish by detection frequency.',
        settings_mode='auto', evidence_scope=pinned, research_intent={'kind':'temperature_comparison', 'protocol_id':protocol_id}))
    assert effective.evidence_scope.canonical() == pinned
    assert effective.research_intent.kind == 'fish_frequency'
    assert effective.research_intent.protocol_id == protocol_id
    assert metadata['constraints'] == []
    assert metadata['retained_user_pins'] == {'edna_metabarcoding.analysis_id':identity,
        'edna_metabarcoding.protocol_id':protocol_id, 'remote_sensing.dataset_id':'mur-miyagi-2020-2023'}
    assert metadata['evidence_scope'] == effective.evidence_scope.canonical()


@pytest.mark.parametrize('query,start,end', [
    ('MUR coverage from 2020 to 2023', '2020-01-01', '2023-12-31'),
    ('Miyagi 2020–2023 coverage', '2020-01-01', '2023-12-31'),
    ('Miyagi 2020-2023 coverage', '2020-01-01', '2023-12-31'),
    ('CTD salinity during 2024', '2024-01-01', '2024-12-31'),
    ('CTD between 2024-02-01 and 2024-02-29', '2024-02-01', '2024-02-29'),
    ('CTD during 2024-02-29', '2024-02-29', '2024-02-29'),
])
def test_literal_calendar_ranges_preserve_inclusive_dates(query, start, end):
    result = planner.explicit_calendar_range(query)
    assert result['time_from'] == start and result['time_to'] == end and result['quote'] in query


@pytest.mark.parametrize('query', [
    'CTD since 2024', 'CTD during last year', 'Compare 2020 with 2023',
    'CTD during 2024 and SST during 2025', 'MUR from 2020 to 2023 except 2021',
    'MUR outside the period from 2020 to 2023', 'CTD during 2024-02-30',
    'MUR from 2023 to 2020', 'CTD during 2024-05-invalid',
])
def test_ambiguous_relative_excluded_and_invalid_calendar_ranges_are_not_filled(query):
    assert planner.explicit_calendar_range(query) is None


def test_absolute_range_is_applied_when_planner_omits_it(planning):
    effective, metadata = planner.plan_settings(ChatRequest(query='Show CTD salinity in Onagawa during 2024.',
        settings_mode='auto', evidence_scope=scope()))
    assert effective.evidence_scope.canonical()['sources']['ctd']['filters'] == {
        'time_from':'2024-01-01', 'time_to':'2024-12-31'}
    assert metadata['resolved_calendar_range'] == {'time_from':'2024-01-01', 'time_to':'2024-12-31', 'quote':'during 2024'}
    assert all(c['quote'] in 'Show CTD salinity in Onagawa during 2024.' for c in metadata['constraints'])
