"""Bounded scientific selections of immutable SST panels, with raw provenance.

Only an operator verifies child raw files when publishing a collection. Serving
verifies the pinned metadata; it does not claim to rehash absent raw NetCDF.
"""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import config
from ingestion.artifact_store import ArtifactStore, BoundedLocalStore
from ingestion.immutable_bundle import (
    canonical_bytes,
    digest,
    read_bundle,
    seal_bundle,
    validate_id,
)
from ingestion.provenance_snapshot import SnapshotConflict
from ingestion.research_sst_panel import (
    ALGORITHM as PANEL_ALGORITHM,
    MAX_PANEL_BYTES,
    applied_definition,
    decode_panel,
)
from preprocessing.research_sst import MAX_OBSERVATIONS

ALGORITHM = "reviewed-area-sst-collection-v1"
MAX_CHILDREN = 512
MAX_COLLECTION_BYTES = 96 * 1024 * 1024
FILES = {"definition.json", "children.json", "observations.json"}


def collection_root():
    root = config.EDNA_CACHE_DIR if config.EDNA_ARTIFACT_URI else config.ANALYSIS_DIR
    return root / "research-sst-collections"


def collection_registered(identity):
    validate_id(identity)
    if config.EDNA_ARTIFACT_URI:
        return identity in ArtifactStore(config.EDNA_ARTIFACT_URI).entries(
            "sst-collections"
        )
    root = collection_root() / "registry"
    if root.is_symlink():
        raise ValueError("Invalid SST collection registry path")
    path = root / (identity + ".json")
    if path.is_symlink():
        raise ValueError("Invalid SST collection registry path")
    return path.is_file()


def _child_reference(panel, area_ids):
    definition = panel["definition"]
    if definition["algorithm_version"] != PANEL_ALGORITHM:
        raise ValueError("Nested SST collections are forbidden")
    areas = {
        a["area_id"] for a in definition["sampling_registry"]["definition"]["areas"]
    }
    if not area_ids or len(area_ids) != len(set(area_ids)) or set(area_ids) - areas:
        raise ValueError("Select existing, unique reviewed child areas")
    return {
        "panel_id": panel["panel_id"],
        "manifest": panel["manifest"],
        "definition": {
            k: v
            for k, v in definition.items()
            if k not in {"product_registry", "sampling_registry"}
        },
        "observations": panel["observations"],
        "area_ids": sorted(area_ids),
    }


def _flatten(definition, children):
    """Reconstruct and verify each child; reject overlapping contradictory rows."""
    product = applied_definition(definition["product_registry"], "sst_product")
    applied_definition(definition["sampling_registry"], "sampling")
    if not 1 <= len(children) <= MAX_CHILDREN or len(children) != len(
        definition["children"]
    ):
        raise ValueError("SST collection child limit/contract exceeded")
    rows, seen, used = {}, set(), 0
    daily = product.temporal_statistic in {"daily_mean", "daily_foundation_analysis"}
    for child, reference in zip(children, definition["children"]):
        if set(child) != {
            "panel_id",
            "manifest",
            "definition",
            "observations",
            "area_ids",
        }:
            raise ValueError("Invalid SST collection child reference")
        identity = validate_id(child["panel_id"])
        if identity in seen or reference != {
            "panel_id": identity,
            "manifest_sha256": digest(child["manifest"]),
            "area_ids": child["area_ids"],
        }:
            raise ValueError("SST collection child identity mismatch")
        seen.add(identity)
        if (
            "product_registry" in child["definition"]
            or "sampling_registry" in child["definition"]
        ):
            raise ValueError("SST collection child registry override")
        full = {
            **child["definition"],
            "product_registry": definition["product_registry"],
            "sampling_registry": definition["sampling_registry"],
        }
        if full.get("algorithm_version") != PANEL_ALGORITHM:
            raise ValueError("Nested SST collections are forbidden")
        files = {
            "definition.json": canonical_bytes(full),
            "observations.json": canonical_bytes(child["observations"]),
            "manifest.json": canonical_bytes(child["manifest"]),
        }
        # The common applied registries are retained once. Reconstruct one
        # child for verification without charging the shared bytes repeatedly.
        used += len(canonical_bytes(child))
        if (
            used > MAX_COLLECTION_BYTES
            or sum(map(len, files.values())) > MAX_PANEL_BYTES
        ):
            raise ValueError("SST collection child metadata byte limit exceeded")
        panel = decode_panel(identity, child["manifest"], files, metadata_only=True)
        if _child_reference(panel, child["area_ids"]) != child:
            raise ValueError("SST collection child selection mismatch")
        for row in child["observations"]:
            if row["area_id"] not in child["area_ids"]:
                continue
            when = datetime.fromisoformat(row["time_utc"])
            stamp = (
                when.astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat()
                if daily
                else when.isoformat()
            )
            key = row["area_id"], stamp
            if key in rows and rows[key] != row:
                raise ValueError(
                    "Conflicting SST collection area/day observations; choose explicit tile ownership"
                )
            rows[key] = row
            if len(rows) > MAX_OBSERVATIONS:
                raise ValueError(
                    "SST collection observation limit exceeded; select a bounded cohort"
                )
    return sorted(
        rows.values(),
        key=lambda row: (row["time_utc"], row["area_id"], row["observation_id"]),
    )


