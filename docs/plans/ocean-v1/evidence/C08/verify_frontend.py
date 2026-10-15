"""Verify the C08 v1 frontend against its unchanged dependency lock."""

from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

output = Path(__file__).resolve().parent
root = output.parents[4]
node_directory = (
    "/Users/jaronchai/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
)
environment = dict(
    os.environ,
    PATH=node_directory + os.pathsep + os.environ.get("PATH", ""),
    NEXT_TELEMETRY_DISABLED="1",
)
lock = json.loads((root / "frontend-v1/package-lock.json").read_text())
installed = json.loads(
    (root / "frontend-v1/node_modules/next/package.json").read_text()
)
assert installed["version"] == lock["packages"]["node_modules/next"]["version"]
receipt = {
    "node": subprocess.check_output(
        [node_directory + "/node", "--version"], text=True
    ).strip(),
    "locked_next": installed["version"],
    "checks": [],
}
for name, command in [
    ("tests", ["npm", "test"]),
    ("typecheck", ["npm", "run", "typecheck"]),
    ("build", ["npm", "run", "build"]),
]:
    with (output / f"frontend-v1-{name}.txt").open("w") as log:
        result = subprocess.run(
            command,
            cwd=root / "frontend-v1",
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    receipt["checks"].append(
        {"name": name, "command": command, "exit_code": result.returncode}
    )
    if result.returncode:
        break
(output / "frontend-result.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
sys.exit(receipt["checks"][-1]["exit_code"])
