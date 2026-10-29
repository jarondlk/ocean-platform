"""C26 source-bound acceptance observations; no provider or release authority."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

VERSION = "system-acceptance-v1"
Status = Literal["passed", "failed", "blocked", "not_run"]
EvidenceKind = Literal[
    "deterministic-fixture",
    "actual-service-synthetic",
    "original-physical",
    "live-service",
    "unrun-live",
]
Text = Annotated[str, StringConstraints(min_length=1, max_length=4000, pattern=r"\S")]
Identity = Annotated[
    str, StringConstraints(min_length=1, max_length=512, pattern=r"\S")
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
SourceRevision = Annotated[
    str,
    StringConstraints(
        pattern=r"^(?:(?:git:)?(?:[a-f0-9]{40}|[a-f0-9]{64})|sha256:[a-f0-9]{64})$"
    ),
]
ExactNumber = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$",
    ),
]


def json_value(value, *, depth=0):
    """Reject coercions, hidden Python objects and nonfinite/unsafe JSON values."""
    if depth > 64:
        raise ValueError("Acceptance JSON exceeds its depth bound")
    if isinstance(value, BaseModel) and type(value).__module__ == __name__:
        return json_value(value.model_dump(mode="python"), depth=depth)
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        value.encode("utf-8")
        return value
    if type(value) in (int, float):
        if (
            type(value) is int
            and abs(value) > 9007199254740991
            or type(value) is float
            and (
                not math.isfinite(value)
                or value.is_integer()
                and abs(value) > 9007199254740991
            )
        ):
            raise ValueError(
                "Acceptance JSON requires finite exact numbers; machine integers use decimal strings"
            )
        return value
    if type(value) is list:
        return [json_value(item, depth=depth + 1) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {
            json_value(key): json_value(item, depth=depth + 1)
            for key, item in value.items()
        }
    raise ValueError("Acceptance JSON contains an unsupported value")


class AcceptanceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always"
    )

    @model_validator(mode="before")
    @classmethod
    def safe_input(cls, value):
        if isinstance(value, cls):
            value = value.model_dump(mode="python")
        return json_value(value)


class EvidenceReference(AcceptanceModel):
    id: Identity
    sha256: Sha256
    source_revision: SourceRevision
    kind: EvidenceKind


class ProviderConfiguration(AcceptanceModel):
    mode: Literal["fixture", "live", "not_invoked"]
    provider: Identity | None
    model: Identity | None
    configuration: dict

    @model_validator(mode="after")
    def concrete_provider(self):
        if self.mode == "not_invoked" and (
            self.provider is not None or self.model is not None or self.configuration
        ):
            raise ValueError("An uninvoked provider has no model configuration")
        if self.mode != "not_invoked" and (self.provider is None or self.model is None):
            raise ValueError(
                "Invoked providers require exact provider/model identities"
            )
        if len(json.dumps(self.configuration, ensure_ascii=False).encode()) > 65536:
            raise ValueError("Provider configuration exceeds its bound")
        return self


class EvaluationInput(AcceptanceModel):
    question_id: Identity
    question: Text
    permissions: list[Identity] = Field(max_length=256)
    scope: dict
    snapshot_id: Identity
    source_revision: SourceRevision
    fixture_id: Identity
    fixture_sha256: Sha256
    provider: ProviderConfiguration

    @model_validator(mode="after")
    def exact_manifest(self):
        if len(self.permissions) != len(set(self.permissions)):
            raise ValueError("Permission identities must be distinct")
        if len(json.dumps(self.scope, ensure_ascii=False).encode()) > 65536:
            raise ValueError("Scope identity exceeds its bound")
        return self


class Measurement(AcceptanceModel):
    basis: Literal["measured", "fixture", "unknown"]
    value: Annotated[float | int, Field(ge=0)] | None

    @model_validator(mode="after")
    def unknown_is_not_zero(self):
        if (self.basis == "unknown") != (self.value is None):
            raise ValueError("Unknown observations have no invented value")
        return self


class Telemetry(AcceptanceModel):
    timing: Measurement
    tool_calls: Measurement
    input_tokens: Measurement
    output_tokens: Measurement
    cost: Measurement

    @model_validator(mode="after")
    def exact_counts(self):
        for name in ("tool_calls", "input_tokens", "output_tokens"):
            value = getattr(self, name).value
            if value is not None and (
                type(value) is not int or value > 9007199254740991
            ):
                raise ValueError(
                    "Tool/token counts require exact nonnegative integer observations"
                )
        return self


def distinct(values, label):
    if len(values) != len(set(values)):
        raise ValueError(label + " identities must be distinct")


def exact_numbers(values):
    for key, value in values.items():
        if not key or len(key) > 512 or not key.strip():
            raise ValueError("Numerical result keys require bounded identities")
        if value is not None:
            try:
                number = Decimal(value)
                if not number.is_finite() or abs(number.as_tuple().exponent) > 10000:
                    raise ValueError(
                        "Numerical result must be a bounded finite decimal"
                    )
            except InvalidOperation:
                raise ValueError(
                    "Numerical result must be an exact decimal string"
                ) from None


class ExpectedOutcome(AcceptanceModel):
    inventory_ids: list[Identity] = Field(max_length=200000)
    numbers: dict[Identity, ExactNumber | None]
    supported_claims: list[Identity] = Field(max_length=4096)
    required_tasks: list[Identity] = Field(min_length=1, max_length=4096)
    valid_citation_ids: list[Identity] = Field(max_length=200000)
    outcome: Literal["completed", "refused", "needs_clarification", "failed"]

    @model_validator(mode="after")
    def independent_oracle(self):
        for name in (
            "inventory_ids",
            "supported_claims",
            "required_tasks",
            "valid_citation_ids",
        ):
            distinct(getattr(self, name), name)
        exact_numbers(self.numbers)
        return self


class ControllerObservation(AcceptanceModel):
    version: Literal["system-controller-observation-v1"] = (
        "system-controller-observation-v1"
    )
    controller: Literal["legacy", "v1"]
    input: EvaluationInput
    evidence_kind: EvidenceKind
    inventory_state: Literal["complete", "partial", "unknown", "unavailable"]
    inventory_ids: list[Identity] = Field(max_length=200000)
    numbers: dict[Identity, ExactNumber | None]
    claims: list[Identity] = Field(max_length=4096)
    claims_complete: bool
    completed_tasks: list[Identity] = Field(max_length=4096)
    cited_ids: list[Identity] = Field(max_length=200000)
    outcome: Literal["completed", "refused", "needs_clarification", "failed"]
    telemetry: Telemetry
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def attributable_observation(self):
        for name in ("inventory_ids", "claims", "completed_tasks", "cited_ids"):
            distinct(getattr(self, name), name)
        distinct([item.id for item in self.evidence], "Evidence")
        exact_numbers(self.numbers)
        if self.evidence_kind == "unrun-live":
            raise ValueError("An unrun live protocol is not a controller observation")
        if any(
            item.kind != self.evidence_kind
            or item.source_revision != self.input.source_revision
            for item in self.evidence
        ):
            raise ValueError(
                "Observation evidence must retain its exact kind and tested source"
            )
        if self.input.provider.mode != "live" and any(
            getattr(self.telemetry, key).basis == "measured"
            for key in ("input_tokens", "output_tokens", "cost")
        ):
            raise ValueError(
                "Fixtures/uninvoked providers cannot claim measured provider billing"
            )
        if self.input.provider.mode == "live" and self.evidence_kind != "live-service":
            raise ValueError("Live providers require actual live-service evidence")
        return self


class MetricAssessment(AcceptanceModel):
    status: Status
    reason: Text | None
    details: dict

    @model_validator(mode="after")
    def explicit_unknowns(self):
        if self.status != "passed" and self.reason is None:
            raise ValueError("An unsuccessful metric requires its concrete reason")
        return self


class ControllerMetrics(AcceptanceModel):
    controller: Literal["legacy", "v1"]
    inventory: MetricAssessment
    numerical: MetricAssessment
    unsupported_claims: MetricAssessment
    completion: MetricAssessment
    citations: MetricAssessment
    telemetry: Telemetry


class ControllerComparison(AcceptanceModel):
    version: Literal["system-controller-comparison-v1"] = (
        "system-controller-comparison-v1"
    )
    status: Status
    reason: Text | None
    input_sha256: Sha256 | None
    oracle_sha256: Sha256
    legacy_observation_sha256: Sha256
    v1_observation_sha256: Sha256
    legacy: ControllerMetrics | None
    v1: ControllerMetrics | None
    live_quality_established: bool = False

    @model_validator(mode="after")
    def bounded_claim(self):
        if self.status != "passed" and self.reason is None:
            raise ValueError("Comparison gates require an explicit reason")
        if self.status == "passed" and (
            self.input_sha256 is None or self.legacy is None or self.v1 is None
        ):
            raise ValueError(
                "Passed comparisons require both matched controller metrics"
            )
        if self.legacy is not None and self.v1 is not None:
            values = [
                getattr(item, key).status
                for item in (self.legacy, self.v1)
                for key in (
                    "inventory",
                    "numerical",
                    "unsupported_claims",
                    "completion",
                    "citations",
                )
            ]
            status = (
                "failed"
                if "failed" in values
                else "blocked"
                if "blocked" in values
                else "not_run"
                if "not_run" in values
                else "passed"
            )
            if self.input_sha256 is None or self.status != status:
                raise ValueError(
                    "Comparison status must retain the independently derived metric states"
                )
        elif (
            self.status != "blocked"
            or self.legacy is not None
            or self.v1 is not None
            or self.input_sha256 is not None
        ):
            raise ValueError(
                "An unmatched comparison remains explicitly blocked without invented metrics"
            )
        if self.live_quality_established:
            raise ValueError(
                "This deterministic comparison does not establish live-model quality"
            )
        return self


class AcceptanceRequirement(AcceptanceModel):
    id: Identity
    phase: Literal["preparation", "release"]
    owner: Identity
    evidence_kind: EvidenceKind

    @model_validator(mode="after")
    def release_is_live(self):
        if self.phase == "release" and self.evidence_kind != "live-service":
            raise ValueError("Release gates require current live-service observations")
        return self


class AcceptanceGateResult(AcceptanceModel):
    requirement_id: Identity
    status: Status
    reason: Text | None
    evidence: list[EvidenceReference] = Field(max_length=128)

    @model_validator(mode="after")
    def no_missing_pass(self):
        distinct([item.id for item in self.evidence], "Evidence")
        if self.status == "passed" and (
            not self.evidence
            or any(item.kind == "unrun-live" for item in self.evidence)
        ):
            raise ValueError("A passed gate requires actual attributable evidence")
        if self.status != "passed" and self.reason is None:
            raise ValueError("An open or failed gate requires its concrete reason")
        return self


class SystemAcceptanceReport(AcceptanceModel):
    version: Literal["system-acceptance-v1"] = VERSION
    source_revision: SourceRevision
    requirements: list[AcceptanceRequirement] = Field(min_length=1, max_length=1024)
    results: list[AcceptanceGateResult] = Field(min_length=1, max_length=1024)
    comparisons: list[ControllerComparison] = Field(max_length=256)
    preparation_status: Status
    release_status: Status
    preparation_complete: bool
    release_accepted: bool

    @model_validator(mode="after")
    def exact_gate_accounting(self):
        distinct([item.id for item in self.requirements], "Requirement")
        distinct([item.requirement_id for item in self.results], "Result")
        expected = {item.id: item for item in self.requirements}
        if {item.requirement_id for item in self.results} != expected.keys():
            raise ValueError(
                "Every named requirement must have exactly one explicit result"
            )
        for result in self.results:
            requirement = expected[result.requirement_id]
            if result.status == "passed":
                if any(
                    item.kind != requirement.evidence_kind for item in result.evidence
                ):
                    raise ValueError(
                        "Evidence kind cannot transfer authority between gates"
                    )
                if requirement.evidence_kind != "original-physical" and any(
                    item.source_revision != self.source_revision
                    for item in result.evidence
                ):
                    raise ValueError(
                        "Acceptance source changed after its evidence was recorded"
                    )
        local = [
            result.status
            for result in self.results
            if expected[result.requirement_id].phase == "preparation"
        ]
        release = [
            result.status
            for result in self.results
            if expected[result.requirement_id].phase == "release"
        ]

        def combine(values):
            return (
                "failed"
                if "failed" in values
                else "blocked"
                if "blocked" in values
                else "not_run"
                if not values or "not_run" in values
                else "passed"
            )

        if self.preparation_status != combine(local) or self.release_status != combine(
            [*local, *release] if release else []
        ):
            raise ValueError("Reported status does not match its actual gate results")
        if self.preparation_complete != (
            self.preparation_status == "passed"
        ) or self.release_accepted != (self.release_status == "passed"):
            raise ValueError(
                "Preparation completion cannot be promoted to release acceptance"
            )
        return self
