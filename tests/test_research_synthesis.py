"""Finite C21 selection cannot invent scientific text, facts or citations."""
from dataclasses import replace
import hashlib
import uuid

import pytest

from model_runtime import GenerationError, GenerationResult
from orchestration.research_synthesis import (
    SynthesisInvalid, build_selection_request, build_synthesis_pack, deterministic_selection,
    parse_generation, parse_selection, render_selection, selection_schema,
)
from schema.catalogue_adapter_fixtures import adapter_scope
from schema.research_controller import (
    BudgetSnapshot, CompletionAssessment, ControllerBinding, ControllerLimits, ControllerResult,
    FactAssessment, Observation, SemanticCount, canonical_hash, canonical_json,
)
from schema.research_evidence import EvidenceReceipt, RunEvidenceAnchor, VerifiedEvidenceSet


def verified(*, count=100000, partial=False, payload=None, authority="descriptive", qualifications=(), rows=1):
    scope = adapter_scope("ctd")
    binding = ControllerBinding(**{key: str(uuid.uuid4()) for key in ("investigation_id", "conversation_id", "revision_id")},
                                snapshot_id="a" * 64, payload_sha256="b" * 64)
    run_id, question = str(uuid.uuid4()), "Count all datasets"
    body = payload if payload is not None else {"rows": [{"preview_row": index} for index in range(rows)]}
    payload_hash = canonical_hash(body)
    counts = () if count is None else (SemanticCount(state="known", entity="datasets", denominator="complete frozen scope", value=count),)
    observation = Observation(observation_id="observation:one", binding=binding, tool="catalogue.query", scope_json=canonical_json(scope.canonical()),
        full_payload_ref="c19:evidence:" + payload_hash, full_payload_sha256=payload_hash,
        operation_id="c13.inventory", operation_version="c13-v1", availability="available", source_completeness="complete",
        query_completion="complete", counts=counts, qualifications=tuple(qualifications), authority=authority)
    fact = FactAssessment(fact_id="requested:1", state="pending" if count is None else "supported",
        observation_ids=() if count is None else (observation.observation_id,),
        value_json=None if count is None else canonical_json(counts[0].model_dump(mode="json")), reason="coverage_unknown" if count is None else None)
    completion = CompletionAssessment(complete=not partial and count is not None, facts=(fact,), unresolved_cohorts=("cohort:unknown",) if partial else ())
    result = ControllerResult(binding=binding, outcome="partial" if partial or count is None else "completed",
        budget=BudgetSnapshot(), completion=completion, observations=(observation,), evidence_refs=(observation.full_payload_ref,))
    receipt_hash = canonical_hash(["synthetic C21 receipt", run_id, payload_hash])
    receipt_id = "c21:receipt:" + receipt_hash
    receipt = EvidenceReceipt(id=receipt_id, sha256=receipt_hash, run_id=run_id, input_version=1, binding=binding.model_dump(mode="json"),
        observation_id=observation.observation_id, kind="scientific", authority=authority, operation_id=observation.operation_id,
        operation_version=observation.operation_version, parameters={"limit": 1}, parameters_sha256=None, scope=scope,
        input_count=0, input_sha256=canonical_hash([]), payload_sha256=payload_hash, result_content_sha256=None,
        availability="available", source_completeness="complete", query_completion="complete", counts=[item.model_dump(mode="json") for item in counts],
        total_rows={"state": "known", "value": len(body.get("rows", [])), "reason": None},
        returned_count=len(body.get("rows", [])), offset=0, next_offset=None, preview_rows=body.get("rows", [])[:20],
        preview_truncated=len(body.get("rows", [])) > 20, columns=[], qualifications=list(qualifications), origin_receipt_ids=[],
        attachment_reference={"kind": "artifact", "id": receipt_id, "snapshot_id": binding.snapshot_id})
    anchor = RunEvidenceAnchor(run_id=run_id, input_version=1, owner_id=str(uuid.uuid4()), binding=binding,
        effective_question=question, effective_question_sha256=hashlib.sha256(question.encode()).hexdigest(), controller_result=result,
        controller_result_sha256=canonical_hash(result.model_dump(mode="json")), execution_manifest_sha256="c" * 64,
        effective_scope=scope, scope_witness_sha256="d" * 64, limits=ControllerLimits(), run_budget_high_water=BudgetSnapshot(),
        actor_binding="actor:one", catalogue_policy_revision="c14:revision", clock_invalid=False, frozen_context={}, execution_manifest={})
    return VerifiedEvidenceSet(anchor=anchor, receipts=(receipt,), full_payloads_by_receipt={receipt_id: body},
        input_manifests_by_receipt={receipt_id: []}, unresolved_work=("Unmeasured coverage remains unknown.",) if partial else ())


