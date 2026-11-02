"""Build deterministic, credential-free quote arithmetic from captured public records."""

from __future__ import annotations
from decimal import Decimal
import json
from pathlib import Path

D = Decimal
DIRECTORY = Path(__file__).resolve().parent
INPUTS = [
    "catalogue-candidates.json",
    "catalogue-supplement.json",
    "catalogue-compute-network.json",
]
SELECTED = {
    "sql_cpu": "D34E-ED22-3AA3",
    "sql_ram": "9AE6-50FF-E3A7",
    "sql_ssd": "A593-7E26-0880",
    "sql_backups": "F8BE-1CC3-FDF3",
    "worker_cpu": "EAED-8A05-843B",
    "worker_ram": "CB4B-B875-93B4",
    "worker_balanced_disk": "6D8C-DF09-314D",
    "global_https_forwarding_minimum": "DEE3-C42E-3E4D",
    "lb_inbound_tokyo": "4445-66EE-8E07",
    "lb_outbound_tokyo": "86C9-AD43-1809",
    "unused_regional_ipv4_reference": "7A91-88CA-899A",
    "standard_vm_ipv4": "C054-7F72-A02E",
    "run_request_cpu": "4856-B847-F1EB",
    "run_request_ram": "02A2-9231-36A6",
    "run_requests": "2DA5-55D3-E679",
    "build_e2_standard_2": "A464-9020-6404",
    "registry_storage": "8502-299A-ABAF",
    "object_standard_tokyo": "1845-1496-2891",
    "object_class_a": "4DBF-185F-A415",
    "object_class_b": "7870-010B-2763",
    "logging_ingestion": "143F-A1B0-E0BE",
    "logging_extra_retention": "F4AE-5A52-ACE3",
    "secret_version_replica": "7756-ADEF-84F4",
    "secret_access": "EBA7-264F-2D2C",
    "tasks_operations": "378A-D762-1F74",
    "dns_zone": "8C22-6FC3-D478",
    "dns_queries": "6DFF-5025-A128",
    "internet_worst_selected_destination": "0D27-F4FA-E8E0",
}


def read(name):
    return json.loads((DIRECTORY / name).read_text())


def rows(record):
    if "records" in record:
        yield from record["records"]
    for item in record.get("results", []):
        yield from item["records"]


def value(price):
    return D(price.get("units", "0")) + D(price.get("nanos", 0)) / D(10**9)


def rate(record):
    return max(
        value(t["unitPrice"])
        for t in record["pricingInfo"][-1]["pricingExpression"]["tieredRates"]
    )


def money(number):
    return str(number.quantize(D(".000000001")))


