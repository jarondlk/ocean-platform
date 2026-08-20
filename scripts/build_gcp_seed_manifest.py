#!/usr/bin/env python3
"""Build a bounded, content-addressed manifest for the Phase 5 GCP seed."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _visible_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != ".DS_Store"
    )


def _entry(path: Path, *, destination: str) -> dict[str, object]:
    return {
        "destination": destination,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _relative_set(paths: Iterable[Path], root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in paths}


def build_seed_manifest(
    *,
    raw_dir: Path,
    sst_dir: Path,
    required_raw_relative: Iterable[str],
    minimum_sst_files: int,
    generated_at: str | None = None,
) -> dict[str, object]:
    """Validate and hash exactly the bounded raw inputs used by Phase 5."""
    if not raw_dir.is_dir():
        raise ValueError(f"Raw directory does not exist: {raw_dir}")
    if not sst_dir.is_dir():
        raise ValueError(f"SST directory does not exist: {sst_dir}")

    required = set(required_raw_relative)
    raw_files = _visible_files(raw_dir)
    actual = _relative_set(raw_files, raw_dir)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing required raw files: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected raw files: {', '.join(unexpected)}")
        raise ValueError("; ".join(details))

    visible_sst = _visible_files(sst_dir)
    unexpected_sst = sorted(
        path.relative_to(sst_dir).as_posix()
        for path in visible_sst
        if path.suffix.lower() != ".nc"
    )
    if unexpected_sst:
        raise ValueError(
            "unexpected non-NetCDF SST files: " + ", ".join(unexpected_sst)
        )
    sst_files = [path for path in visible_sst if path.suffix.lower() == ".nc"]
    if len(sst_files) < minimum_sst_files:
        raise ValueError(
            f"Expected at least {minimum_sst_files} SST files, "
            f"observed {len(sst_files)}."
        )

    raw_entries = [
        _entry(
            path,
            destination=f"raw/{path.relative_to(raw_dir).as_posix()}",
        )
        for path in raw_files
    ]
    sst_entries = [
        _entry(
            path,
            destination=(
                "raw/sst-netcdf/" + path.relative_to(sst_dir).as_posix()
            ),
        )
        for path in sst_files
    ]
    objects = sorted(raw_entries + sst_entries, key=lambda item: item["destination"])
    collection_payload = json.dumps(
        objects,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return {
        "schema_version": 1,
        "seed_id": "phase5-raw-v1",
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(),
        "groups": {
            "ctd_metagenome": {
                "destination_prefix": "raw/",
                "objects": len(raw_entries),
                "bytes": sum(int(item["size_bytes"]) for item in raw_entries),
            },
            "sst_netcdf": {
                "destination_prefix": "raw/sst-netcdf/",
                "minimum_contract_files": minimum_sst_files,
                "objects": len(sst_entries),
                "bytes": sum(int(item["size_bytes"]) for item in sst_entries),
            },
        },
        "total_objects": len(objects),
        "total_bytes": sum(int(item["size_bytes"]) for item in objects),
        "collection_sha256": hashlib.sha256(collection_payload).hexdigest(),
        "objects": objects,
    }


def _required_raw_relative() -> list[str]:
    return sorted(
        path.relative_to(config.RAW_DIR).as_posix()
        for path in config.RAW_FILES.values()
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the content-addressed Phase 5 raw seed manifest"
    )
    parser.add_argument("--raw-dir", type=Path, default=config.RAW_DIR)
    parser.add_argument("--sst-dir", type=Path, default=config.SST_NETCDF_DIR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--minimum-sst-files",
        type=int,
        default=1800,
    )
    args = parser.parse_args()

    try:
        manifest = build_seed_manifest(
            raw_dir=args.raw_dir,
            sst_dir=args.sst_dir,
            required_raw_relative=_required_raw_relative(),
            minimum_sst_files=args.minimum_sst_files,
        )
    except ValueError as exc:
        print(f"seed_manifest_error={exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"manifest={args.output}")
    print(f"objects={manifest['total_objects']}")
    print(f"bytes={manifest['total_bytes']}")
    print(f"collection_sha256={manifest['collection_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
