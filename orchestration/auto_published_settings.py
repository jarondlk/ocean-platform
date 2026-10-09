"""Resolve verified published choices without making the model invent defaults."""
import re

from orchestration.research_intents import SST_INTENTS, normalized, parse_intent
from orchestration.settings_plan import SettingsProposal


def default_analysis(options):
    if len(options) == 1:
        return options[0]
    if not options:
        return None
    # Only method variants of the SAME operational publication/cohort may have
    # a default. Different geographic/cohort/product scopes still need a choice.
    first = options[0]
    if not first.get('publication_id') or any(
        a.get('publication_id') != first['publication_id']
        or a.get('recipe_scope') != first.get('recipe_scope')
        or a.get('time_from') != first.get('time_from')
        or a.get('time_to') != first.get('time_to') for a in options
    ):
        return None
    preferred = [a for a in options if a.get('assignment_methods') == ['qcauto_95pct_3nn_target']]
    return preferred[0] if len(preferred) == 1 else None


def compatible_analyses(request, catalog, kind, filters=None, calendar=None):
    pin = request.evidence_scope.sources.edna_metabarcoding.analysis_id
    choices = [a for a in catalog['analyses'] if a['status'] == 'current'
               and (a['analysis_kind'] != 'provisional_demo' or a['analysis_id'] == pin)
               and any(w['kind'] == kind for w in a.get('workflows', []))]
    methods = {method for a in choices for method in a.get('assignment_methods', [])}
    named = [method for method in methods if re.search(r'(?<!\w)' + re.escape(method) + r'(?!\w)', request.query, re.I)]
    if not named and re.search(r'\b3\s*[- ]?\s*nn\b', request.query, re.I):
        named = ['qcauto_95pct_3nn_target']
    if named:
        choices = [a for a in choices if a.get('assignment_methods') == named]
    if pin:
        return [a for a in choices if a['analysis_id'] == pin]
    filters = dict(filters or {})
    if calendar:
        filters.update({key: calendar[key] for key in ('time_from', 'time_to')})
    for field in ('assignment_method', 'time_from', 'time_to'):
        if field in filters:
            choices = [a for a in choices if filters[field] in a.get('assignment_methods', [])] if field == 'assignment_method' else [a for a in choices if a.get(field) == filters[field]]
    named_regions = [a for a in choices if a.get('recipe_scope', {}).get('region_id')
                     and a['recipe_scope']['region_id'].casefold() in request.query.casefold()]
    return named_regions or choices


def published_dataset(option, catalog):
    candidates = [d for d in catalog['sst_datasets'] if option.get('publication_id')
                  and d.get('publication_id') == option['publication_id']]
    return candidates[0]['dataset_id'] if len(candidates) == 1 else None


def protocol_choice(option, request):
    ids = option['protocol_ids']
    pin = request.research_intent.protocol_id if request.research_intent else None
    named = [identity for identity in ids if identity in request.query]
    requested_id = re.search(r'\bprotocol(?:_id)?\s*[:=]?\s*([a-f0-9]{64})\b', request.query, re.I)
    if len(named) > 1 or requested_id and requested_id[1].lower() not in ids:
        return None, False
    # Match requested instrument/layout/gene before defaulting. A requested
    # unavailable or conflicting instrument must never become the first protocol.
    fields = {
        'sequencing_method': [name for name in ('MiSeq', 'NextSeq', 'NovaSeq', 'Nanopore', 'PacBio')
                              if re.search(r'\b' + name + r'\b', request.query, re.I)],
        'library_layout': (["paired"] if re.search(r'\bpaired(?:[- ]end)?\b', request.query, re.I) else [])
                          + (["single"] if re.search(r'\bsingle[- ]end\b', request.query, re.I) else []),
        'target_gene': [gene for gene in ('12S', '16S', '18S', 'COI') if re.search(r'\b' + gene + r'\b', request.query, re.I)],
    }
    hints = {key: values for key, values in fields.items() if values}
    eligible = [identity for identity in ids if (not named or identity in named) and all(
        all(value.casefold() in str(option.get('protocols', {}).get(identity, {}).get(field, '')).casefold()
            for value in values) for field, values in hints.items())]
    if pin:
        return (pin, False) if pin in eligible else (None, False)
    return (eligible[0], not hints and not named) if eligible else (None, False)


