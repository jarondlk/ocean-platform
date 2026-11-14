"""No credentials/network: exercise the actual writer's refusal and apply order."""

from copy import deepcopy
import json

import pytest

from scripts import beta_b1_apply as writer
from scripts import beta_b1_rollout as rollout
from tests.test_beta_b1_rollout import make_material, completed


@pytest.fixture
def material():
    return make_material()


class FakeCloud:
    def __init__(self, before, after=None):
        self.before, self.after = before, after
        self.requests = []
        self.patched = False

    def request(self, url, **kwargs):
        self.requests.append((url, deepcopy(kwargs)))
        if kwargs.get("method") == "PATCH":
            self.patched = "validateOnly=true" not in url
            return {"name": "fixed-operation"}
        return deepcopy(self.after if self.patched else self.before)


def setup(monkeypatch, tmp_path, material):
    _, before, contract = material
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    monkeypatch.setattr(rollout, "CONTRACT_PATH", path)
    monkeypatch.setattr(rollout, "verify_candidate", lambda directory: {"image": rollout.NEW})
    return before, contract


def test_validation_only_never_changes_live_state(monkeypatch, tmp_path, material):
    before, _ = setup(monkeypatch, tmp_path, material)
    cloud = FakeCloud(before)
    result = writer.execute(cloud, tmp_path, "controller", validate_only=True)
    assert result["service_exactly_unchanged"]
    patches = [(u, k) for u, k in cloud.requests if k.get("method") == "PATCH"]
    assert len(patches) == 1 and "validateOnly=true" in patches[0][0]
    assert patches[0][1]["personal"] is True


def test_failed_entry_stops_before_patch_and_preserves_attempt(monkeypatch, tmp_path, material):
    before, _ = setup(monkeypatch, tmp_path, material)
    def reject(*args):
        raise writer.observer.Rejected("No fresh quiescence")
    monkeypatch.setattr(writer, "fresh_entry", reject)
    cloud = FakeCloud(before)
    with pytest.raises(writer.observer.Rejected):
        writer.execute(cloud, tmp_path, "controller", validate_only=False, execution_name="new", not_before="now")
    assert not any(k.get("method") == "PATCH" for _, k in cloud.requests)
    assert (tmp_path / "controller-apply/plan.json").is_file()


def test_changed_etag_stops_before_patch(monkeypatch, tmp_path, material):
    before, _ = setup(monkeypatch, tmp_path, material)
    class Changed(FakeCloud):
        def request(self, url, **kwargs):
            value = super().request(url, **kwargs)
            if len(self.requests) > 1:
                value["etag"] = "concurrent-update"
            return value
    cloud = Changed(before)
    with pytest.raises(writer.observer.Rejected):
        writer.execute(cloud, tmp_path, "controller", validate_only=True)
    assert not any(k.get("method") == "PATCH" for _, k in cloud.requests)


def test_one_patch_then_exact_verified_readback(monkeypatch, tmp_path, material):
    before, contract = setup(monkeypatch, tmp_path, material)
    after = completed(before, rollout.plan_transition(before, "controller", contract))
    monkeypatch.setattr(writer, "fresh_entry", lambda *args: {"current": True})
    cloud = FakeCloud(before, after)
    result = writer.execute(cloud, tmp_path, "controller", validate_only=False, execution_name="new", not_before="now")
    assert result["all_other_configuration_preserved"]
    assert sum(k.get("method") == "PATCH" for _, k in cloud.requests) == 1
    assert (tmp_path / "controller-apply/operation.json").is_file()


def test_bad_readback_is_retained_without_automatic_rollback(monkeypatch, tmp_path, material):
    before, contract = setup(monkeypatch, tmp_path, material)
    after = completed(before, rollout.plan_transition(before, "controller", contract))
    after["template"]["serviceAccount"] = "wrong@example.com"
    monkeypatch.setattr(writer, "fresh_entry", lambda *args: {"current": True})
    cloud = FakeCloud(before, after)
    with pytest.raises(writer.observer.Rejected):
        writer.execute(cloud, tmp_path, "controller", validate_only=False, execution_name="new", not_before="now")
    assert sum(k.get("method") == "PATCH" for _, k in cloud.requests) == 1
    assert (tmp_path / "controller-apply/after.json").is_file()


@pytest.mark.parametrize("url", ["https://attacker.example/", "http://run.googleapis.com/", "https://run.googleapis.com.attacker.example/", "https://run.googleapis.com:444/", "https://user@run.googleapis.com/"])
def test_tokens_cannot_be_sent_to_unreviewed_destinations(url):
    cloud = writer.Cloud.__new__(writer.Cloud)
    with pytest.raises(writer.observer.Rejected):
        cloud.request(url)


def test_redirects_are_not_followed():
    assert writer.NoRedirect().redirect_request(None, None, 302, "moved", {}, "https://attacker.example/") is None


def log_material(pages):
    class Logs:
        def __init__(self):
            self.requests = []

        def request(self, url, **kwargs):
            self.requests.append(deepcopy(kwargs["body"]))
            return pages[len(self.requests) - 1]
    execution = {"metadata": {"creationTimestamp": "2026-11-14T08:21:32Z"},
                 "status": {"completionTime": "2026-11-14T08:21:50Z"}}
    return Logs(), execution


def test_log_reader_follows_empty_continuation_and_keeps_exact_filter():
    report = {"version": "ocean-beta-runtime-rollout-preflight-v1"}
    cloud, execution = log_material([
        {"nextPageToken": "first"},
        {"entries": [{"jsonPayload": report}], "nextPageToken": "second"}, {}])
    assert writer.observer_report(cloud, "exact-execution", execution) == report
    assert [q.get("pageToken") for q in cloud.requests] == [None, "first", "second"]
    assert len({q["filter"] for q in cloud.requests}) == 1
    assert 'resource.labels.location="asia-northeast1"' in cloud.requests[0]["filter"]
    assert 'execution_name"="exact-execution"' in cloud.requests[0]["filter"]
    assert 'timestamp>="2026-11-14T08:21:32+00:00"' in cloud.requests[0]["filter"]


@pytest.mark.parametrize("pages", [
    [{"nextPageToken": "repeated"}, {"nextPageToken": "repeated"}],
    [{"nextPageToken": str(i)} for i in range(10)],
    [{}],
    [{"entries": [{"jsonPayload": {"version": "ocean-beta-runtime-rollout-preflight-v1"}}]},
     {"entries": []}],
])
def test_log_reader_rejects_missing_incomplete_or_looping_pages(pages):
    if len(pages) == 2 and "entries" in pages[0]:
        pages = [{"entries": pages[0]["entries"] * 2}]
    cloud, execution = log_material(pages)
    with pytest.raises(writer.observer.Rejected):
        writer.observer_report(cloud, "exact-execution", execution)
