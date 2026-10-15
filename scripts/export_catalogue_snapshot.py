"""Generate the versioned C09 schema and portable, synthetic byte examples."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.catalogue_snapshot_fixtures import fixture_snapshot
from ingestion.catalogue_snapshot_transfer import TransferManifest, build_transfer, transfer_id
from schema.catalogue_snapshot import SnapshotManifest, manifest_bytes, manifest_id
from schema.context_catalogue import ContractModel


class SnapshotContract(ContractModel):
    snapshot: SnapshotManifest
    transfer: TransferManifest


def generated_files() -> dict[Path, str]:
    schema = SnapshotContract.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:ocean:catalogue-snapshot:v1"
    schema["x-runtime-validation-required"] = (
        "Cross-object source/operation/origin bindings, exact bytes/counts, "
        "canonical IDs, strict scope semantics, and current access need Python validation."
    )
    snapshot, contents = fixture_snapshot()
    transfer = build_transfer(
        snapshot, contents, destination_id="synthetic:v1-destination",
        authorization_ref="synthetic-authorization-only",
        origin_system="synthetic-independent-source",
        qualifications={key: ("Synthetic fixture only", "Local tests only") for key in contents},
        encodings={key: "json-rows-v1" for key in contents},
    )
    examples = {
        "example_version": "catalogue-snapshot-examples-v1",
        "qualification": "Synthetic frozen examples; no real source access or publication",
        "snapshot_id": manifest_id(snapshot),
        "snapshot": json.loads(manifest_bytes(snapshot)),
        "contents_base64": {key: base64.b64encode(value).decode("ascii") for key, value in contents.items()},
        "transfer_id": transfer_id(transfer),
        "transfer": transfer.model_dump(mode="json"),
    }
    return {ROOT / "schema" / name: json.dumps(value, ensure_ascii=False, sort_keys=True,
                                               indent=2, allow_nan=False) + "\n"
            for name, value in (("catalogue_snapshot.v1.schema.json", schema),
                                ("catalogue_snapshot_examples.json", examples))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, expected in generated_files().items():
        if args.check:
            if not path.exists() or path.read_text() != expected:
                print(f"Stale C09 artifact: {path.relative_to(ROOT)}", file=sys.stderr)
                return 1
        else:
            path.write_text(expected)
    print("C09 snapshot schema and synthetic byte examples are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
