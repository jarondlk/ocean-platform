"""C16 discovery over an explicit newest-first registry, never a global head.

Host-owned discovery policy is evaluated afresh on every request. Its revision
must change with its permission decisions; use a per-user revision callback for
mutable policies. C14 independently rechecks registration, current source policy,
lifecycle and sealed bytes for every descriptor the discovery predicate permits.
An explicitly injected test resolver remains a trusted C14 dependency, not a
runtime fixture fallback. No store, database, model or application paths are found.
Multi-process hosts should explicitly share a stable cursor_key; the generated
process-local default deliberately invalidates cursors after reconfiguration.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable, Sequence

from pydantic import TypeAdapter

import config
from orchestration.catalogue_service import (
    CatalogueService, CatalogueServiceError, catalogue_access_binding,
)
from schema.catalogue_browser import (
    CatalogueSnapshotDescriptor, CatalogueSnapshotsRequest, CatalogueSnapshotsResponse,
)
from schema.context_catalogue import CatalogueListing, Identifier, canonical_json

MAX_CONFIGURED_SNAPSHOTS = 128
_identifier = TypeAdapter(Identifier)


def _error(code="catalogue_unavailable"):
    message, status = {
        "catalogue_unavailable": ("Catalogue is unavailable", 503),
        "catalogue_disabled": ("Catalogue browser is disabled", 503),
        "invalid_request": ("Catalogue request is invalid", 422),
        "invalid_cursor": ("Catalogue cursor is stale or invalid", 409),
    }[code]
    return CatalogueServiceError(code, message, status)


class CatalogueBrowser:
    def __init__(
        self, *, service: CatalogueService, snapshots: Sequence[CatalogueSnapshotDescriptor],
        permitted: Callable, revision: str | Callable, cursor_key: bytes | None = None,
    ):
        if not isinstance(service, CatalogueService) or not callable(permitted):
            raise ValueError("Explicit catalogue service and current discovery policy required")
        if not isinstance(snapshots, (list, tuple)) or len(snapshots) > MAX_CONFIGURED_SNAPSHOTS:
            raise ValueError("A bounded explicit newest-first snapshot registry is required")
        values = tuple(CatalogueSnapshotDescriptor.model_validate(
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        ) for item in snapshots)
        if len({item.snapshot_id for item in values}) != len(values):
            raise ValueError("Configured snapshot identities must be distinct")
        if not callable(revision):
            _identifier.validate_python(revision)
        if cursor_key is not None and (type(cursor_key) is not bytes or len(cursor_key) < 32):
            raise ValueError("Explicit cursor keys require at least 32 bytes")
        self.service, self._permitted, self._revision = service, permitted, revision
        # Immutable encoded copies prevent caller or policy mutations from
        # replacing labels, order or identities after configuration acceptance.
        self._descriptors = tuple(canonical_json(item.model_dump(mode="json")) for item in values)
        self._registry_digest = hashlib.sha256(canonical_json(self._descriptors).encode()).hexdigest()
        self._cursor_key = cursor_key if cursor_key is not None else secrets.token_bytes(32)

    def _offset(self, cursor, context):
        if cursor is None:
            return 0
        try:
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            payload = json.loads(raw)
            if type(payload) is not dict or set(payload) != {"version", "context", "offset", "signature"}:
                raise ValueError("Invalid cursor")
            if canonical_json(payload).encode() != raw:
                raise ValueError("Invalid cursor")
            signature = payload.pop("signature")
            expected = hmac.new(self._cursor_key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()
            if (
                type(signature) is not str or not hmac.compare_digest(signature, expected)
                or payload["version"] != "catalogue-browser-v1" or payload["context"] != context
                or type(payload["offset"]) is not int or payload["offset"] < 1
            ):
                raise ValueError("Invalid cursor")
            return payload["offset"]
        except Exception:
            raise _error("invalid_cursor") from None

    def _cursor(self, offset, context):
        payload = {"version": "catalogue-browser-v1", "context": context, "offset": offset}
        signature = hmac.new(self._cursor_key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(canonical_json({**payload, "signature": signature}).encode()).decode().rstrip("=")

    def discover(self, payload, user):
        binding = catalogue_access_binding(user)
        try:
            request = CatalogueSnapshotsRequest.model_validate(
                payload.model_dump(mode="json", warnings=False) if hasattr(payload, "model_dump") else payload
            )
        except (ValueError, TypeError):
            raise _error("invalid_request") from None
        try:
            if not config.v1_catalogue_enabled() or not config.v1_catalogue_browser_enabled():
                raise _error("catalogue_disabled")
            revision = self._revision(user) if callable(self._revision) else self._revision
            _identifier.validate_python(revision)
            visible, revisions = [], []
            for encoded in self._descriptors:
                detached = CatalogueSnapshotDescriptor.model_validate_json(encoded)
                if self._permitted(user, detached) is not True:
                    continue
                # Recreate after policy evaluation; the predicate sees detached
                # values and cannot change configured response metadata.
                descriptor = CatalogueSnapshotDescriptor.model_validate_json(encoded)
                try:
                    overview = CatalogueListing.model_validate(self.service.overview({
                        "snapshot_id": descriptor.snapshot_id,
                        "scope": request.scope.model_dump(mode="json"),
                    }, user))
                except CatalogueServiceError as exc:
                    if exc.code == "not_found":
                        continue
                    raise _error() from None
                visible.append(descriptor)
                revisions.append([descriptor.snapshot_id, overview.request.access_revision])
            access_revision = "c16:" + hashlib.sha256(canonical_json({
                "binding": binding, "discovery_policy": revision,
                "configured_order": self._registry_digest, "visible_revisions": revisions,
            }).encode()).hexdigest()
            context = hashlib.sha256(canonical_json({
                "access_revision": access_revision, "scope": request.scope.canonical(), "limit": request.limit,
            }).encode()).hexdigest()
            offset = self._offset(request.cursor, context)
            if offset > len(visible):
                raise _error("invalid_cursor")
            page = visible[offset:offset + request.limit]
            following = offset + len(page)
            return CatalogueSnapshotsResponse(
                scope=request.scope, snapshots=page,
                latest_snapshot_id=visible[0].snapshot_id if visible else None,
                total=len(visible), access_revision=access_revision,
                next_cursor=self._cursor(following, context) if following < len(visible) else None,
            ).model_dump(mode="json")
        except CatalogueServiceError:
            raise
        except Exception:
            raise _error() from None
