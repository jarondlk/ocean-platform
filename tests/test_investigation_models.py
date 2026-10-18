"""Fast AppBase fixture checks; actual migration/trigger gates use disposable PG."""

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from db.app_models import (
    AppBase,
    AppUser,
    ResearchContextOperation,
    ResearchContextRevision,
    ResearchConversation,
    ResearchInvestigation,
)


@pytest.fixture
def storage():
    engine = create_engine("sqlite+pysqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    AppBase.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    owners = [uuid.uuid4(), uuid.uuid4()]
    investigations = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    revisions = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    with factory.begin() as session:
        for index, owner in enumerate(owners):
            session.add(AppUser(id=owner, auth_provider="synthetic", auth_subject=str(index), email=f"fixture-{index}@invalid.test"))
        session.flush()
        for index, investigation in enumerate(investigations):
            session.add(ResearchInvestigation(id=investigation, user_id=owners[index == 2], name=f"Fixture {index}"))
        session.flush()
        for index, revision in enumerate(revisions):
            session.add(_revision(investigations[index], owners[index == 2], id=revision))
        session.flush()
        for investigation, revision in zip(investigations, revisions, strict=True):
            record = session.get(ResearchInvestigation, investigation)
            record.head_revision_id = revision
            record.status = "active"
        conversation = ResearchConversation(investigation_id=investigations[0], name="Synthetic conversation")
        operation = _operation(investigations[0], owners[0], expected_head_id=revisions[0])
        session.add_all([conversation, operation])
    yield factory, owners, investigations, revisions, conversation.id, operation.id
    engine.dispose()


def _revision(investigation, owner, **changes):
    return ResearchContextRevision(**{
        "investigation_id": investigation, "sequence": 1,
        "snapshot_id": "a" * 64, "payload_json": "{}", "payload_sha256": "b" * 64,
        "created_by_user_id": owner, **changes,
    })


def _operation(investigation, owner, **changes):
    return ResearchContextOperation(**{
        "user_id": owner, "investigation_id": investigation,
        "idempotency_key": str(uuid.uuid4()), "kind": "attach",
        "candidate_revision_id": uuid.uuid4(), "request_json": "{}",
        "request_sha256": "c" * 64, "candidate_json": "{}", "references_json": "[]",
        **changes,
    })


def test_context_tables_use_only_application_metadata_and_restrict_deletes():
    from db.models import Base

    for model in (ResearchInvestigation, ResearchConversation, ResearchContextRevision, ResearchContextOperation):
        assert model.metadata is AppBase.metadata
        assert model.__tablename__ not in Base.metadata.tables
        for foreign_key in model.__table__.foreign_keys:
            assert foreign_key.column.table.metadata is AppBase.metadata
            assert foreign_key.ondelete == "RESTRICT"


def test_duplicate_sequence_fails_without_overwriting_historical_revision(storage):
    factory, owners, investigations, revisions, _, _ = storage
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(_revision(investigations[0], owners[0], payload_json='{"new":true}'))
    with factory() as session:
        assert session.get(ResearchContextRevision, revisions[0]).payload_json == "{}"
        assert len(session.scalars(select(ResearchContextRevision)).all()) == 3


@pytest.mark.parametrize("field", ["head_revision_id", "predecessor_revision_id", "expected_head_id"])
def test_cross_investigation_revision_binding_fails(storage, field):
    factory, owners, investigations, revisions, _, _ = storage
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            if field == "head_revision_id":
                session.get(ResearchInvestigation, investigations[0]).head_revision_id = revisions[1]
            elif field == "predecessor_revision_id":
                session.add(_revision(investigations[0], owners[0], sequence=2, predecessor_revision_id=revisions[1]))
            else:
                session.add(_operation(investigations[0], owners[0], expected_head_id=revisions[1]))


@pytest.mark.parametrize("kind", ["revision", "operation", "branch"])
def test_cross_owner_records_rejected_by_foreign_keys(storage, kind):
    factory, owners, investigations, revisions, _, _ = storage
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            if kind == "revision":
                session.add(_revision(investigations[0], owners[1], sequence=2))
            elif kind == "operation":
                session.add(_operation(investigations[0], owners[1]))
            else:
                session.add(ResearchInvestigation(user_id=owners[1], name="Forbidden branch", predecessor_investigation_id=investigations[0], predecessor_revision_id=revisions[0]))


@pytest.mark.parametrize("wrong_pair", ["missing_revision", "wrong_investigation"])
def test_refresh_predecessor_pair_is_complete_and_bound(storage, wrong_pair):
    factory, owners, investigations, revisions, _, _ = storage
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(ResearchInvestigation(
                user_id=owners[0], name="Invalid branch",
                predecessor_investigation_id=investigations[0],
                predecessor_revision_id=None if wrong_pair == "missing_revision" else revisions[1],
            ))


def test_refresh_branch_preserves_original_head_and_payload(storage):
    factory, owners, investigations, revisions, _, _ = storage
    with factory.begin() as session:
        branch = ResearchInvestigation(user_id=owners[0], name="New snapshot branch", predecessor_investigation_id=investigations[0], predecessor_revision_id=revisions[0])
        session.add(branch)
        session.flush()
        newer = _revision(branch.id, owners[0], snapshot_id="d" * 64)
        session.add(newer)
        session.flush()
        branch.head_revision_id = newer.id
        branch.status = "active"
    with factory() as session:
        assert session.get(ResearchInvestigation, investigations[0]).head_revision_id == revisions[0]
        assert session.get(ResearchContextRevision, revisions[0]).snapshot_id == "a" * 64
        assert session.get(ResearchInvestigation, branch.id).predecessor_revision_id == revisions[0]


@pytest.mark.parametrize("action", ["update", "delete"])
def test_revision_is_append_only_for_orm_fixtures(storage, action):
    factory, _, _, revisions, _, _ = storage
    with pytest.raises(ValueError, match="immutable"):
        with factory.begin() as session:
            revision = session.get(ResearchContextRevision, revisions[0])
            if action == "update":
                revision.payload_json = '{"changed":true}'
            else:
                session.delete(revision)


@pytest.mark.parametrize("field,value", [
    ("id", uuid.uuid4()), ("user_id", uuid.uuid4()), ("investigation_id", uuid.uuid4()),
    ("idempotency_key", "new-key"), ("kind", "pin"), ("expected_head_id", uuid.uuid4()),
    ("candidate_revision_id", uuid.uuid4()), ("request_json", '{"changed":true}'),
    ("request_sha256", "d" * 64), ("candidate_json", '{"changed":true}'),
    ("references_json", '["changed"]'), ("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
])
def test_operation_prepared_inputs_cannot_be_mutated(storage, field, value):
    factory, _, _, _, _, operation_id = storage
    with pytest.raises(ValueError, match="immutable"):
        with factory.begin() as session:
            setattr(session.get(ResearchContextOperation, operation_id), field, value)


@pytest.mark.parametrize("state", ["prepared", "committed", "conflict", "unavailable", "uncertain"])
def test_operation_delivery_state_can_change_without_rewriting_preparation(storage, state):
    factory, _, _, _, _, operation_id = storage
    with factory.begin() as session:
        operation = session.get(ResearchContextOperation, operation_id)
        operation.state, operation.error_code = state, "synthetic-error"
    with factory() as session:
        operation = session.get(ResearchContextOperation, operation_id)
        assert operation.state == state
        assert operation.request_json == operation.candidate_json == "{}"
        assert operation.references_json == "[]"


@pytest.mark.parametrize("kind", ["investigation", "conversation", "operation"])
def test_application_records_do_not_offer_destructive_orm_delete(storage, kind):
    factory, _, investigations, _, conversation_id, operation_id = storage
    model, identity = {
        "investigation": (ResearchInvestigation, investigations[0]),
        "conversation": (ResearchConversation, conversation_id),
        "operation": (ResearchContextOperation, operation_id),
    }[kind]
    with pytest.raises(ValueError, match="immutable"):
        with factory.begin() as session:
            session.delete(session.get(model, identity))


@pytest.mark.parametrize("kind,field,value", [
    ("investigation", "id", uuid.uuid4()),
    ("investigation", "user_id", uuid.uuid4()),
    ("investigation", "predecessor_investigation_id", uuid.uuid4()),
    ("investigation", "predecessor_revision_id", uuid.uuid4()),
    ("investigation", "created_at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ("conversation", "id", uuid.uuid4()),
    ("conversation", "investigation_id", uuid.uuid4()),
    ("conversation", "created_at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
])
def test_investigation_and_conversation_identity_is_immutable(storage, kind, field, value):
    factory, _, investigations, _, conversation_id, _ = storage
    model, identity = (ResearchInvestigation, investigations[0]) if kind == "investigation" else (ResearchConversation, conversation_id)
    with pytest.raises(ValueError, match="immutable"):
        with factory.begin() as session:
            setattr(session.get(model, identity), field, value)


@pytest.mark.parametrize("kind", ["investigation", "conversation"])
@pytest.mark.parametrize("name", ["", "   ", "x" * 256, " " * 255 + "a"])
def test_names_require_nonempty_bounded_storage(storage, kind, name):
    factory, owners, investigations, _, _, _ = storage
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            if kind == "investigation":
                session.add(ResearchInvestigation(user_id=owners[0], name=name))
            else:
                session.add(ResearchConversation(investigation_id=investigations[0], name=name))


@pytest.mark.parametrize("kind", ["investigation", "conversation"])
def test_concurrent_metadata_changes_do_not_silently_overwrite(storage, kind):
    factory, _, investigations, _, conversation_id, _ = storage
    model, identity = (ResearchInvestigation, investigations[0]) if kind == "investigation" else (ResearchConversation, conversation_id)
    with factory() as first, factory() as second:
        left, right = first.get(model, identity), second.get(model, identity)
        left.name = "First committed rename"
        first.commit()
        right.name = "Stale overwrite"
        with pytest.raises(StaleDataError):
            second.commit()
    with factory() as session:
        assert session.get(model, identity).name == "First committed rename"


def test_retirement_and_legal_hold_preserve_conversations_and_history(storage):
    factory, _, investigations, revisions, conversation_id, operation_id = storage
    with factory.begin() as session:
        investigation = session.get(ResearchInvestigation, investigations[0])
        investigation.legal_hold = True
        investigation.status = "retired"
        investigation.retired_at = datetime.now(timezone.utc)
    with factory() as session:
        assert session.get(ResearchConversation, conversation_id)
        assert session.get(ResearchContextRevision, revisions[0]).payload_json == "{}"
        assert session.get(ResearchContextOperation, operation_id)


@pytest.mark.parametrize("changes", [
    {"snapshot_id": "A" * 64}, {"snapshot_id": "g" * 64}, {"snapshot_id": "a" * 63},
    {"payload_sha256": "b" * 65}, {"sequence": 0},
])
def test_invalid_revision_identity_or_sequence_rejected(storage, changes):
    factory, owners, investigations, _, _, _ = storage
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(_revision(investigations[0], owners[0], **{"sequence": 2, **changes}))


@pytest.mark.parametrize("changes", [
    {"idempotency_key": ""}, {"idempotency_key": "x" * 129}, {"kind": "x" * 33},
    {"state": "invented"}, {"request_sha256": "C" * 64}, {"error_code": "x" * 65},
])
def test_invalid_operation_metadata_rejected(storage, changes):
    factory, owners, investigations, _, _, _ = storage
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(_operation(investigations[0], owners[0], **changes))


def test_idempotency_is_unique_per_owner_across_investigations(storage):
    factory, owners, investigations, _, _, operation_id = storage
    with factory() as session:
        key = session.get(ResearchContextOperation, operation_id).idempotency_key
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(_operation(investigations[1], owners[0], idempotency_key=key))
    with factory.begin() as session:
        session.add(_operation(investigations[2], owners[1], idempotency_key=key))
