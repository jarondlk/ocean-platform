import json
from types import SimpleNamespace

import httpx
import pytest

from model_runtime import VertexRuntime
from orchestration.beta_vertex_research import BetaVertexResearchRuntime


@pytest.mark.parametrize("finish,status", [("STOP", "completed"), ("MAX_TOKENS", "output_limited"),
    ("SAFETY", "refused"), ("OTHER", "unknown"), (None, "unknown")])
def test_beta_gemini_uses_bounded_current_structured_api_and_preserves_completion(monkeypatch, finish, status):
    calls, timeouts, closed = [], [], []
    def generate(**kwargs):
        calls.append(kwargs)
        return {"text": '{"test_only":true}', "candidates": [{"finish_reason": finish}],
                "usage_metadata": {"prompt_token_count": 12, "candidates_token_count": 4, "total_token_count": 16}}
    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate), close=lambda: closed.append(True))
    def create(runtime):
        timeouts.append(runtime.request_timeout_seconds)
        return client
    monkeypatch.setattr(VertexRuntime, "_client", create)
    runtime = BetaVertexResearchRuntime(project="ocean-v1-beta-20261101", location="global", embedding_dim=768,
        max_attempts=1, request_timeout_seconds=45)
    result = runtime.structured_chat_result(model="gemini-3.8-flash", prompt="Synthetic test only",
        schema={"type": "object"}, max_output_tokens=4096, timeout=9.5)
    assert result.status == status
    assert result.usage.total_tokens == 16
    assert timeouts == [9.5] and closed == [True] and len(calls) == 1
    assert calls[0] == {
        "model": "gemini-3.8-flash",
        "contents": "Synthetic test only",
        "config": {
            "response_mime_type": "application/json",
            "response_json_schema": {"type": "object"},
            "max_output_tokens": 4096,
            "thinking_config": {"thinking_level": "LOW", "include_thoughts": False},
        },
    }


def test_actual_sdk_serializes_only_supported_gemini_generation_fields():
    from google import genai
    from google.genai import types
    from google.oauth2.credentials import Credentials

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": '{"test_only":true}'}]},
                "finishReason": "STOP"}],
        })

    with genai.Client(vertexai=True, project="ocean-v1-beta-20261101", location="global",
            credentials=Credentials(token="synthetic-test-only"), http_options=types.HttpOptions(
                api_version="v1", retry_options=types.HttpRetryOptions(attempts=1),
                client_args={"transport": httpx.MockTransport(respond)})) as client:
        runtime = BetaVertexResearchRuntime(project="ocean-v1-beta-20261101", location="global",
            embedding_dim=768, max_attempts=1, client=client)
        result = runtime.structured_chat_result(model="gemini-3.8-flash", prompt="Synthetic test only",
            schema={"type": "object"}, max_output_tokens=4096, timeout=10)

    assert result.status == "completed"
    assert len(requests) == 1
    assert requests[0].url.host == "aiplatform.googleapis.com"
    assert requests[0].url.path.endswith("/locations/global/publishers/google/models/gemini-3.8-flash:generateContent")
    assert json.loads(requests[0].content)["generationConfig"] == {
        "responseMimeType": "application/json",
        "responseJsonSchema": {"type": "object"},
        "maxOutputTokens": 4096,
        "thinkingConfig": {"thinking_level": "LOW", "include_thoughts": False},
    }


def test_provider_failure_is_not_retried_or_exposed(monkeypatch):
    calls = []
    def fail(**kwargs):
        calls.append(True)
        raise RuntimeError("private provider diagnostic never exposed")
    client = SimpleNamespace(models=SimpleNamespace(generate_content=fail), close=lambda: None)
    monkeypatch.setattr(VertexRuntime, "_client", lambda self: client)
    runtime = BetaVertexResearchRuntime(project="ocean-v1-beta-20261101", location="global", embedding_dim=768,
        max_attempts=1, request_timeout_seconds=45)
    result = runtime.structured_chat_result(model="gemini-3.8-flash", prompt="Synthetic test only",
        schema={"type": "object"}, max_output_tokens=4096, timeout=120)
    assert result.status == "failed" and result.content == "" and calls == [True]
    assert "private" not in repr(result.diagnostics())


@pytest.mark.parametrize("change", [{"model": "gemini-2.5-flash"}, {"timeout": float("nan")},
    {"timeout": 0}, {"max_output_tokens": 4097}])
def test_invalid_or_unbounded_generation_never_constructs_a_client(monkeypatch, change):
    monkeypatch.setattr(VertexRuntime, "_client", lambda self: pytest.fail("No external effect"))
    runtime = BetaVertexResearchRuntime(project="ocean-v1-beta-20261101", location="global", embedding_dim=768, max_attempts=1)
    with pytest.raises(ValueError):
        runtime.structured_chat_result(**{"model": "gemini-3.8-flash", "prompt": "Synthetic test only",
            "schema": {"type": "object"}, "max_output_tokens": 4096, "timeout": 10, **change})


def captured_wire_schema(monkeypatch, schema):
    calls = []
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **request: calls.append(request)), close=lambda: None)
    monkeypatch.setattr(VertexRuntime, "_client", lambda self: client)
    runtime = BetaVertexResearchRuntime(project="ocean-v1-beta-20261101", location="global", embedding_dim=768, max_attempts=1)
    runtime.structured_chat_result(model="gemini-3.8-flash", prompt="Synthetic test only", schema=schema,
        max_output_tokens=4096, timeout=10)
    assert len(calls) == 1
    return calls[0]["config"]["response_json_schema"]


