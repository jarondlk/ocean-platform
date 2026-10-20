"""C21 deterministic documentary search over explicitly sealed v1 metadata.

This module performs no discovery, acquisition, model call or budget reservation.
The caller must reserve the complete search as one durable tool attempt.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
import unicodedata
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from api.auth import CurrentUser
from ingestion.scientific_catalogue_inputs import load_registry
from orchestration.catalogue_registration import ScientificCatalogueRegistration
from orchestration.catalogue_service import CatalogueService, FrozenCatalogueResolver, catalogue_access_binding
from orchestration.research_controller_scope import ScopeGuardError, _merge_scope
from orchestration.frozen_scientific_catalogue import _id as scientific_id
from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.context_catalogue import CatalogueListing, ContractModel, Identifier, LocalizedText, Sha256
from schema.research_controller import ControllerBinding, canonical_hash, canonical_scope_json
from schema.scientific_catalogue import INDEX_OBJECT_ID

INDEX_VERSION = "c21-documentary-source-v1"
SEARCH_VERSION = "c21-documentary-search-v1"
RANKING_VERSION = "lexical-en-ja-v1"
MAX_DOCUMENTS = 4000
MAX_TEXT_BYTES = 65536
MAX_INDEX_TEXT_BYTES = 16 * 1024 * 1024
MAX_EXCERPT_BYTES = 2048
QUALIFICATION = "Documentary quotations support interpretation; ranked excerpts do not establish inventory totals, coverage, identity or scientific approval."
_Text = Annotated[str, StringConstraints(min_length=1, max_length=65536)]


class DocumentaryUnavailable(ValueError):
    def __init__(self, reason="documentary_unavailable"):
        self.reason = reason
        super().__init__(reason)


class DocumentInput(ContractModel):
    dataset_id: Identifier
    child_snapshot_id: Sha256
    source_id: Identifier
    source_family: Literal["ctd", "metagenome", "remote_sensing", "edna_metabarcoding"]


class FrozenDocument(ContractModel):
    id: Identifier
    title: LocalizedText
    language: Literal["en", "ja"]
    text: _Text
    content_sha256: Sha256
    input_bindings: Annotated[list[DocumentInput], Field(min_length=1, max_length=256)]
    applicability_scope: EvidenceScope
    qualifications: Annotated[list[str], Field(min_length=1, max_length=256)]

    @field_validator("qualifications")
    @classmethod
    def bounded_qualifications(cls, value):
        if any(not text.strip() or len(text.encode("utf-8")) > 10000 for text in value):
            raise ValueError("Bounded visible documentary qualifications required")
        return value

    @model_validator(mode="after")
    def exact_text_and_inputs(self):
        raw = self.text.encode("utf-8")
        if len(raw) > MAX_TEXT_BYTES or hashlib.sha256(raw).hexdigest() != self.content_sha256:
            raise ValueError("Documentary UTF-8 content hash/bound mismatch")
        ids = [item.dataset_id for item in self.input_bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("Documentary inputs must be distinct")
        enabled = {family for family in FAMILIES if getattr(self.applicability_scope.sources, family).enabled}
        if enabled != {item.source_family for item in self.input_bindings}:
            raise ValueError("Documentary scope must bind its actual scientific families")
        return self


class DocumentaryIndex(ContractModel):
    schema_version: Literal["c21-documentary-source-v1"]
    documents: Annotated[list[FrozenDocument], Field(max_length=MAX_DOCUMENTS)]

    @model_validator(mode="after")
    def unique_documents(self):
        if len({item.id for item in self.documents}) != len(self.documents):
            raise ValueError("Documentary IDs must be distinct within a definition")
        return self


def _tokens(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words = re.findall(r"[a-z0-9_]+", normalized)
    for run in re.findall(r"[\u3040-\u30ff\u3400-\u9fff]+", normalized):
        words.extend(run)
        words.extend(run[index:index + 2] for index in range(len(run) - 1))
    return frozenset(words)


def _applicable(document, scope):
    requested = scope.canonical()
    for family in FAMILIES:
        if not getattr(document.applicability_scope.sources, family).enabled:
            requested["sources"][family] = {"enabled": False, "filters": {}}
        elif not getattr(scope.sources, family).enabled:
            return False
    try:
        merged = _merge_scope(document.applicability_scope.canonical(), requested, question=True)
        return merged == EvidenceScope.model_validate(requested).canonical()
    except (ScopeGuardError, ValueError):
        return False


def _excerpt(text, query_tokens):
    # Ranking normalization never determines byte offsets in original text.
    positions = [match.start() for token in query_tokens
                 for match in re.finditer(re.escape(token), text, flags=re.IGNORECASE)]
    if not positions:
        positions = [match.start() for match in re.finditer(r"\S+", text)
                     if _tokens(match.group()) & query_tokens]
    center = min(positions) if positions else 0
    start = max(0, center - 120)
    end = start
    size = 0
    while end < len(text):
        width = len(text[end].encode("utf-8"))
        if size + width > MAX_EXCERPT_BYTES:
            break
        end += 1
        size += width
    encoded = text.encode("utf-8")
    first, last = len(text[:start].encode("utf-8")), len(text[:end].encode("utf-8"))
    raw = encoded[first:last]
    return {"start_byte": first, "end_byte": last, "text": raw.decode("utf-8"),
            "excerpt_sha256": hashlib.sha256(raw).hexdigest(),
            "prefix_omitted": first > 0, "suffix_omitted": last < len(encoded)}


class FrozenDocumentaryProvider:
    """A real C09/C13/C14 path with no legacy/global/current-source fallback."""

    def __init__(self, *, store, registration, catalogue, clock=time.monotonic, page_size=500):
        if (not isinstance(registration, ScientificCatalogueRegistration)
                or not isinstance(catalogue, CatalogueService)
                or not isinstance(catalogue.resolver, FrozenCatalogueResolver)
                or catalogue.resolver.store is not store
                or catalogue.resolver.registrations.get(registration.snapshot_id) != registration
                or type(page_size) is not int or not 1 <= page_size <= 500 or not callable(clock)):
            raise ValueError("Explicit same-store sealed documentary dependencies required")
        self.store, self.registration, self.catalogue = store, registration, catalogue
        self.clock, self.page_size = clock, page_size
        self.identity = "c21:documentary:" + canonical_hash({
            "provider_version": SEARCH_VERSION, "ranking_version": RANKING_VERSION,
            "snapshot_id": registration.snapshot_id, "registration_id": registration.registration_id,
            "page_size": page_size, "max_excerpt_bytes": MAX_EXCERPT_BYTES,
            "max_documents": MAX_DOCUMENTS, "max_index_text_bytes": MAX_INDEX_TEXT_BYTES})

    def verify_result(self, payload, **original_search_args):
        """Revalidate one retained search, never grant authority to arbitrary JSON.

        This is verification of the already reserved operation. Its work must
        remain inside the caller's active-time accounting and current access.
        """
        if not isinstance(payload, dict) or self.search(**original_search_args) != payload:
            raise DocumentaryUnavailable("documentary_result_changed")

    def search(self, *, query, binding, effective_scope, permitted_input_manifest,
               current_actor, expected_policy_revision, limit=8, remaining_timeout=30):
        try:
            return self._search(query=query, binding=binding, effective_scope=effective_scope,
                permitted_input_manifest=permitted_input_manifest, current_actor=current_actor,
                expected_policy_revision=expected_policy_revision, limit=limit,
                remaining_timeout=remaining_timeout)
        except DocumentaryUnavailable:
            raise
        except Exception:
            raise DocumentaryUnavailable() from None

    def _search(self, *, query, binding, effective_scope, permitted_input_manifest,
                current_actor, expected_policy_revision, limit, remaining_timeout):
        binding = ControllerBinding.model_validate(binding)
        scope = EvidenceScope.model_validate(effective_scope)
        if (not isinstance(current_actor, CurrentUser) or not isinstance(query, str)
                or not query.strip() or len(query.encode("utf-8")) > 32000
                or type(limit) is not int or not 1 <= limit <= 25
                or type(remaining_timeout) not in (int, float) or not math.isfinite(remaining_timeout)
                or not 0 < remaining_timeout <= 180 or binding.snapshot_id != self.registration.snapshot_id):
            raise DocumentaryUnavailable("documentary_invalid_request")
        started = self.clock()
        if type(started) not in (int, float) or not math.isfinite(started):
            raise DocumentaryUnavailable("documentary_invalid_clock")

        last = started

        def fresh():
            nonlocal last
            now = self.clock()
            if type(now) not in (int, float) or not math.isfinite(now) or now < last:
                raise DocumentaryUnavailable("documentary_invalid_clock")
            last = now
            if now - started >= remaining_timeout:
                raise DocumentaryUnavailable("documentary_timeout")
            self.registration.require_current(self.store)
            resolved = self.catalogue.resolver.resolve(current_actor, binding.snapshot_id)
            if resolved.revision != expected_policy_revision:
                raise DocumentaryUnavailable("documentary_access_changed")
            return resolved

        fresh()
        manifest, contents = self.store.read(binding.snapshot_id)
        registry = load_registry(manifest, contents)
        index_object = next(item for item in manifest.objects if item.object_id == INDEX_OBJECT_ID)
        inputs, supplied_inputs = {}, {}
        bindings = {item.dataset_id: item for item in registry.metadata.datasets}
        canonical_inputs = {scientific_id("input", identity): identity for identity in bindings}
        objects = {item.object_id: item for item in manifest.objects}
        for item in permitted_input_manifest:
            if (not isinstance(item, dict) or not {"object_id", "content_sha256"} <= item.keys()
                    or item.keys() - {"object_id", "content_sha256", "source_generation"}):
                raise DocumentaryUnavailable("documentary_input_binding")
            identity = item["object_id"]
            if identity in supplied_inputs:
                if supplied_inputs[identity] != item:
                    raise DocumentaryUnavailable("documentary_input_binding")
                continue
            supplied_inputs[identity] = dict(item)
            dataset_id = canonical_inputs.get(identity, identity if identity in bindings else None)
            if dataset_id is not None:
                if dataset_id in inputs or bindings[dataset_id].snapshot_id != item["content_sha256"] or item.get("source_generation") is not None:
                    raise DocumentaryUnavailable("documentary_input_binding")
                inputs[dataset_id] = item["content_sha256"]
            elif identity not in objects or objects[identity].sha256 != item["content_sha256"] or (
                    "source_generation" in item and item["source_generation"] != objects[identity].provenance.source_generation):
                raise DocumentaryUnavailable("documentary_input_binding")
        visible, cursor, seen = set(), None, set()
        while True:
            fresh()
            request = {"snapshot_id": binding.snapshot_id, "scope": scope.canonical(),
                       "filters": {"roots": ["metadata"]}, "limit": self.page_size}
            if cursor is not None:
                request["cursor"] = cursor
            page = CatalogueListing.model_validate(self.catalogue.list(request, current_actor))
            if (page.request.access_revision != expected_policy_revision or page.query_completion != "complete"
                    or page.availability.status != "available"):
                raise DocumentaryUnavailable("documentary_access_changed")
            for item in page.items:
                if item.id in visible:
                    raise DocumentaryUnavailable("documentary_pagination")
                visible.add(item.id)
            cursor = page.next_cursor
            if cursor is None:
                break
            if cursor in seen:
                raise DocumentaryUnavailable("documentary_pagination")
            seen.add(cursor)
        candidates, total_bytes, document_count = [], 0, 0
        unsupported_metadata = False
        query_tokens = _tokens(query)
        for definition in registry.metadata.definitions:
            fresh()
            if definition.category != "source_documentation" or definition.id not in visible:
                continue
            if "schema_version" not in definition.values:
                unsupported_metadata = True
                continue
            index = DocumentaryIndex.model_validate(definition.values)
            for document in index.documents:
                document_count += 1
                total_bytes += len(document.text.encode("utf-8"))
                if document_count > MAX_DOCUMENTS or total_bytes > MAX_INDEX_TEXT_BYTES:
                    raise DocumentaryUnavailable("documentary_capacity")
                if set(item.dataset_id for item in document.input_bindings) != set(definition.input_dataset_ids):
                    raise DocumentaryUnavailable("documentary_input_binding")
                for item in document.input_bindings:
                    actual = bindings.get(item.dataset_id)
                    if actual is None or (actual.snapshot_id, actual.source_id, actual.source_family) != (
                            item.child_snapshot_id, item.source_id, item.source_family):
                        raise DocumentaryUnavailable("documentary_input_binding")
                if not set(definition.input_dataset_ids) <= inputs.keys() or not _applicable(document, scope):
                    continue
                score = len(query_tokens & _tokens(document.text + " " + document.title.en + " " + document.title.ja))
                if score:
                    candidates.append((-score, definition.id + ":" + document.id, definition, document))
        excerpts = []
        for _, identity, definition, document in sorted(candidates, key=lambda item: (item[0], item[1]))[:limit]:
            fresh()
            excerpt = {"document_id": identity, "definition_id": definition.id,
                       "title": document.title.model_dump(mode="json"), "language": document.language,
                       "source_content_sha256": document.content_sha256,
                       "input_bindings": [item.model_dump(mode="json") for item in document.input_bindings],
                       "qualifications": list(document.qualifications), **_excerpt(document.text, query_tokens)}
            excerpt["excerpt_id"] = "c21:excerpt:" + canonical_hash({
                "snapshot_id": binding.snapshot_id, "index_object_sha256": index_object.sha256, **excerpt})
            excerpts.append(excerpt)
        fresh()
        manifest_inputs = [{"object_id": key, "content_sha256": supplied_inputs[key]["content_sha256"]}
                           for key in sorted(supplied_inputs)]
        qualifications = [QUALIFICATION, "Search covers registered source-documentation metadata only; top-k is a presentation bound."]
        if unsupported_metadata:
            qualifications.append("Some permitted source-documentation metadata has no supported versioned documentary text index and was not searched.")
        return {"version": SEARCH_VERSION, "binding": binding.model_dump(mode="json"),
                "scope_json": canonical_scope_json(scope.canonical()), "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "operation_id": "c21.documentary.search", "operation_version": "c21-v1",
                "index_snapshot_id": binding.snapshot_id, "index_object_sha256": index_object.sha256,
                "access_binding": catalogue_access_binding(current_actor), "policy_revision": expected_policy_revision,
                "inputs": manifest_inputs, "input_count": len(manifest_inputs), "input_sha256": canonical_hash(manifest_inputs),
                "ranking_version": RANKING_VERSION, "limit": limit, "excerpts": excerpts,
                "qualifications": qualifications}
