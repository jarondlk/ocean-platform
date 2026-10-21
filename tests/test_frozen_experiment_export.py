"""C22 actual sealed synthetic C09/C13/C14/C17 inputs; no execution/data access."""
from dataclasses import FrozenInstanceError
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import create_engine, event

from db.app_models import AppBase
from ingestion.immutable_bundle import digest
from ingestion.scientific_catalogue_inputs import load_registry
from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.catalogue_service import CataloguePolicy, CatalogueService, FrozenCatalogueResolver
from orchestration.frozen_experiment_export import (
    FrozenExperimentExport, FrozenExperimentExporter, FrozenExperimentExportError,
    MACHINE_VERSION, PinnedSourcePublicationPolicy, SourcePublicationDecision,
    machine_table_bytes,
)
from orchestration.investigations import InvestigationService
from orchestration.research_intents import QUESTIONS
from preprocessing.edna_analysis import protocol
from schema.edna_catalogue_fixtures import edna_fixture, edna_scope, seal_edna_fixture
from schema.context_catalogue import canonical_json
from schema.research_experiments import ExperimentProposal
from schema.scientific_catalogue import ScientificRegistry
from schema.scientific_catalogue_fixtures import seal_scientific_fixture
from tests.investigation_support import make_investigation_fixture
from tests.test_conference_demo import miyagi_choices
from tests.test_scientific_catalogue_relationships import physical_relationship_fixture


def synthetic_policy(store, registrations, *, withdrawn=()):
    """Explicit test-only decisions; no inferred operational/scientific approval."""
    decisions = {}
    for registration in registrations.values():
        registry = load_registry(*store.read(registration.snapshot_id))
        for binding in registry.metadata.datasets:
            manifest, _ = store.read(binding.snapshot_id)
            capture = next(item for item in manifest.source_captures if item.source_id == binding.source_id)
            decision = SourcePublicationDecision(
                binding.snapshot_id, binding.dataset_id, binding.source_id,
                capture.publication_generation,
                {item.object_id: item.sha256 for item in manifest.objects if item.dataset_id == binding.dataset_id},
                "fixture://c22-explicit-synthetic-decision", binding.dataset_id not in withdrawn, True)
            decisions[(binding.snapshot_id, binding.dataset_id)] = decision
    return PinnedSourcePublicationPolicy(policy_id="synthetic-only:c22", revision="synthetic-decision-v1",
                                         decisions=decisions.values())


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    directory = tmp_path_factory.mktemp("c22-export-actual")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("ENABLE_V1_CATALOGUE", "true")
        patch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
        engine = create_engine("sqlite+pysqlite:///" + str(directory / "separate-v1.sqlite"))

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        AppBase.metadata.create_all(engine)
        fixture = make_investigation_fixture(engine, directory)
        yield fixture
        engine.dispose()


@pytest.fixture(autouse=True)
def enabled(actual, monkeypatch):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
    for denied in actual.policy.values():
        denied.clear()


def frozen(fixture, *, scope=None, pins=(), attachments=()):
    service, actor = fixture.service, fixture.user
    result = service.invoke("create", {"name": "Synthetic C22 input review", "snapshot_id": fixture.snapshots[0],
        "scope": scope or fixture.scope, "idempotency_key": str(uuid.uuid4())}, actor)
    for op, refs in (("pin", pins), ("attach", attachments)):
        for reference in refs:
            result = service.invoke("context/change", {"investigation_id": result["investigation"]["id"],
                "expected_revision_id": result["context"]["id"], "idempotency_key": str(uuid.uuid4()),
                "change": {"op": op, "reference": reference}}, actor)
    chat = service.invoke("conversations/create", {"investigation_id": result["investigation"]["id"],
        "name": "Synthetic C22 chat", "idempotency_key": str(uuid.uuid4())}, actor)
    return service.load_for_submission(investigation_id=result["investigation"]["id"],
        conversation_id=chat["conversation"]["id"], revision_id=result["context"]["id"], user=actor)


