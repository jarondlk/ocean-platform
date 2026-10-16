"""C14 public requests exclude server-owned authorization context."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from retrieval.source_scope import EvidenceScope
from schema.context_catalogue import (
    CatalogueFilters, ContractModel, Identifier, NonnegativeInt, Ordering,
    PageLimit, SCHEMA_VERSION, _finite_json, _strict_scope,
)


class CatalogueRequest(ContractModel):
    schema_version: Literal["context-catalogue-v1"] = SCHEMA_VERSION
    snapshot_id: Identifier
    scope: EvidenceScope

    @field_validator("scope", mode="before")
    @classmethod
    def strict_scope(cls, value):
        return _strict_scope(value)


class CatalogueOverviewRequest(CatalogueRequest):
    pass


class CatalogueListRequest(CatalogueRequest):
    parent_id: Identifier | None = None
    filters: CatalogueFilters = Field(default_factory=CatalogueFilters)
    ordering: list[Ordering] = Field(default_factory=lambda: [Ordering(field="id")], min_length=1, max_length=2)
    limit: PageLimit = 100
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def ordering_contract(self):
        if self.ordering[-1].field != "id" or len({o.field for o in self.ordering}) != len(self.ordering):
            raise ValueError("Ordering requires one final canonical ID tie-breaker")
        return self


class CatalogueOpenRequest(CatalogueRequest):
    object_id: Identifier
    include_details: bool = False


class CatalogueCoverageRequest(CatalogueRequest):
    object_id: Identifier
    parameters: dict = Field(default_factory=dict)
    limit: PageLimit = 100
    offset: NonnegativeInt = 0

    @field_validator("parameters", mode="before")
    @classmethod
    def finite_parameters(cls, value):
        return _finite_json(value)


class CatalogueQueryRequest(CatalogueRequest):
    operation_id: Literal["c13.table", "c13.inventory", "c13.coverage", "c13.quality", "c13.operation"]
    operation_version: Literal["c13-v1"]
    input_ids: list[Identifier] = Field(min_length=1, max_length=1)
    parameters: dict = Field(default_factory=dict)

    @field_validator("parameters", mode="before")
    @classmethod
    def finite_parameters(cls, value):
        return _finite_json(value)


class CatalogueRelationshipsRequest(CatalogueListRequest):
    object_id: Identifier | None = None

    @model_validator(mode="after")
    def one_parent(self):
        if self.object_id is not None and self.parent_id is not None:
            raise ValueError("Relationships select one object or parent")
        return self


class PublishedAnalysisRequest(CatalogueRequest):
    analysis_id: Identifier
    table: Identifier | None = None
    workflow_kind: Identifier | None = None
    protocol_id: Identifier | None = None
    limit: PageLimit = 100
    offset: NonnegativeInt = 0


REQUEST_MODELS = {
    "catalogue.overview": CatalogueOverviewRequest,
    "catalogue.list": CatalogueListRequest,
    "catalogue.open": CatalogueOpenRequest,
    "catalogue.coverage": CatalogueCoverageRequest,
    "catalogue.query": CatalogueQueryRequest,
    "catalogue.relationships": CatalogueRelationshipsRequest,
    "analysis.get_published": PublishedAnalysisRequest,
}
