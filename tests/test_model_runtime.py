from __future__ import annotations

import pytest

import config
import model_runtime


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _VertexEmbedding:
    def __init__(self, values):
        self.values = values


class _VertexResponse:
    def __init__(self, *, text=None, embeddings=None, candidates=None):
        self.text = text
        self.embeddings = embeddings
        self.candidates = candidates


class _VertexModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        from types import SimpleNamespace
        self.calls.append(("chat", kwargs))
        return _VertexResponse(text="vertex answer", candidates=[SimpleNamespace(finish_reason="STOP")])

    def embed_content(self, **kwargs):
        self.calls.append(("embedding", kwargs))
        return _VertexResponse(
            embeddings=[_VertexEmbedding([0.1, 0.2]) for _ in kwargs["contents"]]
        )


class _VertexClient:
    def __init__(self):
        self.models = _VertexModels()


def test_ollama_runtime_normalizes_chat_and_embedding_calls(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        if url.endswith("/api/chat"):
            return _Response({"message": {"content": "grounded answer"}, "done_reason": "stop", "done": True})
        if isinstance(json["input"], list):
            return _Response({"embeddings": [[0.1], [0.2]]})
        return _Response({"embeddings": [[0.3, 0.4]]})

    monkeypatch.setattr(model_runtime.requests, "post", fake_post)
    runtime = model_runtime.OllamaRuntime("http://ollama.internal:11434/")

    assert runtime.chat(
        model="chat-model",
        prompt="question",
        options={"temperature": 0.1},
    ) == "grounded answer"
    assert runtime.embed("text", model="embed-model") == [0.3, 0.4]
    assert runtime.embed_batch(
        ["first", "second"],
        model="embed-model",
    ) == [[0.1], [0.2]]
    assert calls[0][0] == "http://ollama.internal:11434/api/chat"
    assert calls[0][1]["options"] == {"temperature": 0.1}


def test_ollama_runtime_lists_models(monkeypatch):
    monkeypatch.setattr(
        model_runtime.requests,
        "get",
        lambda *_args, **_kwargs: _Response(
            {"models": [{"name": "qwen"}, {"name": "nomic-embed-text"}]}
        ),
    )

    runtime = model_runtime.OllamaRuntime("http://ollama.internal:11434")

    assert [model["name"] for model in runtime.list_models()] == [
        "qwen",
        "nomic-embed-text",
    ]


def test_structured_ollama_has_schema_and_independent_limits(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response({'message': {'content': '{"status":"ready"}'}, 'done_reason': 'stop'})
    monkeypatch.setattr(model_runtime.requests, 'post', post)
    schema = {'type': 'object', 'properties': {'status': {'type': 'string'}}}
    raw = model_runtime.OllamaRuntime('http://localhost:11434').structured_chat(
        model='planner', prompt='plan', schema=schema, max_output_tokens=1234, timeout=17)
    assert raw == '{"status":"ready"}'
    assert calls[0][1]['json']['format'] == schema
    assert calls[0][1]['timeout'] == 17
    assert calls[0][1]['json']['options']['num_predict'] == 1234


def test_structured_vertex_uses_json_schema_without_answer_retry_loop():
    client = _VertexClient()
    runtime = model_runtime.VertexRuntime(project='project', location='global', embedding_dim=2, client=client)
    schema = {'type': 'object'}
    runtime.structured_chat(model='planner', prompt='plan', schema=schema, max_output_tokens=900, timeout=15)
    call = client.models.calls[0][1]
    assert call['config']['response_json_schema'] == schema
    assert call['config']['response_mime_type'] == 'application/json'
    assert call['config']['max_output_tokens'] == 900


def test_runtime_factory_rejects_unimplemented_provider(monkeypatch):
    monkeypatch.setattr(config, "MODEL_PROVIDER", "not-implemented")

    with pytest.raises(
        model_runtime.ModelRuntimeConfigurationError,
        match="Unsupported MODEL_PROVIDER",
    ):
        model_runtime.get_model_runtime()


def test_vertex_runtime_maps_options_and_embedding_task(monkeypatch):
    client = _VertexClient()
    runtime = model_runtime.VertexRuntime(
        project="example-project",
        location="global",
        embedding_dim=2,
        client=client,
    )
    monkeypatch.setattr(config, "CHAT_MAX_OUTPUT_TOKENS", 100)

    assert runtime.endpoint == "vertex://example-project/global"
    assert runtime.chat(
        model="gemini-flash",
        prompt="question",
        options={"temperature": 0.2, "num_predict": 250},
    ) == "vertex answer"
    assert runtime.embed_batch(
        ["first", "second"],
        model="gemini-embedding-001",
        task_type=model_runtime.RETRIEVAL_DOCUMENT,
    ) == [[0.1, 0.2], [0.1, 0.2]]

    chat_call = client.models.calls[0][1]
    assert chat_call["config"] == {
        "temperature": 0.2,
        "max_output_tokens": 100,
        "thinking_config": {
            "thinking_budget": 0,
            "include_thoughts": False,
        },
    }
    embedding_call = client.models.calls[1][1]
    assert embedding_call["config"] == {
        "task_type": "RETRIEVAL_DOCUMENT",
        "output_dimensionality": 2,
        "auto_truncate": False,
    }


def test_vertex_sdk_serializes_effective_controls_and_meters_transport(monkeypatch):
    """Exercise the installed SDK with a local transport, without provider calls."""
    import json
    from types import SimpleNamespace

    import httpx
    from google import genai
    from google.oauth2.credentials import Credentials
    from google.genai import types

    from evaluation.qa.run_v061_acceptance import MeteredModels

    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": "bounded answer"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2,
                              "totalTokenCount": 7},
        })

    monkeypatch.setattr(config, "CHAT_MAX_OUTPUT_TOKENS", 100)
    monkeypatch.setattr(config, "VERTEX_THINKING_BUDGET", 0)
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = genai.Client(vertexai=True, project="fixture", location="global",
                              credentials=Credentials(token="fixture-token"),
                              http_options=types.HttpOptions(httpx_client=transport,
                                  retry_options=types.HttpRetryOptions(attempts=1)))
        try:
            meter = MeteredModels(client.models, limit=1)
            runtime = model_runtime.VertexRuntime(project="fixture", location="global",
                embedding_dim=2, client=SimpleNamespace(models=meter))
            options = {"temperature": 0.2, "top_p": 0.8, "top_k": 10, "seed": 7,
                       "num_predict": 250, "num_ctx": 2048, "repeat_penalty": 1.5}
            result = runtime.chat_result(model="gemini-fixture", prompt="question", options=options)
            assert result.require_completed() == "bounded answer"
            assert result.finish_reason == "STOP"
            assert result.usage == model_runtime.GenerationUsage(input_tokens=5, output_tokens=2, total_tokens=7)
            with pytest.raises(model_runtime.GenerationError) as failure:
                runtime.chat(model="gemini-fixture", prompt="question", options=options)
            assert failure.value.result.status == "failed"
        finally:
            client.close()
    assert len(requests) == len(meter.generations) == 1
    generation = dict(requests[0]["generationConfig"])
    thinking = types.ThinkingConfig.model_validate(generation.pop("thinkingConfig"))
    assert thinking.model_dump(exclude_none=True) == {
        "thinking_budget": 0, "include_thoughts": False,
    }
    assert generation == {
        "temperature": 0.2, "topP": 0.8, "topK": 10, "seed": 7,
        "maxOutputTokens": 100,
    }


