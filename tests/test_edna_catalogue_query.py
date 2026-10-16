"""Canonical relational predicates run without database or retrieval services."""
import copy
import json

import pandas as pd
import pytest

from preprocessing.edna_catalogue_query import (
    EDNA_ASSIGNMENT_METHODS,
    QueryUnavailable,
    normalize_filters,
    select_rows,
    sql_conditions,
)


def query_tables():
    occurrences, classifications, assays, detections = [], [], [], []
    for number, (kind, control) in enumerate((
        ("environmental", False), ("negative_control", True), ("unknown", None),
        ("environmental", False), ("environmental", False),
    )):
        occurrences.append({
            "sample_id": f"s{number}", "provider": "anemone", "provider_locus": "MiFish",
            "provider_team": "Team", "provider_project_id": "Project", "provider_run_id": f"Run{number}",
            "collection_date_utc": "2024-01-01", "temporal_precision": "date",
            "lat": 38.4, "lon": 141.5, "active": number != 3,
        })
        classifications.append({"sample_id": f"s{number}", "sample_kind": kind, "is_control": control})
        availability = {method: {"status": "available", "row_count": 0 if number == 4 else 1}
                        for method in EDNA_ASSIGNMENT_METHODS}
        assays.append({"sample_id": f"s{number}", "assay_id": f"a{number}", "active": True,
                       "community_availability_json": json.dumps(availability)})
        if number != 4:
            for index, method in enumerate(sorted(EDNA_ASSIGNMENT_METHODS)):
                detections.append({"detection_id": f"d{number}{index}", "assay_id": f"a{number}",
                                   "assignment_method": method,
                                   "target_status": "nontarget" if method.endswith("_nontarget") else "target",
                                   "assigned_taxon_name": "Fixture fish", "taxonomy_json": json.dumps({
                                       "kingdom": "Metazoa", "genus": "Fixture", "species": "Fixture fish",
                                       "subspecies": "unknown fixture",
                                   }), "read_count": 17, "active": True})
    assays.append({"sample_id": "s0", "assay_id": "sibling", "active": True,
                   "community_availability_json": "{}"})
    return {key: pd.DataFrame(rows) for key, rows in {
        "occurrences": occurrences, "classifications": classifications,
        "assays": assays, "detections": detections,
    }.items()}


def _ids(rows, key):
    return rows[key][{"occurrences": "sample_id", "assays": "assay_id", "detections": "detection_id"}[key]].tolist()


def test_complete_active_raw_cohorts_are_distinct_and_inputs_unchanged():
    tables = query_tables()
    before = copy.deepcopy(tables)
    result = select_rows(tables, {})
    assert _ids(result, "occurrences") == ["s0", "s1", "s2", "s4"]
    assert _ids(result, "assays") == ["a0", "a1", "a2", "a4", "sibling"]
    assert len(result["detections"]) == 12
    assert set(result["detections"].assignment_method) == EDNA_ASSIGNMENT_METHODS
    assert result["occurrences"].sample_kind.tolist() == ["environmental", "negative_control", "unknown", "environmental"]
    for key in tables:
        pd.testing.assert_frame_equal(tables[key], before[key])


@pytest.mark.parametrize("method", sorted(EDNA_ASSIGNMENT_METHODS))
def test_each_raw_method_selects_available_empty_tables_without_inventing_detections(method):
    result = select_rows(query_tables(), {"assignment_method": method})
    assert _ids(result, "occurrences") == ["s0", "s1", "s2", "s4"]
    assert _ids(result, "assays") == ["a0", "a1", "a2", "a4"]
    assert len(result["detections"]) == 3
    assert set(result["detections"].assignment_method) == {method}


@pytest.mark.parametrize("taxon", ["FIXTURE FISH", "metazoa", "Fixture", "unknown fixture"])
def test_taxon_is_exact_case_insensitive_across_canonical_ranks_and_unknown_labels(taxon):
    result = select_rows(query_tables(), {"taxon": taxon})
    assert _ids(result, "occurrences") == ["s0", "s1", "s2"]
    assert _ids(result, "assays") == ["a0", "a1", "a2"]
    assert len(result["detections"]) == 12
    assert select_rows(query_tables(), {"taxon": "Fixture fi"})["detections"].empty


@pytest.mark.parametrize("criterion", [
    {"taxon": "Fixture fish"}, {"assignment_method": "qcauto_target"}, {"target_status": "target"},
])
def test_assay_and_detection_filters_never_match_a_sibling_assay(criterion):
    result = select_rows(query_tables(), {"assay_id": "sibling", **criterion})
    assert all(frame.empty for frame in result.values())


