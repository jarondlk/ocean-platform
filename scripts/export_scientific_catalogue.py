"""Generate the C13 frozen index/response contract and logical examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schema.context_catalogue import ContractModel
from schema.scientific_catalogue import ScientificRegistry, ScientificResponse
from schema.scientific_catalogue_fixtures import scientific_fixture


class ScientificCatalogueContract(ContractModel):
    registry: ScientificRegistry
    response: ScientificResponse


def logical_examples():
    registry, tables = scientific_fixture(3)
    return {
        "example_version": "c13-logical-inputs-v1",
        "qualification": "Synthetic logical index; bind actual child snapshots and explicitly seal before use.",
        "registry": registry.model_dump(mode="json"),
        "tables": tables,
        "expected": {
            "published_rows": 3,
            "independent_researcher_approval": False,
            "provider_endorsement": False,
            "workflow_execution": False,
        },
    }


def generated_files():
    schema = ScientificCatalogueContract.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:ocean:scientific-catalogue:v1"
    schema["x-runtime-validation-required"] = (
        "C09 exact object bytes/ownership and current access; child snapshot bindings; "
        "published scope compatibility, derived receipt/tombstone eligibility; complete table "
        "counts, decoded resource limits, and reviewed relationship lineage require Python validation."
    )
    return {
        ROOT / "schema" / name: json.dumps(
            payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
        for name, payload in [
            ("scientific_catalogue.v1.schema.json", schema),
            ("scientific_catalogue_examples.json", logical_examples()),
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, expected in generated_files().items():
        if args.check:
            if not path.exists() or path.read_text() != expected:
                print(f"Stale C13 artifact: {path.relative_to(ROOT)}", file=sys.stderr)
                return 1
        else:
            path.write_text(expected)
    print("C13 frozen scientific index schema and logical examples are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
