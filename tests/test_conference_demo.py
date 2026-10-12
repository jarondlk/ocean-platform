"""Conference routing uses fixed publications and never pays for exact questions."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import api.main as api
import config
import orchestration.settings_planner as planner
from api.schemas import ChatRequest
from orchestration.research_intents import QUESTIONS, ResearchIntent, render_research, select_research
from orchestration.research_question import FREQUENCY_JA, SPATIAL_JA
from tests.test_auto_settings import planning, operational_choices  # noqa: F401
from tests.test_chat_source_scope import scope
from tests.test_research_chat import research_chat_fixture
from tests.test_auto_settings import proposal


def miyagi_choices():
    choices = operational_choices()
    for a in choices:
        a['recipe_scope'] = dict(region_id='miyagi-regional-demo', time_from='2020-01-01', time_to='2023-12-31', spatial_year=2023)
        a['time_from'], a['time_to'] = '2020-01-01', '2023-12-31'
        a['workflows'].append({'kind':'monthly_spatial'})
    return choices


@pytest.mark.parametrize('heading', ['', 'よく見つかる魚は何か？\n'])
def test_full_japanese_and_english_have_identical_pinned_rows(planning, heading):  # noqa: F811
    catalog, _, calls = planning
    catalog['analyses'] = miyagi_choices()
    pinned = scope('edna_metabarcoding')
    pinned['sources']['edna_metabarcoding']['analysis_id'] = 'e'*64
    intents = []
    for query in (heading + FREQUENCY_JA, QUESTIONS['fish_frequency'][0]):
        effective, metadata = planner.plan_settings(ChatRequest(query=query, evidence_scope=pinned,
            research_intent={'kind':'fish_frequency', 'protocol_id':'c'*64}))
        intents.append(effective.research_intent)
        assert metadata['deterministic_match'] and not metadata['planner_invoked']
        assert effective.evidence_scope.sources.edna_metabarcoding.analysis_id == 'e'*64
        if query != QUESTIONS['fish_frequency'][0]:
            assert metadata['resolved_calendar_range']['time_from'] == '2020-01-01'
    assert intents[0] == intents[1] and not calls


@pytest.mark.parametrize('query', [FREQUENCY_JA.replace('2023','2024'), FREQUENCY_JA.replace('2020','2024'), SPATIAL_JA.replace('2023','2024')])
def test_incompatible_full_questions_abstain_before_planner(planning, query):  # noqa: F811
    catalog, _, calls = planning
    catalog['analyses'] = miyagi_choices()
    with pytest.raises(planner.PlanningError):
        planner.plan_settings(ChatRequest(query=query, evidence_scope=scope()))
    assert not calls


def test_spatial_year_does_not_narrow_full_publication(planning):  # noqa: F811
    catalog, _, calls = planning
    catalog['analyses'] = miyagi_choices()
    effective, metadata = planner.plan_settings(ChatRequest(query=SPATIAL_JA, evidence_scope=scope()))
    assert effective.research_intent.kind == 'monthly_spatial'
    assert not effective.evidence_scope.sources.edna_metabarcoding.filters.model_dump(exclude_none=True)
    assert metadata['resolved_calendar_range'] is None and not calls


def test_exact_path_retains_conflicting_explicit_filters(planning):  # noqa: F811
    catalog, _, calls = planning
    catalog['analyses'] = miyagi_choices()
    original = scope('edna_metabarcoding')
    original['sources']['edna_metabarcoding']['filters'] = {'provider_run_id':'unrelated'}
    effective, _ = planner.plan_settings(ChatRequest(query=QUESTIONS['fish_frequency'][0], evidence_scope=original))
    assert effective.evidence_scope.sources.edna_metabarcoding.filters.provider_run_id == 'unrelated'
    assert not calls


def test_bypass_can_be_disabled_without_changing_selection(planning, monkeypatch):  # noqa: F811
    catalog, _, calls = planning
    catalog['analyses'] = miyagi_choices()
    monkeypatch.setattr(config, 'AUTO_EXACT_WORKFLOWS_ENABLED', False)
    effective, metadata = planner.plan_settings(ChatRequest(query=QUESTIONS['fish_frequency'][0], evidence_scope=scope()))
    assert len(calls) == 1 and metadata['planner_invoked'] and not metadata['deterministic_match']
    assert effective.research_intent.kind == 'fish_frequency'


def test_language_independent_sardine_guard(tmp_path, monkeypatch):
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    changed = deepcopy(bundle)
    for row in changed['inputs']['canonical']['edna_detection']:
        if row.get('species') == 'Sardinops melanostictus':
            row['species'] = 'unidentified Sardinops'
    protocol = changed['tables']['membership'][0]['protocol_id']
    selected = scope('edna_metabarcoding')
    for query in (QUESTIONS['monthly_spatial'][0], 'マイワシの地域を示してください'):
        result = select_research(changed, selected, query, ResearchIntent(kind='monthly_spatial',protocol_id=protocol))
        assert result.reason == 'aggregate_scope_required' and not result.documents
        assert 'Sardinops melanostictus' in result.answer


def test_full_temporal_rows_and_japanese_context_are_preserved(tmp_path, monkeypatch):
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    selected = scope('edna_metabarcoding')
    selected['sources']['edna_metabarcoding']['analysis_id'] = bundle['manifest']['id']
    protocol = bundle['tables']['membership'][0]['protocol_id']
    query = QUESTIONS['fish_frequency'][-1]
    result = render_research(bundle, selected, query, ResearchIntent(kind='fish_frequency',protocol_id=protocol))
    assert result.reason is None and '検出頻度' in result.answer
    series = next(d for d in result.documents if d['table']=='series')
    assert len(series['result_rows']) > 10
    assert all(row['period'] in result.answer for row in series['result_rows'])
    assert 'プレビュー 10 行' in result.answer and '下の結果表' in result.answer
    assert '収録期間：' in result.answer
    assert '機器・プライマー・PCR条件' in result.answer
    assert '"pcr_cond"' not in result.answer
    body = TestClient(api.app).post('/chat',json={'query':query,'evidence_scope':selected,
        'research_intent':{'kind':'fish_frequency','protocol_id':protocol}}).json()
    assert body['outcome']=='answered' and not body['model_invoked']
    assert body['answer_audit']['invalid_citation_count']==0
    assert all(d['display_language']=='ja' for d in body['analysis_context'])
    assert all(d['protocol_definition']['pcr'] is not None for d in body['analysis_context'])


@pytest.mark.parametrize('query,kind', [
    (FREQUENCY_JA.replace('上位10種', '上位5種'), 'fish_frequency'),
    (FREQUENCY_JA + ' Sardinopsを除外してください。', 'fish_frequency'),
    (FREQUENCY_JA.replace('宮城県', '岩手県'), 'fish_frequency'),
    (SPATIAL_JA.replace('マイワシ', 'カタクチイワシ'), 'monthly_spatial'),
    (QUESTIONS['monthly_spatial'][0] + ' during 2024', 'monthly_spatial'),
])
def test_recorded_ready_plan_cannot_drop_unsupported_qualifiers(planning, query, kind):  # noqa: F811
    catalog, output, calls = planning
    catalog['analyses'] = miyagi_choices()
    selected = scope('edna_metabarcoding')
    selected['sources']['edna_metabarcoding']['analysis_id'] = 'e' * 64
    output['value'] = proposal(evidence_scope=selected, route='published_synthesis',
        research_intent={'kind':kind, 'protocol_id':'c'*64}, required_sources=['edna_metabarcoding'])
    with pytest.raises(planner.PlanningError):
        planner.plan_settings(ChatRequest(query=query, evidence_scope=selected,
            research_intent={'kind':kind,'protocol_id':'c'*64}))
    assert len(calls) == 1


def test_japanese_instrument_conflict_is_preserved(planning):  # noqa: F811
    catalog, output, _ = planning
    catalog['analyses'] = miyagi_choices()
    selected = scope('edna_metabarcoding')
    selected['sources']['edna_metabarcoding']['analysis_id'] = 'e' * 64
    output['value'] = proposal(evidence_scope=selected, route='published_synthesis',
        research_intent={'kind':'fish_frequency','protocol_id':'c'*64}, required_sources=['edna_metabarcoding'])
    with pytest.raises(planner.PlanningError, match='protocol'):
        planner.plan_settings(ChatRequest(query='NextSeqの検出結果を解釈してください。', evidence_scope=selected,
            research_intent={'kind':'fish_frequency','protocol_id':'c'*64}))
