from datetime import datetime, timedelta, timezone
import json
import sys

import pytest

from ingestion.immutable_bundle import digest
from preprocessing.historical_sst_matching import (
    preview_historical_matching,
    preview_relative_temperature_bins,
)
from scripts import preview_historical_sst_matching as cli


def observation(day, value=10.0, area="A"):
    row = {
        "area_id": area,
        "area_version": digest(area),
        "product_definition_id": digest("MUR"),
        "status": "valid",
        "sst_celsius": value,
        "time_utc": f"{day}T09:00:00+00:00",
        "granule_id": digest(day),
        "measurement_type": "satellite_in_situ_analysis",
        "temporal_statistic": "daily_foundation_analysis",
    }
    return {**row, "observation_id": digest(row)}


def member(label, when, area="A", **extra):
    return {
        "physical_sample_id": digest(label),
        "collection_time_utc": when,
        "area_id": area,
        "area_version": digest(area),
        **extra,
    }


def test_assumed_midday_japan_preserves_actual_source_day_and_gap():
    members = [
        member("date", None, temporal_precision="date", collection_date="2021-02-20")
    ]
    result = preview_historical_matching(
        members, [observation("2021-02-19")], digest("panel")
    )
    link = result["links"][0]
    assert link["collection_time_basis"] == "assumed_midday_Asia_Tokyo"
    assert link["original_reported_date"] == "2021-02-20"
    assert link["source_japan_date"] == "2021-02-19"
    assert link["time_difference_hours"] == 18
    assert link["window_used_hours"] == 24
    assert result["scientific_publication"] is False


def test_only_temporal_misses_trigger_bounded_extension():
    members = [
        member("near", "2021-02-20T03:00:00Z"),
        member("late", "2021-02-21T03:00:00Z"),
        member("far", "2021-02-24T03:00:00Z"),
        member("bad-clock", "not-a-time"),
        member("no-area", "2021-02-20T03:00:00Z", area="B"),
    ]
    result = preview_historical_matching(
        members, [observation("2021-02-19")], digest("panel")
    )
    assert result["coverage"]["otherwise_linkable_collections"] == 3
    assert result["coverage"][
        "temporal_unmatched_fraction_at_24_hours"
    ] == pytest.approx(2 / 3)
    assert result["coverage"]["matched_within_extended_48_hours"] == 1
    link = next(r for r in result["links"] if r["physical_sample_id"] == digest("late"))
    assert link["extended_window"] is True and link["time_difference_hours"] == 42
    assert {r["status"] for r in result["unmatched"]} == {
        "sst_unavailable",
        "collection_time_unresolved",
        "sst_area_support_unavailable",
    }


def test_twenty_percent_exactly_does_not_extend():
    members = [member(str(i), "2021-02-20T03:00:00Z") for i in range(4)]
    members.append(member("late", "2021-02-21T03:00:00Z"))
    result = preview_historical_matching(
        members, [observation("2021-02-19")], digest("panel")
    )
    assert result["coverage"]["temporal_unmatched_fraction_at_24_hours"] == 0.2
    assert result["coverage"]["extension_applied"] is False
    assert len(result["links"]) == 4


def test_unsupported_areas_and_invalid_clocks_never_force_extension():
    result = preview_historical_matching([member("missing", None)], [], digest("panel"))
    assert result["coverage"]["temporal_unmatched_fraction_at_24_hours"] is None
    assert result["coverage"]["extension_applied"] is False
    with pytest.raises(ValueError, match="Duplicate"):
        preview_historical_matching([member("same", None)] * 2, [], digest("panel"))


def test_relative_bins_are_region_season_specific_and_fish_independent():
    rows = [
        observation("2021-02-01", 1.0),
        observation("2021-02-02", 2.0),
        observation("2021-02-03", 3.0),
        observation("2021-08-01", 25.0),
        observation("2021-02-01", 12.0, area="B"),
    ]
    result = preview_relative_temperature_bins(rows)
    winter = next(
        p for p in result["partitions"] if p["area_id"] == "A" and p["season"] == "DJF"
    )
    assert {d["category"] for d in winter["daily_bins"]} == {"low", "middle", "high"}
    assert winter["low_max_celsius"] == pytest.approx(5 / 3)
    assert winter["high_min_celsius"] == pytest.approx(7 / 3)
    assert winter["warnings"] == ["short_baseline"]
    assert len(result["partitions"]) == 3
    assert result["baseline_is_long_term_climatology"] is False


