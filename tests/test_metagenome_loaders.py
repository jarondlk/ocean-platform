from __future__ import annotations

from preprocessing.metagenome import (
    load_gn_consistency,
    load_group_mapping,
)


def test_genus_consistency_uses_raw_taxid_level_genus_order(tmp_path):
    path = tmp_path / "gn.consistency.tsv"
    path.write_text("1738655\t3\tWoeseia\n", encoding="utf-8")

    result = load_gn_consistency(path)

    assert result.iloc[0]["genus_taxid"] == 1738655
    assert result.iloc[0]["consistency_level"] == 3
    assert result.iloc[0]["genus"] == "Woeseia"


def test_group_mapping_discards_optional_header_row(tmp_path):
    path = tmp_path / "Kraken.genus-group.tsv"
    path.write_text(
        "genus_txid\tgenus_name\tupper_txid\tupper_name\n"
        "1118494\tDactyliosolen\t33836\tCoscinodiscophyceae\n",
        encoding="utf-8",
    )

    result = load_group_mapping(path)

    assert len(result) == 1
    assert result.iloc[0]["genus"] == "Dactyliosolen"
