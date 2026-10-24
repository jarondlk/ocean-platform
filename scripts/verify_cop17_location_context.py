#!/usr/bin/env python3
"""Demo-only independent SQL and immutable-history acceptance, scientific reads only."""

import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.verify_cop17_locations import guard_demo, scope


def main():
    guard_demo()
    from sqlalchemy import text
    from db.connection import get_engine
    from ingestion import edna_aggregate as a
    from ingestion import location_context as c
    from orchestration.location_context import plan_context, render
    from scripts.verify_cop17_geography import main as previous_geography
    from scripts.verify_cop17_locations import main as previous_locations

    previous_locations()
    previous_geography()
    engine = get_engine()
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        assert conn.exec_driver_sql("SHOW transaction_read_only").scalar() == "on"
        rows = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT s.lat,s.lon,min(s.sample_id) AS sample_id FROM edna_sample s WHERE s.active IS TRUE AND s.provider='anemone' AND s.is_control IS NOT TRUE AND s.lat BETWEEN -90 AND 90 AND s.lon BETWEEN -180 AND 180 GROUP BY s.lat,s.lon ORDER BY s.lat,s.lon"
                )
            ).mappings()
        ]
    assert len(rows) == 216

    def build(limit=10, areas=False, **filters):
        return a.build_aggregate(
            {"provider": "anemone", **filters},
            metric=c.METRIC,
            context_options={"example_limit": limit, "area_groups": areas},
        )

    original_location = a.build_aggregate(
        {"provider": "anemone"}, metric="recorded_locations"
    )
    assert (
        original_location["aggregate_id"]
        == "6a1a0268beca633c46a3878ec9ce36ad1f25e4c1338c51a1bab514a597b2bea4"
    )
    base = build()
    context = base["payload"]["summary"]["location_context"]
    assert [
        {k: r[k] for k in ("lat", "lon", "sample_id")} for r in context["positions"]
    ] == rows
    assert (
        context["groups"]["mapped_positions"] == 96
        and context["groups"]["unassigned_positions"] == 120
    )
    assert len(context["groups"]["generalized_area_groups"]) == 87
    assert (
        context["base_geography_aggregate_id"]
        == "18da70e322a69ed4d45f35cc930212b4221cfc8e167a8310458bf130bea89450"
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        for row in context["positions"]:
            source = (
                conn.execute(
                    text(
                        "SELECT original_sample_label,collection_date_utc,source_snapshot_id,source_file_id,source_row_hash FROM edna_sample WHERE sample_id=:id"
                    ),
                    {"id": row["sample_id"]},
                )
                .mappings()
                .one()
            )
            assert all(
                (str(v) if v is not None else None) == row[k] for k, v in source.items()
            )
    cases = []
    for q, limit, areas in [
        (
            "How many sampling locations are recorded in ANEMONE DB? Please show me 10 example locations.",
            10,
            False,
        ),
        (
            "ANEMONE DBの採水地点はいくつありますか？10か所の例を示してください。",
            10,
            False,
        ),
        ("How many named areas are available in ANEMONE DB?", 0, True),
        ("名前のある採水エリアはいくつありますか？", 0, True),
        ("How many locations? Show me 5 example locations.", 5, False),
        ("How many locations? Show me 20 example locations.", 20, False),
    ]:
        plan = plan_context({"query": q, "evidence_scope": scope()})
        assert plan is not None and plan.clarification is None
        assert plan.context_options == {"example_limit": limit, "area_groups": areas}
        bundle = build(limit=limit, areas=areas)
        assert a.load_aggregate(bundle["aggregate_id"]) == bundle
        answer = render(bundle, q)
        assert "216" in answer and "[aggregate_edna_" in answer
        if areas:
            assert "87" in answer and "120" in answer and "3,184.8" in answer
        else:
            assert (
                len(
                    bundle["payload"]["summary"]["location_context"]["positions"][
                        :limit
                    ]
                )
                == limit
            )
        cases.append(
            {
                "query": q,
                "aggregate_id": bundle["aggregate_id"],
                "example_limit": limit,
                "area_groups": areas,
                "passed": True,
            }
        )
    with (
        patch.object(
            c, "read_positions", side_effect=AssertionError("Warm context scanned rows")
        ),
        patch.object(
            a, "_inputs", side_effect=AssertionError("Warm context scanned inputs")
        ),
    ):
        assert build() == base
    narrow = build(sample_id=rows[0]["sample_id"])
    assert len(narrow["payload"]["summary"]["location_context"]["positions"]) == 1
    empty = build(sample_id="a" * 64)
    assert empty["payload"]["summary"]["location_context"]["positions"] == []
    assert "0 example locations" in render(empty, "Show me10 locations")
    for q in [
        "How many locations in 2020? Show me 10 example locations.",
        "How many locations in Otsuchi Bay? Show me 10 example locations.",
        "How many locations with SST? Show me 10 example locations.",
    ]:
        assert plan_context({"query": q, "evidence_scope": scope()}).clarification
    assert (
        plan_context(
            {
                "query": "Find one ANEMONE eDNA sample from Otsuchi Bay in 2020 and list five fish taxa detected in it. Distinguish species-level and genus-level identifications, and cite the source."
            }
        )
        is None
    )
    for algorithm in (
        a.ALGORITHM,
        a.LOCATION_ALGORITHM,
        a.GEOGRAPHY_ALGORITHM,
        c.ALGORITHM,
    ):
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            identity = conn.execute(
                text(
                    "SELECT aggregate_id FROM edna_aggregate_evidence WHERE algorithm_version=:a ORDER BY aggregate_id LIMIT 1"
                ),
                {"a": algorithm},
            ).scalar_one()
        assert (
            a.load_aggregate(identity) is not None
            and a.aggregate_trace(identity)["found"]
        )
    assert (
        a.build_aggregate({"provider": "anemone"}, metric="recorded_locations")
        == original_location
    )
    print(
        json.dumps(
            {
                "probe": "cop17-location-context",
                "passed": True,
                "cases": cases,
                "reference_sql": {
                    "locations": {"distinct_coordinate_pairs": len(rows)}
                },
                "mapped_positions": 96,
                "unassigned_positions": 120,
                "reference_name_groups": 87,
                "original_count_citation_unchanged": True,
                "v1_v2_v3_v4_history_loads": True,
                "all_representative_rows_match_source": True,
                "scientific_rows_modified": False,
                "users_created_or_reactivated": False,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
