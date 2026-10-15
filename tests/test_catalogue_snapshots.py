"""Synthetic-only sealed snapshot and serialized lifecycle acceptance."""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from ingestion.catalogue_snapshot import (
    LocalCatalogueSnapshotStore,
    SnapshotAccessDenied,
)
from ingestion.provenance_snapshot import SnapshotConflict, SnapshotNotFound
from retrieval.source_scope import FAMILIES
from schema.catalogue_snapshot import (
    SnapshotManifest,
    compare_snapshots,
    manifest_bytes,
    manifest_id,
)


def example(
    *,
    data=b'[{"cast":"synthetic-1"}]',
    generation="g1",
    family="ctd",
    role="canonical_rows",
    object_id="ctd:rows",
    dataset_id="ctd:synthetic",
):
    sha = hashlib.sha256(data).hexdigest()
    manifest = {
        "scope": {
            "version": 1,
            "sources": {
                name: {"enabled": name == family, "filters": {}} for name in FAMILIES
            },
        },
        "source_captures": [
            {
                "source_id": "source:synthetic",
                "source_family": family,
                "source_generation": generation,
                "publication_generation": "p1",
                "classification_generation": "c1",
                "relationship_generation": "r1",
                "operation_generation": "o1",
                "capture_method": "synthetic-consistent-export-v1",
                "qualifiers": ["Synthetic; no scientific approval implied"],
            }
        ],
        "objects": [
            {
                "object_id": object_id,
                "dataset_id": dataset_id,
                "source_id": "source:synthetic",
                "source_family": family,
                "role": role,
                "sha256": sha,
                "size_bytes": len(data),
                "schema_version": "synthetic-rows-v1",
                "operation_id": "export:rows",
                "operation_version": "v1",
                "provenance": {"source_generation": generation, "content_sha256": sha},
            }
        ],
        "operation_versions": {"export:rows": "v1"},
    }
    if family == "edna_metabarcoding":
        classification = {
            **manifest["objects"][0],
            "object_id": "edna:classifications",
            "role": "classifications",
        }
        manifest["objects"].append(classification)
    return SnapshotManifest.model_validate(manifest), {
        obj["object_id"]: data for obj in manifest["objects"]
    }


def store_at(root):
    return LocalCatalogueSnapshotStore(root=root, access_gate=lambda _: True)


@pytest.fixture
def store(tmp_path):
    return store_at(tmp_path / "independent-v1")


def seal(store, **kwargs):
    return store.seal(*example(**kwargs))


def promote(store, identity):
    return store.promote(identity, expected_generation=store.latest()[1])


def test_stable_identity_exact_bytes_replay_and_restart(store):
    manifest, objects = example()
    original = manifest.model_dump(mode="json")
    identity = store.seal(manifest, objects)
    assert identity == manifest_id(manifest)
    assert store.latest() == (None, 0)
    assert store.seal(manifest, objects) == identity
    assert len(store.lifecycle()["audits"]) == 1
    assert store_at(store.root).read(identity)[1] == objects
    assert manifest.model_dump(mode="json") == original
    assert store.promote(identity, expected_generation=0) == 1
    assert store_at(store.root).latest() == (identity, 1)
    assert store.promote(identity, expected_generation=1) == 1
    assert len(store.lifecycle()["audits"]) == 2


def test_order_independence_for_sources_and_objects(store):
    manifest, objects = example(family="edna_metabarcoding", object_id="edna:rows")
    before = manifest_bytes(manifest)
    manifest.objects.reverse()
    assert manifest_bytes(manifest) == before
    assert store.seal(manifest, objects) == hashlib.sha256(before).hexdigest()


