"""Synthetic source contracts for qualified metagenome preparation; no cloud."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('beta_metagenome_preparation',
    HERE / 'deploy/gcp/beta/data/prepare_metagenome.py')
meta = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(meta)


def inputs():
    return {
        'Kraken.genus-sample.tsv': b'2024-04-O-s0\t2024-05-I-hm\nGenusA\t0\t12.500\nGenusB\t1.5e-2\t0\n',
        'MetaEuk.genus-sample.tsv': b'2024-04-O-s0\t2024-05-I-hm\nGenusA\t0\t3\nGenusC\t2.250\t0\nGenusD\t0\t1\n',
        'runid.tsv': b'source-r1\t2024-04-O-s0.1\t2024-06-12\nsource-r2\t2024-04-O-s0.2\t2024-06-13\nsource-r3\t2024-05-I-hm.1\t2024-07-15\n',
        '01.read_summary_gt1kb.tsv': b'2024-04-O-s0.1\t10\t100000\t2\t30000\n2024-04-O-s0.2\t20\t200000\t3\t40000\n2024-05-I-hm.1\t30\t300000\t4\t50000\n',
    }


def pins(value):
    return {key:hashlib.sha256(data).hexdigest() for key, data in value.items()}


def planned(value=None):
    value = inputs() if value is None else value
    return meta.planned_metagenome(value, expected_sha256=pins(value))


def test_full_source_columns_runs_cells_and_explicit_zeros_retained():
    result = planned()
    assert result['counts'] == {'source_columns':2, 'source_runs':3, 'kraken_taxa':2,
        'metaeuk_taxa':3, 'kraken_cells':4, 'metaeuk_cells':6,
        'kraken_explicit_zeros':2, 'metaeuk_explicit_zeros':3}
    frames = result['frames']
    assert frames['collections'].sample_id.tolist() == ['2024-04-O-s0', '2024-05-I-hm']
    assert frames['collections'].collection_date.tolist() == ['2024-04', '2024-05']
    assert frames['run_qc'].source_run_id.tolist() == ['source-r1', 'source-r2', 'source-r3']
    assert frames['run_qc'].run_date.tolist() == ['2024-06-12', '2024-06-13', '2024-07-15']
    assert frames['run_qc'].n_reads_gt1kb.tolist() == [10, 20, 30]
    assert frames['run_qc'].bases_gt1kb.tolist() == [100000, 200000, 300000]
    assert frames['run_qc'].library_id.iloc[0] == frames['run_qc'].library_id.iloc[1]
    assert frames['run_qc'].run_id.nunique() == 3


def test_unknown_units_and_denominators_are_literal_and_ranked_summary_absent():
    result = planned()
    dataset = result['dataset']
    assert dataset.collection_date_precision == 'month'
    assert dataset.descriptor.abundance_unit == dataset.descriptor.abundance_denominator == 'unknown'
    assert dataset.descriptor.omitted_taxa == 'unknown'
    assert 'not independently verified physical extraction libraries' in dataset.qualification
    assert 'scientific approval is false' in dataset.qualification
    tables = {item.name:item for item in dataset.tables}
    for name, method in [('kraken_abundance', 'Kraken'), ('metaeuk_abundance', 'MetaEuk')]:
        assert tables[name].method == method and tables[name].taxonomic_rank == 'genus'
        assert tables[name].abundance_denominator == 'unknown'
        assert next(c.unit for c in tables[name].columns if c.name == 'abundance') == 'unknown'
        assert result['frames'][name].method.eq(method).all()
    assert tables['ranked_taxa'].availability.status == 'unavailable'
    assert tables['ranked_taxa'].row_count is None and tables['ranked_taxa'].object_id is None
    assert 'ranked_taxa' not in result['frames']


def test_exact_decimal_text_and_original_source_locators_survive_export():
    from ingestion.catalogue_adapter_inputs import load_dataset
    result = planned()
    source = result['captured']
    metadata = next(item for item in source.objects if item.role == 'dataset_metadata')
    decoded = load_dataset(result['manifest'], dict(source.contents), metadata)
    values = decoded.tables['kraken_abundance']
    assert set(values.source_value) == {'0', '12.500', '1.5e-2'}
    exact = values.loc[values.source_value == '12.500'].iloc[0]
    assert exact.abundance == 12.5 and (exact.source_row, exact.source_column) == (2, 3)
    assert decoded.tables['run_qc'].bases_gt1kb.sum() == 600000


def test_stable_identity_and_payloads_do_not_mutate_caller_inputs():
    original = inputs()
    before = deepcopy(original)
    first, second = planned(original), planned(original)
    assert original == before
    assert first['snapshot_id'] == second['snapshot_id']
    assert first['source_generation'] == second['source_generation']
    assert dict(first['captured'].contents) == dict(second['captured'].contents)
    altered = deepcopy(original)
    altered['01.read_summary_gt1kb.tsv'] = altered['01.read_summary_gt1kb.tsv'].replace(b'100000', b'100001')
    assert planned(altered)['source_generation'] != first['source_generation']


def test_method_column_order_can_differ_without_cross_column_reinterpretation():
    value = inputs()
    value['MetaEuk.genus-sample.tsv'] = b'2024-05-I-hm\t2024-04-O-s0\nGenusA\t7.500\t0\n'
    result = planned(value)
    frame = result['frames']['metaeuk_abundance']
    library = result['frames']['collections'].set_index('sample_id').loc['2024-05-I-hm', 'library_id']
    observed = frame.loc[frame.library_id == library].iloc[0]
    assert observed.source_value == '7.500' and observed.source_column == 2


@pytest.mark.parametrize('bad', [b'', b'NA', b'NaN', b'inf', b'-1', b' 1', b'1 ', b'1e9999', b'1e-9999'])
def test_bad_or_missing_abundance_cells_cannot_be_dropped_or_filled(bad):
    data = b'2024-04-O-s0\nGenusA\t' + bad + b'\n'
    with pytest.raises(meta.MetagenomePreparationError):
        meta.parse_matrix(data)


@pytest.mark.parametrize('raw', [
    b'2024-04-O-s0\t2024-04-O-s0\nGenusA\t1\t2\n',
    b'2024-04-O-s0\nGenusA\t1\nGenusA\t2\n',
    b'2024-04-O-s0\nGenusA\t1\t2\n',
    b'2024-04-O-s0\t2024-05-I-hm\nGenusA\t1\n',
    b'2024-04-O-s0\n GenusA\t1\n',
    b'2024-04-O-s0\n\nGenusA\t1\n',
    b'2024-13-O-s0\nGenusA\t1\n',
    b'2024-04-unknown-label\nGenusA\t1\n',
    b'2024-04-O-s0\nGenusA\t\xff\n',
])
def test_unqualified_or_incomplete_matrix_inventory_rejected(raw):
    with pytest.raises(meta.MetagenomePreparationError):
        meta.parse_matrix(raw)


@pytest.mark.parametrize('change', [
    lambda d: d.update({'runid.tsv': d['runid.tsv'] + d['runid.tsv'].splitlines(keepends=True)[0]}),
    lambda d: d.update({'runid.tsv': d['runid.tsv'].replace(b'source-r2', b'source-r1')}),
    lambda d: d.update({'runid.tsv': d['runid.tsv'].replace(b'2024-06-12', b'2024-02-30')}),
    lambda d: d.update({'runid.tsv': d['runid.tsv'].replace(b'2024-06-12', b'2024-06')}),
    lambda d: d.update({'runid.tsv': d['runid.tsv'].replace(b'2024-04-O-s0.1', b'2024-04-O-s0')}),
    lambda d: d.update({'01.read_summary_gt1kb.tsv': d['01.read_summary_gt1kb.tsv'].replace(b'\t10\t', b'\t10.5\t')}),
    lambda d: d.update({'01.read_summary_gt1kb.tsv': d['01.read_summary_gt1kb.tsv'].replace(b'\t10\t', b'\t-10\t')}),
    lambda d: d.update({'01.read_summary_gt1kb.tsv': d['01.read_summary_gt1kb.tsv'].replace(b'\t10\t', b'\t9223372036854775808\t')}),
    lambda d: d.update({'01.read_summary_gt1kb.tsv': d['01.read_summary_gt1kb.tsv'].splitlines(keepends=True)[0]}),
    lambda d: d.update({'01.read_summary_gt1kb.tsv': d['01.read_summary_gt1kb.tsv'] + d['01.read_summary_gt1kb.tsv'].splitlines(keepends=True)[0]}),
])
def test_run_and_read_count_inventories_require_exact_explicit_join(change):
    value = inputs()
    change(value)
    with pytest.raises(meta.MetagenomePreparationError):
        planned(value)


def test_method_population_mismatch_is_not_imputed_as_zero():
    value = inputs()
    value['MetaEuk.genus-sample.tsv'] = b'2024-04-O-s0\nGenusA\t0\n'
    with pytest.raises(meta.MetagenomePreparationError, match='column populations'):
        planned(value)


def test_exact_input_membership_and_checksums_required():
    value = inputs()
    expected = pins(value)
    value['runid.tsv'] += b'\n'
    with pytest.raises(meta.MetagenomePreparationError, match='checksum'):
        meta.metagenome_dataset(value, expected_sha256=expected)
    del value['runid.tsv']
    with pytest.raises(meta.MetagenomePreparationError, match='membership'):
        meta.metagenome_dataset(value, expected_sha256=expected)


def test_source_refusal_happens_before_private_output_or_source_reads(tmp_path, monkeypatch):
    def refuse(revision):
        raise meta.MetagenomePreparationError('test source checkpoint absent')
    def forbidden(*args):
        raise AssertionError('Actual scientific source must not be read after checkpoint refusal')
    monkeypatch.setattr(meta, 'source_guard', refuse)
    monkeypatch.setattr(meta, 'verified_metagenome_bytes', forbidden)
    output = tmp_path / 'not-created'
    with pytest.raises(meta.MetagenomePreparationError, match='checkpoint'):
        meta.prepare(raw_package=tmp_path / 'raw', source_root=tmp_path / 'source',
            output=output, revision='0' * 40, applying=True)
    assert not output.exists()


def test_actual_c10_adapter_refuses_abundance_summary_with_unknown_denominator(tmp_path):
    from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
    from orchestration.frozen_catalogue import AdapterAccess, FrozenCatalogueAdapter
    from schema.context_catalogue import OperationRequest
    result = planned()
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda _: True)
    sid = store.seal(result['manifest'], dict(result['captured'].contents))
    adapter = FrozenCatalogueAdapter(store=store,
        access=AdapterAccess('meta-test-owner', 'meta-test-current', lambda snapshot, dataset: True))
    operation = OperationRequest(snapshot_id=sid, scope=result['manifest'].scope,
        operation_id='c10.summary', operation_version='c10-v1', input_ids=[result['dataset'].dataset_id],
        parameters={'table':'kraken_abundance', 'column':'abundance'},
        access_binding='meta-test-owner', access_revision='meta-test-current')
    response = adapter.query(operation).result
    assert response.receipt.availability.status == 'unavailable'
    assert response.rows == []
