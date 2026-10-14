"""Explicit provenance for query vectors; dimensionality alone is not identity."""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Iterable


@dataclass(frozen=True)
class EmbeddingIdentity:
    provider: str
    model: str
    dimension: int

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("Query embedding provider is required")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Query embedding model is required")
        if type(self.dimension) is not int or self.dimension <= 0:
            raise ValueError("Query embedding dimension must be a positive integer")


class IdentifiedEmbedding(list[float]):
    """A list-compatible vector carrying its explicit producing identity."""

    def __init__(self, values: Iterable[float], identity: EmbeddingIdentity):
        super().__init__(values)
        self.identity = identity
        validate_embedding(self)


def validate_embedding(value: object) -> IdentifiedEmbedding:
    """Fail closed for arbitrary callbacks that cannot attest vector identity."""
    if not isinstance(value, IdentifiedEmbedding) or not isinstance(value.identity, EmbeddingIdentity):
        raise ValueError("Query embedding requires an explicit provider/model/dimension identity")
    if len(value) != value.identity.dimension:
        raise ValueError("Query embedding dimension does not match its identity")
    if any(isinstance(item, bool) or not isinstance(item, Real) or not math.isfinite(item) for item in value):
        raise ValueError("Query embedding values must be finite numbers")
    return value


def embedding_parameters(value: object) -> dict:
    embedding = validate_embedding(value)
    return {
        "emb": "[" + ",".join(str(float(item)) for item in embedding) + "]",
        "embedding_provider": embedding.identity.provider,
        "embedding_model": embedding.identity.model,
        "embedding_dim": embedding.identity.dimension,
    }


EMBEDDING_IDENTITY_PREDICATE = (
    "embedding_provider = :embedding_provider "
    "AND embedding_model = :embedding_model "
    "AND embedding_dim = :embedding_dim"
)
