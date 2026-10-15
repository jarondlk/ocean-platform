"""C10 frozen CTD/metagenome catalogue; explicit store and current policy only.

No model, ranking, production paths, database discovery, or fixture fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import hashlib
from typing import Callable

import pandas as pd
import pyarrow.parquet as pq
from pydantic import Field, TypeAdapter

from ingestion.catalogue_adapter_inputs import (
    MAX_DECODED_BYTES,
    MAX_ROWS,
    AdapterUnavailable,
    DatasetInputs,
    load_dataset,
    period,
)
from schema.catalogue_adapter import (
    ADAPTER_VERSION,
    DATASET_VERSION,
    TABLE_VERSION,
    KEYS,
    ROLES,
    AdapterResponse,
    FrozenDataset,
)
from schema.context_catalogue import (
    DATASET_SECTIONS,
    CatalogueCount,
    CatalogueListing,
    CatalogueNode,
    ContractModel,
    Identifier,
    ListingRequest,
    NonnegativeInt,
    OperationRequest,
    PageLimit,
    TextValue,
    canonical_json,
    make_cursor,
    ordered_nodes,
    validate_cursor,
)
from schema.time_range import matches_time, time_bounds
from retrieval.source_scope import FAMILIES

OPERATIONS = ("c10.table", "c10.count", "c10.summary", "c10.coverage")
_identifier = TypeAdapter(Identifier)


class AdapterAccessDenied(PermissionError):
    """Missing/denied identities share the same non-disclosing boundary."""


@dataclass(frozen=True)
class AdapterAccess:
    binding: str
    revision: str
    eligible: Callable[[str, FrozenDataset], bool]

    def __post_init__(self):
        _identifier.validate_python(self.binding)
        _identifier.validate_python(self.revision)
        if not callable(self.eligible):
            raise ValueError("Current dataset access/eligibility callback required")


class Parameters(ContractModel):
    table: str | None = Field(default=None, min_length=1, max_length=256)
    column: Identifier | None = None
    taxon: TextValue | None = None
    limit: PageLimit = 100
    offset: NonnegativeInt = 0


def _rows(frame):
    return [
        {
            key: None
            if pd.isna(value)
            else value.item()
            if hasattr(value, "item")
            else value
            for key, value in row.items()
        }
        for row in frame.to_dict("records")
    ]


def _time_match(value, precision, filters):
    start, end = filters.time_from, filters.time_to
    if start is None and end is None:
        return True
    if value is None or pd.isna(value):
        raise AdapterUnavailable(
            "Collection date is unknown within the requested temporal scope"
        )
    if precision in {"day", "datetime"}:
        return matches_time(value, start, end)
    interval = period(value, precision)
    if interval is None:
        raise AdapterUnavailable("Collection period is unknown")
    lower, upper, exclusive = time_bounds(start, end)
    begin, finish = interval
    if (
        lower
        and finish <= lower
        or upper
        and (begin >= upper if exclusive else begin > upper)
    ):
        return False
    if lower and begin < lower or upper and finish > upper:
        raise AdapterUnavailable(
            "Requested time range cannot resolve a coarse collection period"
        )
    return True


def _anchor(data: DatasetInputs, scope, *, require_complete=True):
    name = "casts" if data.metadata.family == "ctd" else "collections"
    spec = next(t for t in data.metadata.tables if t.name == name)
    if spec.object_id is None or require_complete and spec.completeness != "complete":
        raise AdapterUnavailable("Complete source anchor table is unavailable")
    frame = data.tables[name]
    selection = getattr(scope.sources, data.metadata.family)
    if not selection.enabled:
        return frame.iloc[:0]
    filters = selection.filters
    for key in ("bay", "station", "sample_id"):
        value = getattr(filters, key)
        if value is not None:
            frame = frame.loc[frame[key].eq(value)]
    mask = [
        _time_match(
            row["collection_date"],
            row.get("date_precision", data.metadata.collection_date_precision),
            filters,
        )
        for row in frame.to_dict("records")
    ]
    return frame.loc[pd.Series(mask, index=frame.index, dtype=bool)]


def _scoped(data: DatasetInputs, scope, table, taxon=None):
    selected = _anchor(data, scope)
    anchor_name = "casts" if data.metadata.family == "ctd" else "collections"
    if table not in data.tables:
        raise AdapterUnavailable("Requested table was not retained")
    frame = data.tables[table]
    if table != anchor_name:
        foreign = "cast_id" if data.metadata.family == "ctd" else "library_id"
        frame = frame.loc[frame[foreign].isin(selected[KEYS[anchor_name]])]
    else:
        frame = selected
    if taxon is not None:
        if "taxon" not in frame:
            raise ValueError("Taxon filter is supported only for taxonomic tables")
        frame = frame.loc[frame.taxon.eq(taxon)]
    return frame.sort_values(KEYS[table], kind="stable")


class FrozenCatalogueAdapter:
    def __init__(self, *, store, access: AdapterAccess):
        self.store, self.access = store, access

    def _load(self, request):
        if (request.access_binding, request.access_revision) != (
            self.access.binding,
            self.access.revision,
        ):
            raise AdapterAccessDenied("Current access context mismatch")
        scope = request.scope
        if (
            scope.sources.remote_sensing.enabled
            or scope.sources.edna_metabarcoding.enabled
        ):
            raise ValueError("C10 supports only CTD/metagenome source selections")
        manifest, contents = self.store.read(request.snapshot_id)
        if any(
            selection.filters.model_dump(exclude_none=True)
            or getattr(selection, "analysis_id", None) is not None
            for selection in (
                getattr(manifest.scope.sources, family) for family in FAMILIES
            )
        ):
            raise AdapterUnavailable("C10 requires whole-source snapshot exports")
        captured_families = {
            source.source_family for source in manifest.source_captures
        }
        if any(
            getattr(scope.sources, family).enabled
            and (
                not getattr(manifest.scope.sources, family).enabled
                or family not in captured_families
            )
            for family in ROLES
        ):
            raise AdapterUnavailable(
                "Requested source is absent from this frozen snapshot"
            )
        decoded_bytes = decoded_rows = 0
        for obj in manifest.objects:
            if obj.source_family in ROLES and obj.schema_version == TABLE_VERSION:
                parquet = pq.ParquetFile(BytesIO(contents[obj.object_id])).metadata
                decoded_rows += parquet.num_rows
                decoded_bytes += sum(
                    parquet.row_group(i).total_byte_size
                    for i in range(parquet.num_row_groups)
                )
                if decoded_bytes > MAX_DECODED_BYTES or decoded_rows > MAX_ROWS:
                    raise ValueError("C10 complete snapshot decode budget exceeded")
        known = set()
        datasets = {}
        for obj in manifest.objects:
            if obj.source_family not in ROLES:
                continue
            if obj.role == "dataset_metadata" and obj.schema_version == DATASET_VERSION:
                data = load_dataset(manifest, contents, obj)
                if data.metadata.dataset_id in known:
                    raise ValueError("Duplicate dataset metadata")
                known.add(data.metadata.dataset_id)
                copied = FrozenDataset.model_validate(
                    data.metadata.model_dump(mode="json")
                )
                if self.access.eligible(request.snapshot_id, copied) is True:
                    datasets[data.metadata.dataset_id] = data
        if {
            obj.dataset_id for obj in manifest.objects if obj.source_family in ROLES
        } != known:
            raise AdapterUnavailable(
                "Snapshot requires source-owned C10 frozen dataset metadata"
            )
        return datasets

    @staticmethod
    def _membership(datasets, scope):
        result = {}
        for identity, data in datasets.items():
            selection = getattr(scope.sources, data.metadata.family)
            if not selection.enabled:
                continue
            if (
                selection.filters.model_dump(exclude_none=True)
                and _anchor(data, scope).empty
            ):
                continue
            result[identity] = data
        return result

    @staticmethod
    def _nodes(datasets, request):
        nodes = {}
        ownership = {}

        def add(identity, kind, parent, title, *, data=None, table=None):
            owner = (
                None
                if data is None
                else (data.metadata.source_id, data.metadata.family)
            )
            if identity in nodes:
                if (
                    ownership[identity] != owner
                    or nodes[identity].kind != kind
                    or nodes[identity].parent_id != parent
                ):
                    raise ValueError(
                        "Canonical source/dataset/table identities collide"
                    )
                return
            if kind == "root":
                available, ingestion = True, "complete"
            else:
                anchor_name = (
                    "casts" if data.metadata.family == "ctd" else "collections"
                )
                anchor_spec = next(
                    t for t in data.metadata.tables if t.name == anchor_name
                )
                available = (
                    anchor_spec.object_id is not None
                    and anchor_spec.completeness == "complete"
                )
                ingestion = (
                    "complete"
                    if all(
                        t.completeness == "complete"
                        for t in data.metadata.tables
                        if t.name != "ranked_taxa"
                    )
                    else "partial"
                )
            if table is not None and table.object_id is None:
                available = False
            provenance = (
                {}
                if data is None
                else next(
                    o.provenance.model_dump(mode="json")
                    for o in data.objects
                    if o.role == "dataset_metadata"
                )
            )
            operations = []
            if kind in {"dataset", "table"}:
                for op in OPERATIONS:
                    usable = available and (
                        table is None or table.object_id is not None
                    )
                    if op in {"c10.count", "c10.summary"} and table is not None:
                        usable = usable and table.completeness == "complete"
                    if op == "c10.summary" and table is not None:
                        usable = usable and any(
                            c.dtype in {"number", "integer"}
                            and c.unit.strip().casefold() != "unknown"
                            for c in table.columns
                        )
                        if table.name in {"kraken_abundance", "metaeuk_abundance"}:
                            usable = (
                                usable
                                and table.abundance_denominator.strip().casefold()
                                != "unknown"
                                and table.taxonomic_rank.strip().casefold() != "unknown"
                            )
                    operations.append(
                        {
                            "id": op,
                            "version": ADAPTER_VERSION,
                            "kind": "inventory" if op == "c10.count" else "descriptive",
                            "required_permission": "catalogue.read",
                            "availability": {"status": "available"}
                            if usable
                            else {
                                "status": "unavailable",
                                "reason": "Required complete frozen inputs unavailable",
                            },
                        }
                    )
            if kind == "dataset" and data.metadata.family == "metagenome":
                operations.append(
                    {
                        "id": "c10.contigs",
                        "version": ADAPTER_VERSION,
                        "kind": "descriptive",
                        "required_permission": "catalogue.read",
                        "availability": {
                            "status": "unavailable",
                            "reason": "Contig inputs and operations are unsupported",
                        },
                    }
                )
            nodes[identity] = CatalogueNode.model_validate(
                {
                    "snapshot_id": request.snapshot_id,
                    "scope": request.scope,
                    "id": identity,
                    "kind": kind,
                    "root": "data",
                    "parent_id": parent,
                    "title": title,
                    "purpose": title if data is None else data.metadata.purpose,
                    "availability": table.availability
                    if table is not None
                    else {"status": "available"},
                    "authority": "descriptive",
                    "lifecycle": {
                        "ingestion": ingestion,
                        "publication": "unpublished",
                        "scientific_approval": "not_reviewed",
                        "query_readiness": "ready" if available else "not_ready",
                        "embedding_readiness": "unknown",
                    },
                    "provenance": provenance,
                    "source_family": None if data is None else data.metadata.family,
                    "descriptor": data.metadata.descriptor
                    if kind == "dataset"
                    else None,
                    "sections": list(DATASET_SECTIONS) if kind == "dataset" else [],
                    "operations": operations,
                }
            )
            ownership[identity] = owner

        add("root:data", "root", None, {"en": "Data", "ja": "データ"})
        for identity, data in sorted(datasets.items()):
            metadata = data.metadata
            source = f"c10:source:{metadata.source_id}"
            add(
                source,
                "directory",
                "root:data",
                {"en": metadata.source_id, "ja": metadata.source_id},
                data=data,
            )
            add(
                metadata.collection_id,
                "directory",
                source,
                {"en": metadata.collection_id, "ja": metadata.collection_id},
                data=data,
            )
            add(
                identity,
                "dataset",
                metadata.collection_id,
                metadata.title.model_dump(),
                data=data,
            )
            for spec in metadata.tables:
                table_id = spec.object_id or f"{identity}:unavailable:{spec.name}"
                add(
                    table_id,
                    "table",
                    identity,
                    {"en": spec.name, "ja": spec.name},
                    data=data,
                    table=spec,
                )
        for identity, data in datasets.items():
            nodes[identity].related_ids = [
                key for key in data.metadata.related_ids if key in nodes
            ]
        return nodes

    def list(self, request: ListingRequest | dict) -> CatalogueListing:
        request = ListingRequest.model_validate(
            request.model_dump(mode="json")
            if isinstance(request, ListingRequest)
            else request
        )
        datasets = self._membership(self._load(request), request.scope)
        nodes = self._nodes(datasets, request)
        if request.parent_id is not None and request.parent_id not in nodes:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        items = [
            node
            for node in nodes.values()
            if request.parent_id is None or node.parent_id == request.parent_id
        ]
        f = request.filters
        items = [
            node
            for node in items
            if (not f.roots or node.root in f.roots)
            and (not f.kinds or node.kind in f.kinds)
            and (not f.source_families or node.source_family in f.source_families)
            and (not f.authorities or node.authority in f.authorities)
            and (
                f.search is None
                or f.search.casefold()
                in (node.id + " " + node.title.en + " " + node.title.ja).casefold()
            )
        ]
        items = ordered_nodes(items, request.ordering)
        offset = validate_cursor(request)
        if offset > len(items):
            raise ValueError("Cursor exceeds matching frozen inventory")
        selected = items[offset : offset + request.limit]
        next_cursor = (
            make_cursor(request, offset + len(selected))
            if offset + len(selected) < len(items)
            else None
        )
        return CatalogueListing.model_validate(
            {
                "request": request,
                "items": selected,
                "total": {
                    "state": "known",
                    "entity": "canonical_objects",
                    "denominator": "distinct permitted matching canonical objects",
                    "value": len(items),
                },
                "returned_count": len(selected),
                "next_cursor": next_cursor,
                "preview_truncated": next_cursor is not None,
                "source_completeness": "complete",
                "query_completion": "complete",
                "availability": {"status": "available"},
            }
        )

    def dataset_count(self, request: ListingRequest | dict) -> CatalogueCount:
        request = ListingRequest.model_validate(
            request.model_dump(mode="json")
            if isinstance(request, ListingRequest)
            else request
        )
        datasets = self._membership(self._load(request), request.scope)
        nodes = self._nodes(datasets, request)
        if request.parent_id is not None and request.parent_id not in nodes:
            raise AdapterAccessDenied("Catalogue identity unavailable")

        def descendant(node):
            parent = node.parent_id
            while parent is not None:
                if parent == request.parent_id:
                    return True
                parent = nodes[parent].parent_id
            return request.parent_id is None

        f = request.filters
        matching = [
            node
            for node in nodes.values()
            if node.kind == "dataset"
            and descendant(node)
            and (not f.kinds or "dataset" in f.kinds)
            and (not f.roots or "data" in f.roots)
            and (not f.source_families or node.source_family in f.source_families)
            and (not f.authorities or node.authority in f.authorities)
            and (
                f.search is None
                or f.search.casefold()
                in (node.id + " " + node.title.en + " " + node.title.ja).casefold()
            )
        ]
        return CatalogueCount(
            state="known",
            entity="datasets",
            denominator="Distinct permitted canonical datasets in complete matching descendants",
            value=len(matching),
        )

    def open(self, identity: str, request: ListingRequest | dict) -> CatalogueNode:
        request = ListingRequest.model_validate(
            request.model_dump(mode="json")
            if isinstance(request, ListingRequest)
            else request
        )
        nodes = self._nodes(
            self._membership(self._load(request), request.scope), request
        )
        if identity not in nodes:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        return nodes[identity]

    def query(self, request: OperationRequest | dict) -> AdapterResponse:
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
                "C10 requires one dataset and a supported versioned operation"
            )
        params = Parameters.model_validate(request.parameters)
        if request.operation_id == "c10.coverage":
            if (
                params.table is not None
                or params.column is not None
                or params.taxon is not None
            ):
                raise ValueError(
                    "Coverage uses collection dates, not measurement/run dates"
                )
        elif params.table is None or params.table not in KEYS:
            raise ValueError("A registered table role is required")
        if request.operation_id != "c10.summary" and params.column is not None:
            raise ValueError("Only summary operations accept a measurement column")
        if request.operation_id in {"c10.count", "c10.summary"} and params.offset:
            raise ValueError("Aggregate operations cannot skip result rows")
        datasets = self._load(request)
        data = datasets.get(request.input_ids[0])
        if data is None:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        spec = next((t for t in data.metadata.tables if t.name == params.table), None)
        try:
            if not getattr(request.scope.sources, data.metadata.family).enabled:
                raise AdapterUnavailable("Requested source is disabled")
            columns, rows, completeness = self._execute(data, request, params, spec)
            return self._response(
                data, request, params, spec, columns, rows, completeness
            )
        except AdapterUnavailable as error:
            return self._response(
                data, request, params, spec, [], [], "unavailable", str(error)
            )

    @staticmethod
    def _execute(data, request, params, spec):
        if request.operation_id == "c10.coverage":
            anchor = _anchor(data, request.scope)
            records = _rows(anchor)
            bins = {}
            for row in records:
                key = (
                    row["collection_date"],
                    row.get("date_precision", data.metadata.collection_date_precision),
                )
                bins[key] = bins.get(key, 0) + 1
            entity = "casts" if data.metadata.family == "ctd" else "libraries"
            rows = [
                {
                    "collection_period": when,
                    "precision": precision,
                    "count": count,
                    "entity": entity,
                }
                for (when, precision), count in sorted(
                    bins.items(),
                    key=lambda pair: (pair[0][0] is None, pair[0][0] or "", pair[0][1]),
                )
            ]
            return (
                [
                    ("collection_period", None),
                    ("precision", None),
                    ("count", entity),
                    ("entity", None),
                ],
                rows,
                "complete",
            )
        if spec is None or spec.object_id is None:
            raise AdapterUnavailable("Requested table was not retained")
        frame = _scoped(data, request.scope, params.table, params.taxon)
        if request.operation_id == "c10.table":
            return (
                [(c.name, c.unit) for c in spec.columns],
                _rows(frame),
                spec.completeness,
            )
        if spec.completeness != "complete":
            raise AdapterUnavailable(
                "Exact operations require complete normalized tables; ranked omission is unknown"
            )
        if request.operation_id == "c10.count":
            return (
                [("count", spec.entity), ("entity", None), ("denominator", None)],
                [
                    {
                        "count": len(frame),
                        "entity": spec.entity,
                        "denominator": spec.denominator,
                    }
                ],
                "complete",
            )
        column = next((c for c in spec.columns if c.name == params.column), None)
        if column is None or column.dtype not in {"number", "integer"}:
            raise ValueError(
                "Summary requires an explicitly numeric measurement column"
            )
        if column.unit.strip().casefold() == "unknown" or (
            spec.name in {"kraken_abundance", "metaeuk_abundance"}
            and (
                spec.abundance_denominator.strip().casefold() == "unknown"
                or spec.taxonomic_rank.strip().casefold() == "unknown"
            )
        ):
            raise AdapterUnavailable(
                "Measurement unit, denominator or taxonomic rank is unknown"
            )
        values = pd.to_numeric(frame[column.name], errors="raise")
        present = values.dropna()
        row = {
            "measurement": column.name,
            "n_observed": len(present),
            "n_missing": int(values.isna().sum()),
            "n_zero": int(present.eq(0).sum()),
            "minimum": float(present.min()) if len(present) else None,
            "maximum": float(present.max()) if len(present) else None,
            "mean": float(present.mean()) if len(present) else None,
        }
        columns = [
            (
                key,
                column.unit
                if key in {"minimum", "maximum", "mean"}
                else spec.entity
                if key.startswith("n_")
                else None,
            )
            for key in row
        ]
        return columns, [row], "complete"

    @staticmethod
    def _response(
        data, request, params, spec, columns, rows, completeness, reason=None
    ):
        if params.offset > len(rows) and reason is None:
            raise ValueError("Offset exceeds complete retained result")
        selected = rows[params.offset : params.offset + params.limit]
        content = {"columns": columns, "rows": rows}
        digest = hashlib.sha256(canonical_json(content).encode()).hexdigest()
        inputs = [
            {
                "object_id": obj.object_id,
                "content_sha256": obj.sha256,
                "source_generation": obj.provenance.source_generation,
            }
            for obj in sorted(data.objects, key=lambda o: o.object_id)
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
                "references": [data.metadata.qualification],
            },
            "total_rows": {
                "state": "known",
                "entity": "rows",
                "denominator": "complete scoped operation result rows",
                "value": len(rows),
            }
            if known
            else {
                "state": "unknown",
                "entity": "rows",
                "denominator": "complete scoped operation result rows",
                "reason": reason or "Source table is not complete",
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
            "c10:receipt:"
            + hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
        )
        return AdapterResponse.model_validate(
            {
                "result": {
                    "snapshot_id": request.snapshot_id,
                    "scope": request.scope,
                    "columns": [
                        {"key": key, "title": {"en": key, "ja": key}, "unit": unit}
                        for key, unit in columns
                    ],
                    "rows": selected,
                    "receipt": receipt,
                },
                "table": spec,
                "offset": params.offset,
                "next_offset": params.offset + len(selected)
                if params.offset + len(selected) < len(rows)
                else None,
                "qualifications": [
                    data.metadata.qualification,
                    "Descriptive frozen inputs; scientific approval is independent",
                    "Collection periods retain source precision; expected sampling gaps are not inferred",
                ],
            }
        )

    def inspect(self, identity: str, request: ListingRequest | dict):
        """All six C08 sections, without exposing denied related identities."""
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
                operation_id="c10.coverage",
                operation_version=ADAPTER_VERSION,
                input_ids=[identity],
                access_binding=request.access_binding,
                access_revision=request.access_revision,
            )
        )
        return {
            "node": node,
            "overview": {
                "qualification": data.metadata.qualification,
                "collection_date_precision": data.metadata.collection_date_precision,
                "source_id": data.metadata.source_id,
                "collection_id": data.metadata.collection_id,
            },
            "tables": [t.model_copy(deep=True) for t in data.metadata.tables],
            "coverage": coverage,
            "methods": list(data.metadata.methods),
            "provenance": [
                {
                    "object_id": obj.object_id,
                    "content_sha256": obj.sha256,
                    "source_generation": obj.provenance.source_generation,
                    "origin": obj.provenance.origin.model_dump(mode="json")
                    if obj.provenance.origin
                    else None,
                }
                for obj in data.objects
            ],
            "related": list(node.related_ids),
        }
