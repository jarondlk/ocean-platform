"""Independent membership/count expectations for C08's synthetic reference view."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from schema.context_catalogue import (
    CatalogueFilters,
    CatalogueNode,
    ListingRequest,
    Ordering,
    QueryResult,
    canonical_json,
)
from schema.context_catalogue_fixtures import (
    FixtureAccess,
    fixture_scope,
    make_catalogue,
)


def request(catalogue, access=FixtureAccess(), **updates):
    return ListingRequest(
        snapshot_id=catalogue.snapshot_id,
        scope=fixture_scope(),
        access_binding=access.binding,
        access_revision=access.revision,
        **updates,
    )


@pytest.fixture(scope="module")
def large():
    return make_catalogue(100_000)


def test_100000_dataset_inventory_is_exhaustively_reachable(large):
    access = FixtureAccess()
    query = request(large, filters=CatalogueFilters(kinds=["dataset"]), limit=500)
    identities = []
    for page in large.pages(query, access):
        assert page.total.value == 100_000
        assert page.returned_count == len(page.items)
        assert page.query_completion == "complete"
        identities.extend(node.id for node in page.items)
    expected = [f"synthetic:dataset:{index:06d}" for index in range(100_000)]
    assert identities == expected
    assert len(set(identities)) == 100_000
    assert large.records["synthetic:dataset:000025"].documentary_rank == 26
    assert large.open("synthetic:dataset:099999", access).id == expected[-1]


@pytest.mark.parametrize("limit", [1, 25, 100, 500])
def test_preview_size_never_changes_complete_scope_count(limit):
    c = make_catalogue(137)
    access = FixtureAccess()
    q = request(c, filters=CatalogueFilters(kinds=["dataset"]), limit=limit)
    page = c.list(q, access)
    assert page.total.value == c.dataset_count(q, access).value == 137
    assert page.returned_count == min(limit, 137)
    assert page.preview_truncated == (limit < 137)


def test_crosslinks_facets_and_cycles_do_not_duplicate_descendant_counts():
    c = make_catalogue(12)
    a = FixtureAccess()
    c.edges["synthetic:candidate-link"] += ("root:relationships",)
    q = request(c, parent_id="root:metadata")
    assert c.dataset_count(q, a).value == 1
    assert c.descendants("root:relationships", a) == {
        "synthetic:candidate-link",
        "synthetic:dataset:000000",
    }
    assert (
        len([n for n in c.list(q, a).items if n.id == "synthetic:dataset:000000"]) == 1
    )


def test_listing_parent_means_children_while_summary_means_descendants():
    c = make_catalogue(12)
    a = FixtureAccess()
    q = request(c, parent_id="root:data")
    assert {n.kind for n in c.list(q, a).items} == {"directory"}
    assert c.dataset_count(q, a).value == 12
    for family in ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding"):
        q = request(c, parent_id=f"synthetic:source:{family}")
        assert c.list(q, a).total.value == 3


def test_search_and_source_filters_reach_late_rank_without_relevance_cutoff(large):
    a = FixtureAccess()
    for index in (25, 501, 99_999):
        q = request(
            large, filters=CatalogueFilters(kinds=["dataset"], search=f"{index:06d}")
        )
        assert [n.id for n in large.list(q, a).items] == [
            f"synthetic:dataset:{index:06d}"
        ]
    q = request(
        large,
        filters=CatalogueFilters(source_families=["remote_sensing"], kinds=["dataset"]),
    )
    assert large.dataset_count(q, a).value == 25_000


def test_scientific_scope_uses_existing_source_filters():
    c = make_catalogue(40)
    a = FixtureAccess()
    for family in ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding"):
        q = request(c).model_copy(update={"scope": fixture_scope(family)})
        assert c.dataset_count(q, a).value == 10
        q = q.model_copy(
            update={"scope": fixture_scope(family, time_from="2025-01-01")}
        )
        assert c.dataset_count(q, a).value == 0
    q = request(c).model_copy(
        update={"scope": fixture_scope("edna_metabarcoding", is_control=True)}
    )
    assert c.dataset_count(q, a).value == 0


def test_authorization_precedes_search_count_and_open():
    c = make_catalogue()
    a = FixtureAccess()
    curator = FixtureAccess(subject_id="curator")
    assert c.dataset_count(request(c), a).value == 12
    assert c.dataset_count(request(c, curator), curator).value == 13
    for key in (
        "synthetic:hidden",
        "synthetic:revoked",
        "synthetic:private-experiment",
    ):
        assert c.open(key, a) is None
        q = request(c, filters=CatalogueFilters(search=key))
        page = c.list(q, a)
        assert page.items == [] and page.total.value == 0
    assert "synthetic:private-experiment" not in c.descendants("root:analyses", a)
    assert all(
        n.authority != "experimental"
        for n in c.list(request(c, parent_id="root:analyses"), a).items
    )


def test_revoking_parent_hides_all_descendant_metadata():
    c = make_catalogue()
    a = FixtureAccess(denied_ids=frozenset({"synthetic:source:ctd"}))
    q = request(c, a, filters=CatalogueFilters(kinds=["dataset"]))
    assert c.dataset_count(q, a).value == 9
    assert c.open("synthetic:dataset:000000", a) is None
    assert c.list(request(c, a, parent_id="synthetic:source:ctd"), a).total.value == 0


@pytest.mark.parametrize(
    "change",
    [
        {"revision": "permissions-2"},
        {"subject_id": "researcher-b"},
        {"denied_ids": frozenset({"synthetic:dataset:000001"})},
    ],
)
def test_permission_changes_invalidate_old_cursor_and_counts(change):
    c = make_catalogue()
    a = FixtureAccess()
    q = request(c, limit=2)
    cursor = c.list(q, a).next_cursor
    stale = q.model_copy(update={"cursor": cursor})
    current = replace(a, **change)
    with pytest.raises(ValueError, match="access context"):
        c.list(stale, current)
    fresh = request(c, current, limit=2)
    with pytest.raises(ValueError, match="cursor"):
        ListingRequest.model_validate(
            {**fresh.model_dump(mode="json"), "cursor": cursor}
        )


def test_cursor_continuation_uses_full_validated_context():
    c = make_catalogue(6)
    a = FixtureAccess()
    q = request(c, filters=CatalogueFilters(kinds=["dataset"]), limit=2)
    first = c.list(q, a)
    next_request = ListingRequest.model_validate(
        {**q.model_dump(mode="json"), "cursor": first.next_cursor}
    )
    second = c.list(next_request, a)
    assert [n.id for n in first.items + second.items] == [
        f"synthetic:dataset:{i:06d}" for i in range(4)
    ]
    with pytest.raises(ValueError, match="cursor"):
        ListingRequest.model_validate(
            {**q.model_dump(mode="json"), "limit": 3, "cursor": first.next_cursor}
        )


def test_id_survives_name_parent_and_snapshot_changes():
    c = make_catalogue(4)
    node = c.records["synthetic:dataset:000000"].node
    payload = node.model_dump(mode="json")
    payload.update(
        title={"en": "Renamed dataset", "ja": "名称変更"},
        parent_id="synthetic:different-directory",
        snapshot_id="synthetic-snapshot-2",
    )
    moved = CatalogueNode.model_validate(payload)
    assert moved.id == node.id
    assert moved.snapshot_id != node.snapshot_id and moved.parent_id != node.parent_id


def test_fixture_generation_is_deterministic_without_real_data_or_embeddings():
    left = make_catalogue(8)
    right = make_catalogue(8)
    assert left.edges == right.edges
    assert [
        canonical_json(r.node.model_dump(mode="json")) for r in left.records.values()
    ] == [
        canonical_json(r.node.model_dump(mode="json")) for r in right.records.values()
    ]
    a = FixtureAccess()
    q = request(left, filters=CatalogueFilters(kinds=["dataset"]))
    assert left.dataset_count(q, a).value == 8
    assert all(
        n.lifecycle.query_readiness == "ready"
        and n.lifecycle.embedding_readiness == "not_ready"
        for n in left.list(q, a).items
    )


def test_source_units_unknowns_and_candidate_relationships_are_preserved():
    c = make_catalogue(4)
    a = FixtureAccess()
    nodes = [c.open(f"synthetic:dataset:{index:06d}", a) for index in range(4)]
    assert nodes[0].descriptor.observation_entity == "cast"
    assert (
        nodes[1].descriptor.abundance_denominator == "classified reads in one library"
    )
    assert nodes[1].descriptor.omitted_taxa == "retained_elsewhere"
    assert nodes[2].descriptor.spatial_role == "regional_summary"
    assert nodes[3].descriptor.unit == "detected per eligible assay"
    assert c.open("synthetic:coverage", a).availability.status == "unknown"
    assert c.open("synthetic:unavailable", a).availability.status == "unavailable"
    assert "unverified" in c.open("synthetic:candidate-link", a).purpose.en


def test_shared_examples_use_real_validators_and_preserve_origin_qualifications():
    path = (
        Path(__file__).resolve().parents[1] / "schema/context_catalogue_examples.json"
    )
    cases = json.loads(path.read_text())
    assert cases["schema_version"] == "context-catalogue-v1"
    for value in cases["nodes"]:
        CatalogueNode.model_validate(value)
    from schema.context_catalogue import (
        CatalogueListing,
        OperationRequest,
        OperationReceipt,
    )

    models = {
        "CatalogueNode": CatalogueNode,
        "CatalogueListing": CatalogueListing,
        "OperationRequest": OperationRequest,
        "OperationReceipt": OperationReceipt,
        "QueryResult": QueryResult,
    }
    for model, key in (
        (CatalogueListing, "listings"),
        (OperationRequest, "operations"),
        (QueryResult, "results"),
    ):
        for value in cases[key]:
            model.model_validate(value)
    for case in cases["invalid"]:
        with pytest.raises(ValueError):
            models[case["model"]].model_validate(case["value"])
    origins = [
        n["provenance"]["origin"]
        for n in cases["nodes"]
        if n["provenance"].get("origin")
    ]
    assert origins and all(origin["live_dependency"] is False for origin in origins)


@pytest.mark.parametrize("count", [-1, True, 1.5, "4"])
def test_generator_rejects_ambiguous_cardinality(count):
    with pytest.raises(ValueError):
        make_catalogue(count)


def test_title_order_uses_id_tiebreak_and_filters_reconcile():
    c = make_catalogue(6)
    a = FixtureAccess()
    for i in range(6):
        key = f"synthetic:dataset:{i:06d}"
        record = c.records[key]
        node = record.node.model_copy(
            update={"title": record.node.title.model_copy(update={"en": "Same"})}
        )
        c.records[key] = replace(record, node=node)
    q = request(
        c,
        filters=CatalogueFilters(kinds=["dataset"]),
        ordering=[Ordering(field="title"), Ordering(field="id", direction="desc")],
    )
    assert [n.id for n in c.list(q, a).items] == [
        f"synthetic:dataset:{i:06d}" for i in range(5, -1, -1)
    ]


def test_crosslinks_do_not_disclose_currently_forbidden_targets():
    c = make_catalogue(4)
    key = "synthetic:candidate-link"
    original = c.records[key].node.model_dump(mode="json")
    for hidden in ("synthetic:dataset:000000", "synthetic:source:ctd"):
        a = FixtureAccess(denied_ids=frozenset({hidden}))
        assert c.open(key, a).related_ids == []
        page = c.list(request(c, a, parent_id="root:relationships"), a)
        assert page.items[0].related_ids == []
    assert c.records[key].node.model_dump(mode="json") == original
    assert c.open(key, FixtureAccess()).related_ids == ["synthetic:dataset:000000"]


@pytest.mark.parametrize("preview_limit", [1, 25, 100, 500])
def test_query_receipts_cover_full_scope_independent_of_preview(preview_limit):
    c = make_catalogue(137)
    a = FixtureAccess()
    q = request(c)
    result = c.dataset_result(q, a, preview_limit=preview_limit)
    assert result.receipt.total_rows.value == 137
    assert result.receipt.returned_count == len(result.rows) == min(preview_limit, 137)
    assert result.receipt.preview_truncated == (preview_limit < 137)
    assert len(result.receipt.inputs) == 137
    full = c.dataset_result(q, a, preview_limit=500)
    assert result.receipt.content_sha256 == full.receipt.content_sha256
    assert result.receipt.scope == q.scope and result.snapshot_id == q.snapshot_id
    assert result.receipt.authority == "descriptive"


def test_every_permitted_object_is_reachable_through_roots_and_children():
    c = make_catalogue(40)
    a = FixtureAccess()
    visited = set()
    pending = [
        f"root:{root}"
        for root in ("data", "analyses", "statistics", "metadata", "relationships")
    ]
    while pending:
        key = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        assert c.open(key, a).id == key
        for page in c.pages(request(c, parent_id=key, limit=3), a):
            pending.extend(node.id for node in page.items)
    assert visited == c.descendants(None, a)


def test_shared_sst_gaps_are_missing_days_without_zero_imputation():
    cases = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "schema/context_catalogue_examples.json"
        ).read_text()
    )
    result = QueryResult.model_validate(
        next(
            value
            for value in cases["results"]
            if value["receipt"]["operation_id"] == "catalogue.coverage"
        )
    )
    row = result.rows[0]
    assert row["observed_days"] == 4
    assert row["expected_days"] == 6
    assert row["missing_days"] == 2 == len(row["missing_dates"])
    assert row["observed_days"] + row["missing_days"] == row["expected_days"]
    assert result.receipt.source_completeness == "partial"
    assert result.receipt.query_completion == "complete"
    assert result.receipt.preview_truncated is False


@pytest.mark.parametrize(
    "script", ["export_catalogue_examples.py", "export_catalogue_types.py"]
)
def test_generated_consumers_match_python_owned_contract(script):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    process = subprocess.run(
        [sys.executable, str(root / "scripts" / script), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