def proposal(fixture, *selections, **changes):
    return ExperimentProposal.model_validate({"question": "Review the explicitly selected synthetic cohort",
        "cohort": {"selections": list(selections) or [selection(fixture)]},
        "method": "Review only; no execution", "assumptions": ["Synthetic test inputs"],
        "python_code": "print('review only')\n", "expected_outputs": [{"name": "review.json", "kind": "table", "description": "Synthetic output declaration"}],
        "environment_id": "a" * 64, "limitations": ["No actual scientific inference or approval"], **changes})


def selection(fixture, family="ctd", table="casts", columns=None):
    return {"target_id": fixture.source_dataset_ids[family], "table": table,
            "columns": columns or {"casts": ["cast_id"], "depth_observations": ["depth"],
                "collections": ["library_id"], "run_qc": ["reads"], "kraken_abundance": ["abundance"],
                "metaeuk_abundance": ["abundance"], "ranked_taxa": ["abundance"],
                "observations": ["value"], "occurrences": ["sample_id"],
                "assays": ["assay_id"], "detections": ["read_count"], "classifications": ["sample_kind"]}[table]}


def exporter(fixture, **changes):
    return FrozenExperimentExporter(store=fixture.store, catalogue=fixture.service.catalogue,
        registrations=fixture.registrations,
        **{"publication_policy": synthetic_policy(fixture.store, fixture.registrations), **changes})


def table(exported, ordinal=1):
    return json.loads(exported.files[f"table-{ordinal:02d}.json"])


def registered_fixture(original, snapshot_id, scope):
    registrations = {snapshot_id: register_scientific_snapshot(store=original.store,
        snapshot_id=snapshot_id, registration_id="synthetic:c22:" + snapshot_id)}
    catalogue = CatalogueService(resolver=FrozenCatalogueResolver(store=original.store,
        registrations=registrations, policy_resolver=lambda *args: CataloguePolicy(revision="synthetic-c22",
            dataset_eligible=lambda *args: True, scientific_eligible=lambda *args: True)))
    service = InvestigationService(session_factory=original.factory, site_id="v1:c22-synthetic",
        catalogue_service=catalogue, snapshot_store=original.store, registrations=registrations)
    return SimpleNamespace(store=original.store, registrations=registrations, service=service,
        user=original.user, snapshots=(snapshot_id,), scope=scope, source_dataset_ids=original.source_dataset_ids)


def test_actual_complete_ctd_export_is_deterministic_reconstructible_and_detached(actual):
    context, plan, service = frozen(actual), proposal(actual), exporter(actual)
    first = service.freeze(frozen=context, proposal=plan, user=actual.user)
    second = service.freeze(frozen=context, proposal=plan, user=actual.user)
    assert first.manifest_json == second.manifest_json and first.files == second.files
    assert table(first)["version"] == MACHINE_VERSION
    assert len(table(first)["rows"]) == 4
    assert first.manifest["tables"][0]["entity"] == "casts"
    assert set(first.snapshot_ids) == {context["snapshot_id"], first.manifest["tables"][0]["source_snapshot_id"]}
    assert len(first.manifest["sources"]["datasets"]) == 1
    assert first.manifest["sources"]["datasets"][0]["publication"]["test_only"] is True
    source = first.manifest["sources"]["datasets"][0]
    assert source["source_capture"]["classification_generation"]
    assert source["source_capture"]["relationship_generation"]
    assert all(item["provenance"]["content_sha256"] == item["sha256"] for item in source["object_provenance"])
    assert "metagenome" not in canonical_json(first.manifest["sources"])
    assert first.size_bytes == len(first.manifest_json.encode()) + sum(map(len, first.files.values()))
    restored = FrozenExperimentExport(manifest_json=first.manifest_json, files=dict(first.files))
    assert restored.input_manifest_sha256 == hashlib.sha256(first.manifest_json.encode()).hexdigest()
    assert service.verify(frozen=context, proposal=plan, user=actual.user, exported=restored) is None
    changed = first.manifest
    changed["scope"] = {}
    assert first.manifest["scope"] == context["context"]["scope"]
    with pytest.raises(TypeError):
        first.files["evil.json"] = b"x"
    with pytest.raises(FrozenInstanceError):
        first.size_bytes = 0


@pytest.mark.parametrize("family,role", [("ctd", "depth_observations"), ("metagenome", "run_qc"),
    ("metagenome", "kraken_abundance"), ("remote_sensing", "observations"),
    ("edna_metabarcoding", "occurrences"), ("edna_metabarcoding", "classifications"),
    ("edna_metabarcoding", "assays"), ("edna_metabarcoding", "detections")])
