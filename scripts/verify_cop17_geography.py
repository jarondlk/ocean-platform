#!/usr/bin/env python3
"""Verify full-cohort geography inside the fixed isolated COP17 runtime.

Reference queries are independent SELECT-only SQL in read-only transactions.
The only persistent writes are immutable aggregate receipts in app history;
this probe does not create users or modify scientific rows or cloud resources.
It does not replace signed-in browser or HTTP authentication acceptance.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.verify_cop17_locations import guard_demo, scope  # noqa: E402


QUESTIONS = (
    "how many named area are available",
    "are all sampling data from around the same area",
    "名前付きの採水エリアはいくつありますか？",
    "採水データはすべて同じ地域のものですか？",
)
EXPECTED_EXTENT = {
    "lat_min": 17.45833333,
    "lat_max": 45.54166667,
    "lon_min": 123.8125,
    "lon_max": 148.6875,
}
EXPECTED_POSITIONS = [
    {"lat": 17.45833333, "lon": 148.6875},
    {"lat": 45.54166667, "lon": 141.9375},
]
EXPECTED_COUNTS = {
    "source_occurrences": 3155,
    "valid_coordinate_occurrences": 3154,
    "distinct_coordinate_pairs": 216,
    "missing_coordinate_occurrences": 1,
    "invalid_coordinate_occurrences": 0,
    "controls": 0,
    "unknown_control_status": 3155,
}
NAMED_DEFINITION = (
    "No reviewed area-membership relation is provided by this canonical-catalogue "
    "aggregate; provider/project/sample labels are not bay boundaries."
)


def _separation(positions):
    if not positions:
        return None
    south, north = positions
    latitude1, longitude1 = math.radians(south["lat"]), math.radians(south["lon"])
    latitude2, longitude2 = math.radians(north["lat"]), math.radians(north["lon"])
    haversine = (
        math.sin((latitude2 - latitude1) / 2) ** 2
        + math.cos(latitude1)
        * math.cos(latitude2)
        * math.sin((longitude2 - longitude1) / 2) ** 2
    )
    haversine = max(0.0, min(1.0, haversine))
    # Independent atan2 formulation; the application uses asin.
    return round(
        6371.0088 * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine)),
        3,
    )


def main() -> None:
    guard_demo()
    from sqlalchemy import text

    from db.connection import get_engine
    from ingestion import edna_aggregate as aggregates
    from orchestration.catalogue_geography import plan_catalogue_geography
    from orchestration.edna_aggregation import render_answer

    engine = get_engine()
    valid = "s.lat BETWEEN -90 AND 90 AND s.lon BETWEEN -180 AND 180"

    def reference(*, sample_id=None, project=None):
        # Do not call application predicates or geography/count implementations.
        clauses = ["s.active IS TRUE", "s.provider='anemone'", "s.is_control IS NOT TRUE"]
        params = {}
        if sample_id is not None:
            clauses.append("s.sample_id=:sample_id")
            params["sample_id"] = sample_id
        if project is not None:
            clauses.append("s.provider_project_id=:project")
            params["project"] = project
        where = " AND ".join(clauses)
        with engine.connect() as connection:
            connection.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.exec_driver_sql("SET LOCAL statement_timeout='20s'")
            assert connection.exec_driver_sql("SHOW transaction_read_only").scalar() == "on"
            counts = connection.execute(text(
                "SELECT count(*) AS source_occurrences, "
                f"count(*) FILTER (WHERE {valid}) AS valid_coordinate_occurrences, "
                f"count(DISTINCT (s.lat,s.lon)) FILTER (WHERE {valid}) AS distinct_coordinate_pairs, "
                "count(*) FILTER (WHERE s.lat IS NULL OR s.lon IS NULL) AS missing_coordinate_occurrences, "
                f"count(*) FILTER (WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL AND NOT ({valid})) AS invalid_coordinate_occurrences, "
                "count(*) FILTER (WHERE s.is_control IS TRUE) AS controls, "
                "count(*) FILTER (WHERE s.is_control IS NULL) AS unknown_control_status "
                "FROM edna_sample s WHERE " + where
            ), params).mappings().one()
            extent = connection.execute(text(
                f"SELECT min(s.lat) FILTER (WHERE {valid}) AS lat_min, "
                f"max(s.lat) FILTER (WHERE {valid}) AS lat_max, "
                f"min(s.lon) FILTER (WHERE {valid}) AS lon_min, "
                f"max(s.lon) FILTER (WHERE {valid}) AS lon_max "
                "FROM edna_sample s WHERE " + where
            ), params).mappings().one()
            positions = []
            for ordering in ("s.lat ASC,s.lon ASC", "s.lat DESC,s.lon ASC"):
                row = connection.execute(text(
                    "SELECT s.lat,s.lon FROM edna_sample s WHERE " + where
                    + f" AND {valid} ORDER BY {ordering} LIMIT 1"
                ), params).mappings().first()
                if row is not None:
                    positions.append({"lat": float(row["lat"]), "lon": float(row["lon"])})
        return {
            "locations": {key: int(value) for key, value in counts.items()},
            "coordinate_extent": {key: float(value) if value is not None else None for key, value in extent.items()},
            "latitude_extreme_positions": positions,
            "latitude_extreme_separation_km": _separation(positions),
        }

    def compare(bundle, expected):
        assert bundle["payload"]["algorithm_version"] == aggregates.GEOGRAPHY_ALGORITHM
        assert bundle["payload"]["metric"] == "catalogue_geography"
        geography = bundle["payload"]["summary"]["geography"]
        assert all(geography["locations"][key] == value for key, value in expected["locations"].items())
        for key in ("coordinate_extent", "latitude_extreme_positions", "latitude_extreme_separation_km"):
            assert geography[key] == expected[key], key
        assert geography["named_area_count"] is None
        assert geography["named_area_status"] == "not_established_by_canonical_catalogue"
        assert geography["named_area_definition"] == NAMED_DEFINITION
        assert aggregates.load_aggregate(bundle["aggregate_id"]) == bundle
        return geography

    report = {"probe": "cop17-catalogue-geography", "cases": []}
    expected = reference()
    assert expected["locations"] == EXPECTED_COUNTS, "Demo scientific snapshot count differs"
    assert expected["coordinate_extent"] == EXPECTED_EXTENT, "Demo scientific snapshot extent differs"
    assert expected["latitude_extreme_positions"] == EXPECTED_POSITIONS
    assert expected["latitude_extreme_separation_km"] == 3184.838
    plans = []
    for index, question in enumerate(QUESTIONS):
        plan = plan_catalogue_geography({"query": question, "evidence_scope": scope(sst=index < 2)})
        assert plan is not None and not plan.clarification and plan.metric == "catalogue_geography"
        plans.append(plan)
    assert all(plan.filters == plans[0].filters for plan in plans)
    bundle = aggregates.build_aggregate(plans[0].filters, metric="catalogue_geography")
    geography = compare(bundle, expected)
    assert geography["locations"]["coordinate_precision"] == {"provider_grid_unconfirmed":3154}
    assert geography["locations"]["sample_kinds"] == {"unknown":3155}
    assert geography["locations"]["environmental_classified"] == 0
    for index, question in enumerate(QUESTIONS):
        answer = render_answer(bundle, question)
        assert "[aggregate_edna_" + bundle["aggregate_id"] + "]" in answer
        assert "216" in answer and "3,184.8" in answer
        assert all(f"{value:.6f}" in answer for value in EXPECTED_EXTENT.values())
        assert not re.search(r"\b(?:0|zero)\s+named\s+(?:areas|bays)\b", answer, re.I)
        if index < 2:
            assert "not established" in answer and "does not mean there are zero geographic areas" in answer
        else:
            assert "確定していません" in answer and "ゼロという意味ではありません" in answer
        report["cases"].append({"name":f"alias-{index+1}","aggregate_id":bundle["aggregate_id"],"coordinate_count":216,"named_area_count":None,"reference_sql_match":True})

    # Verified demo-only warm reuse must return the same retained citation and
    # must not repeat the large full-cohort summary/input scans.
    with patch.object(aggregates, "_inputs", side_effect=AssertionError("Warm reuse recomputed inputs")), patch.object(
        aggregates, "edna_summary", side_effect=AssertionError("Warm reuse recomputed summary")
    ):
        warm = aggregates.build_aggregate(plans[0].filters, metric="catalogue_geography")
    assert warm == bundle
    report["cases"].append({"name":"warm-reuse","same_aggregate_id":True,"full_scan_repeated":False})

    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        assert connection.exec_driver_sql("SHOW transaction_read_only").scalar() == "on"
        sample = connection.execute(text(
            "SELECT s.sample_id,s.provider_project_id FROM edna_sample s "
            "WHERE s.active IS TRUE AND s.provider='anemone' AND s.is_control IS NOT TRUE "
            f"AND {valid} ORDER BY s.sample_id LIMIT 1"
        )).mappings().one()
    for name, filters, independent in (
        ("sample-filter", {"sample_id":sample["sample_id"]}, reference(sample_id=sample["sample_id"])),
        ("project-filter", {"provider_project_id":sample["provider_project_id"]}, reference(project=sample["provider_project_id"])),
    ):
        plan = plan_catalogue_geography({"query":QUESTIONS[1],"evidence_scope":scope(filters=filters)})
        assert plan is not None and not plan.clarification and plan.metric == "catalogue_geography"
        scoped = aggregates.build_aggregate(plan.filters, metric="catalogue_geography")
        actual = compare(scoped, independent)
        assert scoped["aggregate_id"] != bundle["aggregate_id"]
        if name == "sample-filter":
            assert actual["locations"]["distinct_coordinate_pairs"] == 1
            assert actual["latitude_extreme_positions"][0] == actual["latitude_extreme_positions"][1]
            assert actual["latitude_extreme_separation_km"] == 0.0
        report["cases"].append({"name":name,"aggregate_id":scoped["aggregate_id"],"coordinate_count":actual["locations"]["distinct_coordinate_pairs"],"reference_sql":independent})

    # Load any already-retained legacy evidence. A fresh environment can prove
    # the same read compatibility with a tiny single-sample legacy receipt.
    for name, algorithm, metric in (
        ("historical-v1",aggregates.ALGORITHM,None),
        ("historical-v2",aggregates.LOCATION_ALGORITHM,"recorded_locations"),
    ):
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            identity = connection.execute(text(
                "SELECT aggregate_id FROM edna_aggregate_evidence WHERE algorithm_version=:algorithm ORDER BY aggregate_id LIMIT 1"
            ), {"algorithm":algorithm}).scalar()
        existing = identity is not None
        if identity is None:
            old = aggregates.build_aggregate({"provider":"anemone","sample_id":sample["sample_id"]},metric=metric)
            identity = old["aggregate_id"]
        old = aggregates.load_aggregate(identity)
        assert old is not None and old["payload"]["algorithm_version"] == algorithm
        assert old["aggregate_id"] != bundle["aggregate_id"]
        assert aggregates.aggregate_trace(identity)["found"]
        report["cases"].append({"name":name,"aggregate_id":identity,"existing_receipt":existing,"load_and_trace_passed":True})

    pinned = scope()
    pinned["sources"]["edna_metabarcoding"]["analysis_id"] = "a"*64
    for name, question, evidence_scope in (
        ("edna-disabled",QUESTIONS[0],scope(edna=False)),
        ("pinned-analysis",QUESTIONS[1],pinned),
        ("unsupported-place","how many named area are available in Japan",scope()),
        ("unsupported-date","are all sampling data from around the same area in 2020",scope()),
        ("directional-qualifier","are all sampling data from around the same northern area",scope()),
    ):
        plan = plan_catalogue_geography({"query":question,"evidence_scope":evidence_scope})
        assert plan is not None and plan.clarification, name
        report["cases"].append({"name":name,"clarification":True})

    pointer = aggregates.publication_pointer()
    with patch.object(aggregates,"publication_pointer",return_value={**pointer,"status":"pending"}):
        try:
            aggregates.build_aggregate(plans[0].filters,metric="catalogue_geography")
        except aggregates.AggregateUnavailable:
            pass
        else:
            raise AssertionError("Stale publication must not serve geography evidence")
    assert aggregates.load_aggregate(bundle["aggregate_id"]) == bundle
    report.update(
        passed=True,
        reference_sql=expected,
        coordinate_extent=expected["coordinate_extent"],
        latitude_extreme_separation_km=expected["latitude_extreme_separation_km"],
        historical_v1_v2_and_geography_v3_roundtrip=True,
        stale_publication_rejected=True,
        scientific_rows_modified=False,
        users_created_or_reactivated=False,
        cloud_resources_modified=False,
        browser_or_http_authentication_test=False,
    )
    print(json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)


if __name__ == "__main__":
    main()
