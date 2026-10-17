"""C16 explicit discovery over actual registered sealed scientific snapshots."""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import replace
import json

import pytest

import config
from orchestration.catalogue_browser import CatalogueBrowser, MAX_CONFIGURED_SNAPSHOTS
from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.catalogue_service import CataloguePolicy, CatalogueService, CatalogueServiceError, FrozenCatalogueResolver
from schema.catalogue_browser import CatalogueSnapshotDescriptor, CatalogueSnapshotsResponse
from schema.catalogue_adapter_fixtures import adapter_scope
from schema.scientific_catalogue_fixtures import seal_scientific_fixture
from tests.catalogue_service_support import fixture_user, synthetic_service
from tests.test_frozen_scientific_catalogue import local


def payload(**updates):
    return {"scope": adapter_scope("ctd").model_dump(mode="json"), **updates}


def configured(tmp_path, *, count=3):
    store, first, _, _, registry, tables, child, _ = local(tmp_path)
    identities = [first] + [seal_scientific_fixture(store, registry, tables, publication=f"synthetic-publication-{index}") for index in range(1, count)]
    state = {"denied": set(), "datasets": set(), "revision": "policy-1", "discovery_revision": "discovery-1", "calls": []}
    registrations = {sid: register_scientific_snapshot(store=store, snapshot_id=sid, registration_id="synthetic:c16") for sid in identities}
    service = CatalogueService(resolver=FrozenCatalogueResolver(
        store=store, registrations=registrations,
        policy_resolver=lambda user, sid: CataloguePolicy(
            state["revision"], lambda snapshot, metadata: metadata.dataset_id not in state["datasets"], lambda snapshot, item: True,
        ),
    ))
    descriptors = [CatalogueSnapshotDescriptor(snapshot_id=sid, label={"en": f"Configured edition {index}", "ja": f"設定版{index}"}) for index, sid in enumerate(reversed(identities))]

    def permitted(user, descriptor):
        state["calls"].append((user.id, descriptor.snapshot_id))
        return descriptor.snapshot_id not in state["denied"]

    browser = CatalogueBrowser(service=service, snapshots=descriptors, permitted=permitted, revision=lambda user: state["discovery_revision"])
    return store, service, browser, descriptors, state, child


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", "true")


def test_newest_eligible_uses_explicit_order_with_full_snapshot_pagination(tmp_path):
    store, _, browser, descriptors, state, _ = configured(tmp_path)
    store.promote(descriptors[-1].snapshot_id, expected_generation=store.latest()[1])
    body = payload(limit=1)
    visited = []
    for page_index in range(3):
        response = browser.discover(body, fixture_user())
        parsed = CatalogueSnapshotsResponse.model_validate(response)
        assert parsed.version == "catalogue-browser-v1" and parsed.total == 3
        assert parsed.latest_snapshot_id == descriptors[0].snapshot_id
        assert [item.snapshot_id for item in parsed.snapshots] == [descriptors[page_index].snapshot_id]
        visited.extend(item.snapshot_id for item in parsed.snapshots)
        body = {**body, "cursor": response["next_cursor"]}
    assert visited == [item.snapshot_id for item in descriptors]
    assert body["cursor"] is None and len(state["calls"]) == 9


def test_denied_labels_counts_and_corrupt_bytes_are_not_probed(tmp_path, monkeypatch):
    _, service, browser, descriptors, state, _ = configured(tmp_path)
    denied = descriptors[0].snapshot_id
    state["denied"].add(denied)
    original = service.overview
    calls = []

    def overview(body, user):
        calls.append(body["snapshot_id"])
        if body["snapshot_id"] == denied:
            raise OSError("Private denied metadata must never be examined")
        return original(body, user)

    monkeypatch.setattr(service, "overview", overview)
    response = browser.discover(payload(), fixture_user())
    assert response["total"] == 2 and response["latest_snapshot_id"] == descriptors[1].snapshot_id
    assert denied not in calls and denied not in str(response)
    assert descriptors[0].label.en not in str(response)


