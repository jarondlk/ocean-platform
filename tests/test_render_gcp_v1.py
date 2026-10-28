"""Offline C24 isolation/configuration acceptance; no live GCP or runtime claims."""
from copy import deepcopy
import hashlib
import json
import socket
import subprocess

import pytest
from pydantic import ValidationError

from schema.research_experiments import ExperimentResources
from scripts import render_gcp_v1 as renderer


FIXTURE = renderer.DIRECTORY / "examples/site.synthetic.json"


def values():
    return json.loads(FIXTURE.read_text())


def change(data, path, value):
    keys = path.split(".")
    for key in keys[:-1]:
        data = data[key]
    data[keys[-1]] = value


def test_exact_schema_is_current():
    assert json.loads((renderer.DIRECTORY / "site.schema.json").read_text()) == renderer.Site.model_json_schema()
    assert renderer.main(["--check-schema"]) == 0


@pytest.mark.parametrize(("path", "bad"), [
    ("target.project_id", "data-infra-infobio"),
    ("target.project_id", "ocean-v1-c23-20261024"),
    ("target.project_number", "469489188516"),
    ("target.project_number", "1010914377085"),
    ("target.project_number", ""),
    ("target.region", ""),
    ("target.zone", "us-central1-a"),
    ("target.subnet_cidr", "0.0.0.0/0"),
    ("target.subnet_cidr", "169.254.0.0/16"),
    ("target.subnet_cidr", "10.70.0.1/24"),
    ("target.sql_private_cidr", "10.70.0.0/24"),
    ("target.public_origin", "https://oceaninfobio.com"),
    ("target.public_origin", "https://www.oceaninfobio.com"),
    ("target.public_origin", "https://tools.oceaninfobio.com"),
    ("target.public_origin", "http://beta.example.invalid"),
    ("target.public_origin", "https://beta.example.invalid/"),
    ("target.public_origin", "https://beta.example.invalid:443"),
    ("target.public_origin", "https://user:password@beta.example.invalid"),
    ("target.public_origin", "https://beta.example.invalid?next=legacy"),
    ("target.public_origin", "https://*.oceaninfobio.com"),
    ("target.public_origin", "https://beta.example.invalid#fragment"),
    ("target.public_origin", "https://beta.example.invalid\n"),
    ("browser.cookie_domain", ".oceaninfobio.com"),
    ("browser.session_cookie", "__Secure-authjs.session-token"),
    ("browser.cookie_secure", False),
    ("browser.cookie_http_only", False),
    ("browser.cookie_path", "/api"),
    ("browser.same_site", "none"),
    ("browser.csrf_origin", "https://oceaninfobio.com"),
    ("browser.cors_origins", ["https://*.oceaninfobio.com"]),
    ("browser.cors_origins", ["https://beta.example.invalid", "https://oceaninfobio.com"]),
    ("browser.oauth_callback", "https://oceaninfobio.com/api/auth/callback/google"),
    ("browser.oauth_client_id", ""),
    ("browser.internal_audience", "ocean-v1-frontend"),
    ("identities.serving", "ocean-platform@data-infra-infobio.iam.gserviceaccount.com"),
    ("identities.supervisor", "default"),
    ("secrets.auth", "raw-secret-value"),
    ("secrets.auth", "projects/469489188516/secrets/ocean-v1-auth/versions/1"),
    ("secrets.oauth", "projects/123456789012/secrets/ocean-v1-oauth/versions/latest"),
    ("services.serving_image", "nginx:latest"),
    ("services.api_image", "asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/api@sha256:" + "a" * 64),
    ("services.controller", "ocean-platform"),
    ("worker.boot_image", "projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64"),
    ("worker.machine_type", "e2-standard-4"),
    ("worker.supervisor_cpu_reserve", 6),
    ("worker.supervisor_memory_reserve_mib", 32768),
    ("worker.aggregate_host_pid_budget", 383),
    ("worker.runtime_files", {"runsc": "a" * 64}),
    ("worker.scientific_image_digest", "latest"),
    ("worker.trusted_init_sha256", "unverified"),
    ("queue.max_concurrent_dispatches", 3),
    ("queue.oidc_audience", "https://oceaninfobio.com"),
    ("queue.controller_uri", "https://beta.example.invalid/internal/research/deliver"),
    ("stores.results_bucket", "ocean-v1-shared-results"),
    ("stores.database_name", "ocean_platform"),
    ("stores.database_disk_limit_gib", 19),
    ("flags.research_dispatch", True),
    ("flags.experiment_dispatch", True),
    ("flags.experiment_dispatch", 0),
    ("operations.monthly_spend_limit", 0),
    ("operations.currency", ""),
    ("operations.max_job_log_bytes", 1024**3),
    ("operations.backup_retention_days", 0),
])
def test_unsafe_configuration_is_rejected(path, bad):
    data = values()
    change(data, path, bad)
    with pytest.raises(ValidationError):
        renderer.Site.model_validate(data)


