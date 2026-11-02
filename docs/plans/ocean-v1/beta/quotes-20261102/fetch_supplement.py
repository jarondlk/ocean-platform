import json
import subprocess
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone

TOKEN = subprocess.run(
    ["/opt/homebrew/bin/gcloud", "auth", "print-access-token"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()


def fetch(item):
    service, identity = item
    rows = []
    page = ""
    total = 0
    while True:
        url = (
            "https://cloudbilling.googleapis.com/v1/services/"
            + identity
            + "/skus?"
            + urllib.parse.urlencode(
                {"pageSize": 5000, "currencyCode": "JPY", "pageToken": page}
            )
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": "Bearer " + TOKEN,
                "X-Goog-User-Project": "ocean-v1-beta-20261101",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            d = json.load(response)
        for s in d.get("skus", []):
            total += 1
            desc = s["description"].lower()
            regions = s.get("serviceRegions", [])
            if s.get("category", {}).get("usageType") != "OnDemand":
                continue
            keep = (
                service == "Cloud Run"
                and "request" in desc
                and "cpu" not in desc
                and "memory" not in desc
            )
            keep |= (
                service == "Cloud Storage"
                and ("class a" in desc or "class b" in desc or "operation" in desc)
                and (
                    "asia-northeast1" in regions
                    or "asia" in regions
                    or "global" in regions
                    or "asia pacific" in desc
                )
            )
            keep |= (
                service == "Compute Engine"
                and any(
                    x in desc
                    for x in [
                        "network load balancing",
                        "load balanced",
                        "http load balancing",
                        "static ip charge",
                        "load balancer data",
                        "ipv4",
                    ]
                )
                and ("asia-northeast1" in regions or "global" in regions)
            )
            keep |= (
                service == "Networking"
                and any(
                    x in desc
                    for x in ["data processing", "data processed", "balancer", "ipv4"]
                )
                and ("asia-northeast1" in regions or "global" in regions)
            )
            if keep:
                rows.append(s)
        page = d.get("nextPageToken", "")
        if not page:
            break
    return {
        "service_name": service,
        "service_id": identity,
        "rows_examined": total,
        "records": rows,
    }


with ThreadPoolExecutor(max_workers=4) as ex:
    results = list(
        ex.map(
            fetch,
            [
                ("Cloud Run", "152E-C115-5142"),
                ("Compute Engine", "6F81-5844-456A"),
                ("Cloud Storage", "95FF-2EF5-5EA1"),
                ("Networking", "E505-1604-58F8"),
            ],
        )
    )
p = Path("docs/plans/ocean-v1/beta/quotes-20261102/catalogue-supplement.json")
assert not p.exists()
p.write_text(
    json.dumps(
        {
            "version": "beta-public-jpy-catalogue-supplement-v1",
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "currency": "JPY",
            "source_api": "https://cloudbilling.googleapis.com/v1/services/{serviceId}/skus?currencyCode=JPY&pageSize=5000",
            "results": results,
        },
        sort_keys=True,
        indent=2,
    )
    + "\n"
)
for a in results:
    print(a["service_name"], a["rows_examined"], len(a["records"]))
    for s in a["records"]:
        print(s["skuId"], s["description"], s["serviceRegions"])
