"""Render private Cloud Run v2 jobs from exact images and installed secret refs.

This script has no API/SDK/token/credential-generation or execution operation.
The JSON files are v2 REST Job bodies, not gcloud v1 replace manifests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from prepare_credentials import (
    PROJECT,
    NUMBER,
    REGION,
    INSTANCE,
    DATABASE,
    CONNECTION,
    IDS,
)

API_REVISION = "7924a28e919b1fb751890c694f7b1f9b26b104ff"
OPERATOR_REVISION = "756c7a7dc46d4ba75e3a0308b7ab23d9b3553bfe"
PROXY = "gcr.io/cloud-sql-connectors/cloud-sql-proxy@sha256:f333a9c59890c3c67b8505166c5dbdcc0b29fca9173a2e09ca0446ab6997a736"


def render(*, image, receipt):
    if not re.fullmatch(
        r"asia-northeast1-docker\.pkg\.dev/"
        + PROJECT
        + r"/ocean-v1-beta/operator@sha256:[a-f0-9]{64}",
        image,
    ):
        raise ValueError("Exact independent operator image digest required")
    if (
        receipt.get("version") != "beta-private-credentials-execution-v1"
        or receipt.get("state") != "credentials_installed"
        or receipt.get("project_id") != PROJECT
        or receipt.get("project_number") != NUMBER
        or receipt.get("instance") != INSTANCE
        or receipt.get("database") != DATABASE
        or set(receipt.get("secret_versions", {})) != set(IDS)
    ):
        raise ValueError("Completed exact beta metadata receipt required")
    versions = {}
    for identifier in IDS:
        entry = receipt["secret_versions"][identifier]
        match = re.fullmatch(
            r"projects/"
            + NUMBER
            + "/secrets/"
            + identifier
            + r"/versions/([1-9][0-9]*)",
            entry.get("name", ""),
        )
        if not match or entry.get("state") != "ENABLED":
            raise ValueError("Explicit numeric enabled secret versions required")
        versions[identifier] = match.group(1)
    jobs = {}
    for stage in ("bootstrap", "migrate", "finalize", "readback"):
        bootstrap = stage in {"bootstrap", "readback"}
        identity = (
            "ocean-v1-beta-db-bootstrap" if bootstrap else "ocean-v1-beta-db-migrator"
        )
        common = {
            "DEPLOYMENT_ENV": "production",
            "OCEAN_V1_PROJECT_ID": PROJECT,
            "OCEAN_V1_SQL_CONNECTION_NAME": CONNECTION,
            "OCEAN_V1_SOURCE_REVISION": API_REVISION,
            "OCEAN_V1_OPERATOR_REVISION": OPERATOR_REVISION,
            "ENABLE_V1_RESEARCH_CONTROLLER": "false",
            "ENABLE_V1_RESEARCH_DISPATCH": "false",
            "ENABLE_V1_SYNTHESIS": "false",
            "ENABLE_V1_EXPERIMENT_DISPATCH": "false",
        }
        env = [{"name": name, "value": value} for name, value in common.items()]
        selected = {
            "OCEAN_V1_OPERATOR_DATABASE_URL": "ocean-v1-beta-bootstrap-database"
            if bootstrap
            else "ocean-v1-beta-migrator-database"
        }
        if stage == "bootstrap":
            selected.update(
                OCEAN_V1_MIGRATOR_PASSWORD="ocean-v1-beta-migrator-password",
                OCEAN_V1_SERVING_PASSWORD="ocean-v1-beta-serving-password",
            )
        env.extend(
            {
                "name": name,
                "valueSource": {
                    "secretKeyRef": {
                        "secret": identifier,
                        "version": versions[identifier],
                    }
                },
            }
            for name, identifier in selected.items()
        )
        operator = {
            "name": "operator",
            "image": image,
            "args": [
                stage,
                "--confirm-project",
                PROJECT,
                "--confirm-database",
                DATABASE,
                "--confirm-source",
                API_REVISION,
                "--confirm-operator",
                OPERATOR_REVISION,
            ],
            "env": env,
            "resources": {"limits": {"cpu": "1", "memory": "1Gi"}},
            "dependsOn": ["sql-proxy"],
        }
        proxy = {
            "name": "sql-proxy",
            "image": PROXY,
            "args": [
                "--private-ip",
                "--address=127.0.0.1",
                "--port=5432",
                "--quitquitquit",
                "--admin-port=9091",
                "--health-check",
                "--http-address=0.0.0.0",
                "--http-port=9090",
                CONNECTION,
            ],
            "resources": {"limits": {"cpu": "1", "memory": "256Mi"}},
            "startupProbe": {
                "httpGet": {"path": "/readiness", "port": 9090},
                "periodSeconds": 5,
                "timeoutSeconds": 2,
                "failureThreshold": 24,
            },
        }
        name = "ocean-v1-beta-db-" + stage
        jobs[name] = {
            "name": "projects/" + PROJECT + "/locations/" + REGION + "/jobs/" + name,
            "labels": {
                "environment": "beta",
                "managed-by": "overhaul",
                "system": "ocean-v1",
            },
            "template": {
                "taskCount": 1,
                "parallelism": 1,
                "template": {
                    "serviceAccount": identity
                    + "@"
                    + PROJECT
                    + ".iam.gserviceaccount.com",
                    "maxRetries": 0,
                    "timeout": "600s",
                    "executionEnvironment": "EXECUTION_ENVIRONMENT_GEN2",
                    "containers": [operator, proxy],
                    "vpcAccess": {
                        "egress": "PRIVATE_RANGES_ONLY",
                        "networkInterfaces": [
                            {
                                "network": "projects/"
                                + PROJECT
                                + "/global/networks/ocean-v1-beta-network",
                                "subnetwork": "projects/"
                                + PROJECT
                                + "/regions/"
                                + REGION
                                + "/subnetworks/ocean-v1-beta-subnet",
                            }
                        ],
                    },
                },
            },
        }
    return jobs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-image", required=True)
    parser.add_argument("--credentials-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("New output directory required")
    jobs = render(
        image=args.operator_image,
        receipt=json.loads(args.credentials_receipt.read_text()),
    )
    args.output.mkdir(parents=True)
    for name, body in jobs.items():
        (args.output / (name + ".json")).write_text(json.dumps(body, indent=2) + "\n")
    print(
        json.dumps(
            {
                "state": "rendered_only",
                "jobs": list(jobs),
                "cloud_calls": False,
                "execution_requested": False,
            }
        )
    )
