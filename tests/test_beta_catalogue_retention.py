"""Same-authority synthetic CAS tests, not a claim of live GCS write access."""
import hashlib

import pytest

from ingestion.beta_catalogue_retention import BetaCatalogueRetentionStore
from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore, SnapshotAccessDenied, SnapshotCommitUncertain
from ingestion.gcs_catalogue_snapshot import PREFIX, GcsCatalogueSnapshotStore, validated_lifecycle
from ingestion.provenance_snapshot import SnapshotConflict, StoredObject
from tests.test_catalogue_snapshots import example
from tests.test_gcs_catalogue_snapshot import Memory


def reference(label="one"):
    return "c17:dependency:" + hashlib.sha256(label.encode()).hexdigest()


class WritableMemory(Memory):
    def __init__(self, root):
        super().__init__(root)
        self.writes, self.before_write, self.after_write = [], None, None

    def replace(self, key, data, *, expected_generation):
        if self.before_write:
            self.before_write(key, data)
        current = self.objects[key]
        if current.generation != expected_generation:
            raise SnapshotConflict("synthetic precondition rejection")
        assert key == PREFIX + "/control.json"
        validated_lifecycle(data)
        self.writes.append((key, data, expected_generation))
        self.objects[key] = StoredObject(data, current.generation + 1)
        if self.after_write:
            self.after_write(key, data)
        return current.generation + 1


def append(state, action, identity, **details):
    state["revision"] += 1
    state["audits"].append({"revision": state["revision"], "action": action,
        "snapshot_id": identity, **details})
    if action == "reference":
        state["references"][details["reference"]] = identity
    elif action == "revoke":
        state["snapshots"][identity]["revoked"] = True
    else:
        raise AssertionError("Unsupported synthetic action")


@pytest.fixture
def retained(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    local = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda _: True)
    identity = local.seal(*example())
    local.add_reference(identity, "c14:synthetic-registration")
    memory = WritableMemory(tmp_path)
    store = BetaCatalogueRetentionStore(access_gate=lambda _: True, _test_store=memory)
    return local, store, memory, identity


def test_retention_write_cannot_reuse_read_scope_observation(retained):
    _, store, memory, identity = retained
    with store.read_scope():
        with pytest.raises(ValueError, match="cannot share"):
            store.add_reference(identity, reference())
    assert memory.writes == []
    store.add_reference(identity, reference())
    assert store.lifecycle()["references"][reference()] == identity


def test_same_c09_control_reopens_after_restart_without_split_authority(retained):
    local, store, memory, identity = retained
    before = store.lifecycle()
    revision = store.add_reference(identity, reference())
    reopened = GcsCatalogueSnapshotStore(access_gate=lambda _: True, _test_store=memory)
    after = reopened.lifecycle()
    assert revision == before["revision"] + 1 == after["revision"]
    assert after["references"] == {**before["references"], reference(): identity}
    assert after["snapshots"] == before["snapshots"]
    assert after["latest"] == before["latest"] and after["latest_generation"] == before["latest_generation"]
    assert after["audits"][:-1] == before["audits"]
    assert store.add_reference(identity, reference()) == revision
    assert len(memory.writes) == 1
    assert all(key == PREFIX + "/control.json" for key, _, _ in memory.writes)
    assert reopened.read(identity)[1] == local.read(identity)[1]


@pytest.mark.parametrize("value", ["c14:dependency:" + "a" * 64, "c17:dependency:" + "A" * 64,
    "c17:dependency:" + "a" * 63, "c17:dependency:" + "a" * 65, "anything", None, 1])
def test_reference_namespace_is_explicit_and_cannot_mutate_other_authority(retained, value):
    _, store, memory, identity = retained
    with pytest.raises(ValueError):
        store.add_reference(identity, value)
    assert not memory.writes


def test_reference_collision_never_rebinds_another_snapshot(retained):
    local, store, memory, identity = retained
    other = local.seal(*example(data=b"other"))
    updated = WritableMemory(local.root)
    store = BetaCatalogueRetentionStore(access_gate=lambda _: True, _test_store=updated)
    store.add_reference(identity, reference())
    with pytest.raises(SnapshotConflict):
        store.add_reference(other, reference())
    assert store.lifecycle()["references"][reference()] == identity
    assert len(updated.writes) == 1


