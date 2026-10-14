from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

import config
from db.retention import RetentionCleanupReport
from scripts import retention_cleanup


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


@pytest.mark.parametrize("confirmation", [None, "", "delete expired chat data", "DELETE EXPIRED CHAT"])
def test_execute_requires_exact_confirmation_before_database_access(monkeypatch, confirmation):
    def unexpected_cleanup(**kwargs):
        raise AssertionError("An unconfirmed command must not reach cleanup or the database.")

    monkeypatch.setattr(retention_cleanup, "cleanup_chat_interactions", unexpected_cleanup)
    argv = ["retention_cleanup.py", "--execute"]
    if confirmation is not None:
        argv.extend(["--confirm", confirmation])
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as error:
        retention_cleanup.main()
    assert error.value.code == 2


@pytest.mark.parametrize(
    ("arguments", "expected_days", "dry_run"),
    [
        ([], config.CHAT_RETENTION_DAYS, True),
        (["--days", "30", "--confirm", retention_cleanup.CONFIRMATION], 30, True),
        (["--days", "90", "--execute", "--confirm", retention_cleanup.CONFIRMATION], 90, False),
    ],
    ids=["default-is-observation", "confirmation-alone-is-observation", "explicit-execution"],
)
def test_cleanup_cli_reports_actual_result_and_preserves_modes(
    monkeypatch, capsys, arguments, expected_days, dry_run
):
    calls = []
    cutoff = datetime(2026, 7, 16, tzinfo=timezone.utc)

    def synthetic_cleanup(**kwargs):
        calls.append(kwargs)
        return RetentionCleanupReport(
            cutoff=cutoff,
            retention_days=kwargs["retention_days"],
            eligible_count=2,
            deleted_count=0 if kwargs["dry_run"] else 1,
            dry_run=kwargs["dry_run"],
        )

    monkeypatch.setattr(retention_cleanup, "cleanup_chat_interactions", synthetic_cleanup)
    monkeypatch.setattr(sys, "argv", ["retention_cleanup.py", *arguments])
    assert retention_cleanup.main() == 0
    assert calls == [{"retention_days": expected_days, "dry_run": dry_run}]
    assert json.loads(capsys.readouterr().out) == {
        "cutoff": cutoff.isoformat(),
        "retention_days": expected_days,
        "eligible_count": 2,
        "deleted_count": 0 if dry_run else 1,
        "dry_run": dry_run,
    }
