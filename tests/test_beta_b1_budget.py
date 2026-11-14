"""Budget refusal cases use captured price units with synthetic usage, no cloud."""

from decimal import Decimal
import json

import pytest

from scripts import beta_b1_budget as budget
from scripts.beta_b0_preflight import ROOT, Rejected


@pytest.fixture
def captures(tmp_path):
    source = json.loads((ROOT / "docs/plans/ocean-v1/beta/b0-20261114/selected-prices.json").read_text())["selection"]
    records = []
    for name, price in source.items():
        value = Decimal(price["normalized_jpy_per_unit"])
        units = int(value)
        nanos = int((value - units) * 10**9)
        records.append({"selection_name": name, "http_status": 200, "result": {"currencyCode": "JPY",
            "skuPrices": [{"consumptionModelDescription": "Default", "rate": {
                "tiers": [{"listPrice": {"units": str(units), "nanos": nanos}}],
                "unitInfo": {"unitQuantity": {"value": "1"}}}}]}})
    def meter(name, values):
        return {"metric": name, "all_pages_read": True, "series": [
            {"sum": str(v), "metric_kind": "DELTA", "resource": {"type": "cloud_run_revision"}, "metric_labels": labels}
            for v, labels in values]}
    metrics = [meter("run.googleapis.com/container/cpu/allocation_time", [(1, {})]),
               meter("run.googleapis.com/container/memory/allocation_time", [(1, {})]),
               meter("run.googleapis.com/request_count", [(1, {})]),
               meter("aiplatform.googleapis.com/publisher/online_serving/token_count", [(10599, {"type": "input"}), (1004, {"type": "output"})]),
               meter("aiplatform.googleapis.com/publisher/online_serving/model_invocation_count", [(2, {})])]
    ancillary = [meter(n, []) for n in ["logging.googleapis.com/billing/bytes_ingested", "logging.googleapis.com/byte_count",
                                      "storage.googleapis.com/api/request_count", "storage.googleapis.com/network/sent_bytes_count"]]
    data = {"public-prices.json": {"records": records}, "usage-summary.json": {"metrics": metrics},
            "ancillary-summary.json": {"captured_utc": "2026-11-14T08:00:00Z", "metrics": ancillary},
            "observer-job.json": {"status": {"executionCount": 3}}, "builds.json": []}
    for name, d in data.items():
        (tmp_path / name).write_text(json.dumps(d))
    return tmp_path


def test_one_segment_uses_shared_cap_and_combined_output_once(captures):
    result = budget.calculate(captures)
    assert result["shared_call_cap"] == 14
    assert result["output_planning_tokens"] == 14 * 4096
    assert result["input_planning_tokens"] == 968380
    assert result["new_questions_considered"] == 1 and not result["new_question_already_submitted"]
    assert result["within_initial500"]


def test_overspend_is_not_admitted(captures):
    p = captures / "usage-summary.json"
    data = json.loads(p.read_text())
    data["metrics"][0]["series"][0]["sum"] = "1000000"
    p.write_text(json.dumps(data))
    result = budget.calculate(captures)
    assert not result["within_initial500"] and Decimal(result["remaining_initial500_jpy"]) < 0


def test_completed_observers_are_reconciled_separately_from_future_reserve(captures):
    two, one = budget.calculate(captures), budget.calculate(captures, future_observers=1)
    assert one["known_observed_and_reserved_jpy"] == two["known_observed_and_reserved_jpy"]
    assert Decimal(two["total_planned_jpy"]) - Decimal(one["total_planned_jpy"]) == Decimal("1.5")
    assert one["future_observers"] == 1 and one["future_observers_reserve_jpy"] == "1.5"


@pytest.mark.parametrize("value", [-1, 3, True, "1"])
def test_invalid_future_observer_reservation_rejected(captures, value):
    with pytest.raises(Rejected):
        budget.calculate(captures, future_observers=value)


@pytest.mark.parametrize("target", ["missing_page", "gauge", "negative", "changed_calls", "currency", "free_nondefault"])
def test_incomplete_or_changed_meter_basis_rejected(captures, target):
    path = captures / ("public-prices.json" if target in {"currency", "free_nondefault"} else "usage-summary.json")
    data = json.loads(path.read_text())
    if target == "missing_page":
        data["metrics"][0]["all_pages_read"] = False
    elif target == "gauge":
        data["metrics"][0]["series"][0]["metric_kind"] = "GAUGE"
    elif target == "negative":
        data["metrics"][0]["series"][0]["sum"] = "-1"
    elif target == "changed_calls":
        data["metrics"][-1]["series"][0]["sum"] = "3"
    elif target == "currency":
        data["records"][0]["result"]["currencyCode"] = "USD"
    else:
        data["records"][0]["result"]["skuPrices"][0]["consumptionModelDescription"] = "Discounted"
    path.write_text(json.dumps(data))
    with pytest.raises(Rejected):
        budget.calculate(captures)