@pytest.mark.parametrize(
    "field",
    [
        "source_generation",
        "publication_generation",
        "classification_generation",
        "relationship_generation",
        "operation_generation",
        "capture_method",
        "qualifiers",
    ],
)
def test_capture_metadata_changes_identity(field):
    manifest, _ = example()
    old = manifest_id(manifest)
    source = manifest.source_captures[0]
    setattr(source, field, ["changed"] if field == "qualifiers" else "changed")
    if field == "source_generation":
        manifest.objects[0].provenance.source_generation = "changed"
    assert manifest_id(manifest) != old


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "family",
        "generation",
        "hash",
        "operation_id",
        "operation_version",
        "disabled",
        "duplicate",
        "extra",
        "eDNA",
        "eDNA_pairing",
        "ownership",
    ],
)
def test_manifest_source_and_contract_validation(change):
    manifest, _ = example()
    value = manifest.model_dump(mode="json")
    obj = value["objects"][0]
    if change == "source":
        obj["source_id"] = "other"
    elif change == "family":
        obj["source_family"] = "metagenome"
    elif change == "generation":
        obj["provenance"]["source_generation"] = "other"
    elif change == "hash":
        obj["provenance"]["content_sha256"] = "f" * 64
    elif change == "operation_id":
        obj["operation_id"] = "wrong"
    elif change == "operation_version":
        obj["operation_version"] = "wrong"
    elif change == "disabled":
        value["scope"]["sources"]["ctd"]["enabled"] = False
    elif change == "duplicate":
        value["objects"].append(obj.copy())
    elif change == "extra":
        value["embedding_complete"] = True
    elif change == "eDNA":
        value, _ = example(family="edna_metabarcoding")
        value = value.model_dump(mode="json")
        value["objects"].pop()
    elif change == "eDNA_pairing":
        value, _ = example(family="edna_metabarcoding")
        value = value.model_dump(mode="json")
        value["objects"][1]["dataset_id"] = "edna:other"
    elif change == "ownership":
        other = {**value["source_captures"][0], "source_id": "source:second"}
        value["source_captures"].append(other)
        value["objects"].append(
            {**obj, "object_id": "other:object", "source_id": "source:second"}
        )
    with pytest.raises(ValidationError):
        SnapshotManifest.model_validate(value)


def test_mutated_model_is_revalidated(store):
    manifest, objects = example()
    manifest.objects[0].operation_version = "wrong"
    with pytest.raises(ValidationError):
        store.seal(manifest, objects)
    assert store.lifecycle()["snapshots"] == {}


@pytest.mark.parametrize("mutation", ["missing", "extra", "hash", "type", "size"])
def test_exact_object_membership_and_bytes(store, mutation):
    manifest, objects = example()
    if mutation == "missing":
        objects.clear()
    elif mutation == "extra":
        objects["extra"] = b""
    elif mutation == "hash":
        objects["ctd:rows"] = b"X" * len(objects["ctd:rows"])
    elif mutation == "type":
        objects["ctd:rows"] = bytearray(objects["ctd:rows"])
    else:
        objects["ctd:rows"] += b" "
    with pytest.raises(ValueError):
        store.seal(manifest, objects)
    assert store.lifecycle()["snapshots"] == {}


def test_old_manifest_reopens_after_new_snapshot_without_embeddings(store):
    old = seal(store)
    promote(store, old)
    new = seal(store, data=b'[{"cast":"synthetic-2"}]', generation="g2")
    promote(store, new)
    assert store.read(old)[1] == example()[1]
    assert store.latest() == (new, 2)
    assert store.changes(old, new) == {
        "removed_object_ids": [],
        "added_object_ids": [],
        "replaced_object_ids": ["ctd:rows"],
    }
    assert "embedding" not in manifest_bytes(store.read(old)[0]).decode()


def test_changes_derive_removed_and_added_canonical_identities():
    old, _ = example()
    new, _ = example(object_id="ctd:new")
    assert compare_snapshots(old, new) == {
        "removed_object_ids": ["ctd:rows"],
        "added_object_ids": ["ctd:new"],
        "replaced_object_ids": [],
    }


def test_stale_pointer_cas_does_not_advance_latest(store):
    first = seal(store)
    second = seal(store, generation="g2")
    assert store.promote(first, expected_generation=0) == 1
    with pytest.raises(SnapshotConflict):
        store.promote(second, expected_generation=0)
    assert store.latest() == (first, 1)


def test_seal_and_lifecycle_changes_do_not_self_invalidate_latest_cas(store):
    generation = store.latest()[1]
    identity = seal(store)
    store.set_hold(identity, True)
    store.add_reference(identity, "investigation:test")
    assert store.promote(identity, expected_generation=generation) == 1


