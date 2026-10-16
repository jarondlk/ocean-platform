"""Explicit synthetic C13 registries; no configured data or publication reads."""

from schema.catalogue_snapshot import SnapshotManifest, SourceCapture
from schema.context_catalogue import LocalizedText
from schema.scientific_catalogue import (
    ADAPTER_VERSION,
    INDEX_SOURCE_ID,
    TRANSPORT_QUALIFICATION,
    DatasetBinding,
    ScientificRegistry,
)


def scientific_scope():
    return {
        "version": 1,
        "sources": {
            family: {"enabled": True, "filters": {}}
            for family in ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding")
        },
    }


def scientific_fixture(count=1205, *, bindings=None):
    """Return logical records; callers supply actual sealed child bindings."""
    if type(count) is not int or not 0 <= count <= 2_000_000:
        raise ValueError("Bounded synthetic result count required")
    if bindings is None:
        bindings = [
            DatasetBinding(
                dataset_id="synthetic:ctd:casts",
                source_family="ctd",
                source_id="synthetic-ctd",
                snapshot_id="a" * 64,
            )
        ]
    bindings = [
        DatasetBinding.model_validate(
            b.model_dump(mode="json") if isinstance(b, DatasetBinding) else b
        )
        for b in bindings
    ]
    ids = [b.dataset_id for b in bindings]
    analysis_scope = scientific_scope()
    families = {binding.source_family for binding in bindings}
    for family, selection in analysis_scope["sources"].items():
        selection["enabled"] = family in families

    def label(text):
        return LocalizedText(en=text, ja=text).model_dump(mode="json")

    table_id = "synthetic:analysis:published:results"
    rows = [
        {
            "result_id": f"result:{i:07d}",
            "value": float(i),
            "support": "observed" if i % 2 == 0 else "qualified",
            "missing": None,
        }
        for i in range(count)
    ]
    registry = ScientificRegistry.model_validate(
        {
            "datasets": [b.model_dump(mode="json") for b in bindings],
            "analyses": [
                {
                    "id": "synthetic:analysis:published",
                    "title": label("Published synthetic finding"),
                    "purpose": label("Exact retained rows for synthetic acceptance"),
                    "input_dataset_ids": ids,
                    "method_id": "synthetic-descriptive-v1",
                    "method_version": "1",
                    "scope": analysis_scope,
                    "publication_status": "published",
                    "approval_basis": "explicit_user_accepted_operational_publication",
                    "independent_researcher_approval": False,
                    "provider_endorsement": False,
                    "availability": {"status": "available"},
                    "tables": [
                        {
                            "name": "results",
                            "object_id": table_id,
                            "columns": [
                                {"key": key, "title": label(key)} for key in rows[0]
                            ]
                            if rows
                            else [
                                {"key": key, "title": label(key)}
                                for key in ("result_id", "value", "support", "missing")
                            ],
                            "row_count": count,
                            "availability": {"status": "available"},
                            "completeness": "complete",
                        }
                    ],
                    "limitations": [
                        "Synthetic retained findings; operational publication is not independent scientific approval."
                    ],
                    "provenance": {
                        "references": [
                            "Synthetic C13 acceptance; no actual scientific data."
                        ]
                    },
                }
            ],
            "workflows": [
                {
                    "id": "synthetic:workflow:available",
                    "title": label("Available descriptive workflow"),
                    "purpose": label(
                        "Describe an operation without executing an experiment"
                    ),
                    "workflow_kind": "descriptive_inventory",
                    "required_sources": list(
                        dict.fromkeys(b.source_family for b in bindings)
                    ),
                    "availability": {"status": "available"},
                    "input_dataset_ids": ids,
                    "analysis_ids": ["synthetic:analysis:published"],
                    "limitations": [
                        "This is a workflow description; it cannot run or approve an experiment."
                    ],
                    "provenance": {"references": ["Synthetic C13 acceptance."]},
                }
            ],
        }
    )
    return registry, {table_id: rows}


def seal_scientific_fixture(
    store,
    metadata,
    tables,
    *,
    generations=None,
    publication="publication-1",
    classification="classification-1",
    relationship="relationship-1",
    operation=ADAPTER_VERSION,
):
    """Seal only supplied logical records and never publish a latest pointer."""
    from ingestion.scientific_catalogue_inputs import registry_exports

    generations = dict(generations or {})
    publication = generations.get("publication", publication)
    generation = generations.get("source", publication)
    captured = registry_exports(metadata, tables, generation=generation)
    manifest = SnapshotManifest(
        scope=scientific_scope(),
        source_captures=[
            SourceCapture(
                source_id=INDEX_SOURCE_ID,
                source_family="ctd",
                source_generation=generation,
                publication_generation=publication,
                classification_generation=generations.get(
                    "classification", classification
                ),
                relationship_generation=generations.get("relationship", relationship),
                operation_generation=generations.get("operation", operation),
                capture_method="synthetic-c13-frozen-scientific-index-v1",
                qualifiers=[TRANSPORT_QUALIFICATION],
            )
        ],
        objects=list(captured.objects),
        operation_versions={
            o.operation_id: o.operation_version for o in captured.objects
        },
    )
    return store.seal(manifest, dict(captured.contents))
