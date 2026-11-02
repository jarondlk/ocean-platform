"""Add qualified datasets to a private copy of the current beta catalogue.

No cloud, source discovery or scientific approval. The caller must first verify
the current base control bytes and use generation CAS when publishing the new
control. Old immutable objects, registrations, audits and references survive.
"""
from __future__ import annotations

import copy
import hashlib

from ingestion.gcs_catalogue_snapshot import validated_lifecycle
from ingestion.immutable_bundle import canonical_bytes
from ingestion.scientific_catalogue_inputs import registry_exports
from orchestration.catalogue_registration import register_scientific_snapshot
from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.catalogue_browser import CatalogueSnapshotDescriptor
from schema.catalogue_snapshot import SnapshotManifest, SourceCapture, manifest_id
from schema.scientific_catalogue import DatasetBinding, ScientificRegistry


def scope(*families):
    return EvidenceScope.model_validate({'version': 1, 'sources': {
        family: {'enabled': family in families, 'filters': {}} for family in FAMILIES}})


def captured_manifest(captured, *, qualifications):
    """Bind every exported object to its exact declared source generation."""
    sources = {}
    for obj in captured.objects:
        identity = (obj.source_id, obj.source_family, obj.provenance.source_generation)
        sources[identity] = SourceCapture(source_id=obj.source_id,
            source_family=obj.source_family, source_generation=obj.provenance.source_generation,
            publication_generation='beta-operational-descriptive-only-v2',
            classification_generation='none-inferred:beta-raw-v1',
            relationship_generation='none-inferred:beta-raw-v1',
            operation_generation='beta-frozen-dataset-exports-v2',
            capture_method='beta-explicit-qualified-dataset-exports-v2',
            qualifiers=list(qualifications))
    return SnapshotManifest(scope=scope(*(i[1] for i in sources)),
        source_captures=list(sources.values()), objects=list(captured.objects),
        operation_versions={obj.operation_id: obj.operation_version for obj in captured.objects})


def append_groups(*, store, activation, groups, authorization_ref):
    """Seal explicit dataset groups and preserve the complete existing lifecycle.

    Each group supplies a label, qualifications and exported dataset triples
    (metadata, frames, CapturedSource). It becomes one C13 datasets-only index.
    This is trusted offline preparation; no arbitrary module names or filenames
    are loaded from data. The supplied private store is never a serving store.
    """
    from api.v1_catalogue_host import _activation, _canonical
    _activation(_canonical(activation))
    before = validated_lifecycle(canonical_bytes(store.lifecycle()))
    result = copy.deepcopy(activation)
    if not groups or not isinstance(authorization_ref, str) or not authorization_ref:
        raise ValueError('Explicit dataset groups and current user authorization required')
    existing_ids = {item['descriptor']['snapshot_id'] for item in result['snapshots']}
    existing_datasets = {d['dataset_id'] for entry in result['snapshots'] for d in entry['datasets']}
    summaries = []
    for group in groups:
        bindings, counts = [], {}
        qualifications = tuple(group['qualifications'])
        if not qualifications or not group['datasets']:
            raise ValueError('Qualified nonempty dataset group required')
        for dataset, frames, captured in group['datasets']:
            if dataset.dataset_id in existing_datasets:
                raise ValueError('Existing dataset cannot be silently replaced or duplicated')
            manifest = captured_manifest(captured, qualifications=qualifications)
            child_id = store.seal(manifest, dict(captured.contents))
            if child_id != manifest_id(manifest):
                raise ValueError('Export seal differs from exact planned source')
            bindings.append(DatasetBinding(dataset_id=dataset.dataset_id,
                source_family=dataset.family, source_id=dataset.source_id, snapshot_id=child_id))
            counts[dataset.dataset_id] = {name: len(frame) for name, frame in frames.items()}
            existing_datasets.add(dataset.dataset_id)
        registry = ScientificRegistry(datasets=bindings, analyses=[], workflows=[],
            definitions=[], relationships=[])
        generation = hashlib.sha256(canonical_bytes(registry.model_dump(mode='json'))).hexdigest()
        index = registry_exports(registry, {}, generation=generation)
        index_manifest = captured_manifest(index, qualifications=qualifications)
        index_id = store.seal(index_manifest, dict(index.contents))
        if index_id in existing_ids:
            raise ValueError('Existing index cannot be silently replaced')
        registration = register_scientific_snapshot(store=store, snapshot_id=index_id,
            registration_id='beta:descriptive:' + index_id[:32])
        registration.require_current(store)
        for identity in (index_id, *registration.child_snapshot_ids):
            store.read(identity)
        descriptor = CatalogueSnapshotDescriptor(snapshot_id=index_id, label=group['label'])
        result['snapshots'].append({'descriptor': descriptor.model_dump(mode='json'),
            'registration': {'snapshot_id': registration.snapshot_id,
                'child_snapshot_ids': list(registration.child_snapshot_ids),
                'references': [list(pair) for pair in registration.references],
                'registration_id': registration.registration_id},
            'datasets': [b.model_dump(mode='json') for b in bindings]})
        existing_ids.add(index_id)
        summaries.append({'snapshot_id': index_id, 'datasets': counts})
    after = validated_lifecycle(canonical_bytes(store.lifecycle()))
    if (after['audits'][:before['revision']] != before['audits']
            or any(after['snapshots'].get(k) != v for k, v in before['snapshots'].items())
            or any(after['references'].get(k) != v for k, v in before['references'].items())
            or (after['latest'], after['latest_generation']) != (before['latest'], before['latest_generation'])):
        raise ValueError('Original lifecycle, references and latest identity must be preserved')
    result['authorization_ref'] = authorization_ref
    result['policy_revision'] = 'beta:descriptive:' + hashlib.sha256(
        canonical_bytes(result['snapshots'])).hexdigest()[:32]
    result['qualifications'] = list(dict.fromkeys([*result['qualifications'],
        'Additional qualified datasets are operationally authorized for this private beta; independent scientific approval remains false.']))
    data = _canonical(result)
    _activation(data)
    return result, {'activation_sha256': hashlib.sha256(data).hexdigest(),
        'base_control_sha256': hashlib.sha256(canonical_bytes(before)).hexdigest(),
        'base_revision': before['revision'], 'new_revision': after['revision'],
        'new_groups': summaries, 'scientific_approval': False, 'research_enabled': False}
