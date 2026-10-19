"""C20 actual C17/C14/controller durability with local synthetic stores only."""
import json
import uuid

import pytest
from sqlalchemy import create_engine, event, func, select

from db.app_models import (
    AppBase, AppUser, ResearchInvestigation, ResearchRun, ResearchRunAttempt,
    ResearchRunEvent, ResearchRunInputHistory, ResearchRunManifest,
    ResearchRunOutbox, ResearchRunPayload, ResearchRunStep,
)
from orchestration.research_controller import ControllerAdmissionError
from orchestration.research_runs import ResearchRunError, ResearchRunService, RunJournal
from schema.research_controller import canonical_hash
from schema.research_runs import RUN_REQUEST_MODELS, validate_run_response
from tests.research_run_support import make_run_fixture


@pytest.fixture(scope="module")
def retained(tmp_path_factory):
    directory = tmp_path_factory.mktemp("c20-local")
    engine = create_engine("sqlite+pysqlite:///" + str(directory / "v1.sqlite"))

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    AppBase.metadata.create_all(engine)
    value = make_run_fixture(engine, directory)
    yield value
    engine.dispose()


@pytest.fixture
def actual(retained, monkeypatch):
    for name in ("ENABLE_V1_CATALOGUE", "ENABLE_V1_INVESTIGATIONS", "ENABLE_V1_RESEARCH_CONTROLLER"):
        monkeypatch.setenv(name, "true")
    retained.state["runtime"] = None
    retained.queue.accept_then_fail = False
    retained.queue.deliveries.clear()
    for excluded in retained.retained.policy.values():
        excluded.clear()
    return retained


def checked(actual, name, request, user=None):
    result = actual.service.invoke(name, request, user or actual.user)
    return validate_run_response(name, result, RUN_REQUEST_MODELS[name].model_validate(request))


def count(actual, model):
    with actual.retained.factory() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_submit_atomic_exact_idempotent_and_owner_scoped(actual):
    request = actual.request()
    models = (ResearchRun, ResearchRunInputHistory, ResearchRunEvent, ResearchRunOutbox)
    before = [count(actual, model) for model in models]
    first = checked(actual, "submit", request)
    assert first == checked(actual, "submit", request)
    assert [count(actual, model) for model in models] == [value + 1 for value in before]
    run = first["run"]
    assert run["result"] is None and run["synthetic"] is False and run["latest_event_cursor"] == 1
    with pytest.raises(ResearchRunError, match="conflict"):
        actual.service.invoke("submit", {**request, "question": "Count datasets"}, actual.user)
    for actor in (actual.retained.other, actual.retained.admin):
        with pytest.raises(ResearchRunError) as failure:
            actual.service.invoke("status", actual.address(run), actor)
        assert failure.value.status_code == 404


def test_failed_transaction_rolls_back_all_run_rows(actual, monkeypatch):
    request = actual.request()
    before = count(actual, ResearchRun)

    def broken(*_):
        raise RuntimeError("Synthetic transaction failure")

    monkeypatch.setattr(actual.service, "_outbox", broken)
    with pytest.raises(RuntimeError):
        actual.service.invoke("submit", request, actual.user)
    assert count(actual, ResearchRun) == before


def test_actual_controller_retains_steps_and_terminal_redelivery(actual):
    run = actual.submit()
    calls = actual.state["factory_calls"]
    result = actual.service.execute_delivery(**actual.delivery(run))
    assert result["run"]["status"] == "completed" and result["run"]["result"] is None
    with actual.retained.factory() as session:
        stored = session.get(ResearchRun, uuid.UUID(run["id"]))
        assert stored.tool_actions == 1 and stored.model_calls == 0
        assert json.loads(stored.controller_result_json)["observations"]
        assert session.scalars(select(ResearchRunStep).where(ResearchRunStep.run_id == stored.id)).one().state == "committed"
        assert session.scalars(select(ResearchRunPayload).where(ResearchRunPayload.run_id == stored.id)).all()
    events = checked(actual, "events", {**actual.address(run), "after_cursor": 0})
    assert [item["kind"] for item in events["events"]] == ["accepted", "started", "progress", "completed"]
    assert actual.service.execute_delivery(**actual.delivery(run)) == result
    assert actual.state["factory_calls"] == calls + 1


