"""Exact recorded-position counts, with real PostgreSQL semantics when enabled."""

import os

import pytest
from sqlalchemy import create_engine, text

from api.edna_service import (
    _aggregate_assay_conditions,
    _detection_conditions,
    _sample_conditions,
    edna_location_summary,
)


@pytest.mark.parametrize(
    "builder", [_sample_conditions, _detection_conditions, _aggregate_assay_conditions]
)
def test_explicit_control_exclusion_keeps_unknown_status_in_all_predicates(builder):
    conditions, params = builder(
        {"provider": "anemone", "exclude_explicit_controls": True}
    )
    assert "s.is_control IS NOT TRUE" in conditions
    assert "is_control" not in params
    # Existing summaries and explicit non-control filters retain their semantics.
    plain, _ = builder({"provider": "anemone"})
    assert "s.is_control IS NOT TRUE" not in plain
    explicit, values = builder({"is_control": False})
    assert "s.is_control IS NOT DISTINCT FROM :is_control" in explicit
    assert values["is_control"] is False


@pytest.mark.parametrize(
    "builder", [_sample_conditions, _detection_conditions, _aggregate_assay_conditions]
)
@pytest.mark.parametrize("value", ["true", "false", 1, 0])
def test_internal_exclusion_flag_rejects_non_boolean_values(builder, value):
    with pytest.raises(ValueError, match="must be a boolean"):
        builder({"exclude_explicit_controls": value})


@pytest.fixture
def positions():
    if os.environ.get("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires disposable PostgreSQL")
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("""
                CREATE TEMP TABLE edna_sample (
                    sample_id text PRIMARY KEY, provider text, active boolean,
                    provider_locus text DEFAULT 'MiFish', provider_team text DEFAULT 'ANEMONE',
                    provider_project_id text, provider_run_id text,
                    collection_date_utc text, temporal_precision text DEFAULT 'second',
                    sample_kind text, is_control boolean, lat double precision,
                    lon double precision, coordinate_precision text)
            """)
            connection.exec_driver_sql("""
                CREATE TEMP TABLE edna_assay (
                    assay_id text PRIMARY KEY, sample_id text, active boolean,
                    community_availability_json text)
            """)
            connection.exec_driver_sql("""
                CREATE TEMP TABLE edna_detection (
                    assay_id text, active boolean, assignment_method text, target_status text,
                    assigned_taxon_name text, superkingdom text, kingdom text, phylum text,
                    "class" text, "order" text, family text, genus text, species text, subspecies text)
            """)
            values = [
                (
                    "s1",
                    35,
                    141,
                    "unknown",
                    None,
                    True,
                    "P1",
                    "R1",
                    "provider_grid_unconfirmed",
                ),
                (
                    "s2",
                    35,
                    141,
                    "unknown",
                    None,
                    True,
                    "P1",
                    "R2",
                    "provider_grid_unconfirmed",
                ),
                (
                    "s3",
                    35.000001,
                    141,
                    "unknown",
                    None,
                    True,
                    "P2",
                    "R2",
                    "provider_grid_unconfirmed",
                ),
                (
                    "s4",
                    40,
                    142,
                    "negative_control",
                    True,
                    True,
                    "P1",
                    "R1",
                    "provider_grid_unconfirmed",
                ),
                ("s5", None, 141, "unknown", None, True, "P1", "R1", "unspecified"),
                (
                    "s6",
                    0,
                    0,
                    "environmental",
                    False,
                    True,
                    "P1",
                    "R1",
                    "reviewed_coordinates",
                ),
                (
                    "s7",
                    float("nan"),
                    141,
                    "unknown",
                    None,
                    True,
                    "P1",
                    "R1",
                    "unspecified",
                ),
                (
                    "s8",
                    float("inf"),
                    141,
                    "unknown",
                    None,
                    True,
                    "P1",
                    "R1",
                    "unspecified",
                ),
                ("s9", 91, 141, "unknown", None, True, "P1", "R1", "unspecified"),
                ("s10", 35, 181, "unknown", None, True, "P1", "R1", "unspecified"),
                (
                    "s11",
                    90,
                    180,
                    "unknown",
                    None,
                    True,
                    "P1",
                    "R1",
                    "provider_grid_unconfirmed",
                ),
                (
                    "s12",
                    -90,
                    -180,
                    "unknown",
                    None,
                    True,
                    "P1",
                    "R1",
                    "provider_grid_unconfirmed",
                ),
                ("s13", 35, None, "unknown", None, True, "P1", "R1", "unspecified"),
                (
                    "s14",
                    40,
                    150,
                    "unknown",
                    None,
                    False,
                    "P1",
                    "R1",
                    "provider_grid_unconfirmed",
                ),
                (
                    "s15",
                    41,
                    150,
                    "unknown",
                    None,
                    True,
                    "P1",
                    "R1",
                    "provider_grid_unconfirmed",
                ),
                ("s16", 41, 143, "environmental", False, True, "P1", "R1", ""),
            ]
            for sid, lat, lon, kind, control, active, project, run, precision in values:
                connection.execute(
                    text("""
                    INSERT INTO edna_sample(sample_id,provider,active,provider_project_id,
                    provider_run_id,collection_date_utc,sample_kind,is_control,lat,lon,coordinate_precision)
                    VALUES (:id,:provider,:active,:project,:run,:date,:kind,:control,:lat,:lon,:precision)
                """),
                    dict(
                        id=sid,
                        provider="other" if sid == "s15" else "anemone",
                        active=active,
                        project=project,
                        run=run,
                        date="2021-01-01T00:00:00Z"
                        if run == "R2"
                        else "2020-01-01T00:00:00Z",
                        kind=kind,
                        control=control,
                        lat=lat,
                        lon=lon,
                        precision=precision,
                    ),
                )
            for aid, sid, method, species, active in [
                ("a1", "s1", "qcauto_target", "Fixture fish", True),
                ("a2", "s1", "qcauto_target", "Fixture fish", True),
                ("a3", "s2", "qcauto_target", "Fixture fish", True),
                ("a4", "s3", "qcauto_95pct_3nn_target", None, True),
                ("a5", "s4", "qcauto_target", "Fixture fish", True),
                ("a6", "s16", "qcauto_target", "Other fish", True),
                ("a7", "s12", "qcauto_target", "Fixture fish", False),
            ]:
                connection.execute(
                    text(
                        "INSERT INTO edna_assay VALUES (:aid,:sid,:active,:available)"
                    ),
                    dict(
                        aid=aid,
                        sid=sid,
                        active=active,
                        available='{"' + method + '":{"row_count":0}}'
                        if species is None
                        else "{}",
                    ),
                )
                if species:
                    connection.execute(
                        text("""
                        INSERT INTO edna_detection(assay_id,active,assignment_method,target_status,species)
                        VALUES (:aid,true,:method,'target',:species)
                    """),
                        dict(aid=aid, method=method, species=species),
                    )
            yield connection
    finally:
        engine.dispose()


