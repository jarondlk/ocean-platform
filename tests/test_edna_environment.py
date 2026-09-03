import json

import pytest

from preprocessing.edna_analysis import build_analysis
from preprocessing.edna_recipe import AnalysisRecipe
from retrieval.edna_environment_linker import EnvironmentObservation, distance_km
from tests.test_edna_analysis import fixture


def environmental_fixture():
    recipe, source = fixture()
    sample = source['edna_sample'][0]
    sample['raw_metadata_json'] = json.dumps({'depth':'0', 'depth_unit':'m', 'temp':'12', 'temp_unit':'degC'})
    data = recipe.model_dump()
    data['metadata_fields'] = [dict(variable='depth', value_key='depth', unit_key='depth_unit', unit='m', reference='synthetic contract'),
                               dict(variable='temperature', value_key='temp', unit_key='temp_unit', unit='degC', reference='synthetic contract')]
    data['sites'] = [dict(sample_id=sample['sample_id'], site_id='site-1', domain_id='bay-1', reference='synthetic registry', source_sha256='a'*64, coordinate_uncertainty_km=0)]
    data['linkage_profile'] = dict(profile_id='synthetic-profile', reviewed_by='fixture', reference='synthetic only', domain_id='bay-1',
        lat_min=38, lat_max=39, lon_min=141, lon_max=142, max_distance_km=1, max_time_hours=24,
        max_depth_difference_m=1, min_valid_fraction=0.9, max_coordinate_uncertainty_km=0.1)
    target = dict(observation_id='ctd-fixture', source_type='ctd', measurement_type='ctd_bulk', variable='temperature', value=11.5, unit='degC',
        lat=38.4, lon=141.5, depth_m=0, time_start='2026-09-01T12:00:00Z', domain_id='bay-1',
        coordinate_basis='measured', coordinate_uncertainty_km=0, source_file_id='ctd-fixture', source_sha256='a'*64,
        source_row_locator='2', source_reference='synthetic CTD fixture', quality_status='valid')
    return AnalysisRecipe.model_validate(data), source, target


def test_qualified_environment_preserves_precision_and_units():
    recipe, source, target = environmental_fixture()
    result = build_analysis(recipe, source, [target])
    link = result['tables']['environment_links'][0]
    assert link['status'] == 'qualified' and link['selected']
    assert link['time_separation_max_hours'] == 12
    assert link['time_separation_min_hours'] == 0
    assert len(result['tables']['environment_pairs']) == 4
    assert all(r['spearman_rho'] is None for r in result['tables']['associations'])
    assert distance_km({'lat':0,'lon':0}, {'lat':0,'lon':1}) == pytest.approx(111.195, abs=0.001)


@pytest.mark.parametrize('change,reason', [
    ({'lat':39.1}, 'outside_reviewed_domain'),
    ({'lat':38.8}, 'distance_exceeded'),
    ({'domain_id':'other'}, 'domain_unverified'),
    ({'time_start':'2019-01-01'}, 'time_window_exceeded'),
    ({'depth_m':20}, 'depth_unavailable_or_incompatible'),
    ({'quality_status':'unknown'}, 'quality_not_validated'),
])
def test_linking_fails_closed(change, reason):
    recipe, source, target = environmental_fixture()
    result = build_analysis(recipe, source, [{**target, **change}])
    assert result['tables']['environment_links'][0]['status'] == reason
    assert not result['tables']['environment_links'][0]['selected']


def test_sst_coverage_and_no_legacy_coordinate_basis():
    recipe, source, target = environmental_fixture()
    with pytest.raises(ValueError):
        EnvironmentObservation.model_validate({**target, 'coordinate_basis':'bay_centroid'})
    sst = {**target, 'source_type':'remote_sensing', 'measurement_type':'sst_skin', 'footprint':[38,38.3,141,142], 'valid_fraction':1}
    assert build_analysis(recipe, source, [sst])['tables']['environment_links'][0]['status'] == 'outside_sst_footprint'
    sst['footprint'] = [38,39,141,142]
    sst['valid_fraction'] = None
    assert build_analysis(recipe, source, [sst])['tables']['environment_links'][0]['status'] == 'insufficient_sst_coverage'
    sst.update(valid_fraction=1, measurement_type='sst_regional')
    assert build_analysis(recipe, source, [sst])['tables']['environment_links'][0]['status'] == 'regional_context_disabled'


def test_unknown_unit_and_no_profile_are_unavailable():
    recipe, source, target = environmental_fixture()
    source['edna_sample'][0]['raw_metadata_json'] = '{"depth":"0","depth_unit":"feet"}'
    result = build_analysis(recipe, source, [target])
    assert all(row['value'] is None for row in result['tables']['metadata'])
    assert result['tables']['environment_links'][0]['status'] == 'depth_unavailable_or_incompatible'
    recipe = recipe.model_copy(update={'linkage_profile':None})
    assert build_analysis(recipe, source, [target])['tables']['environment_links'][0]['status'] == 'linkage_disabled'
