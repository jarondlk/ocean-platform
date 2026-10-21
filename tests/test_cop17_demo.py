"""Professor's October 21 query regressions over synthetic published rows."""
from copy import deepcopy

import pytest
import config
from orchestration.research_intents import QUESTIONS, ResearchIntent, parse_intent, render_research
from tests.test_research_chat import research_chat_fixture, scope_for

E3_B = "Which fish species were most frequently detected along the Miyagi coast from 2020 to 2023? Show the top 10, including the denominators and yearly changes."
E4_B = "Compare fish eDNA detection frequencies under high and low sea surface temperatures in Miyagi. Show a representative time series and cite the datasets."
RECIPE = {"region_id": "miyagi-regional-demo", "time_from": "2020-01-01", "time_to": "2023-12-31"}


@pytest.mark.parametrize("query,kind", [
    (E3_B, "fish_frequency"), (E4_B, "temperature_comparison"),
    ("Please show which fish are most frequently detected in Miyagi during 2020–2023, with annual and seasonal changes.", "fish_frequency"),
    ("How do fish detection frequencies compare between warmer and colder SST conditions?", "temperature_comparison"),
    ("宮城県沿岸で2020年から2023年の魚の検出頻度の上位10種を分母と年別の変化も含めて示してください。", "fish_frequency"),
    ("宮城県沿岸の高い海面水温と低い海面水温の条件で魚の検出頻度を比較し、代表的な時系列とデータセットの出典を示してください。", "temperature_comparison"),
])
def test_bilingual_paraphrases_preserve_workflow(query, kind, monkeypatch):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", True)
    assert parse_intent(query, RECIPE) == kind


@pytest.mark.parametrize("query", [
    E3_B.replace("Miyagi", "Hokkaido"), E3_B.replace("Miyagi", "Onagawa"),
    E3_B.replace("2023", "2024"), E3_B.replace("2020", "2019"),
    E3_B.replace("top 10", "top 5"), E3_B.replace("fish species", "shark species"),
    E3_B + " Excluding sardines.", E3_B + " Only environmental samples.",
    E3_B + " Use MiSeq and NovaSeq together.", E3_B + " Recalculate the denominator.",
    E3_B.replace("yearly changes", "yearly abundance"),
    E4_B + " Explain the causal effects.", E4_B + " for 2022 only",
    E4_B.replace("high and low", "above 20 C and below 10 C"),
    "Compare fish detection frequencies in SST conditions.",
    "Show the top fish detection frequencies in 2019",
    "宮城県の魚の検出頻度の上位5種を示してください。",
    "岩手県の高い海面水温と低い海面水温で魚の検出頻度を比較してください。",
])
def test_unknown_or_conflicting_qualifiers_fail_closed(query, monkeypatch):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", True)
    assert parse_intent(query, RECIPE) is None


def test_profile_is_opt_in(monkeypatch):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", False)
    assert parse_intent(E3_B, RECIPE) is None
    assert parse_intent(QUESTIONS["fish_frequency"][0], RECIPE) == "fish_frequency"


@pytest.mark.parametrize("query,kind", [(E3_B, "fish_frequency"), (E4_B, "temperature_comparison")])
def test_professor_questions_select_identical_rows_and_citations(tmp_path, monkeypatch, query, kind):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", True)
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    # Synthetic rows retain their exact values; this fixture declares Miyagi
    # only to exercise the literal region matching, not real scientific results.
    bundle = deepcopy(bundle)
    bundle["recipe"].update(RECIPE)
    scope = scope_for(bundle["manifest"]["id"])
    protocol = bundle["tables"]["membership"][0]["protocol_id"]
    intent = ResearchIntent(kind=kind, protocol_id=protocol)
    exact = render_research(bundle, scope, QUESTIONS[kind][0], intent)
    varied = render_research(bundle, scope, query, intent)
    assert exact.reason is None and varied.reason is None
    assert varied.documents == exact.documents
    assert varied.diagnostics == exact.diagnostics
    assert not varied.diagnostics["model_invoked"]
    # Wording cannot override disabled required sources or a pinned filter.
    scope["sources"]["edna_metabarcoding"]["filters"] = {"provider_run_id": "unrelated"}
    assert render_research(bundle, scope, query, intent).reason == "aggregate_scope_required"
    scope["sources"]["edna_metabarcoding"]["enabled"] = False
    assert render_research(bundle, scope, query, intent).reason == "source_disabled"
