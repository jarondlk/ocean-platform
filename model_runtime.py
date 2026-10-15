"""Provider boundary for chat generation and text embeddings.

The application currently ships with an Ollama implementation. Keeping the
HTTP contract behind this module lets a cloud-hosted model provider be added
without coupling retrieval, API, and persistence code to that provider.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
import re
import time
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Protocol, TypeVar

import requests

import config


logger = logging.getLogger(__name__)
T = TypeVar("T")

RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
RETRIEVAL_QUERY = "RETRIEVAL_QUERY"


class ModelRuntimeConfigurationError(ValueError):
    """Raised when the selected model provider is unsupported."""


GenerationStatus = Literal["completed", "output_limited", "refused", "failed", "unknown"]


@dataclass(frozen=True)
class GenerationUsage:
    """Counts actually reported by a provider; unavailable counts stay None."""

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


def _safe_label(value: Any, *, limit: int = 200) -> Optional[str]:
    # Diagnostics never accept free-form provider text, URLs with credentials,
    # exception messages or prompts in fields intended to be machine labels.
    if isinstance(value, str) and "://" not in value and re.fullmatch(r"[A-Za-z0-9_./:-]+", value) and len(value) <= limit:
        return value
    return None


@dataclass(frozen=True)
class GenerationResult:
    """Provider-independent outcome of one bounded generation operation.

    Content can be retained for explicit inspection on an incomplete result,
    but only require_completed may release it to a completed-answer consumer.
    Elapsed time includes existing adapter retries and their backoff.
    """

    content: str = field(repr=False)
    provider: str
    model: str
    status: GenerationStatus
    finish_reason: Optional[str]
    elapsed_seconds: float
    usage: Optional[GenerationUsage] = None
    max_output_tokens: Optional[int] = None

    def diagnostics(self) -> Dict[str, Any]:
        """Safe execution metadata, without generated text or provider errors."""
        return {
            "provider": _safe_label(self.provider),
            "model": _safe_label(self.model),
            "status": self.status,
            "finish_reason": _safe_label(self.finish_reason, limit=64),
            "elapsed_seconds": self.elapsed_seconds,
            "usage": asdict(self.usage) if self.usage is not None else None,
            "max_output_tokens": self.max_output_tokens,
        }

    def require_completed(self) -> str:
        if self.status == "completed":
            return self.content
        if self.status == "output_limited":
            raise ModelOutputLimitError(
                max_output_tokens=self.max_output_tokens,
                output_tokens=self.usage.output_tokens if self.usage else None,
                result=self,
            )
        raise GenerationError(self)


class GenerationError(ValueError):
    """A safe typed failure at the shared generation boundary."""

    def __init__(self, result: GenerationResult):
        super().__init__(f"Model generation did not complete: {result.status}")
        self.result = result
        self.diagnostics = result.diagnostics()


class ModelOutputLimitError(GenerationError):
    """Compatibility error for unfinished answers, now shared by providers."""

    def __init__(self, *, max_output_tokens: Optional[int], output_tokens: Optional[int] = None,
                 result: Optional[GenerationResult] = None):
        if result is None:
            result = GenerationResult("", "vertex", "", "output_limited", "MAX_TOKENS", 0.0,
                                      max_output_tokens=max_output_tokens)
        super().__init__(result)
        # Retain the old Vertex message and exact diagnostic shape for existing
        # clients. Full common metadata is available through .result.diagnostics().
        self.args = (("Vertex AI answer did not finish cleanly: MAX_TOKENS"
                      if result.provider == "vertex" and result.finish_reason == "MAX_TOKENS"
                      else "Model answer did not finish cleanly: output limit"),)
        self.diagnostics = {
            "finish_reason": _safe_label(result.finish_reason, limit=64),
            "max_output_tokens": max_output_tokens,
            "output_tokens": _token_count(output_tokens),
        }


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

    def chat_result(
        self, *, model: str, prompt: str, options: Optional[Mapping[str, Any]] = None,
        timeout: int = 120,
    ) -> GenerationResult:
        """Generate content with an explicit termination and execution record."""

    def embed(
        self,
        text_input: str,
        *,
        model: str,
        task_type: str = RETRIEVAL_DOCUMENT,
        timeout: int = 60,
    ) -> List[float]:
        """Embed one text value."""

    def structured_chat(self, *, model: str, prompt: str, schema: dict,
                        max_output_tokens: int, timeout: int) -> str:
        """Generate one bounded JSON response, with no application retries."""

    def structured_chat_result(self, *, model: str, prompt: str, schema: dict,
                               max_output_tokens: int, timeout: int) -> GenerationResult:
        """Generate bounded JSON with the same completion contract as chat."""

    def embed_batch(
        self,
        texts: List[str],
        *,
        model: str,
        task_type: str = RETRIEVAL_DOCUMENT,
        timeout: int = 300,
    ) -> List[List[float]]:
        """Embed a batch of text values."""


def _field(value: Any, name: str) -> Any:
    """Read SDK objects and local mapping fixtures without coercing their data."""
    if isinstance(value, Mapping):
        return value.get(name)
    try:
        return getattr(value, name, None)
    except (AttributeError, ValueError, TypeError):
        return None


def _reason(value: Any) -> Optional[str]:
    candidate = _field(value, "value") if not isinstance(value, str) else value
    return candidate if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else None


def _token_count(value: Any) -> Optional[int]:
    return value if type(value) is int and value >= 0 else None


def _usage(provider: str, response: Any) -> Optional[GenerationUsage]:
    if provider == "ollama":
        source = response
        names = ("prompt_eval_count", "eval_count", "total_token_count")
    else:
        source = _field(response, "usage_metadata")
        names = ("prompt_token_count", "candidates_token_count", "total_token_count")
    counts = tuple(_token_count(_field(source, name)) for name in names)
    return GenerationUsage(*counts) if any(value is not None for value in counts) else None


def _normalize_generation(*, provider: str, model: str, response: Any,
                          elapsed_seconds: float, max_output_tokens: Optional[int]) -> GenerationResult:
    """The sole provider-payload completion decision for both generation modes."""
    status: GenerationStatus = "unknown"
    finish_reason = None
    content = None
    if provider == "ollama" and isinstance(response, Mapping):
        finish_reason = _reason(response.get("done_reason"))
        content = _field(response.get("message"), "content")
        normalized = finish_reason.upper() if finish_reason else None
        if normalized == "STOP":
            # Some old servers omit done; an explicitly unfinished or malformed
            # done flag must not contradict an apparently successful stop.
            done = response.get("done", True)
            status = "completed" if done is True else "unknown"
        elif normalized == "LENGTH":
            status = "output_limited"
        elif normalized in {"REFUSED", "REFUSAL", "SAFETY", "CONTENT_FILTER"}:
            status = "refused"
        elif normalized in {"ERROR", "FAILED"}:
            status = "failed"
        if response.get("error") is not None:
            status = "failed"
    elif provider == "vertex" and (
        isinstance(response, Mapping)
        or any(_field(response, name) is not None for name in ("text", "candidates", "prompt_feedback"))
    ):
        finish_reason = _finish_reason(response)
        content = _field(response, "text")
        normalized = finish_reason.upper() if finish_reason else None
        if normalized == "STOP":
            status = "completed"
        elif normalized == "MAX_TOKENS":
            status = "output_limited"
        elif normalized in {
            "SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
            "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION",
        }:
            status = "refused"
        elif normalized in {"MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS", "NO_IMAGE"}:
            status = "failed"
        blocked_raw = _field(_field(response, "prompt_feedback"), "block_reason")
        blocked = _reason(blocked_raw)
        if blocked and blocked.upper() in {
            "SAFETY", "OTHER", "BLOCKLIST", "PROHIBITED_CONTENT", "IMAGE_SAFETY", "MODEL_ARMOR", "JAILBREAK",
        }:
            status, finish_reason = "refused", finish_reason or blocked
        elif blocked_raw is not None and blocked_raw != "" and blocked != "BLOCKED_REASON_UNSPECIFIED":
            # A new or malformed provider block must not be ignored just
            # because a candidate also advertises STOP.
            status, finish_reason = "unknown", finish_reason or blocked
    else:
        status = "failed"

    if status == "completed" and (not isinstance(content, str) or not content.strip()):
        status = "failed"
    elif content is not None and not isinstance(content, str):
        status = "failed"
    return GenerationResult(
        content=content if isinstance(content, str) else "",
        provider=provider, model=model, status=status, finish_reason=finish_reason,
        elapsed_seconds=elapsed_seconds, usage=_usage(provider, response),
        max_output_tokens=max_output_tokens,
    )


def _generate_result(*, provider: str, model: str, call: Callable[[], Any],
                     max_output_tokens: Optional[int]) -> GenerationResult:
    started = time.monotonic()
    try:
        response = call()
        return _normalize_generation(
            provider=provider, model=model, response=response,
            elapsed_seconds=time.monotonic() - started, max_output_tokens=max_output_tokens,
        )
    except Exception:
        # Raw transport/SDK exceptions can contain request bodies, endpoints and
        # credentials. Neither attach them nor echo them in public diagnostics.
        return GenerationResult(
            content="", provider=provider, model=model, status="failed", finish_reason=None,
            elapsed_seconds=time.monotonic() - started, max_output_tokens=max_output_tokens,
        )


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
        return self.chat_result(model=model, prompt=prompt, options=options, timeout=timeout).require_completed()

    def chat_result(
        self, *, model: str, prompt: str, options: Optional[Mapping[str, Any]] = None,
        timeout: int = 120,
    ) -> GenerationResult:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if options:
            payload["options"] = dict(options)
        return _generate_result(
            provider=self.provider, model=model,
            call=lambda: self._chat_response(payload, timeout),
            max_output_tokens=_token_count((options or {}).get("num_predict")),
        )

    def _chat_response(self, payload: Dict[str, Any], timeout: int) -> Any:
        response = requests.post(self._url("/api/chat"), json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()

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

    def structured_chat(self, *, model: str, prompt: str, schema: dict,
                        max_output_tokens: int, timeout: int) -> str:
        return self.structured_chat_result(
            model=model, prompt=prompt, schema=schema, max_output_tokens=max_output_tokens,
            timeout=timeout,
        ).require_completed()

    def structured_chat_result(self, *, model: str, prompt: str, schema: dict,
                               max_output_tokens: int, timeout: int) -> GenerationResult:
        payload = {
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "stream": False, "format": schema,
            "options": {"temperature": 0, "num_predict": max_output_tokens, "num_ctx": 16384},
        }
        return _generate_result(
            provider=self.provider, model=model,
            call=lambda: self._chat_response(payload, timeout), max_output_tokens=max_output_tokens,
        )

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
    candidates = _field(response, "candidates")
    if not isinstance(candidates, (list, tuple)) or not candidates:
        return None
    return _reason(_field(candidates[0], "finish_reason"))


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
        return self.chat_result(model=model, prompt=prompt, options=options, timeout=timeout).require_completed()

    def chat_result(
        self, *, model: str, prompt: str, options: Optional[Mapping[str, Any]] = None,
        timeout: int = 120,
    ) -> GenerationResult:
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

        return _generate_result(
            provider=self.provider, model=model, max_output_tokens=output_limit,
            call=lambda: self._request(
                "chat",
                lambda: self._client().models.generate_content(
                    model=model, contents=prompt, config=vertex_options,
                ),
            ),
        )

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

    def structured_chat(self, *, model: str, prompt: str, schema: dict,
                        max_output_tokens: int, timeout: int) -> str:
        return self.structured_chat_result(
            model=model, prompt=prompt, schema=schema, max_output_tokens=max_output_tokens,
            timeout=timeout,
        ).require_completed()

    def structured_chat_result(self, *, model: str, prompt: str, schema: dict,
                               max_output_tokens: int, timeout: int) -> GenerationResult:
        # Use an independent client so the answer runtime's 120s timeout and
        # transient retry loop cannot multiply the planner's bounded call.
        planner = VertexRuntime(self.project, self.location, self.embedding_dim,
                                max_attempts=1, request_timeout_seconds=timeout,
                                client=self.client)
        return _generate_result(
            provider=self.provider, model=model, max_output_tokens=max_output_tokens,
            call=lambda: planner._client().models.generate_content(
                model=model, contents=prompt, config={
                    "response_mime_type": "application/json", "response_json_schema": schema,
                    "temperature": 0, "max_output_tokens": max_output_tokens,
                    "thinking_config": {"thinking_budget": 0, "include_thoughts": False},
                },
            ),
        )

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
