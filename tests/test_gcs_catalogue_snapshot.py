"""Synthetic transport evidence for current, immutable, read-only GCS snapshots."""
import hashlib
import json

import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore, SnapshotAccessDenied
from ingestion.gcs_catalogue_snapshot import (
    BUCKET, PREFIX, GcsCatalogueSnapshotStore, validated_lifecycle,
)
from ingestion.immutable_bundle import canonical_bytes
from ingestion.provenance_snapshot import SnapshotConflict, SnapshotNotFound, StoredObject
from schema.catalogue_snapshot import manifest_bytes, manifest_id
from tests.test_catalogue_snapshots import example


class Memory:
    def __init__(self, root):
        self.objects = {}
        for path in root.rglob("*"):
            if path.is_file() and (path.name == "control.json" or "/objects/" in str(path)
                    or "/manifests/" in str(path)):
                self.objects[path.relative_to(root).as_posix()] = StoredObject(path.read_bytes(), 1)
        self.calls, self.hook = [], None

    def read(self, key, *, max_bytes):
        self.calls.append((key, max_bytes))
        if self.hook:
            self.hook(key)
        if key not in self.objects:
            raise SnapshotNotFound("synthetic missing object")
        obj = self.objects[key]
        if len(obj.data) > max_bytes:
            raise ValueError("synthetic bounded transport limit")
        return obj

    def control(self, change):
        key = PREFIX + "/control.json"
        previous = self.objects[key]
        state = json.loads(previous.data)
        change(state)
        self.objects[key] = StoredObject(canonical_bytes(state), previous.generation + 1)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    root = tmp_path / "snapshot-store"
    local = LocalCatalogueSnapshotStore(root=root, access_gate=lambda _: True)
    manifest, contents = example()
    identity = local.seal(manifest, contents)
    local.add_reference(identity, "test:catalogue")
    local.promote(identity, expected_generation=0)
    memory = Memory(root)
    reader = GcsCatalogueSnapshotStore(access_gate=lambda _: True, _test_store=memory)
    return local, reader, memory, identity, manifest, contents


def test_exact_nonempty_local_snapshot_reopens_through_readonly_reader(setup):
    local, reader, memory, identity, manifest, contents = setup
    loaded, retained = reader.read(identity)
    assert manifest_bytes(loaded) == manifest_bytes(manifest) and retained == contents
    assert reader.lifecycle() == local.lifecycle()
    assert reader.latest() == local.latest() == (identity, 1)
    assert all(key.startswith(PREFIX + "/") for key, _ in memory.calls)
    assert sum(key.endswith("control.json") for key, _ in memory.calls) >= 2


def test_control_contract_replays_all_real_local_mutations(tmp_path):
    local = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda _: True)
    a = local.seal(*example())
    b = local.seal(*example(data=b"second"))
    c = local.seal(*example(data=b"third"))
    local.promote(a, expected_generation=0)
    local.promote(b, expected_generation=1)
    local.add_reference(a, "test:reference")
    local.remove_reference(a, "test:reference")
    local.set_hold(a, True)
    local.set_hold(a, False)
    local.revoke(a)
    local.cleanup([a, c])
    state = local.lifecycle()
    assert validated_lifecycle(canonical_bytes(state)) == state


@pytest.mark.parametrize("operation", ["read", "lifecycle", "latest"])
def test_missing_control_never_becomes_empty_state(setup, operation):
    _, reader, memory, identity, _, _ = setup
    del memory.objects[PREFIX + "/control.json"]
    with pytest.raises(ValueError, match="control is unavailable"):
        getattr(reader, operation)(*([identity] if operation == "read" else []))


@pytest.mark.parametrize("change", [
    lambda s: s.update(revision=True),
    lambda s: s.update(revision=s["revision"] + 1),
    lambda s: s.update(latest_generation=77),
    lambda s: s.update(snapshots={}),
    lambda s: s.update(latest="0" * 64),
    lambda s: s.update(references={"test:forged": "0" * 64}),
    lambda s: s["audits"][0].update(action="unreviewed"),
    lambda s: s["audits"][0].update(revision=False),
    lambda s: s["audits"][0].update(extra="unreviewed"),
    lambda s: s["snapshots"][next(iter(s["snapshots"]))].update(revoked=True),
])
def test_incomplete_or_forged_lifecycle_and_audit_rejected(setup, change):
    _, reader, memory, _, _, _ = setup
    memory.control(change)
    with pytest.raises(ValueError, match="lifecycle or audit"):
        reader.lifecycle()


@pytest.mark.parametrize("raw", [b"", b"[]", b"not-json", b'{"revision":NaN}',
    b'{"revision":0,"revision":1}', b" " * (4 * 1024 * 1024 + 1)])
