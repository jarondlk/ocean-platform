"""Historical SST enters normal surfaces without altering scientific identities."""
from copy import deepcopy
from datetime import date, datetime, timezone

import pandas as pd
import pytest

import config
from ingestion.immutable_bundle import digest
from ingestion.regional_publication import (
    DATASET, publish_regional,
    current_publication, analysis_publication, validate_period, _cached_publication,
)
from retrieval.source_scope import EvidenceScope, document_matches, scope_sql
from retrieval.source_aware import scoped_retrieve
from tests.test_chat_source_scope import scope
from tests.test_provisional_research_demo import fixture


@pytest.fixture
def published(tmp_path, monkeypatch, request):
    recipe, inputs = fixture()
    period = deepcopy(inputs['period_preview'])
    for r in period['observations']:
        r.update(source_url='https://example.org/mur', valid_fraction=1.0,
                 valid_ocean_points=20, raw_sha256=digest('retained-raw'))
        r['observation_id'] = digest({k: v for k, v in r.items() if k != 'observation_id'})
    if getattr(request, 'param', None) == 'known_gap':
        period['observations'] = [r for r in period['observations'] if r['time_utc'][:10] != '2021-02-20']
        period['final_series_gaps'] = [{'day':'2021-02-20','reason':'known_acquisition_exclusion'}]
    # Publication only accepts the user-approved Miyagi product/period scope.
    period['definition']['diagnostic_rectangle'] = {'west':141.0, 'east':142.0, 'south':38.0, 'north':39.0}
    period['definition']['grid_step_degrees'] = .05
    period['period_preview_id'] = digest({k:v for k,v in period.items() if k != 'period_preview_id'})
    bundles = {digest(method): {'manifest': {'id': digest(method), 'schema_version': 3},
               'inputs': {'period_preview': period}, 'recipe': {'assignment_method': method}}
               for method in ('qcauto_target', 'qcauto_95pct_3nn_target')}
    import ingestion.edna_analysis_bundle as analyses
    monkeypatch.setattr(analyses, 'load_analysis', lambda identity: bundles[identity])
    monkeypatch.setattr(analyses, 'analysis_status', lambda b: 'current')
    monkeypatch.setattr(config, 'EDNA_ARTIFACT_URI', (tmp_path/'published').as_uri())
    decision = dict(decision_origin='user', approval_basis='explicit_user_accepted_operational_publication',
                    user_instruction='Include the existing evidence in the full system', recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                    period_preview_id=period['period_preview_id'], analysis_ids=tuple(bundles))
    result = publish_regional(decision)
    yield result, period, decision, bundles
    _cached_publication.cache_clear()


def test_sealed_publication_readback_is_idempotent_and_preserves_science(published):
    result, period, decision, bundles = published
    assert publish_regional(decision) == result
    observed = current_publication()
    assert observed['period'] == period
    assert observed['period']['scientific_approval'] is False
    assert observed['period']['scientific_publication'] is False
    assert len(observed['period']['observations']) == 1461
    assert all(analysis_publication(b)['publication_id'] == result['publication_id'] for b in bundles.values())
    altered = deepcopy(next(iter(bundles.values())))
    altered['manifest']['other'] = 'different verified manifest'
    assert analysis_publication(altered) is None


def test_scientific_endorsement_and_interim_or_missing_days_cannot_be_promoted(published):
    _, period, decision, _ = published
    decision['provider_endorsement'] = True
    with pytest.raises(ValueError, match='endorsement'):
        publish_regional(decision)
    for mutation in ('interim', 'missing', 'conflicting_gap'):
        changed = deepcopy(period)
        if mutation == 'interim':
            changed['observations'][0]['processing_generation'] = 'interim'
            changed['observations'][0]['observation_id'] = digest({k:v for k,v in changed['observations'][0].items() if k!='observation_id'})
        elif mutation == 'missing':
            changed['observations'].pop()
        else:
            changed['final_series_gaps'] = [{'day':'2020-01-01','reason':'gap'}]
        changed['period_preview_id'] = digest({k:v for k,v in changed.items() if k!='period_preview_id'})
        with pytest.raises(ValueError):
            validate_period(changed)


def test_stale_analysis_prevents_activation(published, monkeypatch):
    import ingestion.edna_analysis_bundle as analyses
    _, _, decision, _ = published
    monkeypatch.setattr(analyses, 'analysis_status', lambda b: 'historical')
    with pytest.raises(ValueError, match='stale'):
        publish_regional(decision)