def test_definitive_cas_conflict_reloads_and_preserves_concurrent_reference(retained):
    _, store, memory, identity = retained
    def race(key, data):
        memory.before_write = None
        memory.control(lambda state: append(state, "reference", identity, reference=reference("racer")))
    memory.before_write = race
    store.add_reference(identity, reference())
    state = store.lifecycle()
    assert state["references"][reference("racer")] == state["references"][reference()] == identity
    assert len(memory.writes) == 1
    assert state["audits"][-2]["reference"] == reference("racer")


def test_withdrawal_during_reference_cas_denies_retry_without_resurrection(retained):
    _, store, memory, identity = retained
    def revoke(key, data):
        memory.before_write = None
        memory.control(lambda state: append(state, "revoke", identity))
    memory.before_write = revoke
    with pytest.raises(SnapshotAccessDenied):
        store.add_reference(identity, reference())
    assert not memory.writes
    assert reference() not in store.lifecycle()["references"]


def test_access_or_payload_failure_does_not_publish_any_reference(retained):
    _, _, memory, identity = retained
    denied = BetaCatalogueRetentionStore(access_gate=lambda _: False, _test_store=memory)
    with pytest.raises(SnapshotAccessDenied):
        denied.add_reference(identity, reference())
    assert not memory.writes
    def tamper(key):
        if "/objects/" in key:
            memory.hook = None
            old = memory.objects[key]
            memory.objects[key] = StoredObject(b"!" * len(old.data), old.generation + 1)
    memory.hook = tamper
    store = BetaCatalogueRetentionStore(access_gate=lambda _: True, _test_store=memory)
    with pytest.raises(ValueError):
        store.add_reference(identity, reference())
    assert not memory.writes


def test_missing_control_never_creates_new_registry(retained):
    _, store, memory, identity = retained
    del memory.objects[PREFIX + "/control.json"]
    with pytest.raises(ValueError):
        store.add_reference(identity, reference())
    assert not memory.writes


def test_committed_ack_loss_reconciles_exact_current_binding(retained):
    _, store, memory, identity = retained
    def lose_ack(key, data):
        memory.after_write = None
        raise TimeoutError("synthetic postcommit ack loss")
    memory.after_write = lose_ack
    revision = store.add_reference(identity, reference())
    assert revision == store.lifecycle()["revision"]
    assert store.lifecycle()["references"][reference()] == identity
    assert len(memory.writes) == 1


def test_unresolved_ack_loss_retains_uncertain_state_and_retries_idempotently(retained):
    _, store, memory, identity = retained
    def lose_ack_and_reads(key, data):
        memory.after_write = None
        def unreadable(key):
            raise OSError("synthetic read outage")
        memory.hook = unreadable
        raise TimeoutError("synthetic postcommit ack loss")
    memory.after_write = lose_ack_and_reads
    with pytest.raises(SnapshotCommitUncertain) as error:
        store.add_reference(identity, reference())
    assert error.value.action == "reference"
    assert error.value.details == {"snapshot_id": identity, "reference": reference()}
    memory.hook = None
    store.add_reference(identity, reference())
    assert len(memory.writes) == 1


def test_precommit_unknown_failure_is_not_falsely_reported_rolled_back(retained):
    _, store, memory, identity = retained
    def timeout(key, data):
        memory.before_write = None
        raise TimeoutError("synthetic uncertain request")
    memory.before_write = timeout
    with pytest.raises(SnapshotCommitUncertain):
        store.add_reference(identity, reference())
    assert reference() not in store.lifecycle()["references"]
    store.add_reference(identity, reference())
    assert len(memory.writes) == 1


def test_control_bound_fails_before_write(retained, monkeypatch):
    from ingestion import beta_catalogue_retention
    _, store, memory, identity = retained
    monkeypatch.setattr(beta_catalogue_retention, "MAX_CONTROL_BYTES", 1)
    with pytest.raises(ValueError, match="bound exceeded"):
        store.add_reference(identity, reference())
    assert not memory.writes


@pytest.mark.parametrize("name,args", [("remove_reference", ("a" * 64, reference())),
    ("seal", ({}, {})), ("promote", ("a" * 64,)), ("set_hold", ("a" * 64, False)),
    ("revoke", ("a" * 64,)), ("cleanup", (["a" * 64],))])
def test_all_nonadditive_operator_mutations_remain_unsupported(retained, name, args):
    _, store, memory, _ = retained
    with pytest.raises(NotImplementedError):
        getattr(store, name)(*args)
    assert not memory.writes


def test_production_rejects_synthetic_transport(retained, monkeypatch):
    _, _, memory, _ = retained
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    with pytest.raises(ValueError, match="Synthetic transport"):
        BetaCatalogueRetentionStore(access_gate=lambda _: True, _test_store=memory)
