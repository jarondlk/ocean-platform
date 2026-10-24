"""Record frontend acceptance for the C23 Next.js security patch.

This helper performs no deployment, test-source edits or automatic dependency
repair. Existing receipts and command outputs are create-only.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[6]
BASE = Path(__file__).resolve().parent
OWNED = [f"{project}/{name}" for project in ("frontend", "frontend-v1")
         for name in ("package.json", "package-lock.json")]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins():
    names = subprocess.check_output([
        "git", "ls-files", "-z", "--", "frontend", "frontend-v1"
    ], cwd=ROOT).decode().split("\0")
    return {name: digest(ROOT / name) for name in names if name}


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def check_project(project):
    commands = [
        ("audit", ["npm", "audit", "--omit=dev", "--audit-level=moderate", "--json",
                   "--cache", "/private/tmp/ocean-c23-npm-cache"]),
        ("test", ["npm", "test"]),
        ("typecheck", ["npm", "run", "typecheck"]),
        ("build", ["npm", "run", "build"]),
    ]
    results = []
    env = dict(os.environ, NEXT_TELEMETRY_DISABLED="1")
    for label, args in commands:
        started = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        with (BASE / f"{project}-{label}.stdout.txt").open("x") as stdout:
            with (BASE / f"{project}-{label}.stderr.txt").open("x") as stderr:
                process = subprocess.run(args, cwd=ROOT / project, env=env,
                                         stdout=stdout, stderr=stderr)
        result = {"project": project, "check": label, "command": args,
                  "cwd": project, "started_at": started,
                  "seconds": round(time.monotonic() - start, 3),
                  "exit_code": process.returncode}
        write_json(BASE / f"{project}-{label}.command.json", result)
        results.append(result)
        print(json.dumps(result), flush=True)
    return results


def main():
    before = pins()
    write_json(BASE / "acceptance-start.json", {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "npm": subprocess.check_output(["npm", "--version"], text=True).strip(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                        text=True).strip(),
        "frontend_source_pins": before,
        "owned_source_pins": {p: before[p] for p in OWNED},
    })
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(check_project, ("frontend", "frontend-v1")))
    after = pins()
    changed = sorted(p for p in before.keys() | after.keys()
                     if before.get(p) != after.get(p))
    outcome = {"recorded_at": datetime.now(timezone.utc).isoformat(),
               "results": [r for project in results for r in project],
               "frontend_source_files": len(before),
               "changed_paths": changed,
               "passed": not changed and all(r["exit_code"] == 0
                                             for project in results for r in project),
               "frontend_source_pins_after": after,
               "recorder_sha256": digest(Path(__file__).resolve()),
               "C23_complete": False, "deployment_performed": False}
    write_json(BASE / "acceptance.json", outcome)
    print(json.dumps({k: v for k, v in outcome.items()
                      if k != "frontend_source_pins_after"}), flush=True)
    raise SystemExit(0 if outcome["passed"] else 1)


if __name__ == "__main__":
    main()