def make():
    inventory = {}
    for name in INPUTS:
        for entry in rows(read(name)):
            if entry["skuId"] in inventory:
                assert inventory[entry["skuId"]] == entry, entry["skuId"]
            inventory[entry["skuId"]] = entry
    selected = {name: inventory[identity] for name, identity in SELECTED.items()}
    for name, entry in selected.items():
        assert entry["category"]["usageType"] == "OnDemand", name
        assert not any(
            word in entry["description"].lower()
            for word in ["commitment", "trial", "preemptible", "spot"]
        ), name
        assert entry["pricingInfo"][-1]["pricingExpression"]["tieredRates"], name
        assert all(
            t["unitPrice"]["currencyCode"] == "JPY"
            for t in entry["pricingInfo"][-1]["pricingExpression"]["tieredRates"]
        ), name

    def r(name):
        return rate(selected[name])

    def month(name, quantity, hours):
        expression = selected[name]["pricingInfo"][-1]["pricingExpression"]
        base = D(str(expression["baseUnitConversionFactor"]))
        if expression["baseUnit"] == "By.s":
            base /= D(2**30)
        assert expression["usageUnit"] in {"GiBy.mo", "mo"}
        return r(name) * D(str(quantity)) * D(hours) * 3600 / base

    def scenario(hours):
        # Month-based rates use each captured SKU's actual base conversion; no assumed 730h month divisor.
        items = {
            "sql_enterprise_zonal_compute_2vcpu_7_5gib": (
                2 * r("sql_cpu") + D("7.5") * r("sql_ram")
            )
            * hours,
            "sql_ssd_20gib": month("sql_ssd", 20, hours),
            "sql_retained_backups_20gib": month("sql_backups", 20, hours),
            "sql_pitr_log_allowance_10gib_at_ssd_rate": month("sql_ssd", 10, hours),
            "one_global_https_forwarding_minimum": r("global_https_forwarding_minimum")
            * hours,
            "ipv4_attached_to_forwarding_rule": D(0),
            "unbound_address_transition_allowance_not_exact_global_sku": D(100),
            "lb_processing_10gib_in_and_10gib_out": 10 * r("lb_inbound_tokyo")
            + 10 * r("lb_outbound_tokyo"),
            "dns_one_managed_zone": month("dns_zone", 1, hours),
            "dns_100000_queries": 100000 * r("dns_queries"),
            "run_aggregate_monthly_budget_allocation": D(3000),
            "worker_e2_standard_8_37_5_active_hours": D("37.5")
            * (8 * r("worker_cpu") + 32 * r("worker_ram")),
            "worker_50gib_balanced_disk_scenario": month(
                "worker_balanced_disk", 50, hours
            ),
            "worker_ephemeral_external_ipv4_37_5h_if_used": D("37.5")
            * r("standard_vm_ipv4"),
            "two_builds_20_minutes_each_e2_standard_2": 40 * r("build_e2_standard_2"),
            "registry_5gib": month("registry_storage", 5, hours),
            "object_storage_10gib_including_soft_deleted_versions": month(
                "object_standard_tokyo", 10, hours
            ),
            "object_operations_10000_class_a_100000_class_b": 10000
            * r("object_class_a")
            + 100000 * r("object_class_b"),
            "logging_ingestion_5gib_no_free_assumption": 5 * r("logging_ingestion"),
            "eight_single_region_secret_versions": month(
                "secret_version_replica", 8, hours
            ),
            "secret_access_10000_operations": 10000 * r("secret_access"),
            "tasks_100000_operations": 100000 * r("tasks_operations"),
            "internet_10gib_max_selected_destination_rate": 10
            * r("internet_worst_selected_destination"),
        }
        total = sum(items.values())
        reserve = total * D(".10")
        return {
            "fixed_resource_hours": hours,
            "line_items_jpy": {name: money(amount) for name, amount in items.items()},
            "gross_before_contingency_jpy": money(total),
            "cost_contingency_factor": "0.10",
            "contingency_is_tax_claim": False,
            "contingency_jpy": money(reserve),
            "total_with_contingency_jpy": money(total + reserve),
            "headroom_to_50000_jpy": money(D(50000) - total - reserve),
        }

    summaries = {
        name: {
            "sku_id": entry["skuId"],
            "description": entry["description"],
            "regions": entry["serviceRegions"],
            "currency": "JPY",
            "effective_time": entry["pricingInfo"][-1]["effectiveTime"],
            "usage_unit": entry["pricingInfo"][-1]["pricingExpression"]["usageUnit"],
            "no_free_credit_rate_jpy": str(rate(entry)),
        }
        for name, entry in selected.items()
    }
    scenario730 = scenario(730)
    scenario744 = scenario(744)
    assert D(scenario744["total_with_contingency_jpy"]) < 50000
    selected_receipt = {
        "version": "beta-selected-public-jpy-skus-v1",
        "quote_date": "2026-11-02 JST",
        "public_list_not_account_contract": True,
        "selection": summaries,
        "official_records": selected,
    }
    estimate = {
        "version": "beta-public-jpy-cost-qualification-v1",
        "quote_date": "2026-11-02 JST",
        "project_id": "ocean-v1-beta-20261101",
        "region": "asia-northeast1",
        "currency": "JPY",
        "pricing_kind": "Google public list OnDemand/default; no CUD/free credits/negotiated contract assumed",
        "free_credit_assumption": 0,
        "selected_prices": summaries,
        "scenario_730h": scenario730,
        "scenario_31day_744h": scenario744,
        "target_jpy": 50000,
        "public_price_usage_scenario_fits_target": True,
        "is_provider_hard_cap": False,
        "is_usage_forecast_or_invoice": False,
        "paid_resource_provisioning_performed": False,
        "base_month_conversion_qualification": "Captured GiBy.mo and mo SKUs report2595600seconds (721hours) per month. Calculations use each raw baseUnitConversionFactor, including744h/721h proration; do not silently assume730hours per price-month.",
        "ipv4_qualification": "Static external IPv4 assigned to forwarding rules is not charged per official network pricing. JPY100 is an operator transition allowance for unused reservations, not an exact global-unused-IP quote. Regional unused Tokyo reference SKU retained separately; do not mislabel it global. Reserve address only when immediately binding the rule; review actual readback.",
        "pitr_qualification": "10GiB at actual SQL SSD unit rate is a procurement allowance for log storage, not a claim all PITR logs are billed as SSD. Parent must select the actual PITR storage/retention implementation and meter bytes.20GiB backup is separate.",
        "usage_conditions": [
            "SQL Enterprise PostgreSQL dedicatedzonal2vCPU7.5GiB,20GiB SSD; no HA/replica/EnterprisePlus/extendedsupport",
            "Backups20GiB plus10GiB separate log allowance; no deletion/TTL ofheld evidence proposed",
            "One globalHTTPS forwarding minimum; noHTTPredirect forwardingrule; noCloudArmor/CDN/NAT/PSCpaidendpoint",
            "Run aggregateJPY3000 allocation across services; cap is service-scoped/lagged and not a whole-projecthardstop; min0/max1 still requires observedusage",
            "Worker only37.5activehours/month;50GiBbalanced disk scenario pending realC23capacity qualification; noalways-onworker",
            "Build2x20minutes e2-standard-2;Registry5GiB;Objectstorage10GiB acrosslive+retained/softdeleted versions",
            "Logingestion5GiB/month,defaultretention;8singleregionsecretversions,10kaccesses;100kTasksoperations",
            "10GiB inbound+10GiB outboundLBprocessing and10GiB internettransfer pricedatmaxselectedJapan destination;100kDNSqueries",
            "Re-quote before larger volumes, machines, HA, paid add-ons or sustainedwork;notifybeforeforecastexceedsJPY50000",
        ],
        "actual_account_tax_treatment_verified": False,
        "unknowns_remaining": [
            "Accountnegotiatedprices/taxinvoice not inspected;10% iscostcontingency only",
            "ActualAPI/cataloguememory,traffic,snapshotlogbackupvolume andworkersizeacceptance mustbeobserved",
            "GlobalunusedIPv4exactSKU notestablished;normalattachedstate hasofficialzeroIPv4charge",
            "Models/realdataacquisition/transfer notincludedorselected",
        ],
    }
    return selected_receipt, estimate


if __name__ == "__main__":
    selected, estimate = make()
    for name, data in [
        ("selected-prices.json", selected),
        ("cost-qualification.json", estimate),
    ]:
        path = DIRECTORY / name
        if path.exists():
            raise RuntimeError("Refuse overwrite: " + name)
        path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    print(
        json.dumps(
            {
                "gross_730h_jpy": estimate["scenario_730h"][
                    "gross_before_contingency_jpy"
                ],
                "with_reserve_730h_jpy": estimate["scenario_730h"][
                    "total_with_contingency_jpy"
                ],
                "gross_744h_jpy": estimate["scenario_31day_744h"][
                    "gross_before_contingency_jpy"
                ],
                "with_reserve_744h_jpy": estimate["scenario_31day_744h"][
                    "total_with_contingency_jpy"
                ],
                "headroom_744h_jpy": estimate["scenario_31day_744h"][
                    "headroom_to_50000_jpy"
                ],
                "selected_skus": len(selected["selection"]),
            },
            indent=2,
        )
    )
