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


@pytest.fixture
def terminal(captures):
    p = captures / 'usage-summary.json'
    data = json.loads(p.read_text())
    data['metrics'][-1]['series'][0]['sum'] = '4'
    p.write_text(json.dumps(data))
    step = {'state': 'committed', 'payload_hash_verified': True, 'physical_attempts': 1,
            'usage': {'input_tokens': None, 'output_tokens': None}}
    return {'version': 'ocean-beta-b1-q5-diagnostic-v1', 'state': 'read_only_diagnostic_verified',
            'transaction_read_only_verified': True, 'proxy_shutdown_verified': True,
            'run_id': '6e09ea49-b2bd-40ac-a457-b16709912f1d',
            'answer_job_id': 'bb9994e4-c678-4fc3-a59c-97adf0563e13',
            'head': {'status': 'unavailable', 'run_status': 'completed', 'lease_closed': True,
                     'run_lease_closed': True, 'model_calls': 2},
            'generations': {'research_run': [step], 'research_answer': [step]},
            'captured_utc': '2026-11-14T17:00:00Z'}


def test_closed_segment_never_invents_missing_usage_or_admits_a_retry(captures, terminal):
    result = budget.reconcile_terminal(captures, terminal)
    assert result['input_planning_tokens'] == str(10599 + 2 * (65536 + 1586 + 2048))
    assert result['output_planning_tokens'] == str(1004 + 2 * 4096)
    assert Decimal(result['missing_usage_reserve_jpy']) > 0
    assert result['new_questions_considered'] == 0 and result['one_question_model_reserve_jpy'] == '0'
    assert result['new_paid_question_admitted'] is False and result['within_initial550']
    with pytest.raises(Rejected):
        budget.calculate(captures)  # Original pre-submit contract stays strict.


@pytest.mark.parametrize('change', ['active', 'identity', 'corrupt', 'attempts', 'bool_usage', 'negative_usage'])
def test_terminal_reconciliation_requires_exact_closed_known_attempts(captures, terminal, change):
    if change == 'active':
        terminal['head']['lease_closed'] = False
    elif change == 'identity':
        terminal['run_id'] = 'other'
    elif change == 'corrupt':
        terminal['generations']['research_answer'][0]['payload_hash_verified'] = False
    elif change == 'attempts':
        terminal['generations']['research_answer'][0]['physical_attempts'] = 2
    else:
        terminal['generations']['research_answer'][0]['usage']['input_tokens'] = True if change == 'bool_usage' else -1
    with pytest.raises(Rejected):
        budget.reconcile_terminal(captures, terminal)


def test_synthetic_probe_reconciliation_keeps_failed_request_bounded(captures, terminal):
    p = captures / 'usage-summary.json'
    data = json.loads(p.read_text())
    data['metrics'][-1]['series'][0]['sum'] = '6'
    p.write_text(json.dumps(data))
    probes = [{'variant': 'original', 'http_status': 400, 'usage': None,
               'no_beta_history_or_scientific_data_used': True},
              {'variant': 'array_bounds_removed', 'http_status': 200,
               'usage': {'promptTokenCount': 585, 'totalTokenCount': 672},
               'no_beta_history_or_scientific_data_used': True}]
    result = budget.reconcile_terminal(captures, terminal, engineering_reports=probes)
    assert result['terminal_physical_attempts'] == 4
    assert result['input_planning_tokens'] == str(10599 + 2 * (65536 + 1586 + 2048) + 14048 + 585)
    assert result['output_planning_tokens'] == str(1004 + 2 * 4096 + 4096 + 87)
    probes[1]['usage']['totalTokenCount'] = 585 + 4097
    with pytest.raises(Rejected):
        budget.reconcile_terminal(captures, terminal, engineering_reports=probes)