def test_invalid_control_bytes_refused_without_fallback(raw):
    with pytest.raises(ValueError):
        validated_lifecycle(raw)


def test_noncanonical_control_rejected(setup):
    _, reader, memory, _, _, _ = setup
    key = PREFIX + "/control.json"
    memory.objects[key] = StoredObject(json.dumps(reader.lifecycle(), indent=2).encode(), 2)
    with pytest.raises(ValueError):
        reader.lifecycle()


def test_unknown_snapshot_does_not_probe_immutable_payloads(setup):
    _, reader, memory, _, _, _ = setup
    with pytest.raises(SnapshotNotFound):
        reader.read("f" * 64)
    assert [key for key, _ in memory.calls] == [PREFIX + "/control.json"]


@pytest.mark.parametrize("target", ["manifest", "object"])
@pytest.mark.parametrize("corruption", ["missing", "wrong_hash", "oversize"])
def test_every_registered_payload_must_be_present_exact_and_bounded(setup, target, corruption):
    _, reader, memory, identity, manifest, _ = setup
    suffix = f"manifests/{identity}.json" if target == "manifest" else f"objects/{manifest.objects[0].sha256}"
    key = PREFIX + "/" + suffix
    previous = memory.objects[key]
    if corruption == "missing":
        del memory.objects[key]
    elif corruption == "wrong_hash":
        memory.objects[key] = StoredObject(b"!" * len(previous.data), previous.generation + 1)
    else:
        memory.objects[key] = StoredObject(b"x" * (4 * 1024 * 1024 + 1) if target == "manifest"
            else previous.data + b"!", previous.generation + 1)
    with pytest.raises(ValueError):
        reader.read(identity)


def test_hash_correct_but_noncanonical_manifest_is_rejected(setup):
    _, reader, memory, _, manifest, _ = setup
    raw = json.dumps(manifest.model_dump(mode="json"), indent=2).encode()
    identity = hashlib.sha256(raw).hexdigest()
    memory.objects[PREFIX + f"/manifests/{identity}.json"] = StoredObject(raw, 1)
    state = LocalCatalogueSnapshotStore._empty_state()
    state.update(revision=1, snapshots={identity: {"held": False, "revoked": False, "retired": False}},
        audits=[{"revision": 1, "action": "seal", "snapshot_id": identity}])
    memory.objects[PREFIX + "/control.json"] = StoredObject(canonical_bytes(state), 1)
    with pytest.raises(ValueError, match="not canonical"):
        reader.read(identity)


def test_schema_incoherent_manifest_is_rejected_even_with_exact_hash(setup):
    _, reader, memory, _, manifest, _ = setup
    value = manifest.model_dump(mode="json")
    value["objects"][0]["source_family"] = "metagenome"
    raw = canonical_bytes(value)
    identity = hashlib.sha256(raw).hexdigest()
    memory.objects[PREFIX + f"/manifests/{identity}.json"] = StoredObject(raw, 1)
    state = LocalCatalogueSnapshotStore._empty_state()
    state.update(revision=1, snapshots={identity: {"held": False, "revoked": False, "retired": False}},
        audits=[{"revision": 1, "action": "seal", "snapshot_id": identity}])
    memory.objects[PREFIX + "/control.json"] = StoredObject(canonical_bytes(state), 1)
    with pytest.raises(ValueError):
        reader.read(identity)


def test_current_denial_is_checked_before_and_after_payload(setup):
    _, _, memory, identity, _, _ = setup
    decisions = iter([True, False])
    reader = GcsCatalogueSnapshotStore(access_gate=lambda _: next(decisions), _test_store=memory)
    with pytest.raises(SnapshotAccessDenied):
        reader.read(identity)
    assert any("/objects/" in key for key, _ in memory.calls)
    memory.calls.clear()
    reader = GcsCatalogueSnapshotStore(access_gate=lambda _: 1, _test_store=memory)
    with pytest.raises(SnapshotAccessDenied):
        reader.read(identity)
    assert not any("/objects/" in key for key, _ in memory.calls)


def test_mutating_gate_receives_isolated_manifest(setup):
    _, _, memory, identity, manifest, _ = setup
    def gate(value):
        value.objects[0].size_bytes = 0
        return True
    reader = GcsCatalogueSnapshotStore(access_gate=gate, _test_store=memory)
    observed, _ = reader.read(identity)
    assert observed.objects[0].size_bytes == manifest.objects[0].size_bytes > 0


