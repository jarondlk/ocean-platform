"""Bounded per-load validation reuse preserves every row's source assertions."""
import json

import pytest

from ingestion import edna_catalogue_inputs as inputs
from schema.edna_catalogue_fixtures import edna_fixture


def fixture(taxa=("Taxon A",), count=4):
    metadata, frames = edna_fixture(count)
    frames = {name: frame.astype(object) for name, frame in frames.items()}
    rows = frames["detections"]
    for ordinal, index in enumerate(rows.index):
        name = taxa[ordinal % len(taxa)]
        rows.loc[index, "taxonomy_json"] = json.dumps({"species": name})
        rows.loc[index, "assigned_taxon_name"] = name
        rows.loc[index, "assigned_taxon_rank"] = "species"
    return metadata, frames


def observe(monkeypatch):
    calls = []
    original = inputs._json_object

    def parse(value, **kwargs):
        if kwargs.get("label") == "taxonomy":
            calls.append(value)
        return original(value, **kwargs)

    monkeypatch.setattr(inputs, "_json_object", parse)
    return calls


def test_repeated_taxonomy_is_validated_once_per_load_without_mutating_rows(monkeypatch):
    metadata, frames = fixture(("Taxon A", "Taxon B"))
    original = {name: frame.copy(deep=True) for name, frame in frames.items()}
    calls = observe(monkeypatch)
    inputs.validate_rows(metadata, frames)
    assert len(calls) == 2
    inputs.validate_rows(metadata, frames)
    assert len(calls) == 4
    for name, frame in frames.items():
        assert frame.equals(original[name])


def test_later_row_assignment_is_still_checked_after_taxonomy_hit():
    metadata, frames = fixture()
    frames["detections"].iloc[-1, frames["detections"].columns.get_loc("assigned_taxon_name")] = "Different"
    with pytest.raises(ValueError, match="assigned taxonomy contradicts"):
        inputs.validate_rows(metadata, frames)


@pytest.mark.parametrize("raw", [
    '{"species":"A","species":"B"}', '{"species":NaN}',
    '{"invented_rank":"A"}', '["Taxon A"]', '{"species":true}',
])
def test_bad_taxonomy_after_a_valid_repeated_prefix_is_rejected(raw):
    metadata, frames = fixture()
    frames["detections"].iloc[-1, frames["detections"].columns.get_loc("taxonomy_json")] = raw
    with pytest.raises(ValueError):
        inputs.validate_rows(metadata, frames)


@pytest.mark.parametrize("budget", ["entries", "bytes"])
def test_small_memo_evicts_or_skips_without_changing_acceptance(monkeypatch, budget):
    metadata, frames = fixture(("Taxon A", "Taxon B"))
    calls = observe(monkeypatch)
    if budget == "entries":
        monkeypatch.setattr(inputs, "_TAXONOMY_MEMO_ENTRIES", 1)
    else:
        monkeypatch.setattr(inputs, "_TAXONOMY_MEMO_BYTES", 1)
    inputs.validate_rows(metadata, frames)
    assert len(calls) == len(frames["detections"])


def test_a_new_load_recomputes_assignment_instead_of_reusing_process_state(monkeypatch):
    metadata, frames = fixture()
    inputs.validate_rows(metadata, frames)
    monkeypatch.setattr(inputs, "deepest_resolved_assignment", lambda _: ("Changed", "species"))
    with pytest.raises(ValueError, match="assigned taxonomy contradicts"):
        inputs.validate_rows(metadata, frames)


@pytest.mark.parametrize("value", [True, -1, 2**63, 1.0])
def test_primitive_checks_still_cover_each_row(value):
    metadata, frames = fixture()
    frames["detections"].iloc[-1, frames["detections"].columns.get_loc("read_count")] = value
    with pytest.raises(ValueError, match="primitive int64"):
        inputs.validate_rows(metadata, frames)


def test_exact_large_integer_is_preserved():
    metadata, frames = fixture()
    column = frames["detections"].columns.get_loc("read_count")
    frames["detections"].iloc[-1, column] = 2**63 - 1
    inputs.validate_rows(metadata, frames)
    assert type(frames["detections"].iloc[-1, column]) is int
    assert frames["detections"].iloc[-1, column] == 2**63 - 1
