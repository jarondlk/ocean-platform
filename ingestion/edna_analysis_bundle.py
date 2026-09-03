"""Snapshot, publish and verify immutable research analysis runs."""
from datetime import date, datetime
from pathlib import Path
import json
import math
import hashlib
import re
import tempfile

from sqlalchemy import text

import config
from db.connection import get_engine
from ingestion.immutable_bundle import atomic_json, canonical_bytes, digest, seal_bundle, validate_id, read_bundle
from ingestion.provenance_snapshot import SnapshotConflict, SnapshotError
from ingestion.artifact_store import BoundedLocalStore
from preprocessing.edna_analysis import ALGORITHM_VERSION, MAX_ANALYSIS_BYTES, build_analysis, runtime_versions, select_inputs
from preprocessing.edna_recipe import AnalysisRecipe

TABLES = ('membership', 'composition', 'diversity', 'turnover', 'exclusions', 'methods', 'method_summary',
          'controls', 'control_overlap', 'standards', 'metadata', 'environment_links', 'environment_pairs', 'associations')
ANALYSIS_FILES = {f'{name}.json' for name in (*TABLES, 'recipe', 'inputs')}


def analysis_root():
    return config.EDNA_CACHE_DIR / 'analysis' if config.EDNA_ARTIFACT_URI else config.ANALYSIS_DIR / 'edna'


def _remote_store():
    from ingestion.artifact_store import ArtifactStore
    return ArtifactStore(config.EDNA_ARTIFACT_URI)


def _registered_records():
    if config.EDNA_ARTIFACT_URI:
        return [{'analysis_id': identity, **entry['metadata']}
                for identity, entry in sorted(_remote_store().entries('analysis').items())]
    records = []
    directory = analysis_root() / 'registry'
    if directory.is_symlink():
        raise ValueError('Invalid analysis registry path')
    for path in sorted(directory.glob('*.json')):
        if path.is_symlink():
            raise ValueError('Invalid analysis registry path')
        record = json.loads(BoundedLocalStore(directory).read(path.name, max_bytes=4096).data)
        if path.stem != record.get('analysis_id'):
            raise ValueError('Analysis registry identity mismatch')
        records.append(record)
    return records


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def read_canonical(recipe):
    """Bounded reads of one consistent snapshot, including same-run controls."""
    from api.edna_service import _sample_conditions
    filters = recipe.cohort.model_dump(exclude_none=True, exclude={'sample_ids'})
    conditions, params = _sample_conditions(filters)
    if recipe.cohort.sample_ids:
        conditions.append('s.sample_id = ANY(:sample_ids)')
        params['sample_ids'] = recipe.cohort.sample_ids
    with get_engine().connect() as connection, connection.begin():
        connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')

        def read(statement, params=None, maximum=1000):
            rows = connection.execute(text(statement + ' LIMIT :row_limit'), {**(params or {}), 'row_limit': maximum+1}).mappings().all()
            if len(rows) > maximum:
                raise ValueError('Canonical snapshot resource limit exceeded')
            return [{k: _json_value(v) for k,v in r.items()} for r in rows]

        selected = read('SELECT s.* FROM edna_sample s WHERE ' + ' AND '.join(conditions), params)
        scopes = sorted({(s['provider'], s['provider_project_id'], s['provider_run_id']) for s in selected})
        controls = []
        for provider, project, run in scopes:
            controls.extend(read("SELECT * FROM edna_sample WHERE active IS TRUE AND sample_kind <> 'environmental' AND provider=:p AND provider_project_id=:j AND provider_run_id=:r", {'p':provider, 'j':project, 'r':run}))
        samples = list({s['sample_id']: s for s in selected+controls}.values())
        if len(samples) > 1000:
            raise ValueError('Sample snapshot resource limit exceeded')
        assays = read('SELECT * FROM edna_assay WHERE active IS TRUE AND sample_id = ANY(:ids)', {'ids':[s['sample_id'] for s in samples]})
        aids = [a['assay_id'] for a in assays]
        detections = read('SELECT * FROM edna_detection WHERE active IS TRUE AND assay_id = ANY(:ids)', {'ids':aids}, recipe.max_detection_rows)
        standards = read('SELECT * FROM edna_internal_standard WHERE active IS TRUE AND assay_id = ANY(:ids)', {'ids':aids}, 10000)
        rows = samples+assays+detections+standards
        files = read('SELECT * FROM external_source_file WHERE source_file_id = ANY(:ids)', {'ids':sorted({r['source_file_id'] for r in rows})}, 10000)
        snapshots = read('SELECT * FROM external_source_snapshot WHERE snapshot_id = ANY(:ids)', {'ids':sorted({r['source_snapshot_id'] for r in rows})}, 10000)
    return dict(edna_sample=samples, edna_assay=assays, edna_detection=detections,
                edna_internal_standard=standards, external_source_file=files, external_source_snapshot=snapshots)