def test_actual_native_selectors_preserve_qualifiers_and_entities(actual, family, role):
    exported = exporter(actual).freeze(frozen=frozen(actual), proposal=proposal(actual, selection(actual, family, role)), user=actual.user)
    result, meta = table(exported), exported.manifest["tables"][0]["scientific_metadata"]
    assert result["rows"] and meta["qualification"]
    assert exported.manifest["tables"][0]["row_count"] == len(result["rows"])
    if family == "ctd":
        assert {"observation_id", "cast_id", "depth"} <= set(result["columns"])
        assert meta["depth_convention"] == "positive_down"
        assert result["scientific_support"][0]["table"] == "casts"
        assert "collection_date" in result["scientific_support"][0]["columns"]
    elif family == "metagenome":
        assert meta["collection_date_precision"]
        if role == "kraken_abundance":
            assert meta["table"]["method"] == "Kraken" and meta["table"]["abundance_denominator"]
    elif family == "remote_sensing":
        assert {"status", "exclusion_reason", "source_sha256", "valid_fraction"} <= set(result["columns"])
        assert meta["units"]["value"] == meta["descriptor"]["unit"]
    else:
        assert meta["population"] == "eligible"
        assert meta["counting_entities"]["sample_id"] == "source_occurrence"
        assert "not organism abundance" in meta["units"]["read_count"]
        assert json.loads(exported.files["exclusions.json"])["rows"]
    assert all(item.get("arrow_type") for item in exported.manifest["tables"][0]["column_schema"])


def test_scope_is_executed_and_anchor_exclusions_cascade_depth_rows(actual):
    selected_scope = json.loads(canonical_json(actual.scope))
    selected_scope["sources"]["ctd"]["filters"] = {"station": "station-1"}
    context = frozen(actual, scope=selected_scope)
    plan = proposal(actual, selection(actual), selection(actual, "ctd", "depth_observations"))
    before = exporter(actual).freeze(frozen=context, proposal=plan, user=actual.user)
    ids = [row["cast_id"] for row in table(before)["rows"]]
    assert 0 < len(ids) < 4
    changed = plan.model_dump(mode="json")
    changed["cohort"]["exclusions"] = [{"dataset_id": actual.source_dataset_ids["ctd"], "entity": "cast", "ids": ids[:1], "reason": "Explicit synthetic exclusion"}]
    after = exporter(actual).freeze(frozen=context, proposal=changed, user=actual.user)
    assert len(table(after)["rows"]) == len(ids) - 1
    assert all(row["cast_id"] != ids[0] for row in table(after, 2)["rows"])
    assert json.loads(after.files["exclusions.json"])["rows"][0]["reason"] == "Explicit synthetic exclusion"


@pytest.mark.parametrize("policy", ["missing", "withdrawn", "wrong_objects"])
def test_sealing_or_promotion_never_replaces_explicit_current_publication_policy(actual, policy):
    publication = None if policy == "missing" else synthetic_policy(actual.store, actual.registrations,
        withdrawn=[actual.source_dataset_ids["ctd"]] if policy == "withdrawn" else ())
    if policy == "wrong_objects":
        decisions = list(publication.decisions.values())
        decisions = [SourcePublicationDecision(item.child_snapshot_id, item.dataset_id, item.source_id,
            item.publication_generation, {key: "0" * 64 for key in item.object_sha256}, item.decision_reference,
            test_only=True) for item in decisions]
        publication = PinnedSourcePublicationPolicy(policy_id="synthetic", revision="invalid", decisions=decisions)
    with pytest.raises(FrozenExperimentExportError, match="publication_unavailable"):
        exporter(actual, publication_policy=publication).freeze(frozen=frozen(actual), proposal=proposal(actual), user=actual.user)


