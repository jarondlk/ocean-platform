"""Pure mocked setup/renderer checks. No token, random secret or cloud call."""

from __future__ import annotations

import base64
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import google_crc32c

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
PACKAGE = ROOT / "deploy/gcp/beta/setup"
sys.path.insert(0, str(PACKAGE))
import prepare_credentials as credentials  # noqa: E402
import render_jobs as renderer  # noqa: E402


def record():
    return {
        "version": "beta-private-credentials-execution-v1",
        "state": "in_progress",
        "project_id": credentials.PROJECT,
        "project_number": credentials.NUMBER,
        "instance": credentials.INSTANCE,
        "database": credentials.DATABASE,
        "created_containers": [],
        "secret_versions": {},
        "phase": "initial",
    }


def fixture_values():
    values = iter(character * 64 for character in "ABCDE")
    return credentials.make_values(lambda: next(values))


class FakeApi:
    def __init__(self):
        self.project = {
            "projectId": credentials.PROJECT,
            "projectNumber": credentials.NUMBER,
            "lifecycleState": "ACTIVE",
        }
        self.instance = json.loads(
            (HERE.parent / "instance-final-readback.json").read_text()
        )
        self.secrets = {
            identifier: {
                "name": credentials.secret_name(identifier),
                "replication": {
                    "userManaged": {"replicas": [{"location": credentials.REGION}]}
                },
            }
            for identifier in credentials.IDS[:3]
        }
        self.versions = {}
        self.calls = []
        self.payloads = {}
        self.fail_add = None
        self.fail_password = False

    def request(self, method, url, body=None):
        self.calls.append((method, url))
        if method == "GET" and url == credentials.RM:
            return deepcopy(self.project)
        if (
            method == "GET"
            and url == credentials.SQL + "instances/" + credentials.INSTANCE
        ):
            return deepcopy(self.instance)
        if method == "GET" and "/databases/" in url:
            return {
                "project": credentials.PROJECT,
                "instance": credentials.INSTANCE,
                "name": credentials.DATABASE,
            }
        if url.startswith(credentials.SM):
            if method == "POST" and "?secretId=" in url:
                identifier = url.rsplit("=", 1)[1]
                self.secrets[identifier] = {
                    "name": credentials.secret_name(identifier),
                    "replication": body["replication"],
                }
                return deepcopy(self.secrets[identifier])
            if method == "GET" and "/versions?" in url:
                identifier = url.split("/secrets/", 1)[1].split("/", 1)[0]
                return (
                    {"versions": [deepcopy(self.versions[identifier])]}
                    if identifier in self.versions
                    else {}
                )
            if method == "POST" and url.endswith(":addVersion"):
                identifier = url.split("/secrets/", 1)[1].split(":", 1)[0]
                if identifier == self.fail_add:
                    raise credentials.ApiError(503)
                data = base64.b64decode(body["payload"]["data"])
                assert str(google_crc32c.value(data)) == body["payload"]["dataCrc32c"]
                self.payloads[identifier] = data.decode()
                self.versions[identifier] = {
                    "name": credentials.secret_name(identifier) + "/versions/1",
                    "state": "ENABLED",
                    "clientSpecifiedPayloadChecksum": True,
                }
                return deepcopy(self.versions[identifier])
            if method == "GET" and "/versions/" in url:
                identifier = url.split("/secrets/", 1)[1].split("/", 1)[0]
                return deepcopy(self.versions[identifier])
            identifier = url.rsplit("/", 1)[1]
            if identifier not in self.secrets:
                raise credentials.ApiError(404)
            return deepcopy(self.secrets[identifier])
        if method == "PUT" and "/users?name=postgres" in url:
            if self.fail_password:
                raise credentials.ApiError(503)
            assert body["name"] == "postgres"
            assert body["password"] == "C" * 64
            return {"name": "synthetic-operation"}
        if method == "GET" and "/operations/" in url:
            return {
                "name": "synthetic-operation",
                "targetProject": credentials.PROJECT,
                "targetId": credentials.INSTANCE,
                "operationType": "UPDATE_USER",
                "status": "DONE",
            }
        raise AssertionError("unexpected fake API request")


