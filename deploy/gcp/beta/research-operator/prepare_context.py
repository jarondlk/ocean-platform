"""Prepare only committed operator source and public schema/privilege metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PROJECT = "ocean-v1-beta-20261101"
BASE_IMAGE = ("asia-northeast1-docker.pkg.dev/" + PROJECT + "/ocean-v1-beta/context-operator@sha256:"
    "a9be3b94b156c9d1260c609fb5958c4e503772d3564b95c097fa9f3d47bb1340")


def schema_contract():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from db.app_models import AppBase
    from api.v1_beta_research_host import CONTEXT_TABLE_PRIVILEGES, CONTEXT_UPDATE_COLUMNS
    import importlib.util
    spec = importlib.util.spec_from_file_location("research_grant_policy", HERE / "privileges.py")
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    tables = {"app_user": ["SELECT"], "alembic_version": ["SELECT"],
        "rate_limit_bucket": ["SELECT", "INSERT", "UPDATE"],
        **{t: sorted(rights) for t, rights in CONTEXT_TABLE_PRIVILEGES.items()}}
    columns = {table: {"UPDATE": sorted(names)} for table, names in CONTEXT_UPDATE_COLUMNS.items()}
    columns["audit_event"] = {"SELECT": ["created_at"]}
    expected = {table: sorted(AppBase.metadata.tables[table].columns.keys())
        for table in set(policy.READ_TABLES) | set(tables) if table != "alembic_version"}
    expected["alembic_version"] = ["version_num"]
    return {"expected_columns": expected, "existing_serving_table_privileges": tables,
            "existing_serving_column_privileges": columns}


def prepare(*, revision, output):
    output = Path(output).absolute()
    if (not re.fullmatch(r"[a-f0-9]{40}", revision) or output.exists() or output.is_relative_to(ROOT)
            or output.is_symlink() or any(p.is_symlink() for p in output.parents)):
        raise ValueError("Exact source and new private output required")
    sources = {}
    for name in ("Dockerfile", "research_operator.py", "privileges.py", "prepare_context.py"):
        path = HERE / name
        data = subprocess.check_output(["git", "show", revision + ":" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError("Operator checkout differs from selected source")
        sources[name] = data
    for name in ("db/app_models.py", "api/v1_beta_research_host.py"):
        data = subprocess.check_output(["git", "show", revision + ":" + name], cwd=ROOT)
        if (ROOT / name).read_bytes() != data:
            raise ValueError("Privilege/schema contract differs from selected source")
        sources[name] = data
    manifest = {"version": "ocean-v1-beta-research-operator-v1", "project_id": PROJECT,
        "revision": revision, "base_operator_image": BASE_IMAGE,
        "source_pins": {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()},
        "credentials_or_scientific_data_included": False, **schema_contract()}
    output.mkdir(mode=0o700)
    for name in ("Dockerfile", "research_operator.py", "privileges.py"):
        (output / name).write_bytes(sources[name])
    (output / "research-operator-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"revision": revision, "base_image": BASE_IMAGE, "cloud_calls": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(revision=args.revision, output=args.output)))
