"""Read-only checks for a pending beta hosting proposal; never calls GCP."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DIRECTORY = Path(__file__).resolve().parent
PROJECT = "ocean-v1-beta-20261101"
NUMBER = "534831104543"


def read(path):
    return json.loads(path.read_text())


def verify():
    manifest = read(DIRECTORY / "artifacts.json")
    for name, expected in manifest["sha256"].items():
        path = DIRECTORY / name
        assert path.parent.resolve() == DIRECTORY and not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    inputs = read(DIRECTORY / "inspected-inputs.json")
    for name, expected in inputs["sha256"].items():
        path = ROOT / name
        assert path.resolve().is_relative_to(ROOT) and not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    plan = read(DIRECTORY / "plan.json")
    assert not plan["cloud_mutations_performed_by_this_task"]
    assert (
        not plan["commit_performed"]
        and not plan["service_candidate_is_ready_to_submit"]
    )
    assert plan["target"]["project_id"] == PROJECT
    assert plan["target"]["project_number"] == NUMBER
    spec = read(DIRECTORY / "serving-service.pending.json")
    assert (
        spec["name"]
        == f"projects/{PROJECT}/locations/asia-northeast1/services/ocean-v1-beta-serving"
    )
    assert spec["defaultUriDisabled"] and spec["invokerIamDisabled"]
    assert spec["ingress"] == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    assert spec["scaling"]["minInstanceCount"] == 0
    assert spec["scaling"]["maxInstanceCount"] == 1
    template = spec["template"]
    assert template["serviceAccount"] == plan["target"]["runtime_service_account"]
    assert template["executionEnvironment"] == "EXECUTION_ENVIRONMENT_GEN2"
    assert template["vpcAccess"]["egress"] == "PRIVATE_RANGES_ONLY"
    containers = {row["name"]: row for row in template["containers"]}
    assert set(containers) == {"frontend", "api", "sql-proxy"}
    assert containers["frontend"]["ports"] == [{"containerPort": 8080, "name": "http1"}]
    assert "ports" not in containers["api"] and "ports" not in containers["sql-proxy"]
    assert (
        containers["api"]["dependsOn"]
        == containers["frontend"]["dependsOn"]
        == ["sql-proxy"]
    )
    assert "startupProbe" not in containers["api"], (
        "No invented platform probe into loopback API"
    )
    assert containers["sql-proxy"]["startupProbe"]["httpGet"] == {
        "path": "/readiness",
        "port": 9090,
    }
    assert "--address=127.0.0.1" in containers["sql-proxy"]["args"]
    assert "--private-ip" in containers["sql-proxy"]["args"]
    secret_ids = set()
    for name, container in containers.items():
        assert container["image"] == plan["candidate_images"][name]
        assert "@sha256:" in container["image"]
        assert container["resources"]["limits"]["cpu"] == "1"
        assert container["resources"]["cpuIdle"]
        assert not container["resources"]["startupCpuBoost"]
        for entry in container.get("env", []):
            assert entry["name"] != "DATABASE_URL"
            if "valueSource" in entry:
                ref = entry["valueSource"]["secretKeyRef"]
                assert ref["version"] == "1"
                assert ref["secret"].startswith(f"projects/{NUMBER}/secrets/")
                secret_ids.add(ref["secret"].split("/")[-1])
    assert secret_ids == {
        "ocean-v1-beta-auth",
        "ocean-v1-beta-internal",
        "ocean-v1-beta-serving-database",
        "ocean-v1-beta-oauth",
    }
    frontend = {row["name"]: row for row in containers["frontend"]["env"]}
    api = {row["name"]: row for row in containers["api"]["env"]}
    assert frontend["V1_API_ORIGIN"]["value"] == "http://127.0.0.1:8000"
    assert (
        frontend["V1_GOOGLE_CLIENT_ID"]["value"]
        == plan["actual_metadata_inputs"]["oauth_client_id"]
    )
    assert (
        frontend["V1_INTERNAL_AUTH_SECRET"]["valueSource"]
        == api["OCEAN_V1_INTERNAL_AUTH_SECRET"]["valueSource"]
    )
    assert api["OCEAN_V1_DATABASE_USER"]["value"] == "ocean_v1_serving"
    assert (
        api["OCEAN_V1_HOST_CONFIG"]["value"]
        == plan["api_config"]["required_regular_file"]
    )
    flags = {
        name: row["value"] for name, row in api.items() if name.startswith("ENABLE_V1_")
    }
    assert len(flags) == 12 and set(flags.values()) == {"false"}
    config = read(DIRECTORY / "api-host-config.json")
    assert config["revision"] == plan["image_source_revision"]
    assert (
        config["project_id"] == PROJECT and config["database_name"] == "ocean_v1_beta"
    )
    assert config["backend_hosts"] == ["127.0.0.1:8000"]
    assert config["allowed_providers"] == ["google"]
    assert (
        plan["api_config"]["delivery_state"]
        == "not_implemented_or_qualified_in_current_image"
    )
    assert len(plan["iam"]["secret_bindings"]) == 4
    assert plan["iam"]["cloudsql_client_binding"]["role"] == "roles/cloudsql.client"
    assert (
        "instances/ocean-v1-beta-sql"
        in plan["iam"]["cloudsql_client_binding"]["condition"]
    )
    url_map = read(DIRECTORY / "url-map.proposed.json")
    assert plan["load_balancer"]["scheme"] == "EXTERNAL_MANAGED"
    assert url_map["headerAction"]["requestHeadersToRemove"] == ["Forwarded"]
    assert all(
        header["replace"] for header in url_map["headerAction"]["requestHeadersToAdd"]
    )
    assert url_map["hostRules"][0]["hosts"] == ["beta.oceaninfobio.com"]
    assert plan["load_balancer"]["address_value"] is None
    assert plan["dns"]["create_only_record"] == {
        "name": "beta.oceaninfobio.com.",
        "type": "A",
        "ttl": 300,
        "rrdatas": None,
    }
    prices = read(
        ROOT / "docs/plans/ocean-v1/beta/quotes-20261102/selected-prices.json"
    )["selection"]
    cpu = Decimal(prices["run_request_cpu"]["no_free_credit_rate_jpy"])
    memory = Decimal(prices["run_request_ram"]["no_free_credit_rate_jpy"])
    request = Decimal(prices["run_requests"]["no_free_credit_rate_jpy"])
    hourly = (3 * cpu + Decimal("4.75") * memory) * 3600
    example = hourly * 50 + request * 100000
    assert hourly == Decimal(plan["cost"]["serving_example_rate_jpy_per_hour"])
    assert example == Decimal(
        plan["cost"]["serving_example_50h_plus_100k_requests_jpy"]
    )
    assert example < Decimal(plan["cost"]["run_allocation_jpy"])
    assert Decimal(plan["cost"]["original_744h_envelope_jpy"]) < 50000
    assert plan["closed_capabilities"]["queue_state"] == "PAUSED"
    assert not plan["closed_capabilities"]["controller_or_worker_started"]
    assert not plan["closed_capabilities"]["real_scientific_provider_installed"]
    return {
        "verified": True,
        "proposal_ready_to_submit": False,
        "containers": sorted(containers),
        "sole_ingress_port": 8080,
        "secret_resources": len(secret_ids),
        "inspected_inputs": len(inputs["sha256"]),
        "pending_gates": len(plan["readiness_gates"]),
        "run_50h_example_plus_requests_jpy": str(example),
        "original_monthly_envelope_jpy": plan["cost"]["original_744h_envelope_jpy"],
        "cloud_actions_performed": False,
        "full_release_accepted": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
