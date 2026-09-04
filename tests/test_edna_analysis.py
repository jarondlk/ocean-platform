from copy import deepcopy
import json
import math

import pytest

import config
from ingestion.edna_analysis_bundle import publish_analysis, load_analysis, context_documents
from preprocessing.edna_analysis import alpha, beta, build_analysis
from preprocessing.edna_recipe import AnalysisRecipe
from tests.integration.test_anemone_postgres import _frames


def fixture():
    frames, _ = _frames('science')
    source = {k:json.loads(v.to_json(orient='records')) for k,v in frames.items()}
    source['edna_detection'][0].update(genus='A', species='A one', read_count=1)
    other = dict(source['edna_detection'][0], detection_id='9'*64, sequence_sha256='8'*64, genus='B', species='B one')
    source['edna_detection'].append(other)
    for row in list(source['edna_detection']):
        source['edna_detection'].append(dict(row, detection_id=('1' if row['genus']=='A' else '3')*64, assignment_method='qcauto_95pct_3nn_target'))
    recipe = AnalysisRecipe.model_validate(dict(cohort={'provider_project_id':'project-science'},
        assignment_methods=['qcauto_target','qcauto_95pct_3nn_target'], rank='genus', control_policy='environmental_only'))
    return recipe, source


def test_alpha_beta_known_values_and_empty_conventions():
    assert alpha([1,1])['shannon'] == pytest.approx(math.log(2))
    assert alpha([1,1])['simpson_1d'] == 0.5
    assert alpha([1,1])['evenness'] == 1
    assert alpha([1])['evenness'] is None
    assert alpha([0])['shannon'] is None
    assert beta({'a':1}, {'a':100})['bray_curtis_relative_reads'] == 0
    assert beta({'a':1}, {'b':1})['jaccard_similarity'] == 0
    assert beta({}, {})['jaccard_similarity'] is None
    assert beta({}, {'a':1})['bray_curtis_relative_reads'] is None


def test_reproducible_method_separation_and_taxon_aggregation():
    recipe, source = fixture()
    result = build_analysis(recipe, source)
    assert len(result['tables']['diversity']) == 2
    assert all(r['richness'] == 2 for r in result['tables']['diversity'])
    assert all(r['status'] == 'exact_agreement' for r in result['tables']['methods'])
    shuffled = {k:list(reversed(v)) for k,v in source.items()}
    assert build_analysis(recipe, shuffled) == result
    duplicate = dict(source['edna_detection'][0], detection_id='4'*64, sequence_sha256='5'*64)
    source['edna_detection'].append(duplicate)
    changed = build_analysis(recipe, source)
    row = next(r for r in changed['tables']['diversity'] if r['assignment_method']=='qcauto_target')
    assert row['richness'] == 2 and row['retained_reads'] == 3
    assert changed['analysis_id'] != result['analysis_id']


def test_controls_unknowns_unresolved_taxa_and_missing_method():
    recipe, source = fixture()
    source['edna_sample'][0]['is_control'] = None
    result = build_analysis(recipe, source)
    assert result['tables']['diversity'] == []
    assert all(r['reason'] == 'control_or_unknown' for r in result['tables']['membership'])
    assert all(r['status'] == 'not_assessed' for r in result['tables']['controls'])
    source['edna_sample'][0]['is_control'] = False
    source['edna_detection'] = [dict(source['edna_detection'][0], genus=None, species=None)]
    result = build_analysis(recipe, source)
    assert result['tables']['diversity'][0]['richness'] == 0
    assert any(r['reason'] == 'method_unavailable' for r in result['tables']['membership'])


def test_control_overlap_does_not_subtract_and_protocol_partitions_do_not_pool():
    recipe, source = fixture()
    sample = dict(source['edna_sample'][0], sample_id='6'*64, sample_kind='negative_control', is_control=True, lat=None, lon=None)
    assay = dict(source['edna_assay'][0], assay_id='7'*64, sample_id=sample['sample_id'])
    control = dict(source['edna_detection'][0], assay_id=assay['assay_id'], detection_id='8'*64, read_count=100)
    source['edna_sample'].append(sample)
    source['edna_assay'].append(assay)
    source['edna_detection'].append(control)
    original = deepcopy(source)
    result = build_analysis(recipe, source)
    assert result['tables']['control_overlap']
    assert all(r['retained_reads']==2 for r in result['tables']['diversity'])
    assert source == original


def test_recipe_and_resource_limits():
    recipe, source = fixture()
    with pytest.raises(ValueError):
        AnalysisRecipe.model_validate({**recipe.model_dump(), 'rank':'mixed'})
    with pytest.raises(ValueError):
        AnalysisRecipe.model_validate({**recipe.model_dump(), 'cohort':{}})
    with pytest.raises(ValueError, match='Taxon'):
        build_analysis(recipe.model_copy(update={'max_taxa':1}), source)