def test_postgres_exact_pairs_precision_and_coordinate_exclusions(positions):
    result = edna_location_summary({"provider": "anemone"}, connection=positions)
    assert result["source_occurrences"] == 14
    assert result["valid_coordinate_occurrences"] == 8
    assert result["distinct_coordinate_pairs"] == 7
    assert result["missing_coordinate_occurrences"] == 2
    assert result["invalid_coordinate_occurrences"] == 4
    assert result["controls"] == 1
    assert result["unknown_control_status"] == 11
    assert result["environmental_classified"] == 2
    assert result["sample_kinds"] == {
        "environmental": 2,
        "negative_control": 1,
        "unknown": 11,
    }
    assert result["coordinate_precision"] == {
        "provider_grid_unconfirmed": 6,
        "reviewed_coordinates": 1,
        "unspecified": 1,
    }
    assert result["control_policy"] == "explicit_filters"
    # s1/s2 repeat one position; s3 is only 0.000001 degrees away and remains distinct.
    assert "no rounding" in result["definition"]


def test_postgres_default_exclusion_and_explicit_control_filters(positions):
    result = edna_location_summary(
        {"provider": "anemone", "exclude_explicit_controls": True}, connection=positions
    )
    assert result["source_occurrences"] == 13
    assert result["distinct_coordinate_pairs"] == 6
    assert result["valid_coordinate_occurrences"] == 7
    assert result["unknown_control_status"] == 11
    assert result["controls"] == 0
    assert result["control_policy"] == "exclude_explicit_controls"
    for selection, records, pairs in [(True, 1, 1), (False, 2, 2)]:
        explicit = edna_location_summary(
            {"provider": "anemone", "is_control": selection}, connection=positions
        )
        assert explicit["source_occurrences"] == records
        assert explicit["distinct_coordinate_pairs"] == pairs
    # Unknown classifications remain unknown rather than being relabeled environmental.
    unknown = edna_location_summary(
        {"sample_kind": "unknown", "provider": "anemone"}, connection=positions
    )
    assert unknown["environmental_classified"] == 0


@pytest.mark.parametrize(
    "filters,records,pairs",
    [
        ({"provider_project_id": "P2"}, 1, 1),
        ({"provider_run_id": "R2"}, 2, 2),
        ({"time_from": "2021-01-01", "time_to": "2021-12-31"}, 2, 2),
        ({"lat_min": 34, "lat_max": 36, "lon_min": 140, "lon_max": 142}, 3, 2),
        ({"sample_id": "absent"}, 0, 0),
    ],
)
def test_postgres_explicit_source_filters_are_preserved(
    positions, filters, records, pairs
):
    result = edna_location_summary(
        {"provider": "anemone", **filters}, connection=positions
    )
    assert result["source_occurrences"] == records
    assert result["distinct_coordinate_pairs"] == pairs


def test_postgres_assays_methods_and_taxa_use_exists_without_inflating_positions(
    positions,
):
    # Two assays and repeated sample dates cannot inflate a coordinate-pair total.
    result = edna_location_summary(
        {"provider": "anemone", "assignment_method": "qcauto_target"},
        connection=positions,
    )
    assert result["source_occurrences"] == 4
    assert result["distinct_coordinate_pairs"] == 3
    fish = edna_location_summary(
        {
            "provider": "anemone",
            "taxon": "FIXTURE FISH",
            "exclude_explicit_controls": True,
        },
        connection=positions,
    )
    assert fish["source_occurrences"] == 2
    assert fish["distinct_coordinate_pairs"] == 1
    assay = edna_location_summary(
        {"assay_id": "a2", "taxon": "Fixture fish"}, connection=positions
    )
    assert assay["source_occurrences"] == assay["distinct_coordinate_pairs"] == 1
    empty_available = edna_location_summary(
        {"assignment_method": "qcauto_95pct_3nn_target"}, connection=positions
    )
    assert (
        empty_available["source_occurrences"]
        == empty_available["distinct_coordinate_pairs"]
        == 1
    )
    no_fish = edna_location_summary(
        {"assignment_method": "qcauto_95pct_3nn_target", "taxon": "Fixture fish"},
        connection=positions,
    )
    assert no_fish["source_occurrences"] == no_fish["distinct_coordinate_pairs"] == 0
    assert no_fish["coordinate_precision"] == {}
