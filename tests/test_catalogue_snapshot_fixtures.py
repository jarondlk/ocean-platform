"""Executable adapter handoff and persisted-example replay, without a live DB."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import time

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.catalogue_snapshot_capture import CaptureHeads
from ingestion.catalogue_snapshot_fixtures import FIXTURE_ROWS, fixture_registry, fixture_snapshot
from ingestion.catalogue_snapshot_transfer import import_quarantined, transfer_id
from schema.catalogue_snapshot import manifest_id
from scripts.export_catalogue_snapshot import generated_files

ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_schema_and_examples_are_current():
    for path, expected in generated_files().items():
        assert path.read_text() == expected


def test_persisted_example_reopens_and_imports_without_source_or_embeddings(tmp_path):
    value = json.loads((ROOT / "schema/catalogue_snapshot_examples.json").read_text())
    contents = {key: base64.b64decode(data, validate=True)
                for key, data in value["contents_base64"].items()}
    root = tmp_path / "independent-v1"
    store = LocalCatalogueSnapshotStore(root=root, access_gate=lambda manifest: True)
    identity = store.seal(value["snapshot"], contents)
    assert identity == value["snapshot_id"]
    reopened = LocalCatalogueSnapshotStore(root=root, access_gate=lambda manifest: True)
    assert reopened.read(identity)[1] == contents
    assert transfer_id(value["transfer"]) == value["transfer_id"]
    imported = import_quarantined(
        value["transfer"], contents, destination_id="synthetic:v1-destination",
        store=reopened, quarantine_root=tmp_path / "quarantine",
        authorize=lambda transfer: True, eligible=lambda obj, origin: True,
    )
    assert imported.snapshot_id != identity
    assert imported.object_count == 8
    assert sum(count for _, count in imported.row_counts) == 12
    assert reopened.latest() == (None, 0)


def test_frozen_registration_exports_all_roles_with_supplied_source_generations():
    rows = deepcopy(FIXTURE_ROWS)
    registry = fixture_registry(rows=rows)
    rows["ctd"]["casts"].clear()
    heads = CaptureHeads({name: f"new:{name}" for name in registry.required_heads})
    objects = []
    contents = {}
    for requirement in registry.requirements:
        result = requirement.exporter(None, heads, time.monotonic() + 10)
        assert {obj.role for obj in result.objects} == set(requirement.schema_versions)
        assert all(obj.provenance.source_generation == f"new:source:{requirement.source_id}"
                   for obj in result.objects)
        objects.extend(result.objects)
        contents.update(result.contents)
    assert len(objects) == 8
    assert len(json.loads(contents["synthetic:ctd:casts"])) == 1
    assert {obj.role for obj in objects if obj.source_id == "edna_metabarcoding"} == {
        "canonical_rows", "classifications",
    }


def test_old_snapshot_bytes_survive_new_generation_and_changes_are_computed(tmp_path):
    store = LocalCatalogueSnapshotStore(root=tmp_path, access_gate=lambda manifest: True)
    old, original = fixture_snapshot()
    first = store.seal(old, original)
    rows = deepcopy(FIXTURE_ROWS)
    rows["ctd"]["depth_observations"][0]["temperature_degC"] = -2.0
    new, updated = fixture_snapshot(rows=rows, generation="generation-2")
    second = store.seal(new, updated)
    assert first != second == manifest_id(new)
    assert store.read(first)[1] == original
    assert store.read(second)[1] == updated
    changes = store.changes(first, second)
    assert "synthetic:ctd:depth_observations" in changes["replaced_object_ids"]
