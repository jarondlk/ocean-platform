#!/usr/bin/env python3
"""Verify location counts inside the isolated COP17 runtime.

Scientific reads use the published demo snapshot. The only persistent writes
are immutable aggregate evidence in application history. This probe neither
creates/reactivates users nor replaces signed-in browser/HTTP acceptance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

from sqlalchemy.engine import make_url


def guard_demo() -> None:
    """Reject production, generic TCP databases and other artifact roots."""
    url = make_url(os.environ["DATABASE_URL"])
    if (
        url.database != "ocean_cop17"
        or url.query.get("host")
        != "/cloudsql/data-infra-infobio:asia-northeast1:ocean-cop17-postgres"
        or url.host
        or url.port
        or url.drivername not in {"postgresql", "postgresql+psycopg2"}
    ):
        raise RuntimeError("Only the fixed isolated COP17 database socket is allowed")
    if (
        os.environ.get("COP17_DEMO_ENABLED", "").strip().lower() != "true"
        or os.environ.get("EDNA_ARTIFACT_URI")
        != "gs://data-infra-infobio-ocean-cop17/edna-cop17-snapshot"
    ):
        raise RuntimeError(
            "Only the COP17 profile and isolated artifact root are allowed"
        )


def scope(*, edna: bool = True, sst: bool = True, filters: dict | None = None) -> dict:
    return {
        "version": 1,
        "sources": {
            "ctd": {"enabled": False, "filters": {}},
            "metagenome": {"enabled": False, "filters": {}},
            "remote_sensing": {"enabled": sst, "filters": {}},
            "edna_metabarcoding": {"enabled": edna, "filters": filters or {}},
        },
    }


QUESTIONS = (
    "how many sampling area available",
    "How many sampling locations are available in ANEMONE eDNA?",
    "How many sampling areas are available?",
    "ANEMONEの採水地点はいくつありますか？",
)


def main() -> None:
    guard_demo()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlalchemy import text
    from db.connection import get_engine
    from ingestion import edna_aggregate as aggregates
    from orchestration.edna_aggregation import plan_location_count, render_answer

    engine = get_engine()
    valid = "s.lat BETWEEN -90 AND 90 AND s.lon BETWEEN -180 AND 180"

    # Independent reference SQL deliberately does not reuse the application's
    # sample predicates or location aggregation implementation.
    def reference(*, sample_id=None, project=None, controls=None) -> dict:
        clauses = ["s.active IS TRUE", "s.provider = 'anemone'"]
        params = {}
        if controls is None:
            clauses.append("s.is_control IS NOT TRUE")
        else:
            clauses.append("s.is_control IS NOT DISTINCT FROM :controls")
            params["controls"] = controls
        if sample_id is not None:
            clauses.append("s.sample_id = :sample_id")
            params["sample_id"] = sample_id
        if project is not None:
            clauses.append("s.provider_project_id = :project")
            params["project"] = project
        with engine.connect() as connection:
            connection.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.exec_driver_sql("SET LOCAL statement_timeout = '20s'")
            assert (
                connection.exec_driver_sql("SHOW transaction_read_only").scalar()
                == "on"
            )
            return dict(
                connection.execute(
                    text(
                        "SELECT count(*) AS source_occurrences, "
                        f"count(*) FILTER (WHERE {valid}) AS valid_coordinate_occurrences, "
                        f"count(DISTINCT (s.lat,s.lon)) FILTER (WHERE {valid}) AS distinct_coordinate_pairs, "
                        "count(*) FILTER (WHERE s.lat IS NULL OR s.lon IS NULL) AS missing_coordinate_occurrences, "
                        f"count(*) FILTER (WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL AND NOT ({valid})) AS invalid_coordinate_occurrences, "
                        "count(*) FILTER (WHERE s.is_control IS TRUE) AS controls, "
                        "count(*) FILTER (WHERE s.is_control IS NULL) AS unknown_control_status "
                        "FROM edna_sample s WHERE " + " AND ".join(clauses)
                    ),
                    params,
                )
                .mappings()
                .one()
            )

    report = {"probe": "cop17-recorded-location-counts", "cases": []}
    expected = reference()
    assert expected == {
        "source_occurrences": 3155,
        "valid_coordinate_occurrences": 3154,
        "distinct_coordinate_pairs": 216,
        "missing_coordinate_occurrences": 1,
        "invalid_coordinate_occurrences": 0,
        "controls": 0,
        "unknown_control_status": 3155,
    }, "Demo snapshot differs from the reviewed location metadata audit"
    plans = []
    for index, question in enumerate(QUESTIONS):
        plan = plan_location_count(
            {
                "query": question,
                "evidence_scope": scope(sst=index < 2),
            }
        )
        assert (
            plan is not None
            and not plan.clarification
            and plan.metric == "recorded_locations"
        )
        plans.append(plan)
    assert all(plan.filters == plans[0].filters for plan in plans)
    bundle = aggregates.build_aggregate(plans[0].filters, metric="recorded_locations")
    locations = bundle["payload"]["summary"]["locations"]
    assert all(locations[key] == value for key, value in expected.items())
    assert bundle["payload"]["filters"]["exclude_explicit_controls"] is True
    assert locations["sample_kinds"] == {"unknown": 3155}
    assert locations["coordinate_precision"] == {"provider_grid_unconfirmed": 3154}
    assert locations["environmental_classified"] == 0
    assert locations["control_policy"] == "exclude_explicit_controls"
    assert aggregates.load_aggregate(bundle["aggregate_id"]) == bundle
    for index, question in enumerate(QUESTIONS):
        rendered = render_answer(bundle, question)
        assert (
            "216" in rendered
            and "[aggregate_edna_" + bundle["aggregate_id"] + "]" in rendered
        )
        if index == 3:
            assert "座標" in rendered
        report["cases"].append(
            {
                "name": f"alias-{index + 1}",
                "count": 216,
                "aggregate_id": bundle["aggregate_id"],
            }
        )

    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        sample = (
            connection.execute(
                text(
                    "SELECT s.sample_id,s.provider_project_id FROM edna_sample s "
                    "WHERE s.active IS TRUE AND s.provider='anemone' AND s.is_control IS NOT TRUE "
                    f"AND {valid} ORDER BY s.sample_id LIMIT 1"
                )
            )
            .mappings()
            .one()
        )
    for name, filters, independent in (
        (
            "sample-filter",
            {"sample_id": sample["sample_id"]},
            reference(sample_id=sample["sample_id"]),
        ),
        (
            "project-filter",
            {"provider_project_id": sample["provider_project_id"]},
            reference(project=sample["provider_project_id"]),
        ),
        ("explicit-controls", {"is_control": True}, reference(controls=True)),
    ):
        plan = plan_location_count(
            {"query": QUESTIONS[1], "evidence_scope": scope(filters=filters)}
        )
        assert plan is not None and not plan.clarification
        result = aggregates.build_aggregate(plan.filters, metric="recorded_locations")
        actual = result["payload"]["summary"]["locations"]
        assert all(actual[key] == value for key, value in independent.items())
        if name == "sample-filter":
            assert actual["distinct_coordinate_pairs"] == 1
        if name == "explicit-controls":
            assert actual["control_policy"] == "explicit_filters"
            assert not result["payload"]["filters"].get("exclude_explicit_controls")
        assert aggregates.load_aggregate(result["aggregate_id"]) == result
        report["cases"].append(
            {
                "name": name,
                "count": actual["distinct_coordinate_pairs"],
                "reference_sql_match": True,
            }
        )

    for name, question, evidence_scope in (
        ("edna-disabled", QUESTIONS[0], scope(edna=False)),
        (
            "physical-sites",
            "How many distinct physical sampling sites are available?",
            scope(),
        ),
        ("named-areas", "How many named sampling areas are available?", scope()),
        (
            "unsupported-place",
            "How many sampling locations are available in Japan?",
            scope(),
        ),
        (
            "unsupported-date",
            "How many sampling locations are available in 2020?",
            scope(),
        ),
        (
            "combined-sources",
            "How many sampling locations are available across ANEMONE and SST?",
            scope(),
        ),
    ):
        plan = plan_location_count(
            {"query": question, "evidence_scope": evidence_scope}
        )
        assert plan is not None and plan.clarification, name
        report["cases"].append({"name": name, "clarification": True})

    old = aggregates.build_aggregate({"provider": "anemone"})
    assert old["payload"]["algorithm_version"] == "edna-catalogue-aggregate-v1"
    assert bundle["payload"]["algorithm_version"] != old["payload"]["algorithm_version"]
    assert aggregates.load_aggregate(old["aggregate_id"]) == old
    pointer = aggregates.publication_pointer()
    with patch.object(
        aggregates, "publication_pointer", return_value={**pointer, "status": "pending"}
    ):
        try:
            aggregates.build_aggregate(plans[0].filters, metric="recorded_locations")
        except aggregates.AggregateUnavailable:
            pass
        else:
            raise AssertionError(
                "A stale publication must not produce aggregate evidence"
            )
    assert aggregates.load_aggregate(bundle["aggregate_id"]) == bundle
    report.update(
        passed=True,
        reference_sql=expected,
        metadata_audit_count_match=True,
        historical_v1_and_location_v2_roundtrip=True,
        stale_publication_rejected=True,
        scientific_rows_modified=False,
        users_created_or_reactivated=False,
        browser_or_http_authentication_test=False,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
