"""C12 bounded, qualified operations over explicit immutable canonical eDNA.

C08 listing transport is reused; scientific selection uses the same relational
predicate plan as the canonical SQL service and the shared C01 eligibility rule.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
from typing import Callable, Literal

import pandas as pd
import pyarrow.parquet as pq
from pydantic import Field, TypeAdapter

from ingestion.edna_catalogue_inputs import (
    MAX_DECODED_BYTES,
    MAX_ROWS,
    AdapterUnavailable,
    load_dataset,
    parse_community_availability,
)
from orchestration.frozen_catalogue import AdapterAccessDenied, FrozenCatalogueAdapter
from preprocessing.edna_catalogue_query import (
    QueryUnavailable,
    normalize_filters,
    select_rows,
)
from preprocessing.edna_eligibility import (
    PROTOCOL_FIELDS,
    evaluate_analysis_eligibility,
)
from retrieval.source_scope import FAMILIES
from schema.context_catalogue import (
    DATASET_SECTIONS,
    CatalogueNode,
    ContractModel,
    Identifier,
    ListingRequest,
    NonnegativeInt,
    OperationRequest,
    PageLimit,
    TextValue,
    _finite_json,
    canonical_json,
)
from schema.edna_catalogue import ADAPTER_VERSION, DATASET_VERSION, RAW_METHODS
from schema.edna_catalogue import EDNADataset, EDNAResponse, ROLES, TABLE_VERSION

OPERATIONS = ("c12.table", "c12.count", "c12.summary", "c12.coverage", "c12.frequency")
SCIENTIFIC_METHODS = ("qcauto_target", "qcauto_95pct_3nn_target")
ELIGIBILITY_DEFINITION = "C01 environmental false-control, active complete-protocol assay and source-backed supported method (retained active detections or explicit available source table); preprocessing.edna_eligibility.evaluate_analysis_eligibility"
KEYS = {
    "occurrences": "sample_id",
    "classifications": "sample_id",
    "assays": "assay_id",
    "detections": "detection_id",
}
_identifier = TypeAdapter(Identifier)


@dataclass(frozen=True)
class EDNAAccess:
    """Trusted current whole-dataset access and scientific eligibility decision."""

    binding: str
    revision: str
    eligible: Callable[[str, EDNADataset], bool]

    def __post_init__(self):
        _identifier.validate_python(self.binding)
        _identifier.validate_python(self.revision)
        if not callable(self.eligible):
            raise ValueError(
                "Current eDNA dataset access/eligibility callback required"
            )


class Parameters(ContractModel):
    limit: PageLimit = 100
    offset: NonnegativeInt = 0
    population: Literal["raw", "eligible"] = "eligible"
    table: Literal["occurrences", "assays", "detections", "classifications"] = (
        "occurrences"
    )
    filters: dict = Field(default_factory=dict)
    target_gene: TextValue | None = None
    primer_set: TextValue | None = None
    sequencing_method: TextValue | None = None
    frequency_unit: Literal["source_occurrences", "assays"] = "source_occurrences"


def _group_id(kind, values):
    return f"c12:{kind}:" + hashlib.sha256(canonical_json(values).encode()).hexdigest()


def _reference_id(root, identity):
    return _group_id("reference", [root, identity])


def _groups(metadata):
    source = _group_id("source", [metadata.source_id])
    provider = _group_id(
        "provider",
        [
            metadata.source_id,
            metadata.provider,
            metadata.provider_locus,
            metadata.provider_team,
        ],
    )
    project = _group_id(
        "project",
        [
            metadata.source_id,
            metadata.provider,
            metadata.provider_locus,
            metadata.provider_team,
            metadata.provider_project_id,
        ],
    )
    return source, provider, project


def _table_id(metadata, spec):
    return spec.object_id or f"{metadata.dataset_id}:unavailable:{spec.name}"


def _register_identities(owners, data):
    m = data.metadata
    source, provider, project = _groups(m)
    entries = [
        (source, ("source", m.source_id)),
        (
            provider,
            ("provider", m.source_id, m.provider, m.provider_locus, m.provider_team),
        ),
        (project, ("project", provider, m.provider_project_id)),
        (m.collection_id, ("collection", m.source_id, project)),
        (m.dataset_id, ("dataset", m.source_id, m.collection_id)),
    ]
    entries += [
        (_table_id(m, spec), ("table", m.source_id, m.dataset_id, spec.name))
        for spec in m.tables
    ]
    entries += [
        (obj.object_id, ("artifact", m.source_id, m.dataset_id, obj.role))
        for obj in data.objects
        if obj.schema_version != TABLE_VERSION
    ]
    entries += [
        (_reference_id(root, m.dataset_id), ("reference", root, m.dataset_id))
        for root in ("statistics", "metadata")
    ]
    for identity, owner in entries:
        _identifier.validate_python(identity)
        if identity in owners and owners[identity] != owner:
            raise ValueError(
                "Canonical eDNA source/project/dataset/table/artifact identities collide"
            )
        owners[identity] = owner


def _filters(scope, params):
    pinned = scope.sources.edna_metabarcoding.filters.model_dump(exclude_none=True)
    dataset_id = pinned.pop("dataset_id", None)
    extra = normalize_filters(params.filters)
    # Scalar conflicts are never silently overridden. Bound intersections may
    # narrow the shared scope; the final range is revalidated below.
    for key, value in extra.items():
        if key in pinned and pinned[key] != value:
            if key.endswith("_min"):
                value = max(pinned[key], value)
            elif key.endswith("_max"):
                value = min(pinned[key], value)
            else:
                raise AdapterUnavailable(
                    "Operation filters conflict with the frozen request scope"
                )
        pinned[key] = value
    return dataset_id, normalize_filters(pinned)


def _select(data, scope, params, *, denominator=False):
    if not scope.sources.edna_metabarcoding.enabled:
        raise AdapterUnavailable("Requested eDNA source is disabled")
    dataset_id, filters = _filters(scope, params)
    if set(data.tables) != set(ROLES):
        raise AdapterUnavailable(
            "Relational selection requires retained occurrence, classification, assay and detection tables"
        )
    if denominator:
        filters.pop("taxon", None)
    tables = {key: frame.copy() for key, frame in data.tables.items()}
    if dataset_id is not None and dataset_id != data.metadata.dataset_id:
        tables = {key: frame.iloc[:0] for key, frame in tables.items()}
    if params.population == "eligible":
        if (
            filters.get("assignment_method") not in (*SCIENTIFIC_METHODS, None)
            or filters.get("target_status") == "nontarget"
        ):
            raise AdapterUnavailable(
                "method_not_supported: Scientific eDNA populations support only the two target assignment methods"
            )
        # Apply the scientific method population before correlated taxon/assay
        # selection. A nontarget sibling cannot qualify a target occurrence.
        tables["detections"] = tables["detections"].loc[
            tables["detections"].assignment_method.isin(SCIENTIFIC_METHODS)
        ]
        filters["target_status"] = "target"
    protocol = {
        key: getattr(params, key)
        for key in PROTOCOL_FIELDS
        if getattr(params, key) is not None
    }
    for key, value in protocol.items():
        tables["assays"] = tables["assays"].loc[tables["assays"][key].eq(value)]
    # Restrict the relational population before selection, so a sibling assay
    # cannot satisfy a protocol on behalf of the assay selected for a method.
    if protocol:
        ids = set(tables["assays"].sample_id)
        tables["occurrences"] = tables["occurrences"].loc[
            tables["occurrences"].sample_id.isin(ids)
        ]
        tables["classifications"] = tables["classifications"].loc[
            tables["classifications"].sample_id.isin(ids)
        ]
    try:
        selected = select_rows(tables, filters)
    except QueryUnavailable as exc:
        raise AdapterUnavailable(str(exc)) from exc
    if params.population == "eligible":
        method = filters.get("assignment_method")
        if (
            method not in (*SCIENTIFIC_METHODS, None)
            or filters.get("target_status") == "nontarget"
        ):
            raise AdapterUnavailable(
                "method_not_supported: Scientific eDNA populations support only the two target assignment methods"
            )
        methods = (method,) if method else SCIENTIFIC_METHODS
        by_sample = {
            key: frame.to_dict("records")
            for key, frame in selected["assays"].groupby("sample_id", sort=False)
        }
        observed_methods = {}
        for item in (
            tables["detections"].loc[tables["detections"].active.eq(True)].itertuples()
        ):
            observed_methods.setdefault(item.assay_id, set()).add(
                item.assignment_method
            )
        pairs = set()
        for row in selected["occurrences"].to_dict("records"):
            assays = by_sample.get(row["sample_id"], [])
            availability = {
                a["assay_id"]: set(
                    parse_community_availability(a["community_availability_json"])
                )
                | observed_methods.get(a["assay_id"], set())
                for a in assays
            }
            result = evaluate_analysis_eligibility(row, assays, availability, methods)
            pairs.update(
                (item["assay_id"], item["assignment_method"])
                for item in result["method_eligibility"]
                if item["analysis_eligibility"] == "included"
            )
        assay_ids = {item[0] for item in pairs}
        selected["assays"] = selected["assays"].loc[
            selected["assays"].assay_id.isin(assay_ids)
        ]
        sample_ids = set(selected["assays"].sample_id)
        selected["occurrences"] = selected["occurrences"].loc[
            selected["occurrences"].sample_id.isin(sample_ids)
        ]
        selected["detections"] = selected["detections"].loc[
            [
                (row.assay_id, row.assignment_method) in pairs
                for row in selected["detections"].itertuples()
            ]
        ]
    selected["classifications"] = tables["classifications"].loc[
        tables["classifications"].sample_id.isin(selected["occurrences"].sample_id)
    ]
    return {
        key: frame.sort_values(KEYS[key], kind="stable").reset_index(drop=True)
        for key, frame in selected.items()
    }


def _method_rows(data, selected, params, filters):
    assays = selected["assays"].to_dict("records")
    detections = selected["detections"]
    observed_methods = {}
    for item in (
        data.tables["detections"]
        .loc[data.tables["detections"].active.eq(True)]
        .itertuples()
    ):
        observed_methods.setdefault(item.assay_id, set()).add(item.assignment_method)
    requested = filters.get("assignment_method")
    methods = (
        (requested,)
        if requested
        else SCIENTIFIC_METHODS
        if params.population == "eligible"
        else RAW_METHODS
    )
    if filters.get("target_status"):
        methods = tuple(
            method
            for method in methods
            if ("nontarget" if method.endswith("_nontarget") else "target")
            == filters["target_status"]
        )
    groups = {}
    for assay in assays:
        for method in methods:
            key = (method, *(assay[field] for field in PROTOCOL_FIELDS))
            groups.setdefault(key, []).append(assay)
    # Complete empty populations still declare requested methods with an
    # explicit protocol when supplied; no invented protocol is assigned.
    if not groups:
        groups = {
            (method, *(getattr(params, key) for key in PROTOCOL_FIELDS)): []
            for method in methods
        }
    result = []
    for key, items in sorted(groups.items(), key=lambda item: canonical_json(item[0])):
        method, *protocol = key
        ids = {item["assay_id"] for item in items}
        frame = detections.loc[
            detections.assay_id.isin(ids) & detections.assignment_method.eq(method)
        ]
        availability = [
            parse_community_availability(item["community_availability_json"]).get(
                method
            )
            for item in items
        ]
        values = frame.copies_per_ml.dropna().astype(float)
        row = {
            "assignment_method": method,
            "target_status": "nontarget" if method.endswith("_nontarget") else "target",
            **dict(zip(PROTOCOL_FIELDS, protocol, strict=True)),
            "assignment_rows": len(frame),
            "read_count_sum": sum(int(value) for value in frame.read_count),
            "available_assays": sum(
                item is not None
                or method in observed_methods.get(assay["assay_id"], set())
                for assay, item in zip(items, availability, strict=True)
            ),
            "available_empty_assays": sum(
                item is not None and item["row_count"] == 0 for item in availability
            ),
        }
        if params.population == "eligible":
            # An assay included for method A is not automatically eligible for B.
            available_ids = {
                item["assay_id"]
                for item in items
                if method
                in set(
                    parse_community_availability(item["community_availability_json"])
                )
                | observed_methods.get(item["assay_id"], set())
            }
            row["eligible_assays"] = len(available_ids)
        row.update(
            {
                "concentration_reported": int(
                    frame.concentration_status.eq("reported").sum()
                ),
                "concentration_missing": int(
                    frame.concentration_status.eq("missing").sum()
                ),
                "concentration_column_absent": int(
                    frame.concentration_status.eq("column_absent").sum()
                ),
                "concentration_zero": int(values.eq(0).sum()),
                "copies_per_ml_mean": float(values.mean()) if len(values) else None,
            }
        )
        result.append(row)
    return result


class FrozenEDNACatalogueAdapter(FrozenCatalogueAdapter):
    def __init__(self, *, store, access: EDNAAccess):
        self.store, self.access = store, access

    def _load(self, request):
        if (request.access_binding, request.access_revision) != (
            self.access.binding,
            self.access.revision,
        ):
            raise AdapterAccessDenied("Current access context mismatch")
        if any(
            getattr(request.scope.sources, family).enabled
            for family in FAMILIES
            if family != "edna_metabarcoding"
        ):
            raise ValueError("C12 supports only the canonical eDNA source selection")
        manifest, contents = self.store.read(request.snapshot_id)
        if any(
            getattr(manifest.scope.sources, family).filters.model_dump(
                exclude_none=True
            )
            or getattr(getattr(manifest.scope.sources, family), "analysis_id", None)
            is not None
            for family in FAMILIES
        ):
            raise AdapterUnavailable("C12 requires whole-source snapshot exports")
        if request.scope.sources.edna_metabarcoding.enabled and not any(
            source.source_family == "edna_metabarcoding"
            for source in manifest.source_captures
        ):
            raise AdapterUnavailable("eDNA source is absent from this frozen snapshot")
        rows = decoded = 0
        for obj in manifest.objects:
            if (
                obj.source_family == "edna_metabarcoding"
                and obj.schema_version == TABLE_VERSION
            ):
                footer = pq.ParquetFile(BytesIO(contents[obj.object_id])).metadata
                rows += footer.num_rows
                decoded += sum(
                    footer.row_group(i).total_byte_size
                    for i in range(footer.num_row_groups)
                )
                if rows > MAX_ROWS or decoded > MAX_DECODED_BYTES:
                    raise ValueError("C12 complete snapshot decode budget exceeded")
        datasets, known, actual_bytes = {}, set(), 0
        owners = {
            identity: ("reserved",)
            for identity in (
                "root:data",
                "root:statistics",
                "root:metadata",
                "c12:edna",
            )
        }
        for obj in manifest.objects:
            if (
                obj.source_family == "edna_metabarcoding"
                and obj.role == "canonical_rows"
                and obj.schema_version == DATASET_VERSION
            ):
                data = load_dataset(
                    manifest,
                    contents,
                    obj,
                    decoded_budget=MAX_DECODED_BYTES - actual_bytes,
                )
                if data.metadata.dataset_id in known:
                    raise ValueError("Duplicate eDNA dataset metadata")
                known.add(data.metadata.dataset_id)
                actual_bytes += sum(
                    frame.attrs.get("decoded_bytes", 0)
                    for frame in data.tables.values()
                )
                if actual_bytes > MAX_DECODED_BYTES:
                    raise ValueError("C12 actual snapshot decode budget exceeded")
                _register_identities(owners, data)
                datasets[data.metadata.dataset_id] = data
        if known != {
            obj.dataset_id
            for obj in manifest.objects
            if obj.source_family == "edna_metabarcoding"
        }:
            raise AdapterUnavailable("Snapshot requires source-owned C12 eDNA metadata")
        permitted = {}
        for identity, data in datasets.items():
            detached = EDNADataset.model_validate(data.metadata.model_dump(mode="json"))
            if self.access.eligible(request.snapshot_id, detached) is True:
                permitted[identity] = data
        return permitted

    @staticmethod
    def _membership(datasets, scope):
        if not scope.sources.edna_metabarcoding.enabled:
            return {}
        filters = scope.sources.edna_metabarcoding.filters.model_dump(exclude_none=True)
        identity = filters.pop("dataset_id", None)
        result = {}
        for key, data in datasets.items():
            if identity is not None and identity != key:
                continue
            if filters:
                selected = _select(data, scope, Parameters(population="raw"))
                if selected["occurrences"].empty:
                    if any(
                        spec.completeness != "complete" for spec in data.metadata.tables
                    ):
                        raise AdapterUnavailable(
                            "Incomplete eDNA inputs cannot establish scoped dataset absence"
                        )
                    continue
            result[key] = data
        return result

    @staticmethod
    def _nodes(datasets, request):
        nodes = {}

        def add(
            identity, kind, root, parent, title, *, data=None, spec=None, related=None
        ):
            if identity in nodes:
                return
            m = None if data is None else data.metadata
            available = m is None or (
                spec.object_id is not None
                if spec
                else all(item.object_id is not None for item in m.tables)
            )
            complete = m is None or all(
                item.completeness == "complete" for item in m.tables
            )
            relational = m is None or all(item.object_id is not None for item in m.tables)
            provenance = (
                {}
                if data is None or kind == "directory"
                else next(
                    obj.provenance.model_dump(mode="json")
                    for obj in data.objects
                    if obj.role == "canonical_rows"
                )
            )
            operations = []
            if kind in {"dataset", "table"}:
                for operation in OPERATIONS:
                    usable = available and relational and (
                        complete or operation in {"c12.table", "c12.coverage"}
                    )
                    operations.append(
                        {
                            "id": operation,
                            "version": ADAPTER_VERSION,
                            "kind": "inventory"
                            if operation == "c12.count"
                            else "descriptive",
                            "required_permission": "catalogue.read",
                            "availability": {"status": "available"}
                            if usable
                            else {
                                "status": "unavailable",
                                "reason": "Required complete canonical eDNA inputs unavailable",
                            },
                        }
                    )
            nodes[identity] = CatalogueNode.model_validate(
                {
                    "snapshot_id": request.snapshot_id,
                    "scope": request.scope,
                    "id": identity,
                    "kind": kind,
                    "root": root,
                    "parent_id": parent,
                    "title": title,
                    "purpose": m.purpose if kind in {"dataset", "table"} else title,
                    "availability": spec.availability
                    if spec
                    else {"status": "available"}
                    if available
                    else {
                        "status": "unavailable",
                        "reason": "Canonical eDNA inputs unavailable",
                    },
                    "authority": "descriptive",
                    "lifecycle": {
                        "ingestion": "complete"
                        if complete
                        else "partial"
                        if available
                        else "unknown",
                        "publication": "unpublished",
                        "scientific_approval": "not_reviewed",
                        "query_readiness": "ready" if available and relational else "not_ready",
                        "embedding_readiness": "unknown",
                    },
                    "provenance": provenance,
                    "source_family": "edna_metabarcoding"
                    if kind == "dataset"
                    else None,
                    "descriptor": m.descriptor if kind == "dataset" else None,
                    "sections": list(DATASET_SECTIONS) if kind == "dataset" else [],
                    "operations": operations,
                    "related_ids": related or [],
                }
            )

        for root in ("data", "statistics", "metadata"):
            add(f"root:{root}", "root", root, None, {"en": root, "ja": root})
        if datasets:
            add(
                "c12:edna",
                "directory",
                "data",
                "root:data",
                {"en": "Canonical eDNA", "ja": "正規eDNA"},
            )
        for identity, data in sorted(datasets.items()):
            m = data.metadata
            source, provider, project = _groups(m)
            for node_id, parent, title in (
                (source, "c12:edna", m.source_id),
                (
                    provider,
                    source,
                    " / ".join(
                        value or "Unknown"
                        for value in (m.provider, m.provider_locus, m.provider_team)
                    ),
                ),
                (project, provider, m.provider_project_id),
                (m.collection_id, project, m.collection_id),
            ):
                add(
                    node_id,
                    "directory",
                    "data",
                    parent,
                    {"en": title, "ja": title},
                    data=data,
                )
            add(identity, "dataset", "data", m.collection_id, m.title, data=data)
            for spec in m.tables:
                add(
                    _table_id(m, spec),
                    "table",
                    "data",
                    identity,
                    {"en": spec.name, "ja": spec.name},
                    data=data,
                    spec=spec,
                )
            for root in ("statistics", "metadata"):
                add(
                    _reference_id(root, identity),
                    "reference",
                    root,
                    f"root:{root}",
                    m.title,
                    data=data,
                    related=[identity],
                )
        for identity, data in datasets.items():
            nodes[identity].related_ids = [
                key for key in data.metadata.related_ids if key in nodes
            ] + [
                _reference_id(root, identity)
                for root in ("statistics", "metadata")
                if _reference_id(root, identity) not in data.metadata.related_ids
            ]
        return nodes

    def query(self, request: OperationRequest | dict) -> EDNAResponse:
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
                "C12 requires one dataset and a supported versioned operation"
            )
        params = Parameters.model_validate(request.parameters)
        normalize_filters(params.filters)
        if request.operation_id != "c12.table" and params.offset:
            raise ValueError("eDNA aggregate operations cannot skip result rows")
        data = self._load(request).get(request.input_ids[0])
        if data is None:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        try:
            _, filters = _filters(request.scope, params)
            if request.operation_id == "c12.frequency":
                if (
                    params.population != "eligible"
                    or filters.get("assignment_method") not in SCIENTIFIC_METHODS
                    or not filters.get("taxon")
                    or not all(
                        getattr(params, key) is not None for key in PROTOCOL_FIELDS
                    )
                ):
                    raise AdapterUnavailable(
                        "Detection frequency requires an eligible population, one supported target method, an exact taxon and a complete explicit assay protocol"
                    )
            if request.operation_id in {
                "c12.count",
                "c12.summary",
                "c12.frequency",
            } and any(spec.completeness != "complete" for spec in data.metadata.tables):
                raise AdapterUnavailable(
                    "Exact eDNA aggregates require complete frozen relational tables"
                )
            selected = _select(data, request.scope, params)
            rows = self._execute(data, request, params, filters, selected)
            complete = (
                "complete"
                if all(spec.completeness == "complete" for spec in data.metadata.tables)
                else "partial"
            )
            return self._response(data, request, params, rows, complete)
        except AdapterUnavailable as exc:
            return self._response(data, request, params, [], "unavailable", str(exc))

    @staticmethod
    def _execute(data, request, params, filters, selected):
        samples, assays, detections = (
            selected[key] for key in ("occurrences", "assays", "detections")
        )
        common = {
            "population": params.population,
            "eligibility_definition": ELIGIBILITY_DEFINITION
            if params.population == "eligible"
            else "Active retained canonical inventory, including controls and unknown classifications",
        }
        if request.operation_id == "c12.table":
            return selected[params.table].to_dict("records")
        if request.operation_id == "c12.count":
            return [
                {
                    **common,
                    "entity": "source_occurrences",
                    "source_occurrence_count": len(samples),
                    "assay_count": len(assays),
                    "physical_sample_count": None,
                    "controls": int(samples.is_control.eq(True).sum()),
                    "unknown_control_status": int(samples.is_control.isna().sum()),
                    "methods": _method_rows(data, selected, params, filters),
                    "denominator": "Complete matching active source occurrences and distinct assays; alternative assignment methods are separate",
                }
            ]
        if request.operation_id == "c12.summary":
            return [
                {
                    **common,
                    **row,
                    "entity": "detection_rows",
                    "denominator": "Complete matching method and protocol detection rows; reads are not organism abundance",
                }
                for row in _method_rows(data, selected, params, filters)
            ]
        if request.operation_id == "c12.frequency":
            denominator = _select(data, request.scope, params, denominator=True)
            positive = detections.loc[detections.read_count.map(int).gt(0)]
            if params.frequency_unit == "assays":
                numerator = len(set(positive.assay_id))
                count = len(denominator["assays"])
            else:
                positive_ids = set(positive.assay_id)
                numerator = len(
                    set(assays.loc[assays.assay_id.isin(positive_ids)].sample_id)
                )
                count = len(denominator["occurrences"])
            return [
                {
                    **common,
                    "entity": params.frequency_unit,
                    "assignment_method": filters["assignment_method"],
                    "taxon": filters["taxon"],
                    **{key: getattr(params, key) for key in PROTOCOL_FIELDS},
                    "positive_units": numerator,
                    "eligible_denominator": count,
                    "frequency": numerator / count if count else None,
                    "denominator": "Eligible matching protocol units with the selected source-backed method available; taxon predicate removed; positive means retained read_count > 0",
                }
            ]
        precision = {}
        for row in samples.to_dict("records"):
            key = row.get("temporal_precision") or "unknown"
            precision[key] = precision.get(key, 0) + 1
        known = samples.collection_date_utc.dropna()
        return [
            {
                **common,
                "entity": "source_occurrences",
                "observed_occurrences": len(samples),
                "dated_occurrences": len(known),
                "unknown_date_occurrences": int(
                    samples.collection_date_utc.isna().sum()
                ),
                "temporal_precisions": precision,
                "observed_date_labels": int(known.nunique()),
                "earliest_retained_label": min(known) if len(known) else None,
                "latest_retained_label": max(known) if len(known) else None,
                "expected_dates": None,
                "missing_dates": None,
                "coverage_state": "unknown",
                "denominator": "Matching source occurrences and their retained date precision; no expected sampling calendar supplied",
            }
        ]

    @staticmethod
    def _response(data, request, params, rows, completeness, reason=None):
        if params.offset > len(rows) and reason is None:
            raise ValueError("Offset exceeds retained eDNA result")
        # Convert primitive nullable pandas values without coercing zero/False.
        rows = [
            {
                key: None
                if value is pd.NA or (isinstance(value, float) and pd.isna(value))
                else value
                for key, value in row.items()
            }
            for row in rows
        ]
        try:
            _finite_json(rows)
        except ValueError as exc:
            raise AdapterUnavailable(
                "Exact eDNA results exceed the supported browser numeric contract"
            ) from exc
        columns = list(rows[0]) if rows else []
        selected = rows[params.offset : params.offset + params.limit]
        digest = hashlib.sha256(
            canonical_json({"columns": columns, "rows": rows}).encode()
        ).hexdigest()
        inputs = [
            {
                "object_id": obj.object_id,
                "content_sha256": obj.sha256,
                "source_generation": obj.provenance.source_generation,
            }
            for obj in sorted(data.objects, key=lambda obj: obj.object_id)
        ]
        known = completeness == "complete"
        receipt = {
            "snapshot_id": request.snapshot_id,
            "scope": request.scope.model_dump(mode="json"),
            "operation_id": request.operation_id,
            "operation_version": ADAPTER_VERSION,
            "inputs": inputs,
            "parameters": params.model_dump(mode="json"),
            "authority": "descriptive",
            "availability": {"status": "available"}
            if reason is None
            else {"status": "unavailable", "reason": reason},
            "provenance": {
                "source_generation": inputs[0]["source_generation"],
                "references": [data.metadata.qualification, ELIGIBILITY_DEFINITION],
            },
            "total_rows": {
                "state": "known",
                "entity": "rows",
                "denominator": "Complete scoped operation output rows",
                "value": len(rows),
            }
            if known
            else {
                "state": "unknown",
                "entity": "rows",
                "denominator": "Complete scoped operation output rows",
                "reason": reason or "eDNA input completeness is not established",
            },
            "returned_count": len(selected),
            "preview_truncated": len(selected) < len(rows),
            "source_completeness": completeness,
            "query_completion": "not_started"
            if reason
            else "complete"
            if known
            else "partial",
            "content_sha256": digest,
        }
        receipt["receipt_id"] = (
            "c12:receipt:"
            + hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
        )
        return EDNAResponse.model_validate(
            {
                "result": {
                    "snapshot_id": request.snapshot_id,
                    "scope": request.scope,
                    "columns": [
                        {
                            "key": key,
                            "title": {"en": key, "ja": key},
                            "unit": {
                                "copies_per_ml": "copies/mL",
                                "copies_per_ml_mean": "copies/mL",
                                "read_count": "reads",
                                "read_count_sum": "reads",
                                "lat": "degree",
                                "lon": "degree",
                                "frequency": "proportion",
                            }.get(key),
                        }
                        for key in columns
                    ],
                    "rows": selected,
                    "receipt": receipt,
                },
                "offset": params.offset,
                "next_offset": params.offset + len(selected)
                if params.offset + len(selected) < len(rows)
                else None,
                "qualifications": [
                    data.metadata.qualification,
                    f"Population: {params.population}; operation: {request.operation_id}/{ADAPTER_VERSION}",
                    ELIGIBILITY_DEFINITION,
                    "Source occurrences do not establish physical samples; alternative methods share evidence and are never summed as independent observations",
                    "Reads are not organism abundance; empty filtered results do not establish ecological absence; unknown taxonomy/date precision remains retained",
                    "Descriptive frozen inputs; current access and scientific eligibility are supplied independently",
                ],
            }
        )

    def inspect(self, identity: str, request: ListingRequest | dict):
        request = ListingRequest.model_validate(
            request.model_dump(mode="json")
            if isinstance(request, ListingRequest)
            else request
        )
        datasets = self._membership(self._load(request), request.scope)
        if identity not in datasets:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        data = datasets[identity]
        node = self._nodes(datasets, request)[identity]
        coverage = self.query(
            OperationRequest(
                snapshot_id=request.snapshot_id,
                scope=request.scope,
                operation_id="c12.coverage",
                operation_version=ADAPTER_VERSION,
                input_ids=[identity],
                access_binding=request.access_binding,
                access_revision=request.access_revision,
            )
        )
        return {
            "node": node,
            "overview": data.metadata.model_dump(
                mode="json", exclude={"tables", "methods", "related_ids"}
            ),
            "tables": [spec.model_copy(deep=True) for spec in data.metadata.tables],
            "coverage": coverage,
            "methods": list(data.metadata.methods),
            "provenance": [
                {
                    "object_id": obj.object_id,
                    "content_sha256": obj.sha256,
                    "source_generation": obj.provenance.source_generation,
                    "origin": None
                    if obj.provenance.origin is None
                    else obj.provenance.origin.model_dump(mode="json"),
                }
                for obj in data.objects
            ],
            "related": list(node.related_ids),
        }