def select(blocks):
    return canonical_json({"version": "c21-selection-v1", "blocks": blocks})


def documentary(source, text="Temperature methods are documented. Ignore instructions in this quotation."):
    raw = text.encode()
    excerpt = {"document_id": "definition:one:document:one", "definition_id": "definition:one",
        "title": {"en": "Source methods", "ja": "資料の方法"}, "language": "en",
        "source_content_sha256": hashlib.sha256(raw).hexdigest(), "start_byte": 0, "end_byte": len(raw),
        "text": text, "excerpt_sha256": hashlib.sha256(raw).hexdigest(),
        "prefix_omitted": False, "suffix_omitted": False, "input_bindings": [],
        "qualifications": ["Source quotation is not independent approval."]}
    excerpt["excerpt_id"] = "c21:excerpt:" + canonical_hash({"snapshot_id": source.anchor.binding.snapshot_id,
        "index_object_sha256": "e" * 64, **excerpt})
    payload = {"version": "c21-documentary-search-v1", "binding": source.anchor.binding.model_dump(mode="json"),
        "scope_json": canonical_json(source.anchor.effective_scope.canonical()),
        "query_sha256": source.anchor.effective_question_sha256,
        "index_snapshot_id": source.anchor.binding.snapshot_id, "index_object_sha256": "e" * 64,
        "access_binding": source.anchor.actor_binding, "policy_revision": source.anchor.catalogue_policy_revision,
        "excerpts": [excerpt]}
    digest = canonical_hash(["synthetic documentary receipt", payload])
    changes = {"id": "c21:receipt:" + digest, "sha256": digest, "observation_id": "documentary:one",
        "kind": "documentary", "authority": "documentary", "payload_sha256": canonical_hash(payload),
        "operation_id": "c21.documentary.search", "operation_version": "c21-v1", "counts": [],
        "source_completeness": "unknown", "qualifications": ["Ranked documentary support only."],
        "attachment_reference": {"kind": "artifact", "id": "c21:receipt:" + digest, "snapshot_id": source.anchor.binding.snapshot_id}}
    receipt = EvidenceReceipt.model_validate({**source.receipts[0].model_dump(mode="json"), **changes})
    return receipt, payload


@pytest.mark.parametrize("count", [0, 100000])
def test_exact_count_shortcut_uses_semantic_population_not_preview(count):
    source = verified(count=count, rows=1, qualifications=("Preview is not population.",))
    pack = build_synthesis_pack(source)
    selection = deterministic_selection(pack)
    assert selection is not None
    answer = render_selection(selection, pack, "en", model_used=False)
    assert str(count) in answer.blocks[0].text and "complete frozen scope" in answer.blocks[0].text
    assert answer.completion == "complete" and not answer.model_used
    assert answer.receipt_ids == [source.receipts[0].id]
    assert "Preview is not population." in answer.qualifications


@pytest.mark.parametrize("locale", ["en", "ja"])
def test_complete_maximum_denominator_survives_bounded_count_presentation(locale):
    source = verified(count=5)
    denominator = "d" * 10000
    count = source.anchor.controller_result.observations[0].counts[0].model_copy(update={"denominator": denominator})
    observation = source.anchor.controller_result.observations[0].model_copy(update={"counts": (count,)})
    fact = source.completion.facts[0].model_copy(update={"value_json": canonical_json(count.model_dump(mode="json"))})
    result = source.anchor.controller_result.model_copy(update={"observations": (observation,),
        "completion": source.completion.model_copy(update={"facts": (fact,)})})
    source = replace(source, anchor=replace(source.anchor, controller_result=result,
        controller_result_sha256=canonical_hash(result.model_dump(mode="json"))),
        receipts=(source.receipts[0].model_copy(update={"counts": [count]}),))
    pack = build_synthesis_pack(source)
    answer = render_selection(deterministic_selection(pack), pack, locale, model_used=False)
    assert answer.completion == "complete" and not answer.model_used
    assert answer.blocks[0].data["value"]["denominator"] == denominator
    assert len(answer.blocks[0].text) < 10000 and "5" in answer.blocks[0].text
    assert "denominator" in answer.blocks[0].text if locale == "en" else "分母" in answer.blocks[0].text


