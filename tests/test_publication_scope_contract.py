"""Offline scientific scope regressions; a ready model proposal is not authority."""
from copy import deepcopy

import pytest

from api.schemas import ChatRequest
import orchestration.settings_planner as planner
from orchestration.research_question import FREQUENCY_JA
from orchestration.publication_scope import publication_compatibility, scope_option_from_bundle, resolve_protocol, protocol_hints
from orchestration.research_intents import QUESTIONS, ResearchIntent, select_research
from orchestration.research_question import SPATIAL_JA
from tests.test_auto_settings import planning, proposal  # noqa: F401
from tests.test_chat_source_scope import scope
from tests.test_conference_demo import miyagi_choices


F10_QUESTIONS = (
    FREQUENCY_JA.replace("宮城県", "北海道"),
    "Interpret the top 10 fish detection frequencies in Hokkaido from 2020 to 2023",
    FREQUENCY_JA.replace("魚の", "サメの"),
)


@pytest.mark.parametrize("query", F10_QUESTIONS)
@pytest.mark.parametrize("route", ["published_exact", "published_synthesis"])
def test_ready_synthesis_cannot_override_question_scope(query, route, planning):  # noqa: F811
    catalog, output, calls = planning
    catalog["analyses"] = miyagi_choices()
    selected = scope("edna_metabarcoding")
    selected["sources"]["edna_metabarcoding"]["analysis_id"] = "e" * 64
    intent = {"kind": "fish_frequency", "protocol_id": "c" * 64}
    output["value"] = proposal(evidence_scope=deepcopy(selected), route=route,
                               research_intent=intent, required_sources=["edna_metabarcoding"])
    request = ChatRequest(query=query, evidence_scope=selected, research_intent=intent)
    with pytest.raises(planner.PlanningError) as error:
        planner.plan_settings(request)
    assert error.value.status == "clarification_required"
    assert request.evidence_scope.canonical() == selected
    assert request.research_intent.model_dump() == intent
    assert len(calls) == 1  # Stubbed structured output only, no live provider.


SUPPORTED = [(kind, query) for kind, aliases in QUESTIONS.items() for query in aliases] + [
    ("fish_frequency", FREQUENCY_JA),
    ("fish_frequency", "よく見つかる魚は何か？\n" + FREQUENCY_JA.replace("、", "、\n")),
    ("monthly_spatial", SPATIAL_JA.replace("マイワシ", "マイワシ\n")),
    ("fish_frequency", "Interpret the published fish frequencies in Miyagi from 2020 to 2023"),
    ("fish_frequency", "Show published fish frequency using MiSeq paired protocol"),
    ("fish_frequency", "Show published fish frequency using protocol " + "c" * 64),
    ("fish_frequency", FREQUENCY_JA + "MiSeqのペアエンドを使用してください。"),
    ("fish_frequency", FREQUENCY_JA + "手法はqcauto_95pct_3nn_target。"),
    ("fish_frequency", "Show fish frequencies using 3 - NN"),
    ("fish_frequency", "Show published fish frequency from 2020-01-01 to 2023-12-31 using MiSeq paired"),
    ("monthly_spatial", "Show monthly sardine coverage during 2023"),
    ("distribution_change", QUESTIONS["distribution_change"][0] + " from 2020 to 2023"),
]


@pytest.mark.parametrize("kind,query", SUPPORTED)
def test_supported_literals_bind_the_registered_scope_with_traceable_quotes(kind, query):
    result = publication_compatibility(query, kind, miyagi_choices()[1], protocol_id="c" * 64)
    assert result.outcome == "compatible", result
    assert result.version == "publication-scope-v1"
    assert all(e.quote is None or e.quote in query for e in result.evidence)
    assert all("matches" in e.reason for e in result.evidence)


