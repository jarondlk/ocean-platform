"""Synthetic boundary checks for the source-specific beta SST conversion."""
from __future__ import annotations

import copy
from datetime import date, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('beta_sst_preparation',
    ROOT / 'deploy/gcp/beta/data/prepare_sst.py')
preparation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparation)
GAPS = {'2021-02-20', '2021-02-21', '2022-11-09', '2023-04-22', '2023-12-01', '2023-12-02'}


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


def synthetic_period():
    first = date(2020, 1, 1)
    rows = []
    for index in range(1461):
        day = (first + timedelta(days=index)).isoformat()
        if day in GAPS:
            continue
        rows.append({'observation_id':hashlib.sha256(('synthetic:' + day).encode()).hexdigest(),
            'area_id':'miyagi-regional-demo', 'area_is_reviewed':False,
            'native_sample_area_evidence':False, 'scientific_publication':False,
            'measurement_type':'satellite_in_situ_analysis', 'processing_generation':'final',
            'product_version':'04.1', 'temporal_statistic':'daily_foundation_analysis',
            'raw_sha256':hashlib.sha256(('synthetic-raw:' + day).encode()).hexdigest(),
            'time_utc':day + 'T09:00:00+00:00', 'sst_celsius':float(index % 30),
            'status':'valid', 'valid_fraction':0.9, 'valid_ocean_points':90,
            'warnings':['missing_ice_fraction_open_sea_mask_used']})
    return {'schema_version':1, 'algorithm':'historical-regional-context-period-preview-v1',
        'status':'complete_unpublished_regional_context_preview', 'scientific_approval':False,
        'scientific_publication':False, 'area_id':'miyagi-regional-demo',
        'period':{'first_year':2020, 'last_year':2023}, 'definition':{
            'diagnostic_rectangle':{'south':38.0, 'north':39.0, 'west':141.0, 'east':142.0},
            'grid_step_degrees':0.05, 'proposed_quality':{'scientific_approval':False,
                'status':'proposed', 'weighting':'cosine_latitude_grid_point_approximation',
                'max_analysis_error_k':1.0, 'max_sea_ice_fraction':0.15,
                'min_valid_ocean_fraction':0.8, 'min_valid_ocean_points':5,
                'missing_ice_policy':'use_open_sea_mask_with_warning'}},
        'observations':rows, 'final_series_gaps':[{'day':day, 'reason':'interim_generation'} for day in sorted(GAPS)]}


def convert(source):
    data = encoded(source)
    return preparation.regional_dataset(data, source_sha256=hashlib.sha256(data).hexdigest())


def test_synthetic_complete_roundtrip_preserves_values_times_and_provisional_status(tmp_path):
    from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
    from ingestion.sst_catalogue_inputs import load_dataset
    from retrieval.source_scope import EvidenceScope, FAMILIES
    from schema.catalogue_snapshot import SnapshotManifest, SourceCapture
    source = synthetic_period()
    metadata, frames, captured = convert(source)
    rows = frames['observations'].to_dict('records')
    assert len(rows) == 1455
    assert [row['value'] for row in rows] == [row['sst_celsius'] for row in source['observations']]
    assert [row['time'] for row in rows] == [row['time_utc'] for row in source['observations']]
    assert [row['source_sha256'] for row in rows] == [row['raw_sha256'] for row in source['observations']]
    assert all(row['uncertainty'] is None and row['ocean_pixels'] is None for row in rows)
    assert all(row['lat'] is None and row['lon'] is None for row in rows)
    assert all('missing_ice_fraction_open_sea_mask_used' in row['quality_flag'] for row in rows)
    assert metadata.sampling.start == '2020-01-01' and metadata.sampling.end == '2023-12-31'
    assert metadata.processing_generation == 'final'
    assert metadata.observation_entity == 'regional_daily_summary'
    assert metadata.observation_precision == 'datetime'
    assert metadata.descriptor.spatial_resolution == 0.05
    assert metadata.related_ids == []
    assert 'not reviewed' in metadata.qualification
    scope = EvidenceScope.model_validate({'version':1, 'sources':{
        family:{'enabled':family == 'remote_sensing', 'filters':{}} for family in FAMILIES}})
    manifest = SnapshotManifest(scope=scope, source_captures=[SourceCapture(
        source_id=metadata.source_id, source_family='remote_sensing', source_generation=captured.objects[0].provenance.source_generation,
        publication_generation='synthetic-unapproved', classification_generation='none',
        relationship_generation='none', operation_generation='c11-v1', capture_method='synthetic',
        qualifiers=list(preparation.QUALIFICATIONS))], objects=list(captured.objects),
        operation_versions={obj.operation_id:obj.operation_version for obj in captured.objects})
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda manifest: True)
    identity = store.seal(manifest, dict(captured.contents))
    sealed_manifest, contents = store.read(identity)
    obj = next(obj for obj in sealed_manifest.objects if obj.role == 'dataset_metadata')
    loaded = load_dataset(sealed_manifest, contents, obj)
    assert loaded.tables['observations'].to_dict('records') == sorted(rows, key=lambda row: row['observation_id'])
    assert loaded.metadata.model_dump(mode='json') == metadata.model_dump(mode='json')
    assert store.latest() == (None, 0)