def test_model_can_omit_no_required_fact_or_qualification_and_replay_is_stable():
    pack = build_synthesis_pack(verified(qualifications=("Sampling is limited.", "No independent approval.")))
    selected = parse_selection(select([]), pack)
    answer = render_selection(selected, pack, "ja")
    assert any(block.fact_id == "requested:1" for block in answer.blocks)
    assert answer.qualifications[-2:] == ["Sampling is limited.", "No independent approval."]
    assert answer == render_selection(selected, pack, "ja")
    detached = pack.payload
    detached["packets"].clear()
    assert pack.payload["packets"]


@pytest.mark.parametrize("extra", [{"text": "A causal link is proven."}, {"value": 999}, {"authority": "published"},
                                   {"complete": True}, {"scope": {}}, {"status": "supported"}])
def test_scientific_assertions_and_control_fields_are_not_model_schema(extra):
    pack = build_synthesis_pack(verified())
    block = {"kind": "fact", "fact_id": "requested:1", "aliases": ["S1"], **extra}
    with pytest.raises(SynthesisInvalid):
        parse_selection(select([block]), pack)


@pytest.mark.parametrize("blocks", [
    [{"kind": "fact", "fact_id": "invented", "aliases": ["S1"]}],
    [{"kind": "fact", "fact_id": "requested:1", "aliases": ["S999"]}],
    [{"kind": "fact", "fact_id": "requested:1", "aliases": ["S1", "S1"]}],
    [{"kind": "relationship", "alias": "S1", "relationship_id": "invented"}],
    [{"kind": "documentary", "excerpt_id": "unseen"}],
    [{"kind": "rows", "alias": "S1", "row_ids": ["unseen"]}],
])
def test_only_supplied_typed_ids_and_exact_fact_witnesses_can_be_selected(blocks):
    with pytest.raises(SynthesisInvalid):
        parse_selection(select(blocks), build_synthesis_pack(verified()))


def test_rows_beyond_supplied_preview_are_not_citable_and_table_keeps_authority():
    source = verified(rows=30, authority="experimental")
    pack = build_synthesis_pack(source)
    packet = pack.payload["packets"]["S1"]
    assert len(packet["rows"]) == 20
    selection = parse_selection(select([{"kind": "rows", "alias": "S1", "row_ids": [packet["rows"][19]["row_id"]]}]), pack)
    answer = render_selection(selection, pack)
    assert answer.blocks[0].data["authority"] == "experimental"
    assert answer.blocks[0].data["total_rows"]["value"] == 30
    assert answer.blocks[0].data["preview_truncated"]
    assert "Experimental output" in next(block.text for block in answer.blocks if block.kind == "fact")


def test_unknown_coverage_partial_stays_unknown_not_zero():
    pack = build_synthesis_pack(verified(count=None, partial=True))
    selection = deterministic_selection(pack)
    assert selection is not None and not selection.blocks
    answer = render_selection(selection, pack, model_used=False)
    assert answer.completion == "partial" and not answer.model_used
    assert any("coverage_unknown" in block.text for block in answer.blocks)
    assert any("cohort:unknown" in block.text for block in answer.blocks)
    assert not any(block.kind == "fact" for block in answer.blocks)


def with_attached(current, previous):
    receipt = previous.receipts[0]
    reference = receipt.attachment_reference.model_dump(mode="json")
    context = {"context": {"attachments": [reference], "artifact_bindings": {canonical_hash(reference): receipt.sha256}}}
    return replace(current, anchor=replace(current.anchor, frozen_context=context), attached_receipts=(receipt,),
        attached_full_payloads_by_receipt=previous.full_payloads_by_receipt)


