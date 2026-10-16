"""C13 retains the existing C01 publication decision with real frozen eDNA."""
from copy import deepcopy

import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.immutable_bundle import digest
from orchestration.frozen_edna_catalogue import EDNAAccess, FrozenEDNACatalogueAdapter
from orchestration.frozen_scientific_catalogue import FrozenScientificCatalogueAdapter, ScientificAccess
from preprocessing.edna_analysis import protocol
from schema.context_catalogue import OperationRequest
from schema.edna_catalogue_fixtures import edna_fixture, edna_scope, seal_edna_fixture
from schema.scientific_catalogue import ScientificRegistry
from schema.scientific_catalogue_fixtures import scientific_fixture, seal_scientific_fixture
from tests.test_conference_demo import miyagi_choices


@pytest.mark.parametrize("valid", [True, False])
def test_frozen_published_table_keeps_exact_c01_scope_evidence(tmp_path, valid):
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda manifest: True)
    source, frames = edna_fixture(1)
    frames["occurrences"].loc[:, "collection_date_utc"] = "2020-01-01"
    frames["assays"].loc[:, "sequencing_method"] = "MiSeq"
    frames["assays"].loc[:, "target_gene"] = "12S rRNA"
    assay = frames["assays"].iloc[0].to_dict()
    protocol_id = digest(protocol(assay))
    child = seal_edna_fixture(store, [(source, frames)])
    registry, tables = scientific_fixture(23, bindings=[{
        "dataset_id": source.dataset_id, "source_id": source.source_id,
        "source_family": "edna_metabarcoding", "snapshot_id": child,
    }])
    payload = registry.model_dump(mode="json")
    option = deepcopy(miyagi_choices()[1])
    option["protocol_ids"] = [protocol_id]
    option["protocols"] = {protocol_id: protocol(assay)}
    option["recipe_scope"]["assignment_method"] = "qcauto_95pct_3nn_target"
    selected = edna_scope(assignment_method="qcauto_95pct_3nn_target", time_from="2020-01-01",
                          time_to="2023-12-31", sample_kind="environmental", is_control=False).model_dump(mode="json")
    selected["sources"]["edna_metabarcoding"]["analysis_id"] = option["analysis_id"]
    analysis = payload["analyses"][0]
    analysis.update(id=option["analysis_id"], scope=selected, scope_option=option)
    payload["workflows"][0].update(workflow_kind="fish_frequency", analysis_ids=[analysis["id"]])
    registry = ScientificRegistry.model_validate(payload)
    snapshot = seal_scientific_fixture(store, registry, tables)
    source_adapter = FrozenEDNACatalogueAdapter(store=store, access=EDNAAccess("user", "rev", lambda *args: True))
    adapter = FrozenScientificCatalogueAdapter(store=store, adapters={"edna_metabarcoding": source_adapter},
        access=ScientificAccess("user", "rev", lambda *args: True))
    result = adapter.query(OperationRequest(snapshot_id=snapshot, scope=selected, operation_id="c13.table",
        operation_version="c13-v1", input_ids=[analysis["id"]], access_binding="user", access_revision="rev",
        parameters={"table": "results", "workflow_kind": "fish_frequency", "protocol_id": protocol_id if valid else "f" * 64, "limit": 10}))
    if valid:
        assert result.receipt.scope_compatibility.outcome == "compatible"
        assert result.receipt.scope_compatibility.analysis_id == analysis["id"]
        assert any(item.field == "protocol_id" and item.source == "selection" for item in result.receipt.scope_compatibility.evidence)
        assert result.receipt.total_rows.value == 23
        assert len(result.rows) == 10 and result.next_offset == 10
        assert result.receipt.authority == "published"
    else:
        assert result.receipt.availability.status == "unavailable"
        assert result.rows == [] and result.receipt.total_rows.value is None