def test_capture_rollover_failure_leaves_latest_unchanged(store):
    first = seal(store)
    promote(store, first)
    second = seal(store, generation="g2")
    before = store.lifecycle()

    def rollover():
        raise SnapshotConflict("Publication rolled over")

    with pytest.raises(SnapshotConflict):
        store.promote(second, expected_generation=1, validate_capture=rollover)
    assert store.lifecycle() == before
    assert store.latest() == (first, 1)


@pytest.mark.parametrize("which", ["manifest", "object", "missing", "oversized"])
def test_corrupt_incomplete_or_oversized_bundle_rejects_read_and_promotion(
    store, which
):
    identity = seal(store)
    manifest, _ = example()
    if which == "manifest":
        path = store.root / store.prefix / "manifests" / (identity + ".json")
    else:
        path = store.root / store.prefix / "objects" / manifest.objects[0].sha256
    if which == "missing":
        path.unlink()
    elif which == "oversized":
        path.write_bytes(b"x" * (manifest.objects[0].size_bytes + 1))
    else:
        data = path.read_bytes()
        path.write_bytes(b"!" + data[1:])
    with pytest.raises((ValueError, SnapshotNotFound)):
        store.read(identity)
    with pytest.raises((ValueError, SnapshotNotFound)):
        store.promote(identity, expected_generation=0)
    assert store.lifecycle()["latest"] is None


@pytest.mark.parametrize(
    "bad",
    [
        "../escape",
        "/absolute",
        "v1/../escape",
        "v1//catalogue",
        "v1/./catalogue",
        "v1\\catalogue",
        "legacy/catalogue",
    ],
)
def test_unsafe_namespace_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        LocalCatalogueSnapshotStore(
            root=tmp_path, prefix=bad, access_gate=lambda _: True
        )


def test_requires_explicit_absolute_root_and_gate(tmp_path):
    with pytest.raises(ValueError):
        LocalCatalogueSnapshotStore(root=Path("relative"), access_gate=lambda _: True)
    with pytest.raises(ValueError):
        LocalCatalogueSnapshotStore(root=tmp_path, access_gate=None)


@pytest.mark.parametrize(
    "location",
    [
        "root",
        "ancestor",
        "namespace",
        "control",
        "lock",
        "caslock",
        "object",
        "manifest",
    ],
)
def test_symlinks_rejected_for_reads_writes_and_lifecycle(tmp_path, location):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "store"
    if location == "root":
        root.symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError):
            store_at(root)
        return
    if location == "ancestor":
        root.symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError):
            store_at(root / "nested")
        return
    store = store_at(root)
    identity = seal(store)
    manifest, _ = example()
    paths = {
        "namespace": root / "v1",
        "control": root / store.prefix / "control.json",
        "lock": root / store.prefix / "control.lock",
        "caslock": root / store.prefix / "control.json.lock",
        "object": root / store.prefix / "objects" / manifest.objects[0].sha256,
        "manifest": root / store.prefix / "manifests" / (identity + ".json"),
    }
    path = paths[location]
    moved = tmp_path / "saved"
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=moved.is_dir())
    if location == "caslock":
        with pytest.raises(ValueError):
            store.set_hold(identity, True)
    else:
        with pytest.raises(ValueError):
            store.read(identity)


@pytest.mark.parametrize("kind", ["fifo", "directory"])
def test_nonregular_object_is_rejected_without_blocking(store, kind):
    identity = seal(store)
    manifest, _ = example()
    path = store.root / store.prefix / "objects" / manifest.objects[0].sha256
    path.unlink()
    if kind == "fifo":
        import os

        os.mkfifo(path)
    else:
        path.mkdir()
    with pytest.raises(ValueError):
        store.read(identity)


def test_manifest_and_object_returned_values_are_isolated(store):
    identity = seal(store)
    manifest, contents = store.read(identity)
    manifest.objects.clear()
    contents.clear()
    assert store.read(identity)[1] == example()[1]