def test_queue_ack_loss_reuses_delivery_identity(actual):
    run = actual.submit()
    actual.queue.accept_then_fail = True
    with pytest.raises(RuntimeError):
        actual.service.dispatch_outbox()
    actual.queue.accept_then_fail = False
    actual.service.dispatch_outbox()
    duplicates = [item for item in actual.queue.deliveries if item["run_id"] == run["id"]]
    # Earlier tests may leave pending outbox rows. Retry the target directly if
    # the simulated first failure concerned an earlier retained run.
    if len(duplicates) == 1:
        actual.queue.enqueue(**duplicates[0])
        duplicates = [item for item in actual.queue.deliveries if item["run_id"] == run["id"]]
    assert len(duplicates) == 2 and duplicates[0] == duplicates[1]
    result = actual.service.execute_delivery(**duplicates[0])
    assert actual.service.execute_delivery(**duplicates[1]) == result


@pytest.mark.parametrize("committed", [False, True])
def test_crash_boundary_charges_uncertain_or_replays_commit(actual, monkeypatch, committed):
    run = actual.submit()
    delivery = actual.delivery(run)
    original = RunJournal.commit_step
    failed, outbound = [], []
    catalogue = actual.retained.service.catalogue
    execute = catalogue.execute

    def observed(*args, **kwargs):
        if args[0] == "catalogue.query":
            outbound.append(args[0])
        return execute(*args, **kwargs)

    def crash(self, *args):
        if not failed:
            failed.append(True)
            if committed:
                original(self, *args)
            raise RuntimeError("Synthetic worker interruption")
        return original(self, *args)

    monkeypatch.setattr(catalogue, "execute", observed)
    monkeypatch.setattr(RunJournal, "commit_step", crash)
    with pytest.raises(ControllerAdmissionError):
        actual.service.execute_delivery(**delivery)
    actual.clock.advance(31)
    result = actual.service.execute_delivery(**delivery)
    assert result["run"]["status"] == "completed"
    with actual.retained.factory() as session:
        stored = session.get(ResearchRun, uuid.UUID(run["id"]))
        assert stored.active_elapsed_ms >= 31000
        assert stored.tool_actions == (1 if committed else 2)
        assert len(session.scalars(select(ResearchRunAttempt).where(ResearchRunAttempt.run_id == stored.id)).all()) == (1 if committed else 2)
    assert len(outbound) == (1 if committed else 2)


def test_live_claim_and_expired_epoch_fencing(actual):
    run = actual.submit()
    delivery = actual.delivery(run)
    first = actual.service.claim(**delivery)
    assert actual.service.claim(**delivery) is None
    actual.clock.advance(6)
    second = actual.service.claim(**delivery)
    assert second.epoch == first.epoch + 1
    with pytest.raises(ResearchRunError, match="lease_lost"):
        RunJournal(actual.service, first).bind({})


def test_clarification_replacement_keeps_original_and_paused_budget(actual):
    run = actual.submit("What is the meaning of this?")
    paused = actual.service.execute_delivery(**actual.delivery(run))["run"]
    assert paused["status"] == "awaiting_clarification" and paused["clarification_id"]
    before = paused["active_elapsed_ms"]
    actual.clock.advance(36000)
    request = {**actual.address(run), "clarification_id": paused["clarification_id"],
               "answer": "Count all datasets", "idempotency_key": str(uuid.uuid4())}
    queued = checked(actual, "clarify", request)["run"]
    assert queued["question"] == "What is the meaning of this?" and queued["active_elapsed_ms"] == before
    assert checked(actual, "clarify", request)["run"] == queued
    with pytest.raises(ResearchRunError, match="conflict"):
        actual.service.invoke("clarify", {**request, "idempotency_key": str(uuid.uuid4())}, actual.user)
    assert actual.service.execute_delivery(**actual.delivery(run))["run"]["status"] == "completed"
    with actual.retained.factory() as session:
        stored = session.get(ResearchRun, uuid.UUID(run["id"]))
        inputs = session.scalars(select(ResearchRunInputHistory).where(ResearchRunInputHistory.run_id == stored.id).order_by(ResearchRunInputHistory.sequence)).all()
        assert [item.effective_question for item in inputs] == ["What is the meaning of this?", "Count all datasets"]
        assert stored.tool_actions == 1 and stored.active_elapsed_ms < 180000
        assert len(session.scalars(select(ResearchRunManifest).where(ResearchRunManifest.run_id == stored.id)).all()) == 2


