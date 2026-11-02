"""Local scope and artifact checks for a proposed DNS/TLS plan; never applies it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
BETA = "ocean-v1-beta-20261101"
PARENT_PROJECT = "data-infra-infobio"


def read(name):
    return json.loads((DIRECTORY / name).read_text())


def verify():
    manifest = read("artifacts.json")
    for name, expected in manifest["sha256"].items():
        path = DIRECTORY / name
        assert path.resolve().is_relative_to(DIRECTORY) and path.is_file()
        assert not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    plan = read("plan.json")
    assert plan["version"] == "beta-isolated-dns-tls-plan-v1"
    assert plan["state"] == "prepared_not_applied"
    assert not plan["this_task_cloud_mutations_performed"]
    assert plan["beta_project"] == {"id": BETA, "number": "534831104543"}
    assert plan["origin"] == "https://beta.oceaninfobio.com"
    assert plan["dns_name"] == "beta.oceaninfobio.com."
    assert plan["parent_zone"]["project"] == PARENT_PROJECT
    assert plan["parent_zone"]["name"] == "oceaninfobio-com"
    child = plan["proposed_child_zone"]
    assert child["project"] == BETA and child["dns_name"] == plan["dns_name"]
    assert child["name_servers"] is None, "Actual assigned values are still unresolved"
    parent = plan["permitted_parent_zone_change"]
    assert parent["type"] == "NS" and parent["name"] == plan["dns_name"]
    assert parent["ttl"] == 300 and parent["create_only"]
    assert parent["other_parent_zone_records_must_remain_byte_equivalent"]
    assert parent["no_parent_zone_or_apex_NS_change"]
    cert = plan["proposed_certificate"]
    assert cert["domains"] == ["beta.oceaninfobio.com"]
    assert cert["location"] == "global" and cert["scope"] == "DEFAULT"
    assert cert["dns_authorization_type_cli"] == "per-project-record"
    assert not cert["primary_matcher"] and not cert["wildcard_requested"]
    stages = {stage["id"]: stage for stage in plan["stages"]}
    assert len(stages) == 9
    parent_commands = []
    commands_checked = 0
    for stage in plan["stages"]:
        for command in stage.get("commands", []) + stage.get(
            "illustrative_commands_not_ready_to_run", []
        ):
            assert command[0] == "gcloud"
            projects = [arg for arg in command if arg.startswith("--project=")]
            assert len(projects) == 1
            project = projects[0].split("=", 1)[1]
            assert project in {BETA, PARENT_PROJECT}
            if project == PARENT_PROJECT:
                if stage["mutation"]:
                    assert stage["id"] == "add_parent_delegation_only"
                    assert command[1:4] == ["dns", "record-sets", "transaction"]
                    assert "--zone=oceaninfobio-com" in command
                    if command[4] == "add":
                        assert "--type=NS" in command
                        assert "--name=beta.oceaninfobio.com." in command
                        assert "--ttl=300" in command
                    else:
                        assert command[4] in {"start", "execute"}
                    parent_commands.append(command)
                else:
                    assert command[1] == "dns"
                    assert "list" in command or "describe" in command
            commands_checked += 1
    assert len(parent_commands) == 3
    assert not stages["later_bind_after_host_ready"]["allowed_now"]
    help_text = (DIRECTORY / "cli-help/dns-authorizations-create.txt").read_text()
    assert "per-project-record" in help_text and "--location=LOCATION" in help_text
    assert (
        "--dns-authorizations="
        in (DIRECTORY / "cli-help/certificates-create.txt").read_text()
    )
    assert (
        "--hostname=HOSTNAME"
        in (DIRECTORY / "cli-help/map-entries-create.txt").read_text()
    )
    pricing = read("certificate-pricing.json")
    assert pricing["currency"] == "JPY"
    assert pricing["eligibility_count_still_requires_actual_beta_certificate_inventory"]
    global_prices = [
        row for row in pricing["official_records"] if row["skuId"] == "F08F-F1CD-3492"
    ]
    assert len(global_prices) == 1
    tiers = global_prices[0]["pricingInfo"][-1]["pricingExpression"]["tieredRates"]
    assert [row["startUsageAmount"] for row in tiers] == [0, 100, 2000]
    assert tiers[0]["unitPrice"] == {"currencyCode": "JPY", "units": "0", "nanos": 0}
    return {
        "verified": True,
        "state": "prepared_not_applied",
        "ordered_stages": len(stages),
        "explicit_project_commands_checked": commands_checked,
        "parent_mutation_scope": "one create-only beta NS delegation; no existing record changes",
        "actual_child_servers_and_authorization_values_pending": True,
        "certificate_free_tier_eligibility": "requires actual beta inventory",
        "paid_load_balancer_ip_provisioning_performed": False,
        "cloud_mutations_performed_by_this_task": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
