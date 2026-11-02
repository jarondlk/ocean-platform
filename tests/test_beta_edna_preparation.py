"""Synthetic C12 projection checks; no remote source or scientific approval."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('beta_edna_preparation',
    ROOT / 'deploy/gcp/beta/data/prepare_edna.py')
preparation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparation)


def synthetic_bundle(count=4):
    from schema.edna_catalogue_fixtures import edna_fixture
    metadata, frames = edna_fixture(count)
    rows = {role:frame.astype(object).where(frame.notna(), None).to_dict('records')
        for role,frame in frames.items()}
    classifications = {row['sample_id']:row for row in rows['classifications']}
    samples = [{**row, **classifications[row['sample_id']]} for row in rows['occurrences']]
    return {'registry_id':hashlib.sha256(b'synthetic-registry').hexdigest(),
        'generation':hashlib.sha256(b'synthetic-normalization-manifest').hexdigest(),
        'source_package_sha256':preparation.SOURCE_PACKAGE_SHA256,
        'manifest':{'source_snapshot_id':samples[0]['source_snapshot_id']},
        'records':{'edna_sample':samples, 'edna_assay':rows['assays'], 'edna_detection':rows['detections']}}


def test_projection_preserves_unknown_control_nulls_counts_taxonomy_and_primitive_types(tmp_path):
    from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
    from ingestion.edna_catalogue_inputs import load_dataset
    from retrieval.source_scope import EvidenceScope, FAMILIES
    from schema.catalogue_snapshot import SnapshotManifest, SourceCapture
    from schema.edna_catalogue import TABLE_COLUMNS
    bundle = synthetic_bundle()
    result = preparation.normalized_datasets(bundle)
    assert len(result) == 1
    metadata, frames, captured = result[0]
    assert metadata.descriptor.population == 'raw_inventory'
    assert metadata.descriptor.assignment_method == metadata.descriptor.sample_kind == 'mixed'
    assert metadata.related_ids == []
    assert 'no independent scientific approval' in metadata.qualification
    sources = {'occurrences':'edna_sample', 'classifications':'edna_sample',
        'assays':'edna_assay', 'detections':'edna_detection'}
    for role, name in sources.items():
        expected = [{key:row[key] for key in TABLE_COLUMNS[role]} for row in bundle['records'][name]]
        assert frames[role].to_dict('records') == expected
    classifications = frames['classifications'].to_dict('records')
    assert classifications[1]['sample_kind'] == 'negative_control' and classifications[1]['is_control'] is True
    assert classifications[2]['sample_kind'] == 'unknown' and classifications[2]['is_control'] is None
    assert all(row['classification_review_json'] is None for row in classifications)
    assert all(row['physical_sample_id'] is None for row in frames['occurrences'].to_dict('records'))
    scope = EvidenceScope.model_validate({'version':1, 'sources':{
        family:{'enabled':family == 'edna_metabarcoding', 'filters':{}} for family in FAMILIES}})
    manifest = SnapshotManifest(scope=scope, source_captures=[SourceCapture(
        source_id=metadata.source_id, source_family='edna_metabarcoding', source_generation=bundle['generation'],
        publication_generation='synthetic-unapproved', classification_generation='synthetic-source-unchanged',
        relationship_generation='none-inferred', operation_generation='c12-v1', capture_method='synthetic',
        qualifiers=list(preparation.QUALIFICATIONS))], objects=list(captured.objects),
        operation_versions={obj.operation_id:obj.operation_version for obj in captured.objects})
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda manifest: True)
    identity = store.seal(manifest, dict(captured.contents))
    sealed_manifest, contents = store.read(identity)
    obj = next(obj for obj in sealed_manifest.objects if obj.role == 'canonical_rows')
    loaded = load_dataset(sealed_manifest, contents, obj)
    keys = {'occurrences':'sample_id', 'classifications':'sample_id', 'assays':'assay_id', 'detections':'detection_id'}
    for role, frame in frames.items():
        assert loaded.tables[role].to_dict('records') == sorted(frame.to_dict('records'), key=lambda row:row[keys[role]])
    assert store.latest() == (None, 0)


def test_provider_project_partition_keeps_all_related_rows_and_has_distinct_dataset_ids():
    bundle = synthetic_bundle()
    samples = bundle['records']['edna_sample']
    samples[1]['provider_project_id'] = 'Synthetic-Other-Project'
    result = preparation.normalized_datasets(bundle)
    assert len(result) == 2
    assert len({dataset.dataset_id for dataset,_,_ in result}) == 2
    assert sum(len(frames['occurrences']) for _,frames,_ in result) == len(samples)
    assert sum(len(frames['detections']) for _,frames,_ in result) == len(bundle['records']['edna_detection'])
    for dataset,frames,_ in result:
        assert set(frames['occurrences'].provider_project_id) == {dataset.provider_project_id}
        assert set(frames['assays'].sample_id) <= set(frames['occurrences'].sample_id)
        assert set(frames['detections'].assay_id) <= set(frames['assays'].assay_id)


@pytest.mark.parametrize('mutation', [
    lambda b:b.update(registry_id='invalid'),
    lambda b:b.update(generation='invalid'),
    lambda b:b.update(source_package_sha256='0' * 64),
    lambda b:b['records']['edna_sample'][0].pop('provider_locus'),
    lambda b:b['records']['edna_sample'][0].pop('source_occurrence_id'),
    lambda b:b['records']['edna_sample'][0].pop('classification_review_json'),
    lambda b:b['records']['edna_sample'][0].update(source_snapshot_id='f' * 64),
    lambda b:b['records']['edna_sample'][2].update(is_control=False),
    lambda b:b['records']['edna_sample'][0].update(physical_sample_id='fabricated-physical-id'),
    lambda b:b['records']['edna_sample'].append(copy.deepcopy(b['records']['edna_sample'][0])),
    lambda b:b['records']['edna_assay'][0].update(sample_id='f' * 64),
    lambda b:b['records']['edna_detection'][0].update(assay_id='f' * 64),
    lambda b:b['records']['edna_detection'][0].update(read_count=True),
    lambda b:b['records']['edna_detection'][0].update(read_count=-1),
    lambda b:b['records']['edna_detection'][0].update(assignment_method='unsupported-new-method'),
    lambda b:b['records']['edna_detection'][0].update(target_status='nontarget'),
    lambda b:b['records']['edna_detection'][0].update(taxonomy_json='{}'),
    lambda b:b['records']['edna_detection'][0].pop('concentration_status'),
    lambda b:b['records']['edna_detection'].append(copy.deepcopy(b['records']['edna_detection'][0])),
])
def test_projection_refuses_missing_identity_classification_or_method_semantics(mutation):
    bundle = synthetic_bundle()
    mutation(bundle)
    with pytest.raises(ValueError):
        preparation.normalized_datasets(bundle)


@pytest.mark.parametrize('data', [b'{"a":1,"a":2}',b'{"a":NaN}',b'[]',b'\xff',bytearray(b'{}')])
def test_metadata_reader_rejects_ambiguous_or_nonfinite_inputs(data):
    with pytest.raises(ValueError):
        preparation.parsed(data)


def test_private_regular_reader_refuses_checksum_mismatch_symlink_and_budget(tmp_path):
    path = tmp_path/'source.bin'
    path.write_bytes(b'bounded-synthetic-source')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert preparation._read(path,digest=digest) == path.read_bytes()
    with pytest.raises(ValueError):
        preparation._read(path,digest='0' * 64)
    with pytest.raises(ValueError):
        preparation._read(path,maximum=1)
    link = tmp_path/'link.bin'
    link.symlink_to(path)
    with pytest.raises(ValueError):
        preparation._read(link,digest=digest)


def test_private_roots_and_revision_guard_refuse_checkout_relative_or_unknown_inputs():
    for path in [Path('relative'), ROOT, ROOT/'data']:
        with pytest.raises(ValueError):
            preparation._private_root(path)
    with pytest.raises(ValueError):
        preparation.source_guard('HEAD')
