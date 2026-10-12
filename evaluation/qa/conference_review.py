"""Offline factual review and explicitly labelled conference fallback receipts.

This reviews retained evidence; it does not grant scientific peer approval,
authenticate a conference role, call a model, or write application history.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from evaluation.qa.conference_demo import MANIFEST, verify, verify_registration
from ingestion.artifact_store import BoundedLocalStore
from ingestion.immutable_bundle import canonical_bytes, digest, read_bundle
from ingestion.research_readiness import method_status
from orchestration.research_intents import ResearchIntent, render_research
from preprocessing.edna_analysis import taxon_key
from preprocessing.edna_taxonomy import detection_assignment
from orchestration.research_question import FREQUENCY_JA, SPATIAL_JA


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _same_number(actual, expected):
    return actual is None if expected is None else (
        isinstance(actual, (int, float)) and math.isclose(actual, expected, abs_tol=1e-10, rel_tol=1e-12))


def review_sst(bundle):
    """Check rates, contrasts and source-time SST without using published arithmetic."""
    recipe, tables = bundle['recipe'], bundle['tables']
    source = bundle['inputs']['canonical']
    members = {m['physical_sample_id']: m for m in tables['membership']}
    assays = {a['assay_id']: a for a in source['edna_assay']}
    samples = {s['sample_id']: s for s in source['edna_sample']}
    by_assay = {m['assay_id']: m['physical_sample_id'] for m in members.values()}
    reads = Counter()
    for d in source['edna_detection']:
        if (d.get('active', True) and d['assay_id'] in by_assay
                and d['assignment_method'] == recipe['assignment_method']
                and d.get('class') in recipe['fish_classes']):
            lineage = taxon_key(d, 'species')
            if lineage:
                reads[(by_assay[d['assay_id']], digest(lineage))] += d['read_count']
    presence = defaultdict(set)
    for (member, taxon), count in reads.items():
        if count >= recipe['min_read_count']:
            presence[taxon].add(member)
    observations = bundle['inputs']['period_preview']['observations']
    daily = defaultdict(list)
    dates = set()
    for o in observations:
        local = datetime.fromisoformat(o['time_utc']).astimezone(ZoneInfo(recipe['calendar'])).date()
        _require((o['area_id'], local) not in dates, 'Duplicate SST day')
        dates.add((o['area_id'], local))
        label = 'DJF' if local.month in (12, 1, 2) else 'MAM' if local.month <= 5 else 'JJA' if local.month <= 8 else 'SON'
        if o['status'] == 'valid':
            daily[(o['area_id'], label)].append(o['sst_celsius'])
    cuts = {}
    for r in tables['relative_sst_thresholds']:
        values = sorted(daily[(r['area_id'], r['season'])])
        def quantile(q):
            index = (len(values) - 1) * q
            left, right = math.floor(index), math.ceil(index)
            return values[left] + (values[right] - values[left]) * (index - left)
        low, high = quantile(1 / 3), quantile(2 / 3)
        _require(r['supported_days'] == len(values) and _same_number(r['low_max_celsius'], low)
                 and _same_number(r['high_min_celsius'], high), 'SST daily baseline does not reconcile')
        cuts[(r['area_id'], r['season'])] = (r['low_max_celsius'], r['high_min_celsius'])
    links = {r['physical_sample_id']: r for r in tables['sst_links']}
    _require(len(links) == len(tables['sst_links']), 'Duplicate SST member link')
    for identity, link in links.items():
        _require(identity in members, 'SST linked member is outside cohort')
        matches = [o for o in observations if o['time_utc'] == link['source_time_utc']
                   and o['area_id'] == link['area_id'] and o['status'] == 'valid']
        _require(len(matches) == 1 and matches[0]['granule_id'] in link['source_granule_ids']
                 and _same_number(link['sst_celsius'], matches[0]['sst_celsius']), 'SST source observation mismatch')
        _require(link['time_difference_hours'] <= link['window_used_hours']
                 and link['window_used_hours'] in (24, 48), 'SST match outside recorded window')
        sample = samples[assays[members[identity]['assay_id']]['sample_id']]
        collected = (datetime.fromisoformat(members[identity]['collection_date'] + 'T12:00:00+09:00')
                     if sample['temporal_precision'] == 'date' else
                     datetime.fromisoformat(str(sample['collection_date_utc']).replace('Z', '+00:00')))
        source_time = datetime.fromisoformat(link['source_time_utc'])
        _require(collected.tzinfo is not None and source_time.tzinfo is not None
                 and _same_number(link['time_difference_hours'], abs((source_time - collected).total_seconds()) / 3600),
                 'SST source-time difference does not reconcile')
        low, high = cuts[(members[identity]['area_id'], members[identity]['season'])]
        label = 'unpartitioned_ties' if low >= high else 'low' if link['sst_celsius'] <= low else 'high' if link['sst_celsius'] >= high else 'middle'
        _require(link['relative_bin'] == label, 'SST bin differs from daily baseline')
    def cohort(protocol):
        return {i for i, m in members.items() if m['protocol_id'] == protocol}
    def bin_members(protocol, label, area=None, season=None):
        return {i for i in cohort(protocol) if i in links and links[i]['relative_bin'] == label
                and (area is None or members[i]['area_id'] == area)
                and (season is None or members[i]['season'] == season)}
    def delta(key, low, high):
        return float((Fraction(len(high & presence[key]), len(high))
                      - Fraction(len(low & presence[key]), len(low))) * 100) if low and high else None
    def rate(row, ids):
        detected = ids & presence[row['taxon_key']]
        _require(row['eligible'] == len(ids) and row['detected'] == len(detected)
                 and set(row['member_ids']) == ids and set(row['detected_member_ids']) == detected
                 and _same_number(row['frequency'], len(detected) / len(ids) if ids else None),
                 'SST rate does not reconcile')
    for row in tables['temperature_bins']:
        ids = bin_members(row['protocol_id'], row['bin'])
        rate(row, ids)
        all_ids = cohort(row['protocol_id'])
        _require(row['all_edna_eligible'] == len(all_ids)
                 and row['sst_unavailable'] == len(all_ids - set(links)), 'SST denominator mismatch')
    strata = defaultdict(list)
    for row in tables['temperature_strata']:
        low = bin_members(row['protocol_id'], 'low', row['area_id'], row['season'])
        high = bin_members(row['protocol_id'], 'high', row['area_id'], row['season'])
        expected = delta(row['taxon_key'], low, high)
        supported = min(len(low), len(high)) >= recipe['min_stratum_samples']
        _require((row['low_eligible'], row['high_eligible'], row['low_detected'], row['high_detected'])
                 == (len(low), len(high), len(low & presence[row['taxon_key']]), len(high & presence[row['taxon_key']]))
                 and row['supported'] == supported
                 and _same_number(row['difference_percentage_points'], expected), 'SST stratum does not reconcile')
        if supported:
            strata[(row['protocol_id'], row['taxon_key'])].append(Fraction(len(high & presence[row['taxon_key']]), len(high)) * 100
                - Fraction(len(low & presence[row['taxon_key']]), len(low)) * 100)
    reversed_directions = []
    for row in tables['temperature_contrasts']:
        low, high = bin_members(row['protocol_id'], 'low'), bin_members(row['protocol_id'], 'high')
        expected = delta(row['taxon_key'], low, high)
        supported_values = strata[(row['protocol_id'], row['taxon_key'])]
        standardized = float(sum(supported_values) / len(supported_values)) if supported_values else None
        _require((row['low_eligible'], row['high_eligible'], row['low_detected'], row['high_detected'])
                 == (len(low), len(high), len(low & presence[row['taxon_key']]), len(high & presence[row['taxon_key']]))
                 and row['supported_strata'] == len(supported_values)
                 and row['supported'] == (min(len(low), len(high)) >= recipe['min_stratum_samples'] and bool(supported_values))
                 and _same_number(row['difference_percentage_points'], expected)
                 and _same_number(row['standardized_difference_percentage_points'], standardized), 'SST contrast does not reconcile')
        if expected and standardized and expected * standardized < 0:
            reversed_directions.append(row['result_id'])
    for pid in {m['protocol_id'] for m in members.values()}:
        choices = [r for r in tables['temperature_contrasts'] if r['protocol_id'] == pid and r['supported']]
        winners = [r for r in tables['temperature_contrasts'] if r['protocol_id'] == pid and r['representative']]
        _require(winners == ([min(choices, key=lambda r: (-abs(r['standardized_difference_percentage_points']), r['taxon_key']))] if choices else []),
                 'SST representative selection mismatch')
    for row in tables['temperature_series']:
        ids = {i for i in cohort(row['protocol_id']) if (
            str(members[i]['year']) if row['period_kind'] == 'year' else
            f"{members[i]['season_year']}-{members[i]['season']}" if row['period_kind'] == 'season' else
            members[i]['collection_date'][:7]) == row['period']}
        rate(row, ids)
        values = [links[i]['sst_celsius'] for i in ids if i in links]
        _require(row['sst_matched'] == len(values) and _same_number(row['sample_time_sst_mean_celsius'],
                 sum(values) / len(values) if values else None), 'SST temporal context does not reconcile')
    return {'status': 'passed_offline_factual_review', 'final_daily_observations': len(observations),
            'final_series_gaps': bundle['inputs']['period_preview']['final_series_gaps'],
            'rate_rows_checked': len(tables['temperature_bins']) + len(tables['temperature_series']),
            'contrast_rows_checked': len(tables['temperature_contrasts']),
            'stratum_rows_checked': len(tables['temperature_strata']),
            'aggregate_standardized_sign_reversals': reversed_directions,
            'independent_scientific_approval': False}


def replay_sst_receipt(bundle, retained):
    intent = ResearchIntent.model_validate(retained['options']['context']['research_intent'])
    _require(intent.kind == 'temperature_comparison' and not retained['model_invoked']
             and retained['outcome'] == 'answered', 'Unsupported retained SST receipt')
    with patch('ingestion.regional_publication.analysis_publication', lambda _: None):
        rendered = render_research(bundle, retained['options']['evidence_scope'], retained['query'], intent)
    _require(not rendered.reason, 'Retained SST scope cannot be replayed')
    old = retained['analysis_context']
    _require(len(old) == len(rendered.documents), 'Retained SST document count mismatch')
    for before, after in zip(old, rendered.documents, strict=True):
        _require(all(before[key] == after[key if key != 'doc_id' else 'id']
                     for key in ('table', 'result_ids', 'result_rows', 'plot_taxa')),
                 'Retained SST rows, citations or selected graph changed')
        _require('[' + before['doc_id'] + ']' in retained['answer'], 'Retained SST citation missing')
    return rendered


def sample_taxonomy_fallback(bundle, protocol_id):
    """Select a transparent teaching sample, retaining its complete community."""
    source = bundle['inputs']['canonical']
    recipe = bundle['recipe']
    assays = {a['assay_id']: a for a in source['edna_assay']}
    samples = {s['sample_id']: s for s in source['edna_sample']}
    candidates = sorted((m for m in bundle['tables']['membership'] if m['protocol_id'] == protocol_id),
                        key=lambda m: (m['collection_date'], m['physical_sample_id']))
    for member in candidates:
        assay = assays[member['assay_id']]
        rows = [d for d in source['edna_detection'] if d['assay_id'] == assay['assay_id']
                and d['assignment_method'] == recipe['assignment_method'] and d.get('active', True)]
        availability = assay['community_availability_json']
        availability = json.loads(availability) if isinstance(availability, str) else availability
        if (assay.get('active', True) is not True
                or method_status(assay, recipe['assignment_method']) != 'available_nonempty'
                or availability[recipe['assignment_method']]['row_count'] != len(rows)):
            continue
        groups = defaultdict(list)
        for d in rows:
            if d.get('class') in recipe['fish_classes']:
                name, rank = detection_assignment(d)
                if name:
                    groups[(name, rank)].append(d)
        names = {rank: sorted((name for name, r in groups if r == rank),
            key=lambda name: (-sum(d['read_count'] for d in groups[(name, rank)]), name))
            for rank in ('species', 'genus')}
        if len(names['species']) < 3 or len(names['genus']) < 2:
            continue
        illustrated = [(name, 'species') for name in names['species'][:3]] + [(name, 'genus') for name in names['genus'][:2]]
        complete = [{'name': name, 'rank': rank, 'read_count': sum(d['read_count'] for d in evidence),
                     'detection_ids': sorted(d['detection_id'] for d in evidence),
                     'source_row_hashes': sorted(d['source_row_hash'] for d in evidence)}
                    for (name, rank), evidence in sorted(groups.items())]
        sample = samples[assay['sample_id']]
        return {'status': 'verified_labelled_miyagi_replacement', 'original_otsuchi_reproduced': False,
                'title': 'Miyagi sample: five illustrated assignment labels from a larger community',
                'selection_rule': 'Earliest eligible pinned-protocol sample with at least three species and two genus-only assignments; illustrate the three species and two genera with highest source read sums, using name order for ties.',
                'sample_id': sample['sample_id'], 'assay_id': assay['assay_id'], 'collection_date': member['collection_date'],
                'analysis_id': bundle['manifest']['id'], 'protocol_id': protocol_id,
                'assignment_method': recipe['assignment_method'],
                'sample_evidence_path': '/data?view=edna&sample_id=' + sample['sample_id'],
                'assay_evidence_path': '/data?view=edna&sample_id=' + sample['sample_id'] + '&assay_id=' + assay['assay_id'] + '&assignment_method=' + recipe['assignment_method'],
                'provenance_path': '/provenance?view=trace&doc_id=edna_' + assay['assay_id'] + '_' + recipe['assignment_method'],
                'source_snapshot_id': sample['source_snapshot_id'], 'source_file_id': sample['source_file_id'],
                'complete_assignment_counts': dict(Counter(r['rank'] for r in complete)),
                'complete_community_method_rows': len(rows), 'complete_fish_assignments': complete,
                'illustrated_assignments': [r for name, rank in illustrated for r in complete if r['name'] == name and r['rank'] == rank],
                'limitations': ['Five labels are an illustration, not the full community or five independent biological taxa.',
                    'Source assignments are not independent confirmation of species presence.',
                    'Genus-only labels cannot establish species identity; no Japanese common names are supplied.']}
    return {'status': 'omitted_no_compatible_complete_sample', 'original_otsuchi_reproduced': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'artifact-index', 'artifact-receipt', 'retained-sst-receipt', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error('Use a fresh private output directory outside the repository')
    manifest = json.loads(MANIFEST.read_text())
    registration = verify_registration(args.bundle, args.artifact_index, args.artifact_receipt,
        expected_receipt_sha256=manifest['artifact_registration']['receipt_sha256'])
    from ingestion.edna_analysis_bundle import _decode_analysis
    bundle = _decode_analysis(args.bundle.name, *read_bundle(args.bundle.parent, args.bundle.name))
    frequency, _, genus = verify(bundle, manifest, sealed=True)
    _require(frequency['exact_artifact_verification_passed'], 'Conference frequency identity mismatch')
    retained_bytes = BoundedLocalStore(args.retained_sst_receipt.parent).read(
        args.retained_sst_receipt.name, max_bytes=16 * 1024 * 1024).data
    retained = json.loads(retained_bytes)
    sst_review = review_sst(bundle)
    rendered = replay_sst_receipt(bundle, retained)
    sample = sample_taxonomy_fallback(bundle, manifest['protocol_id'])
    representatives = [r for r in bundle['tables']['temperature_contrasts']
                       if r['protocol_id'] == manifest['protocol_id'] and r['representative']]
    report = {'reviewer': 'Codex offline factual and interpretation review', 'review_date_jst': '2026-10-11',
              'decision': 'descriptive_recorded_demo_accepted_with_stated_limits',
              'user_instruction': 'Proceed with the receipt and review using what makes sense.',
              'artifact_registration': registration, 'frequency': frequency, 'sst': sst_review,
              'sst_retained_receipt_sha256': hashlib.sha256(retained_bytes).hexdigest(),
              'sst_exact_rows_result_ids_citations_and_graph_preserved': True,
              'sst_representatives': representatives, 'original_organizer_receipts_recovered': False,
              'sample_replacement_status': sample['status'], 'external_advisor_approval': False,
              'authenticated_citation_resolution': False, 'two_timed_live_rehearsals': False,
              'fresh_provider_validation': False, 'paid_model_calls': 0, 'production_database_written': False,
              'new_local_code_deployed': False, 'conference_ready': False}
    args.output.mkdir(parents=True, mode=0o700)
    outputs = {'review-decision.json': report, 'sample-taxonomy-fallback.json': sample,
               'genus-inspection.json': genus, 'sst-rendered-context.json': rendered.documents,
               'sst-replay-settings.json': {'query': retained['query'], 'options': retained['options'],
                   'organizer_original': False, 'receipt_origin': 'October 9 isolated QA, case 8'}}
    for name, value in outputs.items():
        (args.output / name).write_bytes(canonical_bytes(value))
    (args.output / 'sst-replay-en.md').write_text(rendered.answer)
    names = {t['taxon_key']: t['species'] for d in rendered.documents for t in d['plot_taxa']}
    selected = representatives[0]
    script = ['# Conference operator script — reviewed recorded fallback', '',
        'Freeze: October 13, 2026, 17:00 JST. This packet passed offline factual review; authenticated live acceptance and timings remain open.', '',
        '## Fish frequency — primary', '',
        f"Pin analysis `{manifest['analysis_id']}`, protocol `{manifest['protocol_id']}`, method `{manifest['assignment_method']}`. Enable eDNA. Keep the full 2020–2023 publication interval. Do not pool protocols.", '',
        FREQUENCY_JA, '',
        'Show the top 10 fish by detection frequency, with yearly and seasonal changes', '',
        'Show all ten ranking rows. Use the taxon and year/season selectors to reach every group. Explain eligible proxies, not independent water collections; MiSeq denominators are 0/3/26/10. Preserve unsampled 2020, sparse groups and partial JST seasons. Use the sealed frequency exports if live acceptance is unavailable.', '',
        '## Retained SST comparison — labelled fallback', '', retained['query'], '',
        'Use `sst-replay-settings.json` for original requested/effective settings. Enable eDNA and remote sensing; retain the analysis, MiSeq protocol and `mur-miyagi-2020-2023` dataset pins. Use the manual exact route or verified exact AUTO route only.', '',
        f"The selected graph remains {names[selected['taxon_key']]}. Low SST: {selected['low_detected']}/{selected['low_eligible']}; high SST: {selected['high_detected']}/{selected['high_eligible']}. Aggregate high-minus-low: {selected['difference_percentage_points']:.2f} percentage points; mean supported-stratum difference: {selected['standardized_difference_percentage_points']:.2f} points across {selected['supported_strata']} stratum/strata.", '',
        'Say: these are different descriptive summaries; their opposite signs and limited stratum support prevent a general temperature-response claim. SST is regional foundation context, not native coastal/sample-point temperature. Keep the six final gaps and actual match dates. Do not describe this retained QA receipt as the exact organizer-shared example or a fresh provider test.', '']
    if sample['status'] == 'verified_labelled_miyagi_replacement':
        script += ['## Miyagi sample taxonomy/provenance — explicit Otsuchi replacement', '',
            '大槌の元の例とは別の、宮城の1アッセイの分類・出典確認です。全群集から3種と2属の割当ラベルを例示します。5分類群だけが見つかったという意味ではありません。', '',
            f"Date: {sample['collection_date']}. Full method community: {sample['complete_community_method_rows']} rows. Assignment counts: {sample['complete_assignment_counts']}.", '',
            '| Illustrated name | Source rank | Sequencing reads |', '| --- | --- | ---: |']
        script += [f"| {r['name']} | {r['rank']} | {r['read_count']} |" for r in sample['illustrated_assignments']]
        script += ['', f"[Open source sample]({sample['sample_evidence_path']}) · [Open assay and method]({sample['assay_evidence_path']}) · [Open source trace]({sample['provenance_path']})", '',
            'Open these paths within the authenticated OCEAN site using a role with Data/Provenance access. The complete assignments and detection IDs are retained in `sample-taxonomy-fallback.json`. No model call is required. Read sums are not fish counts. Genus assignments remain genera; Latin names are authoritative.', '']
    else:
        script += ['## Sample taxonomy slot', '', 'Omit: no compatible complete sample was found. Do not invent five assignments.', '']
    script += ['## Sardine question — limitations', '', SPATIAL_JA, '',
        'Explain that the cohort has no species-resolved Japanese-sardine assignments; no species-level map or absence claim is supported. The optional March 2023 Sardinops-genus table has three complete MiSeq occurrences with no genus assignments. Keep the selected month and one-cell limitation; geometry is unverified, so show no footprint or spatial SST comparison.', '',
        '## Final checks', '',
        'Offline citations and exact rows were replayed against retained evidence. Verify live conference-role access separately. Run two complete timed rehearsals in an isolated identity/database before calling the live demonstration ready. No abundance, occupancy, causal, reliability-tier or unsupported SST/CTD validation claim is approved. External scientific approval is not asserted.', '']
    (args.output / 'operator-script.md').write_text('\n'.join(script))
    receipt = {'review_decision': report['decision'], 'registration': registration,
               'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir()},
               'conference_ready': False, 'external_advisor_approval': False,
               'production_database_written': False, 'paid_model_calls': 0}
    (args.output / 'review-receipt.json').write_bytes(canonical_bytes(receipt))
    print(json.dumps({k: report[k] for k in ('decision', 'sample_replacement_status', 'sst_exact_rows_result_ids_citations_and_graph_preserved', 'conference_ready')}, indent=2))


if __name__ == '__main__':
    main()
