#!/usr/bin/env python3
"""Run a bounded ANEMONE observation; suitable for a later weekly job."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.anemone import AnemoneHttpClient, resolve_credentials
from ingestion.anemone_refresh import ROOT_URL, refresh_archive


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--previous", type=Path)
    p.add_argument("--rehash", action="store_true")
    p.add_argument("--max-requests", type=int, default=100000)
    p.add_argument("--max-bytes", type=int, default=512 * 1024 * 1024)
    p.add_argument("--min-interval", type=float, default=0.25)
    a = p.parse_args()
    client = AnemoneHttpClient(resolve_credentials(), base_url=ROOT_URL)
    r = refresh_archive(
        client,
        a.output,
        previous=a.previous,
        rehash=a.rehash,
        max_requests=a.max_requests,
        max_bytes=a.max_bytes,
        min_interval=a.min_interval,
        progress=lambda r: print(json.dumps(r), flush=True),
    )
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
