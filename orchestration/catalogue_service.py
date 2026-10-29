"""C14 trusted service: no configured source discovery or synthetic fallback."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
from threading import RLock
from typing import Callable, Mapping

from pydantic import TypeAdapter, ValidationError

from api.auth import CurrentUser
from ingestion.catalogue_snapshot import SnapshotAccessDenied
from ingestion.provenance_snapshot import SnapshotNotFound
from orchestration.frozen_catalogue import AdapterAccess, AdapterAccessDenied, FrozenCatalogueAdapter
from orchestration.frozen_edna_catalogue import EDNAAccess, FrozenEDNACatalogueAdapter
from orchestration.frozen_scientific_catalogue import FrozenScientificCatalogueAdapter, ScientificAccess
from orchestration.frozen_sst_catalogue import FrozenSSTCatalogueAdapter, SSTAccess
from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.catalogue_service import REQUEST_MODELS
from schema.context_catalogue import (
    CatalogueFilters, CatalogueListing, CatalogueNode, Identifier, ListingRequest,
    OperationRequest, canonical_json, make_cursor, ordered_nodes, validate_cursor,
)
from schema.scientific_catalogue import ScientificResponse

MAX_NAVIGATION_OBJECTS = 150_000
MAX_ANCESTRY_DEPTH = 128
_identifier = TypeAdapter(Identifier)


class CatalogueServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def _error(code):
    message, status = {
        "authentication_required": ("Authentication is required", 401),
        "access_denied": ("Catalogue access is denied", 403),
        "not_found": ("Catalogue object is unavailable", 404),
        "invalid_request": ("Catalogue request is invalid", 422),
        "invalid_cursor": ("Catalogue cursor is stale or invalid", 409),
        "catalogue_unavailable": ("Catalogue is unavailable", 503),
    }[code]
    return CatalogueServiceError(code, message, status)


def _authorize(user):
    if not isinstance(user, CurrentUser):
        raise _error("authentication_required")
    if user.status != "active" or "data:read" not in user.permissions:
        raise _error("access_denied")


def catalogue_access_binding(user):
    _authorize(user)
    return hashlib.sha256(canonical_json({
        "subject": str(user.id), "role": user.role, "account_type": user.account_type,
        "status": user.status, "permissions": sorted(user.permissions),
        "auth_provider": user.auth_provider,
    }).encode()).hexdigest()


@dataclass(frozen=True)
class CataloguePolicy:
    """Revision must change with every effective callback membership decision."""
    revision: str
    dataset_eligible: Callable | Mapping[str, Callable]
    scientific_eligible: Callable

    def __post_init__(self):
        _identifier.validate_python(self.revision)
        if not callable(self.scientific_eligible):
            raise ValueError("Explicit current scientific policy required")
        if not callable(self.dataset_eligible) and (
            not isinstance(self.dataset_eligible, Mapping)
            or set(self.dataset_eligible) != set(FAMILIES)
            or not all(callable(v) for v in self.dataset_eligible.values())
        ):
            raise ValueError("Explicit current dataset policies required")


@dataclass(frozen=True)
class ResolvedCatalogue:
    backend: object
    revision: str
    cache_token: str | None = None

    def __post_init__(self):
        _identifier.validate_python(self.revision)
        if not callable(getattr(self.backend, "view", None)):
            raise ValueError("Explicit complete catalogue view required")
        if self.cache_token is not None:
            _identifier.validate_python(self.cache_token)


class _FrozenBackend:
    def __init__(self, adapter):
        self.adapter = adapter

    def view(self, request):
        return self.adapter._load(request).nodes

    def query(self, request):
        return self.adapter.query(request)

    def inspect(self, identity, request):
        return self.adapter.inspect(identity, request)


class _IntegrityBoundary:
    """Distinguish frozen input verification from public operation parameters."""
    def _load(self, request):
        try:
            return super()._load(request)
        except (PermissionError, SnapshotNotFound):
            raise
        except (ValueError, OSError):
            raise _error("catalogue_unavailable") from None


class _ScientificAdapter(_IntegrityBoundary, FrozenScientificCatalogueAdapter):
    pass


class _DataAdapter(_IntegrityBoundary, FrozenCatalogueAdapter):
    pass


class _SSTAdapter(_IntegrityBoundary, FrozenSSTCatalogueAdapter):
    pass


class _EDNAAdapter(_IntegrityBoundary, FrozenEDNACatalogueAdapter):
    pass


class FrozenCatalogueResolver:
    """Construct fresh policy-bound adapters over explicit registered stores."""
    def __init__(self, *, store, policy_resolver, registrations):
        if not callable(policy_resolver) or not isinstance(registrations, Mapping):
            raise ValueError("Explicit policy resolver and registrations required")
        self.store, self.policy_resolver = store, policy_resolver
        self.registrations = dict(registrations)

    @staticmethod
    def _access_epoch(lifecycle):
        """Retention reference additions do not change scientific visibility.

        Every other lifecycle action still invalidates. Require a complete audit
        chain and live mappings for its additive tail; incomplete control data
        cannot attest compatibility with a historical execution.
        """
        revision, audits = lifecycle['revision'], lifecycle['audits']
        if type(revision) is not int or revision < 0 or not isinstance(audits, list) or len(audits) != revision:
            raise ValueError('Incomplete catalogue lifecycle audit')
        epoch = 0
        for expected, audit in enumerate(audits, 1):
            if (not isinstance(audit, dict) or type(audit.get('revision')) is not int
                    or audit['revision'] != expected or audit.get('action') not in {
                        'seal', 'promote', 'reference', 'unreference', 'hold', 'revoke', 'retire'}):
                raise ValueError('Invalid catalogue lifecycle audit')
            if audit['action'] != 'reference':
                epoch = expected
        for audit in audits[epoch:]:
            reference, snapshot_id = audit.get('reference'), audit.get('snapshot_id')
            if (not isinstance(reference, str) or not reference or not isinstance(snapshot_id, str) or not snapshot_id
                    or not isinstance(lifecycle.get('references'), dict)
                    or lifecycle['references'].get(reference) != snapshot_id):
                raise ValueError('Unverified additive catalogue reference')
        return epoch

    @staticmethod
    def _revision(policy_revision, lifecycle_revision):
        return 'c14:' + hashlib.sha256(canonical_json({
            'policy': policy_revision, 'lifecycle': lifecycle_revision,
        }).encode()).hexdigest()

    def _authorization_state(self, user, snapshot_id):
        _authorize(user)
        registration = self.registrations.get(snapshot_id)
        if registration is None or registration.snapshot_id != snapshot_id:
            raise _error("not_found")
        registration.require_current(self.store)
        policy = self.policy_resolver(user, snapshot_id)
        if not isinstance(policy, CataloguePolicy):
            raise _error("catalogue_unavailable")
        lifecycle = self.store.lifecycle()
        return registration, policy, lifecycle, self._access_epoch(lifecycle)

    def revision_compatible(self, user, snapshot_id, expected_revision):
        """Accept old raw-revision hashes only through a proven reference tail."""
        _, policy, lifecycle, epoch = self._authorization_state(user, snapshot_id)
        return any(expected_revision == self._revision(policy.revision, candidate)
                   for candidate in range(epoch, lifecycle['revision'] + 1))

    def resolve(self, user, snapshot_id):
        registration, policy, _lifecycle, epoch = self._authorization_state(user, snapshot_id)
        revision = self._revision(policy.revision, epoch)
        binding = catalogue_access_binding(user)

        def eligible(family):
            return policy.dataset_eligible if callable(policy.dataset_eligible) else policy.dataset_eligible[family]

        # C10 handles both families, which may have distinct current policies.
        def c10_allowed(snapshot, metadata):
            return eligible(metadata.family)(snapshot, metadata) is True

        c10 = _DataAdapter(store=self.store, access=AdapterAccess(binding, revision, c10_allowed))
        adapters = {
            "ctd": c10, "metagenome": c10,
            "remote_sensing": _SSTAdapter(store=self.store, access=SSTAccess(binding, revision, eligible("remote_sensing"))),
            "edna_metabarcoding": _EDNAAdapter(store=self.store, access=EDNAAccess(binding, revision, eligible("edna_metabarcoding"))),
        }
        adapter = _ScientificAdapter(
            store=self.store, adapters=adapters,
            access=ScientificAccess(binding, revision, policy.scientific_eligible),
        )
        # No frozen-source view cache: C13 rechecks exact bytes and access.
        return ResolvedCatalogue(_FrozenBackend(adapter), revision)


@dataclass(frozen=True)
class _View:
    nodes: dict
    ordered_ids: tuple[str, ...]


@dataclass(frozen=True)
class _BaseView:
    nodes: dict
    paths: dict


class CatalogueService:
    def __init__(self, *, resolver, maximum_cached_views=4):
        if not callable(getattr(resolver, "resolve", None)):
            raise ValueError("Explicit current catalogue resolver required")
        if type(maximum_cached_views) is not int or not 0 <= maximum_cached_views <= 8:
            raise ValueError("Bounded catalogue view cache required")
        self.resolver, self.maximum_cached_views = resolver, maximum_cached_views
        self._cache, self._bases, self._lock = OrderedDict(), OrderedDict(), RLock()

    def execute(self, name, payload, user):
        _authorize(user)
        model = REQUEST_MODELS.get(name)
        if model is None:
            raise _error("invalid_request")
        try:
            request = model.model_validate(payload.model_dump(mode="json", warnings=False) if hasattr(payload, "model_dump") else payload)
        except (ValueError, TypeError):
            raise _error("invalid_request") from None
        try:
            resolved = self.resolver.resolve(user, request.snapshot_id)
            if not isinstance(resolved, ResolvedCatalogue):
                raise _error("catalogue_unavailable")
        except CatalogueServiceError:
            raise
        except (SnapshotAccessDenied, SnapshotNotFound, AdapterAccessDenied, PermissionError):
            raise _error("not_found") from None
        except Exception:
            raise _error("catalogue_unavailable") from None
        try:
            return self._execute(name, request, user, resolved)
        except CatalogueServiceError:
            raise
        except (SnapshotAccessDenied, SnapshotNotFound, AdapterAccessDenied, PermissionError):
            raise _error("not_found") from None
        except ValidationError:
            raise _error("invalid_request") from None
        except Exception:
            raise _error("catalogue_unavailable") from None

    def overview(self, payload, user):
        return self.execute("catalogue.overview", payload, user)

    def list(self, payload, user):
        return self.execute("catalogue.list", payload, user)

    def open(self, payload, user):
        return self.execute("catalogue.open", payload, user)

    def coverage(self, payload, user):
        return self.execute("catalogue.coverage", payload, user)

    def query(self, payload, user):
        return self.execute("catalogue.query", payload, user)

    def relationships(self, payload, user):
        return self.execute("catalogue.relationships", payload, user)

    def get_published(self, payload, user):
        return self.execute("analysis.get_published", payload, user)

    @staticmethod
    def _internal(request, user, resolved, **changes):
        payload = {
            "snapshot_id": request.snapshot_id, "scope": request.scope,
            "access_binding": catalogue_access_binding(user), "access_revision": resolved.revision,
            **changes,
        }
        try:
            return ListingRequest.model_validate(payload)
        except ValueError:
            raise _error("invalid_cursor" if changes.get("cursor") else "invalid_request") from None

    def _execute(self, name, request, user, resolved):
        if name in {"catalogue.overview", "catalogue.list", "catalogue.relationships"}:
            relation = None
            if name == "catalogue.overview":
                options = {"filters": CatalogueFilters(kinds=["root"])}
            else:
                options = request.model_dump(exclude={"schema_version", "snapshot_id", "scope", "object_id"})
                if name == "catalogue.relationships":
                    relation = request.object_id
                    options["filters"]["roots"] = ["relationships"]
                    if relation is not None:
                        options["parent_id"] = relation
            internal = self._internal(request, user, resolved, **options)
            view = self._view(internal, resolved, relation=relation)
            return self._page(view, internal).model_dump(mode="json")
        if name == "catalogue.open":
            internal = self._internal(request, user, resolved)
            view = self._view(internal, resolved)
            node = view.nodes.get(request.object_id)
            if node is None:
                raise _error("not_found")
            if request.include_details:
                inspect = getattr(resolved.backend, "inspect", None)
                details = inspect(request.object_id, internal) if callable(inspect) else {
                    "availability": {"status": "unavailable", "reason": "This backend does not expose object details"},
                }
                return {"node": node.model_dump(mode="json"), "details": self._json(details, permitted_ids=set(view.nodes))}
            return node.model_dump(mode="json")
        if name == "catalogue.query":
            identity, operation, parameters = request.input_ids, request.operation_id, request.parameters
        elif name == "catalogue.coverage":
            identity, operation = [request.object_id], "c13.coverage"
            parameters = {"parameters": request.parameters, "limit": request.limit, "offset": request.offset}
        else:
            identity, operation = [request.analysis_id], "c13.table"
            parameters = request.model_dump(exclude={"schema_version", "snapshot_id", "scope", "analysis_id"}, exclude_none=True)
        native = OperationRequest(
            snapshot_id=request.snapshot_id, scope=request.scope, operation_id=operation,
            operation_version="c13-v1", input_ids=identity, parameters=parameters,
            access_binding=catalogue_access_binding(user), access_revision=resolved.revision,
        )
        try:
            result = resolved.backend.query(native)
        except ValidationError:
            raise _error("invalid_request") from None
        except ValueError:
            raise _error("invalid_request") from None
        try:
            result = ScientificResponse.model_validate(result.model_dump(mode="json") if hasattr(result, "model_dump") else result)
        except ValueError:
            raise _error("catalogue_unavailable") from None
        if result.snapshot_id != native.snapshot_id or result.scope != native.scope or (
            result.receipt.operation_id, result.receipt.operation_version
        ) != (native.operation_id, native.operation_version):
            raise _error("catalogue_unavailable")
        return result.model_dump(mode="json")

    @staticmethod
    def _json(value, *, permitted_ids=None):
        if hasattr(value, "model_dump"):
            return CatalogueService._json(value.model_dump(mode="json"), permitted_ids=permitted_ids)
        if isinstance(value, Mapping):
            return {
                key: [identity for identity in child if isinstance(identity, str) and identity in permitted_ids]
                if key == "related_ids" and isinstance(child, (list, tuple)) and permitted_ids is not None
                else CatalogueService._json(child, permitted_ids=permitted_ids)
                for key, child in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [CatalogueService._json(child, permitted_ids=permitted_ids) for child in value]
        return value

    def _view(self, request, resolved, *, relation=None):
        key, base_key = None, None
        if resolved.cache_token is not None and self.maximum_cached_views:
            key = canonical_json({
                "token": resolved.cache_token,
                "request": request.model_dump(mode="json", exclude={"cursor"}),
                "relationship_of": relation,
            })
            base_key = canonical_json({
                "token": resolved.cache_token, "snapshot_id": request.snapshot_id,
                "scope": request.scope.model_dump(mode="json"),
                "binding": request.access_binding, "revision": request.access_revision,
            })
        # Only an explicit trusted immutable backend may opt into this cache.
        # The resolver has already rechecked current access on this call.
        with self._lock:
            if key is not None and key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            base = self._bases.get(base_key) if base_key is not None else None
            if base is not None:
                self._bases.move_to_end(base_key)
            elif base_key is not None:
                # A filtered view shares its base's node graph. Evict both
                # together, before allocating the next full graph, so bounded
                # base caching cannot retain an extra graph through _cache.
                while len(self._bases) >= self.maximum_cached_views:
                    self._evict_base()
        if base is None:
            base = self._materialize(request, resolved)
            if base_key is not None:
                with self._lock:
                    self._bases[base_key] = base
                    while len(self._bases) > self.maximum_cached_views:
                        self._evict_base()
        nodes, paths = base.nodes, base.paths
        if request.parent_id is not None and request.parent_id not in nodes:
            raise _error("not_found")
        f, selected = request.filters, []
        for node in nodes.values():
            if relation is not None:
                member = node.kind == "relationship" and (relation == node.id or relation in node.related_ids)
            elif request.parent_id is None:
                member = True
            elif f.search:
                member = request.parent_id in paths[node.id][1][:-1]
            else:
                member = node.parent_id == request.parent_id
            if not member or (f.roots and node.root not in f.roots) or (f.kinds and node.kind not in f.kinds) or (f.source_families and node.source_family not in f.source_families) or (f.authorities and node.authority not in f.authorities):
                continue
            if f.search and f.search.casefold() not in paths[node.id][0]:
                continue
            selected.append(node)
        view = _View(nodes, tuple(node.id for node in ordered_nodes(selected, request.ordering)))
        if key is not None:
            with self._lock:
                self._cache[key] = view
                while len(self._cache) > self.maximum_cached_views:
                    self._cache.popitem(last=False)
        return view

    def _evict_base(self):
        """Caller holds _lock; active requests retain their own valid graph."""
        _, base = self._bases.popitem(last=False)
        for key in [key for key, view in self._cache.items() if view.nodes is base.nodes]:
            del self._cache[key]

    def _materialize(self, request, resolved):
        try:
            retained_scope = EvidenceScope.model_validate(request.scope.model_dump(mode="json"))
            supplied = resolved.backend.view(request)
            if not isinstance(supplied, Mapping) or len(supplied) > MAX_NAVIGATION_OBJECTS:
                raise ValueError("Bounded complete permitted node map required")
            nodes, metadata = {}, {}
            for identity, node in supplied.items():
                node = CatalogueNode.model_validate(node.model_dump(mode="json") if hasattr(node, "model_dump") else node)
                if node.id != identity or node.snapshot_id != request.snapshot_id or node.scope != retained_scope or node.membership != "global":
                    raise ValueError("Catalogue view context mismatch")
                # Every node has just passed full wire validation and exact scope
                # equality. Keep the one private request scope instead of a full
                # nested scope graph per node. Responses are serialized copies;
                # neither the backend nor the caller receives this cached graph.
                node.scope = retained_scope
                # Repeated small scientific descriptors/lifecycle qualifiers are
                # also private validated values. Sharing their equal graph keeps
                # full inventories bounded without dropping any metadata. The
                # pool itself is bounded even when every description differs.
                for field in ("purpose", "availability", "lifecycle", "descriptor", "operations", "sections"):
                    value = getattr(node, field)
                    wire = self._json(value)
                    key = (field, canonical_json(wire))
                    retained = metadata.get(key)
                    if retained is not None:
                        setattr(node, field, retained)
                    elif len(metadata) < 1024:
                        metadata[key] = value
                nodes[identity] = node
            for node in nodes.values():
                node.related_ids = [key for key in node.related_ids if key in nodes]
            paths = self._paths(nodes)
        except CatalogueServiceError:
            raise
        except (SnapshotAccessDenied, SnapshotNotFound, AdapterAccessDenied, PermissionError):
            raise _error("not_found") from None
        except Exception:
            raise _error("catalogue_unavailable") from None
        return _BaseView(nodes, paths)

    @staticmethod
    def _paths(nodes):
        result = {}
        for identity in nodes:
            chain, current = [], identity
            while current is not None:
                if current in chain or len(chain) >= MAX_ANCESTRY_DEPTH or current not in nodes:
                    raise ValueError("Catalogue path is cyclic, incomplete or exceeds its bound")
                chain.append(current)
                current = nodes[current].parent_id
            chain.reverse()
            # Logical canonical ancestry only: never interpret filesystem paths.
            segments = (chain, [nodes[key].title.en for key in chain], [nodes[key].title.ja for key in chain])
            text = "\n".join(separator.join(parts) for parts in segments for separator in (" / ", "/")).casefold()
            result[identity] = text, chain
        return result

    @staticmethod
    def _page(view, request):
        offset = validate_cursor(request)
        if offset > len(view.ordered_ids):
            raise _error("invalid_cursor")
        selected = [view.nodes[i] for i in view.ordered_ids[offset:offset + request.limit]]
        following = offset + len(selected)
        cursor = make_cursor(request, following) if following < len(view.ordered_ids) else None
        return CatalogueListing(
            request=request, items=selected,
            total={"state": "known", "entity": "canonical_objects", "denominator": "Distinct permitted matching canonical objects across the complete frozen catalogue view", "value": len(view.ordered_ids)},
            returned_count=len(selected), next_cursor=cursor, preview_truncated=cursor is not None,
            source_completeness="complete", query_completion="complete", availability={"status": "available"},
        )