def test_vertex_runtime_retries_only_transient_statuses():
    delays = []
    attempts = 0

    class _ProviderError(Exception):
        status_code = 429

    def transient_call():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _ProviderError("quota")
        return "ok"

    runtime = model_runtime.VertexRuntime(
        project="example-project",
        location="global",
        embedding_dim=2,
        max_attempts=3,
        retry_initial_seconds=0.25,
        sleep=delays.append,
    )

    assert runtime._request("test", transient_call) == "ok"
    assert attempts == 3
    assert delays == [0.25, 0.5]

    class _PermissionError(Exception):
        status_code = 403

    with pytest.raises(_PermissionError):
        runtime._request("test", lambda: (_ for _ in ()).throw(_PermissionError()))


def test_vertex_runtime_validates_embedding_dimension():
    client = _VertexClient()
    runtime = model_runtime.VertexRuntime(
        project="example-project",
        location="global",
        embedding_dim=3,
        client=client,
    )

    with pytest.raises(ValueError, match="returned dimension 2; expected 3"):
        runtime.embed("text", model="gemini-embedding-001")


def test_vertex_runtime_rejects_truncated_answers():
    class _Candidate:
        finish_reason = "MAX_TOKENS"

    client = _VertexClient()
    client.models.generate_content = lambda **_kwargs: _VertexResponse(
        text="incomplete",
        candidates=[_Candidate()],
    )
    runtime = model_runtime.VertexRuntime(
        project="example-project",
        location="global",
        embedding_dim=2,
        client=client,
    )

    with pytest.raises(ValueError, match="did not finish cleanly: MAX_TOKENS"):
        runtime.chat(model="gemini-flash", prompt="question")


