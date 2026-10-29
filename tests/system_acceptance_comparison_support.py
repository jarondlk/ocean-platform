"""C26 matched synthetic publication through real legacy and v1 controllers.

The shared snapshot is the immutable logical publication source. The legacy
analysis ID and v1 registry wrapper ID are recorded separately; native wrapper
IDs are never represented as equal. Tables/assay/source hashes are copied into
one NEW sealed v1 fixture. Scripted model actions are fixture evidence only.
"""

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from db.app_models import AppBase
from evaluation.system_acceptance import compare_controllers, content_sha256
from ingestion.scientific_catalogue_inputs import load_registry
from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.catalogue_service import (
    CataloguePolicy,
    CatalogueService,
    FrozenCatalogueResolver,
)
from orchestration.citation_syntax import canonical_tokens
from orchestration.investigations import InvestigationService
from orchestration.publication_scope import scope_option_from_bundle
from orchestration.research_intents import QUESTIONS, ResearchIntent, render_research
from schema.scientific_catalogue import ScientificRegistry
from schema.scientific_catalogue_fixtures import seal_scientific_fixture
from tests.investigation_support import make_investigation_fixture
from tests.test_research_controller import FakeRuntime, Harness, tool
from tests.test_research_controller_publication import publication_harness


def run_publication_comparison(directory, *, source_revision):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        "sqlite+pysqlite:///" + str(directory / "publication-app.sqlite")
    )
    AppBase.metadata.create_all(engine)
    try:
        retained = make_investigation_fixture(engine, directory)
        with pytest.MonkeyPatch.context() as patch:
            for name in (
                "ENABLE_V1_RESEARCH_CONTROLLER",
                "ENABLE_V1_CATALOGUE",
                "ENABLE_V1_INVESTIGATIONS",
            ):
                patch.setenv(name, "true")
            prepared = publication_harness.__wrapped__(retained)
            store = prepared.retained.service.store
            native_original = prepared.retained.snapshots[0]
            original = load_registry(*store.read(native_original))
            record = original.metadata.analyses[0].model_dump(mode="json")
            protocol_id = prepared.retained.protocol_id
            assay = record["scope_option"]["protocols"][protocol_id]
            # Explicit hand-authored synthetic numbers are not a scientific
            # analysis. The independent oracle below is not read from a reply.
            tables = {
                "ranking": [
                    {
                        "result_id": "ranking:A",
                        "species": "Synthetic fish A",
                        "value": 1,
                        "period_kind": "year",
                        "period": "2020",
                    },
                    {
                        "result_id": "ranking:B",
                        "species": "Synthetic fish B",
                        "value": 2,
                        "period_kind": "year",
                        "period": "2023",
                    },
                ],
                "series": [
                    {
                        "result_id": "series:A",
                        "species": "Synthetic fish A",
                        "value": 1,
                        "period_kind": "year",
                        "period": "2020",
                    },
                    {
                        "result_id": "series:B",
                        "species": "Synthetic fish B",
                        "value": 2,
                        "period_kind": "season",
                        "period": "2023-MAM",
                    },
                ],
            }
            shared = {
                "version": "c26-shared-publication-fixture-v1",
                "workflow_kind": "fish_frequency",
                "recipe": record["scope_option"]["recipe_scope"],
                "protocol": assay,
                "protocol_id": protocol_id,
                "tables": tables,
                "source_snapshots": [
                    item.model_dump(mode="json") for item in original.metadata.datasets
                ],
                "qualification": "Hand-authored synthetic fixture, no real scientific review, approval or model quality",
            }
            shared_id = content_sha256(shared)
            bundle = {
                "manifest": {
                    "id": shared_id,
                    "schema_version": 2,
                    "limitations": [shared["qualification"]],
                },
                "recipe": deepcopy(shared["recipe"]),
                "tables": {
                    **deepcopy(tables),
                    "membership": [{"protocol_id": protocol_id}],
                },
                "inputs": {
                    "canonical": {
                        "edna_assay": [deepcopy(assay)],
                        "edna_detection": [],
                        "edna_sample": [],
                    }
                },
            }
            option = scope_option_from_bundle(bundle)
            if (
                option["protocol_ids"] != [protocol_id]
                or option["protocols"][protocol_id] != assay
            ):
                raise ValueError(
                    "The same exact retained assay must reach both implementations"
                )
            selected = deepcopy(record["scope"])
            selected["sources"]["edna_metabarcoding"]["analysis_id"] = shared_id
            record.update(
                id=shared_id,
                scope=selected,
                scope_option=option,
                limitations=[shared["qualification"]],
                provenance={
                    "references": [
                        "c26-shared-publication:sha256:" + shared_id,
                        "Original immutable registry: " + native_original,
                    ]
                },
            )
            record["tables"] = []
            frozen_tables = {}
            for name, rows in tables.items():
                object_id = "c26:shared-publication:" + name
                frozen_tables[object_id] = deepcopy(rows)
                record["tables"].append(
                    {
                        "name": name,
                        "object_id": object_id,
                        "columns": [
                            {"key": key, "title": {"en": key, "ja": key}}
                            for key in rows[0]
                        ],
                        "row_count": len(rows),
                        "availability": {"status": "available"},
                        "completeness": "complete",
                    }
                )
            registry = original.metadata.model_dump(mode="json")
            workflows = deepcopy(registry["workflows"])
            for workflow in workflows:
                workflow["analysis_ids"] = [shared_id]
            registry.update(
                analyses=[record], workflows=workflows, definitions=[], relationships=[]
            )
            native_v1 = seal_scientific_fixture(
                store,
                ScientificRegistry.model_validate(registry),
                frozen_tables,
                publication="c26-shared-source-" + shared_id,
            )
            frozen = load_registry(*store.read(native_v1))
            for table in frozen.metadata.analyses[0].tables:
                if frozen.tables[table.object_id] != tables[table.name]:
                    raise ValueError(
                        "Imported published table changed from the shared immutable fixture"
                    )
            registrations = {
                native_v1: register_scientific_snapshot(
                    store=store,
                    snapshot_id=native_v1,
                    registration_id="c26:shared-publication",
                )
            }
            catalogue = CatalogueService(
                resolver=FrozenCatalogueResolver(
                    store=store,
                    registrations=registrations,
                    policy_resolver=lambda user, snapshot: CataloguePolicy(
                        revision="c26-synthetic-shared",
                        dataset_eligible=lambda *args: True,
                        scientific_eligible=lambda *args: True,
                    ),
                )
            )
            investigations = InvestigationService(
                session_factory=retained.factory,
                site_id="v1:c26-shared-publication",
                catalogue_service=catalogue,
                snapshot_store=store,
                registrations=registrations,
            )
            harness = Harness(
                SimpleNamespace(
                    service=investigations,
                    user=retained.user,
                    scope=selected,
                    snapshots=(native_v1,),
                    dataset_ids=retained.dataset_ids,
                ),
                {"user": retained.user},
            )
            question = QUESTIONS["fish_frequency"][0]
            actions = [
                tool(
                    "analysis.get_published",
                    analysis_id=shared_id,
                    workflow_kind="fish_frequency",
                    protocol_id=protocol_id,
                    table=name,
                    limit=1,
                    offset=offset,
                )
                for name in ("ranking", "series")
                for offset in (0, 1)
            ]
            runtime = FakeRuntime(actions)
            request = harness.request(
                question,
                pins=[{"kind": "catalogue", "id": shared_id, "snapshot_id": native_v1}],
            )
            started = monotonic()
            v1 = harness.controller(runtime).execute(request)
            v1_elapsed = monotonic() - started
            started = monotonic()
            legacy = render_research(
                bundle,
                selected,
                question,
                ResearchIntent(kind="fish_frequency", protocol_id=protocol_id),
            )
            legacy_elapsed = monotonic() - started
            legacy_rows = [
                row for document in legacy.documents for row in document["result_rows"]
            ]
            v1_rows = [
                row
                for item in v1.observations
                if item.authority == "published"
                for row in json.loads(item.preview_json)
                if "result_id" in row
            ]
            legacy_citations = [
                "analysis_edna_" + shared_id + "_" + name
                for name in ("ranking", "series")
            ]
            actual_legacy_citations = list(
                dict.fromkeys(
                    item["citation_id"] for item in canonical_tokens(legacy.answer)
                )
            )
            valid_citations = [
                *legacy_citations,
                *(item.full_payload_ref for item in v1.observations),
            ]
            valid_citations = list(dict.fromkeys(valid_citations))
            expected_numbers = {
                "ranking:A": "1",
                "ranking:B": "2",
                "series:A": "1",
                "series:B": "2",
            }
            expected = {
                "inventory_ids": ["ranking:A", "ranking:B", "series:A", "series:B"],
                "numbers": expected_numbers,
                "supported_claims": [
                    "value:" + key + ":" + value
                    for key, value in expected_numbers.items()
                ],
                "required_tasks": ["read-ranking", "read-series"],
                "valid_citation_ids": valid_citations,
                "outcome": "completed",
            }
            manifest = {
                "question_id": "published-fish-frequency",
                "question": question,
                "permissions": sorted(retained.user.permissions),
                "scope": selected,
                "snapshot_id": shared_id,
                "source_revision": source_revision,
                "fixture_id": "c26-shared-publication",
                "fixture_sha256": shared_id,
                "provider": {
                    "mode": "fixture",
                    "provider": "synthetic",
                    "model": "c19-fake",
                    "configuration": {
                        "scripted_actions_sha256": content_sha256(actions)
                    },
                },
            }
            captures = {"legacy": asdict(legacy), "v1": v1.model_dump(mode="json")}
            observations = []
            for controller, rows, elapsed, calls, complete in [
                ("legacy", legacy_rows, legacy_elapsed, 0, legacy.reason is None),
                (
                    "v1",
                    v1_rows,
                    v1_elapsed,
                    v1.budget.tool_actions,
                    v1.outcome == "completed",
                ),
            ]:
                numbers = {row["result_id"]: str(row["value"]) for row in rows}
                unknown = {"basis": "unknown", "value": None}
                observations.append(
                    {
                        "version": "system-controller-observation-v1",
                        "controller": controller,
                        "input": deepcopy(manifest),
                        "evidence_kind": "actual-service-synthetic",
                        "inventory_state": "complete" if complete else "partial",
                        "inventory_ids": [row["result_id"] for row in rows],
                        "numbers": numbers,
                        "claims": [
                            "value:" + key + ":" + value
                            for key, value in numbers.items()
                        ],
                        "claims_complete": True,
                        "completed_tasks": ["read-ranking", "read-series"]
                        if complete
                        else [],
                        "cited_ids": actual_legacy_citations
                        if controller == "legacy"
                        else list(v1.evidence_refs),
                        "outcome": "completed" if complete else "failed",
                        "telemetry": {
                            "timing": {"basis": "measured", "value": elapsed},
                            "tool_calls": {"basis": "measured", "value": calls},
                            "input_tokens": deepcopy(unknown),
                            "output_tokens": deepcopy(unknown),
                            "cost": deepcopy(unknown),
                        },
                        "evidence": [
                            {
                                "id": "c26:publication:" + controller,
                                "sha256": content_sha256(captures[controller]),
                                "source_revision": source_revision,
                                "kind": "actual-service-synthetic",
                            }
                        ],
                    }
                )
            comparison = compare_controllers(expected, *observations)
            blocked_count = render_research(bundle, selected, "Count all datasets")
            return {
                "comparison": comparison.model_dump(mode="json"),
                "expected": expected,
                "observations": observations,
                "captures": captures,
                "shared_publication": shared,
                "native_bindings": {
                    "shared_source_snapshot_id": shared_id,
                    "legacy_analysis_id": bundle["manifest"]["id"],
                    "v1_registry_snapshot_id": native_v1,
                    "v1_controller_snapshot_id": v1.binding.snapshot_id,
                    "identical_native_wrapper_ids_claimed": False,
                },
                "legacy_count_probe": {
                    "status": "blocked",
                    "reason": blocked_count.reason,
                    "answer": blocked_count.answer,
                    "model_invoked": blocked_count.diagnostics["model_invoked"],
                    "native_snapshot_compatible": False,
                },
                "model_calls": {"legacy": 0, "v1_scripted_fixture": len(runtime.calls)},
                "qualification": shared["qualification"],
            }
    finally:
        engine.dispose()
