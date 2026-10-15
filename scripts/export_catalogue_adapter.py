"""Generate C10 frozen input schema and portable logical acceptance examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from schema.catalogue_adapter import AdapterResponse, FrozenDataset
from schema.catalogue_adapter_fixtures import ctd_fixture, metagenome_fixture
from schema.context_catalogue import ContractModel


class CatalogueAdapterContract(ContractModel):
    dataset: FrozenDataset
    response: AdapterResponse


def generated_files():
    schema = CatalogueAdapterContract.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:ocean:catalogue-adapter:v1"
    schema["x-runtime-validation-required"] = (
        "C09 byte identity/current access, Arrow schema and decode bounds, source ownership, "
        "row relationships, full abundance cells and scope semantics need Python validation."
    )
    examples = []
    for metadata, frames in [ctd_fixture(2), metagenome_fixture(2)]:
        rows = {
            name: [
                {key: None if pd.isna(value) else value for key, value in row.items()}
                for row in frame.to_dict("records")
            ]
            for name, frame in frames.items()
        }
        examples.append(
            {"metadata": metadata.model_dump(mode="json"), "table_rows": rows}
        )
    payload = {
        "example_version": "c10-logical-inputs-v1",
        "qualification": "Synthetic source-owned records; convert to explicit Parquet exports, then seal with C09",
        "datasets": examples,
        "expected": {
            "ctd_casts": 2,
            "ctd_depth_observations": 4,
            "ctd_temperature_mean": 0.625,
            "metagenome_libraries": 2,
            "kraken_normalized_cells": 8,
            "beyond_top_ten_kraken_mean": 0.05,
            "beyond_top_ten_metaeuk_mean": 0.15,
        },
    }
    return {
        ROOT / "schema" / name: json.dumps(
            value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
        for name, value in [
            ("catalogue_adapter.v1.schema.json", schema),
            ("catalogue_adapter_examples.json", payload),
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, expected in generated_files().items():
        if args.check:
            if not path.exists() or path.read_text() != expected:
                print(f"Stale C10 artifact: {path.relative_to(ROOT)}", file=sys.stderr)
                return 1
        else:
            path.write_text(expected)
    print("C10 frozen adapter schema and logical examples are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
