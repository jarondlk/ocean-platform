"""Actual sealed C13/C14/C17 publication reads with synthetic C01 metadata.

These invented table rows and test-only operational labels are not scientific
results, publication approval, independent review or real-data evidence.
"""

from types import SimpleNamespace

import pytest

from ingestion.scientific_catalogue_inputs import load_registry
from ingestion.immutable_bundle import digest
from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.catalogue_service import (
    CataloguePolicy,
    CatalogueService,
    FrozenCatalogueResolver,
)
from orchestration.investigations import InvestigationService
from orchestration.research_intents import QUESTIONS
from preprocessing.edna_analysis import protocol
from schema.edna_catalogue_fixtures import edna_fixture, seal_edna_fixture
from schema.scientific_catalogue import ScientificRegistry
from schema.scientific_catalogue_fixtures import seal_scientific_fixture
from tests.test_research_controller import Harness, FakeRuntime, tool, retained  # noqa: F401
from tests.test_research_controller_scope import ANALYSIS, publication


@pytest.fixture(scope="module")
def publication_harness(retained):  # noqa: F811 - imported pytest fixture
    selected, source = publication()
    original = load_registry(*retained.store.read(retained.snapshots[0]))
    registry = original.metadata.model_dump(mode="json")
    analysis = source["details"]["record"]
    dataset = retained.dataset_ids["edna_metabarcoding"]
    binding = next(
        item for item in registry["datasets"] if item["dataset_id"] == dataset
    )
    metadata, frames = edna_fixture(
        12, dataset_id=dataset, source_id=binding["source_id"]
    )
    # This publication's fixed C01 recipe is2020--2023. The reused generic C12
    # fixture starts in2024, so its filtered source disappears and C17 correctly
    # refuses the analysis pin. Seal a NEW synthetic input in the declared period;
    # never weaken source membership or mutate an earlier retained snapshot.
    occurrences = frames["occurrences"]
    for index, row in occurrences.iterrows():
        occurrence = row.to_dict()
        occurrence["collection_date_utc"] = (
            "2020" + occurrence["collection_date_utc"][4:]
        )
        occurrence.pop("scientific_content_sha256")
        occurrences.at[index, "collection_date_utc"] = occurrence["collection_date_utc"]
        occurrences.at[index, "scientific_content_sha256"] = digest(occurrence)
    binding["snapshot_id"] = seal_edna_fixture(
        retained.store,
        [(metadata, frames)],
        publication="c19-test-only-2020-publication-input",
    )
    # The protocol witness must describe an actual retained complete assay, not
    # the pure unit fixture's arbitrary protocol identity or instrument label.
    retained_protocol = protocol(frames["assays"].iloc[0].to_dict())
    protocol_id = digest(retained_protocol)
    analysis["scope_option"]["protocol_ids"] = [protocol_id]
    analysis["scope_option"]["protocols"] = {protocol_id: retained_protocol}
    analysis["input_dataset_ids"] = [dataset]
    analysis["tables"] = []
    tables = {}
    for name in ("ranking", "series"):
        identity = "synthetic:c19:published:" + name
        columns = [
            {"key": "species", "title": {"en": "Species", "ja": "種"}},
            {
                "key": "value",
                "title": {"en": "Synthetic value", "ja": "合成値"},
                "unit": "synthetic_units",
            },
        ]
        rows = [
            {"species": "Synthetic fish A", "value": 1},
            {"species": "Synthetic fish B", "value": 2},
        ]
        tables[identity] = rows
        analysis["tables"].append(
            {
                "name": name,
                "object_id": identity,
                "columns": columns,
                "row_count": len(rows),
                "availability": {"status": "available"},
                "completeness": "complete",
            }
        )
    registry["analyses"] = [analysis]
    registry["workflows"] = [
        {
            "id": "synthetic:c19:frequency",
            "title": {"en": "Synthetic only", "ja": "合成のみ"},
            "purpose": {"en": "Test-only fixed tables", "ja": "テスト専用"},
            "workflow_kind": "fish_frequency",
            "required_sources": ["edna_metabarcoding"],
            "availability": {"status": "available"},
            "input_dataset_ids": [dataset],
            "analysis_ids": [ANALYSIS],
            "limitations": [
                "Synthetic test fixture; no scientific approval or inference"
            ],
            "provenance": {"references": ["C19 test-only fixture"]},
        }
    ]
    registry["relationships"] = []
    registry["definitions"] = []
    sid = seal_scientific_fixture(
        retained.store,
        ScientificRegistry.model_validate(registry),
        tables,
        publication="c19-test-only-published-fixture",
    )
    registered = register_scientific_snapshot(
        store=retained.store,
        snapshot_id=sid,
        registration_id="synthetic:c19:publication",
    )
    registrations = {sid: registered}
    catalogue = CatalogueService(
        resolver=FrozenCatalogueResolver(
            store=retained.store,
            policy_resolver=lambda user, snapshot: CataloguePolicy(
                revision="c19-test-publication",
                dataset_eligible=lambda snapshot, metadata: True,
                scientific_eligible=lambda snapshot, record: True,
            ),
            registrations=registrations,
        )
    )
    service = InvestigationService(
        session_factory=retained.factory,
        site_id="v1:c19-test-publication",
        catalogue_service=catalogue,
        snapshot_store=retained.store,
        registrations=registrations,
    )
    adapted = SimpleNamespace(
        service=service,
        user=retained.user,
        other=retained.other,
        admin=retained.admin,
        scope=selected,
        snapshots=(sid,),
        dataset_ids=retained.dataset_ids,
        protocol_id=protocol_id,
    )
    return Harness(adapted, {"user": retained.user})


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_V1_RESEARCH_CONTROLLER", "true")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")


