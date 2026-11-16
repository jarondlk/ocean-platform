"""Fresh-base eDNA preparation preserves enabled Research and original science."""
import copy
import hashlib
import json

import pandas as pd
import pytest

from api.v1_catalogue_host import _canonical
from deploy.gcp.beta.data import prepare_research_edna as operator
from ingestion.edna_catalogue_inputs import dataset_exports
from ingestion.immutable_bundle import canonical_bytes
from tests.test_beta_edna_preparation import synthetic_bundle
from tests.test_beta_snapshot_catalogue import sealed as sealed


def source_dataset():
    return operator.edna.normalized_datasets(synthetic_bundle())[0]


def test_operational_metadata_supersession_keeps_all_original_scientific_bytes_and_lineage():
    original = source_dataset()
    dataset, tables, captured, receipt = operator.qualify_current_inventory(*original)
    assert original[0].qualification == ' '.join(operator.edna.QUALIFICATIONS)
    assert dataset.qualification == ' '.join(operator.QUALIFICATIONS)
    assert 'Existing Research remains enabled' in dataset.qualification
    assert 'production experiment execution remain gated' in dataset.qualification
    assert 'all beta scientific/research execution gates remain false' not in dataset.qualification
    assert dataset.model_dump(exclude={'qualification'}) == original[0].model_dump(exclude={'qualification'})
    for role in tables:
        pd.testing.assert_frame_equal(tables[role], original[1][role])
    assert {obj.role: obj.sha256 for obj in captured.objects if obj.role != 'canonical_rows'} == {
        obj.role: obj.sha256 for obj in original[2].objects if obj.role != 'canonical_rows'}
    assert receipt['original_generated_metadata_sha256'] != receipt['current_generated_metadata_sha256']
    assert receipt['scientific_table_hashes_unchanged']


def test_supersession_refuses_unrecognized_original_qualification():
    dataset, tables, captured = source_dataset()
    with pytest.raises(ValueError, match='original generated'):
        operator.qualify_current_inventory(dataset.model_copy(update={'qualification': 'unrecognized'}), tables, captured)


@pytest.fixture
def selected(sealed):
    _, output, plan, prepared = sealed
    store = prepared['store']
    store.access_gate = lambda _: True
    store.add_reference(plan['index_id'], 'c17:dependency:' + 'c' * 64)
    store.add_reference(plan['index_id'], 'c21:dependency:' + 'd' * 64)
    store.set_hold(plan['index_id'], True)
    document = json.loads((output / 'activation.json').read_bytes())
    document['research_enabled'] = True
    from deploy.gcp.beta.data.append_catalogue import append_groups
    from ingestion.catalogue_adapter_inputs import dataset_exports as data_exports
    from ingestion.sst_catalogue_inputs import dataset_exports as sst_exports
    from schema.catalogue_adapter_fixtures import metagenome_fixture
    from schema.sst_catalogue_fixtures import sst_fixture
    groups = []
    for (metadata, frames), export in [(metagenome_fixture(3), data_exports), (sst_fixture(3), sst_exports)]:
        groups.append({'label': {'en': 'Synthetic original input', 'ja': '元の合成入力'},
            'qualifications': ['Synthetic only'],
            'datasets': [(metadata, frames, export(metadata, frames, generation='synthetic-base-v3'))]})
    document, _ = append_groups(store=store, activation=document, groups=groups,
        authorization_ref='synthetic-only-three-family-base', research_enabled=True)
    raw = _canonical(document)
    digest = hashlib.sha256(raw).hexdigest()
    key = 'v1/catalogue/activations/' + digest + '.json'
    (output / 'store' / key).write_bytes(raw)
    keys = {'v1/catalogue/control.json', key}
    for identity in store.lifecycle()['snapshots']:
        manifest, _ = store.read(identity)
        keys.add('v1/catalogue/manifests/' + identity + '.json')
        keys.update('v1/catalogue/objects/' + obj.sha256 for obj in manifest.objects)
    objects = []
    for key in sorted(keys):
        raw = (output / 'store' / key).read_bytes()
        objects.append({'key': key, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'generation': 123})
    selection = {'version': operator.VERSION, 'project_id': operator.PROJECT, 'research_enabled': True,
        'activation_sha256': digest, 'control_generation': 123, 'objects': objects}
    return output / 'store', selection, digest, document


