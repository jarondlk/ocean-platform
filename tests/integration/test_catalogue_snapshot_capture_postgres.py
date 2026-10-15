"""Real C09 consistency/rollover acceptance on a verified disposable database.

Opt in with RUN_POSTGRES_INTEGRATION=1 and C09_TEST_DATABASE_URL. DATABASE_URL
is never consulted. The dedicated ocean_c09_* database must use a loopback URL
and observed loopback server, or the exact CI job-owned pinned RFC1918 server.
Every test owns a random schema and verifies zero matching schemas after teardown.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import threading
import time
import uuid
from dataclasses import replace

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine, delete, insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore, SnapshotCommitUncertain
from ingestion.catalogue_snapshot_capture import (
    CaptureBudget, CaptureError, CapturePublicationUncertain, CaptureRollover,
    CapturedSource, SourceExportRegistry, TableHeadCoordinator, capture_snapshot,
)
from ingestion.provenance_snapshot import SnapshotConflict
from schema.catalogue_snapshot import SnapshotObject
from schema.context_catalogue import Provenance
from tests.test_catalogue_snapshot_capture import FAMILIES, registry, scope


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires explicitly verified disposable C09 PostgreSQL",
)


def allowed_disposable_server_address(address):
    try:
        observed = ipaddress.ip_address(address or "")
    except ValueError:
        return False
    if observed.is_loopback:
        return True
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return False
    try:
        pinned = ipaddress.ip_address(os.environ.get("C09_TEST_SERVER_ADDRESS", ""))
    except ValueError:
        return False
    return observed == pinned and any(observed in ipaddress.ip_network(network) for network in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    ))


@pytest.fixture(scope="module")
def disposable_database():
    raw = os.environ.get("C09_TEST_DATABASE_URL")
    if not raw:
        pytest.fail("C09_TEST_DATABASE_URL is required; DATABASE_URL is never used")
    url = make_url(raw)
    if url.get_backend_name() != "postgresql" or url.host not in {
        "127.0.0.1", "localhost", "::1",
    } or not re.fullmatch(r"ocean_c09_[a-z0-9_]+", url.database or ""):
        pytest.fail("C09 URL must identify a dedicated ocean_c09_* loopback PostgreSQL database")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            identity = connection.execute(text(
                "SELECT current_database(), host(inet_server_addr()), inet_server_port(), "
                "current_setting('server_version')"
            )).one()
            assert identity[0] == url.database
            assert allowed_disposable_server_address(identity[1]), "Observed server is not the verified disposable server"
        print(f"C09 disposable PostgreSQL identity: database={identity[0]} address={identity[1]} port={identity[2]} version={identity[3]}")
        yield engine, url
    finally:
        engine.dispose()


@pytest.fixture
def isolated(disposable_database, tmp_path):
    observer, url = disposable_database
    schema_name = f"c09_{uuid.uuid4().hex}"
    with observer.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "options": f"-csearch_path={schema_name} -clock_timeout=8000 -cstatement_timeout=12000",
    })
    metadata = MetaData()
    heads = Table("capture_heads", metadata, Column("name", String, primary_key=True), Column("generation", String, nullable=False))
    rows = Table("canonical_rows", metadata, Column("family", String, primary_key=True), Column("role", String, primary_key=True), Column("payload", String, nullable=False))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(insert(heads), [
            {"name": name, "generation": "g1"} for name in registry().required_heads
        ])
        connection.execute(insert(rows), [
            {"family": family, "role": role, "payload": f"{family}:{role}:g1"}
            for family in FAMILIES for role in (
                ("canonical_rows", "classifications") if family == "edna_metabarcoding" else ("rows",)
            )
        ])
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve() / "isolated-v1", access_gate=lambda manifest: True)

    def exports(family, connection, captured_heads, deadline):
        records = connection.execute(select(rows).where(rows.c.family == family).order_by(rows.c.role)).mappings()
        objects, contents = [], {}
        for record in records:
            identity = f"{family}:{record['role']}"
            payload = record["payload"].encode()
            digest = hashlib.sha256(payload).hexdigest()
            objects.append(SnapshotObject(
                object_id=identity, dataset_id=f"{family}:dataset", source_id=family,
                source_family=family, role=record["role"], sha256=digest, size_bytes=len(payload),
                schema_version="rows-v1", operation_id=identity, operation_version="export-v1",
                provenance=Provenance(source_generation=captured_heads.source_generation(family), content_sha256=digest),
            ))
            contents[identity] = payload
        return CapturedSource(tuple(objects), contents)

    registrations = SourceExportRegistry(tuple(
        replace(item, exporter=lambda connection, captured_heads, deadline, family=item.source_family:
                exports(family, connection, captured_heads, deadline))
        for item in registry().requirements
    ))
    bundle = {
        "engine": engine, "observer": observer, "heads": heads, "rows": rows,
        "store": store, "registry": registrations, "coordinator": TableHeadCoordinator(heads),
    }
    try:
        yield bundle
    finally:
        engine.dispose()
        with observer.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
            remaining = connection.scalar(text(
                "SELECT count(*) FROM pg_namespace WHERE nspname=:schema"
            ), {"schema": schema_name})
            assert remaining == 0
        print(f"C09 disposable schema cleanup: {schema_name} remaining=0")


def capture(database, **changes):
    options = {key: database[key] for key in ("engine", "registry", "coordinator", "store")}
    options.update(scope=scope(), expected_latest_generation=database["store"].latest()[1])
    options.update(changes)
    return capture_snapshot(**options)


def mutate(database, kind, key="publication"):
    with database["engine"].begin() as connection:
        if kind == "update":
            connection.execute(update(database["heads"]).where(database["heads"].c.name == key).values(generation="g2"))
        elif kind == "insert":
            connection.execute(insert(database["heads"]).values(name="new-registry-head", generation="g2"))
        elif kind == "delete":
            connection.execute(delete(database["heads"]).where(database["heads"].c.name == key))
        elif kind == "all":
            connection.execute(update(database["heads"]).values(generation="g2"))
            connection.execute(update(database["rows"]).values(payload="new-canonical-generation-g2"))


def with_export_hook(database, hook):
    registrations = database["registry"].requirements
    first = registrations[0]
    def exported(connection, captured_heads, deadline):
        result = first.exporter(connection, captured_heads, deadline)
        hook(connection, captured_heads, result)
        return result
    return SourceExportRegistry((replace(first, exporter=exported), *registrations[1:]))


def test_read_only_repeatable_read_exact_bytes_and_reopen_after_new_generation(isolated):
    observations = []
    def observe(connection, captured_heads, result):
        observations.append(connection.execute(text(
            "SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only')"
        )).one())
    first = capture(isolated, registry=with_export_hook(isolated, observe))
    assert first.pointer_generation == 1
    assert observations == [("repeatable read", "on")]
    old_manifest, old_bytes = isolated["store"].read(first.snapshot_id)
    assert len(old_bytes) == 5
    assert all(data.endswith(b":g1") for data in old_bytes.values())
    assert {source.classification_generation for source in old_manifest.source_captures} == {"g1"}
    mutate(isolated, "all")
    second = capture(isolated)
    assert second.pointer_generation == 2
    assert second.snapshot_id != first.snapshot_id
    assert isolated["store"].read(first.snapshot_id)[1] == old_bytes
    assert all(data == b"new-canonical-generation-g2" for data in isolated["store"].read(second.snapshot_id)[1].values())


@pytest.mark.parametrize("head", ["publication", "classification", "relationship", "operation", "source:ctd"])
def test_each_relevant_generation_rollover_aborts_before_seal_or_latest(isolated, monkeypatch, head):
    seals = []
    monkeypatch.setattr(isolated["store"], "seal", lambda *args: seals.append(args))
    def rollover(connection, captured_heads, result):
        mutate(isolated, "update", head)
        assert isolated["coordinator"].read(connection, isolated["registry"].required_heads).values[head] == "g1"
    with pytest.raises(CaptureRollover):
        capture(isolated, registry=with_export_hook(isolated, rollover), budget=CaptureBudget(max_attempts=1))
    assert seals == []
    assert isolated["store"].latest() == (None, 0)


@pytest.mark.parametrize("kind", ["insert", "delete"])
def test_head_membership_rollover_is_rejected(isolated, kind):
    with pytest.raises((CaptureRollover, CaptureError)):
        capture(isolated, registry=with_export_hook(isolated, lambda *args: mutate(isolated, kind)),
                budget=CaptureBudget(max_attempts=1))
    assert isolated["store"].latest() == (None, 0)


def test_repeatable_data_does_not_mix_and_bounded_retry_captures_new_generation(isolated):
    old_observations = []
    calls = 0
    def rollover_once(connection, captured_heads, result):
        nonlocal calls
        calls += 1
        if calls == 1:
            mutate(isolated, "all")
            old_observations.extend(connection.scalars(select(isolated["rows"].c.payload)))
    result = capture(isolated, registry=with_export_hook(isolated, rollover_once))
    assert result.attempts == 2
    assert old_observations and all(value.endswith(":g1") for value in old_observations)
    manifest, contents = isolated["store"].read(result.snapshot_id)
    assert all(value == "g2" for value in result.heads.values.values())
    assert all(payload == b"new-canonical-generation-g2" for payload in contents.values())
    assert {source.source_generation for source in manifest.source_captures} == {"g2"}


def test_exporter_database_write_is_rejected_and_never_published(isolated):
    def write(connection, *args):
        connection.execute(update(isolated["rows"]).values(payload="forbidden"))
    with pytest.raises(DBAPIError) as failure:
        capture(isolated, registry=with_export_hook(isolated, write))
    assert failure.value.orig.pgcode == "25006"
    assert isolated["store"].latest() == (None, 0)


def test_scoped_capture_is_rejected_before_any_export_or_seal(isolated, monkeypatch):
    attempts = []
    selected = scope()
    selected.sources.edna_metabarcoding.filters.taxon = "synthetic-taxon"
    monkeypatch.setattr(isolated["store"], "seal", lambda *args: attempts.append("seal"))
    with pytest.raises(CaptureError, match="scoped row filtering"):
        capture(isolated, scope=selected, registry=with_export_hook(isolated, lambda *args: attempts.append("export")))
    assert attempts == []
    assert isolated["store"].latest() == (None, 0)


def test_sql_capture_timeout_is_bounded_and_connection_recovers(isolated):
    def slow(connection, *args):
        connection.execute(text("SELECT pg_sleep(1)"))
    started = time.monotonic()
    with pytest.raises(DBAPIError) as failure:
        capture(isolated, registry=with_export_hook(isolated, slow), budget=CaptureBudget(max_seconds=0.15))
    assert failure.value.orig.pgcode == "57014"
    assert time.monotonic() - started < 3
    assert isolated["store"].latest() == (None, 0)
    with isolated["engine"].connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1


def wait_for_lock(observer, pid):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        with observer.connect() as connection:
            waiting = connection.scalar(text(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"
            ), {"pid": pid})
        if waiting == "Lock":
            return
        time.sleep(0.01)
    raise AssertionError("Competing source writer never reached its PostgreSQL lock")


@pytest.mark.parametrize("kind", ["insert", "update", "delete"])
def test_final_lock_blocks_head_insert_update_delete_through_local_publication(isolated, monkeypatch, kind):
    ready, done = threading.Event(), threading.Event()
    failures, pids = [], []
    def writer():
        try:
            with isolated["engine"].begin() as connection:
                pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                if kind == "insert":
                    connection.execute(insert(isolated["heads"]).values(name="new-registry-head", generation="g2"))
                elif kind == "update":
                    connection.execute(update(isolated["heads"]).values(generation="g2"))
                else:
                    connection.execute(delete(isolated["heads"]).where(isolated["heads"].c.name == "relationship"))
        except Exception as exc:
            failures.append(exc)
        finally:
            done.set()
    worker = threading.Thread(target=writer, name=f"c09-{kind}", daemon=True)
    original = isolated["store"].seal
    def seal(manifest, contents):
        worker.start()
        assert ready.wait(3)
        wait_for_lock(isolated["observer"], pids[0])
        assert not done.is_set()
        return original(manifest, contents)
    monkeypatch.setattr(isolated["store"], "seal", seal)
    try:
        result = capture(isolated)
    finally:
        worker.join(5)
    assert done.is_set() and not failures
    assert isolated["store"].latest() == (result.snapshot_id, 1)
    assert all(value == "g1" for value in result.heads.values.values())


@pytest.mark.parametrize("failure_stage", ["export", "seal"])
def test_failed_export_and_seal_do_not_replace_existing_latest(isolated, monkeypatch, failure_stage):
    first = capture(isolated)
    mutate(isolated, "all")
    def fail(*args):
        raise OSError("synthetic local seal failure")
    if failure_stage == "seal":
        monkeypatch.setattr(isolated["store"], "seal", fail)
        registrations = isolated["registry"]
    else:
        registrations = with_export_hook(isolated, fail)
    with pytest.raises(OSError, match="seal failure"):
        capture(isolated, registry=registrations)
    assert isolated["store"].latest() == (first.snapshot_id, 1)


def test_competing_pointer_update_is_not_silently_adopted(isolated):
    first = capture(isolated)
    with pytest.raises(SnapshotConflict):
        capture(isolated, expected_latest_generation=0)
    assert isolated["store"].latest() == (first.snapshot_id, 1)


def test_final_database_commit_failure_reports_published_snapshot_for_reconciliation(isolated, monkeypatch):
    from sqlalchemy import event
    def fail_commit(connection):
        if connection.get_isolation_level() == "READ COMMITTED":
            raise OSError("synthetic final database release failure")
    event.listen(isolated["engine"], "commit", fail_commit)
    try:
        with pytest.raises(CapturePublicationUncertain) as failure:
            capture(isolated)
    finally:
        event.remove(isolated["engine"], "commit", fail_commit)
    assert isolated["store"].latest() == (failure.value.snapshot_id, failure.value.pointer_generation)
    assert isolated["store"].read(failure.value.snapshot_id)[1]


@pytest.mark.parametrize("committed", [True, False])
def test_unconfirmed_local_promotion_is_reported_as_uncertain_not_rolled_back(isolated, monkeypatch, committed):
    original = isolated["store"].promote
    def uncertain(identity, **options):
        generation = original(identity, **options) if committed else 1
        raise SnapshotCommitUncertain(
            action="promote", details={"snapshot_id": identity}, proposed_revision=2,
            proposed_latest_generation=generation,
        )
    monkeypatch.setattr(isolated["store"], "promote", uncertain)
    with pytest.raises(CapturePublicationUncertain) as failure:
        capture(isolated)
    assert failure.value.pointer_generation == 1
    if committed:
        assert isolated["store"].latest() == (failure.value.snapshot_id, failure.value.pointer_generation)
    else:
        assert isolated["store"].latest() == (None, 0)
