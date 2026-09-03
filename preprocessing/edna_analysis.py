"""Deterministic, method-separated descriptive analyses of canonical eDNA rows."""
from collections import defaultdict
from itertools import combinations
import json
import math
import platform
from importlib.metadata import version

from ingestion.immutable_bundle import canonical_bytes, digest
from preprocessing.edna_recipe import AnalysisRecipe, METHODS
from schema.time_range import matches_time

ALGORITHM_VERSION = 'edna-descriptive-v1'
MAX_ANALYSIS_BYTES = 128 * 1024 * 1024


def runtime_versions():
    return {'python': platform.python_version(), 'scipy': version('scipy'), 'numpy': version('numpy')}


def check_size(value):
    if len(canonical_bytes(value)) > MAX_ANALYSIS_BYTES:
        raise ValueError('Analysis byte resource limit exceeded (128 MiB)')


RANKS = ('superkingdom', 'kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species')
LIMITATIONS = [
    'Indices describe assigned sequence-read composition, not organism abundance.',
    'Missing detection records do not establish biological absence.',
    'Assignment methods share assay evidence; agreement is not independent validation.',
    'No automatic control subtraction or inferential significance testing is applied.',
]


def metadata(row):
    value = row.get('raw_metadata_json') or {}
    return json.loads(value) if isinstance(value, str) else value


def protocol(assay):
    fields = {k: assay.get(k) for k in ('target_gene', 'primer_set', 'sequencing_method', 'library_layout')}
    fields['pcr'] = {k: v for k, v in metadata(assay).items() if k.lower().startswith('pcr')}
    return fields


def taxon_key(row, rank):
    if not row.get(rank) or str(row[rank]).strip().casefold() in {'na', 'unassigned', 'unidentified', 'unknown'}:
        return None
    return tuple((k, str(row.get(k) or '').strip()) for k in RANKS[:RANKS.index(rank) + 1])


def alpha(counts):
    counts = [n for n in counts if n > 0]
    total, richness = sum(counts), len(counts)
    if not total:
        return dict(richness=0, shannon=None, simpson_1d=None, evenness=None, metric_status='no_eligible_reads')
    p = [n / total for n in counts]
    h = max(0.0, -sum(v * math.log(v) for v in p))
    return dict(richness=richness, shannon=h, simpson_1d=1 - sum(v*v for v in p),
                evenness=h / math.log(richness) if richness > 1 else None,
                metric_status='single_taxon' if richness == 1 else 'computed')


def beta(left, right):
    a, b = set(left), set(right)
    union = a | b
    j = len(a & b) / len(union) if union else None
    ln, rn = sum(left.values()), sum(right.values())
    bc = sum(abs(left.get(k, 0)/ln - right.get(k, 0)/rn) for k in union)/2 if ln and rn else None
    return dict(jaccard_similarity=j, jaccard_dissimilarity=None if j is None else 1-j,
                bray_curtis_relative_reads=bc,
                metric_status='computed' if ln and rn else 'empty_composition')


def _matches(sample, cohort):
    for key in ('provider', 'provider_project_id', 'provider_run_id'):
        if getattr(cohort, key) is not None and sample.get(key) != getattr(cohort, key):
            return False
    if cohort.sample_ids and sample['sample_id'] not in cohort.sample_ids:
        return False
    if not matches_time(sample.get('collection_date_utc'), cohort.time_from, cohort.time_to):
        return False
    for key, sign in (('lat_min', 1), ('lat_max', -1), ('lon_min', 1), ('lon_max', -1)):
        bound = getattr(cohort, key)
        value = sample.get(key[:3])
        if bound is not None and (value is None or not math.isfinite(float(value)) or sign * (value - bound) < 0):
            return False
    return True


