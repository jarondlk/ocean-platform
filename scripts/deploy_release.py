#!/usr/bin/env python3
"""Manual, code-only Cloud Run release deployment using short-lived credentials."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request

PROJECT = "data-infra-infobio"
REGION = "asia-northeast1"
SERVICE = "ocean-platform"
REPOSITORY = "jarondlk/ocean-platform"
BUILD_ACCOUNT = f"ocean-release-build@{PROJECT}.iam.gserviceaccount.com"
JOBS = ("ocean-migrate", "ocean-pipeline", "ocean-embedding", "ocean-evaluation", "ocean-anemone-process")
# Changes in these paths require a coordinated data/schema rollout, not this workflow.
DATA_PATHS = ("db", "schema", "migrations", "alembic.ini", "preprocessing", "ingestion",
              "scripts/bootstrap_database.py", "scripts/materialize_edna_retrieval.py",
              "scripts/load_db.py", "scripts/run_anemone_job.py", "scripts/run_edna_analysis.py",
              "retrieval/edna_document_builder.py", "retrieval/edna_materializer.py",
              "retrieval/edna_publication.py", "retrieval/document_builder.py",
              "api/provenance_snapshot_service.py", "scripts/update_embeddings.py")
TERMINAL_BUILD = {"FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED", "EXPIRED"}


class DeploymentError(RuntimeError):
    """A release failed validation or a deployment gate."""


def run(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False, timeout=360)
    if result.returncode:
        # Do not echo command arguments, credentials, or raw cloud configuration.
        raise DeploymentError(f"{args[0]} {args[1]} failed (exit {result.returncode}); {result.stderr[-1800:]}")
    return result.stdout


def cloud(*args: str) -> dict | list:
    args = list(args)
    split = next((i for i, arg in enumerate(args) if arg.startswith("--container=")), len(args))
    return json.loads(run(["gcloud", *args[:split], f"--project={PROJECT}", "--format=json", "--quiet", *args[split:]]))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def github(route: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/{route}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "OCEAN-deploy-release"},
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise DeploymentError(f"GitHub {route.split('/')[0]} returned HTTP {error.code}") from None


def validate_tag(tag: str) -> str:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise DeploymentError("Choose a stable release tag such as v0.4.5.")
    return tag


def source_commit(containers: list[dict]) -> str:
    commits = {entry.get("value") for container in containers for entry in container.get("env", [])
               if entry["name"] == "SOURCE_COMMIT"}
    if len(commits) != 1 or not re.fullmatch(r"[a-f0-9]{40}", next(iter(commits), "") or ""):
        raise DeploymentError("Existing containers must agree on a full SOURCE_COMMIT.")
    if not all(any(e["name"] == "SOURCE_COMMIT" for e in c.get("env", [])) for c in containers):
        raise DeploymentError("A container is missing SOURCE_COMMIT.")
    return commits.pop()


def service_spec(service: dict) -> dict:
    spec = copy.deepcopy(service["spec"]["template"]["spec"])
    for container in spec["containers"]:
        container.pop("image", None)
        container["env"] = [e for e in container.get("env", []) if e["name"] != "SOURCE_COMMIT"]
    return spec


def traffic_map(service: dict) -> dict[str, int]:
    traffic = {t["revisionName"]: t["percent"] for t in service["status"]["traffic"] if t.get("percent", 0)}
    if sum(traffic.values()) != 100:
        raise DeploymentError("Cannot resolve the existing production traffic allocation.")
    return traffic


def image_digests(build: dict) -> dict[str, str]:
    if build.get("status") != "SUCCESS":
        raise DeploymentError("The build must succeed before images can be deployed.")
    expected = f"{REGION}-docker.pkg.dev/{PROJECT}/ocean-platform/"
    images = {}
    for item in build.get("results", {}).get("images", []):
        for name in ("api", "frontend"):
            if item["name"] == f"{expected}{name}:{build['id']}" and re.fullmatch(r"sha256:[a-f0-9]{64}", item["digest"]):
                images[name] = expected + name + "@" + item["digest"]
    if set(images) != {"api", "frontend"}:
        raise DeploymentError("Build results are missing the expected immutable API/frontend images.")
    return images


def check_service(service: dict) -> None:
    containers = {c["name"]: c for c in service["spec"]["template"]["spec"]["containers"]}
    if set(containers) != {"api", "frontend"}:
        raise DeploymentError("Unexpected serving topology.")
    settings = {e["name"]: e.get("value") for e in containers["api"]["env"]}
    if any(settings.get(k) != v for k, v in {"AUTH_MODE": "required", "JOB_EXECUTION_MODE": "external", "PROVENANCE_READ_MODE": "snapshot"}.items()):
        raise DeploymentError("Production authentication/job/provenance boundaries are not configured as expected.")
    source_commit(list(containers.values()))
    traffic_map(service)


def smoke(base: str) -> list[dict]:
    checks = []
    for path, expected in (("/login", 200), ("/api/auth/session", 200), ("/manifest.webmanifest", 200),
                           ("/api/backend/health", 401), ("/api/backend/data/edna/samples", 401),
                           ("/api/backend/provenance/manifest", 401)):
        request = urllib.request.Request(base.rstrip("/") + path)
        try:
            response = urllib.request.build_opener(NoRedirect).open(request, timeout=45)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            response.read()
        if status != expected:
            raise DeploymentError(f"Smoke check {path}: expected {expected}, received {status}")
        checks.append({"path": path, "status": status})
    return checks


class Release:
    def __init__(self, state_dir: Path):
        self.root = state_dir
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "state.json"
        self.state = json.loads(path.read_text()) if path.exists() else {}

    def save(self) -> None:
        (self.root / "state.json").write_text(json.dumps(self.state, indent=2))

    def summary(self, message: str) -> None:
        print(message, flush=True)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
                output.write(message + "\n\n")

    def describe(self) -> dict:
        return cloud("run", "services", "describe", SERVICE, f"--region={REGION}")

    def preflight(self, tag: str) -> None:
        validate_tag(tag)
        release = github("releases/tags/" + tag)
        if release.get("draft") or release.get("prerelease") or not release.get("published_at") or release["tag_name"] != tag:
            raise DeploymentError("Only a published stable GitHub release can be deployed.")
        sha = run(["git", "rev-parse", f"refs/tags/{tag}^{{commit}}"] ).strip()
        run(["git", "merge-base", "--is-ancestor", sha, "origin/main"])
        before = self.describe()
        check_service(before)
        traffic = traffic_map(before)
        # Compare the actual serving revision(s), not a possibly failed latest candidate.
        live_commits = set()
        for revision in traffic:
            data = cloud("run", "revisions", "describe", revision, f"--region={REGION}")
            live_commits.add(source_commit(data["spec"]["containers"]))
        for live in live_commits:
            changed = run(["git", "diff", "--name-only", live, sha, "--", *DATA_PATHS]).strip()
            if changed:
                raise DeploymentError("This release changes database or data-generation code; use a coordinated rollout.\n" + changed)
        self.state = {"tag": tag, "sha": sha, "before": before, "traffic": traffic, "jobs": {}, "job_updates": []}
        for name in JOBS:
            job = cloud("run", "jobs", "describe", name, f"--region={REGION}")
            containers = job["spec"]["template"]["spec"]["template"]["spec"]["containers"]
            if len(containers) != 1:
                raise DeploymentError(f"Unexpected container topology for {name}.")
            source_commit(containers)
            self.state["jobs"][name] = job
        self.save()
        self.summary(f"Validated **{tag}** (`{sha}`). Existing traffic and data/schema compatibility verified. No resources changed.")

    def build(self) -> None:
        source = self.root / "source"
        source.mkdir()
        archive = self.root / "source.tar"
        run(["git", "archive", "--format=tar", "-o", str(archive), self.state["sha"]])
        run(["tar", "-xf", str(archive), "-C", str(source)])
        data = cloud("builds", "submit", str(source), "--config=" + str(source / "cloudbuild.yaml"),
                     "--service-account=projects/" + PROJECT + "/serviceAccounts/" + BUILD_ACCOUNT,
                     "--gcs-source-staging-dir=gs://" + PROJECT + "_cloudbuild/source", "--async")
        self.state["build_id"] = data["id"]
        self.save()
        deadline = time.monotonic() + 2700
        while time.monotonic() < deadline:
            data = cloud("builds", "describe", self.state["build_id"])
            if data["status"] == "SUCCESS":
                self.state["images"] = image_digests(data)
                self.save()
                self.summary(f"Cloud Build `{data['id']}` passed; immutable API and frontend digests recorded.")
                return
            if data["status"] in TERMINAL_BUILD:
                raise DeploymentError("Cloud Build ended with " + data["status"])
            time.sleep(15)
        raise DeploymentError("Build wait timed out; inspect the recorded Cloud Build before retrying.")

    def job(self, name: str, args: list[str]) -> None:
        execution = cloud("run", "jobs", "execute", name, f"--region={REGION}", "--async", "--args=" + ",".join(args))
        execution_name = execution["metadata"]["name"]
        self.summary(f"Started `{execution_name}`.")
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            result = cloud("run", "jobs", "executions", "describe", execution_name, f"--region={REGION}")
            completed = next((c for c in result["status"].get("conditions", []) if c["type"] == "Completed"), {})
            if completed.get("status") == "True":
                self.summary(f"Execution `{execution_name}` succeeded.")
                return
            if completed.get("status") == "False" or result["status"].get("failedCount"):
                raise DeploymentError(f"Execution {execution_name} failed.")
            time.sleep(10)
        raise DeploymentError(f"Execution {execution_name} timed out; inspect it before retrying.")

    def update_job(self, name: str, image: str, sha: str) -> None:
        cloud("run", "jobs", "update", name, f"--region={REGION}", "--image=" + image, "--update-env-vars=SOURCE_COMMIT=" + sha)

    def traffic(self, mapping: dict[str, int]) -> None:
        cloud("run", "services", "update-traffic", SERVICE, f"--region={REGION}",
              "--to-revisions=" + ",".join(f"{r}={p}" for r, p in mapping.items()))

    def deploy(self) -> None:
        current = self.describe()
        if current["metadata"]["resourceVersion"] != self.state["before"]["metadata"]["resourceVersion"]:
            raise DeploymentError("Service changed after preflight; rerun validation before deploying.")
        # Existing jobs must also be unchanged before any release mutation.
        for name, before in self.state["jobs"].items():
            now = cloud("run", "jobs", "describe", name, f"--region={REGION}")
            if now["metadata"]["resourceVersion"] != before["metadata"]["resourceVersion"]:
                raise DeploymentError(f"Job {name} changed after preflight.")
        self.job("ocean-pipeline", ["scripts/database_backup.py", "create", "--output-dir", "/mnt/ocean-data/backups",
                                    "--label", self.state["tag"] + "-github-pre-deploy", "--restore-test"])
        suffix = "r" + os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
        revision = SERVICE + "-" + suffix
        self.state["revision"] = revision
        self.save()
        cloud("run", "services", "update", SERVICE, f"--region={REGION}", "--no-traffic", "--revision-suffix=" + suffix,
              "--tag=release-candidate", "--container=frontend", "--image=" + self.state["images"]["frontend"],
              "--update-env-vars=SOURCE_COMMIT=" + self.state["sha"], "--container=api", "--image=" + self.state["images"]["api"],
              "--update-env-vars=SOURCE_COMMIT=" + self.state["sha"])
        current = self.describe()
        if current["status"].get("latestReadyRevisionName") != revision:
            raise DeploymentError("The candidate is not ready.")
        if service_spec(current) != service_spec(self.state["before"]) or traffic_map(current) != self.state["traffic"]:
            raise DeploymentError("Candidate changed runtime configuration or production traffic unexpectedly.")
        candidate = next(t["url"] for t in current["status"]["traffic"] if t.get("tag") == "release-candidate" and t["revisionName"] == revision)
        self.state["candidate_smoke"] = smoke(candidate)
        self.state["candidate_version"] = current["metadata"]["resourceVersion"]
        self.save()
        try:
            for name in JOBS:
                self.state["job_updates"].append(name)
                self.save()  # Persist before mutation, including ambiguous command failures.
                self.update_job(name, self.state["images"]["api"], self.state["sha"])
            self.job("ocean-migrate", ["scripts/bootstrap_database.py", "--check-only", "--json"])
            if self.describe()["metadata"]["resourceVersion"] != self.state["candidate_version"]:
                raise DeploymentError("Service changed during candidate validation; production promotion stopped.")
            self.state["promotion_attempted"] = True
            self.save()
            self.traffic({revision: 100})
            current = self.describe()
            if traffic_map(current) != {revision: 100}:
                raise DeploymentError("Production traffic verification failed.")
            self.state["production_smoke"] = smoke("https://oceaninfobio.com")
            self.state["deployed"] = True
            self.save()
        except Exception:
            self.rollback()
            raise
        self.summary(f"**{self.state['tag']} deployed**: `{revision}` receives 100% traffic. Candidate and production smoke checks passed. Data and schema were not migrated.")

    def record(self) -> None:
        if not self.state.get("deployed"):
            raise DeploymentError("Cannot record success before deployment completes.")
        deployment = github("deployments", {
            "ref": self.state["sha"], "environment": "production", "auto_merge": False,
            "required_contexts": [], "production_environment": True,
            "description": self.state["tag"] + " deployed by manual workflow",
        })
        github(f"deployments/{deployment['id']}/statuses", {
            "state": "success", "environment": "production", "auto_inactive": True,
            "environment_url": "https://oceaninfobio.com",
            "log_url": f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
            "description": "Candidate and production smoke passed; 100% traffic on release revision.",
        })
        self.summary(f"GitHub deployment `{deployment['id']}` records the exact release commit.")

    def rollback(self) -> None:
        if self.state.get("deployed") or self.state.get("rollback_complete"):
            return
        failures = []
        if self.state.get("promotion_attempted"):
            try:
                current = traffic_map(self.describe())
                if current not in (self.state["traffic"], {self.state["revision"]: 100}):
                    raise DeploymentError("Traffic was changed by another operator; automatic rollback stopped.")
                self.traffic(self.state["traffic"])
            except Exception:
                failures.append("traffic")
        for name in reversed(self.state.get("job_updates", [])):
            container = self.state["jobs"][name]["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]
            try:
                self.update_job(name, container["image"], source_commit([container]))
            except Exception:
                failures.append(name)
        self.state["rollback_complete"] = not failures
        self.state["rollback_failures"] = failures
        self.save()
        self.summary("Rollback needs operator attention: " + ", ".join(failures) if failures else "Previous traffic and job images restored after failed promotion.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preflight", "build", "deploy", "record", "rollback"))
    parser.add_argument("--tag")
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    release = Release(args.state_dir)
    if args.phase == "preflight":
        release.preflight(args.tag or "")
    else:
        getattr(release, args.phase)()


if __name__ == "__main__":
    main()