def test_current_policy_revocation_and_decision_withdrawal_block_reuse(actual):
    context, plan, service = frozen(actual), proposal(actual), exporter(actual)
    exported = service.freeze(frozen=context, proposal=plan, user=actual.user)
    actual.policy[actual.snapshots[0]].add(actual.source_dataset_ids["ctd"])
    with pytest.raises(FrozenExperimentExportError):
        service.verify_access(frozen=context, proposal=plan, user=actual.user, exported=exported)
    actual.policy[actual.snapshots[0]].clear()
    service.publication_policy = synthetic_policy(actual.store, actual.registrations, withdrawn=[actual.source_dataset_ids["ctd"]])
    with pytest.raises(FrozenExperimentExportError, match="publication_unavailable"):
        service.verify(frozen=context, proposal=plan, user=actual.user, exported=exported)


def test_pins_are_binding_and_attachments_remain_supplementary(actual):
    ref = {"kind": "catalogue", "snapshot_id": actual.snapshots[0], "id": actual.source_dataset_ids["ctd"]}
    context = frozen(actual, pins=[ref])
    service = exporter(actual)
    exported = service.freeze(frozen=context, proposal=proposal(actual), user=actual.user)
    assert exported.manifest["pins"] == [ref] and exported.manifest["pin_witnesses"]
    with pytest.raises(FrozenExperimentExportError, match="target_unavailable"):
        service.freeze(frozen=context, proposal=proposal(actual, selection(actual, "metagenome", "collections")), user=actual.user)
    attached = frozen(actual, attachments=[ref])
    result = service.freeze(frozen=attached, proposal=proposal(actual, selection(actual, "metagenome", "collections")), user=actual.user)
    assert result.manifest["attachment_use"].startswith("supplementary_only")
    assert result.manifest["sources"]["datasets"][0]["source_family"] == "metagenome"


def test_distinct_dataset_pins_and_unsupported_definition_pins_do_not_widen(actual):
    pins = [{"kind": "catalogue", "snapshot_id": actual.snapshots[0], "id": actual.source_dataset_ids[family]} for family in ("ctd", "metagenome")]
    for selected in (pins, [{"kind": "catalogue", "snapshot_id": actual.snapshots[0], "id": "synthetic:definition:ctd"}]):
        with pytest.raises(FrozenExperimentExportError, match="unsupported_pin"):
            exporter(actual).freeze(frozen=frozen(actual, pins=selected), proposal=proposal(actual), user=actual.user)


def test_partial_ranked_population_unknown_columns_and_outside_exclusions_refused(actual):
    for plan in (
        proposal(actual, selection(actual, "metagenome", "ranked_taxa")),
        proposal(actual, selection(actual, columns=["invented"])),
        proposal(actual, cohort={"selections": [selection(actual)], "exclusions": [{"dataset_id": actual.source_dataset_ids["ctd"], "entity": "cast", "ids": ["invented"], "reason": "Synthetic"}]}),
    ):
        with pytest.raises(FrozenExperimentExportError):
            exporter(actual).freeze(frozen=frozen(actual), proposal=plan, user=actual.user)


def test_exact_input_size_includes_manifest_sidecars_and_code(actual):
    context = frozen(actual)
    plan = proposal(actual, resources={"max_input_bytes": 100})
    with pytest.raises(FrozenExperimentExportError, match="input_size_exceeded"):
        exporter(actual).freeze(frozen=context, proposal=plan, user=actual.user)
    exported = exporter(actual).freeze(frozen=context, proposal=proposal(actual), user=actual.user)
    metadata = exported.manifest
    metadata["max_input_bytes"] = sum(map(len, exported.files.values()))
    with pytest.raises(FrozenExperimentExportError, match="input_size_exceeded"):
        FrozenExperimentExport(manifest_json=canonical_json(metadata), files=exported.files)


def test_reconstruction_rejects_byte_hash_manifest_domain_and_proposal_tampering(actual):
    context, plan, service = frozen(actual), proposal(actual), exporter(actual)
    exported = service.freeze(frozen=context, proposal=plan, user=actual.user)
    files = dict(exported.files)
    files["table-01.json"] += b" "
    with pytest.raises(FrozenExperimentExportError, match="integrity"):
        FrozenExperimentExport(manifest_json=exported.manifest_json, files=files)
    for patch in ({"source_sha256": "0" * 64}, {"snapshot_ids": exported.manifest["snapshot_ids"] + ["f" * 64]}):
        with pytest.raises(FrozenExperimentExportError, match="integrity"):
            FrozenExperimentExport(manifest_json=canonical_json({**exported.manifest, **patch}), files=exported.files)
    changed = plan.model_dump(mode="json")
    changed["python_code"] = "print('changed')"
    with pytest.raises(FrozenExperimentExportError):
        service.verify_access(frozen=context, proposal=changed, user=actual.user, exported=exported)