def test_runtime_factory_builds_vertex_from_config(monkeypatch):
    monkeypatch.setattr(config, "MODEL_PROVIDER", "vertex")
    monkeypatch.setattr(config, "GOOGLE_CLOUD_PROJECT", "example-project")
    monkeypatch.setattr(config, "GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.setattr(config, "EMBEDDING_DIM", 768)

    runtime = model_runtime.get_model_runtime()

    assert isinstance(runtime, model_runtime.VertexRuntime)
    assert runtime.project == "example-project"
    assert runtime.location == "global"


def test_output_limit_records_budget_without_retrying_or_returning_partial_text():
    from types import SimpleNamespace
    client = _VertexClient()
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            candidates=[SimpleNamespace(finish_reason='MAX_TOKENS')],
            usage_metadata=SimpleNamespace(candidates_token_count=28),
            text='private unfinished answer [S1',
        )

    client.models.generate_content = generate
    runtime = model_runtime.VertexRuntime(project='example-project', location='global', embedding_dim=2, client=client)
    with pytest.raises(model_runtime.ModelOutputLimitError) as failure:
        runtime.chat(model='gemini-flash', prompt='question', options={'num_predict': 32})
    assert len(calls) == 1
    assert failure.value.diagnostics == {'finish_reason': 'MAX_TOKENS', 'max_output_tokens': 32, 'output_tokens': 28}
    assert 'private unfinished' not in str(failure.value)


def _mock_generation(monkeypatch, provider, payload):
    """Use each real adapter with a provider response supplied entirely locally."""
    from types import SimpleNamespace

    calls = []
    if provider == "ollama":
        def post(*args, **kwargs):
            calls.append((args, kwargs))
            if isinstance(payload, Exception):
                raise payload
            return _Response(payload)
        monkeypatch.setattr(model_runtime.requests, "post", post)
        runtime = model_runtime.OllamaRuntime("http://fixture.invalid")
    else:
        def generate(**kwargs):
            calls.append(kwargs)
            if isinstance(payload, Exception):
                raise payload
            return payload
        runtime = model_runtime.VertexRuntime(
            project="fixture", location="global", embedding_dim=2,
            client=SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
        )
    return runtime, calls


def _generation_payload(provider, reason, *, content='{"status":"ready"}', usage=None):
    from types import SimpleNamespace

    if provider == "ollama":
        return {"message": {"content": content}, "done_reason": reason, **(usage or {})}
    return SimpleNamespace(
        text=content, candidates=[SimpleNamespace(finish_reason=reason)],
        usage_metadata=SimpleNamespace(**usage) if usage is not None else None,
    )


def _generate(runtime, method, *, result=True):
    kwargs = {"model": "fixture-model", "prompt": "private full prompt"}
    if method == "structured_chat":
        kwargs.update(schema={"type": "object"}, max_output_tokens=32, timeout=7)
    else:
        kwargs["options"] = {"num_predict": 32}
    return getattr(runtime, method + ("_result" if result else ""))(**kwargs)


@pytest.mark.parametrize("method", ["chat", "structured_chat"])
@pytest.mark.parametrize("provider,reason,status", [
    ("ollama", "stop", "completed"), ("vertex", "STOP", "completed"),
    ("ollama", "length", "output_limited"), ("vertex", "MAX_TOKENS", "output_limited"),
    ("ollama", "refused", "refused"), ("vertex", "SAFETY", "refused"),
    ("ollama", "error", "failed"), ("vertex", "MALFORMED_FUNCTION_CALL", "failed"),
    ("ollama", None, "unknown"), ("vertex", None, "unknown"),
    ("ollama", "new_reason", "unknown"), ("vertex", "OTHER", "unknown"),
])
def test_generation_result_normalizes_all_termination_outcomes(
    monkeypatch, provider, reason, status, method,
):
    runtime, calls = _mock_generation(monkeypatch, provider, _generation_payload(provider, reason))
    result = _generate(runtime, method)
    assert isinstance(result, model_runtime.GenerationResult)
    assert (result.provider, result.model, result.status, result.finish_reason) == (
        provider, "fixture-model", status, reason,
    )
    assert result.content == '{"status":"ready"}'
    assert result.usage is None
    assert result.elapsed_seconds >= 0
    if status == "completed":
        assert result.require_completed() == result.content
        assert _generate(runtime, method, result=False) == result.content
    else:
        expected_error = model_runtime.ModelOutputLimitError if status == "output_limited" else model_runtime.GenerationError
        with pytest.raises(expected_error) as failure:
            result.require_completed()
        assert failure.value.result is result
        assert "private full prompt" not in str(failure.value)
        with pytest.raises(model_runtime.GenerationError):
            _generate(runtime, method, result=False)
    assert len(calls) == 2