def exact_catalogue_plan(request, catalog, calendar=None):
    """Only complete, supported question aliases; added qualifiers stay with LLM validation."""
    coverage = next((c for c in catalog.get('capabilities', []) if c['id'] == 'sst_coverage'), {})
    if normalized(request.query) in {normalized(q) for q in coverage.get('examples', [])}:
        from ingestion.regional_publication import DATASET
        datasets = [d for d in catalog['sst_datasets'] if d['dataset_id'] == DATASET]
        if len(datasets) != 1:
            return None
        dataset = datasets[0]
        sources = {f: {'enabled': False, 'filters': {}} for f in request.evidence_scope.canonical()['sources']}
        sources['remote_sensing'] = {'enabled': True, 'filters': {'dataset_id': DATASET}}
        plan = SettingsProposal(status='ready', route='sst_coverage',
            explanation='Selected the verified final MUR Miyagi calendar and its coverage limitations.',
            evidence_scope={'version': 1, 'sources': sources}, required_sources=['remote_sensing'],
            constraints=[{'family': 'remote_sensing', 'field': 'dataset_id', 'quote': re.search(r'\bMUR\b', request.query, re.I)[0]}])
        return plan, {'analysis_id': None, 'workflow': 'sst_coverage', 'protocol_id': None,
                      'dataset_id': DATASET, 'dataset_label': dataset.get('label', DATASET)}
    kinds = {parse_intent(request.query, a.get('recipe_scope')) for a in catalog['analyses']
             if a['status'] == 'current'} - {None}
    if len(kinds) != 1:
        return None
    kind = kinds.pop()
    option = default_analysis(compatible_analyses(request, catalog, kind, calendar=calendar))
    if not option or kind in SST_INTENTS and not option.get('sst_available'):
        return None
    protocol, defaulted = protocol_choice(option, request)
    if not protocol:
        return None
    sources = {family: {'enabled': False, 'filters': {}} for family in request.evidence_scope.canonical()['sources']}
    sources['edna_metabarcoding'].update(enabled=True, analysis_id=option['analysis_id'])
    required = ['edna_metabarcoding']
    if kind in SST_INTENTS or (request.evidence_scope.sources.edna_metabarcoding.analysis_id
                              and request.evidence_scope.sources.remote_sensing.enabled):
        sources['remote_sensing']['enabled'] = True
    if kind in SST_INTENTS:
        required.append('remote_sensing')
    dataset = published_dataset(option, catalog) if sources['remote_sensing']['enabled'] else None
    if dataset:
        sources['remote_sensing']['filters']['dataset_id'] = dataset
    plan = SettingsProposal(status='ready', route='published_exact',
        explanation='Use the verified published workflow and its comparable assay protocol.',
        evidence_scope={'version': 1, 'sources': sources}, required_sources=required,
        research_intent={'kind': kind, 'protocol_id': protocol})
    selection = choice_metadata(option, kind, protocol, request, defaulted)
    plan.explanation = selection_explanation(selection)
    return plan, selection


def choice_metadata(option, kind, protocol, request, defaulted):
    return {'analysis_id': option['analysis_id'], 'analysis_label': option.get('label', option['analysis_id']),
            'workflow': kind, 'protocol_id': protocol,
            'protocol_label': option.get('protocol_labels', {}).get(protocol, protocol[:12]),
            'analysis_defaulted': not request.evidence_scope.sources.edna_metabarcoding.analysis_id,
            'protocol_defaulted': defaulted}


def selection_explanation(selection):
    return (f"Selected {selection['analysis_label']} · {selection['workflow'].replace('_', ' ')}. "
            f"{'Using the first published assay protocol by default' if selection['protocol_defaulted'] else 'Retaining the selected/requested assay protocol'}: "
            f"{selection['protocol_label']}. Protocols remain separate.")[:1000]
