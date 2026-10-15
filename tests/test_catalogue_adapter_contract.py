"""Portable C10 examples replay through real Parquet/C09 adapter boundaries."""

import json
from pathlib import Path

import pandas as pd

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from orchestration.frozen_catalogue import AdapterAccess, FrozenCatalogueAdapter
from schema.catalogue_adapter import FrozenDataset
from schema.catalogue_adapter_fixtures import seal_fixture
from scripts.export_catalogue_adapter import generated_files
from tests.test_frozen_catalogue_adapters import CTD, META, operation

ROOT = Path(__file__).resolve().parents[1]


def test_generated_contract_and_logical_inputs_are_current():
    for path, expected in generated_files().items():
        assert path.read_text() == expected


def test_portable_logical_examples_replay_without_embeddings_or_live_sources(tmp_path):
    examples = json.loads((ROOT / "schema/catalogue_adapter_examples.json").read_text())
    datasets = [
        (
            FrozenDataset.model_validate(item["metadata"]),
            {
                name: pd.DataFrame.from_records(
                    rows,
                    columns=[
                        column["name"]
                        for column in next(
                            table
                            for table in item["metadata"]["tables"]
                            if table["name"] == name
                        )["columns"]
                    ],
                )
                for name, rows in item["table_rows"].items()
            },
        )
        for item in examples["datasets"]
    ]
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda m: True
    )
    snapshot = seal_fixture(store, datasets)
    adapter = FrozenCatalogueAdapter(
        store=store, access=AdapterAccess("user-a", "revision-1", lambda s, d: True)
    )
    expected = examples["expected"]
    for identity, table, name in [
        (CTD, "casts", "ctd_casts"),
        (CTD, "depth_observations", "ctd_depth_observations"),
        (META, "collections", "metagenome_libraries"),
        (META, "kraken_abundance", "kraken_normalized_cells"),
    ]:
        assert (
            adapter.query(
                operation(snapshot, identity, "c10.count", table=table)
            ).result.rows[0]["count"]
            == expected[name]
        )
    result = adapter.query(
        operation(
            snapshot,
            CTD,
            "c10.summary",
            table="depth_observations",
            column="temperature",
        )
    )
    assert result.result.rows[0]["mean"] == expected["ctd_temperature_mean"]