def test_taxon_method_and_status_are_correlated_to_the_same_detection():
    tables = query_tables()
    tables["detections"].loc[tables["detections"].assignment_method == "qcauto_nontarget", "taxonomy_json"] = '{}'
    tables["detections"].loc[tables["detections"].assignment_method == "qcauto_nontarget", "assigned_taxon_name"] = "Other fish"
    result = select_rows(tables, {"assignment_method": "qcauto_nontarget", "taxon": "Fixture fish"})
    assert all(frame.empty for frame in result.values())
    contradictory = select_rows(tables, {"assignment_method": "qcauto_nontarget", "target_status": "target"})
    assert all(frame.empty for frame in contradictory.values())


@pytest.mark.parametrize(("filters", "expected"), [
    ({"provider": "missing"}, []), ({"provider_locus": "Other"}, []),
    ({"provider_team": "Other"}, []), ({"provider_project_id": "Other"}, []),
    ({"provider_run_id": "Run0"}, ["s0"]), ({"sample_id": "s1"}, ["s1"]),
    ({"sample_kind": "unknown"}, ["s2"]), ({"is_control": True}, ["s1"]),
    ({"is_control": False}, ["s0", "s4"]), ({"lat_min": 38.5}, []),
    ({"lat_max": 38.4}, ["s0", "s1", "s2", "s4"]), ({"lon_min": 141.5}, ["s0", "s1", "s2", "s4"]),
    ({"lon_max": 141.4}, []),
])
def test_shared_scalar_predicates(filters, expected):
    result = select_rows(query_tables(), filters)
    assert _ids(result, "occurrences") == expected
    for entity in result:
        clauses, params = sql_conditions(entity, filters)
        assert clauses and params == filters


@pytest.mark.parametrize(("start", "end", "matches"), [
    ("2024-01-01T18:00:00Z", "2024-01-01T19:00:00Z", True),
    ("2024-01-02T00:00:00Z", None, False),
    (None, "2023-12-31", False), (None, "2024-01-01", True),
    ("2024-01-02T08:00:00+09:00", None, True),
])
def test_day_evidence_uses_utc_interval_overlap_without_inventing_an_instant(start, end, matches):
    result = select_rows(query_tables(), {"time_from": start, "time_to": end})
    assert bool(len(result["occurrences"])) is matches


@pytest.mark.parametrize("precision", ["year", "month", "unknown", None])
def test_coarse_or_unknown_precision_is_retained_but_exact_time_query_is_unavailable(precision):
    tables = query_tables()
    tables["occurrences"].loc[0, "temporal_precision"] = precision
    assert len(select_rows(tables, {})["occurrences"]) == 4
    with pytest.raises(QueryUnavailable, match="coarse or unresolved"):
        select_rows(tables, {"time_from": "2024-01-01"})
    # A known namespace exclusion can be decided without inspecting its date.
    assert select_rows(tables, {"provider": "absent", "time_from": "2024-01-01"})["occurrences"].empty


def test_datetime_offsets_are_compared_in_utc_and_inactive_parents_cannot_leak():
    tables = query_tables()
    tables["occurrences"].loc[0, ["collection_date_utc", "temporal_precision"]] = ["2024-01-01T09:00:00+09:00", "datetime"]
    filters = {"sample_id": "s0", "time_from": "2024-01-01T00:00:00Z", "time_to": "2024-01-01T00:00:00Z"}
    assert len(select_rows(tables, filters)["detections"]) == 4
    tables["assays"].loc[0, "active"] = False
    assert select_rows(tables, filters)["detections"].empty


@pytest.mark.parametrize("filters", [
    {"bogus": 1}, {"assignment_method": "invented"}, {"sample_kind": "animal"},
    {"target_status": "other"}, {"is_control": 1}, {"lat_min": True},
    {"lat_min": float("nan")}, {"lat_min": 91}, {"lon_max": 181},
    {"lon_min": 142, "lon_max": 141}, {"lat_min": 39, "lat_max": 38},
    {"provider": " "}, {"time_from": "2024-02-30"},
    {"time_from": "2024-02-02", "time_to": "2024-02-01"},
])
def test_invalid_operation_filters_fail_before_row_execution(filters):
    with pytest.raises(ValueError):
        normalize_filters(filters)


def test_sql_compatibility_wrappers_render_the_same_predicate_nodes():
    from api.edna_service import _aggregate_assay_conditions, _detection_conditions, _sample_conditions
    filters = {"assay_id": "a0", "assignment_method": "qcauto_target", "taxon": "Fixture fish", "is_control": False}
    for entity, wrapper in (("occurrences", _sample_conditions), ("assays", _aggregate_assay_conditions), ("detections", _detection_conditions)):
        assert wrapper(filters) == sql_conditions(entity, filters)
