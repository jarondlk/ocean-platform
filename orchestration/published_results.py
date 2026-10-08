"""Verified result consumers shared by exact answers and planned synthesis."""
import json
from datetime import date, timedelta

from ingestion.immutable_bundle import digest
from orchestration.prompt_safety import MAX_PROMPT_FIELD_CHARS
from orchestration.research_intents import select_research, abstain


def planned_research(request, bundle):
    from ingestion.edna_analysis_bundle import analysis_status
    from ingestion.provenance_snapshot import SnapshotError
    try:
        if not bundle or analysis_status(bundle) != 'current' or request.research_intent is None:
            return abstain('aggregate_unavailable', 'The planned publication is no longer current. Select a current analysis; no scientific answer was generated.')
        return select_research(bundle, request.evidence_scope.canonical(), request.query, request.research_intent)
    except (ValueError, KeyError, OSError, SnapshotError):
        return abstain('aggregate_unavailable', 'The planned publication could not be verified. Retry or select a current analysis; no scientific answer was generated.')


def result_packets(result, scope):
    """Whole exact rows with explicit display bounds; no partial-JSON evidence."""
    packets = []
    for document in result.documents:
        recipe = document['analysis_recipe']
        source_scopes = {family: {**scope['sources'][family]['filters'],
                                  'time_from': recipe['time_from'], 'time_to': recipe['time_to']}
                         for family in document['covered_source_types']}
        for row in document['result_rows'][:10]:
            packet = {**document, 'id': document['id'] + '_' + row['result_id'],
                      'result_ids': [row['result_id']], 'result_rows': [row],
                      'source_scopes': source_scopes, 'rows_truncated': document['total_rows'] > 10}
            packet['text'] = json.dumps({
                'scope': {'region': recipe['region_id'], 'time_from': recipe['time_from'], 'time_to': recipe['time_to'],
                          'assignment_method': recipe['assignment_method'], 'protocol_id': result.diagnostics['research_intent']['protocol_id']},
                'table': document['table'], 'row': row, 'total_table_rows': document['total_rows'],
                'publication_scope': document.get('analysis_recipe'),
                'publication_limitations': document.get('limitations', []),
                'taxa': document.get('plot_taxa', []),
                'analysis_type': document.get('analysis_type'),
                'publication_status': document.get('publication_status'),
                'interpretation_limits': document.get('interpretation_limits'),
                'display_limit': 10, 'interpretation': 'One exact published row. Rows are selected, not recomputed. Preserve eligible denominators and support/missingness flags. Detection frequency is not abundance; SST associations are not causal effects.',
            }, ensure_ascii=False, default=str)
            if len(packet['text']) <= MAX_PROMPT_FIELD_CHARS:
                packets.append(packet)
    return packets


def sst_coverage(scope):
    """Calendar facts from the complete verified regional ledger, independent of top-k."""
    from ingestion.regional_publication import current_publication, DATASET, NOTES
    from schema.time_range import matches_time

    publication = current_publication()
    filters = scope['sources']['remote_sensing']['filters']
    if not publication or not scope['sources']['remote_sensing']['enabled'] or filters.get('dataset_id') != DATASET:
        raise ValueError('Published MUR coverage is unavailable')
    if any(key.startswith(('lat_', 'lon_')) for key in filters):
        raise ValueError('A smaller coordinate scope cannot inherit regional coverage')
    start, end = filters.get('time_from', '2020-01-01'), filters.get('time_to', '2023-12-31')
    if len(start) != 10 or len(end) != 10 or start < '2020-01-01' or end > '2023-12-31':
        raise ValueError('Coverage is published only for complete dates within 2020–2023')
    period = publication['period']
    dates = sorted(row['time_utc'][:10] for row in period['observations'] if matches_time(row['time_utc'], start, end))
    gaps = [row for row in period['final_series_gaps'] if matches_time(row['day'], start, end)]
    expected = {(date.fromisoformat(start) + timedelta(days=i)).isoformat()
                for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)}
    if set(dates) & {g['day'] for g in gaps} or set(dates) | {g['day'] for g in gaps} != expected:
        raise ValueError('Published coverage does not reconcile with the requested calendar')
    identity = 'mur_coverage_' + digest([publication['publication_id'], filters])
    missing = '\n'.join('- ' + g['day'] + ': ' + g['reason'] for g in gaps) or 'None in the verified requested calendar.'
    answer = (f'Final MUR 04.1 SST coverage for the published Miyagi region, {start}–{end}: '
              f'**{len(dates)} supported days / {len(expected)} calendar days**; **{len(gaps)} missing dates**.\n\n'
              'Missing dates and retained reasons:\n' + missing + '\n\n'
              + ' '.join(NOTES[:3]) + '\n\nGrid spacing is not effective ocean-feature resolution. '
              'The regional footprint and support rules do not establish native sample-area coverage. '
              'This is an operationally accepted publication, without independent researcher approval or provider endorsement. '
              f'[{identity}]')
    document = {'doc_id': identity, 'source_type': 'remote_sensing', 'time': start + 'T09:00:00+00:00',
                'title': 'Verified final MUR Miyagi calendar coverage', 'text': answer,
                'metadata': {'dataset_id': DATASET, 'publication_id': publication['publication_id'],
                             'coverage_summary': True, 'days': len(dates), 'expected_days': len(expected),
                             'observed_start': start, 'observed_end': end, 'final_series_gaps': gaps,
                             'grid_step_degrees': period['definition']['grid_step_degrees'],
                             'region_bounds': period['definition']['diagnostic_rectangle']}}
    return answer, document