def validate_input_provenance(inputs):
    files = {f['source_file_id']: f for f in inputs['external_source_file']}
    snapshots = {s['snapshot_id']: s for s in inputs['external_source_snapshot']}
    for table in ('edna_sample', 'edna_assay', 'edna_detection', 'edna_internal_standard'):
        for row in inputs[table]:
            validate_id(row.get('source_row_hash'))
            f, s = files.get(row.get('source_file_id')), snapshots.get(row.get('source_snapshot_id'))
            if not f or not s or f.get('snapshot_id') != row['source_snapshot_id']:
                raise ValueError('Missing source-file/snapshot provenance')
            validate_id(f.get('sha256'))
            if s.get('status') != 'complete' or f.get('validation_status') != 'valid':
                raise ValueError('Unverified source input')
            locator = row.get('source_row_number') or row.get('source_row_numbers_json')
            if not locator or locator == '[]':
                raise ValueError('Missing source row locator')


def publish_analysis(result):
    validate_input_provenance(result['inputs']['canonical'])
    if set(result['tables']) != set(TABLES):
        raise ValueError('Incomplete analysis table contract')
    root = analysis_root()
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
    for name in ('recipe', 'inputs'):
        (staging / f'{name}.json').write_bytes(canonical_bytes(result[name]))
    for name, rows in result['tables'].items():
        (staging / f'{name}.json').write_bytes(canonical_bytes(rows))
    manifest = seal_bundle(staging, root, result['analysis_id'], {
        'algorithm_version': result['algorithm_version'], 'input_sha256': result['input_sha256'],
        'recipe_sha256': digest(result['recipe']), 'limitations': result['limitations'],
        'table_counts': {k: len(v) for k,v in result['tables'].items()},
    })
    # Validate before registration; a previous unregistered bundle is accepted
    # only if rebuilding from canonical inputs produced exactly the same bytes.
    _decode_analysis(manifest['id'], *read_bundle(root, manifest['id'],
        expected_digest=digest(manifest), required_files=ANALYSIS_FILES))
    record = canonical_bytes({'analysis_id': manifest['id'], 'manifest_sha256': digest(manifest)})
    if (root / 'registry').is_symlink():
        raise ValueError('Invalid analysis registry path')
    registry = BoundedLocalStore(root / 'registry')
    try:
        registry.create(manifest['id'] + '.json', record)
    except SnapshotConflict:
        if registry.read(manifest['id'] + '.json').data != record:
            raise ValueError('Analysis registration conflict')
    # A pointer per recipe prevents concurrent unrelated analyses overwriting each other.
    atomic_json(root / 'recipes' / f"{digest(result['recipe'])}.json", {'analysis_id': manifest['id'], 'manifest_sha256': digest(manifest)})
    if config.EDNA_ARTIFACT_URI:
        _, files = read_bundle(root, manifest['id'], expected_digest=digest(manifest), required_files=ANALYSIS_FILES)
        _remote_store().publish('analysis', manifest['id'], files,
            metadata={'manifest_sha256': digest(manifest), 'recipe_sha256': digest(result['recipe'])})
    return manifest


def load_analysis(identity):
    root = analysis_root()
    validate_id(identity)
    if config.EDNA_ARTIFACT_URI:
        receipt, contents = _remote_store().read('analysis', identity, max_bytes=MAX_ANALYSIS_BYTES)
        manifest = json.loads(contents['manifest.json'])
        if digest(manifest) != receipt['metadata']['manifest_sha256']:
            raise ValueError('Analysis manifest integrity failure')
        return _decode_analysis(identity, manifest, contents)
    record_path = root / 'registry' / (identity + '.json')
    if record_path.is_symlink() or (root / 'registry').is_symlink():
        raise ValueError('Invalid analysis registry path')
    try:
        record = json.loads(BoundedLocalStore(root / 'registry').read(record_path.name, max_bytes=4096).data)
    except SnapshotError as exc:
        raise ValueError('Analysis is not registered or registry is unavailable') from exc
    if record.get('analysis_id') != identity:
        raise ValueError('Analysis registration mismatch')
    manifest, contents = read_bundle(root, identity,
        expected_digest=validate_id(record.get('manifest_sha256')),
        required_files=ANALYSIS_FILES, max_bytes=MAX_ANALYSIS_BYTES)
    return _decode_analysis(identity, manifest, contents)


