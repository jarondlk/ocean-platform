from __future__ import annotations

import argparse
import os
from pathlib import Path

import pytest

from scripts import phase7_release_probe as probe


def _args(**overrides):
    values = {
        "base_url": "https://example.run.app",
        "mode": "load",
        "execute": False,
        "confirm_host": None,
        "cookie_file": None,
        "concurrency": 2,
        "duration_seconds": 180,
        "read_requests": 60,
        "chat_calls": 9,
        "output": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_production_execution_requires_exact_host_confirmation():
    with pytest.raises(probe.ProbeSafetyError, match="confirm-host"):
        probe.validate_config(_args(execute=True, confirm_host="wrong.run.app"))

    config = probe.validate_config(
        _args(execute=True, confirm_host="example.run.app")
    )

    assert config.host == "example.run.app"
    assert config.execute is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("concurrency", 6, "concurrency"),
        ("duration_seconds", 301, "duration"),
        ("read_requests", 301, "read requests"),
        ("chat_calls", 19, "chat calls"),
    ],
)
def test_hard_safety_caps_cannot_be_overridden(field, value, message):
    with pytest.raises(probe.ProbeSafetyError, match=message):
        probe.validate_config(_args(**{field: value}))


def test_chat_schedule_stays_below_application_rate_limit():
    with pytest.raises(probe.ProbeSafetyError, match="nine-per-minute"):
        probe.validate_config(_args(duration_seconds=60, chat_calls=10))


def test_non_local_probe_requires_https():
    with pytest.raises(probe.ProbeSafetyError, match="HTTPS"):
        probe.validate_config(_args(base_url="http://example.run.app"))


def test_cookie_file_must_be_private_and_outside_repository(tmp_path):
    cookie = tmp_path / "cookie.txt"
    cookie.write_text("authjs.session-token=test", encoding="utf-8")
    if os.name == "posix":
        cookie.chmod(0o644)
        with pytest.raises(probe.ProbeSafetyError, match="0600"):
            probe.read_private_cookie(cookie)
        cookie.chmod(0o600)

    assert probe.read_private_cookie(cookie) == "authjs.session-token=test"


def test_cookie_value_is_never_in_sanitized_summary():
    config = probe.validate_config(_args())
    report = probe.summarize(
        config,
        [
            probe.RequestResult(
                kind="read",
                endpoint="/api/backend/health",
                status_code=200,
                latency_ms=12,
                ok=True,
            )
        ],
    )

    assert "cookie" not in str(report).lower()
    assert report["summary"]["failed"] == 0
    assert report["summary"]["read_latency_ms"]["p95"] == 12


def test_repository_cookie_file_is_rejected(tmp_path, monkeypatch):
    project_root = tmp_path / "repo"
    project_root.mkdir()
    cookie = project_root / "cookie.txt"
    cookie.write_text("token=value", encoding="utf-8")
    cookie.chmod(0o600)
    monkeypatch.setattr(probe, "PROJECT_ROOT", Path(project_root))

    with pytest.raises(probe.ProbeSafetyError, match="outside the repository"):
        probe.read_private_cookie(cookie)