def select_inputs(recipe, source):
    def active(name):
        return [r for r in source.get(name, []) if r.get('active', True) is True]
    samples = active('edna_sample')
    selected = [s for s in samples if _matches(s, recipe.cohort)]
    scopes = {(s['provider'], s['provider_project_id'], s['provider_run_id']) for s in selected}
    selected_ids = {s['sample_id'] for s in selected}
    samples = [s for s in samples if s['sample_id'] in selected_ids or (
        s.get('sample_kind') != 'environmental' and
        (s['provider'], s['provider_project_id'], s['provider_run_id']) in scopes)]
    ids = {s['sample_id'] for s in samples}
    assays = [a for a in active('edna_assay') if a['sample_id'] in ids]
    aids = {a['assay_id'] for a in assays}
    detections = [d for d in active('edna_detection') if d['assay_id'] in aids]
    standards = [s for s in active('edna_internal_standard') if s['assay_id'] in aids]
    if len(detections) > recipe.max_detection_rows:
        raise ValueError('Detection-row resource limit exceeded')
    environmental = {s['sample_id'] for s in samples if s.get('sample_kind') == 'environmental' and s.get('is_control') is False}
    if sum(a['sample_id'] in environmental for a in assays) > recipe.max_assays:
        raise ValueError('Assay resource limit exceeded')
    if len(assays) > 1000:
        raise ValueError('Control-inclusive assay resource limit exceeded')
    records = samples + assays + detections + standards
    fids = {r.get('source_file_id') for r in records}
    sids = {r.get('source_snapshot_id') for r in records}
    result = dict(edna_sample=samples, edna_assay=assays, edna_detection=detections, edna_internal_standard=standards,
                  external_source_file=[f for f in source.get('external_source_file', []) if f['source_file_id'] in fids],
                  external_source_snapshot=[s for s in source.get('external_source_snapshot', []) if s['snapshot_id'] in sids])
    return {k: sorted(v, key=digest) for k, v in result.items()}


def method_comparison(detections):
    pairs = defaultdict(dict)
    for d in detections:
        if d['assignment_method'] in METHODS:
            pairs[(d['assay_id'], d['sequence_sha256'])][d['assignment_method']] = d
    output = []
    for (assay, sequence), methods in sorted(pairs.items()):
        a, b = (methods.get(m) for m in METHODS)
        status = 'method_only_sequence'
        if a and b:
            left = {r: a[r] for r in RANKS if a.get(r)}
            right = {r: b[r] for r in RANKS if b.get(r)}
            if not left or not right:
                status = 'unassigned'
            elif left == right:
                status = 'exact_agreement'
            elif any(left[k] != right[k] for k in left.keys() & right.keys()):
                status = 'conflicting_assignment'
            elif left.items() <= right.items() or right.items() <= left.items():
                status = 'compatible_resolution'
            else:
                status = 'incomplete_lineage'
        output.append(dict(assay_id=assay, sequence_sha256=sequence, status=status,
                           qcauto_detection_id=a['detection_id'] if a else None,
                           three_nn_detection_id=b['detection_id'] if b else None,
                           qcauto_taxonomy={r: a.get(r) for r in RANKS} if a else None,
                           three_nn_taxonomy={r: b.get(r) for r in RANKS} if b else None,
                           qcauto_read_count=a['read_count'] if a else None,
                           three_nn_read_count=b['read_count'] if b else None,
                           read_count_difference=b['read_count']-a['read_count'] if a and b else None))
    return output