def test_cancel_and_complete_are_irreversible_and_continue_is_linked(actual):
    run = actual.submit()
    lease = actual.service.claim(**actual.delivery(run))
    cancelled = checked(actual, "cancel", {**actual.address(run), "idempotency_key": str(uuid.uuid4())})["run"]
    assert cancelled["status"] == "cancelled"
    with pytest.raises(ResearchRunError):
        RunJournal(actual.service, lease).bind({})
    child = checked(actual, "continue", {**actual.address(run), "idempotency_key": str(uuid.uuid4())})["run"]
    assert child["id"] != run["id"] and child["continuation_of"] == run["id"]
    assert child["context"] == run["context"] and child["active_elapsed_ms"] == 0
    complete = actual.service.execute_delivery(**actual.delivery(child))["run"]
    assert checked(actual, "cancel", {**actual.address(child), "idempotency_key": str(uuid.uuid4())})["run"] == complete


def test_history_events_and_policy_epoch_cursor(actual):
    request = actual.request()
    runs = [checked(actual, "submit", {**request, "idempotency_key": str(uuid.uuid4())})["run"] for _ in range(3)]
    address = {key: request[key] for key in ("investigation_id", "conversation_id")}
    page = checked(actual, "list", {**address, "limit": 1})
    tail = checked(actual, "list", {**address, "limit": 500, "cursor": page["next_cursor"]})
    assert len(page["items"]) == 1 and len(tail["items"]) == 2
    actual.retained.policy[actual.retained.snapshots[0]].add(actual.retained.source_dataset_ids["ctd"])
    with pytest.raises(ResearchRunError, match="invalid_request"):
        actual.service.invoke("list", {**address, "cursor": page["next_cursor"]}, actual.user)
    actual.retained.policy[actual.retained.snapshots[0]].clear()
    actual.service.execute_delivery(**actual.delivery(runs[0]))
    first = checked(actual, "events", {**actual.address(runs[0]), "after_cursor": 0, "limit": 2})
    last = checked(actual, "events", {**actual.address(runs[0]), "after_cursor": 2, "limit": 2})
    assert first["has_more"] and not last["has_more"] and last["latest_event_cursor"] == 4


def test_archived_history_and_cancel_remain_available(actual):
    run = actual.submit()
    with actual.retained.factory.begin() as session:
        session.get(ResearchInvestigation, uuid.UUID(run["context"]["binding"]["investigation_id"])).status = "archived"
    assert checked(actual, "status", actual.address(run))["run"]["id"] == run["id"]
    assert checked(actual, "cancel", {**actual.address(run), "idempotency_key": str(uuid.uuid4())})["run"]["status"] == "cancelled"
    with pytest.raises(ResearchRunError):
        actual.service.invoke("continue", {**actual.address(run), "idempotency_key": str(uuid.uuid4())}, actual.user)


def test_unconfigured_dispatch_is_unavailable_history_survives_disable(actual):
    request = actual.request()
    unconfigured = ResearchRunService(session_factory=actual.retained.factory, site_id=actual.service.site_id,
        investigations=actual.retained.service, enabled=lambda: True, dispatch_enabled=lambda: True)
    assert not unconfigured.dispatch_available
    with pytest.raises(ResearchRunError):
        unconfigured.invoke("submit", request, actual.user)
    run = actual.service.invoke("submit", request, actual.user)["run"]
    old = actual.service.dispatch_enabled
    actual.service.dispatch_enabled = lambda: False
    try:
        assert checked(actual, "status", actual.address(run))["run"] == run
        with pytest.raises(ResearchRunError):
            actual.service.execute_delivery(**actual.delivery(run))
        assert checked(actual, "cancel", {**actual.address(run), "idempotency_key": str(uuid.uuid4())})["run"]["status"] == "cancelled"
    finally:
        actual.service.dispatch_enabled = old