def test_machine_bytes_preserve_exact_int64_null_unicode_formula_and_finite_float():
    row = {"integer": 2**63 - 1, "min": -(2**63), "missing": None,
           "text": "=SUM(1,2)\n日本語", "float": 0.12345678901234567, "zero": -0.0}
    raw = machine_table_bytes(columns=list(row), rows=[row])
    assert b"9223372036854775807" in raw and json.loads(raw)["rows"] == [row]
    assert json.loads(raw)["rows"][0]["text"].startswith("=")
    for value in (float("nan"), float("inf"), 2**63, b"bytes"):
        with pytest.raises(FrozenExperimentExportError):
            machine_table_bytes(columns=["value"], rows=[{"value": value}])


def test_actual_sealed_int64_above_browser_safe_range_roundtrips_without_pandas_coercion(actual):
    metadata, frames = edna_fixture(1, dataset_id="synthetic:c22:int64", source_id="synthetic-c22-int64")
    for index, value in enumerate((2**63 - 1, 2**53 + 1)):
        frames["detections"].at[index, "read_count"] = value
        row = frames["detections"].iloc[index].to_dict()
        row.pop("scientific_content_sha256")
        frames["detections"].at[index, "scientific_content_sha256"] = digest(row)
    child = seal_edna_fixture(actual.store, [(metadata, frames)])
    original = load_registry(*actual.store.read(actual.snapshots[0]))
    raw = original.metadata.model_dump(mode="json")
    raw.update(datasets=[{"dataset_id": metadata.dataset_id, "source_id": metadata.source_id, "source_family": "edna_metabarcoding", "snapshot_id": child}], analyses=[], workflows=[], relationships=[], definitions=[])
    sid = seal_scientific_fixture(actual.store, ScientificRegistry.model_validate(raw), {})
    registration = register_scientific_snapshot(store=actual.store, snapshot_id=sid, registration_id="synthetic:c22:int64")
    registrations = {sid: registration}
    catalogue = CatalogueService(resolver=FrozenCatalogueResolver(store=actual.store, registrations=registrations,
        policy_resolver=lambda *args: CataloguePolicy(revision="synthetic-c22", dataset_eligible=lambda *args: True, scientific_eligible=lambda *args: True)))
    context = {"snapshot_id": sid, "scope": actual.scope, "pins": [], "attachments": [], "artifact_bindings": []}
    bound = {"investigation_id": str(uuid.uuid4()), "conversation_id": str(uuid.uuid4()), "revision_id": str(uuid.uuid4()), "snapshot_id": sid, "payload_sha256": digest(context), "context": context}
    plan = proposal(actual, {"target_id": metadata.dataset_id, "table": "detections", "columns": ["read_count"]})
    service = FrozenExperimentExporter(store=actual.store, catalogue=catalogue, registrations=registrations,
        publication_policy=synthetic_policy(actual.store, registrations))
    exported = service.freeze(frozen=bound, proposal=plan, user=actual.user)
    assert {item["read_count"] for item in table(exported)["rows"]} >= {2**63 - 1, 2**53 + 1}
    assert all(type(item["read_count"]) is int for item in table(exported)["rows"])
    assert "9223372036854775807" not in exported.manifest_json  # private values stay outside browser metadata


def test_proximity_never_establishes_physical_pairing(actual):
    plan = proposal(actual, cohort={"selections": [selection(actual)], "pairing": {"mode": "physical_identity", "relationship_ids": ["synthetic:relationship:proximity"]}})
    with pytest.raises(FrozenExperimentExportError, match="physical_pairing_unavailable"):
        exporter(actual).freeze(frozen=frozen(actual), proposal=plan, user=actual.user)


def test_generic_published_table_without_c01_scope_is_unavailable(actual):
    plan = proposal(actual, {"kind": "published_analysis", "target_id": "synthetic:analysis:published", "table": "results", "columns": ["value"]})
    with pytest.raises(FrozenExperimentExportError, match="publication_question_unsupported"):
        exporter(actual).freeze(frozen=frozen(actual), proposal=plan, user=actual.user)


