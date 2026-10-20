"""Concrete C21 retrieval over actual sealed C09/C13/C14, no provider mocks."""
from copy import deepcopy
import hashlib
from types import SimpleNamespace
import uuid

import pytest

from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.catalogue_service import CataloguePolicy, CatalogueService, FrozenCatalogueResolver
from orchestration.frozen_documentary import DocumentaryUnavailable, FrozenDocumentaryProvider
from schema.catalogue_adapter_fixtures import adapter_scope
from tests.catalogue_service_support import fixture_user
from tests.test_frozen_scientific_catalogue import CTD, local


def fixture(tmp_path, *, texts=None, change=None, page_size=2, legacy_only=False, index_version="c21-documentary-source-v1"):
    texts = texts or ["Retained temperature sampling protocol.", "水温の測定方法と採水手順。", "Temperature units are degrees Celsius."]

    def configure(registry, tables):
        binding = registry["datasets"][0]
        definitions = []
        for index, text in enumerate(texts):
            document = {"id": f"document:{index:04d}", "title": {"en": "Sampling documentation", "ja": "採水文書"},
                "language": "ja" if "水" in text else "en", "text": text,
                "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "input_bindings": [{"dataset_id": binding["dataset_id"], "child_snapshot_id": binding["snapshot_id"],
                    "source_id": binding["source_id"], "source_family": binding["source_family"]}],
                "applicability_scope": adapter_scope("ctd").canonical(),
                "qualifications": ["Synthetic source quotation, not scientific approval."]}
            if change:
                change(document)
            definitions.append({"id": f"documentation:{index:04d}", "title": document["title"], "purpose": document["title"],
                "category": "source_documentation", "values": {"schema_version": index_version, "documents": [document]},
                "input_dataset_ids": [binding["dataset_id"]], "provenance": {"references": ["Explicit synthetic C21 metadata"]}})
        if legacy_only:
            for definition in definitions:
                definition["values"] = {"source_family": "ctd", "source_reference": "fixture://ctd"}
        registry["definitions"] = definitions

    store, sid, _, _, registry, _, child, _ = local(tmp_path, count=2, configure=configure)
    registration = register_scientific_snapshot(store=store, snapshot_id=sid, registration_id="c21:documentary:test")
    policy = {"denied": set(), "epoch": 1}
    resolver = FrozenCatalogueResolver(store=store, registrations={sid: registration},
        policy_resolver=lambda actor, snapshot: CataloguePolicy(revision=f"policy:{policy['epoch']}",
            dataset_eligible=lambda snapshot, item: item.dataset_id not in policy["denied"],
            scientific_eligible=lambda snapshot, item: item.id not in policy["denied"]))
    service = CatalogueService(resolver=resolver)
    user = fixture_user("c21-documentary")
    provider = FrozenDocumentaryProvider(store=store, registration=registration, catalogue=service, page_size=page_size)
    binding = {key: str(uuid.uuid4()) for key in ("investigation_id", "conversation_id", "revision_id")}
    binding.update(snapshot_id=sid, payload_sha256="a" * 64)
    args = {"query": "temperature", "binding": binding, "effective_scope": adapter_scope("ctd").canonical(),
        "permitted_input_manifest": [{"object_id": CTD, "content_sha256": child}], "current_actor": user,
        "expected_policy_revision": resolver.resolve(user, sid).revision}
    return SimpleNamespace(provider=provider, args=args, store=store, service=service, resolver=resolver,
                           policy=policy, sid=sid, child=child, registry=registry)


def test_real_sealed_provider_traverses_all_metadata_pages_and_ranks_stably(tmp_path, monkeypatch):
    actual = fixture(tmp_path, page_size=1)
    calls, original = [], actual.service.list
    monkeypatch.setattr(actual.service, "list", lambda request, user: (calls.append(deepcopy(request)), original(request, user))[1])
    result = actual.provider.search(**actual.args)
    assert len(calls) >= 3 and any("cursor" in request for request in calls)
    assert result["excerpts"] and result["ranking_version"] == "lexical-en-ja-v1"
    assert [item["document_id"] for item in result["excerpts"]] == sorted(item["document_id"] for item in result["excerpts"])
    assert actual.provider.search(**actual.args) == result
    assert result["input_count"] == 1
    assert result["inputs"] == actual.args["permitted_input_manifest"]
    assert "not establish inventory totals" in result["qualifications"][0]


