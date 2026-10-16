"""Context Catalogue v1: immutable identities and explicit inventory semantics.

These are transport contracts, not an authorization service or scientific approval.
Cursor helpers bind local traversal context; a later authenticated service must
re-evaluate access before using any cursor. EvidenceScope and C01 eligibility
retain their existing independent scientific meanings.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import struct
from functools import cmp_to_key
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from orchestration.publication_scope import (
    ScopeCompatibility,
    VERSION as PUBLICATION_SCOPE_VERSION,
)
from retrieval.source_scope import ALIASES, EvidenceScope
from schema.time_range import time_bounds

SCHEMA_VERSION = "context-catalogue-v1"
ROOTS = ("data", "analyses", "statistics", "metadata", "relationships")
DATASET_SECTIONS = (
    "overview",
    "tables",
    "coverage",
    "methods",
    "provenance",
    "related",
)
SourceFamily = Literal["ctd", "metagenome", "remote_sensing", "edna_metabarcoding"]
Root = Literal["data", "analyses", "statistics", "metadata", "relationships"]
NodeKind = Literal[
    "root",
    "directory",
    "dataset",
    "table",
    "analysis",
    "statistic",
    "metadata",
    "relationship",
    "reference",
    "workflow",
]
Authority = Literal["descriptive", "published", "experimental"]
Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    ),
]
TextValue = Annotated[
    str, StringConstraints(min_length=1, max_length=4000, pattern=r"\S")
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


def _integer_number(value):
    # JSON has one number kind; integral 1.0 and 1 denote the same wire value.
    if type(value) is float and math.isfinite(value) and value.is_integer():
        return int(value)
    return value


NonnegativeInt = Annotated[
    int, Field(strict=True, ge=0, le=9007199254740991), BeforeValidator(_integer_number)
]
PageLimit = Annotated[
    int, Field(strict=True, ge=1, le=500), BeforeValidator(_integer_number)
]
Completion = Literal["complete", "partial", "unknown", "unavailable"]
QueryCompletion = Literal["not_started", "complete", "partial", "failed"]


def canonical_source_family(value: str) -> SourceFamily:
    """Preserve the existing positive legacy alias registry; never guess a family."""
    if not isinstance(value, str) or value.strip().lower() not in ALIASES:
        raise ValueError("Unknown source family")
    return ALIASES[value.strip().lower()]


def canonical_json(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _finite_json(value, _depth=0, _seen=None):
    if _depth > 128:
        raise ValueError("JSON nesting exceeds the contract depth limit")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite JSON numbers are forbidden")
    if (type(value) is int or type(value) is float and value.is_integer()) and abs(
        value
    ) > 9007199254740991:
        raise ValueError(
            "Integral JSON values must fit the exact browser integer range; encode larger exact values as text"
        )
    if isinstance(value, (dict, list, tuple)):
        seen = set() if _seen is None else _seen
        identity = id(value)
        if identity in seen:
            raise ValueError("Cyclic values are not JSON")
        seen.add(identity)
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("JSON object keys must be strings")
            children = value.values()
        else:
            children = value
        for child in children:
            _finite_json(child, _depth + 1, seen)
        seen.remove(identity)
    return value


def _strict_scope(value):
    """Use EvidenceScope validation, with a strict JSON primitive boundary."""
    if isinstance(value, EvidenceScope):
        value = value.model_dump()
    if isinstance(value, dict):
        value = {**value}
        if "version" in value:
            value["version"] = _integer_number(value["version"])
        sources = value.get("sources")
        if not isinstance(sources, dict):
            raise ValueError("Scope sources must be an object")
        for selection in sources.values():
            if not isinstance(selection, dict):
                continue
            filters = selection.get("filters")
            if not isinstance(filters, dict):
                raise ValueError("Scope filters must be an object")
            for key, item in filters.items():
                if item is None:
                    continue
                if key in ("lat_min", "lat_max", "lon_min", "lon_max"):
                    if type(item) not in (int, float) or not math.isfinite(item):
                        raise ValueError(
                            "Scope coordinates must be finite JSON numbers"
                        )
                elif key == "is_control":
                    if type(item) is not bool:
                        raise ValueError("Scope control flag must be a boolean")
                elif not isinstance(item, str):
                    raise ValueError("Scope text filters must be strings")
                elif item != item.strip():
                    raise ValueError("Scope text must have no surrounding whitespace")
                elif key in ("time_from", "time_to") and not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?)?",
                    item,
                ):
                    raise ValueError(
                        "Catalogue dates use YYYY-MM-DD or ISO seconds with optional timezone"
                    )
            try:
                time_bounds(filters.get("time_from"), filters.get("time_to"))
            except OverflowError as exc:
                raise ValueError(
                    "Catalogue time bounds exceed the supported UTC calendar"
                ) from exc
    return value


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ScopedEnvelope(ContractModel):
    schema_version: Literal["context-catalogue-v1"] = SCHEMA_VERSION
    snapshot_id: Identifier
    scope: EvidenceScope

    @field_validator("scope", mode="before")
    @classmethod
    def strict_scope(cls, value):
        return _strict_scope(value)


class LocalizedText(ContractModel):
    en: TextValue
    ja: TextValue


class Availability(ContractModel):
    status: Literal["available", "unknown", "unavailable"]
    reason: TextValue | None = None

    @model_validator(mode="after")
    def qualification(self):
        if self.status != "available" and self.reason is None:
            raise ValueError("Unknown/unavailable availability requires a reason")
        return self


class Lifecycle(ContractModel):
    ingestion: Literal["not_ingested", "partial", "complete", "unknown"]
    publication: Literal["unpublished", "published", "withdrawn", "unknown"]
    scientific_approval: Literal["not_reviewed", "approved", "rejected", "unknown"]
    query_readiness: Literal["ready", "not_ready", "unsupported", "unknown"]
    embedding_readiness: Literal["ready", "not_ready", "unsupported", "unknown"]


class TransferOrigin(ContractModel):
    """Descriptive copied-data provenance; never a live access authorization."""

    origin_system: Identifier
    origin_object_id: TextValue
    source_snapshot_id: Identifier
    source_generation: TextValue
    schema_version: TextValue
    operation_version: TextValue
    content_sha256: Sha256
    scientific_qualification: TextValue
    access_conditions: TextValue
    transfer_authorization_ref: TextValue
    live_dependency: Literal[False] = False

    @field_validator("live_dependency", mode="before")
    @classmethod
    def no_live_dependency(cls, value):
        if value is not False:
            raise ValueError("An origin reference cannot authorize a live dependency")
        return value


class Provenance(ContractModel):
    source_generation: TextValue | None = None
    content_sha256: Sha256 | None = None
    origin: TransferOrigin | None = None
    references: list[TextValue] = Field(default_factory=list)


class OperationDescriptor(ContractModel):
    id: Identifier
    version: Identifier
    kind: Literal["inventory", "descriptive", "published_synthesis", "experimental"]
    required_permission: Identifier
    availability: Availability


class CTDDescriptor(ContractModel):
    family: Literal["ctd"]
    sampling_contract: TextValue
    observation_entity: Literal["cast", "depth_observation"]
    measurement: TextValue
    unit: TextValue
    depth_unit: Literal["m", "dbar"]


class SSTDescriptor(ContractModel):
    family: Literal["remote_sensing"]
    product_id: Identifier
    product_version: TextValue
    spatial_resolution: float = Field(gt=0)
    spatial_resolution_unit: Literal["degree", "km", "m"]
    temporal_resolution: TextValue
    measurement: Literal["sea_surface_temperature"]
    unit: Literal["degC", "K"]
    spatial_role: Literal["native_grid", "coarse_context", "regional_summary"]

    @field_validator("spatial_resolution", mode="before")
    @classmethod
    def numeric_resolution(cls, value):
        if type(value) not in (int, float):
            raise ValueError("Resolution must be a number")
        return value


class MetagenomeDescriptor(ContractModel):
    family: Literal["metagenome"]
    measurement: TextValue
    abundance_unit: TextValue
    abundance_denominator: TextValue
    method: TextValue
    taxonomic_rank: TextValue
    omitted_taxa: Literal["unknown", "not_measured", "retained_elsewhere"]


class EDNADescriptor(ContractModel):
    family: Literal["edna_metabarcoding"]
    protocol_id: Identifier
    protocol: TextValue
    # Descriptive raw inventory is a separate population, never permission to
    # execute a method unsupported by C01 scientific scope/analysis recipes.
    population: Literal["scientific", "raw_inventory"] = "scientific"
    assignment_method: Literal[
        "qcauto_target", "qcauto_95pct_3nn_target", "qcauto_nontarget",
        "qcauto_95pct_3nn_nontarget", "mixed", "unknown",
    ]
    sample_kind: Literal[
        "environmental",
        "negative_control",
        "positive_control",
        "mock_community",
        "unknown",
        "mixed",
    ]
    is_control: bool | None
    measurement: TextValue
    unit: TextValue

    @model_validator(mode="after")
    def controls(self):
        if self.population == "scientific" and (
            self.assignment_method not in {"qcauto_target", "qcauto_95pct_3nn_target"}
            or self.sample_kind == "mixed"
        ):
            raise ValueError("Scientific descriptors require a supported target method and one sample kind")
        if self.sample_kind == "mixed" and self.is_control is not None:
            raise ValueError("Mixed inventory cannot declare one control status")
        if self.population == "raw_inventory" and self.sample_kind == "unknown" and self.is_control is not None:
            raise ValueError("Unknown raw classification requires unknown control status")
        if (
            self.sample_kind == "environmental"
            and self.is_control is not False
            or self.sample_kind
            in ("negative_control", "positive_control", "mock_community")
            and self.is_control is not True
        ):
            raise ValueError("Sample kind and control status conflict")
        return self


ScientificDescriptor = Annotated[
    CTDDescriptor | SSTDescriptor | MetagenomeDescriptor | EDNADescriptor,
    Field(discriminator="family"),
]


class CatalogueNode(ScopedEnvelope):
    id: Identifier
    kind: NodeKind
    root: Root
    parent_id: Identifier | None
    title: LocalizedText
    purpose: LocalizedText
    availability: Availability
    authority: Authority
    lifecycle: Lifecycle
    provenance: Provenance
    source_family: SourceFamily | None = None
    descriptor: ScientificDescriptor | None = None
    sections: list[
        Literal["overview", "tables", "coverage", "methods", "provenance", "related"]
    ] = Field(default_factory=list)
    operations: list[OperationDescriptor] = Field(default_factory=list)
    related_ids: list[Identifier] = Field(default_factory=list)
    membership: Literal["global", "private"] = "global"
    owner_id: Identifier | None = None

    @model_validator(mode="after")
    def semantics(self):
        if self.kind == "root" and (
            self.parent_id is not None or self.id != f"root:{self.root}"
        ):
            raise ValueError("Root identity must be root:<root> and have no parent")
        if self.kind != "root" and self.parent_id is None:
            raise ValueError("Non-root objects require a parent identity")
        if self.parent_id == self.id or self.id in self.related_ids:
            raise ValueError("A node cannot be its own parent or related link")
        if len(self.related_ids) != len(set(self.related_ids)):
            raise ValueError("Related links reference distinct canonical identities")
        if self.kind == "dataset":
            if (
                self.root != "data"
                or self.source_family is None
                or self.descriptor is None
            ):
                raise ValueError(
                    "Datasets require Data root and source-specific scientific semantics"
                )
            if tuple(self.sections) != DATASET_SECTIONS:
                raise ValueError("Datasets expose all six ordered sections")
        if self.descriptor is not None and self.descriptor.family != self.source_family:
            raise ValueError("Descriptor and source family must agree")
        if (
            self.source_family is not None
            and not getattr(self.scope.sources, self.source_family).enabled
        ):
            raise ValueError("A source-owned node must enable that source in its scope")
        if self.membership == "private" and self.owner_id is None:
            raise ValueError("Private membership requires an owner identity")
        if self.membership == "global" and self.owner_id is not None:
            raise ValueError("Global nodes cannot have a private owner")
        if (
            self.root == "analyses"
            and self.authority == "experimental"
            and self.membership != "private"
        ):
            raise ValueError(
                "Experimental results do not join global published analyses"
            )
        if self.authority == "published" and self.lifecycle.publication != "published":
            raise ValueError("Published authority requires a published lifecycle")
        if len({operation.id for operation in self.operations}) != len(self.operations):
            raise ValueError("Supported operation identities must be unique")
        return self


class CatalogueCount(ContractModel):
    state: Literal["known", "unknown"]
    entity: Literal[
        "canonical_objects",
        "datasets",
        "observations",
        "source_occurrences",
        "assays",
        "detection_rows",
        "rows",
    ]
    denominator: TextValue
    basis: Literal["complete_scope"] = "complete_scope"
    value: NonnegativeInt | None = None
    reason: TextValue | None = None

    @model_validator(mode="after")
    def explicit_unknown(self):
        if self.state == "known" and self.value is None:
            raise ValueError(
                "Known counts require an exact integer value, including zero"
            )
        if self.state == "unknown" and (self.value is not None or self.reason is None):
            raise ValueError("Unknown counts require a reason and no numeric value")
        return self


class CatalogueFilters(ContractModel):
    roots: list[Root] = Field(default_factory=list)
    source_families: list[SourceFamily] = Field(default_factory=list)
    kinds: list[NodeKind] = Field(default_factory=list)
    search: TextValue | None = None
    authorities: list[Authority] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_filters(self):
        for name in ("roots", "source_families", "kinds", "authorities"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError("Filter sets cannot contain duplicate values")
        return self


class Ordering(ContractModel):
    field: Literal["id", "title"]
    direction: Literal["asc", "desc"] = "asc"


class ListingRequest(ScopedEnvelope):
    parent_id: Identifier | None = None
    filters: CatalogueFilters = Field(default_factory=CatalogueFilters)
    ordering: list[Ordering] = Field(
        default_factory=lambda: [Ordering(field="id")], min_length=1, max_length=2
    )
    access_revision: Identifier
    access_binding: Identifier
    limit: PageLimit = 100
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def stable_order(self):
        if self.ordering[-1].field != "id" or len(
            {item.field for item in self.ordering}
        ) != len(self.ordering):
            raise ValueError(
                "Ordering requires exactly one final canonical ID tie-breaker"
            )
        if self.cursor is not None:
            validate_cursor(self)
        return self


def cursor_context(request: ListingRequest) -> str:
    """Canonical full request binding, excluding only the cursor itself."""
    payload = request.model_dump(mode="json", exclude={"cursor"})
    # IEEE-754 bytes avoid Python/JavaScript decimal/exponent spelling differences.
    # Integers and floats denoting the same coordinate bind the same scope.
    for selection in payload["scope"]["sources"].values():
        for key in ("lat_min", "lat_max", "lon_min", "lon_max"):
            value = selection["filters"].get(key)
            if value is not None:
                selection["filters"][key] = (
                    "float64:" + struct.pack(">d", float(value)).hex()
                )
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def make_cursor(request: ListingRequest, offset: int) -> str:
    offset = _integer_number(offset)
    if type(offset) is not int or not 0 < offset <= 9007199254740991:
        raise ValueError("Cursor offset must be a positive integer")
    payload = {
        "version": SCHEMA_VERSION,
        "context_sha256": cursor_context(request),
        "offset": offset,
    }
    return (
        base64.urlsafe_b64encode(canonical_json(payload).encode()).decode().rstrip("=")
    )


def validate_cursor(request: ListingRequest, cursor: str | None = None) -> int:
    token = request.cursor if cursor is None else cursor
    if token is None:
        return 0
    try:
        if not isinstance(token, str) or len(token) > 2048:
            raise ValueError("Invalid cursor encoding")
        raw = base64.b64decode(
            token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
        )
        payload = json.loads(raw)
        if isinstance(payload, dict) and "offset" in payload:
            payload["offset"] = _integer_number(payload["offset"])
        if (
            not isinstance(payload, dict)
            or set(payload) != {"version", "context_sha256", "offset"}
            or payload["version"] != SCHEMA_VERSION
            or payload["context_sha256"] != cursor_context(request)
            or type(payload["offset"]) is not int
            or not 0 < payload["offset"] <= 9007199254740991
        ):
            raise ValueError(
                "Cursor does not bind this version/snapshot/scope/filter/order/access context"
            )
        return payload["offset"]
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ValueError("Invalid or stale catalogue cursor") from exc


def ordered_nodes(
    nodes: list[CatalogueNode], ordering: list[Ordering]
) -> list[CatalogueNode]:
    """Locale-independent Unicode code-point order; title means title.en, then ID."""

    def compare(left, right):
        for order in ordering:
            a = left.id if order.field == "id" else left.title.en
            b = right.id if order.field == "id" else right.title.en
            result = (a > b) - (a < b)
            if result:
                return result if order.direction == "asc" else -result
        return 0

    return sorted(nodes, key=cmp_to_key(compare))


class CatalogueListing(ContractModel):
    schema_version: Literal["context-catalogue-v1"] = SCHEMA_VERSION
    request: ListingRequest
    items: list[CatalogueNode]
    total: CatalogueCount
    returned_count: NonnegativeInt
    next_cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    preview_truncated: bool
    source_completeness: Completion
    query_completion: QueryCompletion
    availability: Availability

    @model_validator(mode="after")
    def reconciliation(self):
        if (
            self.returned_count != len(self.items)
            or self.returned_count > self.request.limit
        ):
            raise ValueError("Returned count must exactly describe this bounded page")
        if any(node.membership == "private" for node in self.items):
            raise ValueError(
                "Private Workspace experiments are not global catalogue inventory"
            )
        if self.items != ordered_nodes(self.items, self.request.ordering):
            raise ValueError("Items must follow the declared stable ordering")
        if len({node.id for node in self.items}) != len(self.items):
            raise ValueError(
                "A page cannot duplicate canonical identities through facets or cross-links"
            )
        if any(node.snapshot_id != self.request.snapshot_id for node in self.items):
            raise ValueError("Page items must belong to the requested snapshot")
        if self.total.entity != "canonical_objects":
            raise ValueError("Listing totals count distinct canonical objects")
        offset = validate_cursor(self.request)
        if (
            self.total.value is not None
            and offset + self.returned_count > self.total.value
        ):
            raise ValueError("Page exceeds complete-scope total")
        if self.next_cursor is not None:
            if (
                not self.items
                or validate_cursor(self.request, self.next_cursor)
                != offset + self.returned_count
            ):
                raise ValueError(
                    "Next cursor must continue immediately after this page"
                )
            if (
                self.total.value is not None
                and offset + self.returned_count >= self.total.value
            ):
                raise ValueError("A terminal known page cannot advertise another page")
        if self.preview_truncated != (self.next_cursor is not None):
            raise ValueError("Preview truncation identifies remaining inventory pages")
        if self.query_completion == "complete" and self.total.value is not None:
            if (
                offset + self.returned_count < self.total.value
            ) != self.preview_truncated:
                raise ValueError(
                    "Complete listings must preserve all remaining inventory membership"
                )
        if self.availability.status != "available" and (
            self.items or self.total.value is not None
        ):
            raise ValueError(
                "Unavailable/unknown listings cannot pretend to expose known empty inventory"
            )
        return self


class OperationRequest(ScopedEnvelope):
    operation_id: Identifier
    operation_version: Identifier
    input_ids: list[Identifier]
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    access_revision: Identifier
    access_binding: Identifier

    @field_validator("parameters", mode="before")
    @classmethod
    def finite_parameters(cls, value):
        return _finite_json(value)

    @field_validator("input_ids")
    @classmethod
    def unique_inputs(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Operation input identities must be unique")
        return value


class InputIdentity(ContractModel):
    object_id: Identifier
    content_sha256: Sha256
    source_generation: TextValue | None = None


class OperationReceipt(ScopedEnvelope):
    receipt_id: Identifier
    operation_id: Identifier
    operation_version: Identifier
    inputs: list[InputIdentity]
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    authority: Authority
    availability: Availability
    provenance: Provenance
    total_rows: CatalogueCount
    returned_count: NonnegativeInt
    preview_truncated: bool
    source_completeness: Completion
    query_completion: QueryCompletion
    content_sha256: Sha256
    scope_compatibility: ScopeCompatibility | None = None

    @field_validator("parameters", mode="before")
    @classmethod
    def finite_parameters(cls, value):
        return _finite_json(value)

    @field_validator("scope_compatibility", mode="before")
    @classmethod
    def existing_publication_contract(cls, value):
        if isinstance(value, ScopeCompatibility):
            value = value.as_dict()
        if value is not None:
            expected = {
                "version",
                "outcome",
                "reason",
                "workflow",
                "analysis_id",
                "evidence",
            }
            evidence_fields = {
                "field",
                "outcome",
                "requested",
                "registered",
                "quote",
                "source",
                "reason",
            }
            if (
                not isinstance(value, dict)
                or set(value) != expected
                or value["version"] != PUBLICATION_SCOPE_VERSION
            ):
                raise ValueError("Use the exact existing C01 publication scope receipt")
            if not isinstance(value["evidence"], (list, tuple)) or any(
                not isinstance(row, dict) or set(row) != evidence_fields
                for row in value["evidence"]
            ):
                raise ValueError(
                    "Use the exact existing C01 field-level evidence receipt"
                )
            value = TypeAdapter(ScopeCompatibility).validate_python(value)
        return value

    @model_validator(mode="after")
    def result_semantics(self):
        if len({item.object_id for item in self.inputs}) != len(self.inputs):
            raise ValueError("Input content identities must be unique")
        if (
            self.total_rows.value is not None
            and self.returned_count > self.total_rows.value
        ):
            raise ValueError("Returned rows cannot exceed complete-scope result count")
        if self.query_completion == "complete" and self.total_rows.value is not None:
            if (self.returned_count < self.total_rows.value) != self.preview_truncated:
                raise ValueError(
                    "Complete result previews must declare truncation precisely"
                )
        if (
            self.scope_compatibility is not None
            and self.scope_compatibility.outcome != "compatible"
            and self.query_completion == "complete"
        ):
            raise ValueError(
                "Query readiness cannot override incompatible/unresolved C01 scientific scope"
            )
        if self.availability.status != "available" and (
            self.returned_count or self.total_rows.value is not None
        ):
            raise ValueError(
                "Unavailable results cannot claim known empty scientific data"
            )
        return self


class ResultColumn(ContractModel):
    key: Identifier
    title: LocalizedText
    unit: TextValue | None = None


class QueryResult(ScopedEnvelope):
    columns: list[ResultColumn]
    rows: list[dict[str, JsonValue]]
    receipt: OperationReceipt

    @field_validator("rows", mode="before")
    @classmethod
    def finite_rows(cls, value):
        return _finite_json(value)

    @model_validator(mode="after")
    def receipt_binding(self):
        if (
            self.receipt.snapshot_id != self.snapshot_id
            or self.receipt.scope.canonical() != self.scope.canonical()
        ):
            raise ValueError(
                "Result and receipt must retain the exact snapshot and source scope"
            )
        keys = [column.key for column in self.columns]
        if len(keys) != len(set(keys)) or any(
            set(row) != set(keys) for row in self.rows
        ):
            raise ValueError("Rows must exactly match unique column identities")
        if self.receipt.returned_count != len(self.rows):
            raise ValueError("Receipt returned count must match the result rows")
        return self


class CatalogueContract(ContractModel):
    """Schema export roots; not an endpoint response requiring every envelope."""

    schema_version: Literal["context-catalogue-v1"] = SCHEMA_VERSION
    node: CatalogueNode
    listing_request: ListingRequest
    listing: CatalogueListing
    operation_request: OperationRequest
    receipt: OperationReceipt
    query_result: QueryResult
