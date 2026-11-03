"""Prepare an explicit private beta append from accepted CTD and qualified inputs.

This performs no cloud IO. The base generation is the last accepted receipt,
not a claim of a fresh cloud read. The publisher must verify that exact current
control again before any immutable upload and before its final generation CAS.
An explicit cohort set is required: meta-sst preserves the eDNA latency gate,
while all-qualified selects all locally qualified inputs without passing live gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
PROJECT = 'ocean-v1-beta-20261101'
BASE_SOURCE = 'a4923c4e41fba694f77ebb60c1d3f768390e8b1b'
BASE_RECEIPT = 'docs/plans/ocean-v1/beta/snapshot-activation-20261103/data-upload-complete.json'
COHORT_SETS = ('meta-sst', 'all-qualified')
DEFERRED_EDNA_REASON = (
    'eDNA is deferred from the explicitly selected meta-sst deployment. The full-cohort raw detection page measured15.076610seconds locally, exceeding the then-current15second frontend deadline; cloud latency remains unaccepted. Retained normalized eDNA data are unchanged.'
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_pins(revision):
    from deploy.gcp.beta.data.publish_append import REQUIRED_SOURCES
    names = set(REQUIRED_SOURCES) | {BASE_RECEIPT,
        'deploy/gcp/beta/data/prepare_cohorts.py', 'deploy/gcp/beta/data/append_catalogue.py',
        'deploy/gcp/beta/data/prepare_catalogue.py', 'deploy/gcp/beta/data/prepare_metagenome.py',
        'deploy/gcp/beta/data/prepare_sst.py', 'deploy/gcp/beta/data/prepare_edna.py'}
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('Explicit full preparation source required')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD^{commit}'], cwd=ROOT).decode().strip() != revision:
        raise ValueError('Explicit current source checkpoint required')
    for module in tuple(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file:
            path = Path(file)
            if path.is_absolute() and path.is_relative_to(ROOT) and path.suffix == '.py':
                relative = path.relative_to(ROOT)
                if relative.parts[0] in {'api', 'schema', 'ingestion', 'retrieval', 'orchestration', 'preprocessing', 'db'}:
                    names.add(relative.as_posix())
    pins = {}
    for name in sorted(names):
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            raise ValueError('Regular committed preparation source required')
        data = path.read_bytes()
        if subprocess.check_output(['git', 'show', revision + ':' + name], cwd=ROOT) != data:
            raise ValueError('Preparation source differs from selected commit')
        pins[name] = sha(data)
    return pins


def selected_cohort_set(value):
    if type(value) is not str or value not in COHORT_SETS:
        raise ValueError('Explicit supported cohort set required: meta-sst or all-qualified')
    return value


def cohort_receipt(cohort_set):
    cohort_set = selected_cohort_set(cohort_set)
    return {'cohort_set': cohort_set,
        'deferred_families': {'edna_metabarcoding': DEFERRED_EDNA_REASON} if cohort_set == 'meta-sst' else {}}


def qualified_groups(*, cohort_set, raw_package, sst_publication, edna_metadata, edna_normalized):
    # Selection is mandatory before any imports or source/data/output access.
    cohort_set = selected_cohort_set(cohort_set)
    from deploy.gcp.beta.data import prepare_metagenome as meta, prepare_sst as sst
    inputs, _provenance = meta.verified_metagenome_bytes(Path(raw_package), ROOT)
    metagenome = meta.planned_metagenome(inputs)
    sst_triple = sst.regional_dataset(sst.verified_publication_bytes(Path(sst_publication)))
    groups = [
        {'label': {'en': 'Metagenome source matrices — unknown abundance denominator', 'ja': 'メタゲノム生行列 — 存在量分母は不明'},
            'qualifications': meta.QUALIFICATIONS,
            'datasets': [(metagenome['dataset'], metagenome['frames'], metagenome['captured'])]},
        {'label': {'en': 'MUR regional SST — unreviewed descriptive preview', 'ja': 'MUR地域SST — 未審査の記述的プレビュー'},
            'qualifications': sst.QUALIFICATIONS, 'datasets': [sst_triple]},
    ]
    if cohort_set == 'all-qualified':
        from deploy.gcp.beta.data import prepare_edna as edna
        def edna_triples():
            for bundle in edna.verified_bundles(Path(edna_metadata), Path(edna_normalized)):
                yield from edna.normalized_datasets(bundle)
        groups.append({
            'label': {'en': 'ANEMONE raw inventory — unknown and negative controls', 'ja': 'ANEMONE生インベントリ — 未分類と陰性対照'},
            'qualifications': edna.QUALIFICATIONS, 'datasets': edna_triples()})
    return groups


def prepare(*, cohort_set, revision, output, base_catalogue, raw_package, sst_publication,
            edna_metadata, edna_normalized):
    cohort_set = selected_cohort_set(cohort_set)
    from deploy.gcp.beta.data import prepare_catalogue as ctd
    from deploy.gcp.beta.data.append_catalogue import append_groups
    from deploy.gcp.beta.data.publish_append import validate_bundle
    from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
    from ingestion.gcs_catalogue_snapshot import validated_lifecycle
    from ingestion.immutable_bundle import canonical_bytes
    raw = ctd.raw_module()
    source_pins(revision)
    output, base_catalogue = raw.clean_absolute(output), raw.clean_absolute(base_catalogue)
    raw.safe_ancestors(output.parent)
    if (output.exists() or output.is_symlink() or output.is_relative_to(ROOT)
            or output.is_relative_to(base_catalogue)):
        raise ValueError('New private preparation directory outside all source trees required')
    accepted = json.loads((ROOT / BASE_RECEIPT).read_bytes())
    if accepted['source_revision'] != BASE_SOURCE or len(accepted['objects']) != 8:
        raise ValueError('Exact accepted CTD cloud readback receipt required')
    original = json.loads(ctd.read_private_file(base_catalogue, 'publication-manifest.json', 4 * 1024 * 1024))
    selected = {v['object_key']: v for v in original['files']}
    if len(selected) != 8 or original['source_revision'] != BASE_SOURCE:
        raise ValueError('Exact accepted private CTD source bundle required')
    # Verify every retained CTD object before creating output. No arbitrary
    # recursive copy, path discovery or unchecked scientific payload is used.
    checked = {}
    for item in accepted['objects']:
        key = item['name']
        if key not in selected or not re.fullmatch(
                r'v1/catalogue/(?:control\.json|objects/[a-f0-9]{64}|(?:manifests|activations)/[a-f0-9]{64}\.json)', key):
            raise ValueError('Exact finite CTD base object selection required')
        data = ctd.read_private_file(base_catalogue, selected[key]['local_path'], 512 * 1024 * 1024)
        if len(data) != item['bytes'] or sha(data) != item['sha256']:
            raise ValueError('Accepted private CTD base checksum mismatch')
        checked[key] = data
    base_control = next(v for v in accepted['objects'] if v['name'] == 'v1/catalogue/control.json')
    activation_item = next(v for v in accepted['objects'] if '/activations/' in v['name'])
    before = validated_lifecycle(checked['v1/catalogue/control.json'])
    activation = json.loads(checked[activation_item['name']])
    groups = qualified_groups(cohort_set=cohort_set, raw_package=raw_package,
        sst_publication=sst_publication, edna_metadata=edna_metadata, edna_normalized=edna_normalized)
    output.mkdir(mode=0o700)
    def write(relative, data):
        target = output / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw.private_bytes(target, data)
    for key, data in checked.items():
        write('store/' + key, data)
    write('base/control.json', checked['v1/catalogue/control.json'])
    write('base/activation.json', checked[activation_item['name']])
    store = LocalCatalogueSnapshotStore(root=output / 'store', access_gate=lambda manifest: True)
    new_activation, summary = append_groups(store=store, activation=activation, groups=groups,
        authorization_ref='chat-20261103-all-beta-deployment-and-scientific-data')
    activation_bytes = ctd.canonical(new_activation)
    write('activation.json', activation_bytes)
    write('store/v1/catalogue/activations/' + sha(activation_bytes) + '.json', activation_bytes)
    after = store.lifecycle()
    new_ids = set(after['snapshots']) - set(before['snapshots'])
    keys = set()
    for identity in sorted(new_ids):
        manifest, _ = store.read(identity)
        keys.add('v1/catalogue/manifests/' + identity + '.json')
        keys.update('v1/catalogue/objects/' + obj.sha256 for obj in manifest.objects)
    files = []
    for key in sorted(keys):
        path = output / 'store' / key
        data = path.read_bytes()
        files.append({'path': 'store/' + key, 'object_key': key, 'sha256': sha(data), 'bytes': len(data)})
    control_bytes = (output / 'store/v1/catalogue/control.json').read_bytes()
    manifest = {'version': 'ocean-beta-catalogue-append-publication-v1', 'project_id': PROJECT,
        'bucket': PROJECT + '-snapshots', 'prefix': 'v1/catalogue', 'source_revision': revision,
        'source_pins': source_pins(revision),
        'base_control': {'path': 'base/control.json', 'sha256': base_control['sha256'],
            'generation': int(base_control['generation']), 'bytes': base_control['bytes']},
        'base_activation': {'path': 'base/activation.json', 'sha256': activation_item['sha256'], 'bytes': activation_item['bytes']},
        'new_control': {'path': 'store/v1/catalogue/control.json', 'sha256': sha(control_bytes), 'bytes': len(control_bytes)},
        'activation': {'path': 'activation.json', 'object_key': 'v1/catalogue/activations/' + sha(activation_bytes) + '.json',
            'sha256': sha(activation_bytes), 'bytes': len(activation_bytes)}, 'files': files}
    verified = validate_bundle(output, manifest)
    raw.private_bytes(output / 'publication-manifest.json', canonical_bytes(manifest))
    summary.update({'state': 'qualified_cohorts_private_append_prepared', 'source_revision': revision,
        **cohort_receipt(cohort_set),
        'cloud_calls': False, 'base_current_in_cloud_verified': False,
        'publication_requires_fresh_base_control_and_final_cas': True,
        'snapshot_count': len(new_activation['snapshots']), 'new_datasets': sum(len(s['datasets']) for s in summary['new_groups']),
        'immutable_files': verified['immutable_files'], 'immutable_bytes': verified['immutable_bytes']})
    raw.private_bytes(output / 'preparation-receipt.json', canonical_bytes(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--cohort-set', choices=COHORT_SETS, required=True)
    parser.add_argument('--revision', required=True)
    for name in ('output', 'base-catalogue', 'raw-package', 'sst-publication', 'edna-metadata', 'edna-normalized'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--prepare', action='store_true', required=True)
    args = vars(parser.parse_args())
    args.pop('prepare')
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        result = prepare(**args)
    except Exception:
        print(json.dumps({'state': 'refused', 'error': 'Qualified cohort preparation failed; inspect private partial output before retry',
            'cloud_calls': False, 'scientific_approval': False}))
        return 2
    # Detailed dataset/counts remain in the private receipt; this is sanitized.
    print(json.dumps({key: value for key, value in result.items() if key != 'new_groups'}, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
