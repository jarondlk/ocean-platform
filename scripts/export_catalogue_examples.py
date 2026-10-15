"""Export deterministic shared C08 valid/invalid wire cases (no real data)."""

from __future__ import annotations

import argparse
import hashlib
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schema.context_catalogue import (  # noqa: E402
    SCHEMA_VERSION,
    canonical_json,
    CatalogueNode,
    CatalogueListing,
    ListingRequest,
    OperationRequest,
    OperationReceipt,
    QueryResult,
)
from schema.context_catalogue_fixtures import (
    FixtureAccess,
    fixture_scope,
    make_catalogue,
)


def examples():
    c = make_catalogue(8)
    a = FixtureAccess()
    q = ListingRequest(
        snapshot_id=c.snapshot_id,
        scope=fixture_scope(),
        access_revision=a.revision,
        access_binding=a.binding,
        limit=3,
        filters={"kinds": ["dataset"]},
    )
    pages = list(c.pages(q, a))
    nodes = [
        c.open(key, a).model_dump(mode="json")
        for key in sorted(c.records)
        if c.permitted(key, a)
    ]
    imported = deepcopy(next(node for node in nodes if node["kind"] == "dataset"))
    imported["provenance"]["origin"] = {
        "origin_system": "synthetic-legacy",
        "origin_object_id": "original-object-1",
        "source_snapshot_id": "origin-snapshot-1",
        "source_generation": "origin-generation-1",
        "schema_version": "origin-schema-v1",
        "operation_version": "count-v1",
        "content_sha256": "a" * 64,
        "scientific_qualification": "Published; independent scientific review not established",
        "access_conditions": "Synthetic transfer only; current permission required",
        "transfer_authorization_ref": "synthetic-authorization-1",
        "live_dependency": False,
    }
    nodes.append(imported)
    unknown_control = deepcopy(
        next(
            node
            for node in nodes
            if node["source_family"] == "edna_metabarcoding"
            and node["kind"] == "dataset"
        )
    )
    unknown_control["descriptor"].update(sample_kind="unknown", is_control=None)
    nodes.append(unknown_control)
    unknown = pages[0].model_dump(mode="json")
    unknown.update(
        total={
            "state": "unknown",
            "entity": "canonical_objects",
            "denominator": "all matching permitted canonical objects",
            "basis": "complete_scope",
            "value": None,
            "reason": "Population count not yet established",
        },
        source_completeness="partial",
    )
    unavailable = deepcopy(unknown)
    unavailable.update(
        items=[],
        returned_count=0,
        next_cursor=None,
        preview_truncated=False,
        source_completeness="unavailable",
        query_completion="not_started",
        availability={"status": "unavailable", "reason": "Source unavailable"},
    )
    zero = c.list(
        q.model_copy(
            update={
                "filters": q.filters.model_copy(update={"search": "no-such-fixture"})
            }
        ),
        a,
    ).model_dump(mode="json")
    operation = OperationRequest(
        snapshot_id=c.snapshot_id,
        scope=fixture_scope(),
        operation_id="catalogue.dataset_inventory",
        operation_version="v1",
        input_ids=["synthetic:dataset:000000"],
        access_revision=a.revision,
        access_binding=a.binding,
    ).model_dump(mode="json")
    result = c.dataset_result(q, a, preview_limit=3).model_dump(mode="json")
    gap = deepcopy(result)
    gap_scope = fixture_scope("remote_sensing").model_dump(mode="json")
    gap_rows = [
        {
            "expected_days": 6,
            "observed_days": 4,
            "missing_days": 2,
            "missing_dates": ["2024-01-03", "2024-01-05"],
        }
    ]
    gap.update(
        scope=gap_scope,
        columns=[{"key": key, "title": {"en": key, "ja": key}} for key in gap_rows[0]],
        rows=gap_rows,
    )
    gap["receipt"].update(
        scope=gap_scope,
        receipt_id="synthetic:coverage-receipt",
        operation_id="catalogue.coverage",
        inputs=[
            {
                "object_id": "synthetic:dataset:000002",
                "content_sha256": c.records[
                    "synthetic:dataset:000002"
                ].node.provenance.content_sha256,
            }
        ],
        parameters={"product_id": "synthetic-mur", "entity": "regional_days"},
        total_rows={
            "state": "known",
            "entity": "rows",
            "denominator": "one synthetic regional coverage summary",
            "basis": "complete_scope",
            "value": 1,
            "reason": None,
        },
        returned_count=1,
        preview_truncated=False,
        source_completeness="partial",
        content_sha256=hashlib.sha256(canonical_json(gap_rows).encode()).hexdigest(),
    )
    cases = {
        "schema_version": SCHEMA_VERSION,
        "nodes": nodes,
        "listings": [
            *(p.model_dump(mode="json") for p in pages),
            unknown,
            unavailable,
            zero,
        ],
        "operations": [operation],
        "results": [result, gap],
        "invalid": [],
    }
    dataset = next(
        node
        for node in nodes
        if node["kind"] == "dataset" and node["source_family"] == "ctd"
    )
    edna = unknown_control

    def invalid(model, base, reason, edit):
        value = deepcopy(base)
        edit(value)
        cases["invalid"].append({"model": model, "reason": reason, "value": value})

    def setkey(path, value):
        def edit(target):
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value

        return edit

    invalid(
        "OperationRequest",
        operation,
        "Exact JSON integers cannot silently round in browsers",
        setkey(["parameters"], {"large_exact_integer": 9007199254740993}),
    )
    invalid(
        "QueryResult",
        result,
        "Result integers cannot silently round in browsers",
        setkey(["rows", 0, "dataset_id"], 9007199254740993),
    )
    for boundary_date in ("9999-12-31T23:59:59-23:59", "0001-01-01T00:00:00+23:59"):
        invalid(
            "CatalogueNode",
            dataset,
            "UTC calendar overflow: " + boundary_date,
            setkey(["scope", "sources", "ctd", "filters", "time_from"], boundary_date),
        )
    invalid(
        "CatalogueNode",
        dataset,
        "Exclusive end UTC calendar overflow",
        setkey(["scope", "sources", "ctd", "filters", "time_to"], "9999-12-31"),
    )
    for path, value, reason in [
        (["schema_version"], "context-catalogue-v2", "Unsupported version"),
        (["id"], "/Data/CTD/name", "Paths cannot be canonical identity"),
        (["title", "en"], "", "Missing English title"),
        (["parent_id"], dataset["id"], "Self-parent"),
        (["sections"], ["overview"], "Missing dataset sections"),
        (["source_family"], "sst", "Aliases adapted before wire validation"),
        (["descriptor", "family"], "metagenome", "Source descriptor mismatch"),
        (["authority"], "published", "Published flag without publication lifecycle"),
        (
            ["scope", "sources", "ctd", "filters", "time_from"],
            "2024-02-30",
            "Invalid calendar date",
        ),
        (
            ["scope", "sources", "ctd", "filters", "time_from"],
            42,
            "Non-text scientific filter",
        ),
        (
            ["scope", "sources", "ctd", "filters"],
            [],
            "Malformed scientific filter object",
        ),
        (["scope", "sources", "ctd", "enabled"], "true", "String boolean scope flag"),
    ]:
        if path == ["authority"]:
            invalid(
                "CatalogueNode",
                {
                    **dataset,
                    "lifecycle": {**dataset["lifecycle"], "publication": "unpublished"},
                },
                reason,
                setkey(path, value),
            )
        else:
            invalid("CatalogueNode", dataset, reason, setkey(path, value))
    invalid(
        "CatalogueNode",
        edna,
        "Unknown control classification must not be invented",
        setkey(["descriptor", "sample_kind"], "environmental"),
    )
    invalid(
        "CatalogueNode",
        edna,
        "Control conflicts with known environmental sample",
        lambda v: v["descriptor"].update(sample_kind="environmental", is_control=True),
    )
    invalid(
        "CatalogueNode",
        imported,
        "Origin provenance cannot create live dependency",
        setkey(["provenance", "origin", "live_dependency"], True),
    )
    for path, value, reason in [
        (["returned_count"], 2, "Page returned count mismatch"),
        (["returned_count"], True, "Boolean count"),
        (["total", "value"], -1, "Negative population"),
        (["total", "value"], 1.5, "Fractional population"),
        (["total", "value"], 2**53, "Unsafe cross-language population"),
        (["total", "value"], 0, "Page exceeds whole-scope total"),
        (["total", "state"], "unknown", "Unknown total cannot contain numeric value"),
        (["next_cursor"], None, "Complete listing cannot silently drop later pages"),
        (
            ["request", "access_revision"],
            "permissions-2",
            "Cursor access context mismatch",
        ),
        (["request", "snapshot_id"], "snapshot-2", "Snapshot context mismatch"),
        (["items", 0, "snapshot_id"], "snapshot-2", "Mixed-snapshot item"),
        (["request", "limit"], 501, "Page limit exceeds contract maximum"),
    ]:
        invalid(
            "CatalogueListing",
            pages[1].model_dump(mode="json"),
            reason,
            setkey(path, value),
        )
    invalid(
        "CatalogueListing",
        pages[0].model_dump(mode="json"),
        "Duplicate canonical item",
        lambda v: v["items"].__setitem__(1, deepcopy(v["items"][0])),
    )
    invalid(
        "CatalogueListing",
        unavailable,
        "Unavailable is not known zero",
        setkey(
            ["total"],
            {
                "state": "known",
                "entity": "canonical_objects",
                "denominator": "all permitted canonical objects",
                "value": 0,
            },
        ),
    )
    invalid(
        "OperationRequest",
        operation,
        "Operation inputs must be distinct",
        setkey(["input_ids"], ["same", "same"]),
    )
    invalid(
        "OperationRequest",
        operation,
        "Unknown executable fields forbidden",
        lambda v: v.update(sql="SELECT secret FROM legacy"),
    )
    invalid(
        "QueryResult",
        result,
        "Result/receipt snapshot mismatch",
        setkey(["receipt", "snapshot_id"], "other-snapshot"),
    )
    invalid(
        "QueryResult",
        result,
        "Receipt preview length mismatch",
        setkey(["receipt", "returned_count"], 1),
    )
    invalid(
        "QueryResult",
        result,
        "Preview truncation cannot hide remaining complete result",
        setkey(["receipt", "preview_truncated"], False),
    )
    invalid(
        "QueryResult",
        result,
        "Table column mismatch",
        lambda v: v["rows"][0].update(unregistered="value"),
    )
    models = {
        "CatalogueNode": CatalogueNode,
        "CatalogueListing": CatalogueListing,
        "OperationRequest": OperationRequest,
        "OperationReceipt": OperationReceipt,
        "QueryResult": QueryResult,
    }
    for model, key in (
        (CatalogueNode, "nodes"),
        (CatalogueListing, "listings"),
        (OperationRequest, "operations"),
        (QueryResult, "results"),
    ):
        cases[key] = [
            model.model_validate(value).model_dump(mode="json") for value in cases[key]
        ]
    for case in cases["invalid"]:
        try:
            models[case["model"]].model_validate(case["value"])
        except ValueError:
            continue
        raise AssertionError("Invalid shared case accepted: " + case["reason"])
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "schema/context_catalogue_examples.json"
    text = json.dumps(examples(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.check:
        if not path.exists() or path.read_text() != text:
            raise SystemExit(
                "C08 shared examples differ; run scripts/export_catalogue_examples.py"
            )
        print("C08 shared examples are current")
    else:
        path.write_text(text)
        print("Wrote " + str(path.relative_to(ROOT)))


if __name__ == "__main__":
    main()
