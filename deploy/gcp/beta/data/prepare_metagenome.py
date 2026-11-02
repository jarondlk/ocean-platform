"""Qualified metagenome exports from the already verified private raw cohort.

No acquisition/cloud call, scientific approval, abundance normalization or cross-
source pairing. Units and abundance denominators remain literally ``unknown``;
exact source cell text is retained and numerical summaries remain unavailable.
Only a separately checkpointed --prepare can write new private export bytes.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PROJECT = 'ocean-v1-beta-20261101'
SOURCE_ID = 'beta:existing-raw-metagenome'
INPUTS = {
    'Kraken.genus-sample.tsv': (693529, 'bd752476a1e8a4a19de003e56bfeebe63b22bd5f95a52e7de75a7f14fa748550'),
    'MetaEuk.genus-sample.tsv': (685787, '509269ea6c72e00d497e7f5c4687a1d16508e736327b53e34251a83fbbfb79e3'),
    'runid.tsv': (3478, 'bf04fdd07618c4134fc5c46c67e9fcd4693e63b897c5c715ecbc6050392301cc'),
    '01.read_summary_gt1kb.tsv': (5330, '931447cc5eda57064d176cf7999d8c081b06f446e4f43368116e9076d90f386a'),
}
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_MATRIX_CELLS = 250000
MAX_RUNS = 10000
INTEGER_LIMIT = 2**63 - 1
QC_NAMES = ('n_reads_gt1kb', 'bases_gt1kb', 'n_reads_gt10kb', 'bases_gt10kb')
SAMPLE = re.compile(r'(?P<month>\d{4}-(?:0[1-9]|1[0-2]))-(?P<bay>[OIM])-(?P<station>[A-Za-z0-9][A-Za-z0-9_-]*)')
NUMBER = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
QUALIFICATIONS = (
    'Existing raw metagenome data is operationally authorized for the separate beta; scientific approval is false.',
    'Library keys identify exact source matrix columns, not independently verified physical extraction libraries; no cross-source pairing is inferred.',
    'Collection month and bay/station codes are source-label conventions; actual collection days and independent geocoding are unknown.',
    'Run IDs, sample-replicate labels and actual sequencing-run dates remain separate from collection labels and dates.',
    'Run-to-column links use only the accepted exact source label plus terminal replicate suffix convention; runs and read counts are not aggregated.',
    'All supplied genus-by-source-column cells are retained separately for Kraken and MetaEuk, including every explicit zero; omitted taxa remain unknown.',
    'Abundance unit and denominator are unknown in the source matrices. No fraction/percent assumption, renormalization, cell dropping, method pooling or abundance summary is performed.',
    'The numeric abundance view uses finite float64; original decimal source text and matrix row/column locators are retained for exact lexical values.',
    'Read/base QC fields retain their explicit source greater-than-1kb and greater-than-10kb thresholds; no abundance denominator is inferred from them.',
    'Taxonomic names and genus rank are source-declared method output, not independent taxonomic review. Ranked summaries, group/consistency interpretation and derived findings remain unavailable.',
)


class MetagenomePreparationError(ValueError):
    """Fixed private-input-free diagnostics only."""


def require(value, message):
    if not value:
        raise MetagenomePreparationError(message)


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def ctd_module():
    name = 'ocean_beta_ctd_preparation_for_meta'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, HERE / 'prepare_catalogue.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def verified_metagenome_bytes(package, source_root):
    """Reuse the accepted whole-archive verifier, then read only pinned members."""
    base = ctd_module()
    _ctd, provenance = base.verified_ctd_bytes(Path(package), Path(source_root))
    raw = base.raw_module()
    inputs = {}
    with raw.source_file(Path(package), 'raw-quarantine.tar') as (handle, _signature):
        with tarfile.open(fileobj=handle, mode='r:') as archive:
            for name, (size, sha) in INPUTS.items():
                member = archive.getmember('payload/data/raw/meta/' + name)
                require(member.isfile() and member.size == size, 'Exact pinned metagenome archive member required')
                with archive.extractfile(member) as stream:
                    data = stream.read(size + 1)
                require(len(data) == size and hashlib.sha256(data).hexdigest() == sha,
                    'Pinned source metagenome bytes differ')
                inputs[name] = data
    return inputs, provenance


def _text(value):
    require(type(value) is str and 0 < len(value) <= 255 and value == value.strip()
        and not any(ord(char) < 32 for char in value), 'Explicit unmodified source text required')
    return value


def _sample(label):
    label = _text(label)
    match = SAMPLE.fullmatch(label)
    require(match is not None, 'Unambiguous supported source sample-label convention required')
    month = match['month']
    try:
        date.fromisoformat(month + '-01')
    except ValueError:
        raise MetagenomePreparationError('Valid source collection-month label required') from None
    return month, match['bay'], match['station']


def _rows(data):
    require(type(data) is bytes and 0 < len(data) <= MAX_INPUT_BYTES, 'Bounded exact source table bytes required')
    try:
        rows = list(csv.reader(io.StringIO(data.decode('utf-8'), newline=''), delimiter='\t', strict=True))
    except (UnicodeError, csv.Error):
        raise MetagenomePreparationError('Supported UTF8 source TSV required') from None
    require(rows and all(row for row in rows), 'Empty source rows cannot be silently dropped')
    return rows


def parse_matrix(data):
    """Parse the explicit unlabeled-genus-column format without pandas coercion."""
    rows = _rows(data)
    labels, values = rows[0], rows[1:]
    require(labels and len(set(labels)) == len(labels) and values
        and len(labels) * len(values) <= MAX_MATRIX_CELLS,
        'Bounded distinct matrix sample columns and nonempty taxon rows required')
    for label in labels:
        _sample(label)
    taxa, cells = set(), []
    for row_number, row in enumerate(values, 2):
        require(len(row) == len(labels) + 1, 'Every matrix row must retain every explicit source cell')
        taxon = _text(row[0])
        require(taxon not in taxa, 'Duplicate source taxon rows need explicit scientific resolution')
        taxa.add(taxon)
        for column_number, text in enumerate(row[1:], 2):
            require(type(text) is str and NUMBER.fullmatch(text),
                'Every source abundance cell must be explicit finite numeric text')
            try:
                exact = Decimal(text)
                value = float(exact)
            except (InvalidOperation, ValueError, OverflowError):
                raise MetagenomePreparationError('Finite source abundance cells required') from None
            require(exact.is_finite() and exact >= 0 and math.isfinite(value)
                and not (exact != 0 and value == 0),
                'Negative, nonfinite or underflowing abundance cells cannot be reinterpreted')
            cells.append((labels[column_number - 2], taxon, value, text, row_number, column_number))
    return tuple(labels), tuple(cells), len(taxa)


def parse_runs(data, qc_data, *, labels):
    rows, qc_rows = _rows(data), _rows(qc_data)
    require(len(rows) <= MAX_RUNS and len(qc_rows) <= MAX_RUNS,
        'Bounded source run and QC inventories required')
    qc = {}
    for row in qc_rows:
        require(len(row) == 5, 'Exact five-field source read-summary rows required')
        replicate = _text(row[0])
        require(replicate not in qc, 'Duplicate source read-summary identity refused')
        counts = []
        for text in row[1:]:
            require(re.fullmatch(r'\d+', text) is not None, 'Explicit nonnegative integer QC counts required')
            value = int(text)
            require(value <= INTEGER_LIMIT, 'Source QC count exceeds exact signed integer storage')
            counts.append(value)
        qc[replicate] = tuple(counts)
    runs, run_ids, replicates, bases = [], set(), set(), set()
    for row in rows:
        require(len(row) == 3, 'Exact three-field source run mapping required')
        run_id, replicate, run_date = map(_text, row)
        require(run_id not in run_ids and replicate not in replicates,
            'Run and source sample-replicate identities must be explicit and unique')
        require(re.fullmatch(r'\d{4}-\d{2}-\d{2}', run_date) is not None,
            'Actual sequencing-run day precision required')
        try:
            date.fromisoformat(run_date)
        except ValueError:
            raise MetagenomePreparationError('Valid source sequencing-run day required') from None
        match = re.fullmatch(r'(.+)\.([1-9]\d*)', replicate)
        require(match is not None, 'Exact terminal source replicate suffix required')
        label = match[1]
        _sample(label)
        require(label in labels and replicate in qc, 'Every source run must have one declared column and QC row')
        runs.append((run_id, replicate, run_date, label, qc[replicate]))
        run_ids.add(run_id)
        replicates.add(replicate)
        bases.add(label)
    require(replicates == set(qc) and bases == set(labels),
        'Exact source run/QC and matrix-column membership required; no rows may be dropped')
    return tuple(runs)


def _column(name, dtype='string', unit=None, description=None):
    return {'name':name, 'dtype':dtype, 'nullable':False, 'unit':unit,
        'description':description or ('Retained source ' + name)}


def _table(dataset_id, name, frame, columns, *, method=None, unavailable=False):
    from schema.catalogue_adapter import FrozenTable
    reasons = {'collections':'source_matrix_sample_columns', 'run_qc':'source_sequencing_runs',
        'kraken_abundance':'source_genus_by_column_cells', 'metaeuk_abundance':'source_genus_by_column_cells',
        'ranked_taxa':'unavailable_ranked_summary_rows'}
    value = {'name':name, 'object_id':None if unavailable else dataset_id + ':table:' + name,
        'row_count':None if unavailable else len(frame), 'entity':reasons[name],
        'denominator':'All supplied source rows or explicit cells for this method; no per-read or environmental denominator inferred',
        'columns':columns, 'availability':{'status':'unavailable', 'reason':'No source ranked summary is published by this conversion'}
            if unavailable else {'status':'available'},
        'completeness':'unavailable' if unavailable else 'complete'}
    if name in {'kraken_abundance', 'metaeuk_abundance'}:
        value.update(method=method, taxonomic_rank='genus', abundance_denominator='unknown')
    return FrozenTable.model_validate(value)


def metagenome_dataset(inputs, *, expected_sha256=None):
    """Pure complete source-qualified C10 normalization/export; no IO or approval."""
    import pandas as pd
    from ingestion.catalogue_adapter_inputs import dataset_exports
    from schema.catalogue_adapter import FrozenDataset
    require(type(inputs) is dict and set(inputs) == set(INPUTS), 'Exact declared metagenome input membership required')
    expected = {name:value[1] for name, value in INPUTS.items()} if expected_sha256 is None else expected_sha256
    require(type(expected) is dict and set(expected) == set(INPUTS), 'Explicit complete source input checksums required')
    hashes = {}
    for name, data in inputs.items():
        require(type(data) is bytes and 0 < len(data) <= MAX_INPUT_BYTES
            and type(expected[name]) is str
            and re.fullmatch(r'[a-f0-9]{64}', expected[name] or '')
            and hashlib.sha256(data).hexdigest() == expected[name], 'Exact source metagenome input checksum required')
        hashes[name] = expected[name]
    generation = hashlib.sha256(canonical(hashes)).hexdigest()
    kraken_labels, kraken, kraken_taxa = parse_matrix(inputs['Kraken.genus-sample.tsv'])
    meta_labels, metaeuk, meta_taxa = parse_matrix(inputs['MetaEuk.genus-sample.tsv'])
    require(set(kraken_labels) == set(meta_labels), 'Method column populations must match explicitly; no implicit missing-method zeros')
    runs = parse_runs(inputs['runid.tsv'], inputs['01.read_summary_gt1kb.tsv'], labels=kraken_labels)
    dataset_id = 'beta:metagenome:raw:' + generation
    library_ids = {label:'meta-column:' + hashlib.sha256((generation + '\n' + label).encode()).hexdigest()
        for label in kraken_labels}
    collections = []
    for label in kraken_labels:
        month, bay, station = _sample(label)
        collections.append({'library_id':library_ids[label], 'sample_id':label,
            'collection_date':month, 'bay':bay, 'station':station,
            'has_kraken':True, 'has_metaeuk':True, 'date_basis':'source_label_month'})
    run_rows = [{'run_id':'meta-run:' + hashlib.sha256((generation + '\n' + run).encode()).hexdigest(),
        'source_run_id':run, 'library_id':library_ids[label], 'run_date':run_date,
        'source_sample_replicate':replicate, **dict(zip(QC_NAMES, counts))}
        for run, replicate, run_date, label, counts in runs]
    def matrix_rows(cells, method):
        return [{'measurement_id':'meta-cell:' + hashlib.sha256(canonical([generation, method, row, column])).hexdigest(),
            'library_id':library_ids[label], 'taxon':taxon, 'method':method,
            'taxonomic_rank':'genus', 'abundance':value, 'source_value':text,
            'source_row':row, 'source_column':column}
            for label, taxon, value, text, row, column in cells]
    frames = {'collections':pd.DataFrame(collections), 'run_qc':pd.DataFrame(run_rows),
        'kraken_abundance':pd.DataFrame(matrix_rows(kraken, 'Kraken')),
        'metaeuk_abundance':pd.DataFrame(matrix_rows(metaeuk, 'MetaEuk'))}
    abundance_columns = [_column('measurement_id'), _column('library_id'), _column('taxon'),
        _column('method'), _column('taxonomic_rank'), _column('abundance', 'number', 'unknown'),
        _column('source_value', description='Exact original decimal source cell text; no unit/denominator inference'),
        _column('source_row', 'integer', 'source_tsv_rows', 'One-based source matrix row including header'),
        _column('source_column', 'integer', 'source_tsv_columns', 'One-based data-row field including the unlabeled taxon field')]
    tables = [
        _table(dataset_id, 'collections', frames['collections'], [
            _column('library_id'), _column('sample_id'), _column('collection_date'), _column('bay'),
            _column('station'), _column('has_kraken', 'boolean'), _column('has_metaeuk', 'boolean'), _column('date_basis')]),
        _table(dataset_id, 'run_qc', frames['run_qc'], [
            _column('run_id'), _column('source_run_id'), _column('library_id'), _column('run_date'),
            _column('source_sample_replicate'), *[_column(name, 'integer', 'source_reads' if name.startswith('n_reads')
                else 'source_bases') for name in QC_NAMES]]),
        _table(dataset_id, 'kraken_abundance', frames['kraken_abundance'], abundance_columns, method='Kraken'),
        _table(dataset_id, 'metaeuk_abundance', frames['metaeuk_abundance'], abundance_columns, method='MetaEuk'),
        _table(dataset_id, 'ranked_taxa', None, [_column('summary_id'), _column('library_id'), _column('taxon'),
            _column('method'), _column('abundance', 'number', 'unknown')], unavailable=True),
    ]
    dataset = FrozenDataset.model_validate({'dataset_id':dataset_id, 'source_id':SOURCE_ID,
        'family':'metagenome', 'collection_id':'beta:metagenome:source-columns:' + generation,
        'title':{'en':'Existing raw Kraken and MetaEuk genus matrices', 'ja':'既存の生Kraken・MetaEuk属行列'},
        'purpose':{'en':'Source-qualified descriptive access to every supplied column, run and genus matrix cell',
            'ja':'供給された全列・ラン・属行列セルへの出典条件付き記述的参照'},
        'descriptor':{'family':'metagenome', 'measurement':'source_reported_genus_abundance',
            'abundance_unit':'unknown', 'abundance_denominator':'unknown',
            'method':'Kraken and MetaEuk, retained separately', 'taxonomic_rank':'genus', 'omitted_taxa':'unknown'},
        'collection_date_precision':'month', 'qualification':' '.join(QUALIFICATIONS),
        'methods':['Exact source matrix parsing, no cell filtering or abundance normalization',
            'Explicit source run-to-column label/replicate convention, no run aggregation',
            'Original decimal text retained alongside numeric float64 view'], 'tables':tables, 'related_ids':[]})
    captured = dataset_exports(dataset, frames, generation=generation)
    counts = {'source_columns':len(collections), 'source_runs':len(run_rows),
        'kraken_taxa':kraken_taxa, 'metaeuk_taxa':meta_taxa,
        'kraken_cells':len(kraken), 'metaeuk_cells':len(metaeuk),
        'kraken_explicit_zeros':sum(value == 0 for _, _, value, _, _, _ in kraken),
        'metaeuk_explicit_zeros':sum(value == 0 for _, _, value, _, _, _ in metaeuk)}
    return dataset, frames, captured, generation, counts


def planned_metagenome(inputs, *, expected_sha256=None):
    from retrieval.source_scope import EvidenceScope, FAMILIES
    from schema.catalogue_snapshot import SnapshotManifest, SourceCapture, manifest_id
    dataset, frames, captured, generation, counts = metagenome_dataset(inputs, expected_sha256=expected_sha256)
    scope = EvidenceScope.model_validate({'version':1, 'sources':{
        family:{'enabled':family == 'metagenome', 'filters':{}} for family in FAMILIES}})
    manifest = SnapshotManifest(scope=scope, source_captures=[SourceCapture(
        source_id=SOURCE_ID, source_family='metagenome', source_generation=generation,
        publication_generation='beta-raw-operational-only-v1',
        classification_generation='none-inferred:beta-raw-v1', relationship_generation='none-inferred:beta-raw-v1',
        operation_generation='c10-v1:c13-v1', capture_method='beta-verified-raw-metagenome-source-cells-v1',
        qualifiers=list(QUALIFICATIONS))], objects=list(captured.objects),
        operation_versions={item.operation_id:item.operation_version for item in captured.objects})
    return {'dataset':dataset, 'frames':frames, 'captured':captured, 'manifest':manifest,
        'snapshot_id':manifest_id(manifest), 'source_generation':generation, 'counts':counts}


def source_guard(revision):
    base = ctd_module()
    pins = base.source_guard(revision)
    name = 'deploy/gcp/beta/data/prepare_metagenome.py'
    path = ROOT / name
    require(path.is_file() and not path.is_symlink() and base.git('show', revision + ':' + name) == path.read_bytes(),
        'Metagenome preparation must equal its explicit committed source revision')
    pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return pins


def prepare(*, raw_package, source_root, output, revision, applying=False):
    from schema.catalogue_snapshot import manifest_bytes
    raw = ctd_module().raw_module()
    output = raw.clean_absolute(output)
    require(not output.is_relative_to(ROOT) and not output.is_relative_to(raw.HISTORICAL_ROOT)
        and not output.is_relative_to(Path(raw_package)), 'Private output must be separate from source and raw-package trees')
    require(not output.exists() and not output.is_symlink(), 'A new private output directory is required')
    raw.safe_ancestors(output.parent)
    source_guard(revision)
    inputs, provenance = verified_metagenome_bytes(raw_package, source_root)
    planned = planned_metagenome(inputs)
    pins = source_guard(revision)
    result = {'version':'ocean-beta-metagenome-preparation-v1', 'project_id':PROJECT,
        'state':'qualified_metagenome_plan_only', 'source_revision':revision,
        'source_pins_sha256':hashlib.sha256(canonical(pins)).hexdigest(),
        'dataset_id':planned['dataset'].dataset_id, 'source_generation':planned['source_generation'],
        'snapshot_id':planned['snapshot_id'], **planned['counts'], **provenance,
        'scientific_approval':False, 'abundance_unit':'unknown', 'abundance_denominator':'unknown',
        'cloud_calls':False, 'c09_snapshot_sealed':False, 'cloud_published':False, 'research_enabled':False,
        'output_created':False, 'qualifications':list(QUALIFICATIONS)}
    if not applying:
        return result
    output.mkdir(mode=0o700)
    raw.private_bytes(output / 'manifest.json', manifest_bytes(planned['manifest']))
    (output / 'objects').mkdir(mode=0o700)
    files = []
    for number, item in enumerate(planned['captured'].objects):
        path = f'objects/{number:02d}-{item.sha256}'
        raw.private_bytes(output / path, dict(planned['captured'].contents)[item.object_id])
        files.append({'path':path, 'object_id':item.object_id, 'sha256':item.sha256, 'bytes':item.size_bytes})
    source_guard(revision)
    raw.private_bytes(output / 'export-files.json', canonical({'files':files, 'source_pins':pins}))
    result.update(state='qualified_metagenome_exports_prepared', output_created=True)
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
        print(json.dumps({'state':'refused', 'error':'Qualified metagenome preparation failed; retain private inputs and partial output for inspection',
            'cloud_calls':False, 'scientific_approval':False, 'cloud_published':False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