def pin(harness):
    return {
        "kind": "catalogue",
        "id": ANALYSIS,
        "snapshot_id": harness.retained.snapshots[0],
    }


def page(name, offset, protocol_id):
    return tool(
        "analysis.get_published",
        analysis_id=ANALYSIS,
        workflow_kind="fish_frequency",
        protocol_id=protocol_id,
        table=name,
        limit=1,
        offset=offset,
    )


def test_actual_publication_partial_previews_cannot_finish(publication_harness):
    harness = publication_harness
    request = harness.request(QUESTIONS["fish_frequency"][0], pins=[pin(harness)])
    result = harness.controller(
        FakeRuntime(
            [
                page("ranking", 0, harness.retained.protocol_id),
                page("series", 0, harness.retained.protocol_id),
            ]
        )
    ).execute(request)
    assert result.outcome == "partial" and result.reason == "premature_finish"
    assert not result.completion.complete
    assert result.budget.tool_actions == 4  # pin + inventory + two incomplete tables


def test_actual_publication_all_matching_pages_complete_with_original_binding(
    publication_harness,
):
    harness = publication_harness
    request = harness.request(QUESTIONS["fish_frequency"][0], pins=[pin(harness)])
    runtime = FakeRuntime(
        [
            page(name, offset, harness.retained.protocol_id)
            for name in ("ranking", "series")
            for offset in (0, 1)
        ]
    )
    result = harness.controller(runtime).execute(request)
    assert result.outcome == "completed"
    assert result.budget.tool_actions == 6
    assert result.binding.revision_id == request["revision_id"]
    tables = [
        observation
        for observation in result.observations
        if observation.authority == "published"
    ]
    assert len(tables) == 4 and all(
        observation.preview_truncated for observation in tables
    )
    assert all(observation.page_total_rows == 2 for observation in tables)
    assert all(observation.question_compatibility_sha256 for observation in tables)
    assert any(
        "synthetic_units" in text
        for observation in tables
        for text in observation.qualifications
    )


@pytest.mark.parametrize(
    "question",
    [
        "Show the top 10 fish by detection frequency in Hokkaido from 2020 to 2023",
        "Show the top 10 sharks by detection frequency in Miyagi from 2020 to 2023",
        "北海道で検出頻度が高い魚の上位10種と、年別・季節別の変化を示してください。",
    ],
)
def test_actual_published_template_cannot_override_conflicting_original_question(
    publication_harness, question
):
    harness = publication_harness
    runtime = FakeRuntime([page("ranking", 0, harness.retained.protocol_id)])
    result = harness.controller(runtime).execute(
        harness.request(question, pins=[pin(harness)])
    )
    assert result.outcome == "clarification"
    assert result.budget.tool_actions == 1 and result.budget.model_calls == 0
    assert not result.completion.complete and runtime.calls == []
