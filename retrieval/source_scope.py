"""Versioned, source-owned evidence scope shared by API, SQL and local search."""
from __future__ import annotations

import re
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator, field_validator

from schema.time_range import matches_time, sql_time_conditions, time_bounds

FAMILIES = ('ctd', 'metagenome', 'remote_sensing', 'edna_metabarcoding')
ALIASES = {**{s: s for s in FAMILIES}, 'meta': 'metagenome', 'taxonomy': 'metagenome',
           'taxa': 'metagenome', 'remote': 'remote_sensing', 'satellite': 'remote_sensing',
           'sst': 'remote_sensing', 'satellite_sst': 'remote_sensing',
           **{s: 'edna_metabarcoding' for s in ('edna', 'environmental_dna', 'metabarcoding', 'mifish', 'anemone')}}
EDNA_FIELDS = ('provider', 'provider_project_id', 'provider_run_id', 'assignment_method', 'taxon', 'sample_kind', 'is_control')
LEGACY_FIELDS = ('source_type', 'sample_id', 'station', 'bay', 'time_from', 'time_to',
                 *EDNA_FIELDS, 'lat_min', 'lat_max', 'lon_min', 'lon_max', 'analysis_id')


class ScopeModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class Dates(ScopeModel):
    time_from: str | None = Field(default=None, min_length=1, max_length=64)
    time_to: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode='after')
    def dates(self):
        time_bounds(self.time_from, self.time_to)
        return self


class Coordinates(Dates):
    lat_min: float | None = Field(default=None, ge=-90, le=90)
    lat_max: float | None = Field(default=None, ge=-90, le=90)
    lon_min: float | None = Field(default=None, ge=-180, le=180)
    lon_max: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode='after')
    def coordinates(self):
        for axis in ('lat', 'lon'):
            lo, hi = getattr(self, axis+'_min'), getattr(self, axis+'_max')
            if lo is not None and hi is not None and lo > hi:
                raise ValueError(f'{axis}_min must not exceed {axis}_max')
        return self


class SampleFilters(Dates):
    bay: Literal['O', 'I', 'M'] | None = None
    station: str | None = Field(default=None, min_length=1, max_length=64)
    sample_id: str | None = Field(default=None, min_length=1, max_length=200)


class EdnaFilters(Coordinates):
    sample_id: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    provider_project_id: str | None = Field(default=None, min_length=1, max_length=128)
    provider_run_id: str | None = Field(default=None, min_length=1, max_length=128)
    assignment_method: Literal['qcauto_target', 'qcauto_95pct_3nn_target'] | None = None
    taxon: str | None = Field(default=None, min_length=1, max_length=200)
    sample_kind: Literal['environmental', 'negative_control', 'positive_control', 'mock_community', 'unknown'] | None = None
    is_control: StrictBool | None = None

    @model_validator(mode='after')
    def classification(self):
        if (self.sample_kind == 'environmental' and self.is_control is True
                or self.sample_kind in ('negative_control', 'positive_control', 'mock_community') and self.is_control is False):
            raise ValueError('Sample kind and control status conflict')
        return self


class SampleSelection(ScopeModel):
    enabled: StrictBool
    filters: SampleFilters


class SatelliteFilters(Coordinates):
    dataset_id: str | None = Field(default=None, min_length=1, max_length=128)


class SatelliteSelection(ScopeModel):
    enabled: StrictBool
    filters: SatelliteFilters


class EdnaSelection(ScopeModel):
    enabled: StrictBool
    filters: EdnaFilters
    analysis_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class SourceSelections(ScopeModel):
    ctd: SampleSelection
    metagenome: SampleSelection
    remote_sensing: SatelliteSelection
    edna_metabarcoding: EdnaSelection