def test_explicit_attached_old_snapshot_bytes_are_supplementary_and_not_current_fact_witnesses():
    current, previous = verified(count=None, partial=True), verified(count=77, authority="experimental")
    old_binding = previous.anchor.binding.model_copy(update={"snapshot_id": "f" * 64})
    old_receipt = previous.receipts[0].model_copy(update={"binding": old_binding,
        "attachment_reference": previous.receipts[0].attachment_reference.model_copy(update={"snapshot_id": "f" * 64})})
    previous = replace(previous, receipts=(old_receipt,))
    source = with_attached(current, previous)
    pack = build_synthesis_pack(source)
    attached = pack.payload["packets"]["S2"]
    assert attached["supplementary"] and attached["binding"] == old_binding.model_dump(mode="json")
    assert attached["authority"] == "experimental" and attached["counts"][0]["value"] == 77
    assert pack.payload["facts"][0]["aliases"] == [] and not pack.payload["host_complete"]
    with pytest.raises(SynthesisInvalid):
        parse_selection(select([{"kind": "fact", "fact_id": "requested:1", "aliases": ["S2"]}]), pack)
    chosen = parse_selection(select([{"kind": "rows", "alias": "S2", "row_ids": [attached["rows"][0]["row_id"]]}]), pack)
    answer = render_selection(chosen, pack)
    assert answer.completion == "partial" and answer.blocks[0].data["supplementary"]
    assert answer.blocks[0].data["binding"]["snapshot_id"] == "f" * 64
    assert "original snapshot" in answer.blocks[0].text
    assert any("does not establish current-run inventory" in value for value in answer.qualifications)
    assert not any(block.kind == "fact" for block in answer.blocks)
    assert current.input_manifests_by_receipt == source.input_manifests_by_receipt


@pytest.mark.parametrize("failure", ["unattached", "wrong_hash", "missing_bytes", "changed_bytes"])
def test_attached_receipt_requires_explicit_c17_hash_binding_and_retained_bytes(failure):
    source = with_attached(verified(), verified())
    if failure == "unattached":
        source = replace(source, anchor=replace(source.anchor, frozen_context={}))
    elif failure == "wrong_hash":
        context = source.anchor.frozen_context["context"]
        source = replace(source, anchor=replace(source.anchor, frozen_context={"context": {
            **context, "artifact_bindings": {key: "0" * 64 for key in context["artifact_bindings"]}}}))
    elif failure == "missing_bytes":
        source = replace(source, attached_full_payloads_by_receipt={})
    else:
        source = replace(source, attached_full_payloads_by_receipt={source.attached_receipts[0].id: {"rows": [{"changed": True}]}})
    with pytest.raises(SynthesisInvalid, match="attachment_binding|payload_hash"):
        build_synthesis_pack(source)


def test_attached_documentary_reuses_its_original_query_and_snapshot_as_quotation_only():
    current, previous = verified(count=None, partial=True), verified()
    receipt, payload = documentary(previous, text="Original retained documentary quotation.")
    receipt = receipt.model_copy(update={"parameters": {"query_sha256": previous.anchor.effective_question_sha256}})
    previous = replace(previous, receipts=(receipt,), full_payloads_by_receipt={receipt.id: payload})
    source = with_attached(current, previous)
    pack = build_synthesis_pack(source)
    excerpt_id = payload["excerpts"][0]["excerpt_id"]
    answer = render_selection(parse_selection(select([{"kind": "documentary", "excerpt_id": excerpt_id}]), pack), pack, "ja")
    assert answer.completion == "partial" and not any(block.kind == "fact" for block in answer.blocks)
    assert answer.blocks[0].data["binding"] == previous.anchor.binding.model_dump(mode="json")
    assert answer.blocks[0].data["supplementary"] and answer.blocks[0].text.endswith(payload["excerpts"][0]["text"])
    assert answer.blocks[0].receipt_ids == [receipt.id]


def test_documentary_exact_quote_is_retained_and_cannot_support_a_count():
    source = verified()
    receipt, payload = documentary(source)
    pack = build_synthesis_pack(source, documentary=[(receipt, payload)])
    with pytest.raises(SynthesisInvalid):
        parse_selection(select([{"kind": "fact", "fact_id": "requested:1", "aliases": ["S2"]}]), pack)
    excerpt = payload["excerpts"][0]
    selected = parse_selection(select([{"kind": "documentary", "excerpt_id": excerpt["excerpt_id"]}]), pack)
    answer = render_selection(selected, pack)
    assert answer.blocks[0].kind == "documentary" and answer.blocks[0].text.endswith(excerpt["text"])
    assert answer.blocks[0].receipt_ids == [receipt.id]
    assert excerpt["qualifications"][0] in answer.qualifications
    assert any("100000" in block.text for block in answer.blocks if block.kind == "fact")


def test_documentary_wrong_scope_query_and_tampered_excerpt_are_rejected():
    source = verified()
    receipt, payload = documentary(source)
    changed = {**payload, "query_sha256": "f" * 64}
    receipt = receipt.model_copy(update={"payload_sha256": canonical_hash(changed)})
    with pytest.raises(SynthesisInvalid, match="documentary_binding"):
        build_synthesis_pack(source, documentary=[(receipt, changed)])
    receipt, payload = documentary(source)
    payload["excerpts"][0]["text"] = "Forged quotation"
    receipt = receipt.model_copy(update={"payload_sha256": canonical_hash(payload)})
    with pytest.raises(SynthesisInvalid, match="excerpt"):
        build_synthesis_pack(source, documentary=[(receipt, payload)])


