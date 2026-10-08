"""Immutable user-accepted regional evidence for the ordinary product surfaces.

Operational publication keeps the original scientific decisions and analysis
identities intact. It does not manufacture a provider or researcher approval.
"""
from datetime import date, datetime, timedelta
from functools import lru_cache
import json
import math

from pydantic import Field
from typing import Literal

import config
from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import canonical_bytes, digest, validate_id
from preprocessing.research_recipe import Hash, ResearchModel

NAMESPACE = 'regional-publications'
MAX_BYTES = 16 * 1024 * 1024
DATASET = 'mur-miyagi-2020-2023'
LABEL = 'MUR v4.1 · Miyagi · 2020–2023'
NOTES = [
    'Regional foundation SST uses 0.05-degree grid-point subsampling and cosine-latitude weighting; it is not an hourly station measurement or native sample-point temperature.',
    'Only final 04.1 observations with uncertainty ≤1°C and at least 80% valid open-ocean support are included. Missing ice fractions use the open-sea mask with a warning.',
    'Known final-series gaps remain empty; retained interim 04.1nrt data is excluded.',
    'Linked fish frequencies use singleton occurrence proxies with unresolved physical/environmental identities. Known controls and unresolved repeat groups stay excluded; protocols and assignment methods stay separate.',
    'Read counts are sequencing signals, not fish abundance. Temperature comparisons are associations, not evidence of weather causation.',
]


class PublicationDecision(ResearchModel):
    decision_origin: Literal['user']
    approval_basis: Literal['explicit_user_accepted_operational_publication']
    user_instruction: str = Field(min_length=1, max_length=4000)
    recorded_at_utc: datetime
    period_preview_id: Hash
    analysis_ids: tuple[Hash, ...] = Field(min_length=2, max_length=2)
    independent_researcher_approval: Literal[False] = False
    provider_endorsement: Literal[False] = False


def validate_period(period):
    identity = validate_id(period.get('period_preview_id'))
    if digest({k: v for k, v in period.items() if k != 'period_preview_id'}) != identity:
        raise ValueError('Regional period integrity failure')
    if (period.get('status') != 'complete_unpublished_regional_context_preview'
            or period.get('scientific_approval') is not False
            or period.get('scientific_publication') is not False
            or period.get('native_sample_area_evidence') is not False
            or period.get('period') != {'first_year': 2020, 'last_year': 2023}
            or period.get('definition', {}).get('grid_step_degrees') != 0.05
            or period['definition'].get('diagnostic_rectangle') != {'west': 141.0, 'east': 142.0, 'south': 38.0, 'north': 39.0}):
        raise ValueError('Unsupported regional publication scope')
    days = set()
    for row in period['observations']:
        if digest({k: v for k, v in row.items() if k != 'observation_id'}) != row['observation_id']:
            raise ValueError('Regional observation integrity failure')
        when = datetime.fromisoformat(row['time_utc'])
        day = when.date().isoformat()
        if (when.tzinfo is None or when.utcoffset() != timedelta(0)
                or day in days or not '2020-01-01' <= day <= '2023-12-31'
                or row['area_id'] != period['area_id']
                or row['processing_generation'] != 'final' or row['product_version'] != '04.1'
                or row['status'] != 'valid' or not math.isfinite(row['sst_celsius'])
                or not math.isfinite(row['valid_fraction']) or not 0.8 <= row['valid_fraction'] <= 1.0
                or type(row['valid_ocean_points']) is not int or row['valid_ocean_points'] < 5
                or row['measurement_type'] != 'satellite_in_situ_analysis'
                or row['temporal_statistic'] != 'daily_foundation_analysis'
                or row.get('native_sample_area_evidence') is not False
                or row.get('scientific_publication') is not False):
            raise ValueError('Invalid final regional observation')
        days.add(day)
    gaps = [r['day'] for r in period['final_series_gaps']]
    expected = {(date(2020, 1, 1) + timedelta(days=i)).isoformat() for i in range(1461)}
    if len(gaps) != len(set(gaps)) or days & set(gaps) or days | set(gaps) != expected:
        raise ValueError('Regional coverage does not reconcile')
    return identity