UNSUPPORTED = [
    ("fish_frequency", "Interpret the top 10 sharks detection frequencies in Miyagi from 2020 to 2023"),
    ("fish_frequency", "Interpret the published fish frequencies in Sendai Bay"),
    ("fish_frequency", "Interpret the published fish frequencies in Hokkaido"),
    ("fish_frequency", "Interpret the published fish frequencies during last year"),
    ("fish_frequency", "Interpret the published fish frequencies from 2020 to 2024"),
    ("fish_frequency", "Interpret the published fish frequencies during 2023-02-30"),
    ("fish_frequency", "Interpret the published fish frequencies excluding sardines"),
    ("fish_frequency", "Interpret the published fish frequencies without Sardinops melanostictus"),
    ("fish_frequency", "Interpret the published fish frequencies including negative controls"),
    ("fish_frequency", "Show published fish frequency using DNBSEQ"),
    ("fish_frequency", "Show published fish frequency using BLAST assignment method"),
    ("fish_frequency", "Show published fish frequency using qcauto_target"),
    ("fish_frequency", "Show published fish frequency using NextSeq single-end"),
    ("fish_frequency", "Show published fish frequency using MiSeq single-end"),
    ("fish_frequency", "Show published fish frequency using 18S"),
    ("fish_frequency", "Show published fish frequency using an alternate primer set"),
    ("fish_frequency", "Show published fish frequency using protocol " + "f" * 64),
    ("fish_frequency", FREQUENCY_JA + "カタクチイワシだけを対象にしてください。"),
    ("fish_frequency", FREQUENCY_JA + "12S以外を使用してください。"),
    ("fish_frequency", FREQUENCY_JA + "NextSeqのシングルエンドを使用してください。"),
    ("fish_frequency", FREQUENCY_JA + "手法はBLAST。"),
    ("fish_frequency", FREQUENCY_JA.replace("上位10種", "上位5種")),
    ("monthly_spatial", SPATIAL_JA.replace("マイワシ", "カタクチイワシ")),
    ("monthly_spatial", SPATIAL_JA.replace("2023", "2022")),
    ("temperature_comparison", QUESTIONS["temperature_comparison"][0] + " with top 20 instead"),
    ("distribution_change", QUESTIONS["distribution_change"][0] + " with top 10 instead"),
    ("follow_through", QUESTIONS["follow_through"][0] + " with a new fish panel"),
]


@pytest.mark.parametrize("kind,query", UNSUPPORTED)
def test_every_unresolved_or_conflicting_qualifier_prevents_eligibility(kind, query):
    result = publication_compatibility(query, kind, miyagi_choices()[1], protocol_id="c" * 64)
    assert result.outcome in {"incompatible", "unresolved"}
    assert any(e.outcome != "compatible" for e in result.evidence)
    assert all(e.quote is None or e.quote in query for e in result.evidence)


@pytest.mark.parametrize("kind,query", UNSUPPORTED)
@pytest.mark.parametrize("route", ["published_exact", "published_synthesis"])
def test_ready_routes_require_clarification_and_retain_pins(kind, query, route, planning):  # noqa: F811
    catalog, output, _ = planning
    catalog["analyses"] = miyagi_choices()
    selected = scope("edna_metabarcoding", "remote_sensing")
    selected["sources"]["edna_metabarcoding"]["analysis_id"] = "e" * 64
    selected["sources"]["remote_sensing"]["filters"]["dataset_id"] = "mur-miyagi-2020-2023"
    intent = {"kind": kind, "protocol_id": "c" * 64}
    output["value"] = proposal(evidence_scope=deepcopy(selected), route=route, research_intent=intent,
                               required_sources=["edna_metabarcoding", "remote_sensing"])
    request = ChatRequest(query=query, evidence_scope=selected, research_intent=intent)
    with pytest.raises(planner.PlanningError) as error:
        planner.plan_settings(request)
    assert error.value.status == "clarification_required"
    assert request.evidence_scope.canonical() == selected
    assert request.research_intent.model_dump() == intent


@pytest.mark.parametrize("kind,field", [("fish_frequency", "region_id"), ("fish_frequency", "fish_classes"),
                                      ("monthly_spatial", "spatial_taxon_key"),
                                      ("temperature_comparison", "sst_panel_id"),
                                      ("distribution_change", "endpoint_from")])
def test_missing_registration_cannot_prove_compatibility(kind, field):
    option = miyagi_choices()[1]
    option["recipe_scope"].pop(field)
    result = publication_compatibility(QUESTIONS[kind][0], kind, option, protocol_id="c" * 64)
    assert result.outcome == "unresolved"
    assert any(e.field == field and e.outcome == "unresolved" for e in result.evidence)


