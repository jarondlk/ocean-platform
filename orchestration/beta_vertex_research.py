"""Beta-only Gemini structured generation with bounded calls and no API key.

The shared legacy runtime is unchanged. Gemini 3.8 uses thinking levels rather
than the Gemini 2.x thinking-budget setting used by the older adapter.
"""
from copy import deepcopy
import math

from model_runtime import VertexRuntime, _generate_result


def _gemini_response_schema(schema):
    """Adapt provider grammar only; replay and host validation stay strict.

    Nested bounded arrays in the C21 selection schema exceed Gemini's accepted
    grammar (actual original400/unbounded200 synthetic probe). The provider
    output token cap still bounds generation; host parsing enforces every array
    limit before a selection can render an answer.
    """
    wire = deepcopy(schema)

    def visit(node):
        if isinstance(node, bool):
            return  # Boolean schemas are not boolean enum values.
        if not isinstance(node, dict):
            raise ValueError("Invalid beta response schema")
        if node.get("type") == "array":
            node.pop("minItems", None)
            node.pop("maxItems", None)
        if "const" in node:
            value = node.pop("const")
            if type(value) not in (str, int, float) or (type(value) is float and not math.isfinite(value)):
                raise ValueError("Unsupported beta schema constant")
            if "enum" in node:
                def equal(item):
                    return item == value and (type(item) is type(value) or type(item) in (int, float) and type(value) in (int, float))
                if not isinstance(node["enum"], list) or not any(equal(item) for item in node["enum"]):
                    raise ValueError("Conflicting beta schema constant and enum")
            node["enum"] = [value]
        # These contain schemas; annotations/defaults/examples/enum values do not.
        for key in ("$defs", "definitions", "properties", "patternProperties", "dependentSchemas"):
            if key in node:
                if not isinstance(node[key], dict):
                    raise ValueError("Invalid beta response schema")
                for child in node[key].values():
                    visit(child)
        for key in ("items", "additionalProperties", "unevaluatedProperties", "propertyNames", "contains",
                    "unevaluatedItems", "additionalItems", "not", "if", "then", "else", "contentSchema"):
            if key in node:
                if key == "items" and isinstance(node[key], list):
                    for child in node[key]:
                        visit(child)
                else:
                    visit(node[key])
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            if key in node:
                if not isinstance(node[key], list):
                    raise ValueError("Invalid beta response schema")
                for child in node[key]:
                    visit(child)

    visit(wire)
    return wire


class BetaVertexResearchRuntime(VertexRuntime):
    def structured_chat_result(self, *, model, prompt, schema, max_output_tokens, timeout):
        if (self.project != "ocean-v1-beta-20261101" or self.location != "global"
                or model != "gemini-3.8-flash" or self.max_attempts != 1
                or type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0
                or type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 4096):
            raise ValueError("Explicit bounded beta Gemini generation required")
        wire_schema = _gemini_response_schema(schema)
        planner = VertexRuntime(self.project, self.location, self.embedding_dim,
            max_attempts=1, request_timeout_seconds=min(timeout, 45), client=self.client)
        client = planner._client()
        try:
            return _generate_result(provider="vertex", model=model, max_output_tokens=max_output_tokens,
                call=lambda: client.models.generate_content(model=model, contents=prompt, config={
                    "response_mime_type": "application/json", "response_json_schema": wire_schema,
                    "max_output_tokens": max_output_tokens,
                    "thinking_config": {"thinking_level": "LOW", "include_thoughts": False},
                }))
        finally:
            if self.client is None:
                client.close()