def _decode_analysis(identity, manifest, contents):
    if manifest.get('id') != identity or set(contents) != ANALYSIS_FILES | {'manifest.json'} or set(manifest['files']) != ANALYSIS_FILES:
        raise ValueError('Incomplete analysis file contract')
    for name, sha in manifest['files'].items():
        if hashlib.sha256(contents[name]).hexdigest() != sha:
            raise ValueError('Analysis output integrity failure')
    recipe = json.loads(contents['recipe.json'])
    inputs = json.loads(contents['inputs.json'])
    if digest(recipe) != manifest['recipe_sha256'] or digest(inputs) != manifest['input_sha256']:
        raise ValueError('Analysis input/recipe integrity check failed')
    if digest({'algorithm':manifest['algorithm_version'], 'recipe':recipe, 'input_sha256':digest(inputs)}) != identity:
        raise ValueError('Analysis identity mismatch')
    validate_input_provenance(inputs['canonical'])
    AnalysisRecipe.model_validate(recipe)
    if set(manifest['table_counts']) != set(TABLES):
        raise ValueError('Incomplete analysis table counts')
    tables = {}
    for name in TABLES:
        rows = json.loads(contents[name + '.json'])
        if not isinstance(rows, list) or len(rows) != manifest['table_counts'][name]:
            raise ValueError('Invalid analysis table shape/count')
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Invalid analysis row')
            result_id = validate_id(row.get('result_id'))
            if result_id in seen or result_id != digest([identity, name, {k:v for k,v in row.items() if k != 'result_id'}]):
                raise ValueError('Analysis result identity mismatch')
            seen.add(result_id)
        tables[name] = rows
    return {'manifest':manifest, 'recipe':recipe, 'inputs':inputs, 'tables':tables, 'files':contents}


def analysis_status(bundle):
    recipe = AnalysisRecipe.model_validate(bundle['recipe'])
    try:
        current = select_inputs(recipe, read_canonical(recipe))
        return 'current' if digest(current) == digest(bundle['inputs']['canonical']) and bundle['manifest']['algorithm_version'] == ALGORITHM_VERSION and bundle['inputs'].get('runtime') == runtime_versions() else 'historical'
    except Exception:
        return 'current_state_unavailable'


def analysis_catalog():
    output = []
    for pointer in _registered_records():
        bundle = load_analysis(pointer['analysis_id'])
        if digest(bundle['manifest']) != pointer.get('manifest_sha256'):
            raise ValueError('Analysis pointer integrity check failed')
        output.append({'analysis_id':pointer['analysis_id'], 'recipe':bundle['recipe'],
                       'table_counts':bundle['manifest']['table_counts'], 'status':analysis_status(bundle)})
    return output


def context_documents(scope):
    identity = scope.get('analysis_id')
    if not identity:
        return []
    try:
        bundle = load_analysis(identity)
        if analysis_status(bundle) != 'current':
            return []
        cohort, recipe = bundle['recipe']['cohort'], bundle['recipe']
        # A requested subcohort cannot inherit whole-cohort statistics silently.
        for key in ('provider', 'provider_project_id', 'provider_run_id', 'time_from', 'time_to', 'lat_min', 'lat_max', 'lon_min', 'lon_max'):
            if scope.get(key) is not None and scope[key] != cohort.get(key):
                return []
        if scope.get('sample_id') and cohort.get('sample_ids') != [scope['sample_id']]:
            return []
        if scope.get('taxon') or scope.get('is_control') is True or scope.get('sample_kind') not in {None, 'environmental'}:
            return []
        documents = []
        for name in ('diversity', 'method_summary', 'controls', 'associations', 'environment_links'):
            rows = bundle['tables'][name]
            if name == 'environment_links':
                rows = [r for r in rows if r.get('selected') and r.get('status') == 'qualified']
            if scope.get('assignment_method') and name != 'environment_links':
                if scope['assignment_method'] not in recipe['assignment_methods'] or name == 'method_summary':
                    continue
                rows = [r for r in rows if r.get('assignment_method') == scope['assignment_method']]
            if not rows:
                continue
            featured = rows[:5]
            documents.append(dict(id=f'analysis_edna_{identity}_{name}', title=f'eDNA {name}',
                source_type='analysis', source_family='edna_metabarcoding', covered_source_types=sorted({'edna_metabarcoding'} | ({r['source_type'] for r in featured} if name == 'environment_links' else set())),
                analysis_type='edna_'+name, analysis_id=identity, table=name,
                result_ids=[r['result_id'] for r in featured], recipe=recipe,
                text=f"Cohort: {json.dumps(cohort, sort_keys=True)}. Rank: {recipe['rank']}. Methods: {recipe['assignment_methods']}. Control policy: environmental_only. Minimum reads: {recipe['min_read_count']}. Table rows: {len(rows)}. First {len(featured)} rows (not the complete cohort): {json.dumps(featured, sort_keys=True)}. " + ' '.join(bundle['manifest']['limitations'])))
        return documents
    except (ValueError, OSError, KeyError, SnapshotError):
        return []


