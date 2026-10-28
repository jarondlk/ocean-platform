#!/usr/bin/env python3
"""Validate and render C24 configuration artifacts locally; never apply resources."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator


ROOT = Path(__file__).resolve().parent.parent
DIRECTORY = ROOT / "deploy/gcp-v1"
LEGACY_PROJECTS = {"data-infra-infobio", "ocean-v1-c23-20261024"}
LEGACY_NUMBERS = {"469489188516", "1010914377085"}
MAX_BYTES = 256 * 1024
TEMPLATES = (
    "serving", "controller", "queue", "worker", "storage-database", "identity", "site-policy",
)
GATES = (
    "whole_site_target_and_live_action_authorization",
    "authenticated_v1_host_proxy_and_bootstrap",
    "real_cloud_tasks_adapter_outbox_and_private_invocation",
    "production_experiment_supervisor_health_and_drain",
    "worker_boot_image_unique_id_and_disk_sourceImageId",
    "DNS_TLS_Host_OAuth_cookie_and_cross_origin_validation",
    "inherited_IAM_and_network_legacy_access_denials",
    "two_simultaneous_sandboxes_and_measured_host_capacity",
    "crash_reboot_uncertain_ACK_recovery_and_physical_proof_release",
    "independent_backup_restore_retention_budget_and_alert_readbacks",
    "C26_C27_integrated_acceptance_and_release_promotion",
)
RESOURCE_LIMITS = {
    "cpus": 2, "memory_bytes": 4 * 1024**3, "wall_seconds": 600,
    "max_input_bytes": 256 * 1024**2, "max_output_bytes": 50 * 1024**2,
    "guest_nofile": 256, "native_nofile": 4096, "host_pids_per_job": 128,
}
Name = Annotated[str, StringConstraints(pattern=r"^ocean-v1-[a-z0-9][a-z0-9-]{0,34}[a-z0-9]$")]
Sha = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{64}$")]
Positive = Annotated[int, Field(strict=True, ge=1, le=10**12)]


class ConfigurationError(ValueError):
    """Safe diagnostic which never echoes input values or credentials."""


class Exact(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Target(Exact):
    project_id: Annotated[str, StringConstraints(pattern=r"^ocean-v1-[a-z0-9-]{1,20}[a-z0-9]$")]
    project_number: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{5,14}$")]
    region: Annotated[str, StringConstraints(pattern=r"^[a-z]+-[a-z]+[0-9]$")]
    zone: str
    public_origin: str
    registry: Name
    network: Name
    subnet: Name
    subnet_cidr: str
    sql_private_cidr: str

    @model_validator(mode="after")
    def isolated(self):
        if self.project_id in LEGACY_PROJECTS or self.project_number in LEGACY_NUMBERS:
            raise ValueError("Legacy and temporary C23 projects are excluded")
        if self.zone not in {self.region + suffix for suffix in ("-a", "-b", "-c", "-f")}:
            raise ValueError("Zone must belong to the selected region")
        ranges = [ipaddress.ip_network(value, strict=True) for value in (self.subnet_cidr, self.sql_private_cidr)]
        private = [ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
        if (any(net.version != 4 or not 16 <= net.prefixlen <= 28
                or not any(net.subnet_of(allowed) for allowed in private) for net in ranges)
                or ranges[0].overlaps(ranges[1])):
            raise ValueError("Use disjoint bounded RFC1918 subnet and SQL ranges")
        origin = urlsplit(self.public_origin)
        host = origin.hostname or ""
        if (self.public_origin != "https://" + host or origin.scheme != "https" or origin.netloc != host or origin.path
                or origin.query or origin.fragment or len(host) > 253
                or any(len(label) > 63 for label in host.split("."))
                or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}", host)
                or host in {"oceaninfobio.com", "www.oceaninfobio.com"}
                or (host.endswith(".oceaninfobio.com") and host != "beta.oceaninfobio.com")):
            raise ValueError("An exact independent HTTPS origin is required")
        return self


class Services(Exact):
    serving: Name
    controller: Name
    serving_image: str
    api_image: str
    controller_image: str


class Identities(Exact):
    serving: str
    controller: str
    task_invoker: str
    supervisor: str


class Browser(Exact):
    oauth_client_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]+\.apps\.googleusercontent\.com$")]
    oauth_callback: str
    session_cookie: Annotated[str, StringConstraints(pattern=r"^__Host-ocean-v1-[a-z-]+$")]
    cookie_secure: bool
    cookie_http_only: bool
    cookie_path: Literal["/"]
    cookie_domain: None
    same_site: Literal["lax"]
    csrf_origin: str
    cors_origins: Annotated[list[str], Field(min_length=1, max_length=1)]
    internal_issuer: Annotated[str, StringConstraints(pattern=r"^ocean-v1-[a-z0-9-]+$")]
    internal_audience: Annotated[str, StringConstraints(pattern=r"^ocean-v1-[a-z0-9-]+$")]


class Secrets(Exact):
    auth: str
    internal: str
    oauth: str
    serving_database: str
    controller_database: str
    supervisor_database: str
    verifier_database: str
    termination_seed: str


class Stores(Exact):
    database_instance: Name
    database_name: Annotated[str, StringConstraints(pattern=r"^ocean_v1_[a-z0-9_]+$")]
    database_tier: Annotated[str, StringConstraints(pattern=r"^db-custom-[0-9]+-[0-9]+$")]
    database_disk_gib: Annotated[int, Field(strict=True, ge=20, le=1024)]
    database_disk_limit_gib: Annotated[int, Field(strict=True, ge=20, le=2048)]
    snapshots_bucket: Name
    results_bucket: Name
    quarantine_bucket: Name
    backups_bucket: Name


class Queue(Exact):
    name: Name
    controller_uri: str
    oidc_audience: str
    max_concurrent_dispatches: Annotated[int, Field(strict=True, ge=1, le=2)]
    max_dispatches_per_second: Annotated[int, Field(strict=True, ge=1, le=2)]
    max_attempts: Annotated[int, Field(strict=True, ge=1, le=10)]


class Worker(Exact):
    name: Name
    machine_type: Literal["e2-standard-8", "e2-standard-16"]
    boot_image: str
    boot_image_id: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,19}$")]
    boot_disk_gib: Annotated[int, Field(strict=True, ge=50, le=500)]
    supervisor_cpu_reserve: Annotated[int, Field(strict=True, ge=2, le=8)]
    supervisor_memory_reserve_mib: Annotated[int, Field(strict=True, ge=4096, le=32768)]
    supervisor_host_pid_reserve: Annotated[int, Field(strict=True, ge=128, le=1024)]
    aggregate_host_pid_budget: Annotated[int, Field(strict=True, ge=384, le=4096)]
    runtime_release: Annotated[str, StringConstraints(pattern=r"^release-[0-9]{8}\.[0-9]+$")]
    runtime_files: dict[str, Sha]
    scientific_image_digest: Digest
    scientific_lock_sha256: Sha
    normalized_rootfs_sha256: Sha
    trusted_init_sha256: Sha
    supervisor_source_sha256: Sha

    @model_validator(mode="after")
    def capacity_and_pins(self):
        cpus = 8 if self.machine_type == "e2-standard-8" else 16
        memory = cpus * 4096
        if (cpus < 4 + self.supervisor_cpu_reserve
                or memory < 8192 + self.supervisor_memory_reserve_mib
                or self.aggregate_host_pid_budget < 256 + self.supervisor_host_pid_reserve):
            raise ValueError("Two sandboxes plus explicit supervisor overhead must fit")
        required = {"runsc", "containerd-shim-runsc-v1", "gvisor-bin/checkpointgofer",
                    "gvisor-bin/gvisor-proc-umounter", "gvisor-bin/gvisor-sentry-prewarmer",
                    "gvisor-bin/gvisor_sentry", "gvisor-bin/runsc-fd-parking",
                    "gvisor-bin/runsc-metric-server"}
        if set(self.runtime_files) != required:
            raise ValueError("Pin the complete supported gVisor release material")
        return self


class Operations(Exact):
    currency: Literal["JPY", "USD", "EUR"]
    initial_test_spend_limit: Positive
    monthly_spend_limit: Positive
    log_retention_days: Annotated[int, Field(strict=True, ge=7, le=365)]
    backup_retention_days: Annotated[int, Field(strict=True, ge=7, le=365)]
    result_retention_days: Annotated[int, Field(strict=True, ge=30, le=3650)]
    recovery_point_minutes: Annotated[int, Field(strict=True, ge=1, le=1440)]
    recovery_time_minutes: Annotated[int, Field(strict=True, ge=1, le=10080)]
    max_job_log_bytes: Annotated[int, Field(strict=True, ge=1024, le=1024 * 1024)]


class Flags(Exact):
    research_dispatch: bool
    experiment_dispatch: bool

    @model_validator(mode="after")
    def disabled(self):
        if self.research_dispatch or self.experiment_dispatch:
            raise ValueError("C24 cannot enable live dispatch")
        return self


class Site(Exact):
    version: Literal["c24-site-input-v1"]
    input_class: Literal["synthetic", "operator-values"]
    target: Target
    services: Services
    identities: Identities
    browser: Browser
    secrets: Secrets
    stores: Stores
    queue: Queue
    worker: Worker
    operations: Operations
    flags: Flags

    @model_validator(mode="after")
    def cross_resource_binding(self):
        t = self.target
        origin = t.public_origin
        synthetic_host = urlsplit(origin).hostname.endswith(".invalid")
        if synthetic_host != (self.input_class == "synthetic"):
            raise ValueError("Synthetic and operator origins cannot be interchanged")
        if (not self.browser.cookie_secure or not self.browser.cookie_http_only
                or self.browser.csrf_origin != origin or self.browser.cors_origins != [origin]
                or self.browser.oauth_callback != origin + "/api/auth/callback/google"
                or self.browser.internal_issuer == self.browser.internal_audience):
            raise ValueError("Browser origin, callback and isolated identity must agree")
        identities = list(self.identities.model_dump().values())
        if len(set(identities)) != len(identities) or any(
                not re.fullmatch(r"ocean-v1-[a-z0-9-]{2,20}@" + re.escape(t.project_id)
                                 + r"\.iam\.gserviceaccount\.com", value) for value in identities):
            raise ValueError("Use distinct project-bound v1 service identities")
        secret_refs = list(self.secrets.model_dump().values())
        secret_pattern = r"projects/" + re.escape(t.project_number) + r"/secrets/ocean-v1-[a-z0-9-]+/versions/[1-9][0-9]*"
        if (len({"/".join(ref.split("/")[:4]) for ref in secret_refs}) != len(secret_refs)
                or any(not re.fullmatch(secret_pattern, v) for v in secret_refs)):
            raise ValueError("Use distinct project-bound numeric secret versions")
        prefix = f"{t.region}-docker.pkg.dev/{t.project_id}/{t.registry}/"
        images = [self.services.serving_image, self.services.api_image, self.services.controller_image]
        if any(not re.fullmatch(re.escape(prefix) + r"[a-z0-9-]+@sha256:[a-f0-9]{64}", image) for image in images):
            raise ValueError("Pin each application image in the explicit v1 registry")
        if not re.fullmatch(r"projects/" + re.escape(t.project_id) + r"/global/images/ocean-v1-[a-z0-9-]+", self.worker.boot_image):
            raise ValueError("Use a named v1-owned boot image, never an image family")
        expected_audience = f"https://{self.services.controller}-{t.project_number}.{t.region}.run.app"
        if (self.queue.controller_uri != expected_audience + "/internal/research/deliver"
                or self.queue.oidc_audience != expected_audience):
            raise ValueError("Bind the exact private controller URL and OIDC audience")
        names = [self.services.serving, self.services.controller, self.queue.name, self.worker.name]
        buckets = [self.stores.snapshots_bucket, self.stores.results_bucket,
                   self.stores.quarantine_bucket, self.stores.backups_bucket]
        if len(set(names)) != len(names) or len(set(buckets)) != 4:
            raise ValueError("Independent services and mutable stores cannot alias")
        if any(not bucket.startswith(t.project_id + "-") for bucket in buckets):
            raise ValueError("Global bucket names must carry the explicit v1 project namespace")
        if self.stores.database_disk_limit_gib < self.stores.database_disk_gib:
            raise ValueError("Database growth cap cannot be below initial storage")
        # Never accept arbitrary env, raw secrets, grants, URLs or startup scripts.
        return self


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("Duplicate configuration key")
        result[key] = value
    return result


def read_json(path: Path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ConfigurationError("Expected a bounded regular JSON file")
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ConfigurationError("Configuration exceeds byte limit")
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ConfigurationError("Nonfinite JSON")))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ConfigurationError("Cannot read bounded regular JSON") from exc


def load_site(path: Path):
    try:
        return Site.model_validate(read_json(path))
    except (ValidationError, ValueError, OverflowError) as exc:
        raise ConfigurationError("Configuration violates the C24 schema or isolation policy") from exc


def _env(values):
    return [{"name": name, "value": value} for name, value in sorted(values.items())]


def _secret_env(name, ref):
    parts = ref.split("/")
    return {"name": name, "valueSource": {"secretKeyRef": {"secret": "/".join(parts[:4]), "version": parts[5]}}}


def context(site: Site):
    t, s, ids = site.target, site.services, site.identities
    project_region = f"projects/{t.project_id}/locations/{t.region}"
    grants = []

    def grant(principal, resource, *permissions):
        grants.append({"principal": principal, "resource": resource, "permissions": list(permissions)})

    for principal, names in [(ids.serving, ("auth", "internal", "oauth", "serving_database")),
                             (ids.controller, ("controller_database", "verifier_database")),
                             (ids.supervisor, ("supervisor_database", "termination_seed"))]:
        for name in names:
            grant(principal, "/".join(getattr(site.secrets, name).split("/")[:4]), "secretmanager.versions.access")
    for principal in (ids.serving, ids.controller, ids.supervisor):
        grant(principal, f"//sqladmin.googleapis.com/projects/{t.project_id}/instances/{site.stores.database_instance}",
              "cloudsql.instances.connect", "cloudsql.instances.get")
        grant(principal, "//storage.googleapis.com/" + site.stores.snapshots_bucket,
              "storage.objects.get", "storage.objects.list")
    grant(ids.serving, "//storage.googleapis.com/" + site.stores.results_bucket, "storage.objects.get")
    grant(ids.supervisor, "//storage.googleapis.com/" + site.stores.results_bucket, "storage.objects.create")
    task_resource = f"projects/{t.project_id}/serviceAccounts/{ids.task_invoker}"
    grant(ids.controller, project_region + "/queues/" + site.queue.name, "cloudtasks.tasks.create")
    grant(ids.controller, task_resource, "iam.serviceAccounts.actAs")
    grant(ids.task_invoker, project_region + "/services/" + s.controller, "run.routes.invoke")
    grant(f"service-{t.project_number}@gcp-sa-cloudtasks.iam.gserviceaccount.com", task_resource,
          "iam.serviceAccounts.getOpenIdToken")
    common = {"DEPLOYMENT_ENV": "production", "AUTH_MODE": "required", "ENABLE_MOCK_LOGIN": "false",
              "INTERNAL_AUTH_ISSUER": site.browser.internal_issuer, "INTERNAL_AUTH_AUDIENCE": site.browser.internal_audience,
              "ENABLE_V1_RESEARCH_DISPATCH": "false", "ENABLE_V1_RESEARCH_CONTROLLER": "false",
              "ENABLE_V1_EXPERIMENT_DISPATCH": "false", "JOB_EXECUTION_MODE": "external"}
    front = {"name": "frontend", "image": s.serving_image, "ports": [{"containerPort": 8080}],
             "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
             "env": _env({**common, "AUTH_URL": t.public_origin, "API_BASE_URL": "http://127.0.0.1:8000",
                           "OIDC_PROVIDER_ID": "google", "OIDC_ISSUER": "https://accounts.google.com",
                           "OIDC_CLIENT_ID": site.browser.oauth_client_id}) + [
                 _secret_env("AUTH_SECRET", site.secrets.auth), _secret_env("INTERNAL_AUTH_SECRET", site.secrets.internal),
                 _secret_env("OIDC_CLIENT_SECRET", site.secrets.oauth)]}
    api = {"name": "api", "image": s.api_image,
           "resources": {"limits": {"cpu": "1", "memory": "1Gi"}},
           "env": _env({**common, "CORS_ORIGINS": t.public_origin}) + [
               _secret_env("INTERNAL_AUTH_SECRET", site.secrets.internal),
               _secret_env("DATABASE_URL", site.secrets.serving_database)]}
    controller = {"name": "controller", "image": s.controller_image, "ports": [{"containerPort": 8080}],
                  "resources": {"limits": {"cpu": "2", "memory": "2Gi"}},
                  "env": _env(common) + [_secret_env("DATABASE_URL", site.secrets.controller_database)]}
    return {
        "project": t.project_id, "project_number": t.project_number, "region": t.region, "zone": t.zone,
        "serving_name": project_region + "/services/" + s.serving,
        "controller_name": project_region + "/services/" + s.controller,
        "serving_identity": ids.serving, "controller_identity": ids.controller,
        "containers": [front, api], "controller_containers": [controller],
        "queue_name": project_region + "/queues/" + site.queue.name,
        "queue_rate": {"maxConcurrentDispatches": site.queue.max_concurrent_dispatches,
                       "maxDispatchesPerSecond": site.queue.max_dispatches_per_second},
        "queue_retry": {"maxAttempts": site.queue.max_attempts, "minBackoff": "10s", "maxBackoff": "300s", "maxDoublings": 4},
        "vpc": {"networkInterfaces": [{"network": t.network, "subnetwork": t.subnet}], "egress": "ALL_TRAFFIC"},
        "worker_name": site.worker.name, "machine_type": f"zones/{t.zone}/machineTypes/{site.worker.machine_type}",
        "boot_disk": [{"boot": True, "autoDelete": False, "initializeParams": {
            "sourceImage": site.worker.boot_image, "diskSizeGb": str(site.worker.boot_disk_gib), "diskType": f"zones/{t.zone}/diskTypes/pd-balanced"}}],
        "worker_network": [{"subnetwork": f"projects/{t.project_id}/regions/{t.region}/subnetworks/{t.subnet}", "accessConfigs": []}],
        "worker_identities": [{"email": ids.supervisor, "scopes": ["https://www.googleapis.com/auth/cloud-platform"]}],
        "stores": site.stores.model_dump(), "operations": site.operations.model_dump(),
        "browser": site.browser.model_dump(), "secrets": site.secrets.model_dump(),
        "identities": ids.model_dump(), "queue_delivery": site.queue.model_dump(),
        "scoped_grants": grants,
        "network_policy": {"project": t.project_id, "network": t.network, "subnet": t.subnet,
                           "subnet_cidr": t.subnet_cidr, "sql_private_service_access_cidr": t.sql_private_cidr,
                           "private_google_access": True, "external_worker_IP": False,
                           "legacy_peering_or_routes": [], "worker_inbound": "deny except separately reviewed private control/IAP operator path",
                           "trusted_host_egress": "reviewed Google API and OAuth endpoints only; actual DNS/firewall/proxy behavior remains not_run",
                           "guest_egress": "none"},
        "worker_policy": site.worker.model_dump(), "limits": RESOURCE_LIMITS,
        "capacity": {"per_user": 1, "global": 2, "authority": "C22 PostgreSQL reservation locks",
                     "queue_concurrency_is_capacity_authority": False},
        "gates": [{"gate": gate, "status": "not_run"} for gate in GATES],
        "origin": t.public_origin, "input_class": site.input_class,
    }


def _expand(value, values):
    if isinstance(value, dict):
        if set(value) == {"$value"}:
            try:
                return values[value["$value"]]
            except KeyError as exc:
                raise ConfigurationError("Unresolved template field") from exc
        return {key: _expand(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item, values) for item in value]
    return value


def render(site: Site):
    # Frozen Pydantic models can still contain mutable lists/dicts. Revalidate a
    # detached snapshot, including callers which used model_copy without checks.
    try:
        site = Site.model_validate(site.model_dump())
    except ValidationError as exc:
        raise ConfigurationError("Configuration changed after validation") from exc
    values = context(site)
    documents = {name + ".json": _expand(read_json(DIRECTORY / "templates" / (name + ".json")), values)
                 for name in TEMPLATES}
    for name, artifact in documents.items():
        if (artifact.get("version") != "c24-config-artifact-v1" or artifact.get("evidence_class") != "configuration-only"
                or artifact.get("provider_schema_validated") is not False or artifact.get("apply_allowed") is not False):
            raise ConfigurationError("A rendered artifact cannot claim live or provider authority")
        if name in {"serving.json", "controller.json"}:
            body = artifact["body"]
            expected = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" if name == "serving.json" else "INGRESS_TRAFFIC_INTERNAL_ONLY"
            public_frontend = name == "serving.json"
            if body["ingress"] != expected or body["invokerIamDisabled"] is not public_frontend:
                raise ConfigurationError("Cloud Run ingress and invocation must stay restricted")
            if body["template"]["scaling"] != {"minInstanceCount": 0, "maxInstanceCount": 1}:
                raise ConfigurationError("Keep serving/controller scale bounded")
            expected_containers = values["containers" if public_frontend else "controller_containers"]
            if (body["template"]["containers"] != expected_containers
                    or body["template"]["serviceAccount"] != values["serving_identity" if public_frontend else "controller_identity"]
                    or body["name"] != values["serving_name" if public_frontend else "controller_name"]
                    or body["template"]["vpcAccess"] != values["vpc"]
                    or body["defaultUriDisabled"] is not public_frontend):
                raise ConfigurationError("Serving images, secrets and identities must retain the exact binding")
        if name == "queue.json" and artifact["body"] != {
                "name": values["queue_name"], "rateLimits": values["queue_rate"],
                "retryConfig": values["queue_retry"], "stackdriverLoggingConfig": {"samplingRatio": 0.1}}:
            raise ConfigurationError("Queue identity, throttling and retries must retain the v1 binding")
        if name == "worker.json" and artifact["body"] != {
                "name": values["worker_name"], "machineType": values["machine_type"],
                "canIpForward": False, "deletionProtection": True, "disks": values["boot_disk"],
                "networkInterfaces": values["worker_network"], "serviceAccounts": values["worker_identities"],
                "scheduling": {"automaticRestart": False, "onHostMaintenance": "TERMINATE"},
                "metadata": {"items": [{"key": "enable-oslogin", "value": "TRUE"},
                                       {"key": "block-project-ssh-keys", "value": "TRUE"},
                                       {"key": "disable-legacy-endpoints", "value": "TRUE"}]},
                "shieldedInstanceConfig": {"enableSecureBoot": True, "enableVtpm": True, "enableIntegrityMonitoring": True}}:
            raise ConfigurationError("Worker identity, material and private startup configuration must remain exact")
    policy = documents["site-policy.json"]
    if (policy["live_dispatch_enabled"] is not False or policy["guest_network"] != "none"
            or policy["guest_credentials"] != [] or policy["writable_host_mounts"] != []
            or policy["guest_metadata"] is not False or policy["limits"] != RESOURCE_LIMITS
            or policy["gates"] != values["gates"] or policy["capacity"] != values["capacity"]
            or policy["browser"] != values["browser"] or policy["queue_delivery"] != values["queue_delivery"]
            or policy["worker_material"] != values["worker_policy"] or policy["network"] != values["network_policy"]
            or policy["public_origin"] != values["origin"] or policy["operations"] != values["operations"]
            or policy["activation"] != {"authenticated_v1_host": "unavailable", "real_Cloud_Tasks_adapter": "unavailable",
                                      "production_experiment_supervisor": "unavailable", "research_dispatch": False, "experiment_dispatch": False}
            or policy["supervisor"]["lease_expiry_releases_capacity"] is not False
            or policy["supervisor"]["production_daemon_or_dispatch_adapter_available"] is not False
            or policy["supervisor"]["release_authority"] != "C22 verified physical termination packet and independent durable proof"):
        raise ConfigurationError("Fixed sandbox and live gates cannot be widened")
    identities = documents["identity.json"]["body"]
    storage = documents["storage-database.json"]["body"]
    if (identities["project_wide_roles"] or identities["legacy_resource_grants"]
            or identities["public_worker_invokers"] or storage["database"]["private_ip_only"] is not True
            or storage["database"]["ssl_mode"] != "ENCRYPTED_ONLY"
            or storage["buckets"]["public_access_prevention"] != "enforced"
            or storage["buckets"]["public_grants"] or storage["automatic_results_deletion"] is not False):
        raise ConfigurationError("Identity/storage policy cannot expose or delete retained data")
    if (identities["scoped_permission_intents"] != values["scoped_grants"]
            or identities["project"] != values["project"] or identities["identities"] != values["identities"]
            or identities["secret_versions"] != values["secrets"] or storage["targets"] != values["stores"]
            or storage["project"] != values["project"]):
        raise ConfigurationError("Permission intents must bind the exact v1 resources")
    return documents


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def write_bundle(site, destination):
    documents = render(site)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ConfigurationError("Output must be a new directory with an existing parent")
    staging = Path(tempfile.mkdtemp(prefix=".c24-render-", dir=destination.parent))
    try:
        hashes = {}
        for name, document in documents.items():
            data = canonical(document)
            (staging / name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        manifest = {"version": "c24-rendered-bundle-v1", "evidence_class": "configuration-only",
                    "input_class": site.input_class, "input_sha256": hashlib.sha256(canonical(site.model_dump())).hexdigest(),
                    "files": hashes, "apply_allowed": False, "provider_schema_validated": False,
                    "live_gates": list(GATES)}
        (staging / "manifest.json").write_bytes(canonical(manifest))
        # Never replace an existing directory, including an unrelated empty directory.
        destination.mkdir(mode=0o700)
        for path in staging.iterdir():
            path.rename(destination / path.name)
    finally:
        shutil.rmtree(staging)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--output-dir", type=Path)
    mode.add_argument("--check-schema", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check_schema:
            if args.config or read_json(DIRECTORY / "site.schema.json") != Site.model_json_schema():
                raise ConfigurationError("Committed schema differs from the renderer")
        else:
            if not args.config:
                parser.error("--config is required")
            site = load_site(args.config)
            if args.check:
                render(site)
            else:
                write_bundle(site, args.output_dir)
    except (ConfigurationError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"C24 validation failed ({type(exc).__name__}); no live action was attempted.\n")
    print("C24 offline validation passed; live gates remain closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