def test_empty_and_zero_match_scopes_keep_allowed_snapshots_visible(tmp_path):
    _, _, browser, descriptors, state, _ = configured(tmp_path)
    no_matches = adapter_scope("ctd").model_dump(mode="json")
    no_matches["sources"]["ctd"]["filters"]["station"] = "no-such-station"
    assert browser.discover(payload(scope=no_matches), fixture_user())["total"] == 3
    state["datasets"].add("synthetic:ctd:campaign-a")
    state["revision"] = "policy-2"
    assert browser.discover(payload(), fixture_user())["latest_snapshot_id"] == descriptors[0].snapshot_id
    state["denied"].update(item.snapshot_id for item in descriptors)
    empty = browser.discover(payload(), fixture_user())
    assert empty["snapshots"] == [] and empty["latest_snapshot_id"] is None
    assert empty["total"] == 0 and empty["next_cursor"] is None


@pytest.mark.parametrize("target", ["index", "child"])
def test_current_withdrawal_skips_affected_snapshots_without_labels(tmp_path, target):
    store, _, browser, descriptors, _, child = configured(tmp_path)
    store.revoke(descriptors[0].snapshot_id if target == "index" else child)
    response = browser.discover(payload(), fixture_user())
    assert response["total"] == (2 if target == "index" else 0)
    assert descriptors[0].snapshot_id not in str(response)


def test_missing_registration_is_not_exposed(tmp_path):
    _, service, browser, descriptors, _, _ = configured(tmp_path)
    del service.resolver.registrations[descriptors[0].snapshot_id]
    assert browser.discover(payload(), fixture_user())["total"] == 2


def test_allowed_tail_snapshot_integrity_is_checked_before_any_page_returns(tmp_path):
    store, _, browser, descriptors, _, _ = configured(tmp_path)
    manifest, _ = store.read(descriptors[-1].snapshot_id)
    obj = manifest.objects[0]
    (tmp_path / "v1/catalogue/objects" / obj.sha256).write_bytes(b"synthetic corruption")
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover(payload(limit=1), fixture_user())
    assert failure.value.code == "catalogue_unavailable" and failure.value.status_code == 503


def test_current_callback_failure_is_sanitized_without_previous_results(tmp_path):
    _, service, browser, descriptors, _, _ = configured(tmp_path)
    assert browser.discover(payload(), fixture_user())["total"] == 3

    def failed(user, descriptor):
        raise OSError("/private/path?password=secret")

    unavailable = CatalogueBrowser(service=service, snapshots=descriptors, permitted=failed, revision="current")
    with pytest.raises(CatalogueServiceError) as failure:
        unavailable.discover(payload(), fixture_user())
    assert failure.value.message == "Catalogue is unavailable" and "secret" not in str(failure.value)


@pytest.mark.parametrize("change", ["user", "scope", "limit", "visibility", "predicate_revision", "policy_revision", "lifecycle", "tamper"])
def test_snapshot_cursors_bind_current_complete_context(tmp_path, change):
    store, _, browser, descriptors, state, _ = configured(tmp_path)
    user = fixture_user()
    first = browser.discover(payload(limit=1), user)
    body = payload(limit=1, cursor=first["next_cursor"])
    if change == "user":
        user = fixture_user("other")
    elif change == "scope":
        body["scope"] = adapter_scope("metagenome").model_dump(mode="json")
    elif change == "limit":
        body["limit"] = 2
    elif change == "visibility":
        state["denied"].add(descriptors[-1].snapshot_id)
    elif change == "predicate_revision":
        state["discovery_revision"] = "discovery-2"
    elif change == "policy_revision":
        state["revision"] = "policy-2"
    elif change == "lifecycle":
        store.set_hold(descriptors[0].snapshot_id, True)
    else:
        decoded = json.loads(base64.urlsafe_b64decode(body["cursor"] + "=" * (-len(body["cursor"]) % 4)))
        decoded["offset"] = 2
        body["cursor"] = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode().rstrip("=")
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover(body, user)
    assert failure.value.code == "invalid_cursor" and failure.value.status_code == 409


