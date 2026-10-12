"""Independent arithmetic and evidence-state checks for the offline package."""
from copy import deepcopy
import json

import pytest

from evaluation.qa.conference_demo import genus_inspection, independent_counts, verify, verify_registration
from ingestion.immutable_bundle import canonical_bytes, digest, seal_bundle
from ingestion.provisional_research_bundle import build_demo
from tests.test_provisional_research_demo import fixture


@pytest.fixture
def bundle():
    recipe, inputs = fixture()
    preview = build_demo(recipe, inputs)
    return {'manifest': {'id': preview['analysis_id'], 'schema_version': 3},
            **{k: preview[k] for k in ('recipe', 'inputs', 'tables')}}


def test_all_rows_reconcile_and_corrupt_denominators_fail(bundle):
    result = independent_counts(bundle)
    assert result['rate_rows_checked'] == sum(len(bundle['tables'][t]) for t in ('ranking', 'series'))
    corrupted = deepcopy(bundle)
    corrupted['tables']['series'][-1]['eligible'] += 1
    with pytest.raises(ValueError, match='does not reconcile'):
        independent_counts(corrupted)


def test_unavailable_or_incomplete_assay_cannot_be_recorded_non_detection(bundle):
    protocol = bundle['tables']['membership'][0]['protocol_id']
    inspection = genus_inspection(bundle, protocol)
    assert len(inspection['rows']) == inspection['eligible']
    selected = inspection['rows'][0]['assay_id']
    changed = deepcopy(bundle)
    assay = next(a for a in changed['inputs']['canonical']['edna_assay'] if a['assay_id'] == selected)
    raw = assay['community_availability_json']
    raw = json.loads(raw) if isinstance(raw, str) else raw
    raw[changed['recipe']['assignment_method']]['row_count'] += 1
    assay['community_availability_json'] = raw
    again = genus_inspection(changed, protocol)
    assert again['selected_month'] == inspection['selected_month']
    assert next(r for r in again['rows'] if r['assay_id'] == selected)['status'] == 'evidence_unavailable'
    assert again['geometry_status'] == 'unverified_no_map' and again['species_claim'] is False


def test_preview_parity_never_implies_sealed_or_conference_readiness(bundle):
    protocol = bundle['tables']['membership'][0]['protocol_id']
    years = {str(y): sum(m['year'] == y for m in bundle['tables']['membership']) for y in range(2020, 2024)}
    manifest = {'analysis_id': bundle['manifest']['id'], 'protocol_id': protocol,
                'canonical_source_sha256': digest(bundle['inputs']['canonical']),
                'expected_miseq_year_units': years,
                'expected_protocol_units': {protocol[:8]: len(bundle['tables']['membership'])},
                'organizer_examples': {'otsuchi': {'status': 'unverified'}}}
    report, answers, _ = verify(bundle, manifest, sealed=False)
    assert report['analysis_identity_matches'] and report['expected_counts_match']
    # This synthetic cohort is outside Miyagi, so the full conference question
    # must fail even though its arithmetic and source hash reconcile.
    assert not report['japanese_english_row_parity'] and answers['en'] and answers['ja']
    assert not report['exact_artifact_verification_passed'] and not report['conference_ready']
    manifest['analysis_id'] = '0' * 64
    report, _, _ = verify(bundle, manifest, sealed=True)
    assert not report['exact_artifact_verification_passed']


@pytest.mark.parametrize('corruption', [None, 'receipt', 'manifest', 'recipe', 'object', 'generation', 'file_set'])
def test_sealed_registration_is_bound_to_index_receipt_and_complete_bytes(tmp_path, corruption):
    import hashlib
    identity = 'a' * 64
    staging = tmp_path / 'staging'
    staging.mkdir()
    recipe = {'assignment_method': 'qcauto_95pct_3nn_target'}
    (staging / 'recipe.json').write_bytes(canonical_bytes(recipe))
    manifest = seal_bundle(staging, tmp_path, identity, {'schema_version': 3})
    bundle_path = tmp_path / identity
    metadata = {'manifest_sha256': digest(manifest), 'recipe_sha256': digest(recipe)}
    receipt = {'schema_version': 1, 'namespace': 'provisional-demos', 'id': identity,
               'metadata': metadata, 'files': {
                   p.name: {'size': len(p.read_bytes()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                            'generation': 123} for p in bundle_path.iterdir()}}
    if corruption == 'manifest':
        metadata['manifest_sha256'] = '0' * 64
    elif corruption == 'recipe':
        metadata['recipe_sha256'] = '0' * 64
    elif corruption == 'object':
        receipt['files']['recipe.json']['sha256'] = '0' * 64
    elif corruption == 'generation':
        receipt['files']['recipe.json']['generation'] = 0
    elif corruption == 'file_set':
        receipt['files'].pop('recipe.json')
    entry = {'metadata': metadata, 'receipt_sha256': digest(receipt)}
    index = {'schema_version': 1, 'entries': {identity: entry}}
    if corruption == 'receipt':
        receipt['id'] = 'b' * 64
    index_path, receipt_path = tmp_path / 'index.json', tmp_path / 'receipt.json'
    index_path.write_bytes(canonical_bytes(index))
    receipt_path.write_bytes(canonical_bytes(receipt))
    if corruption:
        with pytest.raises(ValueError):
            verify_registration(bundle_path, index_path, receipt_path)
    else:
        result = verify_registration(bundle_path, index_path, receipt_path)
        assert result['registration_verified'] and result['registered_file_count'] == 2
        assert result['scope'] == 'retained_index_and_receipt_not_live_serving_state'