@pytest.mark.parametrize("zero", [False, True])
def test_actual_published_analysis_exports_all_rows_with_original_c01_question(actual, zero):
    source, frames = edna_fixture(1, dataset_id="synthetic:c22:publication-source")
    frames["occurrences"].loc[:, "collection_date_utc"] = "2020-01-01"
    for index, item in frames["occurrences"].iterrows():
        row = item.to_dict()
        row.pop("scientific_content_sha256")
        frames["occurrences"].at[index, "scientific_content_sha256"] = digest(row)
    assay = frames["assays"].iloc[0].to_dict()
    protocol_id = digest(protocol(assay))
    child = seal_edna_fixture(actual.store, [(source, frames)])
    original = load_registry(*actual.store.read(actual.snapshots[0]))
    raw = original.metadata.model_dump(mode="json")
    raw["datasets"] = [{"dataset_id": source.dataset_id, "source_id": source.source_id,
        "source_family": source.family, "snapshot_id": child}]
    option = deepcopy(miyagi_choices()[1])
    option["protocol_ids"] = [protocol_id]
    option["protocols"] = {protocol_id: protocol(assay)}
    option["recipe_scope"]["assignment_method"] = "qcauto_95pct_3nn_target"
    selected = edna_scope(assignment_method="qcauto_95pct_3nn_target", time_from="2020-01-01",
        time_to="2023-12-31", sample_kind="environmental", is_control=False).canonical()
    selected["sources"]["edna_metabarcoding"]["analysis_id"] = option["analysis_id"]
    analysis = raw["analyses"][0]
    analysis.update(id=option["analysis_id"], scope=selected, scope_option=option, input_dataset_ids=[source.dataset_id])
    object_id = analysis["tables"][0]["object_id"]
    rows = [] if zero else original.tables[object_id]
    analysis["tables"][0]["row_count"] = len(rows)
    raw["analyses"] = [analysis]
    raw["workflows"] = [{**raw["workflows"][0], "workflow_kind": "fish_frequency",
        "required_sources": [source.family], "input_dataset_ids": [source.dataset_id], "analysis_ids": [analysis["id"]]}]
    raw["relationships"], raw["definitions"] = [], []
    sid = seal_scientific_fixture(actual.store, ScientificRegistry.model_validate(raw), {object_id: rows})
    fixture = registered_fixture(actual, sid, selected)
    ref = {"kind": "catalogue", "snapshot_id": sid, "id": analysis["id"]}
    context = frozen(fixture, pins=[ref])
    plan = proposal(actual, {"kind": "published_analysis", "target_id": analysis["id"],
        "table": "results", "columns": ["value"]}, question=QUESTIONS["fish_frequency"][0])
    service = exporter(fixture)
    exported = service.freeze(frozen=context, proposal=plan, user=fixture.user)
    assert len(table(exported)["rows"]) == len(rows)
    meta = exported.manifest["tables"][0]["scientific_metadata"]
    assert meta["scope_compatibility"]["outcome"] == "compatible"
    assert meta["analysis"]["independent_researcher_approval"] is False
    assert exported.manifest["question"] == QUESTIONS["fish_frequency"][0]
    assert service.verify(frozen=context, proposal=plan, user=fixture.user, exported=exported) is None
    bad = plan.model_dump(mode="json")
    bad["question"] += " but only for 2024"
    with pytest.raises(FrozenExperimentExportError, match="publication_question_unsupported"):
        service.freeze(frozen=context, proposal=bad, user=fixture.user)
    bad = plan.model_dump(mode="json")
    bad["cohort"]["selections"] = [{"target_id": source.dataset_id, "table": "detections", "columns": ["read_count"]}]
    with pytest.raises(FrozenExperimentExportError, match="publication_pin_requires_exact_table"):
        service.freeze(frozen=context, proposal=bad, user=fixture.user)
    unpinned = frozen(fixture)
    with pytest.raises(FrozenExperimentExportError, match="analysis_selection_requires_exact_table"):
        service.freeze(frozen=unpinned, proposal=bad, user=fixture.user)


