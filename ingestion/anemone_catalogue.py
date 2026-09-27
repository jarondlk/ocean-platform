"""Hash-verified, resumable catalogue preparation in bounded complete-sample units.

The archive manifest is evidence, never executable configuration. This module does
not publish to production, infer withdrawals, or require provider credentials.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import fcntl
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
from urllib.parse import urlsplit

import pandas as pd

import config
from ingestion.anemone import (
    AnemoneRemoteFile,
    _role_for_file,
    _validate_interpreted_file,
    load_contract,
    validate_scope_url,
)
from ingestion.immutable_bundle import atomic_json
from preprocessing.anemone import (
    REQUIRED_ROLES,
    normalize_anemone_snapshot,
    resolve_normalized_bundle,
    stable_sha256,
)
from preprocessing.edna_taxonomy import TAXONOMY_POLICY_VERSION

CATALOGUE_CONTRACT = config.PROJECT_ROOT / "data_contracts/anemone_catalogue.json"
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_FILES = 250_000
MAX_SAMPLES_PER_UNIT = 128


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_archive_path(root: Path, name: str) -> Path:
    rel = PurePosixPath(name)
    if (
        rel.is_absolute()
        or "\\" in name
        or any(p in {"", ".", ".."} for p in name.split("/"))
    ):
        raise ValueError("Unsafe archive path")
    path = root.joinpath(*rel.parts)
    if root.resolve() not in path.resolve().parents or any(
        p.is_symlink() for p in (path, *path.parents)
    ):
        raise ValueError("Archive symlink or escaped path")
    return path


def read_archive(archive: Path) -> tuple[str, list[dict]]:
    summary = json.loads((archive / "archive-summary.json").read_text())
    manifest = archive / "manifest.jsonl.gz"
    identity = file_sha256(manifest)
    if summary.get("manifest_sha256") != identity:
        raise ValueError("Archive manifest hash mismatch")
    rows, paths, urls = [], set(), set()
    used = 0
    with gzip.open(manifest, "rb") as stream:
        while line := stream.readline(min(1_048_577, MAX_MANIFEST_BYTES - used + 1)):
            if len(line) > 1_048_576:
                raise ValueError("Catalogue manifest line exceeds budget")
            used += len(line)
            if used > MAX_MANIFEST_BYTES or len(rows) >= MAX_FILES:
                raise ValueError("Catalogue manifest exceeds budget")
            row = json.loads(line)
            name, url = row["archive_path"], row["url"]
            safe_archive_path(archive, name)
            parts = PurePosixPath(name).parts
            parsed = urlsplit(url)
            if (
                len(parts) != 7
                or parts[0] != "dist"
                or parsed.scheme != "https"
                or parsed.netloc != "db.anemone.bio"
                or parsed.path != "/" + name
                or parsed.query
                or parsed.fragment
                or any(not part or part in {".", ".."} for part in parts)
            ):
                raise ValueError("Invalid catalogue hierarchy or source URL")
            validate_scope_url(
                url.rsplit("/", 1)[0] + "/", base_url="https://db.anemone.bio/dist/"
            )
            if name in paths or url in urls:
                raise ValueError("Duplicate catalogue identity")
            if not isinstance(row["size"], int) or row["size"] < 0:
                raise ValueError("Invalid archive size")
            if row.get("status") not in {"downloaded", "inventory_only"}:
                raise ValueError("Catalogue contains an incomplete acquisition")
            paths.add(name)
            urls.add(url)
            rows.append(row)
    if len(rows) != summary.get("files") or sum(r["size"] for r in rows) != summary.get(
        "bytes"
    ):
        raise ValueError("Archive count or byte reconciliation failed")
    if not rows:
        raise ValueError("Empty catalogue cannot replace a publication")
    return identity, rows


def source_versions(rows, contract):
    """Source content identity excludes acquisition times and local paths."""
    result = []
    for row in sorted(rows, key=lambda r: r["url"]):
        role = _role_for_file(PurePosixPath(row["archive_path"]).name, contract)
        version = {key: row.get(key) for key in ("url", "archive_path", "size")}
        if role["selection"] == "selected":
            version["sha256"] = row.get("sha256")
        else:
            version.update({key: row.get(key) for key in ("etag", "last_modified")})
        result.append(version)
    return result


def catalogue_units(rows: list[dict], batch_size: int = MAX_SAMPLES_PER_UNIT):
    if not 1 <= batch_size <= MAX_SAMPLES_PER_UNIT:
        raise ValueError("Catalogue batch size must be between 1 and 128 samples")
    runs = defaultdict(lambda: defaultdict(list))
    for row in rows:
        parts = PurePosixPath(row["archive_path"]).parts
        runs["/".join(parts[1:5])][parts[5]].append(row)
    for run, samples in sorted(runs.items()):
        names = sorted(samples)
        for start in range(0, len(names), batch_size):
            yield (
                run,
                [
                    r
                    for name in names[start : start + batch_size]
                    for r in sorted(samples[name], key=lambda x: x["archive_path"])
                ],
            )


def _stage_unit(
    archive: Path,
    raw: Path,
    run: str,
    rows: list[dict],
    contract: dict,
    observed_at: str,
) -> dict:
    if len(rows) > contract["limits"]["maximum_files"]:
        raise ValueError("Catalogue unit exceeds file budget")
    identity = stable_sha256(
        {"contract": contract, "run": run, "files": source_versions(rows, contract)}
    )
    dest = raw / "snapshots" / identity
    if dest.exists():
        manifest = json.loads((dest / "manifest.json").read_text())
        if manifest.get("snapshot_id") != identity or manifest.get(
            "contract_sha256"
        ) != stable_sha256(contract):
            raise ValueError("Resumed source manifest identity mismatch")
        for item in manifest["files"]:
            if item["selection_status"] == "selected":
                path = safe_archive_path(dest, item["relative_path"])
                if (
                    path.stat().st_size != item["size_bytes"]
                    or file_sha256(path) != item["sha256"]
                ):
                    raise ValueError("Resumed source integrity mismatch")
        return manifest
    raw.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".catalogue-", dir=raw))
    files, roles = [], defaultdict(set)
    total = 0
    try:
        for row in rows:
            sample, filename = PurePosixPath(row["archive_path"]).parts[-2:]
            rule = _role_for_file(filename, contract)
            if rule["selection"] == "unknown":
                raise ValueError("Unknown source role; catalogue unit quarantined")
            item = AnemoneRemoteFile(
                relative_path=f"{sample}/{filename}",
                source_url=row["url"],
                sample_name=sample,
                role=rule["role"],
                selection_status=rule["selection"],
                table_contract=rule.get("table_contract"),
                size_bytes=row["size"],
                etag=row.get("etag"),
                last_modified=row.get("last_modified"),
                sha256=row.get("sha256"),
                downloaded_at=row.get("downloaded_at"),
            )
            if item.selection_status == "selected":
                total += item.size_bytes
                if total > contract["limits"]["maximum_download_bytes"]:
                    raise ValueError("Catalogue unit exceeds selected-byte budget")
                source = safe_archive_path(archive, row["archive_path"])
                if (
                    source.stat().st_size != item.size_bytes
                    or file_sha256(source) != item.sha256
                ):
                    raise ValueError("Archived source size or hash mismatch")
                target = stage / item.relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                if file_sha256(target) != item.sha256:
                    raise ValueError("Staged source hash mismatch")
                item.row_count, names = _validate_interpreted_file(
                    target, item, contract
                )
                if names != {sample}:
                    raise ValueError("Source sample identifier mismatch")
                item.validation_status = "valid"
                roles[sample].add(item.role)
            files.append(item.to_dict())
        names = {PurePosixPath(r["archive_path"]).parts[-2] for r in rows}
        if any(not REQUIRED_ROLES.issubset(roles[name]) for name in names):
            raise ValueError("Catalogue sample is missing a required source role")
        manifest = {
            "schema_version": 1,
            "source_provider": "anemone",
            "source_family": "edna_metabarcoding",
            "scope_url": "https://db.anemone.bio/dist/" + run + "/",
            "scope_level": "run",
            "generated_at": observed_at,
            "mode": "archive",
            "status": "complete",
            "contract_version": contract["contract_version"],
            "contract_sha256": stable_sha256(contract),
            "selection_policy": "interpreted_tsv_only",
            "reconciliation_mode": "complete_samples",
            "snapshot_id": identity,
            "source_collection_sha256": identity,
            "file_count": len(files),
            "selected_file_count": sum(
                f["selection_status"] == "selected" for f in files
            ),
            "total_bytes": total,
            "files": files,
            "issues": [],
        }
        atomic_json(stage / "manifest.json", manifest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        stage.replace(dest)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def read_normalized_unit(normalized: Path, identity: str) -> tuple[dict, dict]:
    root, manifest = resolve_normalized_bundle(identity, normalized_root=normalized)
    frames = {}
    for name, entry in manifest["artifacts"].items():
        path = safe_archive_path(root, entry["path"])
        if file_sha256(path) != entry["sha256"]:
            raise ValueError("Normalized artifact checksum mismatch")
        frame = pd.read_parquet(path)
        if len(frame) != entry["row_count"]:
            raise ValueError("Normalized artifact row count mismatch")
        frames[name] = frame
    return frames, manifest


def prepare_catalogue(
    archive: Path, work: Path, *, batch_size=MAX_SAMPLES_PER_UNIT, progress=None
) -> dict:
    """Resume preparation; only a fully reconciled candidate receives a manifest."""
    archive, work = archive.resolve(), work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    with (work / ".prepare.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _prepare_locked(archive, work, batch_size=batch_size, progress=progress)


def _prepare_locked(archive, work, *, batch_size, progress):
    archive_id, rows = read_archive(archive)
    contract = load_contract(CATALOGUE_CONTRACT)
    policy = {
        "contract": stable_sha256(contract),
        "normalization": config.ANEMONE_NORMALIZATION_VERSION,
        "taxonomy": TAXONOMY_POLICY_VERSION,
        "catalogue_policy": 2,
    }
    candidate_id = stable_sha256(
        {
            "sources": source_versions(rows, contract),
            "policy": policy,
            "batch_size": batch_size,
        }
    )
    root = work / "candidates" / candidate_id
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(work / "ledger.sqlite", timeout=30) as ledger:
        ledger.execute("PRAGMA journal_mode=WAL")
        ledger.execute(
            "CREATE TABLE IF NOT EXISTS units (candidate_id TEXT, unit_id TEXT, status TEXT, normalization_id TEXT, error TEXT, PRIMARY KEY(candidate_id,unit_id))"
        )
        units, failures = [], []
        totals, methods, reads, classifications, concentrations = (
            Counter() for _ in range(5)
        )
        seen_samples, seen_occurrences, labels = set(), set(), Counter()
        for number, (run, unit_rows) in enumerate(catalogue_units(rows, batch_size), 1):
            unit_id = stable_sha256(
                {
                    "run": run,
                    "rows": source_versions(unit_rows, contract),
                    "policy": policy,
                }
            )
            previous = ledger.execute(
                "SELECT status,normalization_id FROM units WHERE candidate_id=? AND unit_id=?",
                (candidate_id, unit_id),
            ).fetchone()
            try:
                source = _stage_unit(
                    archive,
                    work / "raw",
                    run,
                    unit_rows,
                    contract,
                    min(
                        r.get("directory_observed_at")
                        or r.get("downloaded_at")
                        or "1970-01-01T00:00:00+00:00"
                        for r in unit_rows
                    ),
                )
                if previous and previous[0] == "complete":
                    frames, result = read_normalized_unit(
                        work / "normalized", previous[1]
                    )
                    if result["source_snapshot_id"] != source["snapshot_id"]:
                        raise ValueError("Ledger source identity mismatch")
                else:
                    result = normalize_anemone_snapshot(
                        source["snapshot_id"],
                        raw_root=work / "raw",
                        normalized_root=work / "normalized",
                        contract=contract,
                        execute=True,
                    )
                    frames, result = read_normalized_unit(
                        work / "normalized", result["normalization_id"]
                    )
                for item in frames["edna_sample"].to_dict("records"):
                    if (
                        item["sample_id"] in seen_samples
                        or item["source_occurrence_id"] in seen_occurrences
                    ):
                        raise ValueError("Cross-unit sample identity collision")
                    seen_samples.add(item["sample_id"])
                    seen_occurrences.add(item["source_occurrence_id"])
                    labels[item["original_sample_label"]] += 1
                totals.update({name: len(frame) for name, frame in frames.items()})
                d = frames["edna_detection"]
                methods.update(d["assignment_method"].value_counts().to_dict())
                reads.update(
                    d.groupby("assignment_method")["read_count"]
                    .sum()
                    .astype(int)
                    .to_dict()
                )
                concentrations.update(
                    d["concentration_status"].value_counts().to_dict()
                )
                classifications.update(
                    frames["edna_sample"]["sample_kind"].value_counts().to_dict()
                )
                units.append(
                    {
                        "unit_id": unit_id,
                        "normalization_id": result["normalization_id"],
                        "source_snapshot_id": source["snapshot_id"],
                        "run": run,
                        "manifest_sha256": file_sha256(
                            work
                            / "normalized"
                            / "snapshots"
                            / result["normalization_id"]
                            / "normalization_manifest.json"
                        ),
                    }
                )
                ledger.execute(
                    "INSERT OR REPLACE INTO units VALUES (?,?,?,?,NULL)",
                    (candidate_id, unit_id, "complete", result["normalization_id"]),
                )
            except Exception as exc:
                # Persist the reason, never credentials or arbitrary provider text.
                error = getattr(exc, "code", type(exc).__name__)
                ledger.execute(
                    "INSERT OR REPLACE INTO units VALUES (?,?,?,NULL,?)",
                    (candidate_id, unit_id, "quarantined", error),
                )
                failures.append(
                    {
                        "unit_id": unit_id,
                        "run": run,
                        "error": error,
                        "message": str(exc) if isinstance(exc, ValueError) else error,
                    }
                )
            ledger.commit()
            if progress:
                progress(
                    {
                        "unit": number,
                        "completed": len(units),
                        "quarantined": len(failures),
                    }
                )
        result = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "archive_manifest_sha256": archive_id,
            "policy": policy,
            "status": "quarantined" if failures else "complete",
            "units": units,
            "failures": failures,
            "row_counts": dict(totals),
            "assignment_rows": dict(methods),
            "read_counts_by_method": dict(reads),
            "sample_kinds": dict(classifications),
            "concentration_status": dict(concentrations),
            "source_files": len(rows),
            "source_occurrences": len(seen_occurrences),
            "distinct_reported_sample_names": len(labels),
            "physical_sample_count": None,
            "normalization_root": str(work / "normalized"),
            "production_imported": False,
            "withdrawals_applied": False,
        }
        if not failures and (
            totals["external_source_file"] != len(rows)
            or totals["edna_sample"] != len({r["url"].rsplit("/", 1)[0] for r in rows})
        ):
            raise ValueError("Candidate coverage reconciliation failed")
        atomic_json(
            work / "observations" / f"{archive_id}.json",
            {
                "archive_manifest_sha256": archive_id,
                "candidate_id": candidate_id,
                "status": result["status"],
                "archive": str(archive),
            },
        )
        if failures:
            atomic_json(root / "attempt-report.json", result)
        elif (root / "candidate.json").exists():
            original = json.loads((root / "candidate.json").read_text())
            for key in (
                "units",
                "row_counts",
                "assignment_rows",
                "read_counts_by_method",
                "sample_kinds",
            ):
                if original[key] != result[key]:
                    raise ValueError("Immutable candidate content conflict")
            result = original
        else:
            atomic_json(root / "candidate.json", result)
        if not failures:
            atomic_json(
                work / "candidate.json",
                {
                    "candidate_id": candidate_id,
                    "manifest_sha256": file_sha256(root / "candidate.json"),
                },
            )
        return result
