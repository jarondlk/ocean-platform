"""Explicit beta context composition, without model/queue/worker execution.

The shared authenticated host remains responsible for request authorization,
feature flags and the independent database schema. This helper only composes
C17 investigation/conversation/context persistence over an already validated
catalogue and its SAME reference-capable canonical lifecycle store. It cannot
turn a read-only reader, empty registry, fake service or local file into durable
production context storage.
"""
from __future__ import annotations

from ingestion.beta_catalogue_retention import BetaCatalogueRetentionStore
from orchestration.catalogue_browser import CatalogueBrowser
from orchestration.catalogue_service import CatalogueService, FrozenCatalogueResolver
from orchestration.investigations import InvestigationService

SITE_ID = "v1:ocean-v1-beta-20261101"
CONTEXT_MUTATION_PATHS = frozenset({
    "/research/investigations/create", "/research/investigations/rename",
    "/research/investigations/archive", "/research/investigations/conversations/create",
    "/research/investigations/conversations/rename", "/research/investigations/context/change",
    "/research/investigations/refresh", "/research/investigations/operations/retry",
})
# UUID application IDs require no sequence rights. Append-only revision/audit
# tables receive no UPDATE or DELETE. Existing auth/limiter grants are separate.
CONTEXT_TABLE_PRIVILEGES = {
    "research_investigation": frozenset({"SELECT", "INSERT"}),
    "research_conversation": frozenset({"SELECT", "INSERT"}),
    "research_context_revision": frozenset({"SELECT", "INSERT"}),
    "research_context_operation": frozenset({"SELECT", "INSERT"}),
    "audit_event": frozenset({"INSERT"}),
}
CONTEXT_UPDATE_COLUMNS = {
    "research_investigation": frozenset({"name", "metadata_version", "status", "head_revision_id",
        "legal_hold", "updated_at", "retired_at"}),
    "research_conversation": frozenset({"name", "metadata_version", "updated_at"}),
    "research_context_operation": frozenset({"state", "error_code", "updated_at"}),
}


def compose_beta_context_services(*, session_factory, site_id, catalogue_service, catalogue_browser):
    """Return real context persistence only after exact shared-store validation.

    No DDL, migration, grants, reference writes, snapshot publication, model or
    provider call is performed. Registration access is read/validated at startup.
    C20/C21 history and artifact attachment remain separately unconfigured.
    """
    from api.v1_host import HostConfigurationError, V1ReadServices
    try:
        if site_id != SITE_ID or not callable(session_factory):
            raise ValueError("Exact beta database/site binding required")
        if (not isinstance(catalogue_service, CatalogueService)
                or not isinstance(catalogue_browser, CatalogueBrowser)
                or catalogue_browser.service is not catalogue_service):
            raise ValueError("Exact validated catalogue/browser binding required")
        resolver = catalogue_service.resolver
        if (not isinstance(resolver, FrozenCatalogueResolver)
                or not isinstance(resolver.store, BetaCatalogueRetentionStore)
                or not resolver.registrations):
            raise ValueError("Explicit beta reference-capable C09 authority required")
        for registration in resolver.registrations.values():
            registration.require_current(resolver.store)
        investigations = InvestigationService(session_factory=session_factory, site_id=site_id,
            catalogue_service=catalogue_service, snapshot_store=resolver.store,
            registrations=resolver.registrations)
        services = V1ReadServices(catalogue_service=catalogue_service,
            catalogue_browser=catalogue_browser, investigation_service=investigations)
        services.validate(session_factory=session_factory, site_id=site_id)
        return services
    except Exception:
        raise HostConfigurationError("Explicit durable beta context binding unavailable") from None
