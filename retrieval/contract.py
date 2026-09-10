"""Shared request contract for local and PostgreSQL hybrid retrieval."""
from __future__ import annotations

import math


class RetrievalBackendError(RuntimeError):
    """Every enabled retrieval branch failed operationally."""


def normalized_weights(vector_weight: float, text_weight: float) -> tuple[float, float]:
    """Return one normalized, non-empty weighting pair."""
    values = (float(vector_weight), float(text_weight))
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("Retrieval weights must be finite and non-negative")
    total = sum(values)
    if total == 0:
        raise ValueError("At least one retrieval weight must be greater than zero")
    return values[0] / total, values[1] / total


def validate_rrf_k(rrf_k: int) -> int:
    value = int(rrf_k)
    if value < 1 or value > 200:
        raise ValueError("rrf_k must be between 1 and 200")
    return value