def test_historical_retrieval_uses_selected_dates_product_and_source_budget(published):
    envelope = scope('remote_sensing', 'edna_metabarcoding')
    envelope['sources']['remote_sensing']['filters'] = {'time_from':'2021-02-01','time_to':'2021-02-28','dataset_id':DATASET}
    EvidenceScope.model_validate(envelope)
    def search(query, **kw):
        return [{'doc_id':'e1','source_type':'edna_metabarcoding','title':'ANEMONE','text':'sample'}] if kw['evidence_scope']['sources']['edna_metabarcoding']['enabled'] else []
    rows, diagnostics = scoped_retrieve('Miyagi historical SST coverage', scope=envelope, k=8, backend='postgres', search=search, options={})
    assert len(rows) <= 8 and any(r['source_type']=='edna_metabarcoding' for r in rows)
    history = [r for r in rows if r['source_type']=='remote_sensing']
    assert history and all(r['time'].startswith('2021-02') for r in history)
    assert history[0]['metadata']['days'] == 28
    assert history[0]['metadata']['dataset_id'] == DATASET
    assert diagnostics['per_source']['remote_sensing']['regional_candidate_count'] > 0
    envelope['sources']['remote_sensing']['enabled'] = False
    rows, _ = scoped_retrieve('SST', scope=envelope, k=8, backend='local', search=search, options={})
    assert all(r['source_type'] != 'remote_sensing' for r in rows)


def test_legacy_dataset_filter_is_not_applied_to_historical_evidence(published):
    from retrieval.regional_sst import regional_search
    envelope = scope('remote_sensing')
    envelope['sources']['remote_sensing']['filters'] = {'dataset_id':'current-sst'}
    rows, _ = regional_search('SST', envelope, 8)
    assert rows == []
    assert document_matches({'source_type':'remote_sensing'}, envelope)
    sql, params = scope_sql(envelope, alias='rd')
    assert 'metadata_json' in sql and 'current-sst' in params.values()


def test_overview_counts_only_published_windows_not_intervening_years(published, monkeypatch, tmp_path):
    from api.overview_coverage import artifact_source
    normalized = tmp_path/'normalized'
    normalized.mkdir()
    pd.DataFrame({'date_jst':['2026-01-01','2026-01-03'], 'mean_sst':[10.,11.]}).to_parquet(normalized/'sst_daily_summary.parquet')
    monkeypatch.setattr(config,'NORMALIZED_DIR',normalized)
    observed = artifact_source('remote_sensing')
    assert observed.total_count == 1463
    assert observed.missing_day_count == 1
    assert observed.missing_dates_within_extent == ['2026-01-02']
    assert not any(b.month.startswith(('2024','2025')) for b in observed.bins)


@pytest.mark.parametrize('legacy_date', ['2026-01-01', date(2026, 1, 1), pd.Timestamp('2026-01-01')])
def test_normal_data_catalog_and_sst_include_history_without_mixing_product_statistics(published, monkeypatch, tmp_path, legacy_date):
    import api.main as api
    path = tmp_path/'production-format.parquet'
    pd.DataFrame({'date_jst':[legacy_date], 'mean_sst':[9.], 'min_sst':[8.], 'max_sst':[10.]}).to_parquet(path)
    monkeypatch.setattr(api, '_read_explore_dataset', lambda key: pd.read_parquet(path))
    combined = api._sst_daily_df().sort_values('date_jst')
    assert combined.iloc[-1]['date_jst'] == '2026-01-01'
    monkeypatch.setattr(api, '_sst_points_df', lambda: pd.DataFrame({'time_jst':['2026-01-01T12:00:00+09:00'], 'sst':[9.]}))
    summary = api.explore_summary(dataset='sst_daily', search=None)
    assert summary.total_rows == 1462
    assert next(p for p in summary.profiles if p.name == 'warnings').unique == 1
    table = api.explore_table(dataset='sst_daily', limit=2, offset=0, search=None)
    assert table.total == 1462 and len(table.rows) == 2
    series = api.explore_timeseries(dataset='sst_daily', limit=2, search=None)
    assert len(series.points) == 2 and all(p.source == DATASET for p in series.points)
    all_data = api.data_sst(limit=100)
    assert all_data.days == 1462
    assert all_data.stats['mean_sst'] is None
    assert {row.dataset_id for row in all_data.daily} == {DATASET, 'current-sst'}
    historical = api.data_sst(dataset_id=DATASET,time_from='2020-01-01',time_to='2020-01-31',limit=100)
    assert historical.days == 31 and historical.observations == 0
    assert all(r.min_sst is None and r.max_sst is None for r in historical.daily)
    assert historical.stats['mean_sst'] is not None
    current = api.data_sst(dataset_id='current-sst',time_to='2026-01-01',limit=100)
    assert current.days == 1 and current.observations == 1  # inclusive whole calendar day


