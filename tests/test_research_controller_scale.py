"""C19 controller with actual C14 and an explicit100k synthetic backend.

This source has a host-frozen test submission loader, not a100k C17/C13 capacity
claim. The separate actual-service suite uses real C17 and sealed C09-C13 data.
"""

from copy import deepcopy
import hashlib
import json
import uuid

import pytest

from orchestration.research_controller import ResearchController
from schema.context_catalogue_fixtures import fixture_scope, make_catalogue
from schema.research_controller import canonical_hash
from tests.catalogue_service_support import dataset_id, fixture_user, synthetic_service
from tests.test_research_controller import FakeRuntime, tool


class ExplicitSubmissionLoader:
    def __init__(self, catalogue, source, user):
        self.catalogue = source
        self.user = user
        self.calls = 0
        self.request = {
            "investigation_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "revision_id": str(uuid.uuid4()),
        }
        context = {
            "snapshot_id": catalogue.snapshot_id,
            "scope": fixture_scope().canonical(),
            "attachments": [],
            "pins": [],
            "artifact_bindings": {},
        }
        self.frozen = {
            **self.request,
            "snapshot_id": catalogue.snapshot_id,
            "payload_sha256": canonical_hash(context),
            "context": context,
        }

    def load_for_submission(self, *, user, **request):
        assert request == self.request and user == self.user
        self.calls += 1
        return deepcopy(self.frozen)


@pytest.fixture(scope="module")
def scale():
    identity = hashlib.sha256(b"explicit C19 synthetic100k").hexdigest()
    catalogue, resolver, service = synthetic_service(
        catalogue=make_catalogue(100_000, snapshot_id=identity)
    )
    user = fixture_user()
    loader = ExplicitSubmissionLoader(catalogue, service, user)
    return catalogue, resolver, service, user, loader


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_V1_RESEARCH_CONTROLLER", "true")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")


def controller(scale, runtime=None, **kwargs):
    _, _, service, user, loader = scale
    return ResearchController(
        investigations=loader,
        catalogue=service,
        identity_provider=lambda: user,
        runtime=runtime,
        model="c19-fake" if runtime else None,
        **kwargs,
    )


@pytest.mark.parametrize("preview", [1, 25, 100, 500])
def test_full100000_count_is_not_preview_or_summary_row_count(scale, preview):
    result = controller(scale, limits={"observation_preview_rows": preview}).execute(
        {**scale[-1].request, "question": "Count all datasets"}
    )
    assert result.outcome == "completed"
    assert result.budget.tool_actions == 1 and result.budget.model_calls == 0
    assert result.observations[0].counts[0].value == 100_000
    assert result.observations[0].input_count == 100_000
    assert result.observations[0].page_total_rows == 1
    assert json.loads(result.completion.facts[0].value_json)["value"] == 100_000


@pytest.mark.parametrize("index", [25, 501, 99_999])
def test_controller_reaches_legacy_rank26_and_late_exact_ids(scale, index):
    identity = dataset_id(index)
    runtime = FakeRuntime(
        [
            tool(
                "catalogue.list",
                filters={"kinds": ["dataset"], "search": identity},
                limit=1,
            )
        ]
    )
    result = controller(scale, runtime).execute(
        {**scale[-1].request, "question": f'Find object "{identity}"'}
    )
    assert result.outcome == "completed"
    assert result.budget.tool_actions == 2 and result.budget.model_calls == 1
    assert json.loads(result.completion.facts[0].value_json)["object_id"] == identity
    prompt = json.loads(runtime.calls[0]["prompt"])
    assert prompt["observations"][0]["input_count"] == 100_000
    assert len(runtime.calls[0]["prompt"].encode("utf-8")) <= 65536
    assert "synthetic:dataset:099999" not in json.dumps(prompt["observations"][0])


def test_later_page_discovery_uses_actual_context_bound_cursor_without_top25_or_preview_cutoff(
    scale,
):
    identity = dataset_id(501)

    class Pages(FakeRuntime):
        def structured_chat_result(self, **request):
            if not self.calls:
                self.actions = [
                    tool("catalogue.list", filters={"kinds": ["dataset"]}, limit=500)
                ]
            else:
                prompt = json.loads(request["prompt"])
                page = prompt["observations"][-1]["listing_page"]
                self.actions = [
                    tool(
                        "catalogue.list",
                        filters={"kinds": ["dataset"]},
                        limit=500,
                        cursor=page["next_cursor"],
                    )
                ]
            return super().structured_chat_result(**request)

    runtime = Pages()
    result = controller(scale, runtime).execute(
        {**scale[-1].request, "question": f'Find object "{identity}"'}
    )
    assert result.outcome == "completed"
    assert result.budget.tool_actions == 3 and result.budget.model_calls == 2
    assert len(result.observations[-1].objects) == 500
    assert result.observations[-1].objects[1].object_id == identity
    prompt = json.loads(runtime.calls[-1]["prompt"])
    assert prompt["observations"][-1]["objects_total"] == 500
    assert len(prompt["observations"][-1]["objects"]) <= 20
    assert len(runtime.calls[-1]["prompt"].encode("utf-8")) <= 65536
