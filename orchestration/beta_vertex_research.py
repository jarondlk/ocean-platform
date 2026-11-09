"""Beta-only Gemini structured generation with bounded calls and no API key.

The shared legacy runtime is unchanged. Gemini 3.8 uses thinking levels rather
than the Gemini 2.x thinking-budget setting used by the older adapter.
"""
import math

from model_runtime import VertexRuntime, _generate_result


class BetaVertexResearchRuntime(VertexRuntime):
    def structured_chat_result(self, *, model, prompt, schema, max_output_tokens, timeout):
        if (self.project != "ocean-v1-beta-20261101" or self.location != "global"
                or model != "gemini-3.8-flash" or self.max_attempts != 1
                or type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0
                or type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 4096):
            raise ValueError("Explicit bounded beta Gemini generation required")
        planner = VertexRuntime(self.project, self.location, self.embedding_dim,
            max_attempts=1, request_timeout_seconds=min(timeout, 45), client=self.client)
        client = planner._client()
        try:
            return _generate_result(provider="vertex", model=model, max_output_tokens=max_output_tokens,
                call=lambda: client.models.generate_content(model=model, contents=prompt, config={
                    "response_mime_type": "application/json", "response_json_schema": schema,
                    "max_output_tokens": max_output_tokens,
                    "thinking_config": {"thinking_level": "LOW", "include_thoughts": False},
                }))
        finally:
            if self.client is None:
                client.close()