@pytest.mark.parametrize("contract", ["controller", "synthesis"])
def test_actual_sdk_normalizes_real_contract_constants_without_mutating_replay_schema(contract):
    from google import genai
    from google.genai import types
    from google.oauth2.credentials import Credentials
    from orchestration.research_synthesis import selection_schema
    from schema.research_controller import canonical_json, controller_action_schema, parse_controller_action

    schema = controller_action_schema() if contract == "controller" else selection_schema()
    original = canonical_json(schema)
    tool = {"kind": "tool", "tool": "catalogue.open", "arguments": {"object_id": "synthetic:ctd"}, "fact_ids": ["requested:1"]}
    content = tool if contract == "controller" else {"version": "c21-selection-v1", "blocks": []}
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(content)}]}, "finishReason": "STOP"}]})

    with genai.Client(vertexai=True, project="ocean-v1-beta-20261101", location="global",
            credentials=Credentials(token="synthetic-test-only"), http_options=types.HttpOptions(
                api_version="v1", retry_options=types.HttpRetryOptions(attempts=1),
                client_args={"transport": httpx.MockTransport(respond)})) as client:
        runtime = BetaVertexResearchRuntime(project="ocean-v1-beta-20261101", location="global", embedding_dim=768, max_attempts=1, client=client)
        result = runtime.structured_chat_result(model="gemini-3.8-flash", prompt="Synthetic test only",
            schema=schema, max_output_tokens=4096, timeout=10)

    assert result.status == "completed" and len(requests) == 1
    generation_config = json.loads(requests[0].content)["generationConfig"]
    wire = generation_config["responseJsonSchema"]
    assert '"const":' not in json.dumps(wire)
    assert canonical_json(schema) == original
    assert "temperature" not in generation_config
    assert generation_config["maxOutputTokens"] == 4096
    assert generation_config["thinkingConfig"] == {"thinking_level": "LOW", "include_thoughts": False}
    if contract == "controller":
        for name, kind in [("ToolAction", "tool"), ("ClarifyAction", "clarify"), ("FinishAction", "finish")]:
            assert wire["$defs"][name]["properties"]["kind"]["enum"] == [kind]
            assert schema["$defs"][name]["properties"]["kind"]["const"] == kind
        action = parse_controller_action(result.require_completed(), fact_ids=("requested:1",))
        assert action.model_dump() == tool
        with pytest.raises(ValueError):
            parse_controller_action(json.dumps({**tool, "kind": "unknown"}), fact_ids=("requested:1",))
    else:
        assert wire["properties"]["version"]["enum"] == ["c21-selection-v1"]
        for name, kind in [("FactSelection", "fact"), ("RowSelection", "rows"), ("RelationshipSelection", "relationship"), ("DocumentarySelection", "documentary")]:
            assert wire["$defs"][name]["properties"]["kind"]["enum"] == [kind]


def test_wire_constant_conversion_visits_schema_locations_not_literal_annotations(monkeypatch):
    literal = {"const": True, "properties": {"kind": {"const": "literal data"}}}
    schema = {"$defs": {"const": {"const": "defined"}},
        "properties": {"const": {"const": "property"}, "payload": {"default": literal, "examples": [literal], "enum": [literal]}},
        "items": {"anyOf": [{"const": 1}, {"allOf": [{"const": "nested"}]}]},
        "additionalProperties": {"const": "extra"}, "prefixItems": [{"const": "first"}]}
    original = json.dumps(schema, sort_keys=True)
    wire = captured_wire_schema(monkeypatch, schema)
    assert json.dumps(schema, sort_keys=True) == original
    assert wire["$defs"]["const"] == {"enum": ["defined"]}
    assert wire["properties"]["const"] == {"enum": ["property"]}
    assert wire["properties"]["payload"] == schema["properties"]["payload"]
    assert wire["properties"]["payload"]["default"] is not literal
    assert wire["items"] == {"anyOf": [{"enum": [1]}, {"allOf": [{"enum": ["nested"]}]}]}
    assert wire["additionalProperties"] == {"enum": ["extra"]}
    assert wire["prefixItems"] == [{"enum": ["first"]}]


@pytest.mark.parametrize("schema", [
    {"const": "tool", "enum": ["tool"]}, {"const": "tool", "enum": ["finish", "tool"]}, {"const": 1, "enum": [1.0]},
])
def test_compatible_existing_enum_retains_the_exact_constant_intersection(monkeypatch, schema):
    assert captured_wire_schema(monkeypatch, schema) == {"enum": [schema["const"]]}


@pytest.mark.parametrize("schema", [
    {"const": "tool", "enum": ["finish"]}, {"const": 1, "enum": [True]}, {"const": "tool", "enum": []},
    {"properties": {"kind": {"const": "tool", "enum": "tool"}}},
    *[{"const": value} for value in (True, None, {"const": "literal"}, ["literal"], float("nan"))],
])
def test_conflicting_or_unsupported_constant_fails_before_any_client(monkeypatch, schema):
    monkeypatch.setattr(VertexRuntime, "_client", lambda self: pytest.fail("Invalid wire schema must not construct a client"))
    runtime = BetaVertexResearchRuntime(project="ocean-v1-beta-20261101", location="global", embedding_dim=768, max_attempts=1)
    with pytest.raises(ValueError):
        runtime.structured_chat_result(model="gemini-3.8-flash", prompt="Synthetic test only", schema=schema,
            max_output_tokens=4096, timeout=10)


def test_beta_wire_fix_preserves_supported_historical_controller_fingerprint():
    from orchestration.research_controller_replay import controller_fingerprint
    from orchestration.research_evidence_projection import SUPPORTED_CONTROLLER_FINGERPRINTS

    assert controller_fingerprint() == "cf87f56712ccf4eddb03fe944e9bb293132163e881fdea38bb515b103c2641a5"
    assert controller_fingerprint() in SUPPORTED_CONTROLLER_FINGERPRINTS
