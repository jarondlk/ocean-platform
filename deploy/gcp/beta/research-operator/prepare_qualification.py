"""Prepare committed code for disposable PG16 qualification, not a deploy image.

Copies only tracked Python sources, migration templates and dependency locks.
Scientific files, credentials, local settings and the checkout's Git store are
excluded. Synthetic test fixtures remain outside every production image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
CODE_ROOTS = {"api", "db", "schema", "orchestration", "ingestion", "preprocessing",
              "retrieval", "sandbox", "migrations", "tests"}


def prepare(*, revision, output):
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Exact committed source required")
    output = output.absolute()
    if output.exists() or output.is_symlink() or output.is_relative_to(ROOT) or any(p.is_symlink() for p in output.parents):
        raise ValueError("New private qualification directory required")
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision], cwd=ROOT, text=True).splitlines()
    selected = []
    for name in paths:
        path = Path(name)
        if (path.suffix == ".py" and (path.parts[0] in CODE_ROOTS or name.startswith("deploy/gcp/beta/"))
                or name in {"config.py", "model_runtime.py", "alembic.ini", "migrations/script.py.mako",
                            "requirements/dev.txt", "requirements/runtime.txt", "tests/__init__.py"}):
            if name != "api/main.py":
                selected.append(name)
    files = {}
    for name in selected:
        data = subprocess.check_output(["git", "show", revision + ":" + name], cwd=ROOT)
        current = ROOT / name
        if current.is_symlink() or current.read_bytes() != data:
            raise ValueError("Selected checkout source differs from its commit")
        files[name] = data
    output.mkdir(mode=0o700)
    pins = {}
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        pins[name] = hashlib.sha256(data).hexdigest()
    receipt = {"source_revision": revision, "qualification_only": True, "source_files": pins,
               "scientific_files_or_credentials_included": False, "production_image_created": False}
    (output / "qualification-source.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return {"source_revision": revision, "files": len(files), "qualification_only": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(revision=args.revision, output=args.output)))