def test_relative_bins_reject_duplicate_days_and_changed_provenance():
    row = observation("2021-02-01")
    with pytest.raises(ValueError, match="identity"):
        preview_relative_temperature_bins([row, row])
    changed = {**row, "sst_celsius": 15.0}
    with pytest.raises(ValueError, match="identity"):
        preview_relative_temperature_bins([changed])
    another = {**row, "granule_id": digest("other")}
    another["observation_id"] = digest(
        {k: v for k, v in another.items() if k != "observation_id"}
    )
    with pytest.raises(ValueError, match="Duplicate regional"):
        preview_relative_temperature_bins([row, another])


def test_identical_values_stay_unpartitioned_with_japan_date_grouping():
    row = observation("2020-11-30")
    row["time_utc"] = "2020-11-30T18:00:00Z"  # December 1 in Japan.
    row["observation_id"] = digest(
        {k: v for k, v in row.items() if k != "observation_id"}
    )
    result = preview_relative_temperature_bins([row])
    assert result["partitions"][0]["season"] == "DJF"
    assert result["partitions"][0]["baseline_from"] == "2020-12-01"
    assert result["partitions"][0]["daily_bins"][0]["category"] == "unpartitioned_ties"


def test_relative_baseline_uses_all_days_not_sampled_positive_subset():
    start = datetime(2020, 5, 1, tzinfo=timezone.utc)
    rows = [
        observation((start + timedelta(days=i)).date().isoformat(), float(i))
        for i in range(30)
    ]
    result = preview_relative_temperature_bins(rows)
    assert result["partitions"][0]["supported_days"] == 30
    assert result["partitions"][0]["warnings"] == []


@pytest.mark.parametrize("value", [True, float("nan"), -10.0, 60.0])
def test_matching_rejects_invalid_temperature_even_if_rehashed(value):
    with pytest.raises(ValueError, match="Invalid matching SST|JSON compliant"):
        preview_historical_matching(
            [], [observation("2021-02-01", value)], digest("panel")
        )


def test_matching_keeps_source_quality_warnings():
    row = observation("2021-02-01")
    row["warnings"] = ["missing_ice_fraction_open_sea_mask_used"]
    row["observation_id"] = digest(
        {k: v for k, v in row.items() if k != "observation_id"}
    )
    result = preview_historical_matching(
        [member("water", "2021-02-01T09:00:00Z")], [row], digest("panel")
    )
    assert result["links"][0]["source_warnings"] == row["warnings"]


def test_cli_content_binding_and_input_preservation(tmp_path, monkeypatch):
    members, observations, output = (
        tmp_path / name for name in ("members.json", "observations.json", "result.json")
    )
    source_members = [member("water", "2021-02-01T09:00:00Z")]
    source_observations = [observation("2021-02-01")]
    members.write_text(json.dumps(source_members))
    observations.write_text(json.dumps(source_observations))
    args = [
        "preview",
        "--members",
        str(members),
        "--observations",
        str(observations),
        "--panel-id",
        digest("panel"),
        "--output",
        str(output),
    ]
    monkeypatch.setattr(sys, "argv", args)
    cli.main()
    result = json.loads(output.read_text())
    assert result["source_members_sha256"] == digest(source_members)
    assert result["source_observations_sha256"] == digest(source_observations)
    assert result["matching"]["coverage"]["matched_within_24_hours"] == 1
    assert result["scientific_publication"] is False
    args[-1] = str(members)
    with pytest.raises(SystemExit):
        cli.main()
    assert json.loads(members.read_text()) == source_members


def test_cli_output_symlink_ancestor_rejected(tmp_path, monkeypatch):
    folder = tmp_path / "actual"
    folder.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(folder, target_is_directory=True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "preview",
            "--members",
            str(tmp_path / "members.json"),
            "--observations",
            str(tmp_path / "observations.json"),
            "--panel-id",
            digest("panel"),
            "--output",
            str(alias / "result.json"),
        ],
    )
    with pytest.raises(SystemExit):
        cli.main()
    assert not (folder / "result.json").exists()
