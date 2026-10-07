"""List or acquire a small explicitly selected historical Himawari comparison set."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.himawari_probe import (
    MAX_FILES,
    connect,
    download_probe,
    list_directory,
    parse_remote_file,
    read_credentials,
    validate_directory,
)
from ingestion.immutable_bundle import atomic_json
from ingestion.sst_acquisition import _read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--list-directory")
    choice.add_argument("--selection", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    selection = None
    if args.list_directory:
        validate_directory(args.list_directory)
    else:
        selection = _read_json(args.selection, 8192)
        if (
            not isinstance(selection, dict)
            or set(selection) != {"remote_paths"}
            or not isinstance(selection["remote_paths"], list)
            or not 1 <= len(selection["remote_paths"]) <= MAX_FILES
            or len(set(selection["remote_paths"])) != len(selection["remote_paths"])
        ):
            raise ValueError("Select 1–4 distinct explicit Himawari archive files")
        for path in selection["remote_paths"]:
            parse_remote_file(path)
    if not args.execute:
        print("Validated bounded probe; add --execute for encrypted archive access")
        return
    credentials = read_credentials(args.credentials_file)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = {"scientific_approval": False, "files": [], "status": "probe_pending"}
    try:
        with connect(credentials) as client:
            if args.list_directory:
                receipt["listing"] = list_directory(client, args.list_directory)
            else:
                for path in selection["remote_paths"]:
                    receipt["files"].append(
                        download_probe(client, path, args.output_dir)
                    )
                    atomic_json(args.output_dir / "probe.json", receipt)
            receipt["status"] = "access_probe_complete_scientific_comparison_pending"
    except Exception as error:
        # Provider exception text can contain credentials or server text.
        receipt.update(status="probe_failed", error_type=type(error).__name__)
    atomic_json(args.output_dir / "probe.json", receipt)
    print(f"Himawari: {receipt['status']}; {len(receipt['files'])} verified raw files")
    if receipt["status"] == "probe_failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
