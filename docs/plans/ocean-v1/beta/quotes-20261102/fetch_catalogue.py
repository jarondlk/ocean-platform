"""Fetch only relevant public JPY catalogue candidates; never writes credentials."""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

DIRECTORY = Path(__file__).resolve().parent
PROJECT = "ocean-v1-beta-20261101"
REGION = "asia-northeast1"
NAMES = {
    "Cloud SQL",
    "Compute Engine",
    "Networking",
    "Cloud Run",
    "Cloud Build",
    "Cloud Storage",
    "Artifact Registry",
    "Cloud DNS",
    "Secret Manager",
    "Cloud Tasks",
    "Cloud Logging",
}


def main():
    token = subprocess.run(
        ["/opt/homebrew/bin/gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    def get(path, params):
        url = (
            "https://cloudbilling.googleapis.com/v1/"
            + path
            + "?"
            + urllib.parse.urlencode(params)
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": "Bearer " + token,
                "X-Goog-User-Project": PROJECT,
            },
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)

    services = []
    page = ""
    while True:
        result = get("services", {"pageSize": 5000, "pageToken": page})
        services.extend(result.get("services", []))
        page = result.get("nextPageToken", "")
        if not page:
            break
    selected = [s for s in services if s["displayName"] in NAMES]
    assert set(s["displayName"] for s in selected) == NAMES

    def predicate(service, s):
        desc = s["description"].lower()
        regions = s.get("serviceRegions", [])
        if s.get("category", {}).get("usageType") != "OnDemand":
            return False
        if service == "Cloud SQL":
            return (
                REGION in regions
                and "trial" not in desc
                and "extended support" not in desc
                and "enterprise plus" not in desc
                and (
                    (
                        "postgresql: zonal" in desc
                        and not any(
                            x in desc
                            for x in ["micro", "small", "ip address", "hyperdisk"]
                        )
                    )
                    or "backup" in desc
                )
            )
        if service == "Compute Engine":
            return (
                REGION in regions
                and (
                    (
                        "e2 instance" in desc
                        and not any(
                            x in desc for x in ["spot", "preemptible", "reserved"]
                        )
                    )
                    or any(
                        x in desc
                        for x in [
                            "storage pd capacity",
                            "balanced pd capacity",
                            "ssd backed pd capacity",
                        ]
                    )
                )
            ) or (
                (REGION in regions or "global" in regions)
                and any(
                    x in desc
                    for x in [
                        "forwarding rule",
                        "load balancing",
                        "external ip",
                        "ipv4",
                        "static ip",
                    ]
                )
            )
        if service == "Networking":
            return (REGION in regions or "global" in regions) and any(
                x in desc
                for x in [
                    "load balancing",
                    "forwarding rule",
                    "ipv4",
                    "external ip",
                    "internet",
                    "egress",
                ]
            )
        if service == "Cloud Run":
            return REGION in regions and not any(
                x in desc for x in ["gpu", "committed", "function", "nvidia"]
            )
        if service == "Cloud Build":
            return "e2" in desc or "standard" in desc
        if service == "Cloud Storage":
            return REGION in regions and any(
                x in desc
                for x in [
                    "standard storage",
                    "class a",
                    "class b",
                    "retrieval",
                    "network egress",
                ]
            )
        if service == "Artifact Registry":
            return any(x in desc for x in ["storage", "network egress"])
        if service == "Cloud DNS":
            return True
        if service == "Secret Manager":
            return True
        if service == "Cloud Tasks":
            return True
        if service == "Cloud Logging":
            return "log" in desc
        return False

    def fetch(service):
        rows = []
        page = ""
        total = 0
        pages = 0
        while True:
            result = get(
                service["name"] + "/skus",
                {"pageSize": 5000, "currencyCode": "JPY", "pageToken": page},
            )
            skus = result.get("skus", [])
            total += len(skus)
            pages += 1
            rows.extend(s for s in skus if predicate(service["displayName"], s))
            page = result.get("nextPageToken", "")
            if not page:
                break
        return {
            "service": service,
            "catalogue_rows_examined": total,
            "pages": pages,
            "records": rows,
        }

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(fetch, selected))
    record = {
        "version": "beta-public-jpy-catalogue-candidates-v1",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_api": "https://cloudbilling.googleapis.com/v1/services/{serviceId}/skus?currencyCode=JPY&pageSize=5000",
        "official_method_documentation": "https://docs.cloud.google.com/billing/docs/reference/rest/v1/services.skus/list",
        "currency": "JPY",
        "region": REGION,
        "rate_kind": "public list OnDemand; not account-specific contract price",
        "free_credits_assumed": 0,
        "results": results,
    }
    path = DIRECTORY / "catalogue-candidates.json"
    if path.exists():
        raise RuntimeError("Refuse overwriting captured candidate receipt")
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "saved": str(path),
                "services": [
                    {
                        "name": r["service"]["displayName"],
                        "id": r["service"]["serviceId"],
                        "examined": r["catalogue_rows_examined"],
                        "retained": len(r["records"]),
                    }
                    for r in results
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
