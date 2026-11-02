"""Append publication preserves existing context retention and exact data."""
import json

import pytest

from deploy.gcp.beta.data.append_catalogue import append_groups
from ingestion.catalogue_adapter_inputs import dataset_exports
from ingestion.scientific_catalogue_inputs import load_registry
from schema.catalogue_adapter_fixtures import metagenome_fixture
from tests.test_beta_snapshot_catalogue import sealed as sealed


def group():
    dataset, frames = metagenome_fixture(3)
    captured = dataset_exports(dataset, frames, generation='synthetic-explicit-source-v2')
    return {'label': {'en': 'Additional qualified inputs', 'ja': '追加の入力'},
        'qualifications': ['Synthetic preparation acceptance; scientific approval false'],
        'datasets': [(dataset, frames, captured)]}


def test_append_preserves_old_data_audits_context_refs_and_publication_authority(sealed):
    _, output, plan, prepared = sealed
    store = prepared['store']
    store.add_reference(plan['index_id'], 'c17:dependency:' + 'a' * 64)
    before = store.lifecycle()
    store.access_gate = lambda manifest: True  # explicit synthetic operator authority
    old = json.loads((output / 'activation.json').read_bytes())
    new, receipt = append_groups(store=store, activation=old, groups=[group()],
        authorization_ref='synthetic-current-user-instruction')
    assert len(new['snapshots']) == 2 and new['snapshots'][0] == old['snapshots'][0]
    assert len(old['snapshots']) == 1  # caller's accepted activation stays unchanged
    after = store.lifecycle()
    assert after['audits'][:before['revision']] == before['audits']
    assert all(after['references'][key] == value for key, value in before['references'].items())
    assert after['latest'] is None and after['latest_generation'] == 0
    assert receipt['base_revision'] == before['revision']
    assert receipt['new_revision'] == after['revision']
    assert not new['scientific_approval'] and not new['research_enabled']
    manifest, contents = store.read(new['snapshots'][1]['descriptor']['snapshot_id'])
    registry = load_registry(manifest, contents).metadata
    assert len(registry.datasets) == 1
    assert not registry.analyses and not registry.relationships
    store.read(plan['child_id'])


def test_duplicate_existing_dataset_is_rejected_without_control_change(sealed):
    _, output, plan, prepared = sealed
    store = prepared['store']
    before = store.lifecycle()
    existing = {'label': {'en': 'duplicate', 'ja': '重複'}, 'qualifications': ['test only'],
        'datasets': [(plan['dataset'], plan['frames'], plan['child'])]}
    with pytest.raises(ValueError, match='Existing dataset'):
        append_groups(store=store, activation=json.loads((output / 'activation.json').read_bytes()),
            groups=[existing], authorization_ref='synthetic')
    assert store.lifecycle() == before


@pytest.mark.parametrize('key,value', [('scientific_approval', True), ('research_enabled', True),
    ('scientific_mode', 'published')])
def test_activation_cannot_introduce_unreviewed_science_authority(sealed, key, value):
    _, output, _, prepared = sealed
    authority = json.loads((output / 'activation.json').read_bytes())
    authority[key] = value
    before = prepared['store'].lifecycle()
    with pytest.raises(ValueError):
        append_groups(store=prepared['store'], activation=authority, groups=[group()],
            authorization_ref='synthetic')
    assert prepared['store'].lifecycle() == before
