"""Prepare only eDNA against an explicitly selected enabled-Research base.

Offline preparation never establishes fresh cloud authority or publishes data.
The publisher still requires an exact fresh base control CAS, immutable base
activation read and independent serving/controller binding before applying.
Original normalized bytes, held exports and receipt histories remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from deploy.gcp.beta.data import prepare_edna as edna
from deploy.gcp.beta.data import prepare_catalogue as ctd
from deploy.gcp.beta.data.append_catalogue import append_groups
from deploy.gcp.beta.data.publish_append import validate_bundle
from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore, MAX_CONTROL_BYTES
from ingestion.edna_catalogue_inputs import dataset_exports
from ingestion.gcs_catalogue_snapshot import validated_lifecycle
from ingestion.immutable_bundle import canonical_bytes
from schema.catalogue_snapshot import (
    MAX_BYTES, MAX_MANIFEST_BYTES, manifest_bytes, manifest_id, validated_manifest,
)

ROOT = Path(__file__).resolve().parents[4]
PROJECT = 'ocean-v1-beta-20261101'
VERSION = 'ocean-beta-b2-current-research-base-v1'
QUALIFICATIONS = (*edna.QUALIFICATIONS[:-1],
    'Raw operational catalogue access is enabled independently of scientific eligibility. '
    'Existing Research remains enabled; scientific approval and production experiment execution remain gated.')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_pins(revision):
    from deploy.gcp.beta.data.prepare_cohorts import source_pins as existing_pins
    # Pin the new operator as well as the original converter and every imported
    # owner module. Lazy imports may add pins; each must match the same commit.
    pins = existing_pins(revision)
    name = Path(__file__).relative_to(ROOT).as_posix()
    data = Path(__file__).read_bytes()
    require(ctd.git('show', revision + ':' + name) == data,
        'Current Research-eDNA preparer must match its selected commit')
    pins[name] = sha(data)
    return pins


def qualify_current_inventory(dataset, tables, captured):
    """Supersede generated operational wording, preserving all scientific rows."""
    require(dataset.family == 'edna_metabarcoding'
        and dataset.qualification == ' '.join(edna.QUALIFICATIONS),
        'Exact original generated eDNA qualification required before supersession')
    generations = {obj.provenance.source_generation for obj in captured.objects}
    require(len(generations) == 1, 'One original retained normalization generation required')
    current = dataset.model_copy(update={'qualification': ' '.join(QUALIFICATIONS)}, deep=True)
    new = dataset_exports(current, tables, generation=next(iter(generations)))
    before = {obj.role: obj.sha256 for obj in captured.objects}
    after = {obj.role: obj.sha256 for obj in new.objects}
    require(set(before) == set(after) and all(before[k] == after[k]
        for k in before if k != 'canonical_rows'),
        'Operational wording supersession must not change scientific table bytes')
    receipt = {'dataset_id': dataset.dataset_id, 'normalization_generation': next(iter(generations)),
        'original_generated_metadata_sha256': before['canonical_rows'],
        'current_generated_metadata_sha256': after['canonical_rows'],
        'scientific_table_hashes_unchanged': True,
        'classification_protocol_identity_and_review_lineage_unchanged': True,
        'reason': 'Replace obsolete all-Research-disabled operational wording; no scientific approval or eligibility granted'}
    return current, tables, new, receipt


def selected_base(base_store, selection, expected_activation):
    """Check a finite private generation/hash selection; never discover a store."""
    from api.v1_catalogue_host import _activation
    require(type(selection) is dict and set(selection) == {
        'version', 'project_id', 'research_enabled', 'activation_sha256',
        'control_generation', 'objects'} and selection['version'] == VERSION
        and selection['project_id'] == PROJECT and selection['research_enabled'] is True,
        'Exact isolated enabled-Research base selection required')
    require(type(expected_activation) is str and re.fullmatch('[a-f0-9]{64}', expected_activation)
        and selection['activation_sha256'] == expected_activation,
        'Independently selected existing Research activation required')
    require(type(selection['control_generation']) is int and selection['control_generation'] > 0
        and type(selection['objects']) is list and 0 < len(selection['objects']) <= 16000,
        'Positive exact control generation and finite object selection required')
    checked = {}
    for item in selection['objects']:
        require(type(item) is dict and set(item) == {'key', 'bytes', 'sha256', 'generation'},
            'Exact base file descriptor fields required')
        key = item['key']
        require(type(key) is str and re.fullmatch(
            r'v1/catalogue/(?:control\.json|objects/[a-f0-9]{64}|(?:manifests|activations)/[a-f0-9]{64}\.json)', key)
            and key not in checked, 'Distinct finite canonical base object keys required')
        require(type(item['generation']) is int and item['generation'] > 0
            and type(item['bytes']) is int and item['bytes'] > 0
            and type(item['sha256']) is str and re.fullmatch('[a-f0-9]{64}', item['sha256']),
            'Exact positive generation/size and hash for each base object required')
        maximum = MAX_BYTES if '/objects/' in key else (
            MAX_CONTROL_BYTES if key.endswith('/control.json') else MAX_MANIFEST_BYTES)
        data = ctd.read_private_file(base_store, key, maximum)
        require(len(data) == item['bytes'] and sha(data) == item['sha256'],
            'Selected current base file differs from its exact readback')
        if not key.endswith('/control.json'):
            require(sha(data) == key.rsplit('/', 1)[1].removesuffix('.json'),
                'Base immutable key must match its content hash')
        else:
            require(item['generation'] == selection['control_generation'],
                'Selected control generation differs from its file observation')
        checked[key] = data
    control_key = 'v1/catalogue/control.json'
    activation_key = 'v1/catalogue/activations/' + expected_activation + '.json'
    require(control_key in checked and activation_key in checked,
        'Explicit current control and independently selected activation required')
    require({k for k in checked if '/activations/' in k} == {activation_key},
        'Only the selected base activation may be copied')
    before = validated_lifecycle(checked[control_key])
    activation, _, registrations, _ = _activation(checked[activation_key], research_enabled=True)
    require(len(activation['snapshots']) == 3
        and all(len(item['datasets']) == 1 for item in activation['snapshots'])
        and {item['datasets'][0]['source_family'] for item in activation['snapshots']}
            == {'ctd', 'metagenome', 'remote_sensing'},
        'Current three-family Research base required; old CTD-only or already-appended bases are refused')
    required = {control_key, activation_key}
    for identity, state in before['snapshots'].items():
        if state['retired']:
            continue
        key = 'v1/catalogue/manifests/' + identity + '.json'
        require(key in checked, 'Every current base manifest must be explicitly selected')
        manifest = validated_manifest(edna.parsed(checked[key]))
        require(manifest_id(manifest) == identity, 'Exact current registered snapshot required')
        require(checked.get(key) == manifest_bytes(manifest), 'Every current base manifest must be explicitly selected')
        required.add(key)
        for obj in manifest.objects:
            payload_key = 'v1/catalogue/objects/' + obj.sha256
            require(payload_key in checked and len(checked[payload_key]) == obj.size_bytes,
                'Every current base payload must have its exact selected bytes')
            required.add(payload_key)
    require(set(checked) == required, 'Complete exact base object membership required; no extra files may be copied')
    for registration in registrations.values():
        for reference, identity in registration.references:
            state = before['snapshots'].get(identity)
            require(before['references'].get(reference) == identity and state is not None
                and not state['retired'] and not state['revoked'],
                'Current base registration is unavailable')
    # No LocalCatalogueSnapshotStore is opened on the input: even its lock file
    # would mutate that private source directory. All preparation writes go to
    # the new output after this finite immutable selection has been verified.
    return checked, before, activation


def prepare(*, revision, output, base_store, selection_path, expected_activation,
            edna_metadata, edna_normalized):
    raw = ctd.raw_module()
    source_pins(revision)
    output, base_store = raw.clean_absolute(output), raw.clean_absolute(base_store)
    raw.safe_ancestors(output.parent)
    raw.safe_ancestors(base_store)
    require(not output.exists() and not output.is_symlink() and not output.is_relative_to(ROOT)
        and not output.is_relative_to(base_store) and not base_store.is_relative_to(output),
        'New private output outside checkout and base source trees required')
    selection_path = raw.clean_absolute(selection_path)
    require(not selection_path.is_relative_to(ROOT), 'Private current-base selection required')
    selection_bytes = ctd.read_private_file(selection_path.parent, selection_path.name, edna.MAX_METADATA_BYTES)
    selection = edna.parsed(selection_bytes)
    checked, before, activation = selected_base(base_store, selection, expected_activation)
    output.mkdir(mode=0o700)

    def write(name, data):
        p = output / name
        p.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        raw.private_bytes(p, data)

    for key, data in checked.items():
        write('store/' + key, data)
    write('base/control.json', checked['v1/catalogue/control.json'])
    write('base/activation.json', checked['v1/catalogue/activations/' + expected_activation + '.json'])
    store = LocalCatalogueSnapshotStore(root=output / 'store', access_gate=lambda _: True)
    supersessions = []

    def triples():
        for bundle in edna.verified_bundles(edna_metadata, edna_normalized):
            for dataset, tables, captured in edna.normalized_datasets(bundle):
                current, frames, new, receipt = qualify_current_inventory(dataset, tables, captured)
                supersessions.append(receipt)
                yield current, frames, new

    result, summary = append_groups(store=store, activation=activation, groups=[{
        'label': {'en': 'ANEMONE raw inventory — unknown and negative controls',
            'ja': 'ANEMONE生インベントリ — 未分類と陰性対照'},
        'qualifications': QUALIFICATIONS, 'datasets': triples()}],
        authorization_ref='chat-20261103-all-beta-deployment-and-scientific-data', research_enabled=True)
    require(len(supersessions) == 39, 'Exactly39 current-v3 eDNA datasets required; inspect partial output before retry')
    activation_bytes = ctd.canonical(result)
    write('activation.json', activation_bytes)
    write('store/v1/catalogue/activations/' + sha(activation_bytes) + '.json', activation_bytes)
    keys = set()
    for identity in set(store.lifecycle()['snapshots']) - set(before['snapshots']):
        manifest, _ = store.read(identity)
        keys.add('v1/catalogue/manifests/' + identity + '.json')
        keys.update('v1/catalogue/objects/' + obj.sha256 for obj in manifest.objects)
    files = []
    for key in sorted(keys):
        data = (output / 'store' / key).read_bytes()
        files.append({'path': 'store/' + key, 'object_key': key, 'sha256': sha(data), 'bytes': len(data)})
    control = (output / 'store/v1/catalogue/control.json').read_bytes()
    base_control = checked['v1/catalogue/control.json']
    base_activation = checked['v1/catalogue/activations/' + expected_activation + '.json']
    manifest = {'version': 'ocean-beta-catalogue-append-publication-v1', 'project_id': PROJECT,
        'bucket': PROJECT + '-snapshots', 'prefix': 'v1/catalogue', 'source_revision': revision,
        'source_pins': source_pins(revision),
        'base_control': {'path': 'base/control.json', 'sha256': sha(base_control), 'bytes': len(base_control),
            'generation': selection['control_generation']},
        'base_activation': {'path': 'base/activation.json', 'sha256': sha(base_activation), 'bytes': len(base_activation)},
        'new_control': {'path': 'store/v1/catalogue/control.json', 'sha256': sha(control), 'bytes': len(control)},
        'activation': {'path': 'activation.json', 'object_key': 'v1/catalogue/activations/' + sha(activation_bytes) + '.json',
            'sha256': sha(activation_bytes), 'bytes': len(activation_bytes)}, 'files': files}
    verification = validate_bundle(output, manifest, research_enabled=True,
        expected_base_activation_sha256=expected_activation)
    write('publication-manifest.json', canonical_bytes(manifest))
    write('metadata-supersessions.json', canonical_bytes(supersessions))
    require(ctd.read_private_file(selection_path.parent, selection_path.name, edna.MAX_METADATA_BYTES) == selection_bytes,
        'Current-base selection changed during preparation; preserve partial output')
    summary.update(state='current_research_edna_append_prepared_not_published', source_revision=revision,
        source_selection_sha256=sha(selection_bytes),
        new_datasets=39, base_activation_sha256=expected_activation,
        immutable_files=verification['immutable_files'], immutable_bytes=verification['immutable_bytes'],
        base_current_in_cloud_verified=False, cloud_calls=False,
        fresh_serving_controller_binding_and_final_CAS_required=True,
        original_sources_and_receipts_unchanged=True)
    write('preparation-receipt.json', canonical_bytes(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('revision', 'expected-activation'):
        parser.add_argument('--' + name, required=True)
    for name in ('output', 'base-store', 'selection-path', 'edna-metadata', 'edna-normalized'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--prepare', required=True, action='store_true')
    arguments = vars(parser.parse_args())
    arguments.pop('prepare')
    try:
        result = prepare(**arguments)
    except Exception:
        print(json.dumps({'state': 'refused', 'cloud_calls': False,
            'error': 'Current Research-eDNA preparation failed; preserve and inspect private partial output before retry'}))
        return 2
    print(json.dumps({k: v for k, v in result.items() if k != 'new_groups'}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