def test_japanese_exact_utf8_windows_reopen_without_normalized_offsets(tmp_path):
    text = "前置き。" * 150 + "水温の測定方法と採水手順。" * 100
    actual = fixture(tmp_path, texts=[text])
    result = actual.provider.search(**{**actual.args, "query": "水温測定"})
    excerpt = result["excerpts"][0]
    raw = text.encode()[excerpt["start_byte"]:excerpt["end_byte"]]
    assert raw.decode() == excerpt["text"]
    assert hashlib.sha256(raw).hexdigest() == excerpt["excerpt_sha256"]
    assert excerpt["source_content_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert len(raw) <= 2048 and excerpt["suffix_omitted"]
    assert "水温" in excerpt["text"]


def test_excerpt_window_uses_earliest_match_independent_of_token_iteration(tmp_path):
    from orchestration.frozen_documentary import _excerpt
    text = "x " * 1000 + "temperature " + "x " * 1500 + "sampling"
    assert _excerpt(text, ["sampling", "temperature"]) == _excerpt(text, ["temperature", "sampling"])
    assert "temperature" in _excerpt(text, ["sampling", "temperature"])["text"]


def test_documentary_metadata_requires_explicit_source_contract_version():
    from orchestration.frozen_documentary import DocumentaryIndex
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DocumentaryIndex.model_validate({"documents": []})


def test_opaque_pre_c21_metadata_is_not_invented_documentary_text(tmp_path):
    actual = fixture(tmp_path, legacy_only=True)
    payload = actual.provider.search(**actual.args)
    assert payload["excerpts"] == []
    assert any("no supported versioned documentary text index" in item for item in payload["qualifications"])
    assert "fixture://ctd" not in str(payload)
    actual.provider.verify_result(payload, **actual.args)


def test_explicit_incompatible_documentary_index_version_fails_closed(tmp_path):
    actual = fixture(tmp_path, index_version="c21-documentary-source-unsupported")
    with pytest.raises(DocumentaryUnavailable):
        actual.provider.search(**actual.args)


def test_new_snapshot_changed_text_keeps_old_exact_content_and_identity(tmp_path):
    first = fixture(tmp_path / "first", texts=["Temperature protocol original."])
    later = fixture(tmp_path / "later", texts=["Temperature protocol changed."])
    old = first.provider.search(**first.args)["excerpts"][0]
    new = later.provider.search(**later.args)["excerpts"][0]
    assert first.sid != later.sid and old["excerpt_id"] != new["excerpt_id"]
    assert "original" in old["text"] and "changed" in new["text"]
    assert first.provider.search(**first.args)["excerpts"][0] == old


def test_denied_document_excluded_before_topk_and_no_hidden_names(tmp_path):
    actual = fixture(tmp_path)
    actual.policy["denied"].add("documentation:0000")
    actual.policy["epoch"] += 1
    args = {**actual.args, "expected_policy_revision": actual.resolver.resolve(actual.args["current_actor"], actual.sid).revision, "limit": 1}
    result = actual.provider.search(**args)
    assert len(result["excerpts"]) == 1
    assert result["excerpts"][0]["definition_id"] != "documentation:0000"
    assert "candidate_count" not in result and "total_documents" not in result


@pytest.mark.parametrize("target", ["index", "child"])
def test_current_withdrawal_blocks_even_retained_snapshot(tmp_path, target):
    actual = fixture(tmp_path)
    actual.provider.search(**actual.args)
    actual.store.revoke(actual.sid if target == "index" else actual.child)
    with pytest.raises(DocumentaryUnavailable):
        actual.provider.search(**actual.args)


def test_policy_change_during_listing_discards_results(tmp_path, monkeypatch):
    actual = fixture(tmp_path)
    original = actual.service.list
    def changed(request, user):
        result = original(request, user)
        actual.policy["epoch"] += 1
        return result
    monkeypatch.setattr(actual.service, "list", changed)
    with pytest.raises(DocumentaryUnavailable, match="access_changed"):
        actual.provider.search(**actual.args)


@pytest.mark.parametrize("change", [
    lambda document: document.update(content_sha256="f" * 64),
    lambda document: document["input_bindings"][0].update(child_snapshot_id="f" * 64),
    lambda document: document["input_bindings"][0].update(source_id="another-source"),
])
def test_bad_registered_text_or_source_binding_fails_honestly(tmp_path, change):
    actual = fixture(tmp_path, change=change)
    with pytest.raises(DocumentaryUnavailable):
        actual.provider.search(**actual.args)


def test_documentary_scope_and_host_pin_manifest_cannot_broaden(tmp_path):
    actual = fixture(tmp_path, change=lambda document: document["applicability_scope"]["sources"]["ctd"]["filters"].update(bay="M"))
    assert actual.provider.search(**actual.args)["excerpts"] == []
    actual = fixture(tmp_path / "pins")
    assert actual.provider.search(**{**actual.args, "permitted_input_manifest": []})["excerpts"] == []
    with pytest.raises(DocumentaryUnavailable, match="input_binding"):
        actual.provider.search(**{**actual.args, "permitted_input_manifest": [{"object_id": CTD, "content_sha256": "b" * 64}]})


def test_tampering_real_sealed_registry_bytes_rejected(tmp_path):
    actual = fixture(tmp_path)
    # The store's actual sealed object paths are discovered from its immutable
    # layout, never by replacing its read() method with a fabricated return.
    matches = [entry for entry in actual.store.root.rglob("*") if entry.is_file() and entry.read_bytes().startswith(b'{"analyses"')]
    assert matches
    matches[0].write_bytes(b"tampered")
    with pytest.raises(DocumentaryUnavailable):
        actual.provider.search(**actual.args)


def test_actual_c13_inventory_input_ids_and_registry_provenance_are_verified(tmp_path):
    actual = fixture(tmp_path)
    result = actual.service.query({"snapshot_id": actual.sid, "scope": actual.args["effective_scope"],
        "operation_id": "c13.inventory", "operation_version": "c13-v1", "input_ids": ["root:data"], "parameters": {"limit": 1}}, actual.args["current_actor"])
    inputs = result["receipt"]["inputs"]
    assert any(item["object_id"].startswith("c13:input:") for item in inputs)
    args = {**actual.args, "permitted_input_manifest": inputs}
    payload = actual.provider.search(**args)
    assert payload["excerpts"] and payload["input_count"] == len(inputs)
    expected_inputs = sorted(({"object_id": item["object_id"], "content_sha256": item["content_sha256"]}
                              for item in inputs), key=lambda item: item["object_id"])
    from schema.research_controller import canonical_hash
    assert payload["inputs"] == expected_inputs and payload["input_sha256"] == canonical_hash(expected_inputs)
    actual.provider.verify_result(payload, **args)
    assert actual.provider.search(**{**args, "permitted_input_manifest": inputs + inputs}) == payload
    assert actual.provider.identity.startswith("c21:documentary:")
    assert actual.provider.search(**{**args, "permitted_input_manifest": [
        {key: value for key, value in item.items() if key != "source_generation" or value is not None} for item in inputs]}) == payload
    payload["excerpts"][0]["text"] = "forged"
    with pytest.raises(DocumentaryUnavailable, match="result_changed"):
        actual.provider.verify_result(payload, **args)


def test_c13_provenance_is_validated_even_when_not_part_of_normalized_input_hash(tmp_path):
    actual = fixture(tmp_path)
    manifest, _ = actual.store.read(actual.sid)
    obj = next(item for item in manifest.objects if item.role == "scientific_registry")
    inputs = [*actual.args["permitted_input_manifest"], {"object_id": obj.object_id,
        "content_sha256": obj.sha256, "source_generation": "forged-generation"}]
    with pytest.raises(DocumentaryUnavailable, match="input_binding"):
        actual.provider.search(**{**actual.args, "permitted_input_manifest": inputs})


def test_invalid_limits_and_backwards_clock_have_no_success(tmp_path):
    actual = fixture(tmp_path)
    with pytest.raises(DocumentaryUnavailable, match="invalid_request"):
        actual.provider.search(**{**actual.args, "limit": True})
    times = iter([2.0, 1.0])
    actual.provider.clock = lambda: next(times)
    with pytest.raises(DocumentaryUnavailable, match="invalid_clock"):
        actual.provider.search(**actual.args)
