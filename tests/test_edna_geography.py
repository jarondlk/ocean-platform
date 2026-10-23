"""Canonical geography uses exact stored positions and preserves catalogue scope."""

import pytest
from sqlalchemy import text

from api.edna_service import edna_geography_summary, edna_location_summary
from tests import test_edna_location_counts as location_tests

positions = location_tests.positions


def summary(connection, **filters):
    return edna_geography_summary({"provider": "anemone", **filters}, connection=connection)


def replace_points(connection, points):
    connection.execute(text("DELETE FROM edna_sample"))
    for index, (lat, lon) in enumerate(points):
        connection.execute(text("""
            INSERT INTO edna_sample(sample_id,provider,active,provider_project_id,
            provider_run_id,collection_date_utc,sample_kind,is_control,lat,lon,coordinate_precision)
            VALUES (:id,'anemone',true,'Provider label - not an area','R1',
                    '2020-01-01T00:00:00Z','unknown',NULL,:lat,:lon,'provider_grid_unconfirmed')
        """), {"id": "point" + str(index), "lat": lat, "lon": lon})


def assert_empty_geometry(value):
    assert value["coordinate_extent"] == {"lat_min": None, "lat_max": None, "lon_min": None, "lon_max": None}
    assert value["latitude_extreme_positions"] == []
    assert value["latitude_extreme_separation_km"] is None
    assert value["locations"]["distinct_coordinate_pairs"] == 0
    assert value["named_area_count"] is None


def test_valid_bounds_and_location_accounting_match_existing_metric(positions):
    result = summary(positions)
    assert result["locations"] == edna_location_summary({"provider": "anemone"}, connection=positions)
    assert result["locations"]["valid_coordinate_occurrences"] == 8
    assert result["locations"]["missing_coordinate_occurrences"] == 2
    assert result["locations"]["invalid_coordinate_occurrences"] == 4
    assert result["coordinate_extent"] == {"lat_min": -90, "lat_max": 90, "lon_min": -180, "lon_max": 180}
    assert result["latitude_extreme_positions"] == [{"lat": -90, "lon": -180}, {"lat": 90, "lon": 180}]
    assert result["latitude_extreme_separation_km"] == 20015.114
    assert result["named_area_status"] == "not_established_by_canonical_catalogue"
    assert result["named_area_count"] is None
    assert result["named_area_definition"] == (
        "No reviewed area-membership relation is provided by this canonical-catalogue aggregate; "
        "provider/project/sample labels are not bay boundaries."
    )
    assert positions.in_transaction()


@pytest.mark.parametrize("sample", ["absent", "s5", "s7", "s8", "s9", "s10", "s13", "s14"])
def test_missing_invalid_empty_and_inactive_scopes_have_no_extent(positions, sample):
    assert_empty_geometry(summary(positions, sample_id=sample))


@pytest.mark.parametrize("point", [
    (None, 141), (35, None), (float("nan"), 141), (35, float("nan")),
    (float("inf"), 141), (35, float("-inf")), (90.1, 141), (35, -180.1),
])
def test_invalid_or_missing_coordinates_never_supply_extreme_positions(positions, point):
    replace_points(positions, [point])
    assert_empty_geometry(summary(positions))
    assert summary(positions)["locations"]["source_occurrences"] == 1


def test_filtered_single_position_has_real_repeated_endpoints_and_zero_separation(positions):
    result = summary(positions, provider_project_id="P2")
    assert result["coordinate_extent"] == {"lat_min": 35.000001, "lat_max": 35.000001, "lon_min": 141, "lon_max": 141}
    assert result["latitude_extreme_positions"] == [{"lat": 35.000001, "lon": 141}, {"lat": 35.000001, "lon": 141}]
    assert result["latitude_extreme_separation_km"] == 0.0
    assert result["locations"]["source_occurrences"] == 1
    assert result["named_area_count"] is None


def test_date_filters_and_nearby_positions_are_preserved_without_rounding(positions):
    result = summary(positions, time_from="2021-01-01", time_to="2021-12-31")
    assert result["locations"]["source_occurrences"] == result["locations"]["distinct_coordinate_pairs"] == 2
    assert result["coordinate_extent"] == {"lat_min": 35, "lat_max": 35.000001, "lon_min": 141, "lon_max": 141}
    assert result["latitude_extreme_positions"] == [{"lat": 35, "lon": 141}, {"lat": 35.000001, "lon": 141}]
    # Only the distance presentation is rounded to 3 decimals, never the stored positions.
    assert result["latitude_extreme_separation_km"] == 0.0


