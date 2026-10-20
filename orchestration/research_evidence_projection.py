"""C21 pure verification of the supported immutable C19/C20 projection.

No controller, tool, provider, database or current publication is executed here.
The historical fingerprint is an explicit supported implementation, not whatever
source happens to be installed when a receipt is reopened.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re

from orchestration.research_controller_observations import ObservationCollector
from orchestration.research_controller_replay import REPLAY_VERSION, restore_generation
from orchestration.research_controller_scope import project_pin, resolve_scope, validate_action
from orchestration.research_intents import TABLES_BY_INTENT
from schema.research_controller import (
    ControllerBinding, ControllerLimits, ControllerResult, DatasetDisposition,
    FactSpec, assess_completion, canonical_hash, compact_observations,
    controller_action_schema, parse_controller_action, scientific_parameters_hash,
    scope_hash, strict_json,
)

SUPPORTED_CONTROLLER_FINGERPRINTS = frozenset({
    "cf87f56712ccf4eddb03fe944e9bb293132163e881fdea38bb515b103c2641a5",
})


class EvidenceProjectionError(ValueError):
    """Retained input cannot establish the claimed scientific projection."""


@dataclass(frozen=True)
class ProjectedEvidence:
    resolution: object
    collector: ObservationCollector
    requests: dict
    origins: dict


def requested_facts(resolution):
    common = {"fact_id": "requested:1", "scope_sha256": scope_hash(resolution.effective_scope)}
    roots = tuple(resolution.inventory_roots)
    if resolution.intent == "count_datasets":
        return (FactSpec(**common, kind="count", entity="datasets", target_ids=roots,
            operation_id="c13.inventory" if len(roots) == 1 else "c19.inventory_union",
            operation_version="c13-v1" if len(roots) == 1 else "c19-v1", requires_complete_source=True),)
    if resolution.intent == "find_exact_id":
        return (FactSpec(**common, kind="find", object_id=resolution.target_id),)
    if resolution.intent == "coverage_dataset":
        return (FactSpec(**common, kind="coverage", target_ids=(resolution.target_id,),
            operation_id="c13.coverage", operation_version="c13-v1",
            required_fields=("coverage_known",), requires_complete_source=True),)
    if resolution.intent == "registered_operation":
        return (FactSpec(**common, kind="operation", target_ids=(resolution.target_id,),
            operation_id="c13.operation", operation_version="c13-v1",
            parameters_sha256=scientific_parameters_hash(json.loads(resolution.operation_json)),
            requires_complete_source=True),)
    if resolution.intent == "publication":
        value = json.loads(resolution.publication_json)
        return (FactSpec(**common, kind="publication", analysis_id=value["analysis_id"],
            workflow_kind=value["workflow_kind"], protocol_id=value["protocol_id"],
            required_tables=TABLES_BY_INTENT[value["workflow_kind"]],
            question_compatibility_sha256=canonical_hash(value["compatibility"]),
            requires_complete_source=True),)
    return ()


def project_retained_run(*, frozen, question, manifest, result, steps):
    """Validate raw committed steps and reproduce the terminal accepted evidence.

    ``steps`` is a detached mapping of logical IDs to verified request/outcome
    dictionaries. The store verifies row/hash/physical-or-prefix origin first.
    """
    result = ControllerResult.model_validate_json(json.dumps(result))
    binding = ControllerBinding.model_validate({key: frozen[key] for key in ControllerBinding.model_fields})
    limits = ControllerLimits.model_validate(manifest["limits"])
    expected_request = {"investigation_id": binding.investigation_id,
        "conversation_id": binding.conversation_id, "revision_id": binding.revision_id,
        "question": question}
    if (manifest.get("protocol_version") != REPLAY_VERSION
            or manifest.get("controller_fingerprint") not in SUPPORTED_CONTROLLER_FINGERPRINTS
            or manifest.get("request") != expected_request
            or manifest.get("binding") != binding.model_dump(mode="json")
            or manifest.get("frozen_context_sha256") != canonical_hash(frozen)
            or result.binding != binding or result.outcome not in {"completed", "partial"}):
        raise EvidenceProjectionError("Unsupported retained execution binding")
    collector = ObservationCollector(binding, limits.observation_preview_rows)
    resolution, inventory = None, None
    failures, generations, used = [], [], set()
    requests, origins = {}, {}

    def projection():
        return canonical_hash({"binding": binding.model_dump(mode="json"),
            "scope_witness_sha256": resolution.sha256 if resolution else None,
            "observations": [item.model_dump(mode="json") for item in collector.observations],
            "full_payloads": dict(collector.payloads), "failures": failures, "generations": generations})

    def raw(key, kind, expected=None):
        item = steps.get(key)
        if item is None:
            return None
        used.add(key)
        if (item["kind"] != kind or item["outcome"].get("kind") != kind
                or item["outcome"].get("version") != REPLAY_VERSION
                or (expected is not None and item["request"] != expected)):
            raise EvidenceProjectionError("Changed committed request")
        return item

    def check(item):
        if item["outcome"].get("projection_sha256") != projection():
            raise EvidenceProjectionError("Changed committed projection")

    def tool(key, name, arguments, *, preflight=False):
        expected = {"tool": name, "arguments": arguments, "preflight": preflight,
            "binding": binding.model_dump(mode="json"),
            "scope_witness_sha256": resolution.sha256 if resolution else None}
        item = raw(key, "tool", expected)
        if item is None:
            return None
        outcome = item["outcome"]
        if outcome.get("accepted") is not True:
            reason = outcome.get("reason")
            if reason in {"tool_rejected", "tool_unavailable"}:
                failures.append({"step_id": key, "tool": name, "reason": reason})
            check(item)
            return None
        if outcome.get("status") != 200 or not isinstance(outcome.get("body"), dict):
            raise EvidenceProjectionError("Unaccepted tool bytes")
        payload = {**arguments, "snapshot_id": binding.snapshot_id, "scope": frozen["context"]["scope"]} if preflight else validate_action(resolution, name, arguments)
        publication = json.loads(resolution.publication_json) if resolution else None
        observation = collector.add(name, payload, outcome["body"],
            question_compatibility_sha256=canonical_hash(publication["compatibility"]) if publication else None)
        # Canonical C20 outcome JSON erases insertion order in nested mappings.
        # The historical collector used that order for qualification display.
        # Preserve the terminal ordering only after proving that every literal
        # qualification, with no additions or omissions, comes from these bytes.
        expected_observation = next((value for value in result.observations
            if value.observation_id == observation.observation_id), None)
        if (expected_observation is not None
                and set(observation.qualifications) == set(expected_observation.qualifications)):
            observation = observation.model_copy(update={"qualifications": expected_observation.qualifications})
            collector.observations[-1] = observation
        requests[observation.observation_id] = payload
        origins[observation.observation_id] = tuple(item.get("origin_step_refs", (key,)))
        check(item)
        return observation

    number, witnesses = 0, []
    for reference in frozen["context"]["pins"]:
        if reference["kind"] == "artifact":
            witnesses.append(project_pin(reference, None))
            continue
        number += 1
        key = f"pin:{number}"
        observation = tool(key, "catalogue.open", {"object_id": reference["id"], "include_details": True}, preflight=True)
        if observation is None:
            raise EvidenceProjectionError("Unresolved retained pin")
        witnesses.append(project_pin(reference, collector.payload(observation)))
    resolution = resolve_scope(frozen, question, witnesses)
    if resolution.status != "ready":
        raise EvidenceProjectionError("Unresolved retained scope")
    facts = requested_facts(resolution)
    inventories = []
    for root in resolution.inventory_roots:
        number += 1
        observation = tool(f"inventory:{number}", "catalogue.query", {
            "operation_id": "c13.inventory", "operation_version": "c13-v1",
            "input_ids": [root], "parameters": {"limit": 1}})
        if observation is None:
            break
        inventories.append(observation)
    if inventories and len(inventories) == len(resolution.inventory_roots):
        inventory = inventories[0] if len(inventories) == 1 else collector.inventory_union(inventories, resolution.inventory_roots, resolution.effective_scope)
        if len(inventories) > 1:
            requests[inventory.observation_id] = {"operation_id": "c19.inventory_union", "operation_version": "c19-v1",
                "input_ids": list(resolution.inventory_roots), "scope": resolution.effective_scope}
            origins[inventory.observation_id] = tuple(ref for item in inventories for ref in origins[item.observation_id])
    turns = sorted({int(match.group(1)) for key in steps if (match := re.fullmatch(r"turn:(\d+):(model:[01]|repair:1|tool)", key))})
    for turn in turns:
        action = None
        for repair in (0, 1):
            item = raw(f"turn:{turn}:model:{repair}", "model")
            if item is None:
                break
            request, outcome = item["request"], item["outcome"]
            if (request.get("model") != manifest.get("model") or request.get("schema") != controller_action_schema()
                    or request.get("max_output_tokens") != 4096 or not isinstance(request.get("prompt"), str)):
                raise EvidenceProjectionError("Changed model request")
            prompt = strict_json(request["prompt"])
            if (prompt.get("question") != question or prompt.get("binding") != binding.model_dump(mode="json")
                    or prompt.get("scope") != resolution.effective_scope
                    or prompt.get("scope_witness_sha256") != resolution.sha256
                    or prompt.get("requested_facts") != [fact.model_dump(mode="json") for fact in facts]
                    or prompt.get("observations") != json.loads(compact_observations(tuple(collector.observations), maximum_bytes=limits.model_context_bytes // 2))):
                raise EvidenceProjectionError("Changed model evidence pack")
            if outcome.get("accepted") is not True:
                check(item)
                break
            generation = restore_generation(outcome["generation"])
            generations.append(generation.diagnostics())
            check(item)
            if generation.status != "completed":
                break
            try:
                action = parse_controller_action(generation.require_completed(), fact_ids=tuple(f.fact_id for f in facts))
                break
            except ValueError:
                reservation = raw(f"turn:{turn}:repair:1", "repair", {"malformed_model_step": f"turn:{turn}:model:0"}) if not repair else None
                if reservation is None:
                    break
                if reservation["outcome"].get("accepted") is not True:
                    raise EvidenceProjectionError("Unaccepted repair")
                check(reservation)
        if action is not None and action.kind == "tool":
            tool(f"turn:{turn}:tool", action.tool, action.arguments)
    if set(steps) != used:
        raise EvidenceProjectionError("Unaccounted retained steps")
    if tuple(collector.observations) != result.observations:
        raise EvidenceProjectionError("Terminal observations do not match executed bytes")
    preliminary = assess_completion(facts, tuple(collector.observations), binding=binding, stopped_reason=result.reason)
    dispositions = ()
    if inventory is not None:
        supported = {fact.fact_id for fact in preliminary.facts if fact.state == "supported"}
        required = tuple(fact.fact_id for fact in facts if fact.required)
        complete = bool(required) and set(required) <= supported
        witnesses = tuple(dict.fromkeys([inventory.observation_id, *[oid for fact in preliminary.facts for oid in fact.observation_ids]]))
        dispositions = (DatasetDisposition(cohort_id="cohort:permitted_inventory", input_count=inventory.input_count,
            input_sha256=inventory.input_sha256, state="covered" if complete else "unresolved", fact_ids=required,
            observation_ids=witnesses, reason=None if complete else result.reason or "Requested facts remain unsupported"),)
    completion = assess_completion(facts, tuple(collector.observations), dispositions, binding=binding, stopped_reason=result.reason)
    if completion != result.completion:
        raise EvidenceProjectionError("Changed terminal completion")
    return ProjectedEvidence(resolution, collector, requests, origins)