@pytest.mark.parametrize("value", [True, 0, 501, "100"])
def test_limit_is_strict_bounded_without_policy_access(tmp_path, value):
    _, _, browser, _, state, _ = configured(tmp_path)
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover(payload(limit=value), fixture_user())
    assert failure.value.code == "invalid_request" and state["calls"] == []


@pytest.mark.parametrize("field", ["role", "access_binding", "access_revision", "revision", "snapshot_id", "permitted", "sql"])
def test_public_request_rejects_authority_registry_and_database_smuggling(tmp_path, field):
    _, _, browser, _, state, _ = configured(tmp_path)
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover(payload(**{field: "forged"}), fixture_user())
    assert failure.value.code == "invalid_request" and state["calls"] == []


@pytest.mark.parametrize("identity,expected", [(None, "authentication_required"), (fixture_user(role="viewer"), "access_denied"), (replace(fixture_user(), status="suspended"), "access_denied")])
def test_authorization_precedes_malformed_body_and_callbacks(tmp_path, identity, expected):
    _, _, browser, _, state, _ = configured(tmp_path)
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover(payload(role="admin"), identity)
    assert failure.value.code == expected and state["calls"] == []


@pytest.mark.parametrize("flag", ["ENABLE_V1_CATALOGUE", "ENABLE_V1_CATALOGUE_BROWSER"])
@pytest.mark.parametrize("value", ["false", "nonsense"])
def test_both_feature_flags_fail_closed_before_discovery(tmp_path, monkeypatch, flag, value):
    _, _, browser, _, state, _ = configured(tmp_path)
    monkeypatch.setenv(flag, value)
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover(payload(), fixture_user())
    assert failure.value.status_code == 503 and state["calls"] == []


def test_browser_feature_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_V1_CATALOGUE_BROWSER", raising=False)
    monkeypatch.setattr(config, "ENABLE_V1_CATALOGUE_BROWSER", "false")
    assert config.v1_catalogue_browser_enabled() is False


def test_registry_and_callback_mutations_do_not_replace_configured_labels(tmp_path):
    _, service, _, descriptors, _, _ = configured(tmp_path)
    original = deepcopy(descriptors)

    def policy(user, descriptor):
        descriptor.label.en = "Untrusted mutation"
        return True

    browser = CatalogueBrowser(service=service, snapshots=descriptors, permitted=policy, revision="policy-1")
    descriptors[0].label.en = "Caller mutation"
    assert browser.discover(payload(), fixture_user())["snapshots"] == [item.model_dump(mode="json") for item in original]


@pytest.mark.parametrize("answer", [1, "true", None, [], {}])
def test_discovery_requires_literal_true(tmp_path, answer):
    _, service, _, descriptors, _, _ = configured(tmp_path)
    browser = CatalogueBrowser(service=service, snapshots=descriptors, permitted=lambda user, descriptor: answer, revision="p1")
    assert browser.discover(payload(), fixture_user())["total"] == 0


def test_explicit_registry_configuration_is_bounded_and_no_silent_discovery():
    _, _, service = synthetic_service(2)
    descriptor = CatalogueSnapshotDescriptor(snapshot_id="a" * 64, label={"en": "A", "ja": "A"})
    base = {"service": service, "permitted": lambda user, item: True, "revision": "one"}
    assert CatalogueBrowser(**base, snapshots=[]).discover(payload(), fixture_user())["total"] == 0
    for values in ([descriptor, descriptor], [descriptor] * (MAX_CONFIGURED_SNAPSHOTS + 1)):
        with pytest.raises(ValueError):
            CatalogueBrowser(**base, snapshots=values)
    with pytest.raises(ValueError):
        CatalogueBrowser(**{**base, "service": None}, snapshots=[])
    with pytest.raises(ValueError):
        CatalogueBrowser(**base, snapshots=[], cursor_key=b"short")