@pytest.mark.parametrize("section", [None, "target", "services", "browser", "identities", "worker", "stores", "secrets", "queue", "operations", "flags"])
def test_unknown_input_cannot_inject_grants_mounts_secrets_or_startup(section):
    data = values()
    target = data if section is None else data[section]
    target["startup_script"] = "secret-command-must-not-run"
    with pytest.raises(ValidationError):
        renderer.Site.model_validate(data)


@pytest.mark.parametrize("section", ["services", "target", "browser", "secrets", "stores", "queue", "identities", "operations", "worker", "flags"])
def test_every_target_section_is_explicit(section):
    data = values()
    del data[section]
    with pytest.raises(ValidationError):
        renderer.Site.model_validate(data)


@pytest.mark.parametrize(("path", "other"), [
    ("services.controller", "services.serving"),
    ("stores.quarantine_bucket", "stores.results_bucket"),
    ("secrets.internal", "secrets.auth"),
    ("secrets.verifier_database", "secrets.supervisor_database"),
    ("identities.controller", "identities.serving"),
])
def test_independent_resources_cannot_alias(path, other):
    data = values()
    group, field = other.split(".")
    change(data, path, data[group][field])
    with pytest.raises(ValidationError):
        renderer.Site.model_validate(data)


def test_beta_is_an_explicit_operator_origin_with_a_new_binding():
    data = values()
    origin = "https://beta.oceaninfobio.com"
    data["input_class"] = "operator-values"
    data["target"]["public_origin"] = origin
    data["browser"].update(csrf_origin=origin, cors_origins=[origin], oauth_callback=origin + "/api/auth/callback/google")
    site = renderer.Site.model_validate(data)
    rendered = renderer.render(site)
    assert rendered["site-policy.json"]["browser"]["cors_origins"] == [origin]
    assert rendered["site-policy.json"]["activation"]["experiment_dispatch"] is False
    data["input_class"] = "synthetic"
    with pytest.raises(ValidationError):
        renderer.Site.model_validate(data)


def test_rendered_project_private_controller_and_physical_release_boundaries():
    site = renderer.load_site(FIXTURE)
    files = renderer.render(site)
    serve = files["serving.json"]["body"]
    controller = files["controller.json"]["body"]
    worker = files["worker.json"]["body"]
    policy = files["site-policy.json"]
    assert controller["ingress"] == "INGRESS_TRAFFIC_INTERNAL_ONLY"
    assert controller["invokerIamDisabled"] is False
    assert serve["ingress"] == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    assert serve["defaultUriDisabled"] is True
    assert serve["invokerIamDisabled"] is True  # Browser login via LB; app session auth remains required.
    assert [c["name"] for c in serve["template"]["containers"]] == ["frontend", "api"]
    assert "ports" not in serve["template"]["containers"][1]
    assert worker["networkInterfaces"][0]["accessConfigs"] == []
    assert worker["canIpForward"] is False
    assert worker["disks"][0]["autoDelete"] is False
    assert "startup-script" not in json.dumps(worker)
    assert policy["guest_credentials"] == [] and policy["guest_network"] == "none"
    assert policy["capacity"]["global"] == 2 and policy["capacity"]["per_user"] == 1
    assert policy["capacity"]["queue_concurrency_is_capacity_authority"] is False
    assert policy["supervisor"]["lease_expiry_releases_capacity"] is False
    approved_limits = ExperimentResources().model_dump()
    assert all(policy["limits"][key] == value for key, value in approved_limits.items())
    assert policy["limits"]["guest_nofile"] == 256 and policy["limits"]["native_nofile"] == 4096
    assert all(g["status"] == "not_run" for g in policy["gates"])
    assert all(a["apply_allowed"] is False and a["provider_schema_validated"] is False for a in files.values())


def test_output_manifest_authenticates_bytes_and_refuses_existing_paths(tmp_path):
    site = renderer.load_site(FIXTURE)
    target = tmp_path / "bundle"
    receipt = renderer.write_bundle(site, target)
    assert len(receipt["files"]) == 7
    for name, digest in receipt["files"].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest
    before = (target / "manifest.json").read_bytes()
    with pytest.raises(renderer.ConfigurationError):
        renderer.write_bundle(site, target)
    assert (target / "manifest.json").read_bytes() == before
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(renderer.ConfigurationError):
        renderer.write_bundle(site, existing)
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(renderer.ConfigurationError):
        renderer.write_bundle(site, link)


