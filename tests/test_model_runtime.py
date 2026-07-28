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
