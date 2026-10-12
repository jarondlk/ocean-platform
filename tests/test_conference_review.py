"""Factual review rejects plausible-looking but incorrect retained evidence."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from evaluation.qa.conference_review import review_sst, replay_sst_receipt, sample_taxonomy_fallback
from ingestion.provisional_research_bundle import build_demo
from ingestion.immutable_bundle import digest
from preprocessing.historical_sst_matching import preview_relative_temperature_bins
from orchestration.research_intents import QUESTIONS, ResearchIntent, render_research
from tests.test_provisional_research_demo import fixture, default_scope


@pytest.fixture
def bundle():
    recipe, inputs = fixture()
    period = inputs['period_preview']
    for observation in period['observations']:
        if observation['time_utc'].startswith(('2020-05-15', '2023-05-15')):
            observation['sst_celsius'] = 5.0 if observation['time_utc'].startswith('2020') else 25.0
            observation['observation_id'] = digest({k: v for k, v in observation.items() if k != 'observation_id'})
    period['relative_temperature'] = preview_relative_temperature_bins(period['observations'])
    period['period_preview_id'] = digest({k: v for k, v in period.items() if k != 'period_preview_id'})
    inputs['user_decision']['period_preview_id'] = period['period_preview_id']
    recipe = recipe.model_copy(update={'min_stratum_samples': 1, 'sst_panel_id': period['period_preview_id']})
    result = build_demo(recipe, inputs)
    return {'manifest': {'id': result['analysis_id'], 'schema_version': 3},
            **{k: result[k] for k in ('recipe', 'inputs', 'tables')}}


def test_sst_review_checks_source_baseline_and_all_rates(bundle):
    report = review_sst(bundle)
    assert report['status'] == 'passed_offline_factual_review'
    assert report['rate_rows_checked'] == sum(len(bundle['tables'][t]) for t in ('temperature_bins', 'temperature_series'))
    assert report['final_daily_observations'] == 1461
    assert not report['independent_scientific_approval']


@pytest.mark.parametrize('table,field', [('temperature_bins', 'eligible'),
    ('sst_links', 'sst_celsius'), ('sst_links', 'time_difference_hours'), ('relative_sst_thresholds', 'low_max_celsius'),
    ('temperature_contrasts', 'standardized_difference_percentage_points'),
    ('temperature_series', 'sst_matched'), ('temperature_strata', 'low_detected')])
def test_sst_review_rejects_corrupted_counts_values_and_standardization(bundle, table, field):
    corrupt = deepcopy(bundle)
    row = next(r for r in corrupt['tables'][table] if isinstance(r[field], (int, float)))
    row[field] += 1
    with pytest.raises(ValueError):
        review_sst(corrupt)


def test_sst_receipt_replay_preserves_scope_rows_citations_and_graph(bundle):
    protocol = bundle['tables']['membership'][0]['protocol_id']
    intent = ResearchIntent(kind='temperature_comparison', protocol_id=protocol)
    query = QUESTIONS['temperature_comparison'][0]
    with patch('ingestion.regional_publication.analysis_publication', lambda _: None):
        result = render_research(bundle, default_scope(), query, intent)
    assert not result.reason
    assert 'opposite signs' in result.answer and 'supported-stratum count' in result.answer
    retained = {'query': query, 'outcome': 'answered', 'model_invoked': False,
                'options': {'context': {'research_intent': intent.model_dump()}, 'evidence_scope': default_scope()},
                'analysis_context': [{**d, 'doc_id': d['id']} for d in result.documents], 'answer': result.answer}
    assert replay_sst_receipt(bundle, retained).documents == result.documents
    corrupt = deepcopy(retained)
    corrupt['analysis_context'][0]['result_rows'][0]['low_detected'] += 1
    with pytest.raises(ValueError, match='changed'):
        replay_sst_receipt(bundle, corrupt)
    corrupt = deepcopy(retained)
    corrupt['analysis_context'][2]['plot_taxa'] = []
    with pytest.raises(ValueError, match='changed'):
        replay_sst_receipt(bundle, corrupt)
    corrupt = deepcopy(retained)
    corrupt['options']['evidence_scope']['sources']['remote_sensing']['enabled'] = False
    with pytest.raises(ValueError, match='scope'):
        replay_sst_receipt(bundle, corrupt)


def test_incompatible_sample_is_omitted_without_inventing_five_assignments(bundle):
    protocol = bundle['tables']['membership'][0]['protocol_id']
    output = sample_taxonomy_fallback(bundle, protocol)
    assert output == {'status': 'omitted_no_compatible_complete_sample', 'original_otsuchi_reproduced': False}


def test_incomplete_assay_never_produces_taxonomy_fallback(bundle):
    for a in bundle['inputs']['canonical']['edna_assay']:
        a['community_availability_json'] = {'qcauto_95pct_3nn_target': {'status': 'available_nonempty', 'row_count': 9999}}
    protocol = bundle['tables']['membership'][0]['protocol_id']
    assert sample_taxonomy_fallback(bundle, protocol)['status'] == 'omitted_no_compatible_complete_sample'


def test_sample_illustrations_keep_rank_and_complete_source_assignments(bundle):
    source = bundle['inputs']['canonical']
    protocol = bundle['tables']['membership'][0]['protocol_id']
    member = min(bundle['tables']['membership'], key=lambda m: (m['collection_date'], m['physical_sample_id']))
    assay = next(a for a in source['edna_assay'] if a['assay_id'] == member['assay_id'])
    sample = next(s for s in source['edna_sample'] if s['sample_id'] == assay['sample_id'])
    sample.update(source_snapshot_id=digest('snapshot'), source_file_id=digest('file'))
    base = next(d for d in source['edna_detection'] if d['assay_id'] == assay['assay_id'])
    for index, (name, rank) in enumerate([('Fixture a', 'species'), ('Fixture b', 'species'),
        ('Fixture c', 'species'), ('UnresolvedA', 'genus'), ('UnresolvedB', 'genus')]):
        row = {**base, 'assignment_method': bundle['recipe']['assignment_method'], 'read_count': 100 + index,
               'detection_id': digest(name), 'source_row_hash': digest('row' + name),
               'class': bundle['recipe']['fish_classes'][0],
               'taxonomy_json': {'class': bundle['recipe']['fish_classes'][0],
                   'genus': name.split()[0], 'species': name if rank == 'species' else 'unidentified ' + name}}
        source['edna_detection'].append(row)
    for d in source['edna_detection']:
        d.setdefault('source_row_hash', digest(d['detection_id']))
    assay['community_availability_json'][bundle['recipe']['assignment_method']]['row_count'] += 5
    result = sample_taxonomy_fallback(bundle, protocol)
    assert result['status'] == 'verified_labelled_miyagi_replacement'
    assert not result['original_otsuchi_reproduced']
    assert len(result['complete_fish_assignments']) > 5
    assert [r['rank'] for r in result['illustrated_assignments']] == ['species'] * 3 + ['genus'] * 2
    assert {r['name'] for r in result['illustrated_assignments'] if r['rank'] == 'genus'} == {'UnresolvedA', 'UnresolvedB'}
    assert result['assay_evidence_path'].startswith('/data?view=edna&sample_id=')
    assert result['provenance_path'].startswith('/provenance?view=trace&doc_id=edna_')
    assert all(r['detection_ids'] for r in result['illustrated_assignments'])