def test_exact_base_selection_does_not_mutate_inputs_or_discard_retention(selected):
    root, selection, digest, document = selected
    before = {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    _, control, activation = operator.selected_base(root, selection, digest)
    assert activation == document and activation['research_enabled'] is True
    assert any(key.startswith('c17:') for key in control['references'])
    assert any(key.startswith('c21:') for key in control['references'])
    assert any(item['held'] for item in control['snapshots'].values())
    assert before == {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('change', ['missing', 'extra', 'hash', 'size', 'generation', 'mode', 'activation', 'duplicate'])
def test_base_requires_complete_exact_immutable_selection_before_output(selected, change):
    root, original, digest, _ = selected
    selection = copy.deepcopy(original)
    if change == 'missing':
        selection['objects'].pop()
    elif change == 'extra':
        selection['objects'].append({'key': 'v1/catalogue/objects/' + 'f' * 64,
            'sha256': 'f' * 64, 'bytes': 1, 'generation': 1})
    elif change == 'hash':
        selection['objects'][0]['sha256'] = 'f' * 64
    elif change == 'size':
        selection['objects'][0]['bytes'] += 1
    elif change == 'generation':
        selection['control_generation'] = True
    elif change == 'mode':
        selection['research_enabled'] = False
    elif change == 'activation':
        selection['activation_sha256'] = 'e' * 64
    else:
        selection['objects'].append(copy.deepcopy(selection['objects'][0]))
    with pytest.raises((ValueError, OSError)):
        operator.selected_base(root, selection, digest)


def test_source_guard_pins_new_operator_as_well_as_every_loaded_owner(monkeypatch):
    from deploy.gcp.beta.data import prepare_cohorts
    monkeypatch.setattr(prepare_cohorts, 'source_pins', lambda revision: {'synthetic-original-source': 'a' * 64})
    monkeypatch.setattr(operator.ctd, 'git', lambda *args: b'wrong committed bytes')
    with pytest.raises(ValueError, match='selected commit'):
        operator.source_pins('b' * 40)


@pytest.mark.parametrize('old_ctd_only', [False, True])
def test_portable_activation_serialization_is_accepted_but_old_ctd_base_is_not(selected, old_ctd_only):
    root, selection, old_digest, document = selected
    document = copy.deepcopy(document)
    if old_ctd_only:
        document['snapshots'] = document['snapshots'][:1]
    raw = (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode()
    digest = hashlib.sha256(raw).hexdigest()
    key = 'v1/catalogue/activations/' + digest + '.json'
    (root / key).write_bytes(raw)
    selection = copy.deepcopy(selection)
    selection['activation_sha256'] = digest
    selection['objects'] = [x for x in selection['objects'] if '/activations/' not in x['key']]
    selection['objects'].append({'key': key, 'sha256': digest, 'bytes': len(raw), 'generation': 123})
    if old_ctd_only:
        with pytest.raises(ValueError, match='three-family'):
            operator.selected_base(root, selection, digest)
    else:
        assert operator.selected_base(root, selection, digest)[2] == document


def test_full_39_dataset_preparation_preserves_base_and_records_metadata_supersessions(selected, tmp_path, monkeypatch):
    root, selection, digest, document = selected
    selection_path = tmp_path / 'selection.json'
    selection_path.write_bytes(canonical_bytes(selection))
    output = tmp_path / 'prepared-b2'
    base_control = (root / 'v1/catalogue/control.json').read_bytes()
    monkeypatch.setattr(operator, 'source_pins', lambda revision: {'synthetic': 'a' * 64})
    monkeypatch.setattr(operator.edna, 'verified_bundles', lambda *args: range(39))
    original_triple = source_dataset()

    def datasets(index):
        original, tables, _ = original_triple
        current = original.model_copy(update={'dataset_id': 'synthetic:b2:dataset:' + str(index),
            'collection_id': 'synthetic:b2:collection:' + str(index)}, deep=True)
        # Give each source its own table object identity while retaining the
        # row populations and generated qualification being superseded.
        specs = [item.model_copy(update={'object_id': current.dataset_id + ':table:' + item.name}) for item in current.tables]
        current = current.model_copy(update={'tables': specs})
        return [(current, tables, dataset_exports(current, tables, generation='synthetic-v3'))]

    monkeypatch.setattr(operator.edna, 'normalized_datasets', datasets)
    # The real source guard is exercised separately; the actual publication
    # structural/lifecycle/byte validator remains active on this synthetic tree.
    from deploy.gcp.beta.data import publish_append
    monkeypatch.setattr(publish_append, '_source_guard', lambda value: None)
    receipt = operator.prepare(revision='b' * 40, output=output, base_store=root,
        selection_path=selection_path, expected_activation=digest,
        edna_metadata=tmp_path, edna_normalized=tmp_path)
    assert receipt['new_datasets'] == 39 and receipt['research_enabled'] is True
    assert receipt['cloud_calls'] is receipt['base_current_in_cloud_verified'] is False
    assert (root / 'v1/catalogue/control.json').read_bytes() == base_control
    activation = json.loads((output / 'activation.json').read_bytes())
    assert activation['snapshots'][:-1] == document['snapshots']
    assert activation['scientific_approval'] is False
    assert len(json.loads((output / 'metadata-supersessions.json').read_bytes())) == 39
    control = json.loads((output / 'store/v1/catalogue/control.json').read_bytes())
    before = json.loads(base_control)
    assert all(control['references'][key] == value for key, value in before['references'].items())
    assert control['audits'][:before['revision']] == before['audits']
