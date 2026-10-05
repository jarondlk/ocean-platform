"""Immutable, manually prepared SST panels with applied review provenance."""

from pathlib import Path
from datetime import timezone
import json
import tempfile
import uuid

import config
from ingestion.anemone_catalogue import file_sha256
from ingestion.artifact_store import ArtifactStore, BoundedLocalStore
from ingestion.immutable_bundle import (
    canonical_bytes,
    digest,
    read_bundle,
    seal_bundle,
    validate_id,
)
from ingestion.provenance_snapshot import SnapshotConflict
from preprocessing.research_recipe import SamplingRegistry
from preprocessing.research_sst import (
    GranuleInput,
    SSTProductDefinition,
    normalize_granule,
    MAX_OBSERVATIONS,
)

ALGORITHM = "reviewed-area-sst-v1"
MAX_PANEL_BYTES = 128 * 1024 * 1024


def panel_root():
    root = config.EDNA_CACHE_DIR if config.EDNA_ARTIFACT_URI else config.ANALYSIS_DIR
    return root / "research-sst"


def applied_definition(payload, kind):
    if (
        set(payload)
        != {
            "schema_version",
            "kind",
            "registry_key",
            "definition",
            "review_id",
            "scientific_approval_sha256",
        }
        or payload["schema_version"] != 1
        or payload["kind"] != kind
    ):
        raise ValueError("An applied research registry record is required")
    uuid.UUID(payload["review_id"])
    validate_id(payload["scientific_approval_sha256"])
    if kind == "sampling":
        definition = SamplingRegistry.model_validate(payload["definition"])
        expected_key = "sampling:" + definition.region_id
    else:
        definition = SSTProductDefinition.model_validate(payload["definition"])
        expected_key = "sst_product:" + definition.product_id
    if payload["registry_key"] != expected_key:
        raise ValueError("Applied registry key mismatch")
    return definition


def build_panel(product_registry, sampling_registry, granules):
    """Batch boundary: callers obtain registry records from the authenticated ledger."""
    product = applied_definition(product_registry, "sst_product")
    sampling = applied_definition(sampling_registry, "sampling")
    if not 1 <= len(granules) <= 1600:
        raise ValueError("SST panel granule count limit exceeded")
    inputs, observations, raw_files, seen, total = [], [], {}, set(), 0
    for path, granule in sorted(granules, key=lambda pair: pair[1].granule_id):
        if granule.granule_id in seen:
            raise ValueError("Duplicate SST panel granule")
        seen.add(granule.granule_id)
        # Read the exact bytes normalized below; recheck after normalization so
        # a file changed during preparation cannot enter an immutable panel.
        if path.is_symlink():
            raise ValueError("SST granule symlinks are forbidden")
        with path.open("rb") as handle:
            data = handle.read(MAX_PANEL_BYTES - total + 1)
        total += len(data)
        if total > MAX_PANEL_BYTES:
            raise ValueError("SST panel byte limit exceeded")
        observations.extend(
            normalize_granule(path, granule, product, list(sampling.areas))
        )
        if (
            len(observations) > MAX_OBSERVATIONS
            or file_sha256(path) != granule.raw_sha256
        ):
            raise ValueError("SST panel observation limit or changed raw granule")
        import hashlib

        if hashlib.sha256(data).hexdigest() != granule.raw_sha256:
            raise ValueError("SST panel raw byte mismatch")
        name = "raw-" + granule.granule_id + ".nc"
        raw_files[name] = data
        inputs.append({**granule.model_dump(mode="json"), "raw_filename": name})
    definition = {
        "schema_version": 1,
        "algorithm_version": ALGORITHM,
        "product_registry": product_registry,
        "sampling_registry": sampling_registry,
        "granules": inputs,
    }
    identity = digest(definition)
    files = {
        **raw_files,
        "definition.json": canonical_bytes(definition),
        "observations.json": canonical_bytes(observations),
    }
    if sum(map(len, files.values())) > MAX_PANEL_BYTES:
        raise ValueError("SST panel byte limit exceeded")
    return identity, definition, observations, files


