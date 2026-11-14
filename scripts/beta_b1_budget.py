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


def _calculate(directory, *, future_observers=2, terminal_report=None):
    require(type(future_observers) is int and 0 <= future_observers <= 2)
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
    if terminal_report is None:
        require((calls, input_tokens, output_tokens) == (2, 10599, 1004))
    else:
        require(terminal_report['version'] == 'ocean-beta-b1-q5-diagnostic-v1'
                and terminal_report['state'] == 'read_only_diagnostic_verified'
                and terminal_report['transaction_read_only_verified'] is True
                and terminal_report['proxy_shutdown_verified'] is True
                and terminal_report['run_id'] == '6e09ea49-b2bd-40ac-a457-b16709912f1d'
                and terminal_report['answer_job_id'] == 'bb9994e4-c678-4fc3-a59c-97adf0563e13')
        head = terminal_report['head']
        require(head['status'] == 'unavailable' and head['run_status'] == 'completed'
                and head['lease_closed'] is True and head['run_lease_closed'] is True
                and type(head['model_calls']) is int and head['model_calls'] == 2 and calls == 4)
        groups = terminal_report['generations']
        require(set(groups) == {'research_run', 'research_answer'} and all(len(v) == 1 for v in groups.values()))
        ceiling_inputs, ceiling_outputs = 10599, 1004
        for values in groups.values():
            step = values[0]
            require(step['state'] == 'committed' and step['payload_hash_verified'] is True
                    and type(step['physical_attempts']) is int and step['physical_attempts'] == 1)
            for name, cap in [('input_tokens', 65536 + 1586 + 2048), ('output_tokens', 4096), ('total_tokens', 65536 + 1586 + 2048 + 4096)]:
                value = step['usage'].get(name)
                require(value is None or type(value) is int and 0 <= value <= cap)
            ceiling_inputs += step['usage']['input_tokens'] if step['usage']['input_tokens'] is not None else 65536 + 1586 + 2048
            # candidates_token_count alone excludes thought tokens. Derive the
            # combined output from total-input only when both exist, otherwise
            # retain the full combined output cap, even on a completed step.
            total, inputs = step['usage'].get('total_tokens'), step['usage']['input_tokens']
            combined = 4096 if total is None or inputs is None else total - inputs
            require(0 <= combined <= 4096)
            ceiling_outputs += max(combined, step['usage']['output_tokens'] or 0)
        require(input_tokens >= 10599 and output_tokens >= 1004)
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
    if terminal_report is not None:
        # Closed physical attempts have no automatic future continuation. Missing
        # provider usage is still bounded in full; it never becomes a free call.
        input_ceiling = max(input_tokens, Decimal(ceiling_inputs))
        output_ceiling = max(output_tokens, Decimal(ceiling_outputs))
        ceiling_cost = input_ceiling * selected['gemini_3_8_flash_input'] + output_ceiling * selected['gemini_3_8_flash_output']
        model_reserve = max(Decimal(0), ceiling_cost - model_observed)
    rollout_reserve, observer_reserve = Decimal(20), Decimal("1.5") * future_observers
    total = known + model_reserve + rollout_reserve + observer_reserve
    result = {"version": "ocean-beta-b1-reservation-v2", "captured_utc": extra["captured_utc"],
            "currency": "JPY", "observed_incremental_gross_jpy": str(observed), "run_jpy": str(run),
            "job_minimums": minimums, "storage_operations_jpy": str(storage), "logging_jpy": str(logging),
            "build_allowance_jpy": str(build_total), "model_observed_jpy": str(model_observed),
            "all_storage_sent_bytes_worst_selected_internet_allowance_jpy": str(network),
            "ancillary_reserve_jpy": "5", "known_observed_and_reserved_jpy": str(known),
            "shared_call_cap": 14, "max_output_tokens_per_call_including_thoughts": 4096,
            "input_planning_tokens": model_input, "output_planning_tokens": model_output,
            "model_planning_jpy": str(planning), "one_question_model_reserve_jpy": str(model_reserve),
            "rollout_reserve_jpy": str(rollout_reserve), "future_observers": future_observers,
            "future_observers_reserve_jpy": str(observer_reserve),
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
    if terminal_report is not None:
        result.update(version='ocean-beta-b1-q5-terminal-reconciliation-v1',
            new_questions_considered=0, new_question_already_submitted=True,
            native_model_calls=str(calls), native_input_tokens=str(input_tokens), native_output_tokens=str(output_tokens),
            terminal_physical_attempts=2, input_planning_tokens=str(input_ceiling), output_planning_tokens=str(output_ceiling),
            model_planning_jpy=str(ceiling_cost), one_question_model_reserve_jpy='0',
            missing_usage_reserve_jpy=str(model_reserve), initial_validation_limit_jpy=550,
            remaining_initial550_jpy=str(550-total), within_initial550=total <= 550,
            prior_questions=3, manual_questions_submitted=5, new_paid_question_admitted=False,
            terminal_diagnostic_captured_utc=terminal_report['captured_utc'])
    return result


def calculate(directory, *, future_observers=2):
    """Original pre-submission estimator, preserving its strict meter baseline."""
    return _calculate(directory, future_observers=future_observers)


def reconcile_terminal(directory, report, *, future_observers=0):
    """Reconcile closed Q5 attempts; this cannot admit another model segment."""
    return _calculate(directory, future_observers=future_observers, terminal_report=report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--future-observers", type=int, choices=(0, 1, 2), default=2)
    args = parser.parse_args()
    result = calculate(args.directory, future_observers=args.future_observers)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["within_initial500"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
