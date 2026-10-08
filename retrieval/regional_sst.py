"""Source-local BM25 retrieval of immutable published regional SST.

The historical branch shares the existing remote-sensing evidence budget and
honours every source filter. It does not require a provider request or embedding.
"""
from collections import deque
from functools import lru_cache

from ingestion.regional_publication import current_publication, documents, DATASET, NOTES
from ingestion.immutable_bundle import digest
from retrieval.local_retriever import BM25
from retrieval.source_scope import document_matches
from schema.time_range import matches_time


@lru_cache(maxsize=4)
def _index(identity):
    publication = current_publication()
    if publication is None or publication['publication_id'] != identity:
        raise ValueError('Regional publication changed while indexing')
    rows = documents(publication)
    scorer = BM25()
    scorer.fit([row['text'] + ' ' + row['title'] for row in rows])
    return rows, scorer


def dataset_choices(scope, search=''):
    publication = current_publication()
    if not publication or search.casefold() not in DATASET.casefold():
        return []
    return [DATASET] if any(document_matches(row, scope) for row in _index(publication['publication_id'])[0]) else []


def regional_search(query, scope, k):
    publication = current_publication()
    if publication is None or not scope['sources']['remote_sensing']['enabled']:
        return [], None
    rows, scorer = _index(publication['publication_id'])
    scores = scorer.score(query)
    eligible = [(row, score) for row, score in zip(rows, scores) if document_matches(row, scope)]
    eligible.sort(key=lambda item: (-item[1], item[0]['time']))
    selected = [{**row, 'score': score, 'rank_sources': {'regional_bm25': rank}} for rank, (row, score) in enumerate(eligible[:k], 1)]
    if eligible:
        filters = scope['sources']['remote_sensing']['filters']
        days = sorted(row['time'][:10] for row, _ in eligible)
        gaps = [gap for gap in publication['period']['final_series_gaps']
                if matches_time(gap['day'], filters.get('time_from'), filters.get('time_to'))]
        eligible_days = set(days)
        values = [r['sst_celsius'] for r in publication['period']['observations']
                  if r['time_utc'][:10] in eligible_days]
        summary = {'doc_id': 'mur_coverage_' + digest([publication['publication_id'], filters]),
                   'source_type': 'remote_sensing', 'time': eligible[0][0]['time'],
                   'title': 'Published Miyagi historical SST coverage under the selected filters',
                   'metadata': {**eligible[0][0]['metadata'], 'coverage_summary': True,
                                'observed_start': days[0], 'observed_end': days[-1], 'days': len(days), 'final_series_gaps': gaps},
                   'text': f"Miyagi historical MUR SST coverage under these filters: {len(days)} supported final 04.1 days, {days[0]} through {days[-1]}. Mean of supported regional daily SST: {sum(values)/len(values):.6g}°C; minimum daily regional mean {min(values):.6g}°C; maximum daily regional mean {max(values):.6g}°C. Final-series gaps: " + ', '.join(g['day'] + ' (' + g['reason'] + ')' for g in gaps) + '. ' + ' '.join(NOTES),
                   'score': 1.0, 'rank_sources': {'regional_coverage': 1}}
        selected = [summary, *selected][:k]
    elif scope['sources']['remote_sensing']['enabled']:
        filters = scope['sources']['remote_sensing']['filters']
        gaps = [g for g in publication['period']['final_series_gaps']
                if matches_time(g['day'], filters.get('time_from'), filters.get('time_to'))]
        if gaps:
            gap_document = {'doc_id': 'mur_gaps_' + digest([publication['publication_id'], filters]),
                            'source_type': 'remote_sensing', 'time': gaps[0]['day'] + 'T09:00:00+00:00',
                            'title': 'Published historical SST final-series gaps',
                            'metadata': {'dataset_id': DATASET, 'publication_id': publication['publication_id'],
                                         'coverage_summary': True, 'days': 0, 'final_series_gaps': gaps,
                                         'observed_start': gaps[0]['day'], 'observed_end': gaps[-1]['day']},
                            'text': 'No final MUR 04.1 regional SST observation is published for these requested dates: '
                                    + ', '.join(g['day'] + ' (' + g['reason'] + ')' for g in gaps)
                                    + '. These are retained coverage-gap receipts, not SST measurements. Interim 04.1nrt evidence is excluded; no final value is substituted.',
                            'score': 1.0, 'rank_sources': {'regional_gap_receipt': 1}}
            if document_matches(gap_document, scope):
                selected = [gap_document]
    return selected, publication['publication_id']


def supplement_sst(query, existing, scope, k):
    historical, identity = regional_search(query, scope, k)
    if identity is None:
        return existing, {}
    # Independent ranking streams interleave; their raw scores are not comparable.
    streams = [deque(historical), deque(existing)]
    merged, seen = [], set()
    while any(streams) and len(merged) < k:
        for stream in streams:
            if stream and len(merged) < k:
                row = stream.popleft()
                if row['doc_id'] not in seen:
                    seen.add(row['doc_id'])
                    merged.append(row)
    return merged, {'regional_publication_id': identity, 'regional_candidate_count': len(historical),
                    'regional_backend': 'immutable_regional_bm25', 'sst_merge_strategy': 'interleaved_ranked_streams_v1'}
