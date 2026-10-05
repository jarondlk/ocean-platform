from copy import deepcopy
from datetime import date

import pytest
from pydantic import ValidationError

from ingestion.immutable_bundle import digest
from ingestion.research_readiness import build_readiness
from preprocessing.edna_detection_frequency import (
    build_detection_frequency,
    registry_versions,
    season,
)
from preprocessing.research_recipe import DetectionFrequencyRecipe, PhysicalMembership
from tests.research_fixtures import h, research_fixture


def calculate(fixture):
    recipe, source, areas, memberships, links, _ = fixture
    return build_detection_frequency(recipe, source, areas, memberships, links)


def test_hand_calculated_endpoint_and_spatial_results():
    f = research_fixture()
    tables = calculate(f)
    sardine = f[-1]["Sardinops melanostictus"]
    series = [
        r
        for r in tables["series"]
        if r["taxon_key"] == sardine and r["period_kind"] == "year"
    ]
    endpoint = {r["period"]: r for r in series}
    assert (
        endpoint["2020"]["detected"],
        endpoint["2020"]["eligible"],
        endpoint["2020"]["frequency"],
    ) == (3, 6, 0.5)
    assert (
        endpoint["2023"]["detected"],
        endpoint["2023"]["eligible"],
        endpoint["2023"]["frequency"],
    ) == (3, 6, 0.5)
    spatial = {r["area_id"]: r for r in tables["spatial"]}
    assert (
        spatial["A"]["detected"] == 0
        and spatial["A"]["eligible"] == 3
        and spatial["A"]["frequency"] == 0
    )
    assert spatial["A"]["sampling_status"] == "sampled_not_detected"
    assert spatial["B"]["frequency"] == 1
    assert (
        spatial["C"]["frequency"] is None
        and spatial["C"]["sampling_status"] == "unsampled"
    )
    assert [r["month"] for r in tables["month_coverage"] if r["selected"]] == [
        "2023-05"
    ]
    ranking = tables["change_ranking"]
    assert ranking[0]["taxon_key"] == sardine
    assert ranking[0]["mean_absolute_change_percentage_points"] == pytest.approx(
        200 / 3
    )
    changes = {r["area_id"]: r for r in tables["changes"] if r["taxon_key"] == sardine}
    assert changes["A"]["difference_percentage_points"] == pytest.approx(-200 / 3)
    assert changes["B"]["difference_percentage_points"] == pytest.approx(200 / 3)
    middle = {
        (r["area_id"], r["year"]): r
        for r in tables["follow_through"]
        if r["taxon_key"] == sardine
    }
    assert middle[("B", 2021)]["frequency"] is None
    assert middle[("B", 2022)]["frequency"] == 0
    assert middle[("A", 2021)]["low_support"] is True


def test_temperature_uses_matched_denominator_and_frozen_representative():
    tables = calculate(research_fixture())
    sardine = research_fixture()[-1]["Sardinops melanostictus"]
    bins = {
        r["bin"]: r for r in tables["temperature_bins"] if r["taxon_key"] == sardine
    }
    assert (bins["low"]["detected"], bins["low"]["eligible"]) == (3, 6)
    assert (bins["high"]["detected"], bins["high"]["eligible"]) == (3, 6)
    assert (
        bins["low"]["all_edna_eligible"] == 15 and bins["low"]["sst_unavailable"] == 3
    )
    representative = [r for r in tables["temperature_contrasts"] if r["representative"]]
    assert len(representative) == 1
    assert (
        representative[0]["taxon_key"] == research_fixture()[-1]["Engraulis japonicus"]
    )
    assert representative[0]["difference_percentage_points"] == pytest.approx(100 / 3)
    spatial = {
        r["area_id"]: r
        for r in tables["spatial_temperature_bins"]
        if r["bin"] == "high"
    }
    assert set(spatial) == {"A", "B", "C"}
    assert {r["taxon_key"] for r in spatial.values()} == {sardine}
    assert (
        spatial["A"]["detected"],
        spatial["A"]["eligible"],
        spatial["A"]["frequency"],
    ) == (0, 3, 0)

    assert (
        spatial["B"]["detected"],
        spatial["B"]["eligible"],
        spatial["B"]["frequency"],
    ) == (3, 3, 1)
    assert spatial["C"]["frequency"] is None
    assert spatial["A"]["sample_time_sst_mean_celsius"] == 20


def test_temperature_comparison_retains_the_q1_top_ten_candidate_list():
    f = research_fixture()
    source = f[1]
    for assay in source["edna_assay"]:
        for number in range(10):
            source["edna_detection"].append(
                {
                    "detection_id": h(assay["assay_id"] + str(number)),
                    "assay_id": assay["assay_id"],
                    "assignment_method": f[0].assignment_method,
                    "read_count": 1,
                    "class": "Actinopterygii",
                    "genus": "Fixturefish",
                    "species": f"Fixturefish common{number}",
                }
            )
        assay["community_availability_json"][f[0].assignment_method]["row_count"] += 10
    tables = calculate(f)
    top_keys = {r["taxon_key"] for r in tables["ranking"]}
    assert len(top_keys) == 10
    assert f[-1]["Engraulis japonicus"] not in top_keys
    assert (
        sum(r["species"].startswith("Fixturefish common") for r in tables["ranking"])
        >= 9
    )
    contrasts = tables["temperature_contrasts"]
    assert {r["taxon_key"] for r in contrasts} == top_keys
    assert all(r["difference_percentage_points"] == 0 for r in contrasts)
    assert {r["taxon_key"] for r in tables["temperature_series"]} <= top_keys