def test_access_gate_and_persisted_revocation_override_old_snapshot(store):
    old = seal(store)
    promote(store, old)
    new = seal(store, generation="g2")
    promote(store, new)
    denied = LocalCatalogueSnapshotStore(root=store.root, access_gate=lambda _: False)
    for action in (
        lambda: denied.read(old),
        denied.latest,
        lambda: denied.add_reference(old, "denied"),
        lambda: denied.promote(old, expected_generation=2),
    ):
        with pytest.raises(SnapshotAccessDenied):
            action()
    store.revoke(old)
    with pytest.raises(SnapshotAccessDenied):
        store_at(store.root).read(old)
    assert store.seal(*example()) == old
    with pytest.raises(SnapshotAccessDenied):
        store.read(old)
    store.revoke(new)
    with pytest.raises(SnapshotAccessDenied):
        store.latest()


def test_gate_cannot_mutate_manifest_and_must_return_literal_true(store):
    identity = seal(store)

    def mutating(manifest):
        manifest.objects.clear()
        return True

    gate = LocalCatalogueSnapshotStore(root=store.root, access_gate=mutating)
    assert len(gate.read(identity)[0].objects) == 1
    bad = LocalCatalogueSnapshotStore(root=store.root, access_gate=lambda _: 1)
    with pytest.raises(SnapshotAccessDenied):
        bad.read(identity)


def test_references_and_holds_persist_and_protect_against_cleanup(store):
    referenced = seal(store)
    held = seal(store, generation="g2")
    current = seal(store, generation="g3")
    promote(store, current)
    store.add_reference(referenced, "investigation:retained")
    store.set_hold(held, True)
    restarted = store_at(store.root)
    assert restarted.cleanup([referenced, held, current])["retired_count"] == 0
    assert restarted.read(referenced)
    assert restarted.read(held)
    before = restarted.lifecycle()
    restarted.add_reference(referenced, "investigation:retained")
    restarted.set_hold(held, True)
    assert restarted.lifecycle() == before
    with pytest.raises(SnapshotConflict):
        restarted.add_reference(held, "investigation:retained")
    with pytest.raises(SnapshotConflict):
        restarted.remove_reference(held, "investigation:retained")
    restarted.remove_reference(referenced, "investigation:retained")
    restarted.set_hold(held, False)
    report = restarted.cleanup([referenced, held, current])
    assert report["retired_count"] == 2
    assert report["physical_deleted_count"] == 0
    assert set(report["retired_ids"]) == {referenced, held}
    assert restarted.lifecycle()["audits"][-1]["retired_count"] == 2
    assert (store.root / store.prefix / "manifests" / (referenced + ".json")).exists()
    for identity in (referenced, held):
        for action in (
            lambda: restarted.read(identity),
            lambda: restarted.set_hold(identity, True),
            lambda: restarted.add_reference(identity, "late"),
            lambda: restarted.seal(
                *example(generation="g1" if identity == referenced else "g2")
            ),
        ):
            with pytest.raises(SnapshotNotFound):
                action()
    state = restarted.lifecycle()
    assert restarted.cleanup([referenced, held])["retired_count"] == 0
    assert restarted.lifecycle() == state


def test_dry_run_is_observation_with_no_audit_or_reservation(store):
    identity = seal(store)
    before = store.lifecycle()
    report = store.cleanup([identity], dry_run=True)
    assert report["eligible_ids"] == [identity]
    assert report["retired_count"] == 0
    assert store.lifecycle() == before
    store.set_hold(identity, True)
    assert store.cleanup([identity])["retired_count"] == 0


@pytest.mark.parametrize(
    "action",
    ["seal", "promote", "hold", "reference", "unreference", "revoke", "cleanup"],
)
def test_failed_commit_changes_no_state_or_success_audit(store, monkeypatch, action):
    identity = seal(store)
    store.add_reference(identity, "existing")
    before = store.lifecycle()

    def fail(*args, **kwargs):
        raise OSError("Synthetic disk failure before atomic state commit")

    monkeypatch.setattr(store.store, "replace", fail)
    functions = {
        "seal": lambda: seal(store, generation="g2"),
        "promote": lambda: promote(store, identity),
        "hold": lambda: store.set_hold(identity, True),
        "reference": lambda: store.add_reference(identity, "new"),
        "unreference": lambda: store.remove_reference(identity, "existing"),
        "revoke": lambda: store.revoke(identity),
        "cleanup": lambda: store.cleanup([seal_id]),
    }
    # Cleanup needs an actually eligible unreferenced snapshot.
    seal_id = identity
    if action == "cleanup":
        monkeypatch.undo()
        seal_id = seal(store, generation="g2")
        before = store.lifecycle()
        monkeypatch.setattr(store.store, "replace", fail)
    with pytest.raises(OSError):
        functions[action]()
    assert store.lifecycle() == before
    assert store_at(store.root).read(identity)[1] == example()[1]


