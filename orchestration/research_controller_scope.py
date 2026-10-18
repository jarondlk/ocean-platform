"""C19 deterministic question/scope/pin boundary, with no model or I/O.

The host supplies a C17 load_for_submission result and current C14 open details.
All reads, authentication and budget charges belong to that host. A catalogue
node's scope is an executed request, never a definition of its pin semantics.
Unsupported pins/qualifiers require clarification rather than disappearing.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from pydantic import TypeAdapter

from orchestration.publication_scope import publication_compatibility, resolve_protocol
from orchestration.research_intents import QUESTIONS
from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.catalogue_service import REQUEST_MODELS
from schema.context_catalogue import (
    CatalogueNode,
    Identifier,
    _strict_scope,
    canonical_json,
)
from schema.investigations import ContextReference, finite_utf8_json
from schema.scientific_catalogue import PublishedAnalysis
from schema.time_range import time_bounds

VERSION = "research-controller-scope-v1"
MAX_QUESTION = 8000
MAX_DETAILS_BYTES = 4 * 1024 * 1024
MAX_PINS = 256
_identifier = TypeAdapter(Identifier)
_sha = re.compile(r"^[a-f0-9]{64}$")
_NATIVE = {
    "c10-v1": {"c10.table", "c10.count", "c10.summary", "c10.coverage"},
    "c11-v1": {
        "c11.table",
        "c11.count",
        "c11.summary",
        "c11.coverage",
        "c11.grid_points",
    },
    "c12-v1": {
        "c12.table",
        "c12.count",
        "c12.summary",
        "c12.coverage",
        "c12.frequency",
    },
}


class ScopeGuardError(ValueError):
    """Safe, deterministic refusal; never includes source or provider text."""


def _json(value, maximum=MAX_DETAILS_BYTES):
    try:
        finite_utf8_json(value)
        text = canonical_json(value)
    except (TypeError, ValueError, UnicodeError, OverflowError):
        raise ScopeGuardError(
            "Scope values must be bounded finite UTF-8 JSON"
        ) from None
    if len(text.encode("utf-8")) > maximum:
        raise ScopeGuardError("Scope input exceeds its byte bound")
    return text


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _scope(value):
    try:
        return EvidenceScope.model_validate(_strict_scope(value)).canonical()
    except (ValueError, TypeError, OverflowError):
        raise ScopeGuardError(
            "A strict source-owned evidence scope is required"
        ) from None


def _uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ScopeGuardError("Canonical submission identity required")
    return value


@dataclass(frozen=True)
class PinWitness:
    reference_json: str
    disposition: str
    constraints_json: str
    details_sha256: str | None
    limitations: tuple[str, ...]

    @property
    def reference(self):
        return json.loads(self.reference_json)

    @property
    def constraints(self):
        return json.loads(self.constraints_json)

    @property
    def sha256(self):
        return _digest(
            {
                "reference": self.reference,
                "disposition": self.disposition,
                "constraints": self.constraints,
                "details_sha256": self.details_sha256,
                "limitations": list(self.limitations),
            }
        )


@dataclass(frozen=True)
class ScopeResolution:
    status: str
    binding_json: str
    scope_json: str
    inventory_roots: tuple[str, ...]
    allowed_dataset_ids: frozenset[str] | None
    pins: tuple[PinWitness, ...]
    limitations: tuple[str, ...]
    question: str
    intent: str
    target_id: str | None
    facts_json: str
    publication_json: str = "null"
    operation_json: str = "null"
    restrictions_json: str = "{}"

    @property
    def effective_scope(self):
        return json.loads(self.scope_json)

    @property
    def binding(self):
        return json.loads(self.binding_json)

    @property
    def requested_facts(self):
        return tuple(json.loads(self.facts_json))

    @property
    def restrictions(self):
        return json.loads(self.restrictions_json)

    @property
    def sha256(self):
        return _digest(
            {
                "version": VERSION,
                "status": self.status,
                "binding": self.binding,
                "scope": self.effective_scope,
                "inventory_roots": self.inventory_roots,
                "allowed_dataset_ids": None
                if self.allowed_dataset_ids is None
                else sorted(self.allowed_dataset_ids),
                "pins": [p.sha256 for p in self.pins],
                "limitations": self.limitations,
                "question": self.question,
                "intent": self.intent,
                "target_id": self.target_id,
                "requested_facts": list(self.requested_facts),
                "publication": json.loads(self.publication_json),
                "operation": json.loads(self.operation_json),
                "restrictions": self.restrictions,
            }
        )


def project_pin(reference, details) -> PinWitness:
    """Project only actual C14 typed dataset/publication identities.

    Generic definitions, roots, relationships and result-table labels do not
    define executable restrictions. Artifact semantics await a trusted C21
    adapter; a retained hash alone does not establish their scientific scope.
    """
    ref = ContextReference.model_validate(reference).model_dump(mode="json")
    ref_json = _json(ref)
    if ref["kind"] == "artifact":
        return PinWitness(
            ref_json,
            "unavailable",
            "{}",
            None,
            ("Artifact pin semantics are unavailable; the pin was retained.",),
        )
    try:
        encoded = _json(details)
        if type(details) is not dict:
            raise ValueError("Object details required")
        node = CatalogueNode.model_validate(details["node"])
        body = details.get("details", details)
        if (
            type(body) is not dict
            or node.id != ref["id"]
            or node.snapshot_id != ref["snapshot_id"]
        ):
            raise ValueError("Pin identity mismatch")
        details_hash = hashlib.sha256(encoded.encode()).hexdigest()
        if (
            node.availability.status != "available"
            or node.lifecycle.publication == "withdrawn"
        ):
            return PinWitness(
                ref_json,
                "unavailable",
                "{}",
                details_hash,
                ("Pinned catalogue object is currently unavailable.",),
            )
        if node.kind == "dataset":
            if node.source_family not in FAMILIES:
                raise ValueError("Dataset source required")
            constraints = {
                "kind": "dataset",
                "dataset_ids": [node.id],
                "family": node.source_family,
                "descriptor": node.descriptor.model_dump(mode="json"),
            }
            descriptor, fields, external = constraints["descriptor"], {}, {}
            if node.source_family == "remote_sensing":
                fields["remote_sensing.dataset_id"] = node.id
                external = {
                    key: descriptor[key] for key in ("product_id", "product_version")
                }
            elif node.source_family == "edna_metabarcoding":
                if descriptor["assignment_method"] in {
                    "qcauto_target",
                    "qcauto_95pct_3nn_target",
                }:
                    fields["edna_metabarcoding.assignment_method"] = descriptor[
                        "assignment_method"
                    ]
                if descriptor["sample_kind"] not in {"mixed", "unknown"}:
                    fields["edna_metabarcoding.sample_kind"] = descriptor["sample_kind"]
                if descriptor["is_control"] is not None:
                    fields["edna_metabarcoding.is_control"] = descriptor["is_control"]
                if descriptor["population"] == "scientific":
                    external["protocol_id"] = descriptor["protocol_id"]
                elif descriptor["assignment_method"] not in {"mixed", "unknown"}:
                    external["raw_assignment_method"] = descriptor["assignment_method"]
            elif node.source_family == "metagenome" and descriptor["method"] in {
                "Kraken",
                "MetaEuk",
            }:
                external["method"] = descriptor["method"]
            constraints.update(source_fields=fields, external=external)
        elif node.kind == "analysis":
            analysis = PublishedAnalysis.model_validate(body["record"])
            if (
                analysis.id != node.id
                or analysis.publication_status != "published"
                or node.authority != "published"
            ):
                raise ValueError("Published immutable analysis required")
            if analysis.availability.status != "available":
                return PinWitness(
                    ref_json,
                    "unavailable",
                    "{}",
                    details_hash,
                    ("Pinned publication is currently unavailable.",),
                )
            constraints = {
                "kind": "publication",
                "dataset_ids": analysis.input_dataset_ids,
                "analysis": analysis.model_dump(mode="json"),
            }
        else:
            return PinWitness(
                ref_json,
                "clarification_required",
                "{}",
                details_hash,
                (
                    "This pinned object has no supported deterministic restriction semantics.",
                ),
            )
        limitations = ()
        if (
            node.source_family == "edna_metabarcoding"
            and constraints.get("descriptor", {}).get("population") == "raw_inventory"
        ):
            limitations = (
                "Pinned eDNA raw inventory is not a scientific cohort; mixed or unknown metadata cannot establish one.",
            )
        return PinWitness(
            ref_json, "applied", _json(constraints), details_hash, limitations
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        UnicodeError,
    ):
        return PinWitness(
            ref_json,
            "unavailable",
            "{}",
            None,
            ("Pinned details could not be verified against their exact identity.",),
        )


_COUNT = (
    r"count (?:all |the )?(?:available )?datasets(?: in (?:the )?current context)?",
    r"how many datasets are (?:available|there|in (?:the )?current context)",
    r"(?:現在のコンテキストの|利用可能な)?データセット数を数えてください",
    r"(?:現在のコンテキストの|利用可能な)?データセットはいくつありますか",
)
_QUOTED = r'(?:"(?P<en>[^"\r\n]+)"|「(?P<ja>[^「」\r\n]+)」)'
_FIND = re.compile(
    r"(?:find (?:object|dataset) "
    + _QUOTED
    + r"|(?:オブジェクト|データセット)「(?P<jp>[^「」\r\n]+)」を探してください)",
    re.I,
)
_COVERAGE = re.compile(
    r"(?:show coverage for dataset "
    + _QUOTED
    + r"|データセット「(?P<jp>[^「」\r\n]+)」のカバレッジを示してください)",
    re.I,
)
_OPERATION = re.compile(
    r'run operation "(?P<operation>[A-Za-z0-9._:-]+)" version "(?P<version>[A-Za-z0-9._:-]+)" on dataset "(?P<target>[^"\r\n]+)"',
    re.I,
)


def _question(question):
    if (
        not isinstance(question, str)
        or not question.strip()
        or len(question) > MAX_QUESTION
    ):
        raise ScopeGuardError("A bounded nonempty original question is required")
    if any(
        ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in question
    ):
        raise ScopeGuardError("Question must be visible UTF-8 text")
    return question.strip().rstrip(".?!。？！").rstrip()


def _parse_question(question):
    text = _question(question)
    # This explicit suffix is not a general language interpreter. The scanner
    # below consumes every byte, including unknown/duplicate keys and residue.
    parts = re.split(r"\s+where\s+|。?条件[:：]\s*", text, maxsplit=1, flags=re.I)
    base, suffix = parts[0].strip(), parts[1] if len(parts) == 2 else None
    qualifiers = {}
    if suffix is not None:
        position = 0
        pattern = re.compile(
            r'(?P<key>[a-z_]+\.(?:enabled|[a-z_]+))\s*=\s*(?P<value>"(?:[^"\\\r\n]|\\["\\])*"|true|false|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)',
            re.I,
        )
        while position < len(suffix):
            match = pattern.match(suffix, position)
            if match is None or match["key"] in qualifiers or len(qualifiers) >= 16:
                return "unresolved", None, {}, None
            qualifiers[match["key"]] = json.loads(match["value"])
            position = match.end()
            if position == len(suffix):
                break
            separator = re.match(r"\s+(?:and)\s+|\s*;\s*", suffix[position:], re.I)
            if separator is None or position + separator.end() == len(suffix):
                return "unresolved", None, {}, None
            position += separator.end()
        if not qualifiers:
            return "unresolved", None, {}, None
    if any(re.fullmatch(pattern, base, re.I) for pattern in _COUNT):
        return "count_datasets", None, qualifiers, None
    for pattern, intent in ((_FIND, "find_exact_id"), (_COVERAGE, "coverage_dataset")):
        match = pattern.fullmatch(base)
        if match:
            target = next(
                value for value in match.groupdict().values() if value is not None
            )
            _identifier.validate_python(target)
            return intent, target, qualifiers, None
    match = _OPERATION.fullmatch(base)
    if match and match["operation"] in _NATIVE.get(match["version"], set()):
        _identifier.validate_python(match["target"])
        return (
            "registered_operation",
            match["target"],
            qualifiers,
            {"operation_id": match["operation"], "operation_version": match["version"]},
        )
    return "unresolved", None, {}, None


def _merge_scope(base, incoming, *, question=False):
    """Intersect pins, or require explicit question qualifiers to stay in bounds."""
    result = json.loads(_json(base))
    for family in FAMILIES:
        old, new = result["sources"][family], incoming["sources"][family]
        if new["enabled"] and not old["enabled"]:
            raise ScopeGuardError("A restriction cannot enable a disabled source")
        if not new["enabled"]:
            old["enabled"] = False
        first, second = old["filters"], new["filters"]
        for key, value in second.items():
            if value is None:
                continue
            prior = first.get(key)
            if prior is None or prior == value:
                first[key] = value
                continue
            if key.startswith(("lat_", "lon_")):
                tighter = (
                    max(prior, value) if key.endswith("min") else min(prior, value)
                )
                if question and tighter != value:
                    raise ScopeGuardError(
                        "Requested geography exceeds binding restrictions"
                    )
                first[key] = tighter
            elif key in {"time_from", "time_to"}:
                left = time_bounds(first.get("time_from"), first.get("time_to"))
                right = time_bounds(second.get("time_from"), second.get("time_to"))
                index = 0 if key == "time_from" else 1
                a, b = left[index], right[index]
                if key == "time_to" and a == b and left[2] != right[2]:
                    # Equal upper instants: exclusive is narrower than inclusive.
                    use_new = right[2]
                else:
                    use_new = b >= a if index == 0 else b <= a
                if question and not use_new:
                    raise ScopeGuardError(
                        "Requested period exceeds binding restrictions"
                    )
                if use_new:
                    first[key] = value
            else:
                raise ScopeGuardError("Explicit restriction values conflict")
        identity = new.get("analysis_id")
        if identity is not None:
            if old.get("analysis_id") not in (None, identity):
                raise ScopeGuardError("Analysis selections conflict")
            old["analysis_id"] = identity
    return _scope(result)


def _qualifier_scope(base, qualifiers):
    value = {
        "version": 1,
        "sources": {
            family: {"enabled": base["sources"][family]["enabled"], "filters": {}}
            for family in FAMILIES
        },
    }
    for path, selected in qualifiers.items():
        family, field = path.split(".", 1)
        if family not in FAMILIES:
            raise ScopeGuardError("Unknown qualifier source")
        if field == "enabled":
            if type(selected) is not bool:
                raise ScopeGuardError("Source selection requires a boolean")
            value["sources"][family]["enabled"] = selected
        else:
            value["sources"][family]["filters"][field] = selected
    return _scope(value)


_EXTERNAL_FIELDS = {"product_id", "product_version", "protocol_id", "method"}


def _split_qualifiers(qualifiers, restrictions):
    fields = {}
    for path, value in qualifiers.items():
        family, key = path.split(".", 1)
        if key in _EXTERNAL_FIELDS:
            if family not in restrictions or restrictions[family].get(key) != value:
                raise ScopeGuardError(
                    "Question qualifier does not match a retained pin restriction"
                )
        else:
            fields[path] = value
    return fields


def check_publication(question, details, scope, *, workflow_kind, protocol_id=None):
    """Reuse C01 against the original question and exact frozen C13 record."""
    raw = details.get("details", details) if type(details) is dict else {}
    analysis = PublishedAnalysis.model_validate(raw["record"])
    if analysis.scope.canonical() != _scope(scope) or analysis.scope_option is None:
        raise ScopeGuardError(
            "Immutable publication requires its exact verified frozen scope"
        )
    return publication_compatibility(
        question,
        workflow_kind,
        analysis.scope_option,
        protocol_id=protocol_id,
        scope=_scope(scope),
    )


def _resolve_scope(frozen_submission, question, pin_witnesses=()) -> ScopeResolution:
    """Resolve a host-frozen C17 submission; no omitted or additional pin accepted."""
    _question(question)
    # C17 bounds the retained context itself at512KiB; its trusted outer binding
    # adds canonical UUIDs/hashes and must not reduce that accepted context limit.
    data = json.loads(_json(frozen_submission, 512 * 1024 + 4096))
    required = {
        "investigation_id",
        "conversation_id",
        "revision_id",
        "snapshot_id",
        "payload_sha256",
        "context",
    }
    if type(data) is not dict or set(data) != required:
        raise ScopeGuardError("Exact frozen C17 submission required")
    for key in ("investigation_id", "conversation_id", "revision_id"):
        _uuid(data[key])
    if (
        not isinstance(data["snapshot_id"], str)
        or not _sha.fullmatch(data["snapshot_id"])
        or not isinstance(data["payload_sha256"], str)
        or not _sha.fullmatch(data["payload_sha256"])
    ):
        raise ScopeGuardError("Frozen snapshot and payload hashes required")
    context = data["context"]
    if (
        type(context) is not dict
        or context.get("snapshot_id") != data["snapshot_id"]
        or _digest(context) != data["payload_sha256"]
    ):
        raise ScopeGuardError("Frozen context hash or snapshot mismatch")
    effective = _scope(context["scope"])
    references = [
        ContextReference.model_validate(r).model_dump(mode="json")
        for r in context["pins"]
    ]
    if len(references) > MAX_PINS or len({_json(r) for r in references}) != len(
        references
    ):
        raise ScopeGuardError("Bounded distinct pins required")
    # Attachments are intentionally validated but never converted to restrictions.
    if (
        type(context.get("attachments")) is not list
        or len(context["attachments"]) > MAX_PINS
    ):
        raise ScopeGuardError("Bounded attachments required")
    for attachment in context["attachments"]:
        ContextReference.model_validate(attachment)
    witnesses = tuple(pin_witnesses)
    if (
        len(witnesses) != len(references)
        or any(not isinstance(p, PinWitness) for p in witnesses)
        or {_json(r) for r in references} != {p.reference_json for p in witnesses}
    ):
        raise ScopeGuardError("Every pin requires one exact current witness")
    if len({p.reference_json for p in witnesses}) != len(witnesses):
        raise ScopeGuardError("Duplicate pin witnesses are not permitted")
    witnesses = tuple(sorted(witnesses, key=lambda p: p.reference_json))
    status, limitations, allowed, publications, restrictions = "ready", [], None, [], {}
    for witness in witnesses:
        if (
            witness.reference["kind"] == "catalogue"
            and witness.reference["snapshot_id"] != data["snapshot_id"]
        ):
            raise ScopeGuardError("Catalogue pin belongs to another snapshot")
        limitations.extend(witness.limitations)
        if witness.disposition != "applied":
            if witness.disposition == "unavailable":
                status = "unavailable"
            elif status == "ready":
                status = "clarification_required"
            continue
        constraints = witness.constraints
        members = frozenset(constraints["dataset_ids"])
        allowed = members if allowed is None else allowed & members
        if not allowed:
            status = "clarification_required" if status != "unavailable" else status
            limitations.append(
                "Pinned dataset restrictions have no common canonical input; clarify their grouping."
            )
        if constraints["kind"] == "dataset":
            family = constraints["family"]
            fixed = restrictions.setdefault(family, {})
            for key, selected in constraints.get("external", {}).items():
                if key in fixed and fixed[key] != selected:
                    status = (
                        "clarification_required" if status != "unavailable" else status
                    )
                    limitations.append(
                        "Pinned product, method or protocol restrictions conflict."
                    )
                fixed[key] = selected
            try:
                effective = _merge_scope(
                    effective,
                    _qualifier_scope(effective, constraints.get("source_fields", {})),
                )
            except (ValueError, TypeError, OverflowError):
                status = "clarification_required" if status != "unavailable" else status
                limitations.append(
                    "Pinned descriptor restrictions conflict with the frozen investigation scope."
                )
        if constraints["kind"] == "publication":
            analysis = constraints["analysis"]
            publications.append(analysis)
            try:
                effective = _merge_scope(effective, _scope(analysis["scope"]))
            except (ValueError, TypeError, OverflowError):
                status = "clarification_required" if status != "unavailable" else status
                limitations.append(
                    "Pinned publication scope conflicts with the frozen investigation scope."
                )
    try:
        intent, target, qualifiers, operation = _parse_question(question)
        effective = _merge_scope(
            effective,
            _qualifier_scope(effective, _split_qualifiers(qualifiers, restrictions)),
            question=True,
        )
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
        intent, target, qualifiers, operation = "unresolved", None, {}, None
    for witness in witnesses:
        constraint = witness.constraints
        if (
            constraint.get("kind") == "dataset"
            and not effective["sources"][constraint["family"]]["enabled"]
        ):
            status = "clarification_required" if status != "unavailable" else status
            limitations.append(
                "A binding dataset pin cannot be satisfied by disabling its source family."
            )
    publication = None
    if len(publications) > 1:
        status = "clarification_required" if status != "unavailable" else status
        limitations.append(
            "Multiple immutable publication pins require an explicit compatible selection; none was dropped."
        )
    if intent == "unresolved" and publications and status == "ready":
        candidates = []
        for analysis in publications:
            option = analysis.get("scope_option")
            if option is None:
                continue
            protocol_id, automatic = resolve_protocol(option, question)
            if automatic and len(option.get("protocol_ids", [])) != 1:
                protocol_id = None
            for workflow in QUESTIONS:
                try:
                    compatibility = check_publication(
                        question,
                        {"record": analysis},
                        effective,
                        workflow_kind=workflow,
                        protocol_id=protocol_id,
                    )
                except (ValueError, KeyError, TypeError, OverflowError):
                    continue
                if compatibility.outcome == "compatible":
                    candidates.append(
                        {
                            "analysis_id": analysis["id"],
                            "workflow_kind": workflow,
                            "protocol_id": protocol_id,
                            "compatibility": compatibility.as_dict(),
                        }
                    )
        if len(candidates) == 1:
            intent, target, publication = (
                "publication",
                candidates[0]["analysis_id"],
                candidates[0],
            )
        else:
            limitations.append(
                "The original question does not uniquely match the exact pinned publication, protocol and scope."
            )
    if intent == "unresolved":
        if status == "ready":
            status = "clarification_required"
        limitations.append(
            "The complete original question or an explicit qualifier requires clarification."
        )
    if (
        target is not None
        and allowed is not None
        and target not in allowed
        and not (publication and target == publication["analysis_id"])
    ):
        if status == "ready":
            status = "clarification_required"
        limitations.append("Requested canonical target is outside the binding pins.")
    roots = ("root:data",) if allowed is None else tuple(sorted(allowed))
    fact = {
        "kind": intent,
        "target_id": target,
        "entity": "datasets" if intent == "count_datasets" else None,
        "basis": "complete_scope",
    }
    if intent == "registered_operation":
        fact.update(operation)
    binding = {key: data[key] for key in required if key != "context"}
    return ScopeResolution(
        status,
        _json(binding),
        _json(effective),
        roots,
        allowed,
        witnesses,
        tuple(dict.fromkeys(limitations)),
        question,
        intent,
        target,
        _json([fact] if intent != "unresolved" else []),
        _json(publication),
        _json(operation),
        _json(restrictions),
    )


def resolve_scope(frozen_submission, question, pin_witnesses=()) -> ScopeResolution:
    """Public pure boundary, with non-disclosing validation errors."""
    try:
        return _resolve_scope(frozen_submission, question, pin_witnesses)
    except ScopeGuardError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        UnicodeError,
    ):
        raise ScopeGuardError(
            "Frozen context or pin witness validation failed"
        ) from None


def _native_guard(resolution, target, operation_id, version, parameters):
    """Native filters may narrow; they may never override an encoded restriction."""
    if any(w.constraints.get("kind") == "publication" for w in resolution.pins):
        raise ScopeGuardError(
            "An immutable publication pin cannot authorize recomputing a different native cohort"
        )
    if operation_id not in _NATIVE.get(version, set()):
        raise ScopeGuardError(
            "Only registered descriptive source operations are allowed"
        )
    # Use the actual source-owned parameter contracts; unknown product/protocol/
    # scope fields cannot be silently ignored inside a generic JSON object.
    from orchestration.frozen_catalogue import Parameters as CTDParameters
    from orchestration.frozen_edna_catalogue import Parameters as EDNAParameters
    from orchestration.frozen_sst_catalogue import Parameters as SSTParameters

    models = {
        "c10-v1": CTDParameters,
        "c11-v1": SSTParameters,
        "c12-v1": EDNAParameters,
    }
    try:
        models[version].model_validate(parameters)
    except (ValueError, TypeError):
        raise ScopeGuardError(
            "Native parameters do not match the registered source contract"
        ) from None
    if version == "c12-v1":
        _native_filter_guard(
            resolution.effective_scope, "edna_metabarcoding", target, parameters
        )
    for witness in resolution.pins:
        constraints = witness.constraints
        if (
            constraints.get("kind") != "dataset"
            or target not in constraints["dataset_ids"]
        ):
            continue
        family = constraints["family"]
        expected = (
            "c12-v1"
            if family == "edna_metabarcoding"
            else "c11-v1"
            if family == "remote_sensing"
            else "c10-v1"
        )
        if version != expected:
            raise ScopeGuardError("Native operation belongs to another pinned source")
        fixed = resolution.restrictions.get(family, {})
        if fixed.get("method"):
            table = {"Kraken": "kraken_abundance", "MetaEuk": "metaeuk_abundance"}[
                fixed["method"]
            ]
            if parameters.get("table") != table:
                raise ScopeGuardError("Native table does not retain the pinned method")
        if fixed.get("protocol_id"):
            # C12 accepts partial assay attributes, not an exact protocol ID.
            # Neither a missing filter nor a matching human label proves this
            # immutable protocol restriction for a native row computation.
            raise ScopeGuardError(
                "Native source contract cannot enforce the exact pinned protocol"
            )
        if fixed.get("raw_assignment_method") and fixed[
            "raw_assignment_method"
        ] not in {"qcauto_target", "qcauto_95pct_3nn_target"}:
            raise ScopeGuardError(
                "Pinned raw-only method cannot be promoted to a supported scientific computation"
            )


def _native_filter_guard(scope, family, target, parameters):
    native_filters = parameters.get("filters", {})
    if type(native_filters) is not dict:
        raise ScopeGuardError("Native source filters must be a finite object")
    if "dataset_id" in native_filters and native_filters["dataset_id"] != target:
        raise ScopeGuardError(
            "Native filters cannot replace the exact requested dataset"
        )
    fields = {
        f"{family}.{key}": value
        for key, value in native_filters.items()
        if key != "dataset_id"
    }
    try:
        _merge_scope(scope, _qualifier_scope(scope, fields), question=True)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ScopeGuardError(
            "Native filters conflict with binding source restrictions"
        ) from None


def validate_action(resolution, name, args):
    """Return a detached strict C14 request; reject all scope/identity widening."""
    if (
        not isinstance(resolution, ScopeResolution)
        or resolution.status != "ready"
        or name not in REQUEST_MODELS
    ):
        raise ScopeGuardError(
            "A resolved scope and known read-only action are required"
        )
    supplied = json.loads(_json(args, 256 * 1024))
    if type(supplied) is not dict:
        raise ScopeGuardError("Catalogue action arguments must be an object")
    snapshot, scope = resolution.binding["snapshot_id"], resolution.effective_scope
    if supplied.get("snapshot_id", snapshot) != snapshot or (
        "scope" in supplied and _scope(supplied["scope"]) != scope
    ):
        raise ScopeGuardError(
            "Action cannot replace the frozen snapshot or effective scope"
        )
    supplied.update(snapshot_id=snapshot, scope=scope)
    try:
        request = (
            REQUEST_MODELS[name]
            .model_validate(supplied)
            .model_dump(mode="json", exclude_none=True)
        )
    except (ValueError, TypeError):
        raise ScopeGuardError(
            "Catalogue action does not match its strict read-only schema"
        ) from None
    allowed = resolution.allowed_dataset_ids
    targets = request.get(
        "input_ids",
        [
            request.get("object_id")
            or request.get("analysis_id")
            or request.get("parent_id")
        ],
    )
    if allowed is not None:
        if name in {"catalogue.overview", "catalogue.relationships"}:
            raise ScopeGuardError(
                "Broad catalogue traversal cannot ignore dataset pins"
            )
        publication = json.loads(resolution.publication_json)
        permitted = allowed | ({publication["analysis_id"]} if publication else set())
        if any(target is None or target not in permitted for target in targets):
            raise ScopeGuardError(
                "Action target is outside the exact pinned canonical inputs"
            )
    if name == "analysis.get_published" or (
        name == "catalogue.query" and request["operation_id"] == "c13.table"
    ):
        publication = json.loads(resolution.publication_json)
        if publication is None or targets != [publication["analysis_id"]]:
            raise ScopeGuardError(
                "Publication execution requires actual-question compatibility"
            )
        params = request if name == "analysis.get_published" else request["parameters"]
        if (
            params.get("workflow_kind") != publication["workflow_kind"]
            or params.get("protocol_id") != publication["protocol_id"]
        ):
            raise ScopeGuardError(
                "Publication workflow or protocol differs from the validated question"
            )
    if name == "catalogue.query" and request["operation_id"] == "c13.operation":
        params = request["parameters"]
        _native_guard(
            resolution,
            targets[0],
            params.get("operation_id"),
            params.get("operation_version"),
            params.get("parameters", {}),
        )
        operation = json.loads(resolution.operation_json)
        if operation is not None and any(
            params.get(key) != value for key, value in operation.items()
        ):
            raise ScopeGuardError(
                "Operation differs from the exact requested operation"
            )
    elif name == "catalogue.coverage" or (
        name == "catalogue.query"
        and request["operation_id"] in {"c13.coverage", "c13.quality"}
    ):
        if any(w.constraints.get("kind") == "publication" for w in resolution.pins):
            raise ScopeGuardError(
                "An immutable publication pin cannot authorize a different native coverage cohort"
            )
        params = request.get("parameters", {})
        native_params = (
            params if name == "catalogue.coverage" else params.get("parameters", {})
        )
        for witness in resolution.pins:
            constraints = witness.constraints
            if (
                constraints.get("kind") == "dataset"
                and targets[0] in constraints["dataset_ids"]
            ):
                family = constraints["family"]
                version = (
                    "c12-v1"
                    if family == "edna_metabarcoding"
                    else "c11-v1"
                    if family == "remote_sensing"
                    else "c10-v1"
                )
                _native_guard(
                    resolution,
                    targets[0],
                    version.split("-")[0] + ".coverage",
                    version,
                    native_params,
                )
    return request
