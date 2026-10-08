"""Versioned descriptions joined to current publication availability."""
from ingestion.immutable_bundle import digest
from orchestration.research_intents import QUESTIONS, SST_INTENTS, TABLES_BY_INTENT

DESCRIPTIONS = {
    'fish_frequency': 'Top ten fish by detection frequency; yearly and seasonal series. Frequency means detected/eligible samples, not sequencing reads or abundance.',
    'temperature_comparison': 'Published high/low SST frequency contrasts and a fixed representative series. Descriptive associations do not establish causation.',
    'monthly_spatial': 'Best-covered month and detections for the fixed spatial taxon across published areas. Unsampled groups are not negative detections.',
    'spatial_temperature': 'Temperature conditions in sampled areas with and without detections of the fixed spatial taxon.',
    'distribution_change': 'Endpoint distribution differences for the fixed three-fish panel using the publication matched strata.',
    'follow_through': 'Intermediate-year changes and SST for the same endpoint-selected fish panel.',
}
CAPABILITIES = [
    {'id': kind, 'description': description, 'tables': list(TABLES_BY_INTENT[kind]),
     'required_sources': ['edna_metabarcoding', *(['remote_sensing'] if kind in SST_INTENTS else [])],
     'examples': list(QUESTIONS[kind]), 'routes': ['published_exact', 'published_synthesis']}
    for kind, description in DESCRIPTIONS.items()
] + [{'id': 'sst_coverage', 'description': 'Exact final MUR Miyagi calendar coverage, missing dates and resolution limitations from the verified regional publication. Interim files do not fill final gaps.',
      'required_sources': ['remote_sensing'], 'routes': ['sst_coverage']}]


def analysis_choices():
    from ingestion.edna_analysis_bundle import _registered_records, load_analysis, analysis_status
    from ingestion.regional_publication import analysis_publication
    from preprocessing.edna_analysis import protocol

    records = _registered_records()
    if len(records) > 100:
        raise ValueError('Analysis options catalog limit exceeded')
    options = []
    for record in records:
        bundle = load_analysis(record['analysis_id'])
        recipe = bundle['recipe']
        research = bundle['manifest'].get('schema_version') in {2, 3}
        accepted = analysis_publication(bundle)
        protocol_ids = sorted({r['protocol_id'] for r in bundle['tables']['membership']}) if research else []
        protocols = {digest(protocol(a)): protocol(a) for a in bundle['inputs']['canonical']['edna_assay']
                     if digest(protocol(a)) in protocol_ids} if research else {}
        option = {
            'analysis_id': record['analysis_id'], 'status': analysis_status(bundle),
            'analysis_kind': 'regional_frequency' if accepted else 'provisional_demo' if bundle['manifest'].get('schema_version') == 3 else 'detection_frequency' if research else 'edna_descriptive',
            'label': (accepted['label'] + ' · ' + recipe['assignment_method']) if accepted else ('PROVISIONAL DEMO · ' + recipe['region_id'] + ' · ' + recipe['assignment_method']) if bundle['manifest'].get('schema_version') == 3 else recipe.get('region_id') or recipe.get('cohort', {}).get('provider_project_id') or 'Selected cohort',
            'time_from': recipe.get('time_from') or recipe.get('cohort', {}).get('time_from'),
            'time_to': recipe.get('time_to') or recipe.get('cohort', {}).get('time_to'),
            'assignment_methods': [recipe['assignment_method']] if research else recipe['assignment_methods'],
            'protocol_ids': protocol_ids,
            'protocol_labels': {key: ' · '.join(str(value[field] or 'unspecified') for field in ('target_gene', 'primer_set', 'sequencing_method', 'library_layout')) + ' · ' + key[:8] for key, value in protocols.items()},
            'protocols': protocols, 'sst_available': bool(recipe.get('sst_panel_id')) if research else False,
            'workflows': [{'kind': kind, 'question': aliases[0], 'description': DESCRIPTIONS[kind]} for kind, aliases in QUESTIONS.items()] if research else [],
            'limitations': bundle['manifest'].get('limitations', []),
            'recipe_scope': {key: recipe[key] for key in
                             ('region_id', 'time_from', 'time_to', 'rank', 'spatial_taxon_key',
                              'sst_panel_id', 'endpoint_from', 'endpoint_to') if key in recipe},
        }
        options.append(option)
    return options


def statistics_catalog():
    from ingestion.regional_publication import current_publication, DATASET, LABEL, NOTES

    publication = current_publication()
    datasets = [] if publication is None else [{
        'dataset_id': DATASET, 'label': LABEL, 'publication_id': publication['publication_id'],
        'time_from': '2020-01-01', 'time_to': '2023-12-31',
        'region_bounds': publication['period']['definition']['diagnostic_rectangle'],
        'limitations': NOTES,
    }]
    return {'version': 1, 'capabilities': CAPABILITIES, 'analyses': analysis_choices(), 'sst_datasets': datasets}
