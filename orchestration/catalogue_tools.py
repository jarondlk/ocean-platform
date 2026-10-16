"""Typed, read-only catalogue tools sharing the authenticated API executor.

The identity provider is supplied by the host, never by model arguments. Each
invocation resolves it again before asking the service for current access.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

import config
from orchestration.catalogue_service import (
    CatalogueService, CatalogueServiceError, catalogue_access_binding,
)
from schema.catalogue_service import (
    CatalogueCoverageRequest,
    CatalogueListRequest,
    CatalogueOpenRequest,
    CatalogueOverviewRequest,
    CatalogueQueryRequest,
    CatalogueRelationshipsRequest,
    PublishedAnalysisRequest,
)

logger = logging.getLogger(__name__)

CATALOGUE_REQUEST_MODELS: Mapping[str, type[BaseModel]] = {
    "catalogue.overview": CatalogueOverviewRequest,
    "catalogue.list": CatalogueListRequest,
    "catalogue.open": CatalogueOpenRequest,
    "catalogue.coverage": CatalogueCoverageRequest,
    "catalogue.query": CatalogueQueryRequest,
    "catalogue.relationships": CatalogueRelationshipsRequest,
    "analysis.get_published": PublishedAnalysisRequest,
}


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def invoke_catalogue(
    service: CatalogueService | None,
    name: str,
    payload: BaseModel | Mapping[str, Any],
    identity_provider: Callable[[], Any],
) -> tuple[int, dict[str, Any]]:
    """Complete one bounded synchronous invocation, including serialization.

    Routes offload this whole function. Its result contains no live resources,
    and the same sanitized error body is returned by the typed agent tools.
    """
    # API authorization middleware runs before public body validation. Resolve
    # trusted identity once here, including for invalid or disabled requests.
    try:
        user = identity_provider()
        catalogue_access_binding(user)
    except CatalogueServiceError as exc:
        return exc.status_code, _error(exc.code, exc.message)
    except Exception:
        logger.error("Catalogue identity resolution failed; returning unavailable")
        return 503, _error("catalogue_unavailable", "Catalogue is unavailable")
    model = CATALOGUE_REQUEST_MODELS.get(name)
    if model is None:
        return 422, _error("invalid_request", "Unknown catalogue operation")
    try:
        # Revalidate even constructed model instances; trusted identity, access
        # bindings and permission revisions cannot be smuggled into tool input.
        raw = payload.model_dump() if isinstance(payload, BaseModel) else payload
        request = model.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        return 422, _error("invalid_request", "Catalogue request is invalid")
    # FastAPI validates the public body before handler dispatch. Keep this
    # ordering identical for tools, including disabled or unavailable services.
    try:
        if not config.v1_catalogue_enabled():
            return 503, _error("catalogue_disabled", "Catalogue access is disabled")
    except config.SecurityConfigurationError:
        return 503, _error("catalogue_unavailable", "Catalogue configuration is invalid")
    if service is None or not callable(getattr(service, "execute", None)):
        return 503, _error("catalogue_unavailable", "Catalogue is unavailable")
    try:
        result = service.execute(name, request.model_dump(mode="json", exclude_none=True), user)
        if isinstance(result, BaseModel):
            result = result.model_dump(mode="json")
        # Both boundaries return precisely the same JSON-compatible values;
        # non-finite numbers and accidental live objects fail closed here.
        serialized = json.loads(json.dumps(result, allow_nan=False))
        if not isinstance(serialized, dict):
            raise TypeError("Catalogue result must be an object")
        return 200, serialized
    except CatalogueServiceError as exc:
        return exc.status_code, _error(exc.code, exc.message)
    except Exception:
        logger.error("Catalogue invocation failed; returning unavailable")
        return 503, _error("catalogue_unavailable", "Catalogue is unavailable")


class CatalogueTools:
    """Seven registered tools with public request schemas and trusted identity."""

    def __init__(
        self,
        service: CatalogueService | None,
        identity_provider: Callable[[], Any],
    ) -> None:
        if not callable(identity_provider):
            raise TypeError("A trusted identity provider is required")
        self._service = service
        self._identity_provider = identity_provider

    @staticmethod
    def schemas() -> list[dict[str, Any]]:
        return [
            {"name": name, "parameters": model.model_json_schema()}
            for name, model in CATALOGUE_REQUEST_MODELS.items()
        ]

    def _invoke(self, name: str, request: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
        return invoke_catalogue(self._service, name, request, self._identity_provider)[1]

    def overview(self, request: CatalogueOverviewRequest | Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke("catalogue.overview", request)

    def list(self, request: CatalogueListRequest | Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke("catalogue.list", request)

    def open(self, request: CatalogueOpenRequest | Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke("catalogue.open", request)

    def coverage(self, request: CatalogueCoverageRequest | Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke("catalogue.coverage", request)

    def query(self, request: CatalogueQueryRequest | Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke("catalogue.query", request)

    def relationships(self, request: CatalogueRelationshipsRequest | Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke("catalogue.relationships", request)

    def get_published(self, request: PublishedAnalysisRequest | Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke("analysis.get_published", request)