def test_species_rank_and_literal_endpoint_years_cannot_be_substituted():
    option = miyagi_choices()[1]
    option["recipe_scope"]["rank"] = "genus"
    assert publication_compatibility(QUESTIONS["fish_frequency"][0], "fish_frequency", option).outcome == "incompatible"
    option = miyagi_choices()[1]
    option["recipe_scope"].update(endpoint_from=2021, endpoint_to=2022)
    query = QUESTIONS["distribution_change"][0] + " from 2020 to 2023"
    result = publication_compatibility(query, "distribution_change", option)
    assert result.outcome == "incompatible"
    assert any(e.field == "endpoint_years" for e in result.evidence)
    query = QUESTIONS["distribution_change"][0] + " from 2021 to 2022"
    assert publication_compatibility(query, "distribution_change", option).outcome == "compatible"


@pytest.mark.parametrize("field,value,query", [
    ("sequencing_method", "NotMiSeq", "using MiSeq paired protocol"),
    ("target_gene", "112S", "using 12S"),
])
def test_protocol_attributes_match_whole_registered_tokens(field, value, query):
    option = miyagi_choices()[1]
    option["protocols"]["c" * 64][field] = value
    assert resolve_protocol(option, query, "c" * 64) == (None, False)


@pytest.mark.parametrize("metadata", [None, "", "   "])
def test_missing_instrument_metadata_never_becomes_a_literal_registered_alias(metadata):
    option = miyagi_choices()[1]
    option["protocols"]["c" * 64]["sequencing_method"] = metadata
    query = "Show published fish frequency using None"
    assert "sequencing_method" not in protocol_hints(query, option)
    result = publication_compatibility(query, "fish_frequency", option, protocol_id="c" * 64)
    assert result.outcome == "unresolved"
    assert resolve_protocol(option, "using MiSeq paired", "c" * 64) == (None, False)


@pytest.mark.parametrize("metadata", [None, "", "   "])
@pytest.mark.parametrize("route", ["published_exact", "published_synthesis"])
def test_ready_model_cannot_authorize_null_or_empty_instrument_metadata(metadata, route, planning):  # noqa: F811
    catalog, output, calls = planning
    catalog["analyses"] = miyagi_choices()
    for option in catalog["analyses"]:
        option["protocols"]["c" * 64]["sequencing_method"] = metadata
    selected = scope("edna_metabarcoding")
    selected["sources"]["edna_metabarcoding"]["analysis_id"] = "e" * 64
    intent = {"kind": "fish_frequency", "protocol_id": "c" * 64}
    output["value"] = proposal(evidence_scope=deepcopy(selected), route=route,
                               research_intent=intent, required_sources=["edna_metabarcoding"])
    request = ChatRequest(query="Show published fish frequency using None", evidence_scope=selected,
                          research_intent=intent)

    with pytest.raises(planner.PlanningError) as error:
        planner.plan_settings(request)

    assert error.value.status == "clarification_required"
    assert error.value.scope_compatibility["outcome"] == "unresolved"
    assert request.evidence_scope.canonical() == selected and request.research_intent.model_dump() == intent
    assert len(calls) == 1  # Recorded synthetic proposal, no provider call.


def test_nonempty_registered_instrument_names_remain_supported_without_null_coercion():
    option = miyagi_choices()[1]
    option["protocols"]["c" * 64]["sequencing_method"] = " CustomSeq-X "
    query = "Show published fish frequency using CustomSeq-X paired protocol"
    assert publication_compatibility(query, "fish_frequency", option, protocol_id="c" * 64).outcome == "compatible"
    option["protocols"]["b" * 64]["sequencing_method"] = "None"
    option["protocols"]["c" * 64]["sequencing_method"] = None
    assert resolve_protocol(option, "using None", "c" * 64) == (None, False)


@pytest.mark.parametrize("count,spacing", [(10, " "), (20, " " * 100), (20, " " * 10000)])
def test_english_numeric_panel_quotes_keep_the_original_span_even_with_long_whitespace(count, spacing):
    query = "Show top" + spacing + str(count) + " fish detection frequencies"
    result = publication_compatibility(query, "fish_frequency", miyagi_choices()[1], protocol_id="c" * 64)
    assert result.outcome == ("compatible" if count == 10 else "incompatible")
    panel_evidence = next(e for e in result.evidence if e.field == "panel_size")
    assert panel_evidence.quote == str(count)


