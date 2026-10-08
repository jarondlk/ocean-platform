from copy import deepcopy
import json

import pytest

from ingestion.immutable_bundle import digest
from ingestion.sst_context_integration import stage_context_batch
from preprocessing.historical_sst_period import build_period_preview, period_batches
from preprocessing.sst_context_review import build_context_diagnostics
from scripts.prepare_historical_sst_period import prepare_period
from tests.test_sst_context_integration import stage_args


QUALITY = {
    "max_analysis_error_k": 1.0,
    "max_sea_ice_fraction": 0.15,
    "min_valid_ocean_fraction": 0.8,
    "min_valid_ocean_points": 5,
    "weighting": "cosine_latitude_grid_point_approximation",
    "missing_ice_policy": "use_open_sea_mask_with_warning",
}


@pytest.fixture
def data(tmp_path):
    args = stage_args(tmp_path)
    staging = stage_context_batch(*args)
    diagnostic = build_context_diagnostics(
        args[0], args[1], staging, proposed_quality=QUALITY
    )
    return args, diagnostic


def test_complete_calendar_preserves_gaps_and_sparse_support(data):
    args, diagnostic = data
    result = build_period_preview(args[0], args[1], [diagnostic], "demo", 2020, 2020)
    assert result["period_preview_id"] == digest(
        {k: v for k, v in result.items() if k != "period_preview_id"}
    )
    assert len(result["observations"]) == 2
    assert len(result["final_series_gaps"]) == 364
    assert result["year_coverage"]["2020"]["supported_days"] == 0
    assert all(r["sst_celsius"] is None for r in result["observations"])
    assert result["scientific_approval"] is False
    assert result["scientific_publication"] is False
    assert result["native_sample_area_evidence"] is False


@pytest.mark.parametrize(
    "kind", ["missing", "duplicate", "source", "calendar", "numeric", "approval"]
)
def test_cannot_assert_completion_with_incomplete_or_changed_inputs(data, kind):
    args, diagnostic = data
    values = [deepcopy(diagnostic)]
    if kind == "missing":
        values = []
    elif kind == "duplicate":
        values *= 2
    elif kind == "source":
        values[0]["source_report_id"] = "f" * 64
    elif kind == "calendar":
        values[0]["daily"].pop()
    elif kind == "numeric":
        values[0]["daily"][0]["proposed_quality_preview"]["sst_celsius"] = 10.0
    else:
        values[0]["scientific_approval"] = True
        values[0]["diagnostics_id"] = digest(
            {k: v for k, v in values[0].items() if k != "diagnostics_id"}
        )
    with pytest.raises(ValueError):
        build_period_preview(args[0], args[1], values, "demo", 2020, 2020)


def test_outside_archive_period_is_not_reported_as_complete(data):
    args, _ = data
    with pytest.raises(ValueError, match="full period"):
        period_batches(args[0], args[1], 2019, 2020)
    with pytest.raises(ValueError, match="ordered"):
        period_batches(args[0], args[1], 2021, 2020)


def test_resume_uses_verified_cached_raw_and_rejects_corruption(data, tmp_path):
    args, _ = data
    arguments = dict(
        area_id="demo",
        first_year=2020,
        last_year=2020,
        bounds=args[2]["context_footprint"],
        quality=QUALITY,
    )
    root = tmp_path / "period"
    first = prepare_period(args[0], args[1], args[3], root, **arguments)

    def no_archive_read(*args, **kwargs):
        raise AssertionError("Resume must use verified local raw rather than reacquire")

    again = prepare_period(
        args[0], args[1], args[3], root, store_factory=no_archive_read, **arguments
    )
    assert first == again
    assert first["provider_downloads"] is False
    raw = next((root / "packages").glob("*/*.nc"))
    raw.write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        prepare_period(
            args[0], args[1], args[3], root, store_factory=no_archive_read, **arguments
        )


def test_unsafe_cached_receipt_path_is_rejected(data, tmp_path):
    args, _ = data
    arguments = dict(
        area_id="demo",
        first_year=2020,
        last_year=2020,
        bounds=args[2]["context_footprint"],
        quality=QUALITY,
    )
    root = tmp_path / "period"
    prepare_period(args[0], args[1], args[3], root, **arguments)
    path = next(root.glob("*/*.staging.json"))
    receipt = json.loads(path.read_bytes())
    receipt["package_path"] = str(tmp_path / "other" / receipt["batch_id"])
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="escaped"):
        prepare_period(args[0], args[1], args[3], root, **arguments)
