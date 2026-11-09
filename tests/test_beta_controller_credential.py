"""Credential transport boundary tests use synthetic values and no credentials."""
import base64
import importlib.util
from pathlib import Path

import google_crc32c
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("credential_boundary", ROOT / "deploy/gcp/beta/research-operator/controller_credential.py")
CREDENTIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CREDENTIAL)


class Session:
    def __init__(self, response):
        self.response, self.calls = response, []
    def request(self, method, url, **kwargs):
        from types import SimpleNamespace
        self.calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: self.response)


@pytest.mark.parametrize("prefix", CREDENTIAL.SECRET_ALIASES)
def test_add_and_recovery_accept_only_exact_project_secret_and_crc(prefix):
    raw = b"synthetic-test-value-not-a-live-credential"
    session = Session({"name": prefix + "/versions/1"})
    store = CREDENTIAL.ControllerSecret(session)
    assert store.add(raw.decode()) == "1"
    method, url, kwargs = session.calls[-1]
    assert method == "POST" and url.endswith(CREDENTIAL.SECRET + ":addVersion")
    assert kwargs["json"]["payload"]["dataCrc32c"] == str(google_crc32c.value(raw))
    assert kwargs["allow_redirects"] is False and kwargs["timeout"] == 15
    session.response = {"name": prefix + "/versions/1", "payload": {
        "data": base64.b64encode(raw).decode(), "dataCrc32c": str(google_crc32c.value(raw))}}
    assert store.access("1") == raw.decode()
    session.response["payload"]["dataCrc32c"] = "0"
    with pytest.raises(ValueError, match="integrity"):
        store.access("1")


@pytest.mark.parametrize("name", ["projects/other/secrets/ocean-v1-beta-controller-database/versions/1",
    "projects/534831104543/secrets/different/versions/1", CREDENTIAL.SECRET + "/versions/latest"])
def test_secret_creation_never_accepts_ambiguous_or_foreign_version(name):
    with pytest.raises(ValueError, match="uncertain"):
        CREDENTIAL.ControllerSecret(Session({"name": name})).add("synthetic-test-only")


def test_initializer_never_treats_a_paginated_inventory_as_an_empty_secret():
    assert CREDENTIAL.ControllerSecret(Session({})).empty()
    assert not CREDENTIAL.ControllerSecret(Session({"nextPageToken": "more"})).empty()
    assert not CREDENTIAL.ControllerSecret(Session({"versions": [{"state": "DESTROYED"}]})).empty()


@pytest.mark.parametrize("dsn", ["postgresql+psycopg2://postgres:synthetic@127.0.0.1:5432/ocean_v1_beta",
    "postgresql+psycopg2://ocean_v1_research_controller:" + "x" * 64 + "@legacy.invalid:5432/ocean_v1_beta",
    "postgresql+psycopg2://ocean_v1_research_controller:" + "x" * 64 + "@127.0.0.1:5432/ocean_v1_beta?options=unsafe"])
def test_reconciliation_cannot_redirect_sql_or_change_database_identity(dsn):
    with pytest.raises(ValueError):
        CREDENTIAL.credential_url(dsn)
