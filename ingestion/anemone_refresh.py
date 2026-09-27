"""Bounded recurring discovery and processed-file acquisition.

Each invocation is a new catalogue observation. Prior bytes are reused only
when current validators agree; --rehash verifies content even if validators lie.
A failed observation never advances current.json or applies withdrawals.
"""

from __future__ import annotations
from collections import deque, defaultdict
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import time
from urllib.parse import urlsplit

from ingestion.anemone import (
    AnemoneRemoteFile,
    SAFE_SEGMENT,
    _direct_child_links,
    _role_for_file,
    _validate_interpreted_file,
    load_contract,
)
from ingestion.anemone_catalogue import (
    CATALOGUE_CONTRACT,
    file_sha256,
    read_archive,
    safe_archive_path,
)
from ingestion.immutable_bundle import atomic_json, digest
from preprocessing.anemone import REQUIRED_ROLES

ROOT_URL = "https://db.anemone.bio/dist/"


class BudgetClient:
    def __init__(
        self,
        client,
        *,
        max_requests=100000,
        min_interval=0.25,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        if max_requests < 1 or min_interval < 0:
            raise ValueError("Invalid provider request budget")
        self.client, self.maximum, self.interval = client, max_requests, min_interval
        self.clock, self.sleep = clock, sleep
        self.requests, self.last = 0, None

    def call(self, method, *args, **kwargs):
        if self.requests >= self.maximum:
            raise ValueError(
                "Provider request budget exhausted; last publication retained"
            )
        if self.last is not None:
            self.sleep(max(0, self.interval - (self.clock() - self.last)))
        self.last = self.clock()
        self.requests += 1
        return getattr(self.client, method)(*args, **kwargs)


def discover(client: BudgetClient, *, max_directories=20000, max_files=250000):
    queue = deque([(ROOT_URL, 0)])
    listings, files = {}, []
    while queue:
        url, depth = queue.popleft()
        if len(listings) >= max_directories:
            raise ValueError("Directory discovery budget exhausted")
        html = client.call("read_directory", url, 2_000_000)
        directories, children = _direct_child_links(url, html)
        # Index sorting links and parent links convey no source-file identity.
        children = [
            u
            for u in children
            if not (urlsplit(u).path == urlsplit(url).path and urlsplit(u).query)
        ]
        for child in directories + children:
            p = urlsplit(child)
            parent = urlsplit(url).path
            tail = p.path[len(parent) :].rstrip("/")
            if (
                p.scheme != "https"
                or p.netloc != "db.anemone.bio"
                or p.query
                or p.fragment
                or not p.path.startswith(parent)
                or not SAFE_SEGMENT.fullmatch(tail)
            ):
                raise ValueError("Unexpected link outside catalogue hierarchy")
        if (depth < 5 and children) or (depth == 5 and directories):
            raise ValueError("Unexpected catalogue layout")
        listings[url] = {
            "sha256": hashlib.sha256(html.encode()).hexdigest(),
            "children": sorted(directories + children),
        }
        if depth < 5:
            queue.extend((d, depth + 1) for d in directories)
        else:
            if not children:
                raise ValueError("Empty source directory is not an approved withdrawal")
            files.extend(children)
            if len(files) > max_files:
                raise ValueError("File discovery budget exhausted")
    if not files:
        raise ValueError("Empty catalogue cannot replace an existing observation")
    return listings, sorted(files)


def refresh_archive(
    client,
    output: Path,
    *,
    previous: Path | None = None,
    rehash=False,
    max_requests=100000,
    min_interval=0.25,
    max_bytes=512 * 1024 * 1024,
    progress=None,
):
    """Produce archive-compatible evidence; publication and scheduling are separate."""
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".refresh.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _refresh_locked(
            client,
            output,
            previous=previous,
            rehash=rehash,
            max_requests=max_requests,
            min_interval=min_interval,
            max_bytes=max_bytes,
            progress=progress,
        )