def test_duplicate_occurrence_is_not_duplicate_sample_or_positive_selection():
    recipe, source, areas, memberships, links, keys = research_fixture()
    # Another source occurrence has positive reads, but the reviewed original
    # assay remains the representative. That occurrence cannot add a numerator.
    original = memberships[6]
    sample = deepcopy(source["edna_sample"][6])
    sample["sample_id"] = h("resequenced")
    assay = deepcopy(source["edna_assay"][6])
    assay.update(assay_id=h("resequenced-assay"), sample_id=sample["sample_id"])
    source["edna_sample"].append(sample)
    source["edna_assay"].append(assay)
    source["edna_detection"].append(
        dict(
            detection_id=h("positive-resequence"),
            assay_id=assay["assay_id"],
            assignment_method="qcauto_target",
            read_count=100,
            **{"class": "Actinopterygii"},
            genus="Sardinops",
            species="Sardinops melanostictus",
        )
    )
    data = original.model_dump(mode="json")
    data["occurrences"].append(
        dict(
            sample_id=sample["sample_id"],
            scientific_content_sha256=sample["scientific_content_sha256"],
        )
    )
    memberships[6] = PhysicalMembership.model_validate(data)
    recipe = DetectionFrequencyRecipe.model_validate(
        {**recipe.model_dump(mode="json"), **registry_versions(areas, memberships)}
    )
    tables = build_detection_frequency(recipe, source, areas, memberships, links)
    a = next(r for r in tables["spatial"] if r["area_id"] == "A")
    assert (a["detected"], a["eligible"]) == (0, 3)
    assert len(tables["membership"]) == 15


def test_stale_and_unknown_identity_exclusions_are_explicit():
    recipe, source, areas, memberships, links, _ = research_fixture()
    source["edna_sample"][0]["scientific_content_sha256"] = h("changed-evidence")
    source["edna_sample"].append(
        dict(sample_id=h("unknown"), sample_kind="unknown", is_control=None)
    )
    links = [
        r for r in links if r["physical_sample_id"] != memberships[0].physical_sample_id
    ]
    tables = build_detection_frequency(recipe, source, areas, memberships, links)
    reasons = [reason for r in tables["exclusions"] for reason in r["reasons"]]
    assert (
        "stale_identity_evidence" in reasons
        and "unreviewed_physical_identity" in reasons
    )
    assert len(tables["membership"]) == 14
    assert len(tables["matched_panel"]) == 1  # A endpoint fell below support.


def test_methods_are_separate_and_method_completeness_is_required():
    f = research_fixture()
    primary = calculate(f)
    alternate = DetectionFrequencyRecipe.model_validate(
        {**f[0].model_dump(mode="json"), "assignment_method": "qcauto_95pct_3nn_target"}
    )
    tables = build_detection_frequency(alternate, *f[1:5])
    assert [(r["detected"], r["eligible"]) for r in primary["ranking"]] == [
        (r["detected"], r["eligible"]) for r in tables["ranking"]
    ]
    f[1]["edna_detection"].pop(0)
    with pytest.raises(ValueError, match="does not reconcile"):
        calculate(f)


def test_recipe_and_link_fail_closed():
    f = research_fixture()
    with pytest.raises(ValidationError):
        DetectionFrequencyRecipe.model_validate(
            {**f[0].model_dump(mode="json"), "assignment_methods": ["qcauto_target"]}
        )
    f[4][0]["sst_celsius"] = float("nan")
    with pytest.raises(ValueError, match="Invalid or untraceable"):
        calculate(f)
    f = research_fixture()
    f[1]["generations"]["canonical_generation"] = h("other")
    with pytest.raises(ValueError, match="canonical_generation mismatch"):
        calculate(f)


def test_calendar_edges_and_determinism():
    assert season(date(2020, 12, 31)) == (2021, "DJF")
    assert season(date(2021, 1, 1)) == (2021, "DJF")
    f = research_fixture()
    first = calculate(f)
    for name in ("edna_sample", "edna_assay", "edna_detection"):
        f[1][name].reverse()
    f[2].reverse()
    f[3].reverse()
    f[4].reverse()
    assert digest(calculate(f)) == digest(first)
    assert all(
        r["partial_period"] for r in first["series"] if r["period"] == "2020-DJF"
    )


def test_readiness_never_approves_physical_identity():
    source = {
        "edna_sample": [
            dict(
                sample_id=h("x"),
                sample_kind="unknown",
                physical_sample_id=h("y"),
                identity_status="unreviewed",
                collection_date_utc="2020-12-31T16:00:00Z",
                temporal_precision="datetime",
                raw_metadata_json={"worldmesh": "test"},
            )
        ],
        "edna_assay": [],
    }
    report = build_readiness(source, {"candidate_id": h("candidate")})
    assert report["coverage"][0]["month"] == "2021-01"
    assert report["counts"]["environmental_occurrences"] == 0
    assert len(report["case_dispositions"]) == 6
    assert all(r["status"] == "data_blocked" for r in report["case_dispositions"])


@pytest.mark.parametrize("value", [True, "3", 3.5])
def test_numeric_recipe_thresholds_do_not_silently_coerce(value):
    from pydantic import ValidationError
    from preprocessing.research_recipe import DetectionFrequencyRecipe

    recipe = research_fixture()[0]
    with pytest.raises(ValidationError):
        DetectionFrequencyRecipe.model_validate(
            {**recipe.model_dump(mode="json"), "min_stratum_samples": value}
        )
