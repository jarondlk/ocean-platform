"""Offline checks for the dedicated, observed C20 PostgreSQL target boundary."""

import pytest

from tests.research_run_postgres_support import (
    allowed_disposable_server_address,
    configured_disposable_url,
)


@pytest.mark.parametrize("observed,pinned,github_actions,allowed", [
    ("127.0.0.1", None, None, True), ("::1", None, None, True),
    ("127.0.0.1", "172.18.0.2", "true", True),
    ("172.18.0.2", None, "true", False),
    ("172.18.0.2", "172.18.0.2", None, False),
    ("172.18.0.2", "172.18.0.2", "false", False),
    ("172.18.0.2", "172.18.0.2", "TRUE", False),
    ("172.18.0.2", "172.18.0.2", "1", False),
    ("172.18.0.2", "172.18.0.3", "true", False),
    ("172.18.0.2", "invalid", "true", False),
    ("172.18.0.2", "172.18.0.2", "true", True),
    ("10.1.0.2", "10.1.0.2", "true", True),
    ("192.168.1.2", "192.168.1.2", "true", True),
    ("8.8.8.8", "8.8.8.8", "true", False),
    ("169.254.1.5", "169.254.1.5", "true", False),
    ("0.0.0.0", "0.0.0.0", "true", False),
    ("224.0.0.1", "224.0.0.1", "true", False),
    ("fc00::2", "fc00::2", "true", False),
    (None, None, "true", False), ("invalid", "invalid", "true", False),
])
def test_c20_observed_server_requires_loopback_or_exact_owned_ci_private_peer(monkeypatch, observed, pinned, github_actions, allowed):
    for key, value in (("C20_TEST_SERVER_ADDRESS", pinned), ("GITHUB_ACTIONS", github_actions)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    assert allowed_disposable_server_address(observed) is allowed


@pytest.mark.parametrize("raw", [
    "postgresql://fixture:fixture@127.0.0.1:5432/ocean_c20_local",
    "postgresql://fixture:fixture@localhost:5432/ocean_c20_fixture_001",
    "postgresql+psycopg2://fixture:fixture@[::1]:5432/ocean_c20_ipv6",
])
def test_c20_url_accepts_only_dedicated_loopback_database(monkeypatch, raw):
    monkeypatch.setenv("C20_TEST_DATABASE_URL", raw)
    url = configured_disposable_url()
    assert url.database.startswith("ocean_c20_")
    assert not url.query


@pytest.mark.parametrize("raw", [
    "sqlite:///ocean_c20_fixture", "not-a-url",
    "postgresql://fixture:fixture@8.8.8.8:5432/ocean_c20_fixture",
    "postgresql://fixture:fixture@172.18.0.2:5432/ocean_c20_fixture",
    "postgresql://fixture:fixture@database.invalid:5432/ocean_c20_fixture",
    "postgresql://fixture:fixture@127.0.0.1:5432/ocean_platform",
    "postgresql://fixture:fixture@127.0.0.1:5432/ocean_c09_fixture",
    "postgresql://fixture:fixture@127.0.0.1:5432/ocean_c20_",
    "postgresql://fixture:fixture@127.0.0.1:5432/ocean_c20_fixture?host=database.invalid",
    "postgresql://fixture:fixture@127.0.0.1:5432/ocean_c20_fixture?options=-csearch_path%3Dpublic",
    "postgresql:///ocean_c20_fixture",
])
def test_c20_url_rejects_other_targets_and_query_overrides_before_connection(monkeypatch, raw):
    monkeypatch.setenv("C20_TEST_DATABASE_URL", raw)
    with pytest.raises(ValueError):
        configured_disposable_url()


def test_c20_never_falls_back_to_ambient_application_database(monkeypatch):
    monkeypatch.delenv("C20_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fixture:fixture@127.0.0.1:5432/ocean_c20_ambient")
    with pytest.raises(ValueError, match="DATABASE_URL is never used"):
        configured_disposable_url()