@pytest.mark.parametrize("value", ["sharks", "not supported by this immutable cohort"])
def test_unsupported_selection_values_never_match_diagnostic_text(value):
    option = miyagi_choices()[1]
    selected = scope("edna_metabarcoding")
    selected["sources"]["edna_metabarcoding"]["filters"]["taxon"] = value
    result = publication_compatibility(QUESTIONS["fish_frequency"][0], "fish_frequency", option,
                                       protocol_id="c" * 64, scope=selected)
    assert result.outcome == "incompatible"
    assert any(e.field == "taxon" and e.outcome == "incompatible" for e in result.evidence)


def test_executor_independently_rejects_questions_and_contradictory_selections(tmp_path, monkeypatch):
    from tests.test_research_chat import research_chat_fixture
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    option = scope_option_from_bundle(bundle)
    selected = scope("edna_metabarcoding")
    selected["sources"]["edna_metabarcoding"]["analysis_id"] = bundle["manifest"]["id"]
    protocol_id = option["protocol_ids"][0]
    intent = ResearchIntent(kind="fish_frequency", protocol_id=protocol_id)
    for query in [*F10_QUESTIONS, "Interpret the published fish frequencies in an unknown place",
                  "Show published fish frequency using DNBSEQ"]:
        result = select_research(bundle, selected, query, intent)
        assert result.reason == "aggregate_scope_required" and not result.documents
        assert result.diagnostics["scope_compatibility"]["outcome"] != "compatible"
    changed = deepcopy(selected)
    changed["sources"]["edna_metabarcoding"]["filters"]["provider_run_id"] = "unrelated"
    result = select_research(bundle, changed, QUESTIONS["fish_frequency"][0], intent)
    assert result.reason == "aggregate_scope_required" and not result.documents
    assert selected["sources"]["edna_metabarcoding"]["filters"] == {}


def test_auto_and_executor_bind_the_same_descriptor_and_keep_exact_rows(tmp_path, monkeypatch, planning):  # noqa: F811
    from tests.test_research_chat import research_chat_fixture
    from orchestration.statistics_catalog import analysis_choices
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    catalog, _, _ = planning
    catalog["analyses"] = analysis_choices()
    selected = scope("edna_metabarcoding")
    selected["sources"]["edna_metabarcoding"]["analysis_id"] = bundle["manifest"]["id"]
    query = QUESTIONS["fish_frequency"][0]
    effective, metadata = planner.plan_settings(ChatRequest(query=query, evidence_scope=selected))
    result = select_research(bundle, effective.evidence_scope.canonical(), query, effective.research_intent)
    assert result.reason is None
    assert result.diagnostics["scope_compatibility"] == metadata["scope_compatibility"]
    for document in result.documents:
        lookup = {r["result_id"]: r for r in bundle["tables"][document["table"]]}
        assert all(row == {key: lookup[row["result_id"]][key] for key in row} for row in document["result_rows"])


def test_api_clarification_returns_and_saves_receipt_without_retrieval_or_answer_calls(planning, monkeypatch):  # noqa: F811
    import api.main as api
    from fastapi.testclient import TestClient
    catalog, output, _ = planning
    catalog["analyses"] = miyagi_choices()
    selected = scope("edna_metabarcoding")
    selected["sources"]["edna_metabarcoding"]["analysis_id"] = "e" * 64
    intent = {"kind": "fish_frequency", "protocol_id": "c" * 64}
    output["value"] = proposal(evidence_scope=selected, route="published_synthesis", research_intent=intent,
                               required_sources=["edna_metabarcoding"])
    saved = []
    monkeypatch.setattr(api, "record_chat_context", lambda **kw: saved.append(kw["evidence_snapshot"]))
    monkeypatch.setattr(api, "get_model_runtime", lambda *a, **kw: pytest.fail("No answer model during clarification"))
    monkeypatch.setattr(api, "retrieve_with_expansion", lambda *a, **kw: pytest.fail("No retrieval during clarification"))
    response = TestClient(api.app).post("/chat", json={"query": F10_QUESTIONS[1], "settings_mode": "auto",
                                                       "evidence_scope": selected, "research_intent": intent})
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "abstained" and not body["model_invoked"]
    assert body["options"]["planning"]["status"] == "clarification_required"
    receipt = body["options"]["planning"]["scope_compatibility"]
    assert receipt["outcome"] != "compatible"
    assert body["retrieval_diagnostics"]["scope_compatibility"] == receipt
    assert saved[-1]["retrieval_diagnostics"]["scope_compatibility"] == receipt
    assert body["options"]["requested"]["evidence_scope"] == selected
