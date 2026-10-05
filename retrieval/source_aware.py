"""Bounded source-local ranking, fair selection and auditable coverage."""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from time import perf_counter

from retrieval.contract import RetrievalBackendError
from retrieval.source_scope import FAMILIES, document_matches, enabled_sources

STRATEGY = 'per_source_round_robin_v1'


def fair_order(rows):
    """Interleave ranked families without comparing their raw RRF scores."""
    groups = {family: deque() for family in FAMILIES}
    for row in rows:
        groups.setdefault(row.get('source_type', 'unknown'), deque()).append(row)
    while any(groups.values()):
        for group in groups.values():
            if group:
                yield group.popleft()


def scoped_retrieve(query, *, scope, k, backend, search, options):
    """Search every enabled family, then cap the total primary count at k."""
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 25:
        raise ValueError('Total primary evidence budget must be between 1 and 25')
    selected = enabled_sources(scope)
    per_source = {f: {'enabled': f in selected, 'attempted': False,
        'state': 'disabled' if f not in selected else 'not_attempted',
        'backend': backend, 'filters': deepcopy(scope['sources'][f]['filters']),
        'candidate_count': 0, 'merged_count': 0, 'linked_count': 0,
        'prompt_count': None, 'failed_branches': [], 'availability': 'unknown'} for f in FAMILIES}
    started_request = perf_counter()
    candidates = []
    failures = 0
    for family in selected:
        isolated = deepcopy(scope)
        for f in FAMILIES:
            isolated['sources'][f]['enabled'] = f == family
        diagnostic = per_source[family]
        diagnostic['attempted'] = True
        started = perf_counter()
        branches = {}
        try:
            rows = search(query, k=k, evidence_scope=isolated,
                          branch_diagnostics=branches, **options)
        except RetrievalBackendError:
            failures += 1
            diagnostic['state'] = 'backend_failed'
            diagnostic['error_code'] = 'retrieval_backends_failed'
            rows = []
        finally:
            diagnostic['elapsed_ms'] = round((perf_counter() - started) * 1000, 3)
            diagnostic['failed_branches'] = branches.get('failed_branches', [])
        # Defense in depth: a broken backend cannot broaden family or filters.
        unique = {}
        for row in rows:
            if row.get('doc_id') and str(row.get('text') or '').strip() and document_matches(row, isolated):
                unique.setdefault(str(row['doc_id']), row)
        eligible = list(unique.values())[:k]
        diagnostic['candidate_count'] = len(eligible)
        if diagnostic['state'] != 'backend_failed':
            diagnostic['state'] = 'retrieved' if eligible else 'empty_under_scope'
        candidates.extend({**row, 'source_local_rank': rank} for rank, row in enumerate(eligible, 1))
    if selected and failures == len(selected):
        raise RetrievalBackendError('Every selected source failed retrieval')
    primary, seen = [], set()
    for row in fair_order(candidates):
        identity = str(row['doc_id'])
        if identity in seen:
            continue
        if len(primary) == k:
            break
        seen.add(identity)
        primary.append(row)
        per_source[row['source_type']]['merged_count'] += 1
    for diagnostic in per_source.values():
        if diagnostic['candidate_count'] and not diagnostic['merged_count']:
            diagnostic['state'] = 'merge_budget_omitted'
    return primary, {'diagnostic_version': 1, 'strategy': STRATEGY, 'per_source': per_source,
        'primary_budget': k, 'per_source_candidate_limit': k,
        'retrieval_elapsed_ms': round((perf_counter() - started_request) * 1000, 3),
        'candidate_count_is_corpus_count': False,
        'coverage_status': 'complete' if selected and all(per_source[f]['merged_count'] for f in selected) else 'partial'}


def reconcile_coverage(diagnostics, primary, linked, context, *, scope):
    """Reconcile against exact final prompt membership, never pre-packing counts."""
    result = deepcopy(diagnostics)
    result.setdefault('diagnostic_version', 1)
    per_source = result.setdefault('per_source', {})
    selected = enabled_sources(scope)
    primary_counts = Counter(row.get('source_type') for row in primary)
    linked_counts = Counter(row.get('source_type') for row in linked)
    derived_counts = Counter()
    for role in ('analysis', 'reliability'):
        for row in context.get(role, []):
            for family in set(row.get('covered_source_types', [])):
                derived_counts[family] += 1
    for family in FAMILIES:
        item = per_source.setdefault(family, {'enabled': family in selected,
            'attempted': None, 'filters': deepcopy(scope['sources'][family]['filters']),
            'availability': 'unknown', 'state': 'legacy_unknown' if family in selected else 'disabled'})
        item['prompt_primary_count'] = primary_counts[family]
        item['prompt_linked_count'] = linked_counts[family]
        item['prompt_context_count'] = derived_counts[family]
        item['prompt_count'] = primary_counts[family] + linked_counts[family] + derived_counts[family]
        item['prompt_omissions'] = [row for row in context.get('omitted', []) if row.get('source_type') == family]
        if family in selected and item['prompt_count'] == 0 and item.get('merged_count', 0) + item.get('linked_count', 0) > 0:
            item['state'] = 'prompt_budget_omitted' if any(r.get('reason') == 'prompt_budget' for r in item['prompt_omissions']) else 'prompt_evidence_omitted'
    supplied = [f for f in selected if per_source[f]['prompt_count'] > 0]
    result['supplied_source_types'] = supplied
    result['missing_enabled_source_types'] = [f for f in selected if f not in supplied]
    required = result.get('expected_source_types', [])
    result['missing_source_types'] = [f for f in required if f not in supplied]
    result['source_coverage_ratio'] = round((len(required) - len(result['missing_source_types'])) / len(required), 3) if required else None
    result['coverage_status'] = 'complete' if selected and len(supplied) == len(selected) else 'partial'
    result['coverage_stage'] = 'final_prompt'
    return result