def test_renderer_never_uses_network_commands_or_ambient_legacy_config(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline configuration contacted an external service or command")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "data-infra-infobio")
    monkeypatch.setenv("DATABASE_URL", "postgresql://do-not-read-ambient-secret")
    monkeypatch.setenv("AUTH_SECRET", "do-not-read-ambient-secret")
    target = tmp_path / "offline"
    renderer.write_bundle(renderer.load_site(FIXTURE), target)
    combined = "\n".join(p.read_text() for p in target.iterdir())
    assert "data-infra-infobio" not in combined
    assert "do-not-read-ambient-secret" not in combined
    assert renderer.main(["--config", str(FIXTURE), "--check"]) == 0


@pytest.mark.parametrize("raw", ['{"version":1,"version":2}', '{"secret":NaN}', '[]', 'null', '{', '"' + 'x' * renderer.MAX_BYTES + '"'])
def test_bounded_unambiguous_inputs_and_safe_errors(tmp_path, capsys, raw):
    path = tmp_path / "bad.json"
    path.write_text(raw)
    with pytest.raises(SystemExit) as error:
        renderer.main(["--config", str(path), "--check"])
    assert error.value.code == 2
    assert raw not in capsys.readouterr().err


def test_symlink_and_directory_inputs_are_rejected(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(FIXTURE)
    for path in [link, tmp_path]:
        with pytest.raises(renderer.ConfigurationError):
            renderer.load_site(path)


def test_mutated_model_cannot_bypass_browser_checks():
    site = renderer.load_site(FIXTURE)
    site.browser.cors_origins.append("https://oceaninfobio.com")
    with pytest.raises(renderer.ConfigurationError):
        renderer.render(site)


@pytest.mark.parametrize(("template", "path", "bad"), [
    ("controller", "body.ingress", "INGRESS_TRAFFIC_ALL"),
    ("controller", "body.invokerIamDisabled", True),
    ("site-policy", "guest_network", "host"),
    ("site-policy", "guest_credentials", ["DATABASE_URL"]),
    ("site-policy", "apply_allowed", True),
    ("identity", "body.project_wide_roles", ["roles/editor"]),
    ("storage-database", "body.automatic_results_deletion", True),
    ("worker", "body.serviceAccounts", [{"email": "legacy@example.com"}]),
    ("worker", "body.metadata", {"items": [{"key": "startup-script", "value": "unexpected"}]}),
    ("queue", "body.name", "projects/data-infra-infobio/locations/asia-northeast1/queues/legacy"),
    ("site-policy", "supervisor.lease_expiry_releases_capacity", True),
    ("site-policy", "activation.research_dispatch", True),
    ("identity", "body.scoped_permission_intents", []),
])
def test_unsafe_template_change_is_rejected(tmp_path, monkeypatch, template, path, bad):
    local = tmp_path / "config"
    (local / "templates").mkdir(parents=True)
    for name in renderer.TEMPLATES:
        source = renderer.DIRECTORY / "templates" / (name + ".json")
        (local / "templates" / source.name).write_bytes(source.read_bytes())
    target = local / "templates" / (template + ".json")
    data = json.loads(target.read_text())
    change(data, path, bad)
    target.write_text(json.dumps(data))
    site = renderer.load_site(FIXTURE)
    monkeypatch.setattr(renderer, "DIRECTORY", local)
    with pytest.raises(renderer.ConfigurationError):
        renderer.render(site)


def test_version_alias_of_same_secret_is_not_independent():
    data = values()
    data["secrets"]["internal"] = data["secrets"]["auth"].removesuffix("1") + "2"
    with pytest.raises(ValidationError):
        renderer.Site.model_validate(data)


def test_increased_queue_retries_do_not_change_capacity_or_physical_authority():
    data = deepcopy(values())
    data["queue"]["max_attempts"] = 10
    site = renderer.Site.model_validate(data)
    rendered = renderer.render(site)
    assert rendered["queue.json"]["body"]["retryConfig"]["maxAttempts"] == 10
    assert rendered["site-policy.json"]["capacity"]["authority"] == "C22 PostgreSQL reservation locks"
    assert rendered["site-policy.json"]["supervisor"]["lease_expiry_releases_capacity"] is False


def test_full_browser_binding_still_rejects_an_overlong_DNS_label():
    data = values()
    origin = "https://" + "a" * 64 + ".example.invalid"
    data["target"]["public_origin"] = origin
    data["browser"].update(csrf_origin=origin, cors_origins=[origin], oauth_callback=origin + "/api/auth/callback/google")
    with pytest.raises(ValidationError):
        renderer.Site.model_validate(data)


def test_controller_name_cannot_make_a_non_DNS_service_URL():
    data = values()
    controller = "ocean-v1-" + "c" * 45
    data["services"]["controller"] = controller
    audience = f"https://{controller}-{data['target']['project_number']}.{data['target']['region']}.run.app"
    data["queue"].update(oidc_audience=audience, controller_uri=audience + "/internal/research/deliver")
    with pytest.raises(ValidationError):
        renderer.Site.model_validate(data)


def test_incomplete_operator_workbook_cannot_render_beta():
    with pytest.raises(renderer.ConfigurationError):
        renderer.load_site(renderer.DIRECTORY / "examples/site.operator.pending.json")