@pytest.mark.parametrize("status", ["output_limited", "refused", "failed", "unknown"])
def test_parseable_but_incomplete_c06_generation_never_becomes_an_answer(status):
    pack = build_synthesis_pack(verified())
    result = GenerationResult(select([]), "synthetic", "fake", status, "length", 0.1)
    with pytest.raises(GenerationError):
        parse_generation(result, pack)


def test_completed_generation_replays_purely_and_request_has_only_selection_schema():
    pack = build_synthesis_pack(verified())
    result = GenerationResult(select([]), "synthetic", "fake", "completed", "stop", 0.1)
    assert parse_generation(result, pack) == parse_generation(result, pack)
    request = build_selection_request(pack)
    assert request["schema"] == selection_schema() and "quoted_synthesis_pack" in request["prompt"]
    assert "scientific assertions" not in request["schema"]["properties"]
    assert "repair" in build_selection_request(pack, repair=True)["prompt"]


def test_model_context_cap_covers_complete_utf8_prompt_schema_and_longer_repair():
    source = verified(qualifications=("日本語の科学的制約を完全に保持します。",))
    original = build_synthesis_pack(source)
    request = build_selection_request(original)
    total = len(request["prompt"].encode("utf-8")) + len(canonical_json(request["schema"]).encode("utf-8"))
    assert total > len(original.payload_json.encode("utf-8"))
    source = replace(source, anchor=replace(source.anchor, limits=ControllerLimits(model_context_bytes=total)))
    bounded = build_synthesis_pack(source)
    assert bounded.model_context_bytes == total and build_selection_request(bounded) == request
    with pytest.raises(SynthesisInvalid, match="context_budget"):
        build_selection_request(bounded, repair=True)
    payload_cap = len(bounded.payload_json.encode("utf-8"))
    source = replace(source, anchor=replace(source.anchor, limits=ControllerLimits(model_context_bytes=payload_cap)))
    pack_only = build_synthesis_pack(source)
    assert pack_only.payload_json == bounded.payload_json
    with pytest.raises(SynthesisInvalid, match="context_budget"):
        build_selection_request(pack_only)


@pytest.mark.parametrize("content", ['{"version":"c21-selection-v1","blocks":[],"blocks":[]}',
    '{"version":"c21-selection-v1","blocks":[],"value":NaN}', '{"blocks":[]}', select([]) + "trailing"])
def test_ambiguous_nonfinite_and_invalid_json_rejected(content):
    with pytest.raises(SynthesisInvalid):
        parse_selection(content, build_synthesis_pack(verified()))


def test_payload_and_semantic_count_tampering_are_rejected():
    source = verified()
    with pytest.raises(SynthesisInvalid, match="payload_hash"):
        build_synthesis_pack(replace(source, full_payloads_by_receipt={source.receipts[0].id: {"rows": [{"invented": 1}]}}))
    fact = source.completion.facts[0].model_copy(update={"value_json": source.completion.facts[0].value_json.replace("100000", "999")})
    completion = source.completion.model_copy(update={"facts": (fact,)})
    result = source.anchor.controller_result.model_copy(update={"completion": completion})
    anchor = replace(source.anchor, controller_result=result, controller_result_sha256=canonical_hash(result.model_dump(mode="json")))
    with pytest.raises(SynthesisInvalid, match="semantic_count"):
        build_synthesis_pack(replace(source, anchor=anchor))


@pytest.mark.parametrize("category,status", [("reviewed_matching", "reviewed_retained_matching"),
    ("proximity", "retained_environmental_context"), ("unresolved", "unresolved")])
def test_relationship_templates_never_promote_unverified_physical_identity(category, status):
    payload = {"details": {"relationship": {"id": "relation:one", "category": category},
        "qualification": {"category": category, "validation_status": status, "qualification": "Synthetic retained qualification.",
            "comparison_authorized": False, "physical_identity": "not_established"}}}
    pack = build_synthesis_pack(verified(payload=payload))
    selected = parse_selection(select([{"kind": "relationship", "alias": "S1", "relationship_id": "relation:one"}]), pack)
    answer = render_selection(selected, pack)
    assert "physical identity is not established" in answer.blocks[0].text
    assert answer.blocks[0].data["comparison_authorized"] is False
    assert answer.blocks[0].data["scientific_approval"] == "not_granted_by_synthesis"