@pytest.mark.parametrize("provider", ["ollama", "vertex"])
@pytest.mark.parametrize("method", ["chat", "structured_chat"])
@pytest.mark.parametrize("counts,expected", [
    (None, None),
    ({}, None),
    ({"input": 4, "output": 2, "total": 6}, (4, 2, 6)),
    ({"input": 4}, (4, None, None)),
    ({"input": True, "output": -1, "total": "6"}, None),
    ({"input": 0, "output": 2.5, "total": 0}, (0, None, 0)),
])
def test_generation_usage_preserves_only_reported_nonnegative_integer_counts(
    monkeypatch, provider, method, counts, expected,
):
    keys = ({"input": "prompt_eval_count", "output": "eval_count", "total": "total_token_count"}
            if provider == "ollama" else
            {"input": "prompt_token_count", "output": "candidates_token_count", "total": "total_token_count"})
    usage = None if counts is None else {keys[key]: value for key, value in counts.items()}
    reason = "stop" if provider == "ollama" else "STOP"
    runtime, _ = _mock_generation(monkeypatch, provider, _generation_payload(provider, reason, usage=usage))
    result = _generate(runtime, method)
    if expected is None:
        assert result.usage is None
    else:
        assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) == expected


@pytest.mark.parametrize("provider", ["ollama", "vertex"])
@pytest.mark.parametrize("method", ["chat", "structured_chat"])
def test_generation_elapsed_time_is_monotonic_measured_and_metadata_is_frozen(monkeypatch, provider, method):
    from dataclasses import FrozenInstanceError
    from types import SimpleNamespace

    reason = "stop" if provider == "ollama" else "STOP"
    payload = _generation_payload(provider, reason)
    if isinstance(payload, dict):
        payload["total_duration"] = 999999999999
    else:
        payload.usage_metadata = SimpleNamespace(total_token_count=1)
    runtime, _ = _mock_generation(monkeypatch, provider, payload)
    times = iter([100.0, 100.125])
    monkeypatch.setattr(model_runtime.time, "monotonic", lambda: next(times))
    result = _generate(runtime, method)
    assert result.elapsed_seconds == 0.125
    with pytest.raises(FrozenInstanceError):
        result.status = "completed"
    if result.usage:
        with pytest.raises(FrozenInstanceError):
            result.usage.total_tokens = 50


@pytest.mark.parametrize("provider", ["ollama", "vertex"])
@pytest.mark.parametrize("method", ["chat", "structured_chat"])
def test_transport_errors_become_safe_failed_results_without_raw_error_chains(monkeypatch, provider, method):
    runtime, calls = _mock_generation(
        monkeypatch, provider, RuntimeError("private full prompt; api_key=secret; provider private output"),
    )
    result = _generate(runtime, method)
    assert result.status == "failed"
    assert result.content == ""
    assert result.usage is None
    with pytest.raises(model_runtime.GenerationError) as failure:
        result.require_completed()
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
    assert len(calls) == 1
    for text in (str(failure.value), repr(failure.value.diagnostics), repr(result.diagnostics())):
        assert "private" not in text
        assert "secret" not in text


@pytest.mark.parametrize("provider", ["ollama", "vertex"])
@pytest.mark.parametrize("method", ["chat", "structured_chat"])
@pytest.mark.parametrize("content", [None, "", "  ", 42, {"text": "wrong shape"}])
def test_explicit_stop_cannot_complete_malformed_or_empty_content(monkeypatch, provider, method, content):
    reason = "stop" if provider == "ollama" else "STOP"
    runtime, _ = _mock_generation(monkeypatch, provider, _generation_payload(provider, reason, content=content))
    result = _generate(runtime, method)
    assert result.status == "failed"
    with pytest.raises(model_runtime.GenerationError):
        result.require_completed()


@pytest.mark.parametrize("method", ["chat", "structured_chat"])
def test_ollama_incomplete_done_flag_overrides_stop(monkeypatch, method):
    payload = _generation_payload("ollama", "stop")
    payload["done"] = False
    runtime, _ = _mock_generation(monkeypatch, "ollama", payload)
    assert _generate(runtime, method).status != "completed"


