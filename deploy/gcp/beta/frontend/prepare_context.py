"""Export a committed, source-only beta host context without local/generated files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
IMPORT = re.compile(r'''(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)["'](\.[^"']+)["']''')


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def source_context(revision: str, output: Path) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use an explicit full committed source SHA")
    if git("rev-parse", "--verify", revision + "^{commit}").decode().strip() != revision:
        raise ValueError("Source commit mismatch")
    tracked = set(git("ls-tree", "-r", "--name-only", revision, "--", "frontend-v1", "frontend/lib/csv.ts").decode().splitlines())
    seeds = {name for name in tracked if name.startswith("frontend-v1/hosting/")
             and (name.startswith(("frontend-v1/hosting/app/", "frontend-v1/hosting/lib/", "frontend-v1/hosting/scripts/"))
                  or PurePosixPath(name).name in {"middleware.ts", "next.config.mjs", "next-env.d.ts", "tsconfig.json", "package.json", "package-lock.json"})}
    seeds |= {"frontend-v1/package.json", "frontend-v1/package-lock.json"}
    assert "frontend-v1/hosting/lib/settings.ts" in seeds
    selected: dict[str, bytes] = {}
    pending = list(seeds)
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        if name not in tracked or not (name.startswith("frontend-v1/") or name == "frontend/lib/csv.ts"):
            raise ValueError("Missing or out-of-scope source: " + name)
        mode = git("ls-tree", revision, "--", name).decode().split()[0]
        if mode != "100644":
            raise ValueError("Refusing non-regular source: " + name)
        data = git("show", revision + ":" + name)
        selected[name] = data
        if PurePosixPath(name).suffix not in {".ts", ".tsx", ".mjs"}:
            continue
        for relative in IMPORT.findall(data.decode()):
            # Normalize relative imports without permitting escape from the UI tree.
            parts: list[str] = []
            for part in (PurePosixPath(name).parent / relative).parts:
                if part == "..":
                    if not parts:
                        raise ValueError("Import escapes source tree")
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            base = "/".join(parts)
            matches = [p for p in [base, base + ".ts", base + ".tsx", base + ".mjs", base + "/index.ts", base + "/index.tsx"] if p in tracked]
            if len(matches) != 1:
                raise ValueError("Unresolved or ambiguous local import: " + name + " -> " + relative)
            pending.append(matches[0])
    banned = {"frontend-v1/src/fixtures.ts", "frontend-v1/src/adapter.ts", "frontend-v1/src/v1-entry.tsx", "frontend-v1/src/research-app.tsx"}
    if banned & selected.keys():
        raise ValueError("Production host graph reaches the synthetic preview")
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new directory")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in sorted(selected.items()):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    packaging = git("show", revision + ":deploy/gcp/beta/frontend/Dockerfile")
    own_source = git("show", revision + ":deploy/gcp/beta/frontend/prepare_context.py")
    if packaging != (HERE / "Dockerfile").read_bytes() or own_source != Path(__file__).read_bytes():
        raise ValueError("Packaging bytes must equal the explicit source commit")
    (output / "Dockerfile").write_bytes(packaging)
    files = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(selected.items())}
    manifest = {"version": "beta-frontend-source-context-v1", "source_commit": revision,
                "source_files": files, "dockerfile_sha256": hashlib.sha256(packaging).hexdigest(),
                "packager_sha256": hashlib.sha256(own_source).hexdigest(),
                "synthetic_preview_graph_included": False, "credentials_or_generated_files_included": False}
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = source_context(args.revision, args.output)
    print(json.dumps({"source_commit": result["source_commit"], "files": len(result["source_files"]),
                      "manifest_sha256": hashlib.sha256((args.output / "source-manifest.json").read_bytes()).hexdigest()}, indent=2))
