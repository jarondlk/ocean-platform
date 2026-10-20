"""Explicit synthetic C21 store over actual C17/C20 retained local services."""
from orchestration.research_evidence import ResearchEvidenceService
from tests.research_run_support import make_run_fixture


def make_evidence_fixture(engine, directory):
    fixture = make_run_fixture(engine, directory)
    evidence = ResearchEvidenceService(session_factory=fixture.retained.factory,
        site_id=fixture.service.site_id, investigations=fixture.retained.service,
        runs=fixture.service, enabled=lambda: True)
    fixture.retained.service.artifact_resolver = evidence.resolve_attachment
    fixture.retained.service.evidence_protection = evidence
    return fixture, evidence


def make_union_fixture(original):
    """A new operational test-only analysis declares two real sealed inputs.

    No scientific result, independent review or approval is invented here: its
    table is empty and the sole requested fact is the declared input inventory.
    """
    from dataclasses import replace
    import hashlib
    from ingestion.scientific_catalogue_inputs import load_registry
    from orchestration.catalogue_registration import register_scientific_snapshot
    from orchestration.catalogue_service import CataloguePolicy, CatalogueService, FrozenCatalogueResolver
    from orchestration.investigations import InvestigationService
    from orchestration.research_controller import ResearchController
    from orchestration.research_dispatch import FakeResearchQueue
    from orchestration.research_runs import ResearchRunService
    from schema.scientific_catalogue import ScientificRegistry
    from schema.scientific_catalogue_fixtures import seal_scientific_fixture
    from tests.research_run_support import RunClock, RunFixture

    source = original.retained
    registry = load_registry(*source.store.read(source.snapshots[0])).metadata.model_dump(mode="json")
    selected = {"version": 1, "sources": {family: {"enabled": family in {"ctd", "metagenome"}, "filters": {}}
        for family in ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding")}}
    registry.update(analyses=[{"id": "c21:synthetic:two-inputs", "title": {"en": "Synthetic input grouping", "ja": "合成入力のまとまり"},
        "purpose": {"en": "Inventory reconstruction only", "ja": "インベントリ再構築専用"},
        "input_dataset_ids": [source.dataset_ids[family] for family in ("ctd", "metagenome")],
        "method_id": "c21:synthetic:inventory", "method_version": "test-only", "scope": selected,
        "publication_status": "published", "approval_basis": "Synthetic operational label; no scientific approval",
        "independent_researcher_approval": False, "provider_endorsement": False,
        "availability": {"status": "available"}, "limitations": ["Empty synthetic table; input inventory test only"],
        "provenance": {"references": ["C21 synthetic local test, not a scientific publication"]},
        "tables": [{"name": "empty", "object_id": "c21:synthetic:empty", "columns": [{"key": "value", "title": {"en": "Value", "ja": "値"}}],
            "row_count": 0, "availability": {"status": "available"}, "completeness": "complete"}]}],
        workflows=[], relationships=[], definitions=[])
    ctd = next(item for item in registry["datasets"] if item["dataset_id"] == source.dataset_ids["ctd"])
    documentary_text = "Count datasets using retained synthetic input metadata. 採水手順の合成文書。"
    registry["definitions"] = [{"id": "c21:synthetic:documentation", "title": {"en": "Synthetic source documentation", "ja": "合成の原資料"},
        "purpose": {"en": "Exact UTF-8 retention test", "ja": "UTF-8保持の検証"}, "category": "source_documentation",
        "input_dataset_ids": [ctd["dataset_id"]], "provenance": {"references": ["Explicit synthetic C21 authoring; no scientific approval"]},
        "values": {"schema_version": "c21-documentary-source-v1", "documents": [{
            "id": "c21:synthetic:document", "title": {"en": "Synthetic inventory documentation", "ja": "合成インベントリ文書"},
            "language": "en", "text": documentary_text, "content_sha256": hashlib.sha256(documentary_text.encode()).hexdigest(),
            "input_bindings": [{"dataset_id": ctd["dataset_id"], "child_snapshot_id": ctd["snapshot_id"], "source_id": ctd["source_id"], "source_family": "ctd"}],
            "applicability_scope": {"version": 1, "sources": {family: {"enabled": family == "ctd", "filters": {}}
                for family in ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding")}},
            "qualifications": ["Synthetic documentary quotation; no scientific result or independent review"]}]}}]
    sid = seal_scientific_fixture(source.store, ScientificRegistry.model_validate(registry), {"c21:synthetic:empty": []}, publication="c21-synthetic-two-input-inventory")
    registration = register_scientific_snapshot(store=source.store, snapshot_id=sid, registration_id="c21:synthetic:union")
    registrations = {sid: registration}
    catalogue = CatalogueService(resolver=FrozenCatalogueResolver(store=source.store, registrations=registrations,
        policy_resolver=lambda user, snapshot: CataloguePolicy(revision="c21:synthetic:union", dataset_eligible=lambda *_: True, scientific_eligible=lambda *_: True)))
    investigations = InvestigationService(session_factory=source.factory, site_id="v1:c21-synthetic-union",
        catalogue_service=catalogue, snapshot_store=source.store, registrations=registrations)
    retained = replace(source, service=investigations, scope=source.scope, snapshots=(sid,), registrations=registrations)
    clock, queue, state = RunClock(), FakeResearchQueue(), {"runtime": None, "factory_calls": 0}

    def controller_factory(identity_provider):
        state["factory_calls"] += 1
        return ResearchController(investigations=investigations, catalogue=catalogue,
            identity_provider=identity_provider, runtime=None, model=None, runtime_identity={"fixture": "C21-union"})

    runs = ResearchRunService(session_factory=source.factory, site_id=investigations.site_id, investigations=investigations,
        controller_factory=controller_factory, queue=queue, db_clock=clock, enabled=lambda: True, dispatch_enabled=lambda: True)
    fixture = RunFixture(retained, runs, queue, clock, state)
    evidence = ResearchEvidenceService(session_factory=source.factory, site_id=investigations.site_id,
        investigations=investigations, runs=runs, enabled=lambda: True)
    investigations.artifact_resolver, investigations.evidence_protection = evidence.resolve_attachment, evidence
    return fixture, evidence