@pytest.mark.parametrize("method", ["chat", "structured_chat"])
def test_vertex_blocked_prompt_without_candidates_is_refused(monkeypatch, method):
    from types import SimpleNamespace

    runtime, _ = _mock_generation(monkeypatch, "vertex", SimpleNamespace(
        text=None, candidates=[], prompt_feedback=SimpleNamespace(block_reason="SAFETY"),
    ))
    result = _generate(runtime, method)
    assert result.status == "refused"
    assert result.finish_reason == "SAFETY"
    with pytest.raises(model_runtime.GenerationError):
        result.require_completed()


@pytest.mark.parametrize("blocked", ["FUTURE_POLICY_BLOCK", {"reason": "private prompt"}, 1])
@pytest.mark.parametrize("method", ["chat", "structured_chat"])
def test_vertex_unknown_or_malformed_block_feedback_overrides_candidate_stop(monkeypatch, method, blocked):
    from types import SimpleNamespace

    payload = _generation_payload("vertex", "STOP")
    payload.prompt_feedback = SimpleNamespace(block_reason=blocked)
    runtime, _ = _mock_generation(monkeypatch, "vertex", payload)
    result = _generate(runtime, method)
    assert result.status == "unknown"
    assert result.finish_reason == "STOP"
    with pytest.raises(model_runtime.GenerationError):
        result.require_completed()


@pytest.mark.parametrize("provider", ["ollama", "vertex"])
@pytest.mark.parametrize("reason", [17, {"text": "private prompt"}, "private full prompt; api_key=secret", "x" * 1000])
def test_malformed_finish_metadata_never_completes_or_enters_diagnostics(monkeypatch, provider, reason):
    runtime, _ = _mock_generation(monkeypatch, provider, _generation_payload(provider, reason))
    result = _generate(runtime, "chat")
    assert result.status == "unknown"
    assert result.finish_reason is None
    with pytest.raises(model_runtime.GenerationError) as failure:
        result.require_completed()
    assert "private" not in repr(failure.value.diagnostics)
    assert "secret" not in repr(result.diagnostics())


@pytest.mark.parametrize("provider", ["ollama", "vertex"])
@pytest.mark.parametrize("method", ["chat", "structured_chat"])
def test_malformed_provider_payload_is_failed(monkeypatch, provider, method):
    runtime, _ = _mock_generation(monkeypatch, provider, ["private invalid payload"])
    result = _generate(runtime, method)
    assert result.status == "failed"
    assert result.content == ""
    with pytest.raises(model_runtime.GenerationError):
        result.require_completed()


@pytest.mark.parametrize("method,expected_attempts", [("chat", 3), ("structured_chat", 1)])
def test_generation_result_preserves_existing_vertex_transport_retry_budget(
    monkeypatch, caplog, method, expected_attempts,
):
    class QuotaError(Exception):
        status_code = 429

    runtime, calls = _mock_generation(monkeypatch, "vertex", QuotaError("private full prompt; api_key=secret"))
    delays = []
    runtime.sleep = delays.append
    runtime.retry_initial_seconds = 0.25
    result = _generate(runtime, method)
    assert result.status == "failed"
    assert len(calls) == expected_attempts
    assert delays == ([0.25, 0.5] if method == "chat" else [])
    assert "private" not in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.parametrize("provider", ["ollama", "vertex"])
@pytest.mark.parametrize("method", ["chat", "structured_chat"])
def test_generation_boundary_propagates_base_exception_cancellation(monkeypatch, provider, method):
    from types import SimpleNamespace

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt()

    if provider == "ollama":
        runtime = model_runtime.OllamaRuntime("http://fixture.invalid")
        monkeypatch.setattr(model_runtime.requests, "post", cancel)
    else:
        runtime = model_runtime.VertexRuntime(
            project="fixture", location="global", embedding_dim=2,
            client=SimpleNamespace(models=SimpleNamespace(generate_content=cancel)),
        )
    with pytest.raises(KeyboardInterrupt):
        _generate(runtime, method)


@pytest.mark.parametrize("label", ["https://user:secret@provider.invalid", "private full prompt", "x" * 201])
def test_generation_diagnostic_labels_reject_credential_urls_and_free_form_text(label):
    result = model_runtime.GenerationResult(
        content="private output", provider=label, model=label, status="unknown",
        finish_reason=label, elapsed_seconds=0.5,
    )
    diagnostics = result.diagnostics()
    assert diagnostics["provider"] is None
    assert diagnostics["model"] is None
    assert diagnostics["finish_reason"] is None
    assert "private" not in repr(diagnostics)
    assert "secret" not in repr(diagnostics)