def test_reserved_repair_crash_cannot_charge_second_repair(actual):
    run = actual.submit()
    first = actual.service.claim(**actual.delivery(run))
    journal = RunJournal(actual.service, first)
    journal.bind({"fixture": "repair"})
    request = {"repair": 1}
    budget = {"active_elapsed_seconds": 0, "tool_actions": 0, "model_calls": 0,
              "malformed_repairs": 1, "cancellation_requested": False}
    journal.prepare_step("turn:1:repair:1", "repair", canonical_hash(request), request, budget, {})
    actual.clock.advance(6)
    recovered = RunJournal(actual.service, actual.service.claim(**actual.delivery(run)))
    assert recovered.bind({"fixture": "repair"})["reserved_repair_steps"] == ["turn:1:repair:1"]
    token = recovered.prepare_step("turn:1:repair:1", "repair", canonical_hash(request), request, budget, {})
    recovered.commit_step(token, {"repair": True}, budget, {})
    with actual.retained.factory() as session:
        assert session.get(ResearchRun, uuid.UUID(run["id"])).malformed_repairs == 1


def test_retained_bytes_are_immutable_and_owner_revocation_is_fresh(actual):
    run = actual.submit()
    actual.service.execute_delivery(**actual.delivery(run))
    for model, field in ((ResearchRunPayload, "payload_json"), (ResearchRunInputHistory, "request_json")):
        with pytest.raises(ValueError):
            with actual.retained.factory.begin() as session:
                item = session.scalars(select(model).where(model.run_id == uuid.UUID(run["id"]))).first()
                setattr(item, field, "{}")
    with actual.retained.factory.begin() as session:
        session.get(AppUser, actual.user.id).status = "suspended"
    try:
        with pytest.raises(ResearchRunError, match="access_denied"):
            actual.service.invoke("status", actual.address(run), actual.user)
        with pytest.raises(ResearchRunError, match="access_denied"):
            actual.service.execute_delivery(**actual.delivery(run))
    finally:
        with actual.retained.factory.begin() as session:
            session.get(AppUser, actual.user.id).status = "active"


@pytest.mark.parametrize('column', ['version', 'input_version', 'event_cursor', 'active_elapsed_ms', 'tool_actions', 'model_calls', 'malformed_repairs', 'lease_epoch'])
def test_nonterminal_counters_cannot_roll_back(actual, column):
    run = actual.submit()
    with actual.retained.factory.begin() as session:
        item = session.get(ResearchRun, uuid.UUID(run['id']))
        setattr(item, column, max(getattr(item, column), 1))
    with pytest.raises(ValueError, match='monotonic'):
        with actual.retained.factory.begin() as session:
            item = session.get(ResearchRun, uuid.UUID(run['id']))
            setattr(item, column, getattr(item, column) - 1)


@pytest.mark.parametrize('column,value', [('status', 'running'), ('controller_result_json', '{}'), ('checkpoint_json', '{}')])
def test_terminal_run_cannot_be_rewritten(actual, column, value):
    run = actual.submit()
    actual.service.execute_delivery(**actual.delivery(run))
    with pytest.raises(ValueError, match='Terminal'):
        with actual.retained.factory.begin() as session:
            item = session.get(ResearchRun, uuid.UUID(run['id']))
            setattr(item, column, value)


def test_continuation_reuses_only_verified_parent_inventory_prefix(actual, monkeypatch):
    run = actual.submit()
    original = RunJournal.commit_step
    failed = []

    def crash(self, *args):
        original(self, *args)
        if not failed:
            failed.append(True)
            raise RuntimeError('Synthetic lost committed acknowledgement')

    monkeypatch.setattr(RunJournal, 'commit_step', crash)
    with pytest.raises(ControllerAdmissionError):
        actual.service.execute_delivery(**actual.delivery(run))
    monkeypatch.setattr(RunJournal, 'commit_step', original)
    parent = checked(actual, 'cancel', {**actual.address(run), 'idempotency_key': str(uuid.uuid4())})['run']
    child = checked(actual, 'continue', {**actual.address(run), 'idempotency_key': str(uuid.uuid4())})['run']
    outbound = []
    catalogue = actual.retained.service.catalogue
    execute = catalogue.execute

    def observed(*args, **kwargs):
        if args[0] == 'catalogue.query':
            outbound.append(args[0])
        return execute(*args, **kwargs)

    monkeypatch.setattr(catalogue, 'execute', observed)
    result = actual.service.execute_delivery(**actual.delivery(child))['run']
    assert result['status'] == 'completed' and not outbound
    assert checked(actual, 'status', actual.address(parent))['run'] == parent
    with actual.retained.factory() as session:
        stored = session.get(ResearchRun, uuid.UUID(child['id']))
        assert stored.tool_actions == 0
        assert len(json.loads(stored.controller_result_json)['observations']) == 1


