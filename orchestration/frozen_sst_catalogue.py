"""C11 exact SST operations over explicit, verified C09 snapshot bytes.

Only C08 listing/cursor transport is reused from C10. SST ownership, scientific
scope, product/sampling semantics and operations are independently validated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from io import BytesIO
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq
from pydantic import TypeAdapter

from ingestion.sst_catalogue_inputs import (
    MAX_DECODED_BYTES,
    MAX_ROWS,
    AdapterUnavailable,
    DatasetInputs,
    load_dataset,
    observation_day,
)
from orchestration.frozen_catalogue import (
    AdapterAccessDenied,
    FrozenCatalogueAdapter,
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
    canonical_json,
)
from schema.sst_catalogue import (
    ADAPTER_VERSION,
    DATASET_VERSION,
    TABLE_COLUMNS,
    TABLE_VERSION,
    SSTDataset,
    SSTResponse,
)
from schema.time_range import matches_time, time_bounds

OPERATIONS = (
    "c11.table",
    "c11.count",
    "c11.summary",
    "c11.coverage",
    "c11.grid_points",
)
_identifier = TypeAdapter(Identifier)


@dataclass(frozen=True)
class SSTAccess:
    """Trusted current whole-dataset access AND scientific eligibility decision."""

    binding: str
    revision: str
    eligible: Callable[[str, SSTDataset], bool]

    def __post_init__(self):
        _identifier.validate_python(self.binding)
        _identifier.validate_python(self.revision)
        if not callable(self.eligible):
            raise ValueError("Current SST dataset access/eligibility callback required")


class Parameters(ContractModel):
    limit: PageLimit = 100
    offset: NonnegativeInt = 0


def _reference_id(root, identity):
    return f"c11:reference:{root}:" + hashlib.sha256(identity.encode()).hexdigest()


def _register_identities(owners, data):
    """All entry points share one canonical namespace, including export artifacts."""
    metadata = data.metadata
    source = metadata.source_id
    entries = [
        (metadata.product_node_id, ("product", source, "c11:sst")),
        (metadata.collection_id, ("collection", source, metadata.product_node_id)),
        (metadata.dataset_id, ("dataset", source, metadata.collection_id)),
        (
            metadata.table.object_id
            or f"{metadata.dataset_id}:unavailable:observations",
            ("table", source, metadata.dataset_id),
        ),
    ]
    entries += [
        (obj.object_id, ("metadata_artifact", source, metadata.dataset_id))
        for obj in data.objects
        if obj.role == "dataset_metadata"
    ]
    entries += [
        (
            _reference_id(root, metadata.dataset_id),
            ("reference", root, metadata.dataset_id),
        )
        for root in ("statistics", "metadata")
    ]
    for identity, owner in entries:
        _identifier.validate_python(identity)
        if identity in owners and owners[identity] != owner:
            raise ValueError(
                "Canonical SST product/collection/dataset/artifact identities collide"
            )
        owners[identity] = owner


def _day_interval(day, calendar):
    begin = datetime.combine(date.fromisoformat(day), time(), ZoneInfo(calendar))
    try:
        finish = begin + timedelta(days=1)
    except OverflowError as exc:
        raise AdapterUnavailable(
            "SST calendar boundary is outside supported range"
        ) from exc
    return begin.astimezone(timezone.utc), finish.astimezone(timezone.utc)


def _filter_bounds(filters):
    lower, upper, exclusive = time_bounds(filters.time_from, filters.time_to)
    # Shared time scope has inclusive timestamp endpoints and exclusive ends
    # for date-only upper bounds. Convert only for interval containment.
    if upper is not None and not exclusive:
        try:
            upper = upper + timedelta(microseconds=1)
        except OverflowError:
            pass
    return lower, upper


def _geography(metadata, filters):
    bounds = (filters.lat_min, filters.lat_max, filters.lon_min, filters.lon_max)
    if all(value is None for value in bounds):
        return None
    if any(value is None for value in bounds):
        raise AdapterUnavailable(
            "SST geographic scope requires all four explicit bounds"
        )
    south, north, west, east = bounds
    if south > north or west > east:
        raise AdapterUnavailable("Unsupported SST geographic bounds")
    support = metadata.support
    if not (
        support.south <= south <= north <= support.north
        and support.west <= west <= east <= support.east
    ):
        raise AdapterUnavailable(
            "Requested region exceeds the retained SST spatial support"
        )
    full = bounds == (support.south, support.north, support.west, support.east)
    if metadata.observation_entity == "regional_daily_summary" and not full:
        raise AdapterUnavailable(
            "A regional SST mean cannot resolve a different geographic scope"
        )
    return bounds


def _select(data: DatasetInputs, scope):
    metadata = data.metadata
    filters = scope.sources.remote_sensing.filters
    if metadata.table.object_id is None:
        raise AdapterUnavailable(
            metadata.table.availability.reason or "SST observations unavailable"
        )
    frame = data.tables["observations"]
    if not scope.sources.remote_sensing.enabled:
        return frame.iloc[:0]
    if filters.dataset_id is not None and filters.dataset_id != metadata.dataset_id:
        return frame.iloc[:0]
    bounds = _geography(metadata, filters)
    if bounds is not None and metadata.observation_entity == "grid_observation":
        south, north, west, east = bounds
        frame = frame.loc[
            frame.lat.between(south, north) & frame.lon.between(west, east)
        ]
    if filters.time_from is not None or filters.time_to is not None:
        lower, upper = _filter_bounds(filters)
        selected = []
        for value in frame.time:
            if metadata.observation_precision == "datetime":
                selected.append(matches_time(value, filters.time_from, filters.time_to))
                continue
            begin, end = _day_interval(value, metadata.calendar)
            if (
                lower is not None
                and end <= lower
                or upper is not None
                and begin >= upper
            ):
                selected.append(False)
            elif (
                lower is not None and begin < lower or upper is not None and end > upper
            ):
                raise AdapterUnavailable(
                    "Requested time scope only partially covers a retained calendar day"
                )
            else:
                selected.append(True)
        frame = frame.loc[pd.Series(selected, index=frame.index, dtype=bool)]
    return frame.sort_values("observation_id", kind="stable")


def _coverage(data, scope, frame):
    metadata, sampling = data.metadata, data.metadata.sampling
    usable = frame.loc[frame.status.eq("valid") & frame.value.notna()]
    days = {
        observation_day(value, metadata.observation_precision, metadata.calendar)
        for value in usable.time
    }
    reason = None
    expected = None
    if sampling is None:
        reason = "No declared daily sampling contract"
    elif metadata.table.completeness != "complete":
        reason = "Incomplete observations cannot establish expected missing dates"
    else:
        bounds = _geography(metadata, scope.sources.remote_sensing.filters)
        support = metadata.support
        if bounds is not None and bounds != (
            support.south,
            support.north,
            support.west,
            support.east,
        ):
            reason = "Daily sampling contract covers the complete retained spatial support only"
        else:
            filters = scope.sources.remote_sensing.filters
            lower, upper = _filter_bounds(filters)
            zone = ZoneInfo(metadata.calendar)
            contract_begin, _ = _day_interval(sampling.start, metadata.calendar)
            _, contract_end = _day_interval(sampling.end, metadata.calendar)
            if any(
                boundary is not None and boundary.astimezone(zone).time() != time()
                for boundary in (lower, upper)
            ):
                reason = "Time scope does not align with the declared daily sampling calendar"
            elif (
                lower is not None
                and lower < contract_begin
                or upper is not None
                and upper > contract_end
                or lower is not None
                and lower >= contract_end
                or upper is not None
                and upper <= contract_begin
            ):
                reason = "Requested time scope extends outside the declared sampling contract"
            else:
                expected = set()
                cursor, last = (
                    date.fromisoformat(sampling.start),
                    date.fromisoformat(sampling.end),
                )
                for step in range((last - cursor).days + 1):
                    day = (cursor + timedelta(days=step)).isoformat()
                    begin, end = _day_interval(day, metadata.calendar)
                    if (lower is None or begin >= lower) and (
                        upper is None or end <= upper
                    ):
                        expected.add(day)
    missing = None if expected is None else sorted(expected - days)
    return {
        "calendar": metadata.calendar,
        "observation_entity": metadata.observation_entity,
        "observed_observations": len(usable),
        "observed_days": len(days),
        "expected_days": None if expected is None else len(expected),
        "missing_days": None if missing is None else len(missing),
        "missing_dates": missing,
        "coverage_state": "unknown" if expected is None else "known",
        "reason": reason,
    }


class FrozenSSTCatalogueAdapter(FrozenCatalogueAdapter):
    """Reuse C08 list/open/count transport; replace every scientific data hook."""

    def __init__(self, *, store, access: SSTAccess):
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
            if family != "remote_sensing"
        ):
            raise ValueError("C11 supports only the SST source selection")
        manifest, contents = self.store.read(request.snapshot_id)
        if any(
            getattr(manifest.scope.sources, family).filters.model_dump(
                exclude_none=True
            )
            or getattr(getattr(manifest.scope.sources, family), "analysis_id", None)
            is not None
            for family in FAMILIES
        ):
            raise AdapterUnavailable("C11 requires whole-source snapshot exports")
        if request.scope.sources.remote_sensing.enabled and not any(
            source.source_family == "remote_sensing"
            for source in manifest.source_captures
        ):
            raise AdapterUnavailable("SST source is absent from this frozen snapshot")
        rows = decoded = 0
        for obj in manifest.objects:
            if (
                obj.source_family == "remote_sensing"
                and obj.schema_version == TABLE_VERSION
            ):
                footer = pq.ParquetFile(BytesIO(contents[obj.object_id])).metadata
                rows += footer.num_rows
                decoded += sum(
                    footer.row_group(i).total_byte_size
                    for i in range(footer.num_row_groups)
                )
                if rows > MAX_ROWS or decoded > MAX_DECODED_BYTES:
                    raise ValueError("C11 complete snapshot decode budget exceeded")
        datasets, known, actual_bytes = {}, set(), 0
        owners = {
            identity: ("reserved",)
            for identity in ("root:data", "root:statistics", "root:metadata", "c11:sst")
        }
        for obj in manifest.objects:
            if obj.source_family != "remote_sensing":
                continue
            if obj.role == "dataset_metadata" and obj.schema_version == DATASET_VERSION:
                data = load_dataset(manifest, contents, obj)
                if data.metadata.dataset_id in known:
                    raise ValueError("Duplicate SST dataset metadata")
                known.add(data.metadata.dataset_id)
                actual_bytes += sum(
                    frame.attrs.get("decoded_bytes", 0)
                    for frame in data.tables.values()
                )
                if actual_bytes > MAX_DECODED_BYTES:
                    raise ValueError("C11 actual snapshot decode budget exceeded")
                _register_identities(owners, data)
                detached = SSTDataset.model_validate(
                    data.metadata.model_dump(mode="json")
                )
                if self.access.eligible(request.snapshot_id, detached) is True:
                    datasets[data.metadata.dataset_id] = data
        if known != {
            obj.dataset_id
            for obj in manifest.objects
            if obj.source_family == "remote_sensing"
        }:
            raise AdapterUnavailable("Snapshot requires source-owned C11 SST metadata")
        return datasets

    @staticmethod
    def _membership(datasets, scope):
        if not scope.sources.remote_sensing.enabled:
            return {}
        filters = scope.sources.remote_sensing.filters
        result = {}
        for identity, data in datasets.items():
            if filters.dataset_id is not None and filters.dataset_id != identity:
                continue
            # Unavailable products retain their explicit state in the inventory;
            # a missing observation table is not evidence of zero matches.
            _geography(data.metadata, filters)
            if any(
                value is not None
                for key, value in filters.model_dump().items()
                if key != "dataset_id"
            ):
                if _select(data, scope).empty:
                    if data.metadata.table.completeness != "complete":
                        raise AdapterUnavailable(
                            "Incomplete SST observations cannot establish scoped dataset absence"
                        )
                    continue
            result[identity] = data
        return result

    @staticmethod
    def _nodes(datasets, request):
        nodes, owners = {}, {}

        def add(
            identity, kind, root, parent, title, *, data=None, table=False, related=None
        ):
            owner = None if data is None else data.metadata.source_id
            if identity in nodes:
                if (
                    owners[identity] != owner
                    or nodes[identity].kind != kind
                    or nodes[identity].parent_id != parent
                ):
                    raise ValueError(
                        "Canonical SST product/collection/dataset identities collide"
                    )
                return
            metadata = None if data is None else data.metadata
            available = metadata is None or metadata.table.object_id is not None
            complete = metadata is None or metadata.table.completeness == "complete"
            operations = []
            if kind in {"dataset", "table"}:
                for operation in OPERATIONS:
                    usable = available and (
                        complete
                        or operation in {"c11.table", "c11.coverage", "c11.grid_points"}
                    )
                    if operation == "c11.grid_points":
                        usable = (
                            usable and metadata.observation_entity == "grid_observation"
                        )
                    operations.append(
                        {
                            "id": operation,
                            "version": ADAPTER_VERSION,
                            "kind": "inventory"
                            if operation == "c11.count"
                            else "descriptive",
                            "required_permission": "catalogue.read",
                            "availability": {"status": "available"}
                            if usable
                            else {
                                "status": "unavailable",
                                "reason": "Required complete SST inputs or grid observations unavailable",
                            },
                        }
                    )
            provenance = (
                {}
                if data is None or kind == "directory"
                else next(
                    obj.provenance.model_dump(mode="json")
                    for obj in data.objects
                    if obj.role == "dataset_metadata"
                )
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
                    "purpose": metadata.purpose
                    if kind in {"dataset", "table"}
                    else title,
                    "availability": metadata.table.availability
                    if metadata is not None and kind in {"dataset", "table"}
                    else {"status": "available"},
                    "authority": "descriptive",
                    "lifecycle": {
                        "ingestion": "complete"
                        if complete
                        else "partial"
                        if available
                        else "unknown",
                        "publication": "unpublished",
                        "scientific_approval": "not_reviewed",
                        "query_readiness": "ready" if available else "not_ready",
                        "embedding_readiness": "unknown",
                    },
                    "provenance": provenance,
                    "source_family": None if data is None else "remote_sensing",
                    "descriptor": metadata.descriptor if kind == "dataset" else None,
                    "sections": list(DATASET_SECTIONS) if kind == "dataset" else [],
                    "operations": operations,
                    "related_ids": related or [],
                }
            )
            owners[identity] = owner

        for root, title in (
            ("data", "Data"),
            ("statistics", "Statistics"),
            ("metadata", "Metadata"),
        ):
            add(f"root:{root}", "root", root, None, {"en": title, "ja": title})
        add(
            "c11:sst",
            "directory",
            "data",
            "root:data",
            {"en": "SST products", "ja": "海面水温プロダクト"},
        )
        for identity, data in sorted(datasets.items()):
            metadata = data.metadata
            label = f"{metadata.descriptor.product_id} {metadata.descriptor.product_version} ({metadata.processing_generation})"
            add(
                metadata.product_node_id,
                "directory",
                "data",
                "c11:sst",
                {"en": label, "ja": label},
                data=data,
            )
            add(
                metadata.collection_id,
                "directory",
                "data",
                metadata.product_node_id,
                {"en": metadata.collection_id, "ja": metadata.collection_id},
                data=data,
            )
            add(
                identity,
                "dataset",
                "data",
                metadata.collection_id,
                metadata.title,
                data=data,
            )
            table_id = (
                metadata.table.object_id or f"{identity}:unavailable:observations"
            )
            add(
                table_id,
                "table",
                "data",
                identity,
                {"en": "Observations", "ja": "観測"},
                data=data,
                table=True,
            )
            for root in ("statistics", "metadata"):
                add(
                    _reference_id(root, identity),
                    "reference",
                    root,
                    f"root:{root}",
                    metadata.title,
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

    def query(self, request: OperationRequest | dict) -> SSTResponse:
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
                "C11 requires one dataset and a supported versioned operation"
            )
        params = Parameters.model_validate(request.parameters)
        if (
            request.operation_id not in {"c11.table", "c11.grid_points"}
            and params.offset
        ):
            raise ValueError("SST aggregate operations cannot skip result rows")
        data = self._load(request).get(request.input_ids[0])
        if data is None:
            raise AdapterAccessDenied("Catalogue identity unavailable")
        try:
            if not request.scope.sources.remote_sensing.enabled:
                raise AdapterUnavailable("Requested SST source is disabled")
            if (
                request.operation_id == "c11.grid_points"
                and data.metadata.observation_entity != "grid_observation"
            ):
                raise AdapterUnavailable(
                    "Underlying grid observations were not retained; regional means cannot recreate them"
                )
            frame = _select(data, request.scope)
            if (
                request.operation_id in {"c11.count", "c11.summary"}
                and data.metadata.table.completeness != "complete"
            ):
                raise AdapterUnavailable(
                    "Exact SST aggregates require complete frozen observations"
                )
            rows, columns = self._execute(data, request, frame)
            return self._response(
                data, request, params, columns, rows, data.metadata.table.completeness
            )
        except AdapterUnavailable as exc:
            return self._response(
                data, request, params, [], [], "unavailable", str(exc)
            )

    @staticmethod
    def _execute(data, request, frame):
        metadata = data.metadata
        unit, entity = metadata.descriptor.unit, metadata.observation_entity
        denominator = f"Usable {entity} measurements in the complete matching frozen product dataset"
        good = frame.loc[frame.status.eq("valid")]
        values = good.value.dropna().astype(float)
        if request.operation_id in {"c11.table", "c11.grid_points"}:
            rows = [
                {key: None if pd.isna(value) else value for key, value in row.items()}
                for row in frame.to_dict("records")
            ]
            return rows, [
                (
                    key,
                    unit
                    if key in {"value", "uncertainty"}
                    else "degree"
                    if key in {"lat", "lon"}
                    else "fraction"
                    if key == "valid_fraction"
                    else "pixels"
                    if key in {"valid_ocean_pixels", "ocean_pixels"}
                    else None,
                )
                for key in TABLE_COLUMNS
            ]
        if request.operation_id == "c11.count":
            row = {
                "count": len(values),
                "entity": entity,
                "denominator": denominator,
                "invalid_count": int(frame.status.eq("invalid").sum()),
                "excluded_count": int(frame.status.eq("excluded").sum()),
                "missing_value_count": int(good.value.isna().sum()),
            }
        elif request.operation_id == "c11.summary":
            row = {
                "measurement": "sea_surface_temperature",
                "unit": unit,
                "n_observed": len(values),
                "n_missing": int(good.value.isna().sum()),
                "n_zero": int(values.eq(0).sum()),
                "minimum": float(values.min()) if len(values) else None,
                "maximum": float(values.max()) if len(values) else None,
                "mean": float(values.mean()) if len(values) else None,
                "entity": entity,
                "denominator": denominator,
            }
        else:
            row = _coverage(data, request.scope, frame)
        return [row], [
            (key, unit if key in {"minimum", "maximum", "mean"} else None)
            for key in row
        ]

    @staticmethod
    def _response(data, request, params, columns, rows, completeness, reason=None):
        if params.offset > len(rows) and reason is None:
            raise ValueError("Offset exceeds retained SST result")
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
                "references": [data.metadata.qualification],
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
                "reason": reason or "SST input completeness is not established",
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
            "c11:receipt:"
            + hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
        )
        metadata = data.metadata
        return SSTResponse.model_validate(
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
                "offset": params.offset,
                "next_offset": params.offset + len(selected)
                if params.offset + len(selected) < len(rows)
                else None,
                "qualifications": [
                    metadata.qualification,
                    metadata.spatial_resolution_basis,
                    metadata.aggregation_method,
                    metadata.quality_policy,
                    metadata.uncertainty_policy,
                    f"Calendar: {metadata.calendar}; precision: {metadata.observation_precision}; product generation: {metadata.processing_generation}",
                    "Descriptive frozen inputs; current access and scientific eligibility are supplied independently",
                    "Observed days count dates with at least one usable retained measurement; daily coverage does not establish complete spatial grid-cell coverage",
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
                operation_id="c11.coverage",
                operation_version=ADAPTER_VERSION,
                input_ids=[identity],
                access_binding=request.access_binding,
                access_revision=request.access_revision,
            )
        )
        return {
            "node": node,
            "overview": data.metadata.model_dump(
                mode="json", exclude={"table", "methods", "related_ids"}
            ),
            "tables": [data.metadata.table.model_copy(deep=True)],
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
