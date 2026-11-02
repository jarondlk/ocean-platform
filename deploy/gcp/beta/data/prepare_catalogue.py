"""Prepare a real qualified CTD catalogue from the verified raw quarantine.

No cloud calls, acquisition, model use, legacy database or scientific approval.
The exact source commit is required; --prepare alone permits a new private local
bundle. Metagenome, ambiguous SST aliases, eDNA and derived findings stay pending.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PROJECT = 'ocean-v1-beta-20261101'
CTD_PATH = 'data/raw/ctd/CTD_Onagawa.tsv'
CTD_SHA256 = 'e5f8ab6f47b3cadecde16518062795e7ae148d4a0b58097d4b24b441819dd529'
CTD_BYTES = 1242925
POLICY = 'beta-raw-ctd-owner-v1'
AUTHORIZATION = 'chat-20261102-all-eligible-existing-data'
MAX_METADATA = 4 * 1024 * 1024
SOURCE_PATHS = (
    'deploy/gcp/beta/data/prepare_catalogue.py',
    'deploy/gcp/beta/data/prepare_quarantine.py',
    'deploy/gcp/beta/data/scope-amendment.json',
    'preprocessing/ctd.py', 'preprocessing/common.py', 'preprocessing/edna_recipe.py',
    'ingestion/catalogue_adapter_inputs.py', 'ingestion/catalogue_snapshot.py',
    'ingestion/scientific_catalogue_inputs.py', 'ingestion/immutable_bundle.py',
    'orchestration/catalogue_registration.py', 'schema/catalogue_adapter.py',
    'schema/catalogue_snapshot.py', 'schema/scientific_catalogue.py',
    'schema/context_catalogue.py', 'retrieval/source_scope.py',
)
QUALIFICATIONS = (
    'Raw source data operationally authorized for the separate beta; scientific approval is false.',
    'All original CTD depth rows are retained for the declared depth, temperature and salinity columns; other raw fields remain in quarantine.',
    'Units follow the existing OCEAN CTD contract: depth_m in m, temperature in degC, salinity in PSU. Independent sensor calibration or unit validation is not claimed.',
    'Signed source depths are retained without absolute-value or sign conversion.',
    'Collection dates retain actual source day precision; bay/station are source-label codes, not independent geocoding.',
    'Source sample labels identify only this CTD collection; no cross-source physical pairing is inferred.',
    'Metagenome library/run/denominator conversion, SST embedded-time qualification, eDNA and derived analyses remain pending.',
)


class CataloguePreparationError(ValueError):
    """Fixed safe diagnostics; never raw scientific rows, tokens or DSNs."""


def require(value, message):
    if not value:
        raise CataloguePreparationError(message)


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + '\n').encode()


def raw_module():
    name = 'ocean_beta_raw_quarantine_package'
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HERE / 'prepare_quarantine.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git(*args):
    result = subprocess.run(['git', '-C', str(ROOT), *args],
        capture_output=True, check=False, timeout=15)
    require(result.returncode == 0, 'Exact committed catalogue-preparation source is required')
    return result.stdout


def source_guard(revision):
    require(re.fullmatch(r'[a-f0-9]{40}', revision or ''), 'Explicit full source revision is required')
    require(git('rev-parse', '--verify', 'HEAD^{commit}').decode().strip() == revision,
        'Preparation must use the explicitly selected current commit')
    paths = set(SOURCE_PATHS)
    local_roots = {'ingestion', 'preprocessing', 'schema', 'retrieval', 'orchestration', 'api', 'db'}
    for module in tuple(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if not file:
            continue
        path = Path(file)
        if not path.is_absolute() or not path.is_relative_to(ROOT) or path.suffix != '.py':
            continue
        relative = path.relative_to(ROOT)
        if relative.parts[0] in local_roots or relative.as_posix() in {'config.py', 'model_runtime.py'}:
            paths.add(relative.as_posix())
    pins = {}
    for name in sorted(paths):
        path = ROOT / name
        require(path.is_file() and not path.is_symlink(), 'Committed preparation file must be regular')
        data = path.read_bytes()
        require(git('show', revision + ':' + name) == data,
            'Selected catalogue-preparation source differs from its commit')
        pins[name] = hashlib.sha256(data).hexdigest()
    return pins


def read_private_file(root, name, maximum):
    raw = raw_module()
    with raw.source_file(root, name) as (stream, info):
        require(0 < info[4] <= maximum, 'Bounded private package metadata required')
        value = stream.read(maximum + 1)
    require(len(value) == info[4], 'Private package metadata length mismatch')
    return value


def verified_ctd_bytes(package, source_root):
    raw = raw_module()
    package, source_root = raw.clean_absolute(package), raw.clean_absolute(source_root)
    raw.safe_ancestors(package)
    require(not package.is_relative_to(ROOT), 'Raw quarantine must remain outside the checkout')
    manifest = read_private_file(package, 'source-manifest.json', raw.MAX_MANIFEST_BYTES)
    amendment = read_private_file(package, 'scope-amendment.json', raw.MAX_TRANSFER_BYTES)
    transfer = read_private_file(package, 'transfer-manifest.json', raw.MAX_TRANSFER_BYTES)
    receipt = json.loads(read_private_file(package, 'preparation-receipt.json', MAX_METADATA))
    committed, _revision = raw.committed_amendment()
    require(amendment == committed, 'Quarantine path amendment differs from the committed pinned package')
    original, sources, _signature = raw.read_manifest(source_root / raw.MANIFEST_RELATIVE,
        checkout_root=ROOT, source_root=source_root, expected=raw.EXPECTED, amendment=amendment)
    require(manifest == original, 'Quarantine original source manifest differs from the exact pinned cohort')
    require(transfer == raw.canonical(raw.transfer_manifest(source_root, sources, raw.EXPECTED, amendment)),
        'Exact reconciled transfer manifest required')
    require(receipt.get('state') == 'raw_quarantine_prepared_and_verified'
        and receipt.get('project_id') == PROJECT and receipt.get('files') == raw.EXPECTED.files
        and receipt.get('payload_bytes') == raw.EXPECTED.payload_bytes
        and receipt.get('scientific_approval') is False and receipt.get('published_or_promoted') is False,
        'Verified raw-quarantine preparation receipt required')
    archive = package / 'raw-quarantine.tar'
    raw.safe_ancestors(archive.parent)
    verification = raw.verify_archive(archive, sources, {
        'source-manifest.json':manifest, 'scope-amendment.json':amendment,
        'transfer-manifest.json':transfer})
    require(verification == receipt.get('archive_verification'), 'Raw archive differs from its complete verified receipt')
    with raw.source_file(package, 'raw-quarantine.tar') as (handle, _signature):
        with tarfile.open(fileobj=handle, mode='r:') as bundle:
            member = bundle.getmember('payload/' + CTD_PATH)
            require(member.isfile() and member.size == CTD_BYTES, 'Pinned CTD archive member required')
            stream = bundle.extractfile(member)
            with stream:
                ctd = stream.read(CTD_BYTES + 1)
    require(len(ctd) == CTD_BYTES and hashlib.sha256(ctd).hexdigest() == CTD_SHA256,
        'Pinned original CTD bytes required')
    return ctd, {'raw_archive_sha256':verification['sha256'],
        'raw_archive_bytes':verification['bytes'], 'raw_source_manifest_sha256':raw.EXPECTED.manifest_sha256,
        'raw_path_amendment_sha256':raw.AMENDMENT_SHA256, 'raw_cohort_files':raw.EXPECTED.files,
        'raw_cohort_payload_bytes':raw.EXPECTED.payload_bytes}


def scope():
    from retrieval.source_scope import EvidenceScope, FAMILIES
    return EvidenceScope.model_validate({'version':1, 'sources':{
        family:{'enabled':family == 'ctd', 'filters':{}} for family in FAMILIES}})


def table(dataset_id, name, frame, columns):
    from schema.catalogue_adapter import FrozenTable
    return FrozenTable.model_validate({'name':name, 'object_id':dataset_id + ':table:' + name,
        'row_count':len(frame), 'entity':'source_cast_labels' if name == 'casts' else 'source_depth_observation_rows',
        'denominator':'Every retained source ' + ('cast label' if name == 'casts' else 'depth row')
            + ' in this exact CTD file; no preview or cross-source pairing',
        'columns':columns, 'availability':{'status':'available'}, 'completeness':'complete'})


def column(name, dtype='string', unit=None, nullable=False, description=None):
    return {'name':name, 'dtype':dtype, 'unit':unit, 'nullable':nullable,
        'description':description or ('Retained source ' + name)}


def ctd_dataset(data, *, source_sha256=CTD_SHA256):
    """Use accepted normalization, retain all rows, reject guessed keys/dates."""
    import pandas as pd
    from preprocessing.ctd import load_ctd_raw, standardize_ctd_columns
    from preprocessing.common import derive_sample_dims
    from schema.catalogue_adapter import FrozenDataset
    from ingestion.catalogue_adapter_inputs import dataset_exports
    require(type(data) is bytes and hashlib.sha256(data).hexdigest() == source_sha256,
        'Explicit source CTD bytes and their checksum are required')
    original = pd.read_csv(io.BytesIO(data), sep='\t', dtype='string', keep_default_na=False)
    require({'date', 'label', 'depth', 'temperature', 'salinity'} <= set(original.columns),
        'Supported original CTD date/label/depth/temperature/salinity columns required')
    require(0 < len(original) <= 100000 and all(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value or '')
        for value in original['date']), 'CTD collection dates require actual source day precision')
    require(all(value and value == value.strip() and len(value) <= 256
        and not any(ord(char) < 32 for char in value) for value in original['label']),
        'Complete unmodified source sample labels are required')
    frame = standardize_ctd_columns(load_ctd_raw(io.BytesIO(data)))
    require(len(frame) == len(original) and not frame.ctd_date.isna().any()
        and frame.sample_id.astype(str).tolist() == original.label.tolist(),
        'Normalization cannot drop rows or alter source sample labels')
    for key in ['depth_m', 'temperature', 'salinity']:
        require(not frame[key].isna().any() and all(math.isfinite(float(x)) for x in frame[key]),
            'All published CTD measurements must be finite; no silent coercion or row omission')
    require(frame.groupby('sample_id').ctd_date.nunique().max() == 1,
        'Repeated source sample labels across dates need separate cast identity review')
    identities = sorted(frame.sample_id.unique())
    dimensions = derive_sample_dims(pd.Series(identities, dtype='string'))
    by_label = dimensions.set_index('sample_id').to_dict('index')
    dataset_id = 'beta:ctd:raw:' + source_sha256
    cast_ids = {label:'ctd-cast:' + hashlib.sha256((source_sha256 + '\n' + label).encode()).hexdigest()
        for label in identities}
    casts = []
    for label in identities:
        selected = frame.loc[frame.sample_id == label]
        dims = by_label[label]
        casts.append({'cast_id':cast_ids[label], 'sample_id':label,
            'collection_date':selected.ctd_date.iloc[0].strftime('%Y-%m-%d'),
            'bay':None if pd.isna(dims['bay']) else str(dims['bay']),
            'station':None if pd.isna(dims['station_code']) else str(dims['station_code'])})
    rows = [{'observation_id':'ctd-row:' + source_sha256 + ':' + str(index + 1),
        'cast_id':cast_ids[str(row.sample_id)], 'depth':float(row.depth_m),
        'temperature':float(row.temperature), 'salinity':float(row.salinity), 'source_row':index + 1}
        for index, row in enumerate(frame.itertuples(index=False))]
    frames = {'casts':pd.DataFrame(casts), 'depth_observations':pd.DataFrame(rows)}
    tables = [table(dataset_id, 'casts', frames['casts'], [column('cast_id'), column('sample_id'),
        column('collection_date'), column('bay', nullable=True), column('station', nullable=True)]),
        table(dataset_id, 'depth_observations', frames['depth_observations'], [
            column('observation_id'), column('cast_id'), column('depth', 'number', 'm'),
            column('temperature', 'number', 'degC'), column('salinity', 'number', 'PSU'),
            column('source_row', 'integer', 'source_data_rows', description='One-based original data row excluding header')])]
    dataset = FrozenDataset.model_validate({'dataset_id':dataset_id, 'source_id':'beta:existing-raw-ctd',
        'family':'ctd', 'collection_id':'beta:ctd:collection:' + source_sha256,
        'title':{'en':'Existing raw CTD collection', 'ja':'既存の生CTDコレクション'},
        'purpose':{'en':'Descriptive access to every retained CTD cast and supported depth measurement',
            'ja':'保持されたCTD観測と対応する深度測定の記述的参照'},
        'descriptor':{'family':'ctd', 'sampling_contract':'Original source sample labels and actual collection days; no cross-source physical pairing',
            'observation_entity':'depth_observation', 'measurement':'temperature', 'unit':'degC', 'depth_unit':'m'},
        'collection_date_precision':'day', 'depth_convention':'signed_source',
        'qualification':' '.join(QUALIFICATIONS),
        'methods':['Existing OCEAN load_ctd_raw and standardize_ctd_columns; no summary regeneration',
            'Retained source depth, temperature and salinity; no calibration or scientific approval inferred'],
        'tables':tables, 'related_ids':[]})
    # The actual C10 validator/writer closes row/schema/unit/foreign-key semantics.
    captured = dataset_exports(dataset, frames, generation=source_sha256)
    return dataset, frames, captured


def snapshot(captured, *, source_id, generation, method):
    from schema.catalogue_snapshot import SnapshotManifest, SourceCapture
    return SnapshotManifest(scope=scope(), source_captures=[SourceCapture(
        source_id=source_id, source_family='ctd', source_generation=generation,
        publication_generation='beta-raw-operational-only-v1',
        classification_generation='none-inferred:beta-raw-v1',
        relationship_generation='none-inferred:beta-raw-v1', operation_generation='c10-v1:c13-v1',
        capture_method=method, qualifiers=list(QUALIFICATIONS))], objects=list(captured.objects),
        operation_versions={item.operation_id:item.operation_version for item in captured.objects})


def planned_snapshots(data, *, source_sha256=CTD_SHA256):
    from ingestion.scientific_catalogue_inputs import registry_exports
    from schema.catalogue_snapshot import manifest_id
    from schema.scientific_catalogue import DatasetBinding, ScientificRegistry, INDEX_SOURCE_ID
    dataset, frames, child = ctd_dataset(data, source_sha256=source_sha256)
    child_manifest = snapshot(child, source_id=dataset.source_id,
        generation=source_sha256, method='beta-verified-raw-ctd-normalization-v1')
    child_id = manifest_id(child_manifest)
    binding = DatasetBinding(dataset_id=dataset.dataset_id, source_family='ctd',
        source_id=dataset.source_id, snapshot_id=child_id)
    registry = ScientificRegistry(datasets=[binding], analyses=[], workflows=[], definitions=[], relationships=[])
    generation = hashlib.sha256(canonical({'dataset':dataset.dataset_id, 'child':child_id})).hexdigest()
    index = registry_exports(registry, {}, generation=generation)
    index_manifest = snapshot(index, source_id=INDEX_SOURCE_ID,
        generation=generation, method='beta-c13-dataset-bindings-only-v1')
    return {'dataset':dataset, 'frames':frames, 'child':child,
        'child_manifest':child_manifest, 'child_id':child_id, 'binding':binding,
        'registry':registry, 'index':index, 'index_manifest':index_manifest,
        'index_id':manifest_id(index_manifest)}


def seal_catalogue(output, planned):
    from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
    from orchestration.catalogue_registration import register_scientific_snapshot
    from schema.catalogue_browser import CatalogueSnapshotDescriptor
    raw = raw_module()
    allowed = {source.source_id:source.source_generation
        for key in ['child_manifest', 'index_manifest'] for source in planned[key].source_captures}
    store = LocalCatalogueSnapshotStore(root=output / 'store',
        access_gate=lambda manifest:all(allowed.get(c.source_id) == c.source_generation for c in manifest.source_captures))
    require(store.seal(planned['child_manifest'], dict(planned['child'].contents)) == planned['child_id'],
        'Actual child seal differs from planned source identity')
    require(store.seal(planned['index_manifest'], dict(planned['index'].contents)) == planned['index_id'],
        'Actual scientific index seal differs from planned source identity')
    registration = register_scientific_snapshot(store=store, snapshot_id=planned['index_id'],
        registration_id='beta:raw-ctd-owner:' + planned['index_id'][:24])
    registration.require_current(store)
    # Read all exact sealed bytes through the accepted store, after registration.
    for identity in [planned['child_id'], planned['index_id']]:
        store.read(identity)
    descriptor = CatalogueSnapshotDescriptor(snapshot_id=planned['index_id'],
        label={'en':'Raw CTD collection — qualified descriptive data', 'ja':'生CTDコレクション — 条件付き記述データ'})
    activation = {'version':'ocean-v1-catalogue-activation-v1', 'project_id':PROJECT,
        'site_id':'v1:' + PROJECT, 'policy_revision':POLICY, 'authorization_ref':AUTHORIZATION,
        'access':{'roles':['admin'], 'account_types':['internal']},
        'scientific_mode':'datasets_only', 'scientific_approval':False, 'research_enabled':False,
        'snapshots':[{'descriptor':descriptor.model_dump(mode='json'),
            'registration':{'snapshot_id':registration.snapshot_id,
                'child_snapshot_ids':list(registration.child_snapshot_ids),
                'references':[list(pair) for pair in registration.references],
                'registration_id':registration.registration_id},
            'datasets':[planned['binding'].model_dump(mode='json')]}],
        'qualifications':list(QUALIFICATIONS)}
    activation_bytes = canonical(activation)
    activation_sha = hashlib.sha256(activation_bytes).hexdigest()
    raw.private_bytes(output / 'activation.json', activation_bytes)
    files = []
    base = output / 'store'
    control = base / 'v1/catalogue/control.json'
    selected = sorted((base / 'v1/catalogue/objects').iterdir())
    selected += sorted((base / 'v1/catalogue/manifests').iterdir())
    selected.append(control)
    for path in selected:
        relative = path.relative_to(base).as_posix()
        require(path.is_file() and not path.is_symlink() and re.fullmatch(
            r'v1/catalogue/(?:objects/[a-f0-9]{64}|manifests/[a-f0-9]{64}\.json|control\.json)', relative),
            'Only exact immutable catalogue bytes and lifecycle control may be uploaded')
        value = path.read_bytes()
        files.append({'local_path':path.relative_to(output).as_posix(), 'object_key':relative,
            'bytes':len(value), 'sha256':hashlib.sha256(value).hexdigest(),
            'immutable':relative != 'v1/catalogue/control.json', 'upload_last':path == control})
    files.append({'local_path':'activation.json',
        'object_key':'v1/catalogue/activations/' + activation_sha + '.json',
        'bytes':len(activation_bytes), 'sha256':activation_sha, 'immutable':True, 'upload_last':False})
    lifecycle = store.lifecycle()
    require(lifecycle['latest'] is None and lifecycle['latest_generation'] == 0,
        'Preparation must not promote a mutable latest pointer')
    return {'activation_sha256':activation_sha, 'activation_bytes':len(activation_bytes),
        'activation_object_key':'v1/catalogue/activations/' + activation_sha + '.json',
        'files':files, 'registration':activation['snapshots'][0]['registration'],
        'lifecycle_revision':lifecycle['revision'], 'store':store}


def prepare(*, raw_package, source_root, output, revision, applying=False):
    raw = raw_module()
    output = raw.clean_absolute(output)
    require(not output.is_relative_to(ROOT) and not output.is_relative_to(raw.HISTORICAL_ROOT)
        and not output.is_relative_to(Path(raw_package)), 'Private output must be outside source and raw-package trees')
    require(not output.exists() and not output.is_symlink(), 'A new private output directory is required')
    raw.safe_ancestors(output.parent)
    source_guard(revision)
    data, provenance = verified_ctd_bytes(Path(raw_package), Path(source_root))
    planned = planned_snapshots(data)
    pins = source_guard(revision)
    result = {'version':'ocean-beta-ctd-catalogue-preparation-v1', 'project_id':PROJECT,
        'state':'verified_catalogue_plan_only', 'source_revision':revision,
        'source_pins_sha256':hashlib.sha256(canonical(pins)).hexdigest(),
        'dataset_id':planned['dataset'].dataset_id, 'child_snapshot_id':planned['child_id'],
        'scientific_index_snapshot_id':planned['index_id'],
        'casts':len(planned['frames']['casts']), 'depth_observations':len(planned['frames']['depth_observations']),
        'source_ctd_sha256':CTD_SHA256, **provenance,
        'scientific_approval':False, 'cloud_calls':False, 'research_enabled':False,
        'metagenome':'pending qualified library/run/abundance conversion',
        'sst':'pending embedded-source-time and byte-alias qualification',
        'edna':'pending exact source inventory and classification authority',
        'derived_analyses':'excluded; no reviews or published findings invented',
        'c09_snapshot_sealed':False, 'cloud_published':False, 'output_created':False}
    if not applying:
        return result
    output.mkdir(mode=0o700)
    sealed = seal_catalogue(output, planned)
    pins = source_guard(revision)
    publication = {key:value for key, value in sealed.items() if key != 'store'}
    publication.update({'version':'ocean-beta-catalogue-upload-manifest-v1', 'project_id':PROJECT,
        'bucket':PROJECT + '-snapshots', 'namespace':'v1/catalogue',
        'source_revision':revision, 'source_pins':pins,
        'child_snapshot_id':planned['child_id'], 'scientific_index_snapshot_id':planned['index_id'],
        'scientific_approval':False, 'cloud_uploaded':False,
        'upload_order':'Immutable objects/manifests/activation first; lifecycle control last; activate serving only after verification'})
    raw.private_bytes(output / 'publication-manifest.json', canonical(publication))
    result.update({'state':'qualified_ctd_catalogue_sealed_and_registered_locally',
        'output_created':True, 'c09_snapshot_sealed':True,
        'activation_sha256':sealed['activation_sha256'], 'upload_files':len(sealed['files']),
        'lifecycle_revision':sealed['lifecycle_revision'], 'source_pins_sha256':hashlib.sha256(canonical(pins)).hexdigest()})
    raw.private_bytes(output / 'preparation-receipt.json', canonical(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--raw-package', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        result = prepare(raw_package=args.raw_package, source_root=args.source_root,
            output=args.output, revision=args.revision, applying=args.prepare)
    except Exception:
        # pandas/Pydantic/storage errors can contain scientific rows or paths.
        print(json.dumps({'state':'refused', 'error':'Qualified catalogue preparation failed; inspect private inputs and partial output before retry',
            'cloud_calls':False, 'scientific_approval':False, 'cloud_published':False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