def decode_panel(identity, manifest, files, *, metadata_only=False):
    """Verify a full panel or its pinned metadata references in an analysis export.

    Metadata verification does not claim the referenced NetCDF bytes are present.
    Full panel loads still require and hash every raw granule.
    """
    import hashlib

    validate_id(identity)
    required = (
        {"definition.json", "observations.json", "manifest.json"}
        if metadata_only
        else set(manifest["files"]) | {"manifest.json"}
    )
    if manifest.get("id") != identity or set(files) != required:
        raise ValueError("SST panel file contract mismatch")
    if json.loads(files["manifest.json"]) != manifest:
        raise ValueError("SST panel manifest mismatch")
    for name, sha in manifest["files"].items():
        validate_id(sha)
        if name in files and hashlib.sha256(files[name]).hexdigest() != sha:
            raise ValueError("SST panel integrity failure")
    definition = json.loads(files["definition.json"])
    if (
        digest(definition) != identity
        or definition.get("algorithm_version") != ALGORITHM
        or definition.get("schema_version") != 1
    ):
        raise ValueError("SST panel identity/algorithm mismatch")
    product = applied_definition(definition["product_registry"], "sst_product")
    sampling = applied_definition(definition["sampling_registry"], "sampling")
    expected = {"definition.json", "observations.json"}
    granules = {}
    for entry in definition["granules"]:
        granule = GranuleInput.model_validate(
            {k: v for k, v in entry.items() if k != "raw_filename"}
        )
        name = "raw-" + granule.granule_id + ".nc"
        if (
            entry["raw_filename"] != name
            or granule.granule_id in granules
            or manifest["files"].get(name) != granule.raw_sha256
            or (
                not metadata_only
                and hashlib.sha256(files[name]).hexdigest() != granule.raw_sha256
            )
        ):
            raise ValueError("SST panel raw provenance mismatch")
        expected.add(name)
        granules[granule.granule_id] = granule
    if set(manifest["files"]) != expected or not 1 <= len(granules) <= 1600:
        raise ValueError("SST panel granule file contract mismatch")
    rows = json.loads(files["observations.json"])
    if (
        not isinstance(rows, list)
        or len(rows) != len(granules) * len(sampling.areas)
        or len(rows) > MAX_OBSERVATIONS
    ):
        raise ValueError("SST panel observation count mismatch")
    areas = {a.area_id: digest(a.model_dump(mode="json")) for a in sampling.areas}
    seen = set()
    for row in rows:
        granule = granules.get(row["granule_id"])
        pair = row["granule_id"], row["area_id"]
        if (
            pair in seen
            or row["observation_id"]
            != digest({k: v for k, v in row.items() if k != "observation_id"})
            or not granule
            or row["raw_sha256"] != granule.raw_sha256
            or row["source_url"] != granule.source_url
            or row["area_version"] != areas.get(row["area_id"])
            or row["product_definition_id"] != digest(product.model_dump(mode="json"))
            or row.get("temporal_statistic") != product.temporal_statistic
            or row.get("measurement_type") != product.measurement_type
            or row["time_utc"]
            != granule.expected_time_utc.astimezone(timezone.utc).isoformat()
        ):
            raise ValueError("SST panel observation provenance mismatch")
        seen.add(pair)
    return {
        "panel_id": identity,
        "manifest": manifest,
        "definition": definition,
        "observations": rows,
        "files": files,
    }


def publish_panel(product_registry, sampling_registry, granules):
    identity, definition, rows, files = build_panel(
        product_registry, sampling_registry, granules
    )
    root = panel_root()
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    for name, data in files.items():
        (staging / name).write_bytes(data)
    manifest = seal_bundle(
        staging, root, identity, {"schema_version": 1, "algorithm_version": ALGORITHM}
    )
    manifest, files = read_bundle(
        root, identity, expected_digest=digest(manifest), max_bytes=MAX_PANEL_BYTES
    )
    decode_panel(identity, manifest, files)
    metadata = {"manifest_sha256": digest(manifest)}
    if config.EDNA_ARTIFACT_URI:
        ArtifactStore(config.EDNA_ARTIFACT_URI).publish(
            "sst-panels", identity, files, metadata=metadata
        )
    else:
        registry = BoundedLocalStore(root / "registry")
        record = canonical_bytes({"panel_id": identity, **metadata})
        try:
            registry.create(identity + ".json", record)
        except SnapshotConflict:
            if registry.read(identity + ".json").data != record:
                raise ValueError("SST panel registry conflict")
    return identity


def load_panel(identity):
    validate_id(identity)
    if config.EDNA_ARTIFACT_URI:
        receipt, files = ArtifactStore(config.EDNA_ARTIFACT_URI).read(
            "sst-panels", identity, max_bytes=MAX_PANEL_BYTES
        )
        manifest = json.loads(files["manifest.json"])
        if digest(manifest) != receipt["metadata"]["manifest_sha256"]:
            raise ValueError("SST panel receipt mismatch")
    else:
        registry = BoundedLocalStore(panel_root() / "registry")
        record = json.loads(registry.read(identity + ".json", max_bytes=4096).data)
        if record.get("panel_id") != identity:
            raise ValueError("SST panel registry identity mismatch")
        manifest, files = read_bundle(
            panel_root(),
            identity,
            expected_digest=validate_id(record["manifest_sha256"]),
            max_bytes=MAX_PANEL_BYTES,
        )
    return decode_panel(identity, manifest, files)