def test_assays_and_taxon_filters_cannot_multiply_or_widen_geography(positions):
    result = summary(positions, assignment_method="qcauto_target", exclude_explicit_controls=True)
    assert result["locations"]["source_occurrences"] == 3
    assert result["locations"]["distinct_coordinate_pairs"] == 2
    assert result["coordinate_extent"] == {"lat_min": 35, "lat_max": 41, "lon_min": 141, "lon_max": 143}
    assert result["latitude_extreme_positions"] == [{"lat": 35, "lon": 141}, {"lat": 41, "lon": 143}]
    fish = summary(positions, taxon="FIXTURE FISH", exclude_explicit_controls=True)
    assert fish["locations"]["source_occurrences"] == 2
    assert fish["locations"]["distinct_coordinate_pairs"] == 1
    assert fish["coordinate_extent"] == {"lat_min": 35, "lat_max": 35, "lon_min": 141, "lon_max": 141}
    assay = summary(positions, assay_id="a2", taxon="Fixture fish")
    assert assay["locations"]["source_occurrences"] == 1
    assert assay["coordinate_extent"] == fish["coordinate_extent"]
    assert_empty_geometry(summary(positions, assignment_method="qcauto_95pct_3nn_target", taxon="Fixture fish"))


def test_explicit_control_and_unknown_classification_policies_are_preserved(positions):
    unknown_included = summary(positions, exclude_explicit_controls=True)
    assert unknown_included["locations"]["unknown_control_status"] == 11
    assert unknown_included["locations"]["controls"] == 0
    assert unknown_included["locations"]["distinct_coordinate_pairs"] == 6
    controls = summary(positions, is_control=True)
    assert controls["locations"]["controls"] == 1
    assert controls["latitude_extreme_positions"] == [{"lat": 40, "lon": 142}, {"lat": 40, "lon": 142}]
    classified = summary(positions, is_control=False)
    assert classified["locations"]["unknown_control_status"] == 0
    assert classified["locations"]["distinct_coordinate_pairs"] == 2
    assert classified["coordinate_extent"] == {"lat_min": 0, "lat_max": 41, "lon_min": 0, "lon_max": 143}


def test_separation_uses_actual_extreme_positions_not_bounding_rectangle_corners(positions):
    replace_points(positions, [(0, 0), (90, 120), (45, -170)])
    result = summary(positions)
    assert result["coordinate_extent"] == {"lat_min": 0, "lat_max": 90, "lon_min": -170, "lon_max": 120}
    assert result["latitude_extreme_positions"] == [{"lat": 0, "lon": 0}, {"lat": 90, "lon": 120}]
    # Equator to pole is exactly a quarter circumference for the chosen sphere.
    assert result["latitude_extreme_separation_km"] == 10007.557


def test_tied_extreme_latitudes_use_stable_longitude_tie_breaking(positions):
    replace_points(positions, [(10, 20), (20, 100), (10, -50), (20, 30)])
    result = summary(positions)
    assert result["latitude_extreme_positions"] == [{"lat": 10, "lon": -50}, {"lat": 20, "lon": 30}]
    assert result["coordinate_extent"] == {"lat_min": 10, "lat_max": 20, "lon_min": -50, "lon_max": 100}


def test_dateline_endpoint_distance_uses_short_great_circle_path(positions):
    replace_points(positions, [(-1, 179), (1, -179)])
    result = summary(positions)
    assert result["coordinate_extent"] == {"lat_min": -1, "lat_max": 1, "lon_min": -179, "lon_max": 179}
    assert result["latitude_extreme_positions"] == [{"lat": -1, "lon": 179}, {"lat": 1, "lon": -179}]
    assert result["latitude_extreme_separation_km"] == 314.499


def test_latitude_extreme_distance_is_not_a_claim_of_maximum_pairwise_span(positions):
    replace_points(positions, [(35, 100), (35, 145)])
    result = summary(positions)
    assert result["locations"]["distinct_coordinate_pairs"] == 2
    assert result["coordinate_extent"]["lon_min"] == 100
    assert result["coordinate_extent"]["lon_max"] == 145
    assert result["latitude_extreme_positions"] == [{"lat": 35, "lon": 100}, {"lat": 35, "lon": 100}]
    assert result["latitude_extreme_separation_km"] == 0.0


def test_current_catalogue_latitude_extreme_pair_has_the_audited_separation(positions):
    replace_points(positions, [(17.45833333, 148.6875), (45.54166667, 141.9375)])
    result = summary(positions)
    assert result["latitude_extreme_separation_km"] == 3184.838
    assert result["named_area_count"] is None
    # The project label supplied above is never treated as a reviewed geographic name.
    assert result["named_area_status"] == "not_established_by_canonical_catalogue"