@pytest.mark.parametrize('mutation', [
    lambda s:s.update(scientific_approval=True),
    lambda s:s.update(scientific_publication=True),
    lambda s:s.update(status='published'),
    lambda s:s.update(area_id='confirmed-sample-footprint'),
    lambda s:s.update(schema_version=True),
    lambda s:s['definition'].update(grid_step_degrees=True),
    lambda s:s['definition'].update(grid_step_degrees=0.01),
    lambda s:s['definition']['diagnostic_rectangle'].update(north=40.0),
    lambda s:s['definition']['proposed_quality'].update(scientific_approval=True),
    lambda s:s['definition']['proposed_quality'].update(status='approved'),
    lambda s:s['definition']['proposed_quality'].update(max_analysis_error_k=True),
    lambda s:s['period'].update(first_year=2019),
    lambda s:s['period'].update(last_year=True),
    lambda s:s['observations'][0].update(area_is_reviewed=True),
    lambda s:s['observations'][0].update(native_sample_area_evidence=True),
    lambda s:s['observations'][0].update(scientific_publication=True),
    lambda s:s['observations'][0].update(product_version='04.1nrt'),
    lambda s:s['observations'][0].update(processing_generation='interim'),
    lambda s:s['observations'][0].update(measurement_type='satellite_retrieval'),
    lambda s:s['observations'][0].update(temporal_statistic='daily_mean'),
    lambda s:s['observations'][0].update(time_utc='2020-01-01T09:00:00'),
    lambda s:s['observations'][0].update(time_utc='2020-01-01T00:00:00+00:00'),
    lambda s:s['observations'][0].update(sst_celsius=True),
    lambda s:s['observations'][0].update(valid_fraction=0.79),
    lambda s:s['observations'][0].update(valid_ocean_points=5.0),
    lambda s:s['observations'][0].update(valid_ocean_points=True),
    lambda s:s['observations'][0].update(raw_sha256='invalid'),
    lambda s:s['observations'][0].update(warnings=[]),
    lambda s:s['observations'].append(copy.deepcopy(s['observations'][0])),
    lambda s:s['observations'].pop(),
    lambda s:s['final_series_gaps'].pop(),
    lambda s:s['final_series_gaps'].append({'day':'2020-01-01','reason':'interim_generation'}),
    lambda s:s['final_series_gaps'][0].update(reason='newly_invented'),
    lambda s:s['final_series_gaps'][0].update(day='2021-02-30'),
])
def test_conversion_refuses_relabeling_gaps_missing_qualifiers_and_silent_coercion(mutation):
    source = synthetic_period()
    mutation(source)
    with pytest.raises(ValueError):
        convert(source)


@pytest.mark.parametrize('payload', [b'{"a":1,"a":2}', b'{"a":NaN}', b'[]', b'\xff', bytearray(b'{}')])
def test_source_parser_refuses_duplicate_nonfinite_nonobject_or_bad_bytes(payload):
    with pytest.raises(ValueError):
        preparation.parsed(payload)


def test_conversion_requires_exact_bytes_hash_and_rejects_invalid_celsius():
    data = encoded(synthetic_period())
    with pytest.raises(ValueError, match='checksum'):
        preparation.regional_dataset(data, source_sha256='0' * 64)
    source = synthetic_period()
    source['observations'][0]['sst_celsius'] = -274.0
    with pytest.raises(ValueError):
        convert(source)


def test_source_revision_guard_rejects_unknown_revision_before_git():
    with pytest.raises(ValueError, match='Explicit full'):
        preparation.source_guard('HEAD')


def test_summary_keeps_operational_preview_and_missing_source_bodies_explicit():
    data = encoded(synthetic_period())
    summary = preparation.summary(data, source_sha256=hashlib.sha256(data).hexdigest())
    assert summary['observations'] == 1455
    assert summary['retained_final_series_gaps'] == 6
    assert summary['scientific_approval'] is summary['scientific_publication'] is summary['area_is_reviewed'] is False
    assert summary['raw_granule_bodies_reverified'] is False
    assert summary['cloud_calls'] is summary['sealed_or_registered'] is False


def pinned_private_source(tmp_path, monkeypatch):
    period = encoded(synthetic_period())
    period_sha = hashlib.sha256(period).hexdigest()
    publication = encoded({'period_sha256':period_sha, 'decision':{
        'approval_basis':'explicit_user_accepted_operational_publication',
        'independent_researcher_approval':False, 'provider_endorsement':False}})
    publication_sha = hashlib.sha256(publication).hexdigest()
    registry = encoded({'id':publication_sha, 'files':{
        'period.json':{'sha256':period_sha, 'size':len(period)},
        'publication.json':{'sha256':publication_sha}}})
    registry_sha = hashlib.sha256(registry).hexdigest()
    files = {'0-current.json':encoded({'publication_id':publication_sha, 'receipt_sha256':registry_sha}),
        '1-index.json':encoded({'entries':{publication_sha:{'receipt_sha256':registry_sha}}}),
        '2-period.json':period, '3-publication.json':publication,
        '4-' + publication_sha + '.json':registry}
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    monkeypatch.setattr(preparation, 'SOURCE_FILES', {name:(len(data),hashlib.sha256(data).hexdigest())
        for name,data in files.items()})
    monkeypatch.setattr(preparation, 'PERIOD_SHA256', period_sha)
    monkeypatch.setattr(preparation, 'PUBLICATION_SHA256', publication_sha)
    monkeypatch.setattr(preparation, 'REGISTRY_SHA256', registry_sha)
    return period


def test_private_reader_reconciles_every_pinned_file_and_explicit_source_qualification(tmp_path, monkeypatch):
    expected = pinned_private_source(tmp_path, monkeypatch)
    assert preparation.verified_publication_bytes(tmp_path) == expected
    (tmp_path / '2-period.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='length'):
        preparation.verified_publication_bytes(tmp_path)


def test_private_reader_refuses_symlink_even_when_target_bytes_match(tmp_path, monkeypatch):
    pinned_private_source(tmp_path, monkeypatch)
    path = tmp_path / '2-period.json'
    destination = tmp_path / 'period-retained.json'
    path.rename(destination)
    path.symlink_to(destination)
    with pytest.raises(ValueError, match='regular'):
        preparation.verified_publication_bytes(tmp_path)
