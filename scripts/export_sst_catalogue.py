"""Generate C11 SST metadata/response schema and portable logical inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from schema.context_catalogue import ContractModel
from schema.sst_catalogue import SSTDataset, SSTResponse
from schema.sst_catalogue_fixtures import sst_fixture


class SSTCatalogueContract(ContractModel):
    dataset: SSTDataset
    response: SSTResponse


def logical_examples():
    cases = []
    for name, fixture in [
        ("final_regional", sst_fixture(6)),
        (
            "interim_regional",
            sst_fixture(
                6, dataset_id="synthetic:sst:mur-interim", generation="interim"
            ),
        ),
        (
            "final_grid",
            sst_fixture(
                6, dataset_id="synthetic:sst:mur-grid", entity="grid_observation"
            ),
        ),
        (
            "unknown_sampling",
            sst_fixture(6, dataset_id="synthetic:sst:unknown-calendar", sampling=False),
        ),
    ]:
        metadata, frames = fixture
        rows = {
            role: [
                {key: None if pd.isna(value) else value for key, value in row.items()}
                for row in frame.to_dict("records")
            ]
            for role, frame in frames.items()
        }
        cases.append(
            {
                "case": name,
                "metadata": metadata.model_dump(mode="json"),
                "table_rows": rows,
            }
        )
    absent, _ = sst_fixture(0, dataset_id="synthetic:sst:unavailable")
    absent_value = absent.model_dump(mode="json")
    absent_value["table"].update(
        object_id=None,
        row_count=None,
        availability={
            "status": "unavailable",
            "reason": "No eligible frozen product export",
        },
        completeness="unavailable",
    )
    absent = SSTDataset.model_validate(absent_value)
    cases.append(
        {
            "case": "unavailable",
            "metadata": absent.model_dump(mode="json"),
            "table_rows": {},
        }
    )
    return {
        "example_version": "c11-logical-inputs-v1",
        "qualification": "Synthetic source-owned observations; explicit Parquet/C09 sealing required",
        "datasets": cases,
        "expected": {
            "raw_rows_per_retained_dataset": 6,
            "eligible_nonnull_observations": 3,
            "measured_zero_observations": 1,
            "missing_value_observations": 1,
            "invalid_observations": 1,
            "excluded_observations": 1,
            "eligible_sum": 9.0,
            "eligible_mean": 3.0,
            "expected_daily_dates": 7,
            "missing_eligible_dates": [
                "2024-02-28",
                "2024-02-29",
                "2024-03-01",
                "2024-03-02",
            ],
        },
    }


def generated_files():
    schema = SSTCatalogueContract.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:ocean:sst-catalogue:v1"
    schema["x-runtime-validation-required"] = (
        "C09 byte identity/current access and eligibility; canonical product identities; "
        "calendar/product/support compatibility; fixed Arrow schema, decoded budgets, "
        "quality semantics, unique cells and complete-population operations require Python validation."
    )
    return {
        ROOT / "schema" / name: json.dumps(
            payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
        for name, payload in [
            ("sst_catalogue.v1.schema.json", schema),
            ("sst_catalogue_examples.json", logical_examples()),
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, expected in generated_files().items():
        if args.check:
            if not path.exists() or path.read_text() != expected:
                print(f"Stale C11 artifact: {path.relative_to(ROOT)}", file=sys.stderr)
                return 1
        else:
            path.write_text(expected)
    print("C11 frozen SST schema and logical examples are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
