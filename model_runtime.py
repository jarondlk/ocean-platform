"""Provider boundary for chat generation and text embeddings.

The application currently ships with an Ollama implementation. Keeping the
HTTP contract behind this module lets a cloud-hosted model provider be added
without coupling retrieval, API, and persistence code to that provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol

import requests

import config


class ModelRuntimeConfigurationError(ValueError):
    """Raised when the selected model provider is unsupported."""


class ModelRuntime(Protocol):
    provider: str
    endpoint: str

    def list_models(self, *, timeout: int = 3) -> List[Dict[str, Any]]:
        """Return provider model metadata."""

    def chat(
        self,
        *,
        model: str,
        prompt: str,
        options: Optional[Mapping[str, Any]] = None,
        timeout: int = 120,
    ) -> str:
        """Generate one non-streaming chat response."""

    def embed(
        self,
        text_input: str,
        *,
        model: str,
        timeout: int = 60,
    ) -> List[float]:
        """Embed one text value."""

    def embed_batch(
        self,
        texts: List[str],
        *,
        model: str,
        timeout: int = 300,
    ) -> List[List[float]]:
        """Embed a batch of text values."""


@dataclass(frozen=True)
class OllamaRuntime:
    endpoint: str
    provider: str = "ollama"

    def _url(self, path: str) -> str:
        return f"{self.endpoint.rstrip('/')}{path}"

    def list_models(self, *, timeout: int = 3) -> List[Dict[str, Any]]:
        response = requests.get(self._url("/api/tags"), timeout=timeout)
        response.raise_for_status()
        models = response.json().get("models", [])
        if not isinstance(models, list):
            raise ValueError("Ollama returned invalid model metadata")
        return [model for model in models if isinstance(model, dict)]

    def chat(
        self,
        *,
        model: str,
        prompt: str,
        options: Optional[Mapping[str, Any]] = None,
        timeout: int = 120,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if options:
            payload["options"] = dict(options)
        response = requests.post(
            self._url("/api/chat"),
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The model returned an empty answer")
        return content

    def embed(
        self,
        text_input: str,
        *,
        model: str,
        timeout: int = 60,
    ) -> List[float]:
        response = requests.post(
            self._url("/api/embed"),
            json={"model": model, "input": text_input},
            timeout=timeout,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings", [])
        if embeddings and isinstance(embeddings[0], list):
            return embeddings[0]
        raise ValueError(f"No embedding returned for model {model}")

    def embed_batch(
        self,
        texts: List[str],
        *,
        model: str,
        timeout: int = 300,
    ) -> List[List[float]]:
        response = requests.post(
            self._url("/api/embed"),
            json={"model": model, "input": texts},
            timeout=timeout,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings", [])
        if (
            isinstance(embeddings, list)
            and len(embeddings) == len(texts)
            and all(isinstance(item, list) for item in embeddings)
        ):
            return embeddings
        raise ValueError(
            f"Expected {len(texts)} embeddings from model {model}"
        )


def get_model_runtime(
    provider: Optional[str] = None,
) -> ModelRuntime:
    selected = (provider or config.MODEL_PROVIDER).strip().lower()
    if selected == "ollama":
        return OllamaRuntime(config.OLLAMA_BASE_URL)
    raise ModelRuntimeConfigurationError(
        f"Unsupported MODEL_PROVIDER: {selected or '<empty>'}"
    )
