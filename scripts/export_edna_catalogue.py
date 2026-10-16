"""Generate C12 canonical eDNA schema and portable logical relational inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from schema.context_catalogue import ContractModel
from schema.edna_catalogue import EDNADataset, EDNAResponse
from schema.edna_catalogue_fixtures import edna_fixture


class EDNACatalogueContract(ContractModel):
    dataset: EDNADataset
    response: EDNAResponse


def logical_examples():
    cases = []
    for name, count in [("mixed_raw_inventory", 10), ("available_empty", 0)]:
        metadata, frames = edna_fixture(count, dataset_id=f"synthetic:edna:{name}")
        cases.append(
            {
                "case": name,
                "metadata": metadata.model_dump(mode="json"),
                "table_rows": {
                    role: [
                        {
                            key: None if pd.isna(value) else value
                            for key, value in row.items()
                        }
                        for row in frame.to_dict("records")
                    ]
                    for role, frame in frames.items()
                },
            }
        )
    metadata, _ = edna_fixture(0, dataset_id="synthetic:edna:unavailable")
    value = metadata.model_dump(mode="json")
    for table in value["tables"]:
        table.update(
            object_id=None,
            row_count=None,
            availability={
                "status": "unavailable",
                "reason": "No eligible retained canonical export",
            },
            completeness="unavailable",
        )
    cases.append(
        {
            "case": "unavailable",
            "metadata": EDNADataset.model_validate(value).model_dump(mode="json"),
            "table_rows": {},
        }
    )
    return {
        "example_version": "c12-logical-inputs-v1",
        "qualification": "Synthetic canonical relational inventory; explicit Parquet/C09 sealing and current access required",
        "datasets": cases,
        "expected": {
            "mixed_occurrences": 10,
            "mixed_assays": 10,
            "mixed_detections": 35,
            "mixed_classifications": 10,
            "available_empty_count": 0,
            "unavailable_count": None,
            "raw_methods": [
                "qcauto_target",
                "qcauto_95pct_3nn_target",
                "qcauto_nontarget",
                "qcauto_95pct_3nn_nontarget",
            ],
        },
    }


def generated_files():
    schema = EDNACatalogueContract.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:ocean:edna-catalogue:v1"
    schema["x-runtime-validation-required"] = (
        "C09 identity/access/withdrawal, relational references, canonical classifications/review lineage, "
        "source-backed method availability, exact Arrow types/decoded budgets and C01 scientific eligibility "
        "require Python validation. Raw inventory descriptors do not grant scientific execution."
    )
    return {
        ROOT / "schema" / name: json.dumps(
            value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
        for name, value in [
            ("edna_catalogue.v1.schema.json", schema),
            ("edna_catalogue_examples.json", logical_examples()),
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, expected in generated_files().items():
        if args.check:
            if not path.exists() or path.read_text() != expected:
                print(f"Stale C12 artifact: {path.relative_to(ROOT)}", file=sys.stderr)
                return 1
        else:
            path.write_text(expected)
    print("C12 frozen eDNA schema and logical examples are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
