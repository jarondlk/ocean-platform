from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_retention_cleanup_supports_documented_script_invocation():
    result = subprocess.run(
        [sys.executable, "scripts/retention_cleanup.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--execute" in result.stdout
    assert "--confirm" in result.stdout
