"""Offline safety checks for the disposable C03 PostgreSQL identity boundary."""
import pytest

from tests.integration.test_retention_concurrency_postgres import allowed_disposable_server_address


@pytest.mark.parametrize(
    ("observed", "expected", "github_actions", "allowed"),
    [
        ("127.0.0.1", None, None, True),
        ("::1", None, None, True),
        ("127.0.0.1", "172.18.0.2", "true", True),
        ("172.18.0.2", None, "true", False),
        ("172.18.0.2", "172.18.0.2", None, False),
        ("172.18.0.2", "172.18.0.2", "false", False),
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
        (None, None, "true", False),
        ("invalid", "invalid", "true", False),
    ],
)
def test_c03_server_address_requires_loopback_or_exact_ci_owned_private_peer(
    monkeypatch, observed, expected, github_actions, allowed,
):
    for name, value in (
        ("C03_TEST_SERVER_ADDRESS", expected), ("GITHUB_ACTIONS", github_actions),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert allowed_disposable_server_address(observed) is allowed
