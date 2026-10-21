#!/usr/bin/env python3
"""Transport an immutable scientific store into the fixed COP17 bucket.

Scientific IDs, object bytes, hashes, metadata and decisions are preserved.
Only destination object-generation receipts and mutable receipt pointers change.
Source objects are read at their sealed generations; writes are destination-only.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.artifact_store import ArtifactStore, BoundedGcsStore, MAX_BYTES  # noqa: E402
from ingestion.immutable_bundle import canonical_bytes, digest  # noqa: E402
from ingestion.provenance_snapshot import SnapshotConflict  # noqa: E402

SOURCE_BUCKET = "data-infra-infobio-ocean-data"
TARGET_BUCKET = "data-infra-infobio-ocean-cop17"
SOURCE_PREFIX = "edna"
TARGET_PREFIX = "edna-cop17-snapshot"
NAMESPACES = (
    "analysis",
    "provisional-demos",
    "regional-publications",
    "sst-panels",
    "sst-collections",
    "recipes",
    "raw",
    "normalized",
    "retrieval",
)


def transport_receipt(receipt, generations):
    if set(generations) != set(receipt["files"]):
        raise ValueError("Every sealed object needs exactly one destination generation")
    result = deepcopy(receipt)
    for name, generation in generations.items():
        if type(generation) is not int or generation <= 0:
            raise ValueError("Invalid destination generation")
        result["files"][name]["generation"] = generation
    return result


def rewrite_pointer(value, mapping):
    if isinstance(value, dict):
        return {
            key: mapping.get(item, item)
            if key == "receipt_sha256" and isinstance(item, str)
            else rewrite_pointer(item, mapping)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [rewrite_pointer(item, mapping) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-target", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.confirm_target != "gs://" + TARGET_BUCKET + "/" + TARGET_PREFIX:
        raise ValueError("Only the fixed isolated COP17 destination is allowed")
    from google.cloud import storage
    from google.oauth2.credentials import Credentials
    from google.api_core.exceptions import PreconditionFailed

    credentials = Credentials(
        subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], text=True
        ).strip()
    )
    client = storage.Client(project="data-infra-infobio", credentials=credentials)
    source = ArtifactStore(
        store=BoundedGcsStore(bucket=SOURCE_BUCKET, prefix=SOURCE_PREFIX, client=client)
    )
    target = ArtifactStore(
        store=BoundedGcsStore(bucket=TARGET_BUCKET, prefix=TARGET_PREFIX, client=client)
    )
    source_bucket, target_bucket = (
        client.bucket(SOURCE_BUCKET),
        client.bucket(TARGET_BUCKET),
    )
    mapping, records = {}, []
    namespace_generations = {}

    def create_or_verify(key, data):
        try:
            return target.store.create(key, data)
        except SnapshotConflict:
            observed = target._read(key, len(data))
            if observed.data != data:
                raise ValueError(
                    "Existing destination metadata differs from this snapshot"
                )
            return observed.generation

    def transfer(item):
        namespace, identity, entry = item
        original = json.loads(
            source._read(f"{namespace}/registry/{identity}.json", 4 * 1024 * 1024).data
        )
        if (
            digest(original) != entry["receipt_sha256"]
            or original["id"] != identity
            or original["namespace"] != namespace
        ):
            raise ValueError("Source receipt/index identity mismatch")
        if (
            not 0 < len(original["files"]) <= 4000
            or sum(f["size"] for f in original["files"].values()) > MAX_BYTES
        ):
            raise ValueError(
                "Source artifact exceeds the maintained file/byte contract"
            )
        generations = {}
        for name, info in original["files"].items():
            key = f"{namespace}/objects/{identity}/{name}"
            observed = source._read(key, info["size"])
            if (
                observed.generation != info["generation"]
                or len(observed.data) != info["size"]
                or hashlib.sha256(observed.data).hexdigest() != info["sha256"]
            ):
                raise ValueError(
                    "Source scientific object failed its sealed generation/hash"
                )
            src_blob = source_bucket.blob(SOURCE_PREFIX + "/" + key)
            try:
                copied = source_bucket.copy_blob(
                    src_blob,
                    target_bucket,
                    TARGET_PREFIX + "/" + key,
                    if_generation_match=0,
                    if_source_generation_match=info["generation"],
                )
                generation = int(copied.generation)
                if int(copied.size) != info["size"]:
                    raise ValueError("Destination copy size mismatch")
            except PreconditionFailed:
                copied = target._read(key, info["size"])
                if (
                    len(copied.data) != info["size"]
                    or hashlib.sha256(copied.data).hexdigest() != info["sha256"]
                ):
                    raise ValueError(
                        "Existing destination object does not match sealed science"
                    )
                generation = copied.generation
            generations[name] = generation
        receipt = transport_receipt(original, generations)
        create_or_verify(
            f"{namespace}/registry/{identity}.json", canonical_bytes(receipt)
        )
        return {
            "namespace": namespace,
            "id": identity,
            "source_receipt_sha256": digest(original),
            "destination_receipt_sha256": digest(receipt),
            "file_count": len(generations),
            "scientific_bytes": sum(f["size"] for f in original["files"].values()),
            "files": receipt["files"],
            "metadata": entry["metadata"],
        }

    for namespace in NAMESPACES:
        index, generation = source.pointer(namespace + "/index.json")
        namespace_generations[namespace] = generation
        entries = {} if index is None else source.entries(namespace)
        with ThreadPoolExecutor(max_workers=4) as pool:
            transferred = list(
                pool.map(
                    transfer,
                    [
                        (namespace, identity, entry)
                        for identity, entry in entries.items()
                    ],
                )
            )
        new_entries = {}
        for record in transferred:
            mapping[record["source_receipt_sha256"]] = record[
                "destination_receipt_sha256"
            ]
            new_entries[record["id"]] = {
                "receipt_sha256": record["destination_receipt_sha256"],
                "metadata": record["metadata"],
            }
        if index is not None:
            create_or_verify(
                namespace + "/index.json",
                canonical_bytes({"schema_version": 1, "entries": new_entries}),
            )
        records.extend(transferred)
        print(
            json.dumps(
                {
                    "namespace": namespace,
                    "artifacts_verified_and_transported": len(transferred),
                }
            ),
            flush=True,
        )

    pointers = []
    for namespace in NAMESPACES:
        prefix = SOURCE_PREFIX + "/" + namespace + "/"
        for blob in client.list_blobs(source_bucket, prefix=prefix):
            relative = blob.name[len(SOURCE_PREFIX) + 1 :]
            tail = blob.name[len(prefix) :]
            if tail == "index.json" or tail.startswith(("objects/", "registry/")):
                continue
            obj = source._read(relative, MAX_BYTES)
            try:
                payload = json.loads(obj.data)
            except (ValueError, UnicodeDecodeError):
                data = obj.data
            else:
                rewritten = rewrite_pointer(payload, mapping)
                data = obj.data if rewritten == payload else canonical_bytes(rewritten)
            create_or_verify(relative, data)
            pointers.append(relative)
        if (
            source.pointer(namespace + "/index.json")[1]
            != namespace_generations[namespace]
        ):
            raise ValueError("Source registry changed during the controlled snapshot")
    report = {
        "source": "gs://" + SOURCE_BUCKET + "/" + SOURCE_PREFIX,
        "destination": "gs://" + TARGET_BUCKET + "/" + TARGET_PREFIX,
        "scientific_ids_and_bytes_preserved": True,
        "artifact_count": len(records),
        "artifacts": records,
        "mutable_pointers": pointers,
        "excluded_namespaces": ["classification-reviews", "evaluation", "operations"],
    }
    args.report.write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"artifacts", "mutable_pointers"}
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
