from copy import deepcopy
import pytest
from scripts.snapshot_cop17_artifacts import transport_receipt, rewrite_pointer


def test_storage_restore_changes_only_generation_receipts_and_preserves_science():
    original = {
        "id": "science-id",
        "namespace": "analysis",
        "files": {
            "table.json": {"sha256": "sealed-hash", "size": 12, "generation": 100}
        },
        "metadata": {"decision": "operational only"},
    }
    before = deepcopy(original)
    copied = transport_receipt(original, {"table.json": 200})
    assert original == before
    assert copied["id"] == original["id"] and copied["metadata"] == original["metadata"]
    assert copied["files"]["table.json"] == {
        "sha256": "sealed-hash",
        "size": 12,
        "generation": 200,
    }
    assert rewrite_pointer(
        {"receipt_sha256": "old", "analysis_id": "old", "scientific_hash": "old"},
        {"old": "new"},
    ) == {"receipt_sha256": "new", "analysis_id": "old", "scientific_hash": "old"}


@pytest.mark.parametrize(
    "mapping",
    [
        {},
        {"other.json": 200},
        {"table.json": 0},
        {"table.json": True},
        {"table.json": "200"},
        {"table.json": 200, "extra": 300},
    ],
)
def test_unsealed_or_ambiguous_generation_binding_is_rejected(mapping):
    with pytest.raises(ValueError):
        transport_receipt(
            {
                "files": {
                    "table.json": {"sha256": "sealed", "size": 12, "generation": 100}
                }
            },
            mapping,
        )