class EvidenceScope(ScopeModel):
    version: Literal[1]
    sources: SourceSelections

    @field_validator('version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int:
            raise ValueError('Scope version must be an integer')
        return value

    def canonical(self):
        return self.model_dump(exclude_none=True)


def enabled_sources(scope):
    return [s for s in FAMILIES if scope['sources'][s]['enabled']]


def legacy_scope(request):
    source = ALIASES.get((request.get('source_type') or '').strip().lower())
    if not source and any(request.get(k) is not None for k in (*EDNA_FIELDS, 'analysis_id')):
        source = 'edna_metabarcoding'
    return {'version': 1, 'sources': {family: {
        'enabled': not source or source == family,
        'filters': {k: v for k, v in request.items() if k in LEGACY_FIELDS and k not in ('source_type', 'analysis_id') and v is not None},
        **({'analysis_id': request['analysis_id']} if family == 'edna_metabarcoding' and request.get('analysis_id') else {}),
    } for family in FAMILIES}}


def document_matches(document, scope):
    family = document.get('source_type')
    selection = scope['sources'].get(family)
    if not selection or not selection['enabled']:
        return False
    values = {**(document.get('metadata') or {}), **document}
    if family == 'remote_sensing':
        values.setdefault('dataset_id', 'current-sst')
    filters = selection['filters']
    if not matches_time(values.get('time'), filters.get('time_from'), filters.get('time_to')):
        return False
    for key, expected in filters.items():
        if expected is None or key in ('time_from', 'time_to'):
            continue
        if key == 'taxon':
            if expected.casefold() not in {str(t).casefold() for t in values.get('taxon_terms', [])}:
                return False
        elif key in ('lat_min', 'lat_max', 'lon_min', 'lon_max'):
            actual = values.get(key[:3])
            try:
                if actual is None or not math.isfinite(float(actual)) or (float(actual) < expected if key.endswith('min') else float(actual) > expected):
                    return False
            except (ValueError, TypeError):
                return False
        elif values.get(key) != expected:
            return False
    return True


def scope_sql(scope, *, alias='', sample_ids=None, assignment_methods=None):
    """Compile only trusted columns/operators. Every request value is bound."""
    if alias and not re.fullmatch(r'[a-z_]+', alias):
        raise ValueError('Invalid SQL alias')
    prefix = alias+'.' if alias else ''
    clauses, params = [], {}
    for i, family in enumerate(enabled_sources(scope)):
        stem = f'scope_{i}_'
        filters = scope['sources'][family]['filters']
        branch = [f'{prefix}source_type = :{stem}family']
        params[stem+'family'] = family
        times, values = sql_time_conditions(prefix+'time', filters.get('time_from'), filters.get('time_to'))
        for key, value in values.items():
            times = [c.replace(':'+key, ':'+stem+key) for c in times]
            params[stem+key] = value
        branch.extend(times)
        for key, value in filters.items():
            if value is None or key in ('time_from', 'time_to'):
                continue
            name = stem+key
            params[name] = value
            if key == 'dataset_id' and family == 'remote_sensing':
                branch.append(f"COALESCE(NULLIF(CAST({prefix}metadata_json AS jsonb)->>'dataset_id', ''), 'current-sst') = :{name}")
            elif key == 'taxon':
                table = alias or 'retrieval_document'
                ranks = ('assigned_taxon_name', 'superkingdom', 'kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species', 'subspecies')
                terms = ' OR '.join(f'lower(detection."{rank}") = lower(:{name})' for rank in ranks)
                branch.append(f'EXISTS (SELECT 1 FROM edna_detection detection WHERE detection.assay_id = {table}.assay_id AND detection.assignment_method = {table}.assignment_method AND detection.active IS TRUE AND ({terms}))')
            elif key in ('lat_min', 'lat_max', 'lon_min', 'lon_max'):
                branch.append(f'{prefix}{key[:3]} {">=" if key.endswith("min") else "<="} :{name}')
            elif key == 'is_control':
                branch.append(f'{prefix}is_control IS NOT DISTINCT FROM :{name}')
            elif key in LEGACY_FIELDS and key not in ('source_type', 'analysis_id'):
                branch.append(f'{prefix}{key} = :{name}')
            else:
                raise ValueError('Unsupported source filter')
        if family == 'edna_metabarcoding':
            for column, members in (('sample_id', sample_ids), ('assignment_method', assignment_methods)):
                if members is not None:
                    name = stem+'allowed_'+column
                    params[name] = sorted(set(members))
                    branch.append(f'{prefix}{column} = ANY(:{name})')
        clauses.append('('+' AND '.join(branch)+')')
    return '('+' OR '.join(clauses)+')' if clauses else 'FALSE', params