def request_scope(scope):
    """Resolve an explicit analysis request without silently changing its cohort."""
    bundle = load_analysis(scope['analysis_id'])
    if analysis_status(bundle) != 'current':
        raise ValueError('Analysis is historical or its current inputs cannot be verified')
    recipe = bundle['recipe']
    cohort = recipe['cohort']
    for key in ('provider', 'provider_project_id', 'provider_run_id', 'time_from', 'time_to', 'lat_min', 'lat_max', 'lon_min', 'lon_max'):
        if scope.get(key) is not None and scope[key] != cohort.get(key):
            raise ValueError('Request filters differ from the analysis cohort')
    if scope.get('sample_id') and cohort['sample_ids'] != [scope['sample_id']]:
        raise ValueError('Request sample differs from the analysis cohort')
    if scope.get('assignment_method') and scope['assignment_method'] not in recipe['assignment_methods']:
        raise ValueError('Request method differs from the analysis recipe')
    if scope.get('taxon') or scope.get('bay') or scope.get('is_control') is True or scope.get('sample_kind') not in {None, 'environmental'}:
        raise ValueError('Request filters differ from the analysis cohort')
    updates = {k:v for k,v in cohort.items() if k != 'sample_ids' and v is not None}
    updates.update(source_type='edna_metabarcoding', sample_kind='environmental', is_control=False)
    allowed = {s['sample_id'] for s in bundle['inputs']['canonical']['edna_sample'] if s.get('sample_kind') == 'environmental' and s.get('is_control') is False}
    return updates, allowed, set(recipe['assignment_methods'])


def provenance_descriptors():
    descriptors = []
    for pointer in _registered_records():
        bundle = load_analysis(pointer['analysis_id'])
        if digest(bundle['manifest']) != pointer['manifest_sha256']:
            raise ValueError('Analysis pointer integrity check failed')
        descriptors.append(dict(analysis_id=pointer['analysis_id'], manifest=bundle['manifest'],
            manifest_sha256=digest(bundle['manifest']), recipe=bundle['recipe'],
            bundle_path=f"data/analysis/edna/{pointer['analysis_id']}",
            bundle_route=f"/data/edna/analysis/runs/{pointer['analysis_id']}/export?format=bundle"))
    return descriptors


def analysis_trace(doc_id, descriptors):
    match = re.fullmatch(r'analysis_edna_([a-f0-9]{64})_([a-z_]+)', doc_id)
    if not match:
        return None
    identity, table = match.groups()
    descriptor = next((d for d in descriptors if d['analysis_id'] == identity), None)
    if not descriptor or table not in TABLES:
        return None
    manifest = descriptor['manifest']
    return dict(doc_id=doc_id, found=True, trace={
        'document': {'doc_id':doc_id, 'source_type':'analysis', 'title':'eDNA '+table,
                     'metadata':descriptor, 'lineage_level':'immutable_analysis'},
        'embedding': {'embedding_status':'not_applicable'},
        'artifacts': [{'id':f'edna_analysis:{identity}:{name}', 'path':descriptor['bundle_path']+'/'+name, 'sha256':sha}
                      for name,sha in manifest['files'].items()],
        'source_files': [{'id':'analysis_inputs:'+identity, 'path':descriptor['bundle_path']+'/inputs.json',
                         'sha256':manifest['files']['inputs.json'], 'bundle_route':descriptor['bundle_route']}],
        'trace_path': [{'level':'citation', 'key':doc_id}, {'level':'analysis_recipe', 'key':manifest['recipe_sha256']},
                       {'level':'result_table', 'key':manifest['files'][table+'.json']},
                       {'level':'canonical_records_and_source_files', 'key':manifest['input_sha256']}],
    })


def run_analysis(recipe, *, execute=False, environment=None):
    source = read_canonical(recipe)
    result = build_analysis(recipe, source, environment)
    validate_input_provenance(result['inputs']['canonical'])
    if execute:
        publish_analysis(result)
    return {'execute':execute, 'analysis_id':result['analysis_id'],
            'table_counts':{k:len(v) for k,v in result['tables'].items()}}