def build_collection(selections):
    """Each (fully verified child panel, reviewed area IDs) pins an explicit scope."""
    # Consume lazily: never retain all child raw files in operator memory.
    first, children, used = None, [], 0
    for panel, areas in selections:
        if len(children) >= MAX_CHILDREN:
            raise ValueError("SST collection child limit exceeded")
        if first is None:
            first = panel["definition"]
        if any(
            panel["definition"][key] != first[key]
            for key in ("product_registry", "sampling_registry")
        ):
            raise ValueError(
                "SST collection requires one applied product and sampling generation"
            )
        # Publication callers must supply the full verified child bytes; a
        # metadata-only export cannot establish raw verification at publication.
        decode_panel(panel["panel_id"], panel["manifest"], panel["files"])
        child = _child_reference(panel, areas)
        used += len(canonical_bytes(child))
        if used > MAX_COLLECTION_BYTES:
            raise ValueError("SST collection byte limit exceeded")
        children.append(child)
    if first is None:
        raise ValueError("SST collection requires at least one child")
    children.sort(key=lambda child: child["panel_id"])
    definition = {
        "schema_version": 1,
        "algorithm_version": ALGORITHM,
        "product_registry": first["product_registry"],
        "sampling_registry": first["sampling_registry"],
        "integrity_basis": "operator_verified_raw_children_serving_verified_metadata",
        "children": [
            {
                "panel_id": c["panel_id"],
                "manifest_sha256": digest(c["manifest"]),
                "area_ids": c["area_ids"],
            }
            for c in children
        ],
    }
    observations = _flatten(definition, children)
    files = {
        "definition.json": canonical_bytes(definition),
        "children.json": canonical_bytes(children),
        "observations.json": canonical_bytes(observations),
    }
    if sum(map(len, files.values())) > MAX_COLLECTION_BYTES:
        raise ValueError("SST collection byte limit exceeded")
    return digest(definition), definition, observations, files


def decode_collection(identity, manifest, files):
    validate_id(identity)
    if (
        manifest.get("id") != identity
        or set(manifest.get("files", {})) != FILES
        or set(files) != FILES | {"manifest.json"}
        or sum(map(len, files.values())) > MAX_COLLECTION_BYTES
    ):
        raise ValueError("SST collection file/byte contract mismatch")
    if json.loads(files["manifest.json"]) != manifest:
        raise ValueError("SST collection manifest mismatch")
    for name, sha in manifest["files"].items():
        if hashlib.sha256(files[name]).hexdigest() != validate_id(sha):
            raise ValueError("SST collection integrity failure")
    definition = json.loads(files["definition.json"])
    if (
        digest(definition) != identity
        or definition.get("schema_version") != 1
        or definition.get("algorithm_version") != ALGORITHM
        or definition.get("integrity_basis")
        != "operator_verified_raw_children_serving_verified_metadata"
        or set(definition)
        != {
            "schema_version",
            "algorithm_version",
            "product_registry",
            "sampling_registry",
            "integrity_basis",
            "children",
        }
    ):
        raise ValueError("SST collection identity/algorithm mismatch")
    children, observations = (
        json.loads(files["children.json"]),
        json.loads(files["observations.json"]),
    )
    if _flatten(definition, children) != observations:
        raise ValueError("SST collection aggregate mismatch")
    return {
        "panel_id": identity,
        "manifest": manifest,
        "definition": definition,
        "children": children,
        "observations": observations,
        "files": files,
    }


def publish_collection(selections):
    identity, definition, rows, files = build_collection(selections)
    root = collection_root()
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    for name, data in files.items():
        (staging / name).write_bytes(data)
    manifest = seal_bundle(
        staging, root, identity, {"schema_version": 1, "algorithm_version": ALGORITHM}
    )
    manifest, files = read_bundle(
        root, identity, expected_digest=digest(manifest), max_bytes=MAX_COLLECTION_BYTES
    )
    decode_collection(identity, manifest, files)
    metadata = {"manifest_sha256": digest(manifest)}
    if config.EDNA_ARTIFACT_URI:
        ArtifactStore(config.EDNA_ARTIFACT_URI).publish(
            "sst-collections", identity, files, metadata=metadata
        )
    else:
        registry = BoundedLocalStore(root / "registry")
        record = canonical_bytes({"panel_id": identity, **metadata})
        try:
            registry.create(identity + ".json", record)
        except SnapshotConflict:
            if registry.read(identity + ".json").data != record:
                raise ValueError("SST collection registration conflict")
    return identity


def load_collection(identity):
    validate_id(identity)
    if config.EDNA_ARTIFACT_URI:
        receipt, files = ArtifactStore(config.EDNA_ARTIFACT_URI).read(
            "sst-collections", identity, max_bytes=MAX_COLLECTION_BYTES
        )
        manifest = json.loads(files["manifest.json"])
        if digest(manifest) != receipt["metadata"]["manifest_sha256"]:
            raise ValueError("SST collection receipt mismatch")
    else:
        record = json.loads(
            BoundedLocalStore(collection_root() / "registry")
            .read(identity + ".json", max_bytes=4096)
            .data
        )
        if record.get("panel_id") != identity:
            raise ValueError("SST collection registry identity mismatch")
        manifest, files = read_bundle(
            collection_root(),
            identity,
            expected_digest=validate_id(record["manifest_sha256"]),
            max_bytes=MAX_COLLECTION_BYTES,
        )
    return decode_collection(identity, manifest, files)