def test_immutable_publication_recovery_freshness_and_context(tmp_path, monkeypatch):
    recipe, source = fixture()
    monkeypatch.setattr(config, 'ANALYSIS_DIR', tmp_path)
    monkeypatch.setattr('ingestion.edna_analysis_bundle.read_canonical', lambda _: source)
    result = build_analysis(recipe, source)
    manifest = publish_analysis(result)
    assert publish_analysis(result) == manifest
    bundle = load_analysis(result['analysis_id'])
    assert bundle['recipe'] == recipe.model_dump()
    scope = dict(analysis_id=result['analysis_id'], provider_project_id='project-science')
    assert context_documents(scope)
    assert context_documents({**scope, 'taxon':'A'}) == []
    source['edna_detection'][0]['read_count'] = 5
    assert context_documents(scope) == []
    assert load_analysis(result['analysis_id'])['inputs']['canonical']['edna_detection']
    path = tmp_path/'edna'/result['analysis_id']/'diversity.json'
    path.write_text('[]')
    with pytest.raises(ValueError, match='integrity'):
        load_analysis(result['analysis_id'])


def test_turnover_protocol_partitions_and_method_disagreements():
    recipe, source = fixture()
    sample = dict(source['edna_sample'][0], sample_id='6'*64)
    assay = dict(source['edna_assay'][0], assay_id='7'*64, sample_id=sample['sample_id'])
    source['edna_sample'].append(sample)
    source['edna_assay'].append(assay)
    source['edna_detection'].append(dict(source['edna_detection'][0], detection_id='0'*64, assay_id=assay['assay_id'], read_count=100))
    result = build_analysis(recipe, source)
    turnover = result['tables']['turnover']
    assert len(turnover) == 1
    assert turnover[0]['jaccard_similarity'] == 0.5
    assert turnover[0]['bray_curtis_relative_reads'] == 0.5
    assert turnover[0]['pair_type'] == 'site_unresolved'
    assert any(row['status'] == 'method_only_sequence' for row in result['tables']['methods'])
    source['edna_assay'][-1]['primer_set'] = 'different protocol'
    assert not build_analysis(recipe, source)['tables']['turnover']
    # The same taxon name with an incompatible ancestor remains a separate key.
    source['edna_detection'].append(dict(source['edna_detection'][0], detection_id='4'*64, sequence_sha256='5'*64, family='Other family'))
    row = next(r for r in build_analysis(recipe, source)['tables']['diversity'] if r['assay_id'] != assay['assay_id'] and r['assignment_method']=='qcauto_target')
    assert row['richness'] == 3


@pytest.mark.parametrize('change,status', [({'genus':'Other'}, 'conflicting_assignment'),
                                         ({'species':None}, 'compatible_resolution'),
                                         ({k:None for k in ('superkingdom','kingdom','phylum','class','order','family','genus','species')}, 'unassigned')])
def test_sequence_paired_method_status(change, status):
    recipe, source = fixture()
    source['edna_detection'][2].update(change)
    rows = build_analysis(recipe, source)['tables']['methods']
    assert any(row['status'] == status for row in rows)


def test_analysis_snapshot_size_limit_never_truncates(monkeypatch):
    recipe, source = fixture()
    monkeypatch.setattr('preprocessing.edna_analysis.MAX_ANALYSIS_BYTES', 1)
    with pytest.raises(ValueError, match='byte resource'):
        build_analysis(recipe, source)


def test_analysis_snapshot_provenance_roundtrip(tmp_path, monkeypatch):
    from api.provenance_snapshot_service import ProvenanceSnapshotService
    from ingestion.edna_analysis_bundle import provenance_descriptors, analysis_trace
    from ingestion.provenance_snapshot import prepare_snapshot, publish_snapshot, LocalSnapshotStore, SnapshotError
    from tests.test_provenance_snapshot import _manifest
    recipe, source = fixture()
    monkeypatch.setattr(config, 'ANALYSIS_DIR', tmp_path/'analysis')
    result = build_analysis(recipe, source)
    publish_analysis(result)
    manifest = _manifest()
    manifest['edna_analyses'] = provenance_descriptors()
    snapshot = prepare_snapshot(manifest, manifest_id='edna-analysis-test')
    store = LocalSnapshotStore(tmp_path/'provenance')
    publish_snapshot(snapshot, store=store)
    service = ProvenanceSnapshotService(store=store)
    doc_id = f"analysis_edna_{result['analysis_id']}_diversity"
    assert service.trace_payload(doc_id)['trace'] == analysis_trace(doc_id, manifest['edna_analyses'])['trace']
    assert service.manifest_payload(limit_documents=100, include_embeddings=True)['edna_analyses'] == manifest['edna_analyses']
    changed = deepcopy(manifest)
    changed['edna_analyses'][0]['recipe']['rank'] = 'species'
    with pytest.raises(SnapshotError, match='Incomplete eDNA analysis'):
        prepare_snapshot(changed, manifest_id='invalid')