def test_source_policy_change_after_controller_return_blocks_publication(actual, monkeypatch):
    run = actual.submit()
    original = actual.service.controller_factory

    def factory(identity_provider):
        controller = original(identity_provider)
        execute = controller.execute

        def changed(*args, **kwargs):
            result = execute(*args, **kwargs)
            actual.retained.policy[actual.retained.snapshots[0]].add(actual.retained.source_dataset_ids['ctd'])
            return result

        controller.execute = changed
        return controller

    monkeypatch.setattr(actual.service, 'controller_factory', factory)
    with pytest.raises(ResearchRunError, match='access_denied'):
        actual.service.execute_delivery(**actual.delivery(run))
    with actual.retained.factory() as session:
        item = session.get(ResearchRun, uuid.UUID(run['id']))
        assert item.status != 'completed' and item.controller_result_json is None
        assert not session.scalar(select(ResearchRunEvent.cursor).where(ResearchRunEvent.run_id == item.id, ResearchRunEvent.kind == 'completed'))
    with pytest.raises(ResearchRunError, match='access_denied'):
        actual.service.invoke('status', actual.address(run), actual.user)


def test_backward_database_clock_is_sticky_exhaustion(actual):
    run = actual.submit()
    actual.service.claim(**actual.delivery(run))
    actual.clock.advance(-1)
    try:
        stopped = actual.service.execute_delivery(**actual.delivery(run))['run']
        assert stopped['status'] == 'partial' and stopped['active_elapsed_ms'] == 180000
        actual.clock.advance(2)
        assert actual.service.execute_delivery(**actual.delivery(run))['run'] == stopped
        with actual.retained.factory() as session:
            assert session.get(ResearchRun, uuid.UUID(run['id'])).reason_code == 'invalid_clock'
    finally:
        actual.clock.advance(1)


def test_policy_revoked_at_terminal_event_flush_rolls_back_publication(actual, monkeypatch):
    run = actual.submit()
    original = actual.service._event

    def changed(session, record, kind):
        original(session, record, kind)
        if kind == 'completed':
            actual.retained.policy[actual.retained.snapshots[0]].add(actual.retained.source_dataset_ids['ctd'])

    monkeypatch.setattr(actual.service, '_event', changed)
    with pytest.raises(ResearchRunError, match='access_denied'):
        actual.service.execute_delivery(**actual.delivery(run))
    with actual.retained.factory() as session:
        item = session.get(ResearchRun, uuid.UUID(run['id']))
        assert item.status == 'running' and item.controller_result_json is None
        assert not session.scalar(select(ResearchRunEvent.cursor).where(ResearchRunEvent.run_id == item.id, ResearchRunEvent.kind == 'completed'))


def test_long_uncertain_interval_clamps_to_honest_exhausted_high_water(actual):
    run = actual.submit()
    actual.service.claim(**actual.delivery(run))
    actual.clock.advance(86400 * 100)
    lease = actual.service.claim(**actual.delivery(run))
    assert lease is not None
    with actual.retained.factory() as session:
        assert session.get(ResearchRun, uuid.UUID(run['id'])).active_elapsed_ms == 180000


def test_run_discovery_bounds_page_bytes_and_keeps_a_valid_cursor(actual, monkeypatch):
    import orchestration.research_runs as module

    request = actual.request()
    rows = [checked(actual, 'submit', {**request, 'idempotency_key': str(uuid.uuid4())})['run'] for _ in range(3)]
    encoded = len(json.dumps(rows[0], ensure_ascii=False).encode('utf-8'))
    monkeypatch.setattr(module, 'MAX_LIST_PAGE_BYTES', int(encoded * 1.5))
    address = {key: request[key] for key in ('investigation_id', 'conversation_id')}
    first = checked(actual, 'list', {**address, 'limit': 500})
    assert len(first['items']) == 1 and first['next_cursor']
    second = checked(actual, 'list', {**address, 'limit': 500, 'cursor': first['next_cursor']})
    assert len(second['items']) == 1 and second['items'][0]['id'] != first['items'][0]['id']
