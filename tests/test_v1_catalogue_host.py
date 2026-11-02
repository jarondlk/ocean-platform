"""Configured empty authority is distinct from missing/changed catalogue input."""
from dataclasses import replace
import json
import os

import pytest

from api.v1_catalogue_host import (
    CatalogueHostConfigurationError, PROJECT, VERSION, load_empty_catalogue,
)
from orchestration.catalogue_service import CatalogueServiceError
from schema.catalogue_adapter_fixtures import adapter_scope
from tests.catalogue_service_support import fixture_user

KEY = b"independent-catalogue-cursor-test-key" * 2


def document(**changes):
    return {"version": VERSION, "project_id": PROJECT, "site_id": "v1:" + PROJECT,
        "revision": "beta-empty-registry-v1", "snapshots": [], **changes}


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", "true")


def file(tmp_path, value=None):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(document() if value is None else value))
    path.chmod(0o444)
    return path


def load(path, **changes):
    return load_empty_catalogue(path, project_id=PROJECT, site_id="v1:" + PROJECT,
        cursor_key=KEY, _allow_test_owner=True, **changes)


def request(**changes):
    return {"scope": adapter_scope("ctd").model_dump(mode="json"), **changes}


def test_explicit_empty_registry_produces_real_zero_snapshot_discovery(tmp_path):
    service, browser = load(file(tmp_path))
    result = browser.discover(request(), fixture_user())
    assert browser.service is service
    assert result["version"] == "catalogue-browser-v1"
    assert result["snapshots"] == [] and result["total"] == 0
    assert result["latest_snapshot_id"] is result["next_cursor"] is None
    assert result["access_revision"].startswith("c16:")


def test_invented_snapshot_is_not_found_not_a_scientific_zero_result(tmp_path):
    service, _ = load(file(tmp_path))
    with pytest.raises(CatalogueServiceError) as failure:
        service.overview({"snapshot_id": "a" * 64, **request()}, fixture_user())
    assert failure.value.code == "not_found" and failure.value.status_code == 404


@pytest.mark.parametrize("change", ["removed", "mutated", "same_bytes_replaced", "writable"])
def test_changed_authority_never_falls_back_to_empty(tmp_path, change):
    path = file(tmp_path)
    service, browser = load(path)
    if change == "removed":
        path.unlink()
    elif change == "mutated":
        path.chmod(0o644)
        path.write_text(json.dumps(document(revision="withdrawn")))
        path.chmod(0o444)
    elif change == "same_bytes_replaced":
        replacement = tmp_path / "replacement.json"
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o444)
        replacement.replace(path)
    else:
        path.chmod(0o644)
    for action in [lambda: browser.discover(request(), fixture_user()),
            lambda: service.overview({"snapshot_id": "a" * 64, **request()}, fixture_user())]:
        with pytest.raises(CatalogueServiceError) as failure:
            action()
        assert failure.value.code == "catalogue_unavailable" and failure.value.status_code == 503


@pytest.mark.parametrize("value", [
    document(snapshots=[{"snapshot_id": "a" * 64}]),
    document(snapshots=None), document(snapshots={}),
    document(version="unknown"), document(project_id="data-infra-infobio"),
    document(site_id="v1:data-infra-infobio"), document(revision=""),
    document(revision=1), document(extra="unreviewed"), [], None,
])
def test_nonempty_or_unreviewed_authority_configuration_is_rejected(tmp_path, value):
    path = tmp_path / "unreviewed.json"
    path.write_text(json.dumps(value))
    path.chmod(0o444)
    with pytest.raises(CatalogueHostConfigurationError, match="immutable beta catalogue"):
        load(path)


@pytest.mark.parametrize("raw", [
    '{"version":"wrong","version":"ocean-v1-empty-catalogue-v1"}',
    "not-json", "{\"revision\":NaN}", " " * 4097, "",
])
def test_invalid_duplicate_or_unbounded_json_rejected(tmp_path, raw):
    path = tmp_path / "invalid.json"
    path.write_text(raw)
    path.chmod(0o444)
    with pytest.raises(CatalogueHostConfigurationError):
        load(path)


@pytest.mark.parametrize("mode", [0o400, 0o644, 0o666])
def test_configuration_requires_reviewed_readonly_mode(tmp_path, mode):
    path = file(tmp_path)
    path.chmod(mode)
    with pytest.raises(CatalogueHostConfigurationError):
        load(path)


def test_symlink_final_and_parent_paths_rejected(tmp_path):
    path = file(tmp_path)
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(CatalogueHostConfigurationError):
        load(alias)
    directory = tmp_path / "alias-directory"
    directory.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(CatalogueHostConfigurationError):
        load(directory / path.name)


def test_hardlink_and_fifo_are_rejected_without_blocking(tmp_path):
    path = file(tmp_path)
    os.link(path, tmp_path / "hardlink.json")
    with pytest.raises(CatalogueHostConfigurationError):
        load(path)
    fifo = tmp_path / "fifo.json"
    os.mkfifo(fifo, 0o444)
    with pytest.raises(CatalogueHostConfigurationError):
        load(fifo)


def test_missing_relative_or_parent_navigation_paths_rejected(tmp_path):
    for path in [tmp_path / "missing.json", "relative.json", tmp_path / ".." / "catalogue.json"]:
        with pytest.raises(CatalogueHostConfigurationError):
            load(path)


def test_nonroot_fixture_exception_cannot_enter_production(tmp_path, monkeypatch):
    path = file(tmp_path)
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    with pytest.raises(CatalogueHostConfigurationError):
        load(path)
    # Production also refuses a writable temporary ancestry, even on root CI.
    with pytest.raises(CatalogueHostConfigurationError):
        load_empty_catalogue(path, project_id=PROJECT, site_id="v1:" + PROJECT, cursor_key=KEY)


def test_unauthorized_user_does_not_probe_missing_authority(tmp_path):
    path = file(tmp_path)
    _, browser = load(path)
    path.unlink()
    for user in [None, replace(fixture_user(), status="suspended"),
            replace(fixture_user(), permissions=frozenset())]:
        with pytest.raises(CatalogueServiceError) as failure:
            browser.discover(request(), user)
        assert failure.value.status_code in {401, 403}


def test_current_user_binding_and_cursor_guards_are_retained(tmp_path):
    _, browser = load(file(tmp_path))
    first = browser.discover(request(), fixture_user())
    other = browser.discover(request(), fixture_user(2))
    assert first["access_revision"] != other["access_revision"]
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover(request(cursor="invented-cursor"), fixture_user())
    assert failure.value.code == "invalid_cursor"


def test_disabled_flag_cannot_be_overridden_by_catalogue_file(tmp_path, monkeypatch):
    _, browser = load(file(tmp_path))
    monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", "false")
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover(request(), fixture_user())
    assert failure.value.code == "catalogue_disabled"
