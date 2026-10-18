"""C19 scientific projection preserves native states, units and opaque cursors."""

from copy import deepcopy
import base64
import json
import uuid

import pytest

from orchestration.research_controller_observations import ObservationCollector
from schema.context_catalogue_fixtures import make_catalogue
from schema.research_controller import (
    ControllerBinding,
    canonical_hash,
    compact_observations,
)
from tests.catalogue_service_support import payload, synthetic_service, fixture_user


@pytest.fixture
def source():
    catalogue, _, service = synthetic_service(
        catalogue=make_catalogue(137, snapshot_id="a" * 64)
    )
    binding = ControllerBinding(
        investigation_id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        revision_id=str(uuid.uuid4()),
        snapshot_id=catalogue.snapshot_id,
        payload_sha256="b" * 64,
    )
    return catalogue, service, binding


def response(source, row):
    catalogue, service, _ = source
    value = service.query(
        payload(
            catalogue,
            operation_id="c13.inventory",
            operation_version="c13-v1",
            input_ids=["root:data"],
            parameters={"limit": 1},
        ),
        fixture_user(),
    )
    value["rows"] = [row]
    value["columns"] = [
        {
            "key": key,
            "title": {"en": key, "ja": key},
            "unit": "degC" if key == "temperature" else None,
        }
        for key in row
    ]
    value["receipt"].update(
        operation_id="c13.coverage",
        content_sha256=canonical_hash({"rows": [row], "columns": value["columns"]}),
    )
    return value


def add(source, row):
    catalogue, _, binding = source
    collector = ObservationCollector(binding)
    observation = collector.add(
        "catalogue.coverage",
        payload(catalogue, object_id="synthetic:dataset:000000"),
        response(source, row),
    )
    return collector, observation


def test_known_native_sst_optional_null_reason_is_not_unknown_coverage(source):
    _, observation = add(
        source,
        {
            "calendar": "UTC",
            "observation_entity": "grid_cell_day",
            "expected_days": 4,
            "observed_days": 3,
            "missing_days": 1,
            "coverage_state": "known",
            "reason": None,
        },
    )
    assert "coverage_known" in observation.known_fields


@pytest.mark.parametrize("state", ["unknown", "unavailable", "partial"])
def test_native_coverage_state_cannot_be_upgraded_to_known(source, state):
    _, observation = add(
        source,
        {
            "calendar": "UTC",
            "observation_entity": "grid_cell_day",
            "expected_days": None,
            "observed_days": 3,
            "missing_days": None,
            "coverage_state": state,
            "reason": "No sampling contract",
        },
    )
    assert "coverage_known" not in observation.known_fields


def test_ctd_unknown_collection_label_remains_unresolved(source):
    _, observation = add(
        source,
        {
            "collection_period": None,
            "precision": "unknown",
            "count": 2,
            "entity": "casts",
        },
    )
    assert "coverage_known" not in observation.known_fields


def test_native_units_and_limitations_survive_preview_compaction(source):
    catalogue, _, binding = source
    value = response(source, {"temperature": -1.2})
    value["qualifications"] = [
        "Retained sampling support only; no local precision claim."
    ]
    observation = ObservationCollector(binding).add(
        "catalogue.coverage",
        payload(catalogue, object_id="synthetic:dataset:000000"),
        value,
    )
    summary = json.loads(compact_observations((observation,), keep_recent=0))[0]
    assert summary["preview"] == []
    assert any("degC" in text for text in summary["qualifications"])
    assert value["qualifications"][0] in summary["qualifications"]


def test_actual_listing_cursor_metadata_is_not_shortened_as_preview_text(source):
    catalogue, service, binding = source
    args = payload(catalogue, filters={"kinds": ["dataset"]})
    listing = service.list(args, fixture_user())
    listing = deepcopy(listing)
    original = listing["next_cursor"]
    decoded = base64.urlsafe_b64decode(original + "=" * (-len(original) % 4))
    # Equivalent accepted JSON whitespace makes a valid long opaque token;
    # arbitrary padding characters would fail C08 validation before projection.
    listing["next_cursor"] = (
        base64.urlsafe_b64encode(decoded + b" " * 1200).decode().rstrip("=")
    )
    assert 1000 < len(listing["next_cursor"]) <= 2048
    observation = ObservationCollector(binding).add("catalogue.list", args, listing)
    meta = json.loads(observation.preview_json)[0]["listing_page"]
    assert meta["next_cursor"] == listing["next_cursor"]
    summary = json.loads(compact_observations((observation,), maximum_bytes=16000))[0]
    assert summary["listing_page"]["next_cursor"] == listing["next_cursor"]