def test_second_object_is_verified_not_only_a_first_object_preview(setup):
    local, _, _, _, manifest, contents = setup
    data = b"another exact complete object"
    sha = hashlib.sha256(data).hexdigest()
    value = manifest.model_dump(mode="json")
    value["objects"].append({**value["objects"][0], "object_id": "ctd:second",
        "size_bytes": len(data), "sha256": sha,
        "provenance": {**value["objects"][0]["provenance"], "content_sha256": sha}})
    identity = local.seal(value, {**contents, "ctd:second": data})
    memory = Memory(local.root)
    reader = GcsCatalogueSnapshotStore(access_gate=lambda _: True, _test_store=memory)
    assert len(reader.read(identity)[1]) == 2
    memory.objects[PREFIX + "/objects/" + sha] = StoredObject(b"!" * len(data), 2)
    with pytest.raises(ValueError, match="object integrity"):
        reader.read(identity)


@pytest.mark.parametrize("change", ["generation", "revocation", "missing"])
def test_control_rechecked_after_payload_and_never_automatically_retried(setup, change):
    _, reader, memory, identity, _, _ = setup
    changed = False
    def hook(key):
        nonlocal changed
        if "/objects/" not in key or changed:
            return
        changed = True
        if change == "missing":
            del memory.objects[PREFIX + "/control.json"]
        elif change == "generation":
            old = memory.objects[PREFIX + "/control.json"]
            memory.objects[PREFIX + "/control.json"] = StoredObject(old.data, old.generation + 1)
        else:
            def revoke(state):
                state["revision"] += 1
                state["snapshots"][identity]["revoked"] = True
                state["audits"].append({"revision": state["revision"], "action": "revoke", "snapshot_id": identity})
            memory.control(revoke)
    memory.hook = hook
    with pytest.raises(ValueError if change == "missing" else SnapshotConflict):
        reader.read(identity)
    assert sum("/objects/" in key for key, _ in memory.calls) == 1


def test_revoked_snapshot_not_downloaded_and_lifecycle_result_detached(setup):
    local, reader, memory, identity, _, _ = setup
    state = reader.lifecycle()
    state["snapshots"].clear()
    assert reader.lifecycle()["snapshots"]
    local.revoke(identity)
    memory.objects[PREFIX + "/control.json"] = StoredObject(canonical_bytes(local.lifecycle()), 2)
    memory.calls.clear()
    with pytest.raises(SnapshotAccessDenied):
        reader.read(identity)
    assert [key for key, _ in memory.calls] == [PREFIX + "/control.json"]


@pytest.mark.parametrize("name", ["seal", "promote", "add_reference", "remove_reference", "set_hold", "revoke", "cleanup"])
def test_serving_reader_has_no_mutation_capability(setup, name):
    _, reader, memory, _, _, _ = setup
    with pytest.raises(NotImplementedError, match="read-only"):
        getattr(reader, name)("untrusted")
    assert memory.calls == []


@pytest.mark.parametrize("changes", [{"bucket": "data-infra-infobio"}, {"prefix": "v1/catalogue/../legacy"},
    {"prefix": "/v1/catalogue"}, {"prefix": "v1/catalogue/"}, {"access_gate": None}])
def test_foreign_target_and_implicit_authority_refused_without_client(changes):
    with pytest.raises(ValueError, match="isolated beta"):
        GcsCatalogueSnapshotStore(**{"access_gate": lambda _: True, **changes})


def test_injected_transport_is_test_only(setup, monkeypatch):
    _, _, memory, _, _, _ = setup
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    with pytest.raises(ValueError, match="explicit test"):
        GcsCatalogueSnapshotStore(access_gate=lambda _: True, _test_store=memory)


def test_actual_bounded_gcs_transport_pins_generations_and_never_lists(setup):
    _, _, memory, identity, manifest, contents = setup
    class Blob:
        def __init__(self, key):
            self.key, self.generation, self.size = key, None, None
        def reload(self):
            obj = memory.objects[self.key]
            self.generation, self.size = obj.generation, len(obj.data)
        def download_as_bytes(self, *, if_generation_match):
            obj = memory.objects[self.key]
            assert if_generation_match == obj.generation
            calls.append((self.key, if_generation_match))
            return obj.data
    class Bucket:
        def blob(self, key):
            return Blob(key)
    class Client:
        def bucket(self, name):
            assert name == BUCKET
            return Bucket()
        def list_blobs(self, *args, **kwargs):
            raise AssertionError("Object listing/discovery is forbidden")
    calls = []
    reader = GcsCatalogueSnapshotStore(access_gate=lambda _: True, client=Client())
    actual, payloads = reader.read(identity)
    assert manifest_id(actual) == manifest_id(manifest) and payloads == contents
    assert [key for key, _ in calls].count(PREFIX + "/control.json") == 2
    assert all(generation == 1 for _, generation in calls)
