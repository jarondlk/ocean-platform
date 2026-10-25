"""Create-only source-bound local checks for the C23 operator adapter."""
from __future__ import annotations

import ast
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[6]
BASE = Path(__file__).resolve().parent
ROOTS = ("orchestration/experiment_sandbox/linux_runtime.py",
         "tests/test_experiment_sandbox_linux_runtime.py")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    found, pending = {}, deque(ROOT / value for value in ROOTS)

    def add_module(name):
        if not name:
            return
        parts = name.split(".")
        for index in range(1, len(parts) + 1):
            initializer = ROOT.joinpath(*parts[:index], "__init__.py")
            if initializer.is_file():
                pending.append(initializer)
        path = ROOT.joinpath(*parts).with_suffix(".py")
        if path.is_file():
            pending.append(path)

    while pending:
        path = pending.popleft()
        key = str(path.relative_to(ROOT))
        if key in found:
            continue
        raw = path.read_bytes()
        found[key] = hashlib.sha256(raw).hexdigest()
        module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        for node in ast.walk(ast.parse(raw)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    add_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    prefix = package.split(".")
                    parent = prefix[:len(prefix) - node.level + 1]
                    base = ".".join(parent + ([node.module] if node.module else []))
                else:
                    base = node.module or ""
                add_module(base)
                for alias in node.names:
                    add_module(base + "." + alias.name)
    return dict(sorted(found.items()))


def main():
    output = BASE / "local-20261025-01"
    output.mkdir()
    before = snapshot()
    prior_names = ["checkpoint.json", "pushed-checkpoint.json", "hosted-preparation.json",
                   "materials/discovery-20261024/verification.json"]
    prior = {name: digest(BASE.parent / name) for name in prior_names}
    original = json.loads((BASE.parent / "pushed-checkpoint.json").read_text())["source_files"]
    for name, expected in original.items():
        assert digest(ROOT / name) == expected, ("original preparation source changed", name)
    (output / "source-before.json").write_text(json.dumps(before, indent=2, sort_keys=True) + "\n")
    commands = [
        ("pytest", [str(ROOT / ".venv/bin/python"), "-m", "pytest", ROOTS[1], "-q", "--tb=short"]),
        ("ruff", [str(ROOT / ".venv/bin/ruff"), "check", *ROOTS]),
    ]
    checks = []
    for label, command in commands:
        start = time.monotonic()
        with (output / (label + ".txt")).open("x") as stream:
            code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
        checks.append({"label": label, "command": command, "exit_code": code,
                       "seconds": time.monotonic() - start})
        if code:
            raise SystemExit(json.dumps({"failed": label, "evidence": str(output)}))
    text = (output / "pytest.txt").read_text()
    assert re.search(r"\b78 passed\b", text) and "failed" not in text and "skipped" not in text
    after = snapshot()
    (output / "source-after.json").write_text(json.dumps(after, indent=2, sort_keys=True) + "\n")
    assert before == after, "Local imported source graph drifted during checks"
    assert prior == {name: digest(BASE.parent / name) for name in prior_names}
    assert all(digest(ROOT / name) == expected for name, expected in original.items())
    evidence = {str(path.relative_to(ROOT)): digest(path) for path in sorted(output.iterdir())}
    receipt = {
        "component": "C23", "kind": "Operator Linux adapter local control acceptance; real runtime gates open",
        "recorded_at": datetime.now(timezone.utc).isoformat(), "date_jst": "2026-10-25",
        "python": sys.version, "sqlite_version": sqlite3.sqlite_version,
        "checks": checks, "passed": 78,
        "actual_sqlite_interoperation_cases_with_mock_runtime": 3,
        "source_files": before, "local_import_graph_paths": len(before),
        "owned_source_files": {name: before[name] for name in ROOTS},
        "preserved_original_preparation_paths": original, "preserved_prior_receipts": prior,
        "evidence_files": evidence, "recorder_sha256": digest(Path(__file__)),
        "no_fork_or_preexec": True,
        "helpers": "Fresh Python -I -S -B; standalone stdlib branch precedes project imports",
        "private_diagnostics": "Per-command caps only: runtime stderr 1MiB, control stdout64KiB; create frame body not duplicated",
        "real_linux_runsc_executed": False, "generated_analysis_executed_on_host": False,
        "runtime_acceptance_verified": False, "C23_complete": False,
        "production_dispatch_built": False, "reservation_released": False,
        "review": "Independent source review by c23_runtime_design; no scientific/runtime approval",
        "attempt_history": [
            "Initial additional watchdog-handshake tests: 2failed/69passed because the control fixture still replaced the tested arm function with its fake",
            "Corrected only the test reference to call the saved real arm function with a mocked Popen; final71passed, then seven diagnostic cases added",
            "An early draft used os.fork/preexec; root review rejected that before actual Linux use. Replaced by fresh stdlib helpers, ready/deadline/parent/cancel fences; no actual generated/runtime execution occurred",
        ],
        "remaining_actual_gates": [
            "Exact pinned runsc CLI flags, FDexec, stdout lifetime, state PID/bundle and wait JSON on approved Linux",
            "Real outer/inner cgroup limits, controller death/deadline/queued-launch cancellation and populated0 proof",
            "Pinned wrapper guest quota/capability/readback, cleanup/output frames and UID ownership",
            "Containment probes and repeated numerical fixtures with current image/runtime",
            "Durable integration and verified release guard acceptance; this adapter never releases C22",
        ],
    }
    target = output / "verification.json"
    with target.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"receipt": str(target.relative_to(ROOT)), "sha256": digest(target),
                      "passed": 78, "source_graph_paths": len(before), "C23_complete": False}))


if __name__ == "__main__":
    main()

