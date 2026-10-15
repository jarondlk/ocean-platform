"""Explicitly completed model results for consumer tests with synthetic content.

This adapter is deliberately test-only: choosing this fixture declares that its
successful callback represents a provider-confirmed stop. Production runtimes
must inspect the provider response before declaring completion.
"""
from collections.abc import Callable


class CompletedGenerationRuntime:
    provider = "test-fixture"

    def __init__(self, *, chat: Callable | None = None, structured_chat: Callable | None = None):
        self._chat_callback = chat
        self._structured_chat_callback = structured_chat

    def chat(self, **kwargs):
        if self._chat_callback is None:
            raise AssertionError("No completed chat callback was configured")
        return self._chat_callback(**kwargs)

    def structured_chat(self, **kwargs):
        if self._structured_chat_callback is None:
            raise AssertionError("No completed structured chat callback was configured")
        return self._structured_chat_callback(**kwargs)

    def _completed(self, content, kwargs):
        from model_runtime import GenerationResult

        assert isinstance(content, str), "The completed fixture must supply text"
        return GenerationResult(
            content=content,
            provider=self.provider,
            model=kwargs.get("model", "synthetic-model"),
            status="completed",
            finish_reason="stop",
            elapsed_seconds=0.0,
            max_output_tokens=kwargs.get("max_output_tokens"),
        )

    def chat_result(self, **kwargs):
        return self._completed(self.chat(**kwargs), kwargs)

    def structured_chat_result(self, **kwargs):
        return self._completed(self.structured_chat(**kwargs), kwargs)
