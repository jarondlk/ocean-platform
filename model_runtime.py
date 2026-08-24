"""Provider boundary for chat generation and text embeddings.

The application currently ships with an Ollama implementation. Keeping the
HTTP contract behind this module lets a cloud-hosted model provider be added
without coupling retrieval, API, and persistence code to that provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, TypeVar

import requests

import config


logger = logging.getLogger(__name__)
T = TypeVar("T")

RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
RETRIEVAL_QUERY = "RETRIEVAL_QUERY"


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
        task_type: str = RETRIEVAL_DOCUMENT,
        timeout: int = 60,
    ) -> List[float]:
        """Embed one text value."""

    def embed_batch(
        self,
        texts: List[str],
        *,
        model: str,
        task_type: str = RETRIEVAL_DOCUMENT,
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
        task_type: str = RETRIEVAL_DOCUMENT,
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
        task_type: str = RETRIEVAL_DOCUMENT,
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


def _status_code(exc: Exception) -> Optional[int]:
    """Extract a numeric HTTP/gRPC status code without importing an SDK type."""
    for attribute in ("status_code", "code"):
        value = getattr(exc, attribute, None)
        if callable(value):
            value = value()
        value = getattr(value, "value", value)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _embedding_values(item: Any) -> List[float]:
    values = item.get("values") if isinstance(item, dict) else getattr(item, "values", None)
    if not isinstance(values, list) or not values:
        raise ValueError("Vertex AI returned an invalid embedding")
    if not all(isinstance(value, (int, float)) for value in values):
        raise ValueError("Vertex AI returned a non-numeric embedding")
    return [float(value) for value in values]


def _finish_reason(response: Any) -> Optional[str]:
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list) or not candidates:
        return None
    value = getattr(candidates[0], "finish_reason", None)
    value = getattr(value, "value", value)
    return str(value).upper() if value is not None else None


@dataclass
class VertexRuntime:
    """Vertex AI implementation using workload identity through ADC."""

    project: str
    location: str
    embedding_dim: int
    max_attempts: int = 3
    retry_initial_seconds: float = 0.5
    request_timeout_seconds: int = 120
    client: Any = field(default=None, repr=False, compare=False)
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False, compare=False)
    provider: str = "vertex"

    @property
    def endpoint(self) -> str:
        return f"vertex://{self.project}/{self.location}"

    def _client(self) -> Any:
        if self.client is None:
            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:  # pragma: no cover - exercised in image builds
                raise ModelRuntimeConfigurationError(
                    "MODEL_PROVIDER=vertex requires the google-genai package"
                ) from exc
            self.client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                http_options=types.HttpOptions(
                    api_version="v1",
                    timeout=self.request_timeout_seconds * 1000,
                    # Keep retry accounting in _request so attempts remain
                    # observable and never multiply behind the application.
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        return self.client

    def _request(self, operation: str, call: Callable[[], T]) -> T:
        delay = self.retry_initial_seconds
        for attempt in range(1, self.max_attempts + 1):
            try:
                return call()
            except Exception as exc:
                status = _status_code(exc)
                transient = status in {429, 500, 502, 503, 504}
                if not transient or attempt >= self.max_attempts:
                    raise
                logger.warning(
                    "Vertex %s received transient status %s; retrying attempt %d/%d",
                    operation,
                    status,
                    attempt + 1,
                    self.max_attempts,
                )
                self.sleep(delay)
                delay *= 2
        raise RuntimeError(f"Vertex {operation} exhausted retry loop")

    def list_models(self, *, timeout: int = 3) -> List[Dict[str, Any]]:
        del timeout
        return [
            {"name": config.CHAT_MODEL, "kind": "chat", "provider": self.provider},
            {
                "name": config.EMBEDDING_MODEL,
                "kind": "embedding",
                "provider": self.provider,
                "dimensions": self.embedding_dim,
            },
        ]

    def chat(
        self,
        *,
        model: str,
        prompt: str,
        options: Optional[Mapping[str, Any]] = None,
        timeout: int = 120,
    ) -> str:
        del timeout
        source = dict(options or {})
        vertex_options: Dict[str, Any] = {}
        for key in ("temperature", "top_p", "top_k", "seed"):
            if source.get(key) is not None:
                vertex_options[key] = source[key]
        requested_output = source.get("max_output_tokens", source.get("num_predict"))
        output_limit = config.CHAT_MAX_OUTPUT_TOKENS
        if requested_output is not None:
            output_limit = min(int(requested_output), output_limit)
        vertex_options["max_output_tokens"] = output_limit
        vertex_options["thinking_config"] = {
            "thinking_budget": config.VERTEX_THINKING_BUDGET,
            "include_thoughts": False,
        }

        response = self._request(
            "chat",
            lambda: self._client().models.generate_content(
                model=model,
                contents=prompt,
                config=vertex_options,
            ),
        )
        finish_reason = _finish_reason(response)
        if finish_reason not in {None, "STOP"}:
            raise ValueError(
                f"Vertex AI answer did not finish cleanly: {finish_reason}"
            )
        content = getattr(response, "text", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Vertex AI returned an empty answer")
        return content

    def embed(
        self,
        text_input: str,
        *,
        model: str,
        task_type: str = RETRIEVAL_DOCUMENT,
        timeout: int = 60,
    ) -> List[float]:
        embeddings = self.embed_batch(
            [text_input],
            model=model,
            task_type=task_type,
            timeout=timeout,
        )
        return embeddings[0]

    def embed_batch(
        self,
        texts: List[str],
        *,
        model: str,
        task_type: str = RETRIEVAL_DOCUMENT,
        timeout: int = 300,
    ) -> List[List[float]]:
        del timeout
        if not texts:
            return []
        response = self._request(
            "embedding",
            lambda: self._client().models.embed_content(
                model=model,
                contents=texts,
                config={
                    "task_type": task_type,
                    "output_dimensionality": self.embedding_dim,
                    "auto_truncate": False,
                },
            ),
        )
        items = getattr(response, "embeddings", None)
        if not isinstance(items, list) or len(items) != len(texts):
            raise ValueError(
                f"Expected {len(texts)} embeddings from Vertex model {model}"
            )
        embeddings = [_embedding_values(item) for item in items]
        invalid = [len(item) for item in embeddings if len(item) != self.embedding_dim]
        if invalid:
            raise ValueError(
                f"Vertex model {model} returned dimension {invalid[0]}; "
                f"expected {self.embedding_dim}"
            )
        return embeddings


def get_model_runtime(
    provider: Optional[str] = None,
) -> ModelRuntime:
    selected = (provider or config.MODEL_PROVIDER).strip().lower()
    if selected == "ollama":
        return OllamaRuntime(config.OLLAMA_BASE_URL)
    if selected == "vertex":
        if not config.GOOGLE_CLOUD_PROJECT:
            raise ModelRuntimeConfigurationError(
                "MODEL_PROVIDER=vertex requires GOOGLE_CLOUD_PROJECT"
            )
        return VertexRuntime(
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
            embedding_dim=config.EMBEDDING_DIM,
            max_attempts=config.MODEL_MAX_ATTEMPTS,
            retry_initial_seconds=config.MODEL_RETRY_INITIAL_SECONDS,
            request_timeout_seconds=config.MODEL_REQUEST_TIMEOUT_SECONDS,
        )
    raise ModelRuntimeConfigurationError(
        f"Unsupported MODEL_PROVIDER: {selected or '<empty>'}"
    )