def _refresh_locked(
    client, output, *, previous, rehash, max_requests, min_interval, max_bytes, progress
):
    budget = BudgetClient(client, max_requests=max_requests, min_interval=min_interval)
    start = datetime.now(timezone.utc).isoformat()
    contract = load_contract(CATALOGUE_CONTRACT)
    prior = {r["url"]: r for r in read_archive(previous)[1]} if previous else {}
    listings, urls = discover(budget)
    observation_id = digest({"started_at": start, "listings": listings})
    stage = output / "observations" / observation_id
    stage.mkdir(parents=True, exist_ok=False)
    # Shared hash-addressed selected bytes are durable checkpoints across failed
    # observations; they are never a claim that a whole catalogue is complete.
    cache = output / "objects"
    cache.mkdir(exist_ok=True)
    rows = []
    downloaded = 0
    changed = []
    reused = 0
    for index, url in enumerate(urls, 1):
        name = urlsplit(url).path.rsplit("/", 1)[-1]
        sample = urlsplit(url).path.split("/")[-2]
        role = _role_for_file(name, contract)
        if role["selection"] == "unknown":
            raise ValueError(
                "Unsupported source role; observation retained for investigation"
            )
        info = budget.call("metadata", url)
        size = info.get("size_bytes")
        if not isinstance(size, int) or size < 0:
            raise ValueError("Provider did not expose a valid source size")
        row = {
            "url": url,
            "archive_path": urlsplit(url).path.lstrip("/"),
            "size": size,
            "etag": info.get("etag"),
            "last_modified": info.get("last_modified"),
            "role": role["role"],
            "status": "inventory_only",
            "sha256": None,
            "directory_observed_at": start,
        }
        old = prior.get(url)
        if role["selection"] == "selected":
            current = {k: row[k] for k in ("size", "etag", "last_modified")}
            same = (
                old
                and any(current[k] for k in ("etag", "last_modified"))
                and all(old.get(k) == v for k, v in current.items())
            )
            source = None
            if same and not rehash and old.get("sha256"):
                oldpath = safe_archive_path(previous, old["archive_path"])
                if oldpath.is_file() and file_sha256(oldpath) == old["sha256"]:
                    source = oldpath
                    row["sha256"] = old["sha256"]
                    reused += 1
            version = digest({"url": url, **current})
            checkpoint = cache / (version + ".json")
            if (
                source is None
                and any(current[k] for k in ("etag", "last_modified"))
                and not rehash
                and checkpoint.exists()
            ):
                saved = json.loads(checkpoint.read_text())
                cached = cache / saved["sha256"]
                if cached.is_file() and file_sha256(cached) == saved["sha256"]:
                    source = cached
                    row["sha256"] = saved["sha256"]
                    reused += 1
            if source is None:
                if downloaded + size > max_bytes:
                    raise ValueError("Selected download byte budget exhausted")
                part = cache / (version + ".part")
                response = budget.call("open", url)
                h = hashlib.sha256()
                count = 0
                try:
                    with part.open("wb") as stream:
                        while block := response.read(1024 * 1024):
                            count += len(block)
                            if count > size or downloaded + count > max_bytes:
                                raise ValueError(
                                    "Source exceeded declared size or byte budget"
                                )
                            stream.write(block)
                            h.update(block)
                    if count != size:
                        raise ValueError("Truncated source response")
                finally:
                    response.close()
                after = budget.call("metadata", url)
                if any(
                    after.get(k) != info.get(k)
                    for k in ("size_bytes", "etag", "last_modified")
                ):
                    raise ValueError(
                        "Source changed during acquisition; retry observation"
                    )
                row["sha256"] = h.hexdigest()
                source = cache / row["sha256"]
                if source.exists() and file_sha256(source) != row["sha256"]:
                    raise ValueError("Cached content integrity failure")
                part.replace(source)
                downloaded += count
                atomic_json(checkpoint, {"sha256": row["sha256"]})
            destination = safe_archive_path(stage, row["archive_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if file_sha256(destination) != row["sha256"]:
                raise ValueError("Staged source integrity failure")
            item = AnemoneRemoteFile(
                name, url, sample, role["role"], "selected", role.get("table_contract")
            )
            _, names = _validate_interpreted_file(destination, item, contract)
            if names != {sample}:
                raise ValueError("Provider sample identifier mismatch")
            row["status"] = "downloaded"
            row["downloaded_at"] = start
            if not old or old.get("sha256") != row["sha256"]:
                changed.append(url)
        rows.append(row)
        if progress and index % 100 == 0:
            progress(
                {
                    "files": index,
                    "total": len(urls),
                    "request_operations": budget.requests,
                    "downloaded_bytes": downloaded,
                }
            )
    # Recheck all child links: a moving tree is not silently treated as complete.
    end_listings, end_urls = discover(budget)
    if urls != end_urls or any(
        listings[u]["children"] != end_listings[u]["children"] for u in listings
    ):
        raise ValueError("Catalogue changed during acquisition; retry observation")
    sample_roles = defaultdict(set)
    for row in rows:
        sample_roles[row["url"].rsplit("/", 1)[0]].add(row["role"])
    if any(REQUIRED_ROLES - roles for roles in sample_roles.values()):
        raise ValueError("Source directory is missing required processed files")
    manifest = stage / "manifest.jsonl.gz"
    with gzip.open(manifest, "wt") as stream:
        for row in rows:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
    report = {
        "files": len(rows),
        "bytes": sum(r["size"] for r in rows),
        "manifest_sha256": file_sha256(manifest),
        "started_at": start,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "source_root": ROOT_URL,
        "request_operations": budget.requests,
        "downloaded_bytes": downloaded,
        "reused_files": reused,
        "changed_selected_files": changed,
        "withdrawal_candidates": sorted(set(prior) - set(urls)),
        "withdrawals_applied": False,
        "production_imported": False,
        "rehash": rehash,
        "freshness_limit": "Validators are hints; use periodic --rehash to detect changes under unchanged validators.",
    }
    atomic_json(
        stage / "catalogue-observation.json",
        {"before": listings, "after": end_listings},
    )
    atomic_json(stage / "archive-summary.json", report)
    read_archive(stage)
    atomic_json(
        output / "current.json",
        {
            "observation_id": observation_id,
            "manifest_sha256": report["manifest_sha256"],
        },
    )
    return {"archive": str(stage), **report}
