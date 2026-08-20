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
        self.calls.append(("chat", kwargs))
        return _VertexResponse(text="vertex answer")

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
            return _Response({"message": {"content": "grounded answer"}})
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