def build_analysis(recipe: AnalysisRecipe, source: dict, environment=None):
    from preprocessing.edna_quality import quality_reports
    from retrieval.edna_environment_linker import environmental_reports
    inputs = select_inputs(recipe, source)
    snapshot = {'canonical': inputs, 'environment': sorted(environment or [], key=digest), 'runtime': runtime_versions()}
    check_size(snapshot)
    samples = {s['sample_id']: s for s in inputs['edna_sample']}
    assays = {a['assay_id']: a for a in inputs['edna_assay']}
    detections = defaultdict(list)
    for d in inputs['edna_detection']:
        detections[(d['assay_id'], d['assignment_method'])].append(d)
    sites = {s.sample_id: s for s in recipe.sites}
    tables = {name: [] for name in ('membership', 'composition', 'diversity', 'turnover', 'exclusions', 'methods', 'method_summary')}
    vectors, partitions, common_by_key = {}, defaultdict(list), {}
    all_taxa = set()
    for sid, sample in sorted(samples.items()):
        if not any(a['sample_id'] == sid for a in assays.values()):
            tables['membership'].append(dict(sample_id=sid, status='sample_excluded', reason='no_active_assay'))
    for aid, assay in sorted(assays.items()):
        sample = samples[assay['sample_id']]
        environmental = sample.get('sample_kind') == 'environmental' and sample.get('is_control') is False
        p = protocol(assay)
        comparable = all(p.get(k) for k in ('target_gene', 'primer_set', 'sequencing_method'))
        for method in recipe.assignment_methods:
            rows = detections.get((aid, method), [])
            common = dict(sample_id=sample['sample_id'], assay_id=aid, assignment_method=method, rank=recipe.rank,
                          provider=sample['provider'], provider_project_id=sample['provider_project_id'],
                          provider_run_id=sample['provider_run_id'], sample_kind=sample.get('sample_kind'),
                          is_control=sample.get('is_control'), collection_date_utc=sample.get('collection_date_utc'),
                          temporal_precision=sample.get('temporal_precision'), lat=sample.get('lat'), lon=sample.get('lon'))
            status = 'included' if environmental and rows and comparable else 'sample_excluded'
            reason = (None if status == 'included' else 'control_or_unknown' if not environmental
                      else 'method_unavailable' if not rows else 'protocol_incomplete')
            partition = digest([sample['provider'], sample['provider_project_id'], sample['provider_run_id'], p, method, recipe.rank])
            common['partition_id'] = partition
            tables['membership'].append({**common, 'status': status, 'reason': reason, 'protocol': p, 'detection_count': len(rows)})
            counts, contributing = defaultdict(int), defaultdict(list)
            excluded_reads = 0
            for row in rows:
                key = taxon_key(row, recipe.rank)
                why = reason or ('unresolved_rank' if key is None else 'below_min_read_count' if row['read_count'] < recipe.min_read_count else None)
                if why:
                    tables['exclusions'].append({**common, 'detection_id': row['detection_id'], 'read_count': row['read_count'], 'reason': why})
                    excluded_reads += row['read_count']
                else:
                    counts[key] += row['read_count']
                    contributing[key].append(row['detection_id'])
            if status != 'included':
                continue
            total = sum(counts.values())
            all_taxa.update(counts)
            if len(all_taxa) > recipe.max_taxa:
                raise ValueError('Taxon resource limit exceeded')
            for key, n in sorted(counts.items()):
                tables['composition'].append({**common, 'taxon_key': digest(key), 'taxon': dict(key)[recipe.rank],
                                               'taxonomy': dict(key), 'read_count': n, 'read_proportion': n/total,
                                               'detection_ids': sorted(contributing[key]), 'status': 'recorded'})
            tables['diversity'].append({**common, **alpha(counts.values()), 'retained_reads': total,
                                       'excluded_reads': excluded_reads, 'source_reads': total + excluded_reads,
                                       'source_detection_count': len(rows)})
            key = (aid, method)
            vectors[key], common_by_key[key] = dict(counts), common
            partitions[partition].append(key)
    pair_count = sum(len(v)*(len(v)-1)//2 for v in partitions.values())
    if pair_count > recipe.max_comparisons:
        raise ValueError('Pairwise resource limit exceeded')
    for partition, members in sorted(partitions.items()):
        for a, b in combinations(sorted(members), 2):
            left, right = common_by_key[a], common_by_key[b]
            ls, rs = sites.get(left['sample_id']), sites.get(right['sample_id'])
            pair_type = 'site_unresolved' if not ls or not rs else 'same_site' if ls.site_id == rs.site_id else 'different_site'
            from retrieval.edna_environment_linker import distance_km
            tables['turnover'].append(dict(partition_id=partition, assignment_method=a[1], rank=recipe.rank,
                left_assay_id=a[0], right_assay_id=b[0], left_sample_id=left['sample_id'], right_sample_id=right['sample_id'],
                left_time=left['collection_date_utc'], right_time=right['collection_date_utc'], pair_type=pair_type,
                distance_km=distance_km(left, right), **beta(vectors[a], vectors[b])))
    if set(recipe.assignment_methods) == set(METHODS):
        tables['methods'] = method_comparison(inputs['edna_detection'])
        if len(tables['methods']) > recipe.max_comparisons:
            raise ValueError('Method comparison resource limit exceeded')
        for row in tables['methods']:
            sample = samples[assays[row['assay_id']]['sample_id']]
            row.update(sample_id=sample['sample_id'], sample_kind=sample.get('sample_kind'), is_control=sample.get('is_control'))
        for aid in sorted(assays):
            rows = [r for r in tables['methods'] if r['assay_id'] == aid]
            sample = samples[assays[aid]['sample_id']]
            tables['method_summary'].append(dict(assay_id=aid, sample_id=sample['sample_id'], sample_kind=sample.get('sample_kind'), is_control=sample.get('is_control'), sequence_union=len(rows),
                matched_sequences=sum(r['qcauto_detection_id'] is not None and r['three_nn_detection_id'] is not None for r in rows),
                status_counts={s: sum(r['status'] == s for r in rows) for s in sorted({r['status'] for r in rows})}))
    tables.update(quality_reports(recipe, inputs))
    tables.update(environmental_reports(recipe, inputs, tables['diversity'], environment or []))
    identity = digest({'algorithm': ALGORITHM_VERSION, 'recipe': recipe.model_dump(), 'input_sha256': digest(snapshot)})
    for name, rows in tables.items():
        tables[name] = [{**r, 'result_id': digest([identity, name, r])} for r in sorted(rows, key=digest)]
    result = dict(analysis_id=identity, algorithm_version=ALGORITHM_VERSION, recipe=recipe.model_dump(),
                input_sha256=digest(snapshot), inputs=snapshot, tables=tables, limitations=LIMITATIONS)
    check_size(result)
    return result