def test_promoted_analysis_preserves_exact_results_and_source_disable(monkeypatch):
    from ingestion.provisional_research_bundle import build_demo
    from orchestration.research_intents import QUESTIONS, ResearchIntent, render_research
    import ingestion.regional_publication as publication
    recipe, inputs = fixture()
    result = build_demo(recipe, inputs)
    bundle = {'manifest': {'id':result['analysis_id'],'schema_version':3}, 'recipe':result['recipe'], 'inputs':result['inputs'], 'tables':result['tables']}
    envelope = scope('remote_sensing', 'edna_metabarcoding')
    protocol = next(iter(result['tables']['membership']))['protocol_id']
    monkeypatch.setattr(publication,'analysis_publication',lambda b: None)
    original = render_research(bundle,envelope,QUESTIONS['fish_frequency'][0],ResearchIntent(kind='fish_frequency',protocol_id=protocol))
    monkeypatch.setattr(publication,'analysis_publication',lambda b: {'publication_id':digest('operational'),'approval_basis':'explicit_user_accepted_operational_publication'})
    promoted = render_research(bundle,envelope,QUESTIONS['fish_frequency'][0],ResearchIntent(kind='fish_frequency',protocol_id=protocol))
    assert 'Published Miyagi regional analysis' in promoted.answer
    assert [d['result_rows'] for d in promoted.documents] == [d['result_rows'] for d in original.documents]
    assert all(d['analysis_type']=='regional_frequency' for d in promoted.documents)
    assert 'not fish abundance' in promoted.answer
    envelope['sources']['remote_sensing']['enabled']=False
    disabled = render_research(bundle,envelope,QUESTIONS['temperature_comparison'][0],ResearchIntent(kind='temperature_comparison',protocol_id=protocol))
    assert disabled.reason=='source_disabled'


def test_corrupt_historical_branch_reports_failure_and_keeps_other_sources(monkeypatch):
    import retrieval.regional_sst as regional
    def failed(*args):
        raise ValueError('private path must not be exposed')
    monkeypatch.setattr(regional,'supplement_sst',failed)
    envelope = scope('remote_sensing','edna_metabarcoding')
    def search(query, **kw):
        return [{'doc_id':'e1','source_type':'edna_metabarcoding','title':'ANEMONE','text':'sample'}] if kw['evidence_scope']['sources']['edna_metabarcoding']['enabled'] else []
    rows, diagnostics = scoped_retrieve('SST and eDNA',scope=envelope,k=8,backend='postgres',search=search,options={})
    assert [r['doc_id'] for r in rows]==['e1']
    assert diagnostics['per_source']['remote_sensing']['state']=='backend_failed'
    assert diagnostics['per_source']['remote_sensing']['failed_branches']==['regional_publication']
    assert 'private path' not in str(diagnostics)


@pytest.mark.parametrize('published', ['known_gap'], indirect=True)
def test_known_empty_dates_return_gap_receipts_not_invented_measurements(published):
    from retrieval.regional_sst import regional_search
    envelope = scope('remote_sensing')
    envelope['sources']['remote_sensing']['filters'] = {'dataset_id':DATASET,'time_from':'2021-02-20','time_to':'2021-02-20'}
    rows, _ = regional_search('Do we have final or interim SST?',envelope,8)
    assert len(rows)==1
    assert rows[0]['metadata']['days']==0
    assert rows[0]['rank_sources']=={'regional_gap_receipt':1}
    assert 'not SST measurements' in rows[0]['text']
    envelope['sources']['remote_sensing']['filters']['lat_min']=38.0
    assert regional_search('SST',envelope,8)[0]==[]  # a regional receipt is not a point location
