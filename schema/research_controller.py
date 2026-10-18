"""C19 strict actions and trusted, receipt-derived completion projections.

Only actions are model input. Fact specifications, observations and dispositions
are host-owned; a model cannot submit completion claims through this boundary.
Large payloads and complete input manifests stay in the host's evidence store.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from retrieval.source_scope import EvidenceScope
from schema.catalogue_service import REQUEST_MODELS
from schema.context_catalogue import Identifier, Sha256, _finite_json, _strict_scope, canonical_json
from schema.investigations import UUIDString

MAX_ACTION_BYTES = 65536
MAX_ACTION_DEPTH = 128
TRUSTED_ARGUMENT_FIELDS = frozenset({
    "snapshot_id", "scope", "schema_version", "access_binding", "access_revision",
    "user", "user_id", "owner", "owner_id", "role", "account_type", "permissions",
    "investigation_id", "conversation_id", "revision_id", "payload_sha256",
    "identity", "authorization", "database", "database_url",
})
ToolName = Literal[
    "catalogue.overview", "catalogue.list", "catalogue.open", "catalogue.coverage",
    "catalogue.query", "catalogue.relationships", "analysis.get_published",
]
Completion = Literal["complete", "partial", "unknown", "unavailable"]
Availability = Literal["available", "unknown", "unavailable"]
QueryCompletion = Literal["not_started", "complete", "partial", "failed"]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
PositiveInt = Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
Text = Annotated[str, Field(min_length=1, max_length=10000)]


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


def canonical_hash(value) -> str:
    _finite_json(value)
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_scope_json(value: EvidenceScope | dict | str) -> str:
    if isinstance(value, str):
        value = strict_json(value)
    if isinstance(value, EvidenceScope):
        value = value.model_dump(mode="json")
    return canonical_json(EvidenceScope.model_validate(_strict_scope(value)).canonical())


def scope_hash(value: EvidenceScope | dict | str) -> str:
    return hashlib.sha256(canonical_scope_json(value).encode("utf-8")).hexdigest()


def scientific_parameters_hash(value: dict) -> str:
    """Compare raw requests with C13 Parameters' expanded default/null fields.

    Only known outer transport defaults are removed. Native scientific keys,
    including nested limit/offset/null values, retain their exact meaning.
    """
    optional = {"table", "operation_id", "operation_version", "workflow_kind", "protocol_id"}
    return canonical_hash({
        key: item for key, item in value.items()
        if key not in {"limit", "offset"}
        and not (key in optional and item is None)
        and not (key == "parameters" and item == {})
    })


def _depth(value, level=0):
    if level > MAX_ACTION_DEPTH:
        raise ValueError("Controller JSON exceeds nesting bound")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Controller object keys must be strings")
            _depth(item, level + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _depth(item, level + 1)


def strict_json(content: str):
    if not isinstance(content, str):
        raise ValueError("Controller JSON must be text")
    try:
        if len(content.encode("utf-8")) > MAX_ACTION_BYTES:
            raise ValueError("Controller JSON exceeds byte bound")
    except UnicodeError:
        raise ValueError("Controller JSON must be UTF-8") from None

    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate controller JSON key")
            result[key] = item
        return result

    try:
        value = json.loads(content, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite controller JSON")))
        _depth(value)
        _finite_json(value)
        canonical_json(value).encode("utf-8")
        return value
    except (TypeError, UnicodeError, RecursionError):
        raise ValueError("Invalid controller JSON") from None


class ControllerBinding(FrozenContract):
    investigation_id: UUIDString
    conversation_id: UUIDString
    revision_id: UUIDString
    snapshot_id: Sha256
    payload_sha256: Sha256


class ControllerLimits(FrozenContract):
    active_seconds: Annotated[float, Field(gt=0, le=180)] = 180.0
    tool_actions: Annotated[int, Field(strict=True, ge=1, le=12)] = 12
    malformed_repairs: Annotated[int, Field(strict=True, ge=0, le=1)] = 1
    listing_default: Literal[100] = 100
    listing_maximum: Literal[500] = 500
    observation_preview_rows: Annotated[int, Field(strict=True, ge=0, le=500)] = 20
    model_context_bytes: Annotated[int, Field(strict=True, ge=1024, le=262144)] = 65536


class BudgetSnapshot(FrozenContract):
    active_elapsed_seconds: Annotated[float, Field(ge=0)] = 0.0
    tool_actions: NonnegativeInt = 0
    model_calls: NonnegativeInt = 0
    malformed_repairs: Annotated[int, Field(strict=True, ge=0, le=1)] = 0
    cancellation_requested: bool = False


class ToolAction(FrozenContract):
    kind: Literal["tool"]
    tool: ToolName
    arguments: dict
    fact_ids: list[Identifier] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_arguments(self):
        _finite_json(self.arguments)
        _depth(self.arguments)
        def trusted_keys(value):
            if isinstance(value, dict):
                if any(key in TRUSTED_ARGUMENT_FIELDS for key in value):
                    raise ValueError("Model cannot supply trusted tool fields")
                for item in value.values():
                    trusted_keys(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    trusted_keys(item)
        trusted_keys(self.arguments)
        if len(self.fact_ids) != len(set(self.fact_ids)):
            raise ValueError("Action fact IDs must be distinct")
        # Validate against C14 itself. The host replaces these placeholders at
        # dispatch; no model-provided envelope is accepted or silently stripped.
        scope = {"version": 1, "sources": {
            key: {"enabled": True, "filters": {}}
            for key in ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding")
        }}
        REQUEST_MODELS[self.tool].model_validate({
            **self.arguments, "snapshot_id": "0" * 64, "scope": scope,
        })
        if len(canonical_json(self.arguments).encode("utf-8")) > MAX_ACTION_BYTES:
            raise ValueError("Tool arguments exceed byte bound")
        return self


class ClarifyAction(FrozenContract):
    kind: Literal["clarify"]
    fact_ids: list[Identifier] = Field(min_length=1, max_length=32)
    reason: Literal["scope_conflict", "pin_unresolved", "ambiguous_request", "unsupported_request", "missing_information"]

    @field_validator("fact_ids")
    @classmethod
    def distinct(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Action fact IDs must be distinct")
        return value


class FinishAction(FrozenContract):
    kind: Literal["finish"]


ControllerAction = Annotated[ToolAction | ClarifyAction | FinishAction, Field(discriminator="kind")]
ACTION_ADAPTER = TypeAdapter(ControllerAction)


def controller_action_schema() -> dict:
    return ACTION_ADAPTER.json_schema()


def parse_controller_action(content: str, *, fact_ids: tuple[str, ...] | None = None) -> ControllerAction:
    action = ACTION_ADAPTER.validate_python(strict_json(content))
    if fact_ids is not None and any(value not in fact_ids for value in getattr(action, "fact_ids", ())):
        raise ValueError("Action refers to an unknown requested fact")
    return action


class FactSpec(FrozenContract):
    """Host-owned requested fact; never extracted from a model finish claim."""
    fact_id: Identifier
    kind: Literal["count", "find", "coverage", "operation", "publication"]
    scope_sha256: Sha256
    required: bool = True
    target_ids: tuple[Identifier, ...] = ()
    entity: Identifier | None = None
    denominator: Text | None = None
    object_id: Identifier | None = None
    exact_name: Text | None = None
    operation_id: Identifier | None = None
    operation_version: Identifier | None = None
    parameters_sha256: Sha256 | None = None
    required_fields: tuple[Identifier, ...] = ()
    analysis_id: Identifier | None = None
    workflow_kind: Identifier | None = None
    protocol_id: Identifier | None = None
    required_tables: tuple[Identifier, ...] = ()
    question_compatibility_sha256: Sha256 | None = None
    requires_complete_source: bool = False

    @model_validator(mode="after")
    def required_contract(self):
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("Fact targets must be distinct")
        if self.kind == "count" and not (self.entity and self.operation_id and self.operation_version):
            raise ValueError("Count fact needs semantic entity and registered operation/version")
        if self.kind == "find" and (self.object_id is None) == (self.exact_name is None):
            raise ValueError("Find fact needs exactly one canonical identity or exact name")
        if self.kind == "coverage" and (not self.target_ids or not self.required_fields):
            raise ValueError("Coverage fact needs targets and requested known fields")
        if self.kind == "operation" and not (self.operation_id and self.operation_version and self.parameters_sha256):
            raise ValueError("Operation fact needs exact operation/version/parameters")
        if self.kind == "publication" and not (self.analysis_id and self.workflow_kind and self.required_tables and self.question_compatibility_sha256):
            raise ValueError("Publication fact needs actual-question compatibility and all required tables")
        return self


class SemanticCount(FrozenContract):
    state: Literal["known", "unknown"]
    entity: Identifier
    denominator: Text
    value: NonnegativeInt | None = None
    reason: Text | None = None
    basis: Literal["complete_scope"] = "complete_scope"

    @model_validator(mode="after")
    def known_or_unknown(self):
        if self.state == "known" and self.value is None:
            raise ValueError("Known semantic count requires a value, including zero")
        if self.state == "unknown" and (self.value is not None or self.reason is None):
            raise ValueError("Unknown semantic count needs a reason and no value")
        return self


class ObjectWitness(FrozenContract):
    object_id: Identifier
    exact_names: tuple[Text, ...] = ()


class Observation(FrozenContract):
    """Trusted validated payload projection; full rows/inputs remain external."""
    observation_id: Identifier
    binding: ControllerBinding
    tool: ToolName
    scope_json: str
    full_payload_ref: Identifier
    full_payload_sha256: Sha256
    operation_id: Identifier | None = None
    operation_version: Identifier | None = None
    parameters_sha256: Sha256 | None = None
    target_ids: tuple[Identifier, ...] = ()
    input_count: NonnegativeInt = 0
    input_sha256: Sha256 = canonical_hash([])
    availability: Availability
    source_completeness: Completion
    query_completion: QueryCompletion
    qualifications: tuple[Text, ...] = ()
    counts: tuple[SemanticCount, ...] = ()
    objects: tuple[ObjectWitness, ...] = ()
    known_fields: tuple[Identifier, ...] = ()
    output_fields: tuple[Identifier, ...] = ()
    analysis_id: Identifier | None = None
    workflow_kind: Identifier | None = None
    protocol_id: Identifier | None = None
    table_names: tuple[Identifier, ...] = ()
    question_compatibility_sha256: Sha256 | None = None
    authority: Literal["descriptive", "published", "experimental"] = "descriptive"
    result_content_sha256: Sha256 | None = None
    page_offset: NonnegativeInt = 0
    page_returned_count: NonnegativeInt = 0
    page_total_rows: NonnegativeInt | None = None
    next_offset: NonnegativeInt | None = None
    preview_truncated: bool = False
    preview_json: str = "[]"

    @field_validator("scope_json")
    @classmethod
    def scope_canonical(cls, value):
        return canonical_scope_json(value)

    @field_validator("preview_json")
    @classmethod
    def bounded_preview(cls, value):
        preview = strict_json(value)
        if not isinstance(preview, list) or len(preview) > 500:
            raise ValueError("Observation preview must be at most 500 rows")
        return canonical_json(preview)

    @property
    def scope_sha256(self):
        return hashlib.sha256(self.scope_json.encode("utf-8")).hexdigest()


class DatasetDisposition(FrozenContract):
    cohort_id: Identifier
    input_count: NonnegativeInt
    input_sha256: Sha256
    state: Literal["pending", "covered", "unresolved", "unavailable", "excluded"]
    required: bool = True
    fact_ids: tuple[Identifier, ...] = ()
    observation_ids: tuple[Identifier, ...] = ()
    reason: Text | None = None
    exclusion_verified: bool = False


class FactAssessment(FrozenContract):
    fact_id: Identifier
    required: bool = True
    state: Literal["supported", "pending", "unresolved"]
    observation_ids: tuple[Identifier, ...] = ()
    value_json: str | None = None
    reason: Text | None = None

    @model_validator(mode="after")
    def support_needs_witness(self):
        if self.state == "supported" and not self.observation_ids:
            raise ValueError("Supported facts need executed observation witnesses")
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("Fact observation witnesses must be distinct")
        return self

    @property
    def status(self):
        return self.state


class CompletionAssessment(FrozenContract):
    complete: bool
    facts: tuple[FactAssessment, ...]
    unresolved_cohorts: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def no_false_completion(self):
        if len({fact.fact_id for fact in self.facts}) != len(self.facts):
            raise ValueError("Fact assessments must have distinct identities")
        if self.complete and (not any(fact.required for fact in self.facts)
                              or any(fact.required and fact.state != "supported" for fact in self.facts)
                              or self.unresolved_cohorts):
            raise ValueError("Unresolved facts or cohorts cannot claim completion")
        return self


def _compatible(fact: FactSpec, observation: Observation, binding: ControllerBinding | None):
    return (
        (binding is None or observation.binding == binding)
        and observation.scope_sha256 == fact.scope_sha256
        and (not fact.target_ids or set(fact.target_ids) <= set(observation.target_ids))
        and observation.availability == "available"
        and observation.query_completion == "complete"
        and (not fact.requires_complete_source or observation.source_completeness == "complete")
        and (fact.operation_id is None or fact.operation_id == observation.operation_id)
        and (fact.operation_version is None or fact.operation_version == observation.operation_version)
        and (fact.parameters_sha256 is None or fact.parameters_sha256 == observation.parameters_sha256)
    )


def _complete_publication_table(pages: list[Observation]) -> bool:
    """Prove complete immutable table coverage, independently of row previews."""
    if not pages or any(page.result_content_sha256 is None or page.page_total_rows is None
                        or page.parameters_sha256 is None for page in pages):
        return False
    identities = {
        (page.result_content_sha256, page.page_total_rows, page.parameters_sha256,
         page.operation_id, page.operation_version, page.input_count, page.input_sha256,
         page.target_ids) for page in pages
    }
    if len(identities) != 1:
        return False
    total = pages[0].page_total_rows
    offset = 0
    for page in sorted(pages, key=lambda value: value.page_offset):
        returned = page.page_returned_count
        if page.page_offset != offset or page.page_offset + returned > total:
            return False
        if (returned == 0 and total != 0) or page.preview_truncated != (returned < total):
            return False
        end = page.page_offset + returned
        if page.next_offset != (end if end < total else None):
            return False
        offset = end
    # Duplicate zero-length pages do not prove additional coverage either.
    return offset == total and (total != 0 or len(pages) == 1)


def assess_completion(
    facts: tuple[FactSpec, ...], observations: tuple[Observation, ...],
    dispositions: tuple[DatasetDisposition, ...] = (), *,
    binding: ControllerBinding | None = None, stopped_reason: str | None = None,
) -> CompletionAssessment:
    """Evaluate host facts, never model finish text or proposed dispositions.

    Calling without an explicit binding still refuses to combine observations
    from different submitted revisions. A model finish is merely a stop request;
    unresolved and explicitly unavailable dispositions never become complete.
    """
    if len({fact.fact_id for fact in facts}) != len(facts):
        raise ValueError("Requested fact identities must be distinct")
    if len({obs.observation_id for obs in observations}) != len(observations):
        raise ValueError("Observation identities must be distinct")
    if binding is None and observations:
        binding = observations[0].binding
    assessments = []
    for fact in facts:
        candidates = [obs for obs in observations if _compatible(fact, obs, binding)]
        witnesses, value = [], None
        if fact.kind == "count":
            counts = [(obs, count) for obs in candidates for count in obs.counts
                      if count.entity == fact.entity and count.state == "known"
                      and (fact.denominator is None or count.denominator == fact.denominator)]
            if counts and len({(count.value, count.denominator) for _, count in counts}) == 1:
                witnesses = [obs for obs, _ in counts]
                value = canonical_json(counts[0][1].model_dump(mode="json"))
        elif fact.kind == "find":
            matches = [(obs, obj) for obs in candidates for obj in obs.objects
                       if (fact.object_id is not None and obj.object_id == fact.object_id)
                       or (fact.exact_name is not None and fact.exact_name in obj.exact_names)]
            if matches and len({obj.object_id for _, obj in matches}) == 1:
                witnesses = [obs for obs, _ in matches]
                value = canonical_json({"object_id": matches[0][1].object_id})
        elif fact.kind in {"coverage", "operation"}:
            field = "known_fields" if fact.kind == "coverage" else "output_fields"
            witnesses = [obs for obs in candidates if set(fact.required_fields) <= set(getattr(obs, field))]
        else:
            publication = [obs for obs in candidates if obs.authority == "published"
                           and obs.tool in {"analysis.get_published", "catalogue.query"}
                           and obs.operation_id == "c13.table" and obs.operation_version == "c13-v1"
                           and obs.source_completeness == "complete"
                           and obs.analysis_id == fact.analysis_id and obs.workflow_kind == fact.workflow_kind
                           and obs.protocol_id == fact.protocol_id
                           and obs.question_compatibility_sha256 == fact.question_compatibility_sha256]
            table_pages = {table: [obs for obs in publication if obs.table_names == (table,)]
                           for table in fact.required_tables}
            if all(_complete_publication_table(pages) for pages in table_pages.values()):
                witnesses = [obs for pages in table_pages.values() for obs in pages]
        if witnesses:
            assessments.append(FactAssessment(fact_id=fact.fact_id, required=fact.required, state="supported",
                observation_ids=tuple(dict.fromkeys(obs.observation_id for obs in witnesses)), value_json=value))
        else:
            assessments.append(FactAssessment(fact_id=fact.fact_id, required=fact.required,
                state="unresolved" if stopped_reason else "pending", reason=stopped_reason))
    supported = {fact.fact_id for fact in assessments if fact.state == "supported"}
    requested = {fact.fact_id: fact for fact in facts}
    by_id = {obs.observation_id: obs for obs in observations}
    unresolved = []
    for disposition in dispositions:
        if not disposition.required:
            continue
        verified = disposition.state == "excluded" and disposition.exclusion_verified and bool(disposition.reason)
        if disposition.state == "covered" and disposition.fact_ids and set(disposition.fact_ids) <= supported:
            direct_witness = any(
                identity in by_id and by_id[identity].binding == binding
                and by_id[identity].input_count == disposition.input_count
                and by_id[identity].input_sha256 == disposition.input_sha256
                and any(identity in fact.observation_ids for fact in assessments if fact.fact_id in disposition.fact_ids)
                for identity in disposition.observation_ids
            )
            fact_scopes = {requested[identity].scope_sha256 for identity in disposition.fact_ids}
            # Finding one requested object does not aggregate the whole input
            # cohort. A separate complete inventory witness establishes the
            # cohort's exact retained membership while the supported facts
            # establish what the question actually required of that population.
            # C13 manifests include a registry witness; semantic dataset counts
            # therefore need not equal the full receipt input_count.
            inventory_witness = len(fact_scopes) == 1 and any(
                identity in by_id and by_id[identity].binding == binding
                and by_id[identity].scope_sha256 in fact_scopes
                and by_id[identity].tool == "catalogue.query"
                and (by_id[identity].operation_id, by_id[identity].operation_version)
                    in {("c13.inventory", "c13-v1"), ("c19.inventory_union", "c19-v1")}
                and by_id[identity].availability == "available"
                and by_id[identity].source_completeness == "complete"
                and by_id[identity].query_completion == "complete"
                and by_id[identity].input_count == disposition.input_count
                and by_id[identity].input_sha256 == disposition.input_sha256
                and any(count.state == "known" and count.entity == "datasets"
                        and count.basis == "complete_scope" for count in by_id[identity].counts)
                for identity in disposition.observation_ids
            )
            verified = direct_witness or inventory_witness
        if not verified:
            unresolved.append(disposition.cohort_id)
    required_ids = {fact.fact_id for fact in facts if fact.required}
    # With no requested facts there is no supported question to declare done.
    complete = bool(required_ids) and required_ids <= supported and not unresolved
    return CompletionAssessment(complete=complete, facts=tuple(assessments), unresolved_cohorts=tuple(unresolved))


def compact_observations(observations: tuple[Observation, ...], *, maximum_bytes: int = 65536, keep_recent: int = 2) -> str:
    """Bound quoted row/object previews without changing retained observations.

    If mandatory scientific limitations alone exceed the budget, fail explicitly
    rather than silently dropping them. Complete object membership and payload
    bytes remain in the host. Recent listing cursors survive optional previews.
    """
    if type(maximum_bytes) is not int or maximum_bytes <= 0 or type(keep_recent) is not int or keep_recent < 0:
        raise ValueError("Invalid observation compaction bounds")
    summaries = []
    for index, observation in enumerate(observations):
        row = observation.model_dump(mode="json", exclude={"preview_json"})
        recent = index >= len(observations) - keep_recent
        objects = row["objects"]
        row["objects"] = objects[:20] if recent else []
        row["objects_total"] = len(objects)
        row["objects_sha256"] = canonical_hash(objects)
        row["objects_quoted_data"] = True
        preview = json.loads(observation.preview_json)
        row["preview"] = preview if recent else []
        if (recent and observation.tool in {"catalogue.overview", "catalogue.list", "catalogue.relationships"}
                and preview and isinstance(preview[0], dict) and isinstance(preview[0].get("listing_page"), dict)):
            row["listing_page"] = preview[0]["listing_page"]
        summaries.append(row)
    encoded = canonical_json(summaries)
    if len(encoded.encode("utf-8")) > maximum_bytes:
        for row in summaries:
            row["preview"] = []
            row["objects"] = []
        encoded = canonical_json(summaries)
    if len(encoded.encode("utf-8")) > maximum_bytes:
        raise ValueError("Scientific observation metadata exceeds context budget")
    return encoded


bounded_prompt_observations = compact_observations


class ControllerResult(FrozenContract):
    binding: ControllerBinding
    outcome: Literal["completed", "partial", "clarification", "cancelled", "unavailable", "failed"]
    budget: BudgetSnapshot
    completion: CompletionAssessment
    observations: tuple[Observation, ...] = ()
    evidence_refs: tuple[Identifier, ...] = ()
    reason: Text | None = None

    @model_validator(mode="after")
    def exact_completion(self):
        if self.outcome == "completed" and not self.completion.complete:
            raise ValueError("Controller cannot complete unsupported requested facts")
        if any(observation.binding != self.binding for observation in self.observations):
            raise ValueError("Controller observations changed submitted context")
        observation_ids = {obs.observation_id for obs in self.observations}
        if any(identity not in observation_ids for fact in self.completion.facts
               if fact.state == "supported" for identity in fact.observation_ids):
            raise ValueError("Fact support must reference this result's executed observations")
        if any(reference not in {obs.full_payload_ref for obs in self.observations} for reference in self.evidence_refs):
            raise ValueError("Evidence references must come from executed observations")
        return self