def run():
    passed = []

    def check(name, condition=True):
        assert condition, name
        passed.append(name)

    with (
        patch.object(
            credentials,
            "acquire_token",
            side_effect=AssertionError("token acquisition forbidden"),
        ),
        patch.object(
            credentials.secrets,
            "token_urlsafe",
            side_effect=AssertionError("real secret generation forbidden"),
        ),
    ):
        output = io.StringIO()
        with redirect_stdout(output):
            assert credentials.main([]) == 0
        check(
            "defaultplan performs no token acquisition, random generation or API call",
            json.loads(output.getvalue())["state"] == "plan_only",
        )
    api = FakeApi()
    result = record()
    snapshots = []
    credentials.install(
        api,
        result,
        lambda: snapshots.append(json.dumps(result)),
        token_factory=iter(character * 64 for character in "ABCDE").__next__,
        sleep=lambda seconds: None,
    )
    check(
        "all seven values retained before postgres password update",
        result["state"] == "credentials_installed"
        and len(result["secret_versions"]) == 7,
    )
    mutations = [(method, url) for method, url in api.calls if method != "GET"]
    check(
        "four empty containers created without runtime IAM or job mutations",
        sum("?secretId=" in url for _, url in mutations) == 4,
    )
    check(
        "password update is last mutation",
        mutations[-1]
        == (
            "PUT",
            credentials.SQL
            + "instances/"
            + credentials.INSTANCE
            + "/users?name=postgres",
        ),
    )
    check(
        "seven distinct version refs are numeric",
        all(
            value["name"].endswith("/versions/1")
            for value in result["secret_versions"].values()
        ),
    )
    values, postgres = fixture_values()
    check(
        "coupled payload values match exact predeclared synthetic inputs",
        api.payloads == values and postgres == "C" * 64,
    )
    check(
        "migrator and serving DSNs use corresponding password versions",
        api.payloads["ocean-v1-beta-migrator-password"]
        in api.payloads["ocean-v1-beta-migrator-database"]
        and api.payloads["ocean-v1-beta-serving-password"]
        in api.payloads["ocean-v1-beta-serving-database"],
    )
    check(
        "metadata snapshots contain no private values or base64 payloads",
        not any(
            value in "".join(snapshots)
            or base64.b64encode(value.encode()).decode() in "".join(snapshots)
            for value in values.values()
        ),
    )
    check(
        "helper never reads secret payloads",
        not any(":access" in url for _, url in api.calls),
    )
    changes = [
        (
            "wrong project number",
            lambda value: value.project.update(projectNumber="469489188516"),
        ),
        (
            "non-runnable SQL",
            lambda value: value.instance.update(state="PENDING_CREATE"),
        ),
        (
            "foreign SQL connection",
            lambda value: value.instance.update(connectionName="legacy"),
        ),
        (
            "public SQL",
            lambda value: value.instance["settings"]["ipConfiguration"].update(
                ipv4Enabled=True
            ),
        ),
        (
            "wrong SQL network",
            lambda value: value.instance["settings"]["ipConfiguration"].update(
                privateNetwork="legacy"
            ),
        ),
        (
            "missing SQL deletion protection",
            lambda value: value.instance["settings"].update(
                deletionProtectionEnabled=False
            ),
        ),
        (
            "disabled PITR",
            lambda value: value.instance["settings"]["backupConfiguration"].update(
                pointInTimeRecoveryEnabled=False
            ),
        ),
        (
            "wrong secret replicas",
            lambda value: value.secrets[credentials.IDS[0]].update(
                replication={"automatic": {}}
            ),
        ),
        (
            "existing destroyed version",
            lambda value: value.versions.update(
                {credentials.IDS[0]: {"name": "existing", "state": "DESTROYED"}}
            ),
        ),
    ]
    for name, change in changes:
        invalid = FakeApi()
        change(invalid)
        try:
            credentials.preflight(invalid)
        except credentials.SetupError:
            check(
                name + " rejects before any mutation",
                all(method == "GET" for method, _ in invalid.calls),
            )
        else:
            raise AssertionError(name)
    for failure in ("version", "password"):
        failing = FakeApi()
        if failure == "version":
            failing.fail_add = credentials.IDS[2]
        else:
            failing.fail_password = True
        partial = record()
        try:
            credentials.install(
                failing,
                partial,
                lambda: None,
                token_factory=iter(character * 64 for character in "ABCDE").__next__,
                sleep=lambda seconds: None,
            )
        except credentials.ApiError:
            check(
                failure + " failure remains partial and does not retry",
                partial.get("pending_mutation") is not None,
            )
        else:
            raise AssertionError("expected partial failure")
        if failure == "version":
            check(
                "partial version failure never changes postgres password",
                not any(method == "PUT" for method, _ in failing.calls),
            )
        before = len(failing.calls)
        try:
            credentials.preflight(failing)
        except credentials.SetupError:
            check(
                failure + " partial run cannot automatically resume",
                all(method == "GET" for method, _ in failing.calls[before:]),
            )
        else:
            raise AssertionError("partial resume accepted")
    with tempfile.TemporaryDirectory(
        prefix="ocean-beta-credential-metadata-"
    ) as temporary:
        destination = Path(temporary) / "receipt.json"
        failing = FakeApi()
        failing.fail_password = True
        output = io.StringIO()
        with (
            patch.object(credentials, "acquire_token", return_value="synthetic-token"),
            patch.object(credentials, "PrivateGoogleApi", return_value=failing),
            patch.object(credentials, "make_values", return_value=fixture_values()),
            patch.object(
                credentials.secrets,
                "token_urlsafe",
                side_effect=AssertionError("real generation forbidden"),
            ),
            redirect_stdout(output),
        ):
            code = credentials.main(
                [
                    "--apply",
                    "--receipt",
                    str(destination),
                    "--confirm-project",
                    credentials.PROJECT,
                    "--confirm-instance",
                    credentials.INSTANCE,
                ]
            )
        stored = json.loads(destination.read_text())
        check(
            "CLI partial failure persists only status and numeric refs",
            code == 2
            and stored["state"] == "failed_requires_manual_inspection"
            and stored["http_status"] == 503
            and len(stored["secret_versions"]) == 7
            and not any(value in destination.read_text() for value in values.values()),
        )
        before = destination.read_bytes()
        with (
            patch.object(
                credentials,
                "acquire_token",
                side_effect=AssertionError("must not acquire token"),
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = credentials.main(
                [
                    "--apply",
                    "--receipt",
                    str(destination),
                    "--confirm-project",
                    credentials.PROJECT,
                    "--confirm-instance",
                    credentials.INSTANCE,
                ]
            )
        check(
            "CLI never overwrites or automatically resumes an existing receipt",
            code == 2 and destination.read_bytes() == before,
        )
    for factory in (lambda: "short", lambda: "A" * 64):
        try:
            credentials.make_values(factory)
        except credentials.SetupError:
            check("invalid or duplicate value source rejects")
        else:
            raise AssertionError("unsafe value accepted")
    client = credentials.PrivateGoogleApi("synthetic-token")
    with patch.object(
        client._opener, "open", side_effect=AssertionError("network forbidden")
    ):
        for destination in (
            "http://secretmanager.googleapis.com/",
            credentials.RM + "-foreign",
            "https://example.invalid/",
        ):
            try:
                client.request("GET", destination)
            except credentials.SetupError:
                check("foreign or non-HTTPS destination rejected")
            else:
                raise AssertionError("unsafe API destination")
    image = (
        "asia-northeast1-docker.pkg.dev/"
        + credentials.PROJECT
        + "/ocean-v1-beta/operator@sha256:"
        + "0" * 64
    )
    jobs = renderer.render(image=image, receipt=result)
    for name, job in jobs.items():
        task = job["template"]["template"]
        containers = task["containers"]
        environment = containers[0]["env"]
        selected = {
            entry["valueSource"]["secretKeyRef"]["secret"]
            for entry in environment
            if "valueSource" in entry
        }
        stage = containers[0]["args"][0]
        check(
            stage + " job has bounded task and no execution token",
            task["maxRetries"] == 0
            and task["timeout"] == "600s"
            and job["template"]["taskCount"] == 1
            and job["template"]["parallelism"] == 1
            and "startExecutionToken" not in job
            and "runExecutionToken" not in job,
        )
        check(
            stage
            + " proxy has private fixed endpoints and required startup dependency",
            containers[0]["dependsOn"] == ["sql-proxy"]
            and containers[1]["image"] == renderer.PROXY
            and "--private-ip" in containers[1]["args"]
            and containers[1]["startupProbe"]["httpGet"]
            == {"path": "/readiness", "port": 9090},
        )
        check(
            stage + " job mounts only stage credentials",
            selected
            == (
                {
                    "ocean-v1-beta-bootstrap-database",
                    "ocean-v1-beta-migrator-password",
                    "ocean-v1-beta-serving-password",
                }
                if stage == "bootstrap"
                else {"ocean-v1-beta-bootstrap-database"}
                if stage == "readback"
                else {"ocean-v1-beta-migrator-database"}
            ),
        )
        check(
            stage + " has explicit isolated DirectVPC and SA",
            task["vpcAccess"]["egress"] == "PRIVATE_RANGES_ONLY"
            and task["serviceAccount"].endswith(
                "@" + credentials.PROJECT + ".iam.gserviceaccount.com"
            ),
        )
    for invalid_image in (
        image.replace(credentials.PROJECT, "data-infra-infobio"),
        image.split("@")[0] + ":latest",
    ):
        try:
            renderer.render(image=invalid_image, receipt=result)
        except ValueError:
            check("foreign or mutable image rejected")
        else:
            raise AssertionError("unsafe image accepted")
    for modified in (dict(result, state="failed"), deepcopy(result)):
        if modified.get("state") == "credentials_installed":
            modified["secret_versions"][credentials.IDS[0]]["name"] = (
                credentials.secret_name(credentials.IDS[0]) + "/versions/latest"
            )
        try:
            renderer.render(image=image, receipt=modified)
        except ValueError:
            check("partial or mutable secret receipt rejected")
        else:
            raise AssertionError("unsafe refs accepted")
    return {
        "version": "beta-private-setup-pure-checks-v1",
        "passed": len(passed),
        "checks": passed,
        "live_cloud_calls": False,
        "real_secret_or_token_generation": False,
        "fixtures": "deterministic synthetic values only",
    }, jobs


if __name__ == "__main__":
    result, jobs = run()
    print(json.dumps(result, indent=2))
