"""Explicit synthetic C14 test dependencies; never imported by runtime code.

The fixture backend supplies the complete current permitted C08 view. The new
service performs search, ordering and pagination itself, so these tests do not
reuse C08's optimized ``pages`` reference helper as acceptance evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import uuid

from api.auth import CurrentUser, ROLE_PERMISSIONS
from retrieval.source_scope import document_matches
from schema.context_catalogue import canonical_json
from schema.context_catalogue_fixtures import FixtureAccess, fixture_scope, make_catalogue
from schema.scientific_catalogue import ScientificResponse


def fixture_user(subject="researcher-a", *, role="researcher"):
    return CurrentUser(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"c14-test:{subject}"),
        email=f"{subject}@example.invalid",
        display_name=subject,
        role=role,
        account_type="internal",
        status="active",
        permissions=ROLE_PERMISSIONS[role],
        auth_provider="synthetic-c14",
    )


def payload(catalogue, **updates):
    return {
        "snapshot_id": catalogue.snapshot_id,
        "scope": fixture_scope().model_dump(mode="json"),
        **updates,
    }


def dataset_id(index):
    return f"synthetic:dataset:{index:06d}"


@dataclass
class SyntheticServiceBackend:
    """Complete-view dependency injected into the real C14 service explicitly."""

    catalogue: object
    access: FixtureAccess
    view_calls: int = 0
    query_calls: int = 0

    def view(self, request):
        self.view_calls += 1
        if request.snapshot_id != self.catalogue.snapshot_id:
            raise ValueError("Synthetic snapshot mismatch")
        scope = request.scope.canonical()
        nodes = {}
        for identity, record in self.catalogue.records.items():
            if not self.catalogue.permitted(identity, self.access):
                continue
            if record.node.source_family is not None and not document_matches(
                record.observation, scope
            ):
                continue
            nodes[identity] = self.catalogue.open(identity, self.access).model_copy(
                update={"scope": request.scope}
            )
        return nodes

    def query(self, request):
        """A test-only fixed inventory operation over complete descendant inputs."""
        self.query_calls += 1
        if request.operation_id != "c13.inventory" or request.operation_version != "c13-v1":
            raise ValueError("Synthetic backend supports fixed inventory only")
        if len(request.input_ids) != 1 or set(request.parameters) - {"limit"}:
            raise ValueError("Synthetic inventory requires one explicit input")
        identity = request.input_ids[0]
        if not self.catalogue.permitted(identity, self.access):
            raise PermissionError("Synthetic input unavailable")
        scope = request.scope.canonical()
        keys = sorted(
            key
            for key in self.catalogue.descendants(identity, self.access)
            if self.catalogue.records[key].node.kind == "dataset"
            and document_matches(self.catalogue.records[key].observation, scope)
        )
        columns = [{"key": "count", "title": {"en": "Count", "ja": "件数"}}]
        rows = [{"count": len(keys)}]
        content_hash = hashlib.sha256(
            canonical_json({"columns": columns, "rows": rows}).encode()
        ).hexdigest()
        return ScientificResponse.model_validate(
            {
                "snapshot_id": request.snapshot_id,
                "scope": request.scope,
                "columns": columns,
                "rows": rows,
                "qualifications": ["Synthetic explicit dependency; no scientific approval"],
                "receipt": {
                    "snapshot_id": request.snapshot_id,
                    "scope": request.scope,
                    "receipt_id": "synthetic:inventory:" + content_hash,
                    "operation_id": request.operation_id,
                    "operation_version": request.operation_version,
                    "parameters": request.parameters,
                    "inputs": [
                        {
                            "object_id": key,
                            "content_sha256": self.catalogue.records[key].node.provenance.content_sha256,
                        }
                        for key in keys
                    ],
                    "authority": "descriptive",
                    "availability": {"status": "available"},
                    "provenance": {"references": ["Synthetic complete-scope fixture"]},
                    "total_rows": {
                        "state": "known",
                        "entity": "rows",
                        "denominator": "One complete-scope dataset count",
                        "value": 1,
                    },
                    "returned_count": 1,
                    "preview_truncated": False,
                    "source_completeness": "complete",
                    "query_completion": "complete",
                    "content_sha256": content_hash,
                },
            }
        )


@dataclass
class MutableFixtureResolver:
    catalogues: dict
    policies: dict = field(default_factory=dict)
    revisions: dict = field(default_factory=dict)
    calls: int = 0
    backends: list = field(default_factory=list)

    def resolve(self, user, snapshot_id):
        from orchestration.catalogue_service import ResolvedCatalogue

        self.calls += 1
        catalogue = self.catalogues[snapshot_id]
        access = FixtureAccess(
            subject_id=user.display_name,
            revision=self.revisions.get(user.id, "permissions-1"),
            denied_ids=self.policies.get(user.id, frozenset()),
        )
        backend = SyntheticServiceBackend(catalogue, access)
        self.backends.append(backend)
        return ResolvedCatalogue(
            backend=backend,
            revision=access.revision,
            cache_token=f"synthetic:{id(catalogue)}:{access.binding}",
        )

    def revoke(self, user, *identities):
        self.policies[user.id] = frozenset(identities)
        self.revisions[user.id] = "permissions-2"


def synthetic_service(count=137, *, catalogue=None):
    from orchestration.catalogue_service import CatalogueService

    catalogue = catalogue or make_catalogue(count)
    resolver = MutableFixtureResolver({catalogue.snapshot_id: catalogue})
    return catalogue, resolver, CatalogueService(resolver=resolver)
