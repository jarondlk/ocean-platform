"""Typed proposals; only backend-validated settings reach evidence execution."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orchestration.research_intents import ResearchIntent
from retrieval.source_scope import EvidenceScope

SourceFamily = Literal['ctd', 'metagenome', 'remote_sensing', 'edna_metabarcoding']


class QuestionConstraint(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    family: SourceFamily
    field: str = Field(min_length=1, max_length=64)
    quote: str = Field(min_length=1, max_length=200)


class SettingsProposal(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: Literal[1] = 1
    status: Literal['ready', 'clarification']
    explanation: str = Field(min_length=1, max_length=1000)
    clarification: str | None = Field(default=None, max_length=1000)
    evidence_scope: EvidenceScope
    preset: Literal['measurement', 'synthesis', 'comparison'] = 'measurement'
    route: Literal['rag', 'published_exact', 'published_synthesis', 'sst_coverage'] = 'rag'
    research_intent: ResearchIntent | None = None
    constraints: list[QuestionConstraint] = Field(default_factory=list, max_length=32)
    unresolved_constraints: list[str] = Field(default_factory=list, max_length=12)
    analysis_document_ids: list[str] = Field(default_factory=list, max_length=10)
    reliability_document_ids: list[str] = Field(default_factory=list, max_length=10)
    required_sources: list[SourceFamily] = Field(default_factory=list, max_length=4)
    comparison_kind: Literal['none', 'comparison', 'overlap'] = 'none'

    @model_validator(mode='after')
    def readiness(self):
        if self.status == 'clarification' and not self.clarification:
            raise ValueError('Clarification text is required')
        if self.status == 'ready' and (self.clarification or self.unresolved_constraints):
            raise ValueError('Unresolved constraints cannot be applied')
        if len(set(self.required_sources)) != len(self.required_sources):
            raise ValueError('Duplicate source requirements')
        return self
