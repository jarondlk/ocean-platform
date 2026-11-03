"""C13 coalesces only canonical C11/C12 family carriers across real sources."""
from copy import deepcopy

import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from orchestration.frozen_edna_catalogue import EDNAAccess, FrozenEDNACatalogueAdapter
from orchestration.frozen_scientific_catalogue import FrozenScientificCatalogueAdapter, ScientificAccess
from orchestration.frozen_sst_catalogue import FrozenSSTCatalogueAdapter, SSTAccess
from schema.context_catalogue import CatalogueFilters, ListingRequest, OperationRequest
from schema.edna_catalogue_fixtures import edna_fixture, seal_edna_fixture
from schema.scientific_catalogue import ScientificRegistry
from schema.scientific_catalogue_fixtures import scientific_scope, seal_scientific_fixture
from schema.sst_catalogue_fixtures import sst_fixture, seal_sst_fixture


def configured(tmp_path, *, shared_children=False, metadata_change=None, scientific_shadow=None):
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda _: True)
    edna = [edna_fixture(2, dataset_id='test:edna:' + name,
        source_id='test-edna-' + name, provider_project_id='Project-' + name) for name in ('a', 'b')]
    sst = [sst_fixture(4, dataset_id='test:sst:' + name, source_id='test-sst-' + name)
        for name in ('a', 'b')]
    if metadata_change:
        metadata_change(edna, sst)
    fixtures = [*edna, *sst]
    bindings = []
    for family, values, seal in [('edna_metabarcoding', edna, seal_edna_fixture),
            ('remote_sensing', sst, seal_sst_fixture)]:
        common = seal(store, values) if shared_children else None
        for metadata, frames in values:
            sid = common if common else seal(store, [(metadata, frames)])
            bindings.append({'dataset_id':metadata.dataset_id, 'source_family':family,
                'source_id':metadata.source_id, 'snapshot_id':sid})
    definitions = []
    if scientific_shadow:
        definitions = [{'id':scientific_shadow, 'title':{'en':'Hidden shadow', 'ja':'非表示の別名'},
            'purpose':{'en':'Synthetic denied shadow', 'ja':'合成の拒否された別名'},
            'category':'source_documentation', 'values':{'synthetic':True},
            'input_dataset_ids':[fixtures[0][0].dataset_id], 'provenance':{'references':['Synthetic only']}}]
    registry = ScientificRegistry(datasets=bindings, definitions=definitions)
    index = seal_scientific_fixture(store, registry, {})
    policy = {'denied':set(), 'source_calls':[], 'scientific_calls':[]}

    def eligible(snapshot, metadata):
        policy['source_calls'].append(metadata.dataset_id)
        return metadata.dataset_id not in policy['denied']

    def scientific(snapshot, item):
        policy['scientific_calls'].append(item.id)
        return False

    adapters = {
        'edna_metabarcoding':FrozenEDNACatalogueAdapter(store=store,
            access=EDNAAccess('user-a', 'revision-1', eligible)),
        'remote_sensing':FrozenSSTCatalogueAdapter(store=store,
            access=SSTAccess('user-a', 'revision-1', eligible)),
    }
    combined = FrozenScientificCatalogueAdapter(store=store, adapters=adapters,
        access=ScientificAccess('user-a', 'revision-1', scientific))
    return index, combined, {m.dataset_id for m, _ in fixtures}, policy


def request(index, **changes):
    return ListingRequest(snapshot_id=index, scope=scientific_scope(),
        access_binding='user-a', access_revision='revision-1', **changes)


@pytest.mark.parametrize('shared_children', [False, True])
def test_multiple_edna_providers_and_sst_sources_have_complete_unique_membership(tmp_path, shared_children):
    sid, adapter, identities, _ = configured(tmp_path, shared_children=shared_children)
    found, cursor = [], None
    while True:
        page = adapter.list(request(sid, limit=1, cursor=cursor,
            filters=CatalogueFilters(kinds=['dataset'])))
        assert page.total.value == 4
        found.extend(node.id for node in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert set(found) == identities and len(found) == len(set(found)) == 4
    result = adapter.query(OperationRequest(snapshot_id=sid, scope=scientific_scope(),
        access_binding='user-a', access_revision='revision-1', operation_id='c13.inventory',
        operation_version='c13-v1', input_ids=['root:data']))
    assert result.rows[0]['count'] == 4 and result.rows[0]['entity'] == 'datasets'


def test_denial_omits_only_actual_source_dataset_after_namespace_validation(tmp_path):
    sid, adapter, identities, policy = configured(tmp_path)
    policy['denied'].add('test:edna:a')
    result = adapter.list(request(sid, limit=500, filters=CatalogueFilters(kinds=['dataset'])))
    assert {node.id for node in result.items} == identities - {'test:edna:a'}
    assert result.total.value == 3


@pytest.mark.parametrize('carrier', ['c11:sst', 'c12:edna'])
def test_hidden_scientific_record_cannot_claim_global_family_carrier(tmp_path, carrier):
    sid, adapter, _, policy = configured(tmp_path, scientific_shadow=carrier)
    with pytest.raises(ValueError, match='collid|carrier'):
        adapter.list(request(sid))
    assert policy['source_calls'] == policy['scientific_calls'] == []


@pytest.mark.parametrize('family,carrier', [
    ('edna_metabarcoding', 'c11:sst'), ('remote_sensing', 'c12:edna')])
def test_source_owned_collection_cannot_shadow_other_family_carrier(tmp_path, family, carrier):
    def change(edna, sst):
        target = edna if family == 'edna_metabarcoding' else sst
        target[0][0].collection_id = carrier
    sid, adapter, _, policy = configured(tmp_path, metadata_change=change)
    with pytest.raises(ValueError, match='collid|carrier'):
        adapter.list(request(sid))
    assert policy['source_calls'] == policy['scientific_calls'] == []


@pytest.mark.parametrize('family', ['edna_metabarcoding', 'remote_sensing'])
def test_equal_source_owned_directory_ids_are_still_rejected(tmp_path, family):
    def change(edna, sst):
        target = edna if family == 'edna_metabarcoding' else sst
        for metadata, _ in target:
            metadata.collection_id = 'test:source-owned-collection-collision'
    sid, adapter, _, policy = configured(tmp_path, metadata_change=change)
    with pytest.raises(ValueError, match='collid|carrier'):
        adapter.list(request(sid))
    assert policy['source_calls'] == policy['scientific_calls'] == []


@pytest.mark.parametrize('family,carrier', [
    ('edna_metabarcoding', 'c12:edna'), ('remote_sensing', 'c11:sst')])
@pytest.mark.parametrize('changes', [
    {'title':{'en':'A source-owned title', 'ja':'ソース所有タイトル'}},
    {'parent_id':'root:metadata'}, {'root':'metadata'}, {'kind':'table'},
    {'source_family':'ctd'}, {'related_ids':['test:source-link']},
])
def test_carrier_id_alone_never_bypasses_shape_label_or_ownership_checks(tmp_path, monkeypatch, family, carrier, changes):
    sid, adapter, _, policy = configured(tmp_path)
    native = adapter.adapters[family]
    original = type(native)._nodes

    def changed(datasets, listing):
        nodes = original(datasets, listing)
        nodes[carrier] = nodes[carrier].model_copy(update=deepcopy(changes))
        return nodes

    monkeypatch.setattr(native, '_nodes', changed)
    with pytest.raises(ValueError, match='carrier'):
        adapter.list(request(sid))
    assert policy['source_calls'] == policy['scientific_calls'] == []
