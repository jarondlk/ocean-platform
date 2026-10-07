"""Context-first NASA archive; native patches and scientific publication stay pending."""

from functools import partial

from ingestion.immutable_bundle import digest
from ingestion.sst_hybrid_acquisition import acquire_hybrid, build_hybrid_plan
from ingestion.sst_nasa_subset import (
    download_nasa_pilot,
    nasa_subset_plan,
    validate_nasa_pilot,
)

MAX_CONTEXT_BYTES = 4 * 1024**3
ALGORITHM = "private-nasa-mur-context-v1"


def context_child(descriptor, provider):
    if (
        provider != "nasa_podaac"
        or descriptor["role"] != "context"
        or len(descriptor["days"]) != 1
    ):
        raise ValueError("NASA context worker requires one-day context descriptors")
    return nasa_subset_plan(
        [
            {
                "day": descriptor["days"][0],
                "role": "context",
                "footprint": descriptor["footprint"],
                "location_id": None,
            }
        ]
    )


def build_nasa_context_plan(inventory):
    hybrid = build_hybrid_plan(inventory)
    requests = []
    for r in hybrid["requests"]:
        if r["role"] != "context":
            continue
        descriptor = {k: r[k] for k in ("role", "days", "footprint", "location_id")}
        child = context_child(descriptor, "nasa_podaac")
        requests.append({**descriptor, "request_sha256": child["plan_sha256"]})
    plan = {
        "schema_version": 1,
        "kind": "historical_nasa_mur_context_acquisition",
        "algorithm": ALGORITHM,
        "provider": "nasa_podaac",
        "acquisition_scope": "context_only",
        "source_hybrid_plan_sha256": hybrid["plan_sha256"],
        "source_inventory": inventory,
        "sampling_years": hybrid["sampling_years"],
        "context_footprint": hybrid["context_footprint"],
        "excluded_days": hybrid["excluded_days"],
        "expected": {
            "context_days": len(requests),
            "native_location_days": 0,
            "excluded_context_days": len(hybrid["excluded_days"]),
            "excluded_native_location_days": 0,
        },
        "request_count": len(requests),
        "estimated_raw_bytes": len(requests) * 1024**2,
        "maximum_raw_bytes": MAX_CONTEXT_BYTES,
        "native_patch_acquisition_pending": True,
        "interim_retention": "separate_unapproved_raw_generation_not_eligible_final_series",
        "scientific_approval": False,
        "scientific_publication": False,
        "requests": requests,
    }
    return {**plan, "plan_sha256": digest(plan)}


def validate_nasa_context_plan(plan):
    if plan != build_nasa_context_plan(plan["source_inventory"]):
        raise ValueError("NASA context preflight binding mismatch")


def acquire_nasa_context(plan, destination, work_root, credential_path, **kwargs):
    # Allow exact interim containers to be retained as raw provenance with their
    # own classification. Strict final-series qualification still rejects them.
    validator = partial(validate_nasa_pilot, archive_interim=True)
    downloader = kwargs.pop(
        "downloader", partial(download_nasa_pilot, credential_path=credential_path)
    )
    return acquire_hybrid(
        plan,
        destination,
        work_root,
        downloader=downloader,
        plan_validator=validate_nasa_context_plan,
        child_planner=context_child,
        raw_validator=validator,
        **kwargs,
    )
