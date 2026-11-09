from types import SimpleNamespace

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
    assert calls[0]["config"]["thinking_config"] == {"thinking_level": "LOW", "include_thoughts": False}
    assert calls[0]["config"]["response_json_schema"] == {"type": "object"}


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
