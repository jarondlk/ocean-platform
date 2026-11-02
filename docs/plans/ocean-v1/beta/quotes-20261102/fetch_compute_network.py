import json
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

TOKEN = subprocess.run(
    ["/opt/homebrew/bin/gcloud", "auth", "print-access-token"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
rows = []
page = ""
total = 0
while True:
    url = (
        "https://cloudbilling.googleapis.com/v1/services/6F81-5844-456A/skus?"
        + urllib.parse.urlencode(
            {"currencyCode": "JPY", "pageSize": 5000, "pageToken": page}
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
        if (
            any(
                x in desc
                for x in ["internet", "premium internet", "external ip", "static ip"]
            )
            and ("asia-northeast1" in regions or "global" in regions)
        ) or ("static ip" in desc and not regions):
            rows.append(s)
    page = d.get("nextPageToken", "")
    if not page:
        break
p = Path("docs/plans/ocean-v1/beta/quotes-20261102/catalogue-compute-network.json")
assert not p.exists()
p.write_text(
    json.dumps(
        {
            "version": "beta-public-jpy-compute-network-candidates-v1",
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_api": "https://cloudbilling.googleapis.com/v1/services/6F81-5844-456A/skus?currencyCode=JPY&pageSize=5000",
            "currency": "JPY",
            "rows_examined": total,
            "records": rows,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
for s in rows:
    print(s["skuId"], s["description"], s["serviceRegions"])
