"""Versioned eligibility for derived evidence; regeneration is not approval.

Raw historical files remain readable. Only current, unchanged, input-bound
artifacts with an explicit eligibility decision can enter scientific context.
The existing EvidenceDecision contract supplies that decision, never the model
or a producer's algorithmic reliability tier.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from preprocessing.research_recipe import EvidenceDecision, Hash, ResearchModel

CURRENT_METHODS = {
    "taxa_env_correlation": "taxa-env-full-abundance-v2",
    "sst_ctd_validation": "sst-ctd-spatial-v2",
    "corroboration": "reliability-checks-v2",
    "diversity_prediction": "reliability-checks-v2",
}
# Gap estimates use the old spatially unqualified baseline. They stay unavailable
# as validated evidence; C02 does not redesign interpolation or approve it.
FILE_METHODS = {"taxa_env_correlations.parquet": "taxa_env_correlation", "sst_ctd_validation.parquet": "sst_ctd_validation",
                "corroboration.parquet": "corroboration", "diversity_prediction.parquet": "diversity_prediction",
                "gap_interpolation.parquet": "gap_interpolation"}
TYPE_METHODS = {"correlation": "taxa_env_correlation", "cross_source_validation": "sst_ctd_validation", **{key: key for key in CURRENT_METHODS},
                "gap_interpolation": "gap_interpolation"}
ID_METHODS = {"analysis_taxa_env_correlations": "taxa_env_correlation",
              "reliability_sst_ctd_validation": "sst_ctd_validation",
              "reliability_corroboration_summary": "corroboration",
              "reliability_diversity_prediction": "diversity_prediction",
              "reliability_gap_interpolation": "gap_interpolation"}
UNAFFECTED_ANALYSIS_TYPES = {"trend", "ctd_temporal_trends", "diversity_indices", "bay_comparison",
                             "edna_diversity", "edna_method_summary", "edna_controls", "edna_associations", "edna_environment_links",
                             "regional_frequency", "provisional_demo", "detection_frequency", "edna_catalogue_summary"}


def digest(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    checksum = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def input_receipts(paths):
    return {str(Path(path).resolve()): file_hash(path) for path in paths if Path(path).is_file()}


class DerivedReceipt(ResearchModel):
    schema_version: Literal[1] = 1
    method_id: str = Field(min_length=1, max_length=100)
    method_version: str = Field(min_length=1, max_length=100)
    inputs: dict[str, Hash]
    parameters: dict[str, Any]
    output_sha256: Hash
    generation_sha256: Hash
    operation_status: Literal["computed", "unavailable"]
    operation_reason: str | None = None
    eligibility: Literal["review_required", "eligible", "invalidated", "superseded"] = "review_required"
    eligibility_reason: str = "Regenerated output requires an explicit eligibility review."
    review: EvidenceDecision | None = None
    scientific_approval: Literal[False] = False
    superseded_by: Hash | None = None


@dataclass(frozen=True)
class DerivedEligibility:
    eligible: bool
    status: str
    reason: str
    method_version: str | None = None
    generation_sha256: str | None = None
    scientific_approval: Literal[False] = False

    def as_dict(self):
        return asdict(self)


def _generation(receipt):
    return digest({key: receipt[key] for key in ("method_id", "method_version", "inputs", "parameters",
                                               "output_sha256", "operation_status", "operation_reason")})


def make_receipt(method_id, output_sha256, operation):
    version = operation.get("method_version") or CURRENT_METHODS.get(method_id, "unvalidated-legacy-method")
    values = {
        "method_id": method_id, "method_version": version,
        "inputs": operation.get("inputs", {}), "parameters": operation.get("parameters", {}),
        "output_sha256": output_sha256, "operation_status": operation.get("status", "unavailable"),
        "operation_reason": operation.get("reason"),
    }
    return DerivedReceipt(**values, generation_sha256=_generation(values)).model_dump(mode="json")


def document_method(document, role=None):
    if not isinstance(document, dict):
        return "invalid_document"
    identity = document.get("id") or document.get("doc_id")
    receipt = document.get("derived_artifact")
    receipt_method = receipt.get("method_id") if isinstance(receipt, dict) else None
    method = ID_METHODS.get(identity) or TYPE_METHODS.get(document.get("analysis_type")) or receipt_method
    if method:
        return method
    if role == "reliability" or document.get("source_type") == "reliability":
        return "unknown_reliability"
    if (role == "analysis" or document.get("source_type") in {"analysis", "pre_analysis"}
            or str(identity).startswith("analysis_")) and document.get("analysis_type") not in UNAFFECTED_ANALYSIS_TYPES:
        return "unknown_analysis"
    return None


def _document_payload(document):
    return {key: value for key, value in document.items() if key not in {"derived_artifact", "derived_eligibility"}}


def stamp_document(document, method_id, operation):
    result = _document_payload(document)
    result["derived_artifact"] = make_receipt(method_id, digest(result), operation)
    return result


def _superseded_generations():
    import config
    generations = set()
    for root in (config.ANALYSIS_DIR, config.RELIABILITY_DIR):
        path = root / "derived_invalidations.json"
        if path.exists():
            try:
                registry = json.loads(path.read_text())
                values = registry["superseded_generations"]
                if registry.get("schema_version") != 1 or not isinstance(values, list) or any(
                    not isinstance(value, str) or len(value) != 64 or set(value) - set("0123456789abcdef") for value in values
                ):
                    return None
                generations.update(values)
            except (OSError, ValueError, TypeError, KeyError):
                # An unreadable invalidation registry cannot authorize evidence.
                return None
    return generations


_CONFIGURED_TOMBSTONES = object()


def receipt_eligibility(raw, output_sha256, *, expected_inputs=None, require_review=True,
                        superseded_generations=_CONFIGURED_TOMBSTONES):
    try:
        receipt = DerivedReceipt.model_validate(raw)
        values = receipt.model_dump(mode="json")
        if receipt.eligibility in {"invalidated", "superseded"}:
            return DerivedEligibility(False, receipt.eligibility, receipt.eligibility_reason,
                                      receipt.method_version, receipt.generation_sha256)
        # Frozen consumers inject the exact retained tombstones. The sentinel
        # preserves the existing configured-registry behavior for legacy callers.
        superseded = (_superseded_generations()
                      if superseded_generations is _CONFIGURED_TOMBSTONES
                      else superseded_generations)
        if superseded is not None and (not isinstance(superseded, (set, frozenset, list, tuple))
                or any(not isinstance(value, str) or len(value) != 64
                       or set(value) - set("0123456789abcdef") for value in superseded)):
            superseded = None
        if superseded is None:
            status, reason = "invalid_registry", "The retained invalidation registry cannot be verified."
        elif receipt.generation_sha256 in superseded:
            status, reason = "superseded", "This retained generation was superseded; copying it does not restore eligibility."
        elif CURRENT_METHODS.get(receipt.method_id) != receipt.method_version:
            status, reason = "legacy_method", "This method version is ineligible; regenerate and review it."
        elif receipt.output_sha256 != output_sha256 or receipt.generation_sha256 != _generation(values):
            status, reason = "hash_mismatch", "Output or method/input provenance changed after regeneration."
        elif receipt.operation_status != "computed" or not receipt.inputs:
            status, reason = "unavailable", receipt.operation_reason or "The computation or its input provenance is unavailable."
        elif expected_inputs is not None and receipt.inputs != expected_inputs:
            status, reason = "stale_inputs", "The retained input hashes do not match the selected current inputs."
        elif not require_review:
            return DerivedEligibility(False, "computed_candidate", "Current hash-bound computation; scientific eligibility still requires review.",
                                      receipt.method_version, receipt.generation_sha256)
        elif receipt.eligibility != "eligible" or receipt.review is None:
            status, reason = "review_required", "Regeneration and algorithmic checks do not establish scientific eligibility."
        elif receipt.review.evidence_sha256 != receipt.generation_sha256:
            status, reason = "review_mismatch", "The eligibility decision does not bind this output and its exact method/inputs."
        else:
            return DerivedEligibility(True, "eligible", "Current method, unchanged output/inputs and bound eligibility decision.",
                                      receipt.method_version, receipt.generation_sha256)
        return DerivedEligibility(False, status, reason, receipt.method_version, receipt.generation_sha256)
    except (ValueError, TypeError, KeyError):
        return DerivedEligibility(False, "invalid_receipt", "The derived-evidence receipt cannot be verified.")


def document_eligibility(document, *, role=None, expected_inputs=None):
    if not isinstance(document, dict):
        return DerivedEligibility(False, "invalid_document", "Invalid derived document.")
    method = document_method(document, role)
    if method is None:
        return DerivedEligibility(True, "unaffected", "This document is outside the affected derived methods.")
    raw = document.get("derived_artifact")
    if raw is None:
        return DerivedEligibility(False, "legacy_unversioned", "Affected legacy evidence requires regeneration and eligibility review.")
    result = receipt_eligibility(raw, digest(_document_payload(document)), expected_inputs=expected_inputs)
    if not isinstance(raw, dict):
        return result
    if raw.get("method_id") != method:
        return DerivedEligibility(False, "method_mismatch", "The receipt does not match this derived document type.")
    return result


def review_document(document, decision):
    """Pure application of a trusted existing eligibility decision, not a UI grant.

    Callers must already be authorized by the established review workflow. Tests
    use synthetic reviewers; producers never call this automatically.
    """
    review = EvidenceDecision.model_validate(decision)
    receipt = DerivedReceipt.model_validate(document["derived_artifact"])
    if receipt.eligibility in {"invalidated", "superseded"}:
        raise ValueError("Invalidated historical evidence cannot be reauthorized; regenerate it.")
    if review.evidence_sha256 != receipt.generation_sha256:
        raise ValueError("Review must bind the exact regenerated method, inputs and output.")
    result = dict(document)
    result["derived_artifact"] = receipt.model_copy(update={"eligibility": "eligible", "review": review,
                                                           "eligibility_reason": "Explicit bound eligibility decision."}).model_dump(mode="json")
    if not document_eligibility(result).eligible:
        raise ValueError("This method/output is not eligible for review authorization.")
    return result


def invalidate_document(document, reason, *, superseded_by=None):
    result = dict(document)
    receipt = DerivedReceipt.model_validate(document["derived_artifact"])
    result["derived_artifact"] = receipt.model_copy(update={
        "eligibility": "superseded" if superseded_by else "invalidated",
        "eligibility_reason": reason, "superseded_by": superseded_by,
    }).model_dump(mode="json")
    return result


def current_method_inputs(method_id):
    """Read only known configured inputs; receipt strings never choose files."""
    import config
    paths = {
        "taxa_env_correlation": [config.SERVING_DIR / "sample_multisource_context.parquet",
                                 config.NORMALIZED_DIR / "kraken_genus_abundance.parquet"],
        "sst_ctd_validation": [config.NORMALIZED_DIR / "ctd_summary.parquet",
                               config.NORMALIZED_DIR / "sst_daily_summary.parquet"],
        "corroboration": [config.SERVING_DIR / "sample_multisource_context.parquet",
                          config.RELIABILITY_DIR / "sst_ctd_validation.parquet",
                          config.RELIABILITY_DIR / "diversity_prediction.parquet",
                          config.NORMALIZED_DIR / "ctd_summary.parquet",
                          config.NORMALIZED_DIR / "sst_daily_summary.parquet",
                          config.NORMALIZED_DIR / "kraken_genus_abundance.parquet",
                          config.ANALYSIS_DIR / "diversity_indices.parquet",
                          config.ANALYSIS_DIR / "taxa_env_correlations.parquet",
                          config.ANALYSIS_DIR / "derived_artifacts.json"],
        "diversity_prediction": [config.ANALYSIS_DIR / "diversity_indices.parquet",
                                 config.ANALYSIS_DIR / "taxa_env_correlations.parquet",
                                 config.ANALYSIS_DIR / "derived_artifacts.json",
                                 config.NORMALIZED_DIR / "kraken_genus_abundance.parquet",
                                 config.SERVING_DIR / "sample_multisource_context.parquet"],
    }
    return input_receipts(paths.get(method_id, ()))


def retain_artifact_history(directory, filenames):
    """Copy the previous local generation before replacement, without deleting it."""
    directory = Path(directory)
    names = [name for name in filenames if Path(name).name == name and (directory / name).is_file()]
    snapshots = {name: (directory / name).read_bytes() for name in names}
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in snapshots.items()}
    if not hashes:
        return None
    generation = digest(hashes)
    target = directory / "derived_history" / generation
    target.mkdir(parents=True, exist_ok=True)
    for name, checksum in hashes.items():
        output = target / name
        if output.exists() and file_hash(output) != checksum:
            raise ValueError("A retained immutable history file was modified.")
        if not output.exists():
            output.write_bytes(snapshots[name])
    manifest = {"schema_version": 1, "generation_sha256": generation, "files": hashes,
                "current_eligibility": "superseded", "reason": "Retained history is not current validated evidence."}
    (target / "history.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    # Preserve raw historical bytes, but invalidate their reviewed generation IDs
    # independently so a copied or symlinked archive cannot become current again.
    registry_path = directory / "derived_invalidations.json"
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {"schema_version": 1, "superseded_generations": []}
    superseded = set(registry["superseded_generations"])
    for name, raw in snapshots.items():
        if name.endswith("documents.jsonl"):
            candidates = [json.loads(line).get("derived_artifact", {}) for line in raw.decode().splitlines() if line.strip()]
        elif name == "derived_artifacts.json":
            candidates = list(json.loads(raw)["artifacts"].values())
        else:
            continue
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("generation_sha256"):
                superseded.add(candidate["generation_sha256"])
    registry["superseded_generations"] = sorted(superseded)
    registry_path.write_text(json.dumps(registry, sort_keys=True, indent=2) + "\n")
    return manifest


def write_artifact_manifest(directory, artifacts):
    """Bind generated local files and methods; every candidate still needs review."""
    root = Path(directory)
    receipts = {name: make_receipt(method, file_hash(root / name), operation)
                for name, (method, operation) in artifacts.items() if (root / name).is_file()}
    manifest = {"schema_version": 1, "artifacts": receipts}
    (root / "derived_artifacts.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


def file_eligibility(path, *, expected_inputs=None, output_sha256=None):
    path = Path(path)
    if "derived_history" in path.resolve().parts:
        return DerivedEligibility(False, "superseded", "Retained history is not current validated evidence.")
    try:
        manifest = json.loads((path.parent / "derived_artifacts.json").read_text())
        raw = manifest["artifacts"][path.name]
        if not isinstance(raw, dict) or raw.get("method_id") != FILE_METHODS.get(path.name):
            return DerivedEligibility(False, "method_mismatch", "The receipt does not match this artifact file.")
        return receipt_eligibility(raw, output_sha256 or file_hash(path), expected_inputs=expected_inputs)
    except (OSError, ValueError, TypeError, KeyError):
        return DerivedEligibility(False, "legacy_unversioned", "Retained file has no verifiable current eligibility receipt.")