def validate_payload(payload, period):
    if set(payload) != {'schema_version', 'dataset_id', 'label', 'period_sha256', 'decision', 'analyses', 'notes'} or payload['schema_version'] != 1 or payload['dataset_id'] != DATASET or payload['label'] != LABEL or payload['notes'] != NOTES:
        raise ValueError('Unknown regional publication contract')
    decision = PublicationDecision.model_validate(payload['decision'])
    if decision.independent_researcher_approval or decision.provider_endorsement or decision.recorded_at_utc.tzinfo is None:
        raise ValueError('Operational acceptance is not scientific endorsement')
    if validate_period(period) != decision.period_preview_id or digest(period) != payload['period_sha256']:
        raise ValueError('Regional publication decision binding failure')
    if set(payload['analyses']) != set(decision.analysis_ids):
        raise ValueError('Regional analysis decision binding failure')
    for identity, row in payload['analyses'].items():
        validate_id(identity)
        validate_id(row['manifest_sha256'])
    if {r['assignment_method'] for r in payload['analyses'].values()} != {'qcauto_target', 'qcauto_95pct_3nn_target'}:
        raise ValueError('Both distinct assignment methods are required')


def prepare_regional(decision):
    """Read-only preflight of current sealed analyses and explicit acceptance."""
    from ingestion.edna_analysis_bundle import load_analysis, analysis_status
    decision = PublicationDecision.model_validate(decision).model_dump(mode='json')
    analyses, period = {}, None
    for identity in decision['analysis_ids']:
        bundle = load_analysis(identity)
        if bundle['manifest'].get('schema_version') != 3 or analysis_status(bundle) != 'current':
            raise ValueError('Regional analysis is unavailable or stale')
        candidate = bundle['inputs']['period_preview']
        if period is not None and digest(period) != digest(candidate):
            raise ValueError('Regional analyses use different SST evidence')
        period = candidate
        analyses[identity] = {'manifest_sha256': digest(bundle['manifest']), 'assignment_method': bundle['recipe']['assignment_method']}
    payload = dict(schema_version=1, dataset_id=DATASET, label=LABEL,
                   period_sha256=digest(period), decision=decision, analyses=analyses, notes=NOTES)
    validate_payload(payload, period)
    return payload, period


def publish_regional(decision, *, store=None):
    payload, period = prepare_regional(decision)
    analyses = payload["analyses"]
    identity = digest(payload)
    store = store or ArtifactStore(config.EDNA_ARTIFACT_URI)
    receipt = store.publish(NAMESPACE, identity, {'publication.json': canonical_bytes(payload), 'period.json': canonical_bytes(period)})
    # Read-back validates the exact retained generations before activation.
    _read_publication(store, identity, digest(receipt))
    pointer, generation = store.pointer(NAMESPACE + '/current.json')
    next_pointer = {'schema_version': 1, 'publication_id': identity, 'receipt_sha256': digest(receipt)}
    if pointer != next_pointer:
        store.replace_pointer(NAMESPACE + '/current.json', next_pointer, generation)
    return {'publication_id': identity, 'receipt_sha256': digest(receipt), 'dataset_id': DATASET,
            'days': len(period['observations']), 'gaps': period['final_series_gaps'], 'analyses': analyses}


def _read_publication(store, identity, receipt_sha256=None):
    receipt, files = store.read(NAMESPACE, validate_id(identity), max_bytes=MAX_BYTES)
    if ((receipt_sha256 is not None and digest(receipt) != validate_id(receipt_sha256))
            or set(files) != {'publication.json', 'period.json'}):
        raise ValueError('Regional publication receipt integrity failure')
    payload, period = json.loads(files['publication.json']), json.loads(files['period.json'])
    if digest(payload) != identity:
        raise ValueError('Regional publication identity failure')
    validate_payload(payload, period)
    return {'publication_id': identity, 'payload': payload, 'period': period}


@lru_cache(maxsize=4)
def _cached_publication(uri, identity, receipt_sha256):
    return _read_publication(ArtifactStore(uri), identity, receipt_sha256)


def current_publication():
    if not config.EDNA_ARTIFACT_URI:
        return None
    pointer, _ = ArtifactStore(config.EDNA_ARTIFACT_URI).pointer(NAMESPACE + '/current.json')
    if pointer is None:
        return None
    if set(pointer) != {'schema_version', 'publication_id', 'receipt_sha256'} or pointer['schema_version'] != 1:
        raise ValueError('Invalid regional publication pointer')
    return _cached_publication(config.EDNA_ARTIFACT_URI, pointer['publication_id'], pointer['receipt_sha256'])


