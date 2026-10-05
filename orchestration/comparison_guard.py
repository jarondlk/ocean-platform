"""Narrow, deterministic guard for explicit multi-source comparisons.

Retrieving both sides is not a scientific matching calculation. Published
research routes execute before this legacy RAG guard.
"""
from __future__ import annotations

import re

from retrieval.source_scope import enabled_sources

LABELS = {'ctd': 'CTD', 'metagenome': 'Metagenome',
          'remote_sensing': 'SST', 'edna_metabarcoding': 'ANEMONE eDNA'}
MENTIONS = {
    'ctd': r'\bctd\b|water[- ]column profiles?',
    'metagenome': r'\bmetagenom(?:e|es|ic|ics)\b',
    'remote_sensing': r'\bsst\b|sea[- ]surface temperature|\bsatellite\b',
    'edna_metabarcoding': r'\banemone\b|\bedna\b|\bmifish\b|\bmetabarcoding\b',
}
OVERLAP = r'\boverlap\w*\b|\bcoincid\w*\b|\bco[- ]?occurr\w*\b|\bmatch(?:es|ed|ing)?\b|\balign\w*\b|\bcorrespond\w*\b'
COMPARISON = r'\bcompar\w*\b|\bversus\b|\bvs\.?\b|\brelationship\w*\b|\bcorrelat\w*\b|\bdiffer\w*\b|\bwarmer\b|\bcooler\b'
LIMITATIONS = {
    'backend_failed': 'source search failed',
    'publication_unavailable': 'publication is unavailable',
    'merge_budget_omitted': 'total evidence budget excluded this source',
    'prompt_budget_omitted': 'answer context budget excluded this source',
    'prompt_evidence_omitted': 'evidence was excluded during context validation',
    'empty_under_scope': 'no evidence was retrieved under the selected filters',
}


def comparison_requirement(query):
    families = [f for f, pattern in MENTIONS.items() if re.search(pattern, query, re.I)]
    if len(families) < 2:
        return None
    if re.search(OVERLAP, query, re.I):
        return {'kind': 'overlap', 'sources': families}
    if re.search(COMPARISON, query, re.I):
        return {'kind': 'comparison', 'sources': families}
    return None


def comparison_guard(query, scope, diagnostics):
    requirement = comparison_requirement(query)
    if requirement is None:
        return None
    required = requirement['sources']
    diagnostics['comparison_requirement'] = requirement
    selected = enabled_sources(scope)
    disabled = [f for f in required if f not in selected]
    supplied = diagnostics.get('supplied_source_types', [])
    missing = [f for f in required if f not in supplied]
    if disabled:
        diagnostics['comparison_status'] = 'source_disabled'
        return 'source_disabled', 'Enable ' + ', '.join(LABELS[f] for f in disabled) + ' to request this comparison. The model was not run.'
    if missing:
        diagnostics['comparison_status'] = 'incomplete_source_coverage'
        diagnostics['coverage_status'] = 'partial'
        diagnostics['missing_required_source_types'] = missing
        states = diagnostics.get('per_source', {})
        details = '; '.join(f"{LABELS[f]}: {LIMITATIONS.get(states.get(f, {}).get('state'), 'evidence not supplied')}" for f in missing)
        return 'incomplete_source_coverage', (
            'The supplied evidence does not establish the requested cross-source comparison. '
            f'Required evidence is missing from the final context ({details}). '
            'This does not establish that source records or overlap are absent. '
            'Review the source filters, publication readiness and evidence budget. The model was not run.')
    if requirement['kind'] == 'overlap':
        diagnostics['comparison_status'] = 'overlap_unverified'
        diagnostics['coverage_status'] = 'unverified'
        return 'overlap_unverified', (
            'The supplied evidence does not establish where these sampling events overlap with other observations. '
            'Records from both sources were supplied, but retrieval is not a verified date/location match. '
            'Use an approved, published matching result with its scope and provenance; '
            'no overlap or non-overlap was inferred. The model was not run.')
    diagnostics['comparison_status'] = 'evidence_supplied'
    return None