def test_actual_verified_physical_pairing_requires_all_retained_scoped_endpoints(actual):
    relationship, datasets = physical_relationship_fixture()
    data = next(iter(datasets.values()))
    frames = {name: frame.copy(deep=True) for name, frame in data.tables.items()}
    # New explicitly synthetic provider classification makes both retained
    # physical endpoints eligible; the physical review fixture is unchanged.
    frames["classifications"].loc[:, "sample_kind"] = "environmental"
    frames["classifications"].loc[:, "is_control"] = False
    child = seal_edna_fixture(actual.store, [(data.metadata, frames)])
    original = load_registry(*actual.store.read(actual.snapshots[0]))
    raw = original.metadata.model_dump(mode="json")
    raw.update(datasets=[{"dataset_id": data.metadata.dataset_id, "source_id": data.metadata.source_id,
        "source_family": data.metadata.family, "snapshot_id": child}], analyses=[], workflows=[], definitions=[], relationships=[relationship])
    sid = seal_scientific_fixture(actual.store, ScientificRegistry.model_validate(raw), {})
    fixture = registered_fixture(actual, sid, edna_scope().canonical())
    selected = {"target_id": data.metadata.dataset_id, "table": "occurrences", "columns": ["sample_id"]}
    plan = proposal(actual, cohort={"selections": [selected], "pairing": {"mode": "physical_identity", "relationship_ids": [relationship["id"]]}})
    context, service = frozen(fixture), exporter(fixture)
    exported = service.freeze(frozen=context, proposal=plan, user=fixture.user)
    proof = json.loads(exported.files["pairing.json"])
    assert proof["relationships"][0]["record"]["category"] == "verified_physical_identity"
    assert proof["comparison_authorized"] is False
    bad = plan.model_dump(mode="json")
    bad["cohort"]["exclusions"] = [{"dataset_id": data.metadata.dataset_id, "entity": "source_occurrence",
        "ids": [relationship["endpoints"][0]["entity_id"]], "reason": "Synthetic exclusion removes endpoint"}]
    with pytest.raises(FrozenExperimentExportError, match="physical_pairing_unavailable"):
        service.freeze(frozen=context, proposal=bad, user=fixture.user)


def test_callback_cannot_claim_a_different_source_publication_generation(actual):
    trusted = synthetic_policy(actual.store, actual.registrations)

    class MisboundPolicy:
        def evaluate(self, **kwargs):
            return {**trusted.evaluate(**kwargs), "publication_generation": "invented-generation"}

    with pytest.raises(FrozenExperimentExportError, match="publication_unavailable"):
        exporter(actual, publication_policy=MisboundPolicy()).freeze(frozen=frozen(actual), proposal=proposal(actual), user=actual.user)


@pytest.mark.parametrize("family,entity,anchor,dependent,key", [
    ("metagenome", "library", "collections", "kraken_abundance", "library_id"),
    ("edna_metabarcoding", "source_occurrence", "occurrences", "detections", "sample_id"),
    ("remote_sensing", "sst_observation", "observations", "observations", "observation_id"),
])
def test_explicit_source_exclusions_cascade_each_native_entity(actual, family, entity, anchor, dependent, key):
    context, service = frozen(actual), exporter(actual)
    selections = [selection(actual, family, anchor)]
    if anchor != dependent:
        selections.append(selection(actual, family, dependent))
    plan = proposal(actual, *selections)
    before = service.freeze(frozen=context, proposal=plan, user=actual.user)
    identity = table(before)["rows"][0][key]
    changed = plan.model_dump(mode="json")
    changed["cohort"]["exclusions"] = [{"dataset_id": actual.source_dataset_ids[family],
        "entity": entity, "ids": [identity], "reason": "Explicit synthetic exclusion; no scientific review claim"}]
    after = service.freeze(frozen=context, proposal=changed, user=actual.user)
    assert len(table(after)["rows"]) == len(table(before)["rows"]) - 1
    if family == "metagenome":
        assert all(row["library_id"] != identity for row in table(after, 2)["rows"])
    elif family == "edna_metabarcoding":
        support = table(after, 2)["scientific_support"]
        occurrences = next(item["rows"] for item in support if item["table"] == "occurrences")
        assert all(row["sample_id"] != identity for row in occurrences)
