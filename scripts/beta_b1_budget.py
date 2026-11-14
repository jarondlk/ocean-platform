"""Reconcile bounded B1 planning from captured provider meters and public prices.

This is a gross planning envelope, not an invoice or provider currency cap.
Only one new question/answer segment is considered; explicit continuation needs
new admission and reconciled usage. No cloud calls or credentials are used.
"""

import argparse
from datetime import datetime
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.beta_b0_preflight import require


def calculate(directory):
    def load(name):
        return json.loads((directory / name).read_text())
    usage, extra = load("usage-summary.json"), load("ancillary-summary.json")
    selected = {}
    for item in load("public-prices.json")["records"]:
        require(item["http_status"] == 200 and item["result"]["currencyCode"] == "JPY")
        defaults = [p for p in item["result"]["skuPrices"] if p["consumptionModelDescription"] == "Default"]
        require(len(defaults) == 1)
        rate = defaults[0]["rate"]
        amounts = [Decimal(str(t["listPrice"].get("units", "0"))) + Decimal(str(t["listPrice"].get("nanos", 0))) / 10**9
                   for t in rate["tiers"]]
        quantity = Decimal(rate["unitInfo"]["unitQuantity"]["value"])
        require(quantity.is_finite() and quantity > 0)
        selected[item["selection_name"]] = max(amounts) / quantity
    require(len(selected) == 31 and all(p.is_finite() and p >= 0 for p in selected.values()))
    metrics = {m["metric"]: m for m in usage["metrics"] + extra["metrics"]}
    require(all(m["all_pages_read"] is True and all(s["metric_kind"] == "DELTA"
                and Decimal(s["sum"]).is_finite() and Decimal(s["sum"]) >= 0 for s in m["series"]) for m in metrics.values()))
    sums = {name: sum((Decimal(s["sum"]) for s in m["series"]), Decimal(0)) for name, m in metrics.items()}
    require(all(x.is_finite() and x >= 0 for x in sums.values()))
    cpu = sums["run.googleapis.com/container/cpu/allocation_time"]
    ram = sums["run.googleapis.com/container/memory/allocation_time"]
    requests = sums["run.googleapis.com/request_count"]
    run = cpu * selected["run_request_cpu"] + ram * selected["run_request_ram"] + requests * selected["run_requests"]
    job_cpu = {s["resource"]["labels"]["job_name"]: Decimal(s["sum"])
               for s in metrics["run.googleapis.com/container/cpu/allocation_time"]["series"] if s["resource"]["type"] == "cloud_run_job"}
    job_ram = {s["resource"]["labels"]["job_name"]: Decimal(s["sum"])
               for s in metrics["run.googleapis.com/container/memory/allocation_time"]["series"] if s["resource"]["type"] == "cloud_run_job"}
    observer_count = load("observer-job.json")["status"]["executionCount"]
    require(type(observer_count) is int and 0 <= observer_count <= 20)
    minimums = []
    for name, seconds in job_cpu.items():
        count = observer_count if name == "ocean-v1-beta-provider-preflight-20261111" else 1
        memory = Decimal("1.25") if name in {"ocean-v1-beta-controller-credential", "ocean-v1-beta-research-grants"} else Decimal(".75")
        minimum = count * (120 * selected["run_request_cpu"] + 60 * memory * selected["run_request_ram"])
        metered = seconds * selected["run_request_cpu"] + job_ram[name] * selected["run_request_ram"]
        minimums.append({"job": name, "executions": count, "additional_jpy": str(max(Decimal(0), minimum - metered))})
    minimum = sum((Decimal(x["additional_jpy"]) for x in minimums), Decimal(0))
    class_b = {"ReadObject", "GetObjectMetadata", "GetBucketMetadata", "GetBucketStorageLayout", "GetIamPolicy"}
    a = b = Decimal(0)
    for s in metrics["storage.googleapis.com/api/request_count"]["series"]:
        if s["metric_labels"]["method"] in class_b:
            b += Decimal(s["sum"])
        else:
            a += Decimal(s["sum"])
    storage = a * selected["object_class_a"] + b * selected["object_class_b"]
    logging = max(sums["logging.googleapis.com/billing/bytes_ingested"], sums["logging.googleapis.com/byte_count"]) / 2**30 * selected["logging_ingestion"]
    build_total = Decimal(0)
    for build in load("builds.json"):
        require(build["status"] == "SUCCESS" and build["options"]["machineType"] == "E2_STANDARD_2")
        start = datetime.fromisoformat(build["startTime"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(build["finishTime"].replace("Z", "+00:00"))
        minutes = (Decimal(str((end - start).total_seconds())) / 60).to_integral_value(rounding=ROUND_CEILING)
        build_total += minutes * selected["build_e2_standard_2"]
    tokens = metrics["aiplatform.googleapis.com/publisher/online_serving/token_count"]["series"]
    input_tokens = sum((Decimal(s["sum"]) for s in tokens if s["metric_labels"]["type"] == "input"), Decimal(0))
    output_tokens = sum((Decimal(s["sum"]) for s in tokens if s["metric_labels"]["type"] == "output"), Decimal(0))
    calls = sums["aiplatform.googleapis.com/publisher/online_serving/model_invocation_count"]
    require((calls, input_tokens, output_tokens) == (2, 10599, 1004))
    model_observed = input_tokens * selected["gemini_3_8_flash_input"] + output_tokens * selected["gemini_3_8_flash_output"]
    network = sums["storage.googleapis.com/network/sent_bytes_count"] / 2**30 * selected["internet_worst_selected_destination"]
    observed = run + minimum + storage + logging + build_total + model_observed
    known = observed + network + 5
    # Same conservative UTF8-byte/schema/wrapper input bound as the accepted
    # shared-14-call audit. Combined output cap counts thought tokens once.
    model_input = 14 * (65536 + 1586 + 2048)
    model_output = 14 * 4096
    planning = model_input * selected["gemini_3_8_flash_input"] + model_output * selected["gemini_3_8_flash_output"]
    model_reserve = (planning / 5).to_integral_value(rounding=ROUND_CEILING) * 5
    rollout_reserve, observer_reserve = Decimal(20), Decimal(3)
    total = known + model_reserve + rollout_reserve + observer_reserve
    return {"version": "ocean-beta-b1-reservation-v1", "captured_utc": extra["captured_utc"],
            "currency": "JPY", "observed_incremental_gross_jpy": str(observed), "run_jpy": str(run),
            "job_minimums": minimums, "storage_operations_jpy": str(storage), "logging_jpy": str(logging),
            "build_allowance_jpy": str(build_total), "model_observed_jpy": str(model_observed),
            "all_storage_sent_bytes_worst_selected_internet_allowance_jpy": str(network),
            "ancillary_reserve_jpy": "5", "known_observed_and_reserved_jpy": str(known),
            "shared_call_cap": 14, "max_output_tokens_per_call_including_thoughts": 4096,
            "input_planning_tokens": model_input, "output_planning_tokens": model_output,
            "model_planning_jpy": str(planning), "one_question_model_reserve_jpy": str(model_reserve),
            "rollout_reserve_jpy": str(rollout_reserve), "two_observers_reserve_jpy": str(observer_reserve),
            "total_planned_jpy": str(total), "remaining_initial500_jpy": str(500 - total),
            "within_initial500": total <= 500, "new_questions_considered": 1,
            "new_question_already_submitted": False, "prior_questions": 3, "prior_model_calls": 2,
            "initial_validation_limit_jpy": 500, "monthly_beta_target_jpy": 50000,
            "provider_currency_hard_cap_or_invoice_claimed": False,
            "output_semantics_source": "https://ai.google.dev/gemini-api/docs/thinking#token-limits",
            "endpoint_qualification": "Planning applies the documented combined Gemini response/thought output cap to the same generateContent configuration on Vertex; it is not an independent provider billing guarantee.",
            "input_qualification": "Retains the prior one token per bounded UTF8 byte plus schema and2048 wrapper envelope; no provider countTokens proof is claimed.",
            "no_model_limits_or_scientific_authority_changed": True,
            "reconcile_actual_usage_before_next_question_or_continuation": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    result = calculate(args.directory)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["within_initial500"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