def test_interrupted_registration_bytes_never_become_readable(store, monkeypatch):
    manifest, contents = example()
    identity = manifest_id(manifest)

    def fail(*args, **kwargs):
        raise OSError("Synthetic initial state commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(store.store, "replace", fail)
        with pytest.raises((OSError, SnapshotNotFound)):
            store.seal(manifest, contents)
    assert store.latest() == (None, 0)
    with pytest.raises(SnapshotNotFound):
        store.read(identity)
    assert store.seal(manifest, contents) == identity


def test_error_after_atomic_replace_is_reconciled_truthfully(store, monkeypatch):
    identity = seal(store)
    original = store.store.replace

    def fail_after_commit(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("Synthetic post-commit mtime failure")

    monkeypatch.setattr(store.store, "replace", fail_after_commit)
    assert store.set_hold(identity, True) == 2
    assert store.lifecycle()["snapshots"][identity]["held"] is True
    assert store.lifecycle()["audits"][-1]["action"] == "hold"


@pytest.mark.parametrize("first", ["hold", "cleanup"])
def test_hold_cleanup_ordering_under_same_real_file_lock(store, monkeypatch, first):
    identity = seal(store)
    reached = threading.Event()
    release = threading.Event()
    original = store._commit

    def blocked(state, generation, *, action, details):
        if action == ("hold" if first == "hold" else "retire"):
            reached.set()
            assert release.wait(5)
        return original(state, generation, action=action, details=details)

    monkeypatch.setattr(store, "_commit", blocked)
    other = store_at(store.root)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first_future = (
            workers.submit(store.set_hold, identity, True)
            if first == "hold"
            else workers.submit(store.cleanup, [identity])
        )
        assert reached.wait(5)
        second_future = (
            workers.submit(other.cleanup, [identity])
            if first == "hold"
            else workers.submit(other.set_hold, identity, True)
        )
        assert not second_future.done()
        release.set()
        result = first_future.result(timeout=5)
        if first == "hold":
            assert second_future.result(timeout=5)["retired_count"] == 0
            assert other.read(identity)
        else:
            assert result["retired_count"] == 1
            with pytest.raises(SnapshotNotFound):
                second_future.result(timeout=5)
            with pytest.raises(SnapshotNotFound):
                other.read(identity)


def test_control_bound_failure_preserves_last_committed_state(store, monkeypatch):
    identity = seal(store)
    before = store.lifecycle()
    monkeypatch.setattr("ingestion.catalogue_snapshot.MAX_CONTROL_BYTES", 1)
    # Existing bounded state read itself fails, preserving state without truncation.
    with pytest.raises(ValueError):
        store.set_hold(identity, True)
    monkeypatch.undo()
    assert store.lifecycle() == before


def test_invalid_control_state_fails_closed(store):
    identity = seal(store)
    path = store.root / store.prefix / "control.json"
    data = json.loads(path.read_bytes())
    data["snapshots"][identity]["held"] = "false"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        store.read(identity)


def test_false_capture_validation_does_not_advance_latest(store):
    identity = seal(store)
    with pytest.raises(SnapshotConflict):
        store.promote(identity, expected_generation=0, validate_capture=lambda: False)
    assert store.latest() == (None, 0)


def test_export_artifact_bound_never_truncates_large_inventory(store):
    rows = (
        b"[" + b",".join(b'{"dataset_id":"synthetic"}' for _ in range(100_001)) + b"]"
    )
    manifest, contents = example(data=rows)
    identity = store.seal(manifest, contents)
    assert store.read(identity)[1]["ctd:rows"] == rows
    assert len(json.loads(rows)) == 100_001


def test_manifest_bound_rejects_without_registration(store, monkeypatch):
    monkeypatch.setattr("schema.catalogue_snapshot.MAX_MANIFEST_BYTES", 100)
    with pytest.raises(ValueError, match="manifest byte limit"):
        seal(store)
    assert store.lifecycle()["snapshots"] == {}


def test_aggregate_bytes_and_object_count_bounds_are_explicit():
    manifest, _ = example()
    value = manifest.model_dump(mode="json")
    value["objects"] = [
        {
            **value["objects"][0],
            "object_id": f"ctd:part-{index}",
            "size_bytes": 300_000_000,
        }
        for index in range(2)
    ]
    with pytest.raises(ValidationError, match="byte limit"):
        SnapshotManifest.model_validate(value)
    value["objects"] = [
        {**value["objects"][0], "object_id": f"ctd:part-{index}", "size_bytes": 0}
        for index in range(4001)
    ]
    with pytest.raises(ValidationError, match="4000"):
        SnapshotManifest.model_validate(value)


@pytest.mark.parametrize(
    "registry",
    ["classification_generation", "relationship_generation", "operation_generation"],
)
def test_mixed_global_registry_generations_reject(registry):
    manifest, _ = example()
    value = manifest.model_dump(mode="json")
    value["source_captures"].append(
        {**value["source_captures"][0], "source_id": "source:second", registry: "newer"}
    )
    value["objects"].append(
        {
            **value["objects"][0],
            "object_id": "second:rows",
            "dataset_id": "second:dataset",
            "source_id": "source:second",
        }
    )
    with pytest.raises(ValidationError, match="mixed global registry"):
        SnapshotManifest.model_validate(value)


def test_exact_copy_origin_hash_must_match_object_bytes():
    manifest, _ = example()
    value = manifest.model_dump(mode="json")
    value["objects"][0]["provenance"]["origin"] = {
        "origin_system": "synthetic-origin",
        "origin_object_id": "raw:rows",
        "source_snapshot_id": "origin:snapshot",
        "source_generation": "g1",
        "schema_version": "rows-v1",
        "operation_version": "export-v1",
        "content_sha256": "f" * 64,
        "scientific_qualification": "Synthetic only",
        "access_conditions": "Local fixture",
        "transfer_authorization_ref": "synthetic:authorization",
    }
    with pytest.raises(ValidationError, match="Exact copied origin hash"):
        SnapshotManifest.model_validate(value)


@pytest.mark.parametrize("actually_committed", [True, False])
def test_unobservable_failed_commit_surfaces_uncertainty(
    store, monkeypatch, actually_committed
):
    from ingestion.catalogue_snapshot import SnapshotCommitUncertain

    identity = seal(store)
    original_write = store.store.replace
    original_read = store.store.read
    failed = False

    def uncertain_write(*args, **kwargs):
        nonlocal failed
        if actually_committed:
            original_write(*args, **kwargs)
        failed = True
        raise OSError("Synthetic ambiguous write transport failure")

    def unavailable_read(*args, **kwargs):
        if failed:
            raise OSError("Synthetic state cannot be observed")
        return original_read(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(store.store, "replace", uncertain_write)
        patch.setattr(store.store, "read", unavailable_read)
        with pytest.raises(SnapshotCommitUncertain) as failure:
            store.promote(identity, expected_generation=0)
    assert failure.value.action == "promote"
    assert failure.value.details == {"snapshot_id": identity}
    assert failure.value.proposed_latest_generation == 1
    assert failure.value.proposed_revision == 2
    # A fresh observation provides reconciliation, rather than a blind retry.
    assert store.latest() == ((identity, 1) if actually_committed else (None, 0))


def test_failed_commit_with_missing_previous_state_is_uncertain(store, monkeypatch):
    from ingestion.catalogue_snapshot import SnapshotCommitUncertain

    identity = seal(store)

    def write_then_lose_state(*args, **kwargs):
        (store.root / store.prefix / "control.json").unlink()
        raise OSError("Synthetic loss of previously committed state")

    monkeypatch.setattr(store.store, "replace", write_then_lose_state)
    with pytest.raises(SnapshotCommitUncertain):
        store.set_hold(identity, True)
