"""Concrete new-beta credential installation; default is a static read-only plan.

No values, tokens, request/response bodies or secret hashes enter receipts.
Mutations have no automatic retry. Partial/uncertain outcomes require manual
inspection; this helper has no resume, overwrite, rotation or cleanup command.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request

import google_crc32c

PROJECT = "ocean-v1-beta-20261101"
NUMBER = "534831104543"
REGION = "asia-northeast1"
INSTANCE = "ocean-v1-beta-sql"
DATABASE = "ocean_v1_beta"
CONNECTION = PROJECT + ":" + REGION + ":" + INSTANCE
SM = "https://secretmanager.googleapis.com/v1/"
SQL = "https://sqladmin.googleapis.com/sql/v1beta4/projects/" + PROJECT + "/"
RM = "https://cloudresourcemanager.googleapis.com/v1/projects/" + PROJECT
EXISTING = ("auth", "internal", "serving-database")
NEW = (
    "bootstrap-database",
    "migrator-database",
    "migrator-password",
    "serving-password",
)
IDS = tuple("ocean-v1-beta-" + name for name in EXISTING + NEW)


class SetupError(ValueError):
    """Only fixed, credential-safe diagnostics belong in this exception."""


class ApiError(SetupError):
    def __init__(self, status):
        self.status = status
        super().__init__(
            "Google API request failed; inspect non-secret status metadata"
        )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


class PrivateGoogleApi:
    def __init__(self, token):
        self._token = token
        self._opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, url, body=None):
        if url != RM and not url.startswith((SM + "projects/" + NUMBER + "/", SQL)):
            raise SetupError("Unexpected API destination rejected")
        payload = (
            None if body is None else json.dumps(body, separators=(",", ":")).encode()
        )
        request = urllib.request.Request(
            url,
            data=payload,
            method=method,
            headers={
                "Authorization": "Bearer " + self._token,
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                data = response.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise SetupError("Unexpected API response size")
                return json.loads(data)
        except urllib.error.HTTPError as error:
            raise ApiError(error.code) from None
        except SetupError:
            raise
        except Exception:
            raise SetupError(
                "Google API transport failed; operation outcome may require inspection"
            ) from None


def acquire_token():
    try:
        child = subprocess.run(
            ["gcloud", "auth", "print-access-token", "--project=" + PROJECT, "--quiet"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        token = child.stdout.strip()
        if child.returncode or not re.fullmatch(r"[A-Za-z0-9._~-]{20,8192}", token):
            raise ValueError()
        return token
    except Exception:
        raise SetupError("A working authorized GCP CLI login is required") from None


def secret_name(identifier):
    if identifier not in IDS:
        raise SetupError("Unexpected secret identifier")
    return "projects/" + NUMBER + "/secrets/" + identifier


def check_sql(document):
    settings = document.get("settings", {})
    ip = settings.get("ipConfiguration", {})
    backup = settings.get("backupConfiguration", {})
    scalar = {
        "project": PROJECT,
        "name": INSTANCE,
        "connectionName": CONNECTION,
        "databaseVersion": "POSTGRES_16",
        "region": REGION,
        "gceZone": REGION + "-a",
        "state": "RUNNABLE",
    }
    wanted = {
        "edition": "ENTERPRISE",
        "availabilityType": "ZONAL",
        "tier": "db-custom-2-7680",
        "dataDiskType": "PD_SSD",
        "dataDiskSizeGb": "20",
        "storageAutoResize": True,
        "storageAutoResizeLimit": "30",
        "deletionProtectionEnabled": True,
        "connectorEnforcement": "REQUIRED",
    }
    if (
        any(document.get(key) != value for key, value in scalar.items())
        or any(settings.get(key) != value for key, value in wanted.items())
        or ip.get("ipv4Enabled") is not False
        or ip.get("authorizedNetworks", []) != []
        or ip.get("privateNetwork")
        != "projects/" + PROJECT + "/global/networks/ocean-v1-beta-network"
        or ip.get("sslMode") != "ENCRYPTED_ONLY"
        or backup.get("enabled") is not True
        or backup.get("pointInTimeRecoveryEnabled") is not True
        or backup.get("transactionLogRetentionDays") != 7
        or backup.get("location") != REGION
        or backup.get("backupRetentionSettings")
        != {"retainedBackups": 7, "retentionUnit": "COUNT"}
    ):
        raise SetupError(
            "Actual private SQL settings do not match the reviewed beta target"
        )
    addresses = document.get("ipAddresses", [])
    try:
        if not addresses or any(
            item.get("type") != "PRIVATE"
            or ipaddress.ip_address(item["ipAddress"])
            not in ipaddress.ip_network("10.93.0.0/20")
            for item in addresses
        ):
            raise ValueError()
    except Exception:
        raise SetupError(
            "SQL must have only the reviewed private address range"
        ) from None


def check_secret(document, identifier):
    if document.get("name") != secret_name(identifier) or document.get(
        "replication"
    ) != {"userManaged": {"replicas": [{"location": REGION}]}}:
        raise SetupError("Secret ownership or exact Tokyo replication mismatch")


def no_versions(api, identifier):
    result = api.request("GET", SM + secret_name(identifier) + "/versions?pageSize=1")
    if result.get("versions") or result.get("nextPageToken"):
        raise SetupError(
            "Existing secret versions forbid automatic installation or resume"
        )


def preflight(api):
    project = api.request("GET", RM)
    if (
        project.get("projectId") != PROJECT
        or str(project.get("projectNumber")) != NUMBER
        or project.get("lifecycleState") != "ACTIVE"
    ):
        raise SetupError("Exact active beta project and number required")
    check_sql(api.request("GET", SQL + "instances/" + INSTANCE))
    database = api.request(
        "GET", SQL + "instances/" + INSTANCE + "/databases/" + DATABASE
    )
    if (
        database.get("project") != PROJECT
        or database.get("instance") != INSTANCE
        or database.get("name") != DATABASE
    ):
        raise SetupError("Exact independent database must already exist")
    missing = []
    for identifier in IDS:
        try:
            result = api.request("GET", SM + secret_name(identifier))
        except ApiError as error:
            if error.status == 404 and identifier in tuple(
                "ocean-v1-beta-" + name for name in NEW
            ):
                missing.append(identifier)
                continue
            raise
        check_secret(result, identifier)
        no_versions(api, identifier)
    return missing


def make_values(token_factory=None):
    factory = (
        token_factory
        if token_factory is not None
        else lambda: secrets.token_urlsafe(48)
    )
    random_values = []
    for _ in range(5):
        candidate = factory()
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{64}", candidate)
            or candidate in random_values
        ):
            raise SetupError("Independent URL-safe 64-character values required")
        random_values.append(candidate)
    auth, internal, postgres, migrator, serving = random_values

    def dsn(user, password):
        return (
            "postgresql+psycopg2://"
            + user
            + ":"
            + password
            + "@127.0.0.1:5432/"
            + DATABASE
        )

    values = dict(
        zip(
            IDS,
            (
                auth,
                internal,
                dsn("ocean_v1_serving", serving),
                dsn("postgres", postgres),
                dsn("ocean_v1_migrator", migrator),
                migrator,
                serving,
            ),
        )
    )
    return values, postgres


def install(api, record, persist, token_factory=None, sleep=time.sleep):
    record["phase"] = "preflight"
    persist()
    missing = preflight(api)
    record["preflight_verified"] = True
    persist()
    for identifier in missing:
        record["phase"], record["pending_mutation"] = "create_container", identifier
        persist()
        result = api.request(
            "POST",
            SM + "projects/" + NUMBER + "/secrets?secretId=" + identifier,
            {
                "replication": {"userManaged": {"replicas": [{"location": REGION}]}},
                "labels": {
                    "environment": "beta",
                    "managed-by": "overhaul",
                    "system": "ocean-v1",
                },
            },
        )
        check_secret(result, identifier)
        record["created_containers"].append(identifier)
        record.pop("pending_mutation", None)
        persist()
    # Re-read every replica policy/version inventory before generating any value.
    if preflight(api):
        raise SetupError(
            "All seven exact empty containers must be verified before value generation"
        )
    record["phase"] = "install_versions"
    persist()
    values, postgres = make_values(token_factory)
    try:
        for identifier in IDS:
            no_versions(api, identifier)
            record["pending_mutation"] = identifier + ":addVersion"
            persist()
            data = values[identifier].encode()
            version = api.request(
                "POST",
                SM + secret_name(identifier) + ":addVersion",
                {
                    "payload": {
                        "data": base64.b64encode(data).decode(),
                        "dataCrc32c": str(google_crc32c.value(data)),
                    }
                },
            )
            name = version.get("name", "")
            if (
                not re.fullmatch(
                    re.escape(secret_name(identifier)) + r"/versions/[1-9][0-9]*", name
                )
                or version.get("state") != "ENABLED"
                or version.get("clientSpecifiedPayloadChecksum") is not True
            ):
                raise SetupError(
                    "Secret version ownership/state/checksum acknowledgement mismatch"
                )
            checked = api.request("GET", SM + name)
            if checked.get("name") != name or checked.get("state") != "ENABLED":
                raise SetupError("Secret version metadata readback mismatch")
            record["secret_versions"][identifier] = {"name": name, "state": "ENABLED"}
            record.pop("pending_mutation", None)
            persist()
        # Last mutation: never set postgres until every coupled value is retained.
        record["phase"], record["pending_mutation"] = (
            "set_postgres_password",
            "new_beta_postgres_password",
        )
        persist()
        operation = api.request(
            "PUT",
            SQL + "instances/" + INSTANCE + "/users?name=postgres",
            {"name": "postgres", "password": postgres},
        )
        name = operation.get("name", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name):
            raise SetupError("SQL password operation identity rejected")
        record["postgres_password_operation"] = name
        persist()
        for _ in range(120):
            observed = api.request("GET", SQL + "operations/" + name)
            if (
                observed.get("name") != name
                or observed.get("targetProject") != PROJECT
                or observed.get("targetId") != INSTANCE
                or observed.get("operationType") != "UPDATE_USER"
            ):
                raise SetupError("SQL password operation target mismatch")
            if observed.get("status") == "DONE":
                if observed.get("error"):
                    raise SetupError(
                        "SQL password operation failed; inspect metadata before recovery"
                    )
                record.pop("pending_mutation", None)
                record["state"], record["phase"] = "credentials_installed", "completed"
                persist()
                return
            sleep(2)
        raise SetupError(
            "SQL password operation is still pending; manual inspection required"
        )
    finally:
        # Do not claim in-process immutable strings can be securely zeroed.
        values.clear()
        postgres = None


def plan():
    return {
        "version": "beta-private-credentials-plan-v1",
        "state": "plan_only",
        "project_id": PROJECT,
        "project_number": NUMBER,
        "instance": INSTANCE,
        "database": DATABASE,
        "existing_empty_containers": ["ocean-v1-beta-" + name for name in EXISTING],
        "new_containers_if_absent": ["ocean-v1-beta-" + name for name in NEW],
        "values_installed": list(IDS),
        "postgres_password_update": "last mutation after seven verified versions",
        "value_generation": False,
        "token_acquisition": False,
        "cloud_calls": False,
        "automatic_retry_resume_overwrite": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--confirm-project")
    parser.add_argument("--confirm-instance")
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps(plan(), indent=2))
        return 0
    if (
        args.confirm_project != PROJECT
        or args.confirm_instance != INSTANCE
        or args.receipt is None
        or args.receipt.exists()
        or args.receipt.is_symlink()
    ):
        print("Exact beta confirmations and a new metadata receipt path are required")
        return 2
    record = {
        "version": "beta-private-credentials-execution-v1",
        "state": "in_progress",
        "project_id": PROJECT,
        "project_number": NUMBER,
        "instance": INSTANCE,
        "database": DATABASE,
        "created_containers": [],
        "secret_versions": {},
        "phase": "initial",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "manual_inspection_required_after_any_failure": True,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the receipt exclusively before acquiring credentials or making calls.
    with args.receipt.open("x") as output:
        output.write(json.dumps(record, indent=2) + "\n")

    def persist():
        args.receipt.write_text(json.dumps(record, indent=2) + "\n")

    try:
        api = PrivateGoogleApi(acquire_token())
        install(api, record, persist)
        print(
            json.dumps(
                {
                    "state": record["state"],
                    "receipt": str(args.receipt),
                    "secret_version_count": len(record["secret_versions"]),
                }
            )
        )
        return 0
    except Exception as error:
        record["state"] = "failed_requires_manual_inspection"
        record["error"] = (
            str(error)
            if isinstance(error, SetupError)
            else "Credential setup failed; retain metadata and inspect before recovery"
        )
        if isinstance(error, ApiError):
            record["http_status"] = error.status
        persist()
        print(
            json.dumps(
                {
                    "state": record["state"],
                    "phase": record["phase"],
                    "receipt": str(args.receipt),
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
