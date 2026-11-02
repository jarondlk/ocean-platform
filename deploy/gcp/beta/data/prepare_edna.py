"""Local, exact-source C12 projection of retained ANEMONE normalized bundles.

No acquisition, classification review, physical identity resolution, cloud call,
scientific approval or snapshot mutation occurs. Two older schema bundles are
explicitly excluded instead of fabricating missing canonical identity fields.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
INDEX_SHA256 = '76d89bc641b739f3b5648287f24e947bdd6b6a7f3f8bbbf31020f7d516fd4d86'
SOURCE_PACKAGE_SHA256 = 'e3eb67bc569118712152cb23f64acdacec66c111d888774b07cfff8c9dd68eb6'
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_BUNDLE_BYTES = 256 * 1024 * 1024
MAX_ROWS = 2_000_000
ARTIFACTS = ('edna_sample', 'edna_assay', 'edna_detection', 'edna_internal_standard',
    'edna_anchor_event', 'external_source_file', 'external_source_snapshot')
QUALIFICATIONS = (
    'Raw inventory of exact retained ANEMONE normalized source occurrences; descriptive operational beta access grants no independent scientific approval.',
    'Provider classification, tri-state control status, evidence basis and null review lineage are retained. Unknown records are not reclassified as environmental; negative controls stay controls.',
    'Physical sample identities remain unresolved. Source occurrence IDs are not verified environmental sampling-event identities and do not establish CTD/SST pairing.',
    'Raw target and nontarget assignment methods remain separate alternatives over sequence evidence; do not sum them as independent biological observations.',
    'Read counts are sequencing signals, not organism abundance. Missing/absent concentration remains unknown; retained zero is not ecological absence.',
    'Original collection precision, provider coordinate precision, protocols, taxonomy and source-file method availability/counts are preserved without filling unknown metadata.',
    'Internal-standard, source-file, snapshot and anchor artifacts are integrity-verified but not promoted into unsupported C12 table roles or analyses. Original private bundles remain retained.',
    'Scientific eligibility and complete-protocol checks remain separate from raw catalogue access; all beta scientific/research execution gates remain false.',
)


class EDNAPreparationError(ValueError):
    """Safe fixed errors without raw source values or scientific row echo."""


def require(condition, message):
    if not condition:
        raise EDNAPreparationError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
        allow_nan=False) + '\n').encode()


def parsed(data):
    require(type(data) is bytes and 0 < len(data) <= MAX_METADATA_BYTES,
        'Bounded original eDNA metadata bytes required')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate eDNA source metadata key')
            result[key] = value
        return result
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(EDNAPreparationError('Nonfinite eDNA source metadata')))
    except (UnicodeError, json.JSONDecodeError):
        raise EDNAPreparationError('Valid original eDNA metadata JSON required') from None
    require(type(value) is dict, 'Original eDNA metadata must be an object')
    return value


def _sha(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None


def _private_root(value):
    root = Path(value)
    require(root.is_absolute() and '..' not in root.parts and not root.is_relative_to(ROOT),
        'Private eDNA staging outside the checkout required')
    for ancestor in (root, *root.parents):
        require(not ancestor.is_symlink(), 'eDNA source ancestors cannot be symbolic links')
    require(root.is_dir(), 'Existing private eDNA source directory required')
    return root


def _read(path, *, length=None, digest=None, maximum=MAX_FILE_BYTES):
    require(path.is_file() and not path.is_symlink(), 'Pinned regular eDNA source file required')
    before = path.stat()
    require(0 < before.st_size <= maximum and (length is None or before.st_size == length),
        'Bounded exact eDNA source length required')
    data = path.read_bytes()
    after = path.stat()
    def signature(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    require(signature(before) == signature(after) and (digest is None or hashlib.sha256(data).hexdigest() == digest),
        'Pinned eDNA source checksum or stable identity mismatch')
    return data


def source_guard(revision):
    require(type(revision) is str and re.fullmatch('[a-f0-9]{40}', revision),
        'Explicit full eDNA source revision required')
    def git(*args):
        result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True,
            timeout=20, check=False)
        require(result.returncode == 0, 'Committed eDNA preparation source required')
        return result.stdout
    require(git('rev-parse', 'HEAD^{commit}').decode().strip() == revision,
        'Explicit eDNA source must be current committed HEAD')
    names = {'deploy/gcp/beta/data/prepare_edna.py', 'ingestion/edna_catalogue_inputs.py',
        'schema/edna_catalogue.py', 'schema/context_catalogue.py',
        'preprocessing/anemone_classification.py', 'preprocessing/edna_taxonomy.py'}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename)
            if path.is_absolute() and path.is_relative_to(ROOT) and path.suffix == '.py':
                relative = path.relative_to(ROOT)
                if relative.parts[0] in {'schema', 'ingestion', 'retrieval', 'db', 'orchestration', 'preprocessing'}:
                    names.add(relative.as_posix())
    pins = {}
    for name in sorted(names):
        path = ROOT / name
        require(path.is_file() and not path.is_symlink(), 'Regular committed eDNA source required')
        data = path.read_bytes()
        require(git('show', revision + ':' + name) == data, 'eDNA converter source differs from selected commit')
        pins[name] = hashlib.sha256(data).hexdigest()
    return pins


def verified_bundles(metadata_directory, normalized_directory):
    """Yield39 exact current-format inputs; no fallback to the older two bundles."""
    import pyarrow.parquet as pq
    metadata_root = _private_root(metadata_directory)
    normalized_root = _private_root(normalized_directory)
    index_bytes = _read(metadata_root / '0-index.json', digest=INDEX_SHA256, maximum=MAX_METADATA_BYTES)
    index = parsed(index_bytes)
    require(index.get('schema_version') == 1 and type(index.get('entries')) is dict
        and len(index['entries']) == 41, 'Exact retained41-entry eDNA normalized source index required')
    local_registries = {}
    for path in metadata_root.iterdir():
        if re.fullmatch(r'\d+-[a-f0-9]{64}\.json', path.name):
            identity = path.name.split('-', 1)[1][:-5]
            require(identity not in local_registries, 'Duplicate eDNA registry source file')
            local_registries[identity] = path
    require(set(local_registries) == set(index['entries']), 'Complete exact eDNA registry file membership required')
    for identity, entry in sorted(index['entries'].items()):
        require(_sha(identity) and type(entry) is dict and _sha(entry.get('receipt_sha256')),
            'Pinned eDNA registry identity required')
        registry_bytes = _read(local_registries[identity], digest=entry['receipt_sha256'], maximum=MAX_METADATA_BYTES)
        registry = parsed(registry_bytes)
        require(registry.get('id') == identity and registry.get('namespace') == 'normalized'
            and registry.get('metadata') == entry.get('metadata'), 'eDNA registry/index ownership mismatch')
        metadata = registry.get('metadata', {})
        if metadata.get('source_package_sha256') != SOURCE_PACKAGE_SHA256:
            continue
        require(_sha(metadata.get('snapshot_id')) and _sha(metadata.get('normalization_id')),
            'Actual eDNA normalization source identities required')
        files = registry.get('files')
        require(type(files) is dict and set(files) == {'normalization_manifest.json'} | {name + '.parquet' for name in ARTIFACTS},
            'Complete exact normalized eDNA artifact membership required')
        directory = _private_root(normalized_root / identity)
        require({path.name for path in directory.iterdir()} == set(files),
            'Private normalized eDNA bundle must match exact retained registry members')
        data = {}
        for name, spec in files.items():
            require(type(spec) is dict and _sha(spec.get('sha256')) and type(spec.get('size')) is int
                and type(spec.get('generation')) is int and spec['generation'] > 0,
                'Exact original eDNA artifact generation/length/checksum required')
            data[name] = _read(directory / name, length=spec['size'], digest=spec['sha256'])
        require(sum(len(value) for value in data.values()) <= MAX_BUNDLE_BYTES, 'Bounded eDNA normalization bundle required')
        manifest_bytes = data['normalization_manifest.json']
        manifest = parsed(manifest_bytes)
        require(manifest.get('schema_version') == 1 and manifest.get('normalization_version') == 3
            and manifest.get('mode') == 'execute' and manifest.get('status') == 'complete' and manifest.get('ok') is True
            and manifest.get('source_family') == 'edna_metabarcoding' and manifest.get('source_provider') == 'anemone'
            and manifest.get('source_scope_level') == 'run'
            and manifest.get('normalization_id') == metadata['normalization_id']
            and manifest.get('source_snapshot_id') == metadata['snapshot_id']
            and manifest.get('classification_review') is None and manifest.get('classification_review_sha256') is None,
            'Complete v3 run normalization with unchanged absent review lineage required')
        frames = {}
        decoded = 0
        for name in ARTIFACTS:
            artifact = manifest.get('artifacts', {}).get(name, {})
            require(artifact.get('path') == name + '.parquet'
                and artifact.get('sha256') == files[name + '.parquet']['sha256']
                and type(artifact.get('row_count')) is int and 0 <= artifact['row_count'] <= MAX_ROWS
                and manifest.get('row_counts', {}).get(name) == artifact['row_count'],
                'Normalized eDNA manifest artifact binding mismatch')
            parquet = pq.ParquetFile(BytesIO(data[name + '.parquet']))
            require(parquet.metadata.num_rows == artifact['row_count']
                and parquet.schema_arrow.names == artifact.get('columns'), 'eDNA source Parquet count/columns differ from manifest')
            require(sum(parquet.metadata.row_group(i).total_byte_size for i in range(parquet.metadata.num_row_groups)) <= MAX_BUNDLE_BYTES,
                'Bounded source eDNA decoded artifact required')
            table = parquet.read(use_threads=False)
            decoded += table.nbytes
            require(decoded <= MAX_BUNDLE_BYTES, 'Bounded cumulative source eDNA decoded data required')
            # Keep Python primitives/None intact; pandas default numeric null conversion is avoided.
            if name in {'edna_sample', 'edna_assay', 'edna_detection'}:
                frames[name] = table.to_pylist()
        yield {'registry_id':identity, 'registry_sha256':entry['receipt_sha256'],
            'generation':hashlib.sha256(manifest_bytes).hexdigest(), 'manifest':manifest,
            'records':frames, 'source_package_sha256':SOURCE_PACKAGE_SHA256}


def normalized_datasets(bundle):
    """Project exact canonical columns, splitting only provider/project ownership."""
    import pandas as pd
    from ingestion.edna_catalogue_inputs import dataset_exports
    from schema.edna_catalogue import EDNADataset, TABLE_COLUMNS
    require(type(bundle) is dict and _sha(bundle.get('registry_id')) and _sha(bundle.get('generation'))
        and bundle.get('source_package_sha256') == SOURCE_PACKAGE_SHA256,
        'Explicit verified eDNA bundle identity/generation required')
    records = bundle.get('records', {})
    require(set(records) == {'edna_sample', 'edna_assay', 'edna_detection'}
        and all(type(rows) is list for rows in records.values()), 'Exact canonical eDNA source records required')
    require(sum(len(rows) for rows in records.values()) <= MAX_ROWS, 'Bounded eDNA source population required')
    samples, assays, detections = (records[name] for name in ('edna_sample', 'edna_assay', 'edna_detection'))
    require(samples and len({row.get('sample_id') for row in samples}) == len(samples)
        and len({row.get('assay_id') for row in assays}) == len(assays)
        and len({row.get('detection_id') for row in detections}) == len(detections),
        'Nonempty canonical eDNA occurrence population with distinct row identities required')
    all_samples = {row['sample_id'] for row in samples}
    all_assays = {row['assay_id'] for row in assays}
    require(all(row.get('sample_id') in all_samples for row in assays)
        and all(row.get('assay_id') in all_assays for row in detections),
        'No orphan canonical eDNA assay or detection may be dropped')
    groups = {}
    for sample in samples:
        require(all(name in sample for name in TABLE_COLUMNS['occurrences'] + TABLE_COLUMNS['classifications']),
            'Current C12 identity/provider/classification columns required; no historical backfill')
        require(sample.get('source_snapshot_id') == bundle['manifest'].get('source_snapshot_id'),
            'Canonical eDNA occurrence source differs from normalization manifest')
        key = tuple(sample[name] for name in ('provider', 'provider_locus', 'provider_team', 'provider_project_id'))
        groups.setdefault(key, []).append(sample)
    result = []
    for key, group in sorted(groups.items(), key=lambda item: canonical(item[0])):
        sample_ids = {row['sample_id'] for row in group}
        selected_assays = [row for row in assays if row['sample_id'] in sample_ids]
        assay_ids = {row['assay_id'] for row in selected_assays}
        selected_detections = [row for row in detections if row['assay_id'] in assay_ids]
        source_rows = {'occurrences':group, 'classifications':group,
            'assays':selected_assays, 'detections':selected_detections}
        projected = {}
        for role, rows in source_rows.items():
            require(all(all(name in row for name in TABLE_COLUMNS[role]) for row in rows),
                'Exact current canonical eDNA columns required; no implicit defaults')
            projected[role] = pd.DataFrame([{name:row[name] for name in TABLE_COLUMNS[role]} for row in rows],
                columns=TABLE_COLUMNS[role], dtype=object)
        group_sha = hashlib.sha256(canonical(key)).hexdigest()[:24]
        dataset_id = 'beta:edna:normalization:' + bundle['registry_id'] + ':' + group_sha
        source_id = 'beta:existing-anemone:' + bundle['manifest']['source_snapshot_id']
        dataset = EDNADataset.model_validate({'dataset_id':dataset_id, 'source_id':source_id,
            'provider':key[0], 'provider_locus':key[1], 'provider_team':key[2], 'provider_project_id':key[3],
            'collection_id':'beta:edna:source-project:' + bundle['registry_id'] + ':' + group_sha,
            'title':{'en':'ANEMONE retained source inventory — ' + key[3],
                'ja':'ANEMONE保存済みソースインベントリ — ' + key[3]},
            'purpose':{'en':'Raw source occurrences, assays and method-separated detections with original classification limits',
                'ja':'元の分類制約を保持するソース記録・アッセイ・手法別検出の生インベントリ'},
            'descriptor':{'family':'edna_metabarcoding', 'protocol_id':'retained-assay-protocols:' + group_sha,
                'protocol':'Retained source assay protocols; inspect original assay fields and missing metadata',
                'population':'raw_inventory', 'assignment_method':'mixed', 'sample_kind':'mixed',
                'is_control':None, 'measurement':'assigned_reads', 'unit':'reads'},
            'qualification':' '.join(QUALIFICATIONS),
            'methods':['Exact retained v3 normalization; no reclassification, missing-value filling or source-record deactivation',
                'Source method alternatives, availability and read/concentration semantics remain distinct',
                'Scientific eligibility and physical-sample resolution are independently gated'],
            'tables':[{'name':role, 'object_id':dataset_id + ':table:' + role,
                'row_count':len(frame), 'availability':{'status':'available'}, 'completeness':'complete'}
                for role, frame in projected.items()], 'related_ids':[]})
        captured = dataset_exports(dataset, projected, generation=bundle['generation'])
        result.append((dataset, projected, captured))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--private-metadata', required=True, type=Path)
    parser.add_argument('--private-normalized', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        source_guard(args.revision)
        counts = {'bundles':0, 'datasets':0, 'occurrences':0, 'assays':0, 'detections':0, 'classifications':0, 'export_bytes':0}
        for bundle in verified_bundles(args.private_metadata, args.private_normalized):
            counts['bundles'] += 1
            for dataset, frames, captured in normalized_datasets(bundle):
                counts['datasets'] += 1
                for role, frame in frames.items():
                    counts[role] += len(frame)
                counts['export_bytes'] += sum(len(data) for data in captured.contents.values())
        require(counts['bundles'] == 39, 'All39 qualified source bundles required')
        pins = source_guard(args.revision)
        result = {'state':'qualified_edna_raw_inventory_plan_only', 'source_revision':args.revision,
            'source_pins_sha256':hashlib.sha256(canonical(pins)).hexdigest(), **counts,
            'excluded_older_bundles':2, 'scientific_approval':False, 'physical_identity_inferred':False,
            'cloud_calls':False, 'sealed_or_registered':False}
    except Exception:
        print(json.dumps({'state':'refused', 'error':'Qualified eDNA preparation failed; inspect private source and qualification',
            'cloud_calls':False, 'scientific_approval':False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