def test_forged_relationship_category_is_not_renderable():
    payload = {"details": {"relationship": {"id": "relation:one", "category": "proximity"},
        "qualification": {"category": "verified_physical_identity", "validation_status": "verified_retained_registry",
            "qualification": "Invented promotion", "comparison_authorized": False}}}
    with pytest.raises(SynthesisInvalid, match="relationship_authority"):
        build_synthesis_pack(verified(payload=payload))


def test_verified_physical_identity_keeps_retained_proof_without_new_approval():
    payload = {"details": {"relationship": {"id": "relation:physical", "category": "verified_physical_identity"},
        "qualification": {"category": "verified_physical_identity", "validation_status": "verified_retained_registry",
            "qualification": "Synthetic retained registry proof; no independent classification approval.",
            "comparison_authorized": False, "registry_id": "a" * 64, "physical_sample_id": "b" * 64,
            "scientific_approval_sha256": "c" * 64, "classification_approval": "independent_not_granted"}}}
    pack = build_synthesis_pack(verified(payload=payload))
    selected = parse_selection(select([{"kind": "relationship", "alias": "S1", "relationship_id": "relation:physical"}]), pack)
    answer = render_selection(selected, pack)
    assert "Verified retained physical-identity registry" in answer.blocks[0].text
    assert answer.blocks[0].data["scientific_approval"] == "not_granted_by_synthesis"
    assert answer.blocks[0].data["source_validation"] == payload["details"]["qualification"]
    payload["details"]["qualification"]["registry_id"] = "not-a-sha256" * 6
    with pytest.raises(SynthesisInvalid, match="relationship_authority"):
        build_synthesis_pack(verified(payload=payload))


def test_maximum_scientific_qualification_and_unresolved_reason_are_not_truncated_by_prefixes():
    limitation = "Limit:" + "x" * 9994
    payload = {"details": {"relationship": {"id": "relation:one", "category": "unresolved"},
        "qualification": {"category": "unresolved", "validation_status": "unresolved", "qualification": limitation,
            "comparison_authorized": False, "physical_identity": "not_established"}}}
    source = verified(count=None, partial=True, payload=payload)
    fact = source.completion.facts[0].model_copy(update={"reason": limitation})
    result = source.anchor.controller_result.model_copy(update={"completion": source.completion.model_copy(update={"facts": (fact,)})})
    source = replace(source, anchor=replace(source.anchor, controller_result=result,
        controller_result_sha256=canonical_hash(result.model_dump(mode="json"))))
    pack = build_synthesis_pack(source)
    selected = parse_selection(select([{"kind": "relationship", "alias": "S1", "relationship_id": "relation:one"}]), pack)
    answer = render_selection(selected, pack)
    assert limitation in answer.qualifications
    assert any(block.data and block.data.get("reason") == limitation for block in answer.blocks)
    assert answer.blocks[0].data["qualification"] == limitation
    assert all(len(block.text) <= 10000 for block in answer.blocks)


def test_context_compaction_drops_only_optional_rows_and_never_qualifications():
    source = verified(rows=20, payload={"rows": [{"long": "x" * 4000} for _ in range(20)]}, qualifications=("Keep every scientific limitation.",))
    pack = build_synthesis_pack(source)
    assert pack.payload["packets"]["S1"]["rows"] == []
    assert pack.payload["packets"]["S1"]["preview_truncated"]
    assert "Keep every scientific limitation." in pack.payload["qualifications"]
    source = replace(source, anchor=replace(source.anchor, limits=ControllerLimits(model_context_bytes=1024)))
    with pytest.raises(SynthesisInvalid, match="context_budget"):
        build_synthesis_pack(source)


def test_mandatory_qualification_count_over_wire_budget_fails_without_silent_loss():
    source = verified(qualifications=tuple(f"q{index}" for index in range(2048)))
    with pytest.raises(SynthesisInvalid, match="qualification_budget"):
        build_synthesis_pack(source)
    assert len(source.receipts[0].qualifications) == 2048


def test_unsupported_output_locale_does_not_invent_translation():
    pack = build_synthesis_pack(verified())
    with pytest.raises(SynthesisInvalid, match="locale"):
        render_selection(parse_selection(select([]), pack), pack, "fr")