def analysis_publication(bundle):
    if bundle['manifest'].get('schema_version') != 3:
        return None
    publication = current_publication()
    if publication:
        bound = publication['payload']['analyses'].get(bundle['manifest']['id'])
        if bound and bound['manifest_sha256'] == digest(bundle['manifest']):
            return {'publication_id': publication['publication_id'], 'label': LABEL,
                    'approval_basis': 'explicit_user_accepted_operational_publication'}
    return None


def daily_rows(publication):
    return [{'date_jst': r['time_utc'][:10], 'mean_sst': r['sst_celsius'], 'min_sst': None, 'max_sst': None,
             'dataset_id': DATASET, 'observation_id': r['observation_id'], 'warnings': r['warnings']}
            for r in publication['period']['observations']]


def documents(publication):
    identity = publication['publication_id']
    period = publication['period']
    shared = {'dataset_id': DATASET, 'publication_id': identity, 'product': 'MUR v4.1',
              'area_id': period['area_id'], 'region_bounds': period['definition']['diagnostic_rectangle'],
              'processing_generation': 'final', 'grid_step_degrees': 0.05,
              'measurement_type': 'satellite_in_situ_analysis', 'temporal_statistic': 'daily_foundation_analysis',
              'operational_acceptance': 'user', 'independent_researcher_approval': False, 'provider_endorsement': False}
    result = []
    for row in period['observations']:
        day = row['time_utc'][:10]
        result.append({'doc_id': 'mur_' + row['observation_id'], 'source_type': 'remote_sensing',
                       'time': row['time_utc'], 'title': f'Miyagi MUR regional SST {day}',
                       'metadata': {**shared, 'observation_id': row['observation_id'], 'source_url': row['source_url'],
                                    'raw_sha256': row['raw_sha256'], 'warnings': row['warnings']},
                       'text': f"Miyagi coastal regional SST on {day}: {row['sst_celsius']:.6g}°C. Final MUR 04.1 daily foundation analysis, satellite and in-situ input. Region 38–39N, 141–142E. Valid open-ocean grid points: {row['valid_ocean_points']}; valid fraction: {row['valid_fraction']}. " + ' '.join(NOTES[:2])})
    return result


def publication_trace(identity):
    """Read retained publication lineage independently of the current pointer.

    This publication-wide trace does not claim every retained observation was
    supplied for an answer; the frozen citation metadata records answer scope.
    """
    from ingestion.provenance_snapshot import SnapshotNotFound
    validate_id(identity)
    doc_id = 'regional_publication_' + identity
    if not config.EDNA_ARTIFACT_URI:
        return {'doc_id': doc_id, 'found': False, 'trace': {}}
    try:
        publication = _read_publication(ArtifactStore(config.EDNA_ARTIFACT_URI), identity)
    except SnapshotNotFound:
        return {'doc_id': doc_id, 'found': False, 'trace': {}}
    payload, period = publication['payload'], publication['period']
    return {
        'doc_id': doc_id, 'found': True,
        'trace': {
            'document': {'doc_id': doc_id, 'source_type': 'remote_sensing', 'title': LABEL,
                         'text': 'Publication-wide retained lineage; the citation metadata records the answer scope.',
                         'metadata': {**payload, 'publication_id': identity,
                                      'period_preview_id': period['period_preview_id'],
                                      'days': len(period['observations']),
                                      'final_series_gaps': period['final_series_gaps']},
                         'lineage_level': 'immutable_regional_publication'},
            'embedding': {'embedding_status': 'not_applicable'},
            'artifacts': [{'id': identity, 'sha256': identity,
                           'path': NAMESPACE + '/objects/' + identity + '/publication.json'},
                          {'id': period['period_preview_id'], 'sha256': payload['period_sha256'],
                           'path': NAMESPACE + '/objects/' + identity + '/period.json'}],
            'source_files': [{'id': r['observation_id'], 'sha256': r['raw_sha256'],
                              'path': r['source_url'], 'time_utc': r['time_utc'],
                              'processing_generation': r['processing_generation']}
                             for r in period['observations']],
            'trace_path': [{'level': 'operational_publication', 'key': identity},
                           {'level': 'retained_period_preview', 'key': period['period_preview_id']},
                           *[{'level': 'original_analysis_manifest', 'key': k,
                              'keys': [v['manifest_sha256']]} for k, v in sorted(payload['analyses'].items())]],
        },
    }
