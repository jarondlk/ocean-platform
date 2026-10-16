"""C13 scientific map over a sealed index and explicitly bound source snapshots.

The index's CTD carrier is storage metadata. Scientific source membership comes
only from validated child bindings and their current source-adapter policies.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
from typing import Callable
from types import SimpleNamespace

import pyarrow.parquet as pq
from pydantic import Field, TypeAdapter

from ingestion.scientific_catalogue_inputs import (
    AdapterUnavailable,
    MAX_DECODED_BYTES,
    MAX_ROWS,
    load_registry,
    _decoded_size,
)
from ingestion.catalogue_adapter_inputs import dataset_metadata as _ctd_metadata
from ingestion.sst_catalogue_inputs import dataset_metadata as _sst_metadata
from ingestion.edna_catalogue_inputs import dataset_metadata as _edna_metadata
from orchestration.frozen_catalogue import AdapterAccessDenied, FrozenCatalogueAdapter
from orchestration.publication_scope import publication_compatibility
from orchestration.research_intents import QUESTIONS, SST_INTENTS
from preprocessing.scientific_catalogue_relationships import validate_relationship
from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.catalogue_snapshot import MAX_BYTES
from schema.context_catalogue import (
    CatalogueCount,
    CatalogueNode,
    ContractModel,
    Identifier,
    ListingRequest,
    NonnegativeInt,
    OperationRequest,
    PageLimit,
    canonical_json,
)
from schema.scientific_catalogue import ADAPTER_VERSION, ScientificResponse

OPERATIONS = (
    "c13.table",
    "c13.inventory",
    "c13.coverage",
    "c13.quality",
    "c13.operation",
)
_identifier = TypeAdapter(Identifier)


def _operations(*operations):
    return [
        {
            "id": operation,
            "version": ADAPTER_VERSION,
            "kind": "inventory" if operation == "c13.inventory" else "descriptive",
            "required_permission": "catalogue.read",
            "availability": {"status": "available"},
        }
        for operation in operations
    ]


def _source_operations(family):
    values = _operations(
        "c13.inventory", "c13.coverage", "c13.quality", "c13.operation"
    )
    if family in {"ctd", "metagenome"}:
        values[2]["availability"] = {
            "status": "unavailable",
            "reason": "No registered source quality operation; retained quality metadata remains inspectable",
        }
    return values


@dataclass(frozen=True)
class ScientificAccess:
    binding: str
    revision: str
    eligible: Callable[[str, object], bool]

    def __post_init__(self):
        _identifier.validate_python(self.binding)
        _identifier.validate_python(self.revision)
        if not callable(self.eligible):
            raise ValueError("Current scientific object access policy required")


class Parameters(ContractModel):
    table: Identifier | None = None
    limit: PageLimit = 100
    offset: NonnegativeInt = 0
    operation_id: Identifier | None = None
    operation_version: Identifier | None = None
    parameters: dict = Field(default_factory=dict)
    workflow_kind: Identifier | None = None
    protocol_id: Identifier | None = None


@dataclass
class _Context:
    registry: object
    nodes: dict
    associations: dict
    data: dict
    bindings: dict
    adapters: dict
    requests: dict
    analyses: dict
    records: dict
    relationships: dict


def _id(kind, identity):
    return f"c13:{kind}:" + hashlib.sha256(identity.encode()).hexdigest()


def _single_scope(scope, family):
    value = scope.model_dump(mode="json")
    for name in FAMILIES:
        if name != family:
            value["sources"][name] = {"enabled": False, "filters": {}}
    return EvidenceScope.model_validate(value)


def _request(request, binding):
    return ListingRequest(
        snapshot_id=binding.snapshot_id,
        scope=_single_scope(request.scope, binding.source_family),
        access_binding=request.access_binding,
        access_revision=request.access_revision,
    )


def _eligible(policy, snapshot, item):
    detached = type(item).model_validate(item.model_dump(mode="json"))
    return policy(snapshot, detached) is True


def _filters_present(scope):
    return any(
        getattr(scope.sources, family).filters.model_dump(exclude_none=True)
        or getattr(getattr(scope.sources, family), "analysis_id", None)
        for family in FAMILIES
    )


class FrozenScientificCatalogueAdapter(FrozenCatalogueAdapter):
    """C08 transport with source-owned scientific input and policy validation."""

    def __init__(self, *, store, adapters, access: ScientificAccess):
        if set(adapters) - set(FAMILIES):
            raise ValueError("Only explicit canonical source adapters are supported")
        self.store, self.adapters, self.access = store, dict(adapters), access

    def _load(self, request):
        if (request.access_binding, request.access_revision) != (
            self.access.binding,
            self.access.revision,
        ):
            raise AdapterAccessDenied("Current scientific access context mismatch")
        manifest, contents = self.store.read(request.snapshot_id)
        registry = load_registry(manifest, contents)
        # All identities, including denied records and source artifacts, enter one
        # namespace before policy decisions can omit anything from inventory.
        owners = {
            f"root:{root}": ("root", root)
            for root in ("data", "analyses", "statistics", "metadata", "relationships")
        }

        def reserve(identity, owner):
            if identity in owners and owners[identity] != owner:
                raise ValueError("Scientific/source canonical identities collide")
            owners[identity] = owner

        bindings = {item.dataset_id: item for item in registry.metadata.datasets}
        for item in registry.metadata.datasets:
            if item.snapshot_id == request.snapshot_id:
                raise ValueError(
                    "Scientific index cannot reference itself as a raw source"
                )
            reserve(item.dataset_id, ("dataset", item.source_family, item.source_id))
            for kind in ("statistics", "metadata"):
                reserve(_id(kind, item.dataset_id), (kind, item.dataset_id))
        for item in (
            *registry.metadata.analyses,
            *registry.metadata.workflows,
            *registry.metadata.definitions,
            *registry.metadata.relationships,
        ):
            reserve(item.id, ("scientific", item.id))
        for analysis in registry.metadata.analyses:
            reserve(_id("history", analysis.id), ("history", analysis.id))
            for table in analysis.tables:
                if table.object_id is not None:
                    reserve(table.object_id, ("result_table", analysis.id))
        for obj in registry.objects:
            if obj.role == "scientific_registry":
                reserve(obj.object_id, ("index",))

        child_snapshots = {}
        rows = sum(len(value) for value in registry.tables.values())
        decoded = _decoded_size(registry.tables)
        encoded = sum(obj.size_bytes for obj in manifest.objects)
        for binding in registry.metadata.datasets:
            adapter = self.adapters.get(binding.source_family)
            if adapter is None:
                raise AdapterUnavailable(
                    "A bound scientific input source adapter is unavailable"
                )
            if (adapter.access.binding, adapter.access.revision) != (
                self.access.binding,
                self.access.revision,
            ):
                raise AdapterAccessDenied("Current source access context mismatch")
            key = (id(adapter.store), binding.snapshot_id)
            if key not in child_snapshots:
                child, payloads = adapter.store.read(binding.snapshot_id)
                if _filters_present(child.scope):
                    raise AdapterUnavailable(
                        "Scientific source bindings require whole-source snapshots"
                    )
                encoded += sum(obj.size_bytes for obj in child.objects)
                if encoded > MAX_BYTES:
                    raise ValueError(
                        "C13 complete index/source encoded budget exceeded"
                    )
                for obj in child.objects:
                    reserve(
                        obj.dataset_id, ("dataset", obj.source_family, obj.source_id)
                    )
                    reserve(obj.object_id, ("source_object", obj.dataset_id))
                    if obj.schema_version in {
                        "catalogue-parquet-v1",
                        "catalogue-sst-parquet-v1",
                        "catalogue-edna-parquet-v1",
                    }:
                        footer = pq.ParquetFile(
                            BytesIO(payloads[obj.object_id])
                        ).metadata
                        rows += footer.num_rows
                        decoded += sum(
                            footer.row_group(i).total_byte_size
                            for i in range(footer.num_row_groups)
                        )
                        if rows > MAX_ROWS or decoded > MAX_DECODED_BYTES:
                            raise ValueError(
                                "C13 complete source decode budget exceeded"
                            )
                # Validate the complete source hierarchy namespace using only
                # typed metadata before any source or scientific callback.
                for obj in child.objects:
                    parser = {
                        "catalogue-dataset-v1": _ctd_metadata,
                        "catalogue-sst-dataset-v1": _sst_metadata,
                        "catalogue-edna-dataset-v1": _edna_metadata,
                    }.get(obj.schema_version)
                    if parser is None:
                        continue
                    metadata = parser(payloads[obj.object_id])
                    source_objects = tuple(
                        item
                        for item in child.objects
                        if item.dataset_id == obj.dataset_id
                    )
                    dummy = SimpleNamespace(
                        metadata=metadata, objects=source_objects, tables={}
                    )
                    pure_request = ListingRequest(
                        snapshot_id=binding.snapshot_id,
                        scope=_single_scope(child.scope, obj.source_family),
                        access_binding=request.access_binding,
                        access_revision=request.access_revision,
                    )
                    native_adapter = self.adapters.get(obj.source_family, adapter)
                    for node in native_adapter._nodes(
                        {obj.dataset_id: dummy}, pure_request
                    ).values():
                        if (
                            node.kind == "root"
                            or node.id == obj.dataset_id
                            or any(item.object_id == node.id for item in source_objects)
                        ):
                            continue
                        reserve(
                            node.id,
                            (
                                "source_hierarchy",
                                obj.source_id,
                                node.kind,
                                node.parent_id,
                            ),
                        )
                child_snapshots[key] = child
            child = child_snapshots[key]
            matching = [
                obj for obj in child.objects if obj.dataset_id == binding.dataset_id
            ]
            if not matching or any(
                (obj.source_id, obj.source_family)
                != (binding.source_id, binding.source_family)
                for obj in matching
            ):
                raise ValueError("Frozen scientific dataset/source binding mismatch")

        loaded, data, requests, selected_adapters = {}, {}, {}, {}
        for binding in registry.metadata.datasets:
            adapter = self.adapters[binding.source_family]
            native = _request(request, binding)
            # Disabled sources remain denied; the carrier cannot enable them.
            if not getattr(request.scope.sources, binding.source_family).enabled:
                continue
            key = (id(adapter), binding.snapshot_id)
            if key not in loaded:
                loaded[key] = adapter._load(native)
            selected = adapter._membership(loaded[key], native.scope)
            value = selected.get(binding.dataset_id)
            if value is not None:
                data[binding.dataset_id] = value
                requests[binding.dataset_id] = native
                selected_adapters[binding.dataset_id] = adapter
        actual = sum(
            frame.attrs.get("decoded_bytes", 0)
            for values in loaded.values()
            for value in values.values()
            for frame in value.tables.values()
        )
        if actual + _decoded_size(registry.tables) > MAX_DECODED_BYTES:
            raise ValueError("C13 actual complete source decode budget exceeded")
        # Scientific decisions require every declared input. No partial input
        # set can silently stand in for a published result or a relationship.
        visible = {}
        for item in (
            *registry.metadata.analyses,
            *registry.metadata.workflows,
            *registry.metadata.definitions,
            *registry.metadata.relationships,
        ):
            if set(item.input_dataset_ids) <= set(data) and _eligible(
                self.access.eligible, request.snapshot_id, item
            ):
                visible[item.id] = item
        relationships = {
            item.id: validate_relationship(item, data)
            for item in registry.metadata.relationships
            if item.id in visible
        }
        analyses = {
            item.id: item
            for item in registry.metadata.analyses
            if item.id in visible
            and item.publication_status == "published"
            and registry.eligibility[item.id].eligible
        }
        context = _Context(
            registry,
            {},
            {},
            data,
            bindings,
            selected_adapters,
            requests,
            analyses,
            visible,
            relationships,
        )
        self._build_nodes(context, request)
        return context

    @staticmethod
    def _membership(context, scope):
        return context

    @staticmethod
    def _nodes(context, request):
        return context.nodes

    @staticmethod
    def _build_nodes(context, request):
        nodes, associations = context.nodes, context.associations

        def add(
            identity,
            kind,
            root,
            parent,
            title,
            *,
            purpose=None,
            authority="descriptive",
            publication="unpublished",
            availability=None,
            provenance=None,
            inputs=(),
            operations=(),
        ):
            if identity in nodes:
                raise ValueError("Scientific catalogue node identities collide")
            nodes[identity] = CatalogueNode.model_validate(
                {
                    "snapshot_id": request.snapshot_id,
                    "scope": request.scope,
                    "id": identity,
                    "kind": kind,
                    "root": root,
                    "parent_id": parent,
                    "title": title,
                    "purpose": purpose or title,
                    "availability": availability or {"status": "available"},
                    "authority": authority,
                    "lifecycle": {
                        "ingestion": "complete",
                        "publication": publication,
                        "scientific_approval": "not_reviewed",
                        "query_readiness": "ready",
                        "embedding_readiness": "unknown",
                    },
                    "provenance": provenance or {},
                    "related_ids": sorted(set(inputs)),
                    "operations": list(operations) or _operations("c13.inventory")
                    if kind in {"root", "directory"}
                    else list(operations),
                }
            )
            associations[identity] = set(inputs)

        for root in ("data", "analyses", "statistics", "metadata", "relationships"):
            add(f"root:{root}", "root", root, None, {"en": root, "ja": root})
        # Reuse validated Data hierarchy nodes; relabel only envelope scope and
        # snapshot, retaining the exact child binding for inspection and receipts.
        groups = {}
        for identity, value in context.data.items():
            key = (
                id(context.adapters[identity]),
                context.bindings[identity].snapshot_id,
                context.bindings[identity].source_family,
            )
            groups.setdefault(key, []).append(identity)
        for ids in groups.values():
            first = ids[0]
            native_nodes = context.adapters[first]._nodes(
                {identity: context.data[identity] for identity in ids},
                context.requests[first],
            )
            for identity, node in native_nodes.items():
                if node.root != "data" or node.kind == "root":
                    continue
                if identity in nodes:
                    existing = nodes[identity]
                    if (
                        existing.kind != node.kind
                        or existing.parent_id != node.parent_id
                    ):
                        raise ValueError("Canonical source hierarchy nodes collide")
                    continue
                payload = node.model_dump(mode="json")
                payload.update(
                    snapshot_id=request.snapshot_id,
                    scope=request.scope.model_dump(mode="json"),
                    related_ids=[],
                    operations=_source_operations(
                        context.bindings[identity].source_family
                    )
                    if node.kind == "dataset"
                    else _operations("c13.inventory")
                    if node.kind == "directory"
                    else [],
                )
                nodes[identity] = CatalogueNode.model_validate(payload)
                associations[identity] = {identity} if node.kind == "dataset" else set()
        for identity, data in context.data.items():
            node = nodes[identity]
            for root in ("statistics", "metadata"):
                ref = _id(root, identity)
                add(
                    ref,
                    "statistic" if root == "statistics" else "metadata",
                    root,
                    f"root:{root}",
                    node.title,
                    inputs=[identity],
                    provenance=node.provenance.model_dump(mode="json"),
                    operations=_source_operations(
                        context.bindings[identity].source_family
                    )
                    if root == "statistics"
                    else [],
                )
                nodes[identity].related_ids.append(ref)
        for analysis in context.registry.metadata.analyses:
            if (
                analysis.id not in context.records
                or analysis.publication_status not in {"published", "historical"}
            ):
                continue
            history = _id("history", analysis.id)
            add(
                history,
                "reference",
                "metadata",
                "root:metadata",
                analysis.title,
                purpose=analysis.purpose,
                inputs=analysis.input_dataset_ids,
                provenance=analysis.provenance.model_dump(mode="json"),
            )
            if analysis.id not in context.analyses:
                continue
            add(
                analysis.id,
                "analysis",
                "analyses",
                "root:analyses",
                analysis.title,
                purpose=analysis.purpose,
                authority="published",
                publication="published",
                availability=analysis.availability,
                provenance=analysis.provenance.model_dump(mode="json"),
                inputs=analysis.input_dataset_ids,
                operations=_operations("c13.table"),
            )
            for table in analysis.tables:
                identity = table.object_id or _id(
                    "absent_table", analysis.id + ":" + table.name
                )
                add(
                    identity,
                    "table",
                    "analyses",
                    analysis.id,
                    {"en": table.name, "ja": table.name},
                    authority="published",
                    publication="published",
                    availability=table.availability,
                    inputs=analysis.input_dataset_ids,
                    provenance=analysis.provenance.model_dump(mode="json"),
                    operations=_operations("c13.table"),
                )
        for workflow in context.registry.metadata.workflows:
            if workflow.id not in context.records:
                continue
            if any(
                not getattr(request.scope.sources, family).enabled
                for family in workflow.required_sources
            ):
                continue
            add(
                workflow.id,
                "workflow",
                "analyses",
                "root:analyses",
                workflow.title,
                purpose=workflow.purpose,
                availability=workflow.availability,
                inputs=workflow.input_dataset_ids,
                provenance=workflow.provenance.model_dump(mode="json"),
            )
        for definition in context.registry.metadata.definitions:
            if definition.id in context.records:
                add(
                    definition.id,
                    "metadata",
                    "metadata",
                    "root:metadata",
                    definition.title,
                    purpose=definition.purpose,
                    inputs=definition.input_dataset_ids,
                    provenance=definition.provenance.model_dump(mode="json"),
                )
        for relationship in context.registry.metadata.relationships:
            if relationship.id in context.relationships:
                add(
                    relationship.id,
                    "relationship",
                    "relationships",
                    "root:relationships",
                    relationship.title,
                    purpose=relationship.purpose,
                    inputs=relationship.input_dataset_ids,
                    provenance=relationship.provenance.model_dump(mode="json"),
                )
        for identity, node in nodes.items():
            node.related_ids = [key for key in node.related_ids if key in nodes]

    def dataset_count(self, request):
        request = ListingRequest.model_validate(
            request.model_dump(mode="json")
            if isinstance(request, ListingRequest)
            else request
        )
        context = self._load(request)
        identities = self._descendant_datasets(context, request)
        return CatalogueCount(
            state="known",
            entity="datasets",
            value=len(identities),
            denominator="Distinct permitted canonical input datasets across all matching scientific descendants and links",
        )

    @staticmethod
    def _descendant_datasets(context, request):
        if request.parent_id is not None and request.parent_id not in context.nodes:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        result = set()
        f = request.filters
        for node in context.nodes.values():
            current = node.id
            visited = set()
            descendant = request.parent_id is None
            while current is not None:
                if current in visited:
                    raise ValueError("Scientific hierarchy cycle")
                visited.add(current)
                if current == request.parent_id:
                    descendant = True
                    break
                current = context.nodes[current].parent_id
            if (
                not descendant
                or (f.roots and node.root not in f.roots)
                or (f.kinds and node.kind not in f.kinds)
                or (f.authorities and node.authority not in f.authorities)
            ):
                continue
            if (
                f.search
                and f.search.casefold()
                not in (node.id + " " + node.title.en + " " + node.title.ja).casefold()
            ):
                continue
            ids = context.associations[node.id]
            if f.source_families:
                ids = {
                    identity
                    for identity in ids
                    if context.bindings[identity].source_family in f.source_families
                }
            result.update(ids)
        return result

    def query(self, request):
        request = OperationRequest.model_validate(
            request.model_dump(mode="json")
            if isinstance(request, OperationRequest)
            else request
        )
        if (
            request.operation_id not in OPERATIONS
            or request.operation_version != ADAPTER_VERSION
            or len(request.input_ids) != 1
        ):
            raise ValueError(
                "C13 requires one scientific identity and a supported versioned operation"
            )
        params = Parameters.model_validate(request.parameters)
        context = self._load(request)
        identity = request.input_ids[0]
        if identity not in context.nodes:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        try:
            if request.operation_id == "c13.table":
                if params.operation_id or params.operation_version or params.parameters:
                    raise ValueError(
                        "Published table reads cannot execute a source operation"
                    )
                analysis = context.analyses.get(identity)
                if analysis is None:
                    analysis = next(
                        (
                            a
                            for a in context.analyses.values()
                            if any(t.object_id == identity for t in a.tables)
                        ),
                        None,
                    )
                if analysis is None:
                    raise AdapterUnavailable(
                        "This catalogue object is a description, not a published result table"
                    )
                if request.scope.canonical() != analysis.scope.canonical():
                    raise AdapterUnavailable(
                        "Immutable published tables require their exact frozen source scope; subcohorts cannot inherit published findings"
                    )
                compatibility = None
                if analysis.scope_option is not None:
                    kinds = {
                        w.workflow_kind
                        for w in context.registry.metadata.workflows
                        if analysis.id in w.analysis_ids
                    }
                    if (
                        params.workflow_kind not in kinds
                        or params.workflow_kind not in QUESTIONS
                    ):
                        raise AdapterUnavailable(
                            "Select an explicitly registered immutable publication workflow"
                        )
                    required = {"edna_metabarcoding"}
                    if params.workflow_kind in SST_INTENTS:
                        required.add("remote_sensing")
                    actual = {
                        context.bindings[key].source_family
                        for key in analysis.input_dataset_ids
                    }
                    if not required <= actual:
                        raise AdapterUnavailable(
                            "Published workflow lacks its required frozen scientific input sources"
                        )
                    compatible = publication_compatibility(
                        QUESTIONS[params.workflow_kind][0],
                        params.workflow_kind,
                        analysis.scope_option,
                        protocol_id=params.protocol_id,
                        scope=request.scope.canonical(),
                    )
                    if compatible.outcome != "compatible":
                        raise AdapterUnavailable(compatible.reason)
                    compatibility = compatible.as_dict()
                tables = [
                    t
                    for t in analysis.tables
                    if (params.table is None or t.name == params.table)
                    and (identity == analysis.id or t.object_id == identity)
                ]
                if len(tables) != 1:
                    raise ValueError("Select one retained published result table")
                table = tables[0]
                if (
                    analysis.availability.status != "available"
                    or table.object_id is None
                ):
                    raise AdapterUnavailable("Published result bytes are unavailable")
                return self._response(
                    context,
                    request,
                    params,
                    table.columns,
                    context.registry.tables[table.object_id],
                    table.completeness,
                    authority="published",
                    inputs=analysis.input_dataset_ids,
                    table_ids=[table.object_id],
                    scope_compatibility=compatibility,
                    qualifications=[
                        *analysis.limitations,
                        f"Analysis method: {analysis.method_id}/{analysis.method_version}",
                        analysis.approval_basis,
                        "Published status is separate from independent scientific approval or provider endorsement",
                    ],
                )
            if request.operation_id == "c13.inventory":
                if (
                    any(
                        (
                            params.table,
                            params.operation_id,
                            params.operation_version,
                            params.parameters,
                            params.workflow_kind,
                            params.protocol_id,
                        )
                    )
                    or params.offset
                ):
                    raise ValueError(
                        "Inventory counts require only a descendant identity and preview limit"
                    )
                listing = ListingRequest(
                    snapshot_id=request.snapshot_id,
                    scope=request.scope,
                    parent_id=identity,
                    access_binding=request.access_binding,
                    access_revision=request.access_revision,
                )
                ids = self._descendant_datasets(context, listing)
                rows = [
                    {
                        "entity": "datasets",
                        "count": len(ids),
                        "denominator": "Distinct permitted canonical input datasets across complete matching descendants and cross-root links",
                    }
                ]
                return self._response(
                    context, request, params, None, rows, "complete", inputs=ids
                )
            return self._delegate(context, request, params, identity)
        except AdapterUnavailable as exc:
            return self._response(
                context, request, params, [], [], "unavailable", reason=str(exc)
            )

    def _delegate(self, context, request, params, identity):
        if identity not in context.data:
            identity = next(
                (key for key in context.data if _id("statistics", key) == identity),
                identity,
            )
        if identity not in context.data:
            raise AdapterUnavailable(
                "Source operations require a canonical input dataset"
            )
        family = context.bindings[identity].source_family
        if params.workflow_kind or params.protocol_id or params.table:
            raise ValueError(
                "Source operation parameters belong in the explicit parameters object"
            )
        native_params = dict(params.parameters)
        if {"limit", "offset"} & set(native_params):
            raise ValueError("Native source paging uses the C13 limit and offset")
        native_params.update(limit=params.limit, offset=params.offset)
        if request.operation_id == "c13.operation":
            operation, version = params.operation_id, params.operation_version
            if operation is None or version is None:
                raise ValueError(
                    "A source operation requires its explicit operation ID and version"
                )
        else:
            if params.operation_id or params.operation_version:
                raise ValueError(
                    "Named source views select their registered source operation"
                )
            prefix = (
                "c10"
                if family in {"ctd", "metagenome"}
                else "c11"
                if family == "remote_sensing"
                else "c12"
            )
            if request.operation_id == "c13.quality" and prefix == "c10":
                raise AdapterUnavailable(
                    "No registered CTD/metagenome quality operation; retained quality metadata remains inspectable"
                )
            operation = prefix + (
                ".coverage" if request.operation_id == "c13.coverage" else ".count"
            )
            version = prefix + "-v1"
            if request.operation_id == "c13.quality" and prefix == "c12":
                native_params.setdefault("population", "raw")
        native = OperationRequest(
            snapshot_id=context.bindings[identity].snapshot_id,
            scope=context.requests[identity].scope,
            operation_id=operation,
            operation_version=version,
            input_ids=[identity],
            parameters=native_params,
            access_binding=request.access_binding,
            access_revision=request.access_revision,
        )
        value = context.adapters[identity].query(native)
        result = value.result if hasattr(value, "result") else value
        # Preserve the native full-population hash/count and receipt separately;
        # only the source adapter can define scientific aggregation or scope.
        receipt = result.receipt.model_dump(mode="json")
        receipt.update(
            snapshot_id=request.snapshot_id,
            scope=request.scope.model_dump(mode="json"),
            operation_id=request.operation_id,
            operation_version=ADAPTER_VERSION,
            parameters=params.model_dump(mode="json"),
            inputs=self._inputs(context, [identity]),
            provenance={
                "references": [
                    "Exact delegated source receipt: " + result.receipt.receipt_id,
                    "Native operation: " + operation + "/" + version,
                ]
            },
        )
        receipt["receipt_id"] = (
            "c13:receipt:"
            + hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
        )
        return ScientificResponse.model_validate(
            {
                "snapshot_id": request.snapshot_id,
                "scope": request.scope,
                "columns": result.columns,
                "rows": result.rows,
                "receipt": receipt,
                "offset": value.offset,
                "next_offset": value.next_offset
                if operation
                in {
                    "c10.table",
                    "c10.coverage",
                    "c11.table",
                    "c11.grid_points",
                    "c12.table",
                }
                else None,
                "qualifications": [
                    *value.qualifications,
                    "Source operation "
                    + operation
                    + "/"
                    + version
                    + "; original snapshot "
                    + native.snapshot_id,
                ],
            }
        )

    @staticmethod
    def _inputs(context, ids, table_ids=()):
        return [
            {
                "object_id": obj.object_id,
                "content_sha256": obj.sha256,
                "source_generation": obj.provenance.source_generation,
            }
            for obj in context.registry.objects
            if obj.role == "scientific_registry" or obj.object_id in table_ids
        ] + [
            {
                "object_id": _id("input", identity),
                "content_sha256": context.bindings[identity].snapshot_id,
            }
            for identity in sorted(set(ids))
        ]

    @classmethod
    def _response(
        cls,
        context,
        request,
        params,
        columns,
        rows,
        completeness,
        *,
        authority="descriptive",
        inputs=(),
        table_ids=(),
        scope_compatibility=None,
        qualifications=(),
        reason=None,
    ):
        if params.offset > len(rows) and reason is None:
            raise ValueError("Offset exceeds complete scientific result")
        if columns is None:
            columns = [
                {"key": key, "title": {"en": key, "ja": key}}
                for key in (rows[0] if rows else [])
            ]
        column_values = [
            c.model_dump(mode="json") if hasattr(c, "model_dump") else c
            for c in columns
        ]
        selected = rows[params.offset : params.offset + params.limit]
        known = completeness == "complete"
        receipt = {
            "snapshot_id": request.snapshot_id,
            "scope": request.scope.model_dump(mode="json"),
            "operation_id": request.operation_id,
            "operation_version": ADAPTER_VERSION,
            "parameters": params.model_dump(mode="json"),
            "scope_compatibility": scope_compatibility,
            "inputs": cls._inputs(context, inputs, table_ids),
            "authority": authority,
            "availability": {"status": "available"}
            if reason is None
            else {"status": "unavailable", "reason": reason},
            "provenance": {"references": [context.registry.metadata.qualification]},
            "total_rows": {
                "state": "known",
                "entity": "rows",
                "denominator": "Complete scoped scientific operation output rows",
                "value": len(rows),
            }
            if known
            else {
                "state": "unknown",
                "entity": "rows",
                "denominator": "Complete scoped scientific operation output rows",
                "reason": reason or "Retained result completeness is not established",
            },
            "returned_count": len(selected),
            "preview_truncated": len(selected) < len(rows),
            "source_completeness": completeness,
            "query_completion": "not_started"
            if reason
            else "complete"
            if known
            else "partial",
            "content_sha256": hashlib.sha256(
                canonical_json({"columns": column_values, "rows": rows}).encode()
            ).hexdigest(),
        }
        receipt["receipt_id"] = (
            "c13:receipt:"
            + hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
        )
        return ScientificResponse.model_validate(
            {
                "snapshot_id": request.snapshot_id,
                "scope": request.scope,
                "columns": columns,
                "rows": selected,
                "receipt": receipt,
                "offset": params.offset,
                "next_offset": params.offset + len(selected)
                if params.offset + len(selected) < len(rows)
                else None,
                "qualifications": [
                    context.registry.metadata.qualification,
                    *qualifications,
                    "Descriptive operations do not execute experiments or grant scientific approval; current access applies to every frozen input",
                ],
            }
        )

    def inspect(self, identity, request):
        request = ListingRequest.model_validate(
            request.model_dump(mode="json")
            if isinstance(request, ListingRequest)
            else request
        )
        context = self._load(request)
        if identity not in context.nodes:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        node = context.nodes[identity]
        if identity in context.data:
            value = context.adapters[identity].inspect(
                identity, context.requests[identity]
            )
            return {
                **value,
                "node": node,
                "source_operations": [
                    operation.model_dump(mode="json")
                    for operation in value["node"].operations
                ],
                "snapshot_binding": context.bindings[identity].model_dump(mode="json"),
            }
        if identity in context.relationships:
            return {
                "node": node,
                "relationship": context.records[identity].model_dump(mode="json"),
                "qualification": context.relationships[identity],
            }
        if identity in context.records:
            record = context.records[identity].model_dump(mode="json")
            if "analysis_ids" in record:
                record["analysis_ids"] = [
                    key for key in record["analysis_ids"] if key in context.analyses
                ]
            return {"node": node, "record": record}
        for analysis in context.registry.metadata.analyses:
            if identity == _id("history", analysis.id):
                return {
                    "node": node,
                    "record": analysis.model_dump(mode="json"),
                    "eligibility": context.registry.eligibility[analysis.id].as_dict(),
                }
        for dataset_id, data in context.data.items():
            if identity in {_id("metadata", dataset_id), _id("statistics", dataset_id)}:
                return {
                    "node": node,
                    "dataset": dataset_id,
                    "metadata": data.metadata.model_dump(mode="json"),
                    "source_operations": [
                        operation.model_dump(mode="json")
                        for operation in context.adapters[dataset_id]
                        ._nodes({dataset_id: data}, context.requests[dataset_id])[
                            dataset_id
                        ]
                        .operations
                    ],
                    "snapshot_binding": context.bindings[dataset_id].model_dump(
                        mode="json"
                    ),
                    "provenance": [obj.model_dump(mode="json") for obj in data.objects],
                }
        return {"node": node}
