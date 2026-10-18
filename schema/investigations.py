"""C17 owner-private investigation requests; trusted identity stays server-owned.

References select retained objects. Attachments and pins are separate context
operations and never alter the independent C08 scientific evidence scope.
"""
from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from retrieval.source_scope import EvidenceScope
from schema.context_catalogue import ContractModel, Identifier, Sha256, _finite_json, _strict_scope

MAX_CONTEXT_REFERENCES = 256
UUIDString = Annotated[
    str,
    StringConstraints(min_length=36, max_length=36, pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"),
]
PositiveVersion = Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
InvestigationName = Annotated[str, StringConstraints(min_length=1, max_length=200)]


def finite_utf8_json(value):
    """Reject non-JSON objects, nonfinite numbers and lone Unicode surrogates."""
    _finite_json(value)
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Investigation values must be finite UTF-8 JSON") from exc
    return value


class InvestigationRequest(ContractModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, allow_inf_nan=False, revalidate_instances="always",
    )

    @model_validator(mode="before")
    @classmethod
    def json_values(cls, value):
        if isinstance(value, cls):
            value = value.model_dump(mode="python")
        # Scope instances are accepted for trusted internal typed callers;
        # HTTP callers can supply only the canonical JSON representation.
        if isinstance(value, dict):
            value = {
                key: item.model_dump(mode="python") if isinstance(item, (EvidenceScope, InvestigationRequest)) else item
                for key, item in value.items()
            }
        return finite_utf8_json(value)

    @field_validator("name", check_fields=False)
    @classmethod
    def meaningful_name(cls, value):
        if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Names require visible text without surrounding whitespace or controls")
        return value

    @field_validator("scope", mode="before", check_fields=False)
    @classmethod
    def scientific_scope(cls, value):
        return _strict_scope(value)


class ContextReference(InvestigationRequest):
    kind: Literal["catalogue", "artifact"]
    id: Identifier
    snapshot_id: Sha256


class InvestigationCreateRequest(InvestigationRequest):
    name: InvestigationName
    snapshot_id: Sha256
    scope: EvidenceScope
    idempotency_key: UUIDString


class InvestigationListRequest(InvestigationRequest):
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 25
    after_id: UUIDString | None = None


class InvestigationGetRequest(InvestigationRequest):
    investigation_id: UUIDString


class InvestigationRenameRequest(InvestigationGetRequest):
    name: InvestigationName
    expected_version: PositiveVersion
    idempotency_key: UUIDString


class InvestigationArchiveRequest(InvestigationGetRequest):
    archived: bool = True
    expected_version: PositiveVersion
    idempotency_key: UUIDString


class ConversationCreateRequest(InvestigationGetRequest):
    name: InvestigationName
    idempotency_key: UUIDString


class ConversationListRequest(InvestigationGetRequest, InvestigationListRequest):
    pass


class ConversationGetRequest(InvestigationGetRequest):
    conversation_id: UUIDString


class ConversationRenameRequest(ConversationGetRequest):
    name: InvestigationName
    expected_version: PositiveVersion
    idempotency_key: UUIDString


class ContextGetRequest(InvestigationGetRequest):
    revision_id: UUIDString | None = None


class ContextReferenceChange(InvestigationRequest):
    op: Literal["attach", "detach", "pin", "unpin"]
    reference: ContextReference


class ContextScopeChange(InvestigationRequest):
    op: Literal["scope"]
    scope: EvidenceScope


ContextChange = Annotated[ContextReferenceChange | ContextScopeChange, Field(discriminator="op")]


class ContextChangeRequest(InvestigationGetRequest):
    expected_revision_id: UUIDString
    idempotency_key: UUIDString
    change: ContextChange


class InvestigationRefreshRequest(InvestigationGetRequest):
    expected_revision_id: UUIDString
    target_snapshot_id: Sha256
    name: InvestigationName
    idempotency_key: UUIDString


class OperationGetRequest(InvestigationRequest):
    operation_id: UUIDString


class OperationRetryRequest(OperationGetRequest):
    pass


INVESTIGATION_REQUEST_MODELS: dict[str, type[InvestigationRequest]] = {
    "create": InvestigationCreateRequest,
    "list": InvestigationListRequest,
    "get": InvestigationGetRequest,
    "rename": InvestigationRenameRequest,
    "archive": InvestigationArchiveRequest,
    "conversations/create": ConversationCreateRequest,
    "conversations/list": ConversationListRequest,
    "conversations/get": ConversationGetRequest,
    "conversations/rename": ConversationRenameRequest,
    "context/get": ContextGetRequest,
    "context/change": ContextChangeRequest,
    "refresh": InvestigationRefreshRequest,
    "operations/get": OperationGetRequest,
    "operations/retry": OperationRetryRequest,
}
