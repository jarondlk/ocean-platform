"""Offline conference evidence verification. No database, provider or model calls.

Supply a downloaded sealed bundle, or an explicitly labelled local preview.
Raw inputs and resulting receipts must remain outside the repository.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from ingestion.immutable_bundle import canonical_bytes, digest, read_bundle
from orchestration.research_intents import QUESTIONS, ResearchIntent, render_research
from orchestration.research_question import FREQUENCY_JA
from preprocessing.edna_analysis import taxon_key, protocol as assay_protocol
from ingestion.research_readiness import method_status
from retrieval.source_scope import FAMILIES

MANIFEST = Path(__file__).with_name('conference_manifest.json')


def verify_registration(bundle_path, index_path, receipt_path, *, expected_receipt_sha256=None):
    """Bind downloaded bytes to the retained publication index and receipt."""
    from ingestion.artifact_store import BoundedLocalStore, MAX_INDEX_BYTES
    from ingestion.immutable_bundle import validate_id

    def read_json(path):
        return json.loads(BoundedLocalStore(path.parent).read(
            path.name, max_bytes=MAX_INDEX_BYTES).data)

    identity = validate_id(bundle_path.name)
    index, receipt = read_json(index_path), read_json(receipt_path)
    entry = index.get('entries', {}).get(identity)
    if (index.get('schema_version') != 1 or not isinstance(entry, dict)
            or receipt.get('schema_version') != 1
            or receipt.get('namespace') != 'provisional-demos'
            or receipt.get('id') != identity
            or digest(receipt) != entry.get('receipt_sha256')
            or (expected_receipt_sha256 is not None and digest(receipt) != expected_receipt_sha256)
            or receipt.get('metadata') != entry.get('metadata')):
        raise ValueError('Publication registration integrity failure')
    manifest, contents = read_bundle(bundle_path.parent, identity,
        expected_digest=entry['metadata']['manifest_sha256'])
    if (set(receipt.get('files', {})) != set(contents)
            or digest(json.loads(contents['recipe.json'])) != entry['metadata']['recipe_sha256']):
        raise ValueError('Publication registration file contract failure')
    for name, data in contents.items():
        info = receipt['files'][name]
        if (info.get('size') != len(data)
                or info.get('sha256') != hashlib.sha256(data).hexdigest()
                or type(info.get('generation')) is not int or info['generation'] <= 0):
            raise ValueError('Publication registered object integrity failure')
    return {'analysis_id': identity, 'receipt_sha256': digest(receipt),
            'manifest_sha256': digest(manifest), 'registered_file_count': len(contents),
            'registration_verified': True,
            'scope': 'retained_index_and_receipt_not_live_serving_state'}


def independent_counts(bundle):
    """Reconcile every displayed rate directly against full detection evidence."""
    recipe, tables = bundle['recipe'], bundle['tables']
    members = tables['membership']
    by_assay = {m['assay_id']:m for m in members}
    if len(by_assay) != len(members) or len({m['physical_sample_id'] for m in members}) != len(members):
        raise ValueError('Duplicate selected assay or sampling unit')
    source=bundle['inputs']['canonical']
    samples={s['sample_id']:s for s in source['edna_sample']}
    assays={a['assay_id']:a for a in source['edna_assay']}
    included=[sid for m in members for sid in m['occurrence_ids']]
    excluded=[sid for e in tables['exclusions'] for sid in e['occurrence_ids']]
    if (len(set(included))!=len(included) or set(included)&set(excluded)
            or set(included)|set(excluded)!=set(samples)):
        raise ValueError('Membership and exclusions do not partition source occurrences')
    for m in members:
        assay=assays[m['assay_id']]
        sample=samples[assay['sample_id']]
        if (sample.get('active',True) is not True or sample.get('is_control') is True
                or assay['sample_id'] not in m['occurrence_ids']
                or assay.get('active',True) is not True
                or method_status(assay,recipe['assignment_method'])!='available_nonempty'
                or digest(assay_protocol(assay))!=m['protocol_id']):
            raise ValueError('Selected membership has incompatible source/assay evidence')
        if sample['temporal_precision']=='date':
            day=date.fromisoformat(str(sample['collection_date_utc'])[:10])
        else:
            when=datetime.fromisoformat(str(sample['collection_date_utc']).replace('Z','+00:00'))
            if when.tzinfo is None:
                raise ValueError('Unqualified collection time')
            day=when.astimezone(ZoneInfo(recipe['calendar'])).date()
        if day.isoformat()!=m['collection_date']:
            raise ValueError('Selected collection date does not match source/JST calendar')
    reads = Counter()
    for d in bundle['inputs']['canonical']['edna_detection']:
        if (d.get('active', True) is not True or d['assay_id'] not in by_assay
                or d['assignment_method'] != recipe['assignment_method'] or d.get('class') not in recipe['fish_classes']):
            continue
        lineage = taxon_key(d, 'species')
        if lineage:
            reads[(by_assay[d['assay_id']]['physical_sample_id'], digest(lineage))] += d['read_count']
    presence = defaultdict(set)
    for (member, taxon), count in reads.items():
        if count >= recipe['min_read_count']:
            presence[taxon].add(member)
    def period(member, kind):
        day = date.fromisoformat(member['collection_date'])
        if kind == 'year':
            return str(day.year)
        if kind == 'month':
            return day.isoformat()[:7]
        label = 'DJF' if day.month in (12,1,2) else 'MAM' if day.month <= 5 else 'JJA' if day.month <= 8 else 'SON'
        return f"{day.year + (day.month == 12)}-{label}"
    checked = 0
    for name in ('ranking','series'):
        for row in tables[name]:
            cohort = {m['physical_sample_id'] for m in members if m['protocol_id']==row['protocol_id']
                      and (name == 'ranking' or period(m,row['period_kind'])==row['period'])}
            detected = cohort & presence[row['taxon_key']]
            rate = len(detected)/len(cohort) if cohort else None
            if (row['eligible'] != len(cohort) or row['detected'] != len(detected)
                    or row['frequency'] != rate or set(row['member_ids']) != cohort
                    or set(row['detected_member_ids']) != detected):
                raise ValueError('Published rate does not reconcile: ' + row['result_id'])
            checked += 1
    for protocol in {m['protocol_id'] for m in members}:
        cohort={m['physical_sample_id'] for m in members if m['protocol_id']==protocol}
        expected=sorted((k for k,ids in presence.items() if ids & cohort),key=lambda k:(-len(presence[k]&cohort),k))[:10]
        ranked=sorted((r for r in tables['ranking'] if r['protocol_id']==protocol),key=lambda r:r['position'])
        if [r['taxon_key'] for r in ranked] != expected:
            raise ValueError('Top-ten panel differs from full evidence')
        if any(r['taxon_key'] not in expected for r in tables['series'] if r['protocol_id']==protocol):
            raise ValueError('Temporal series substituted the fixed panel')
    return {'rate_rows_checked':checked, 'protocol_units':dict(Counter(m['protocol_id'][:8] for m in members)),
            'membership_units':len(members),'excluded_occurrences':len(set(excluded)),
            'species_resolved_sardinops_rows':sum(d.get('species')=='Sardinops melanostictus'
                and taxon_key(d,'species') is not None for d in source['edna_detection'])}


def genus_inspection(bundle, protocol):
    rows=[r for r in bundle['tables']['month_coverage'] if r['protocol_id']==protocol]
    if not rows:
        return {'status':'no_published_coverage'}
    winner=min(rows,key=lambda r:(-r['sampled_areas'],-r['eligible'],r['month']))
    selected=[r for r in rows if r.get('selected')]
    if winner['eligible'] and (len(selected)!=1 or selected[0]['month']!=winner['month']):
        raise ValueError('Published month selection differs from coverage rule')
    source=bundle['inputs']['canonical']
    assays={a['assay_id']:a for a in source['edna_assay']}
    samples={s['sample_id']:s for s in source['edna_sample']}
    result=[]
    for m in bundle['tables']['membership']:
        if m['protocol_id']!=protocol or m['month']!=winner['month']:
            continue
        method=bundle['recipe']['assignment_method']
        assay=assays[m['assay_id']]
        method_rows=[d for d in source['edna_detection'] if d['assay_id']==m['assay_id']
                     and d['assignment_method']==method and d.get('active',True) is True]
        availability=assay.get('community_availability_json') or {}
        availability=json.loads(availability) if isinstance(availability,str) else availability
        available=(assay.get('active',True) is True and method_status(assay,method)=='available_nonempty'
                   and len(method_rows)==availability[method]['row_count'])
        evidence=[d for d in method_rows if d.get('genus')=='Sardinops' and taxon_key(d,'genus') is not None]
        detected=available and sum(d['read_count'] for d in evidence)>=bundle['recipe']['min_read_count']
        location=[]
        for sid in m['occurrence_ids']:
            sample=samples[sid]
            metadata=sample.get('raw_metadata_json') or {}
            metadata=json.loads(metadata) if isinstance(metadata,str) else metadata
            location.append({'sample_id':sid,'lat':sample.get('lat'),'lon':sample.get('lon'),
                             'worldmesh':metadata.get('worldmesh'),
                             'coordinate_precision':sample.get('coordinate_precision')})
        result.append({'sample_ids':m['occurrence_ids'],'assay_id':m['assay_id'],'source_locations':location,
                       'collection_date':m['collection_date'],'genus':'Sardinops','rank':'genus',
                       'status':'recorded_detection' if detected else 'recorded_non_detection' if available else 'evidence_unavailable',
                       'detection_ids':[d['detection_id'] for d in evidence],
                       'assay_evidence_path':'/data?view=edna&assay_id='+m['assay_id']+'&assignment_method='+method})
    return {'status':'one_cell_inspection_only','selected_month':winner['month'],
            'coverage_result_id':winner['result_id'],'eligible':winner['eligible'],'rows':result,
            'geometry_status':'unverified_no_map','species_claim':False,
            'limitations':['Sardinops genus is not Japanese sardine species.',
                           'Recorded non-detection does not establish biological absence.',
                           'This table does not establish a multi-area spatial distribution.']}


def verify(bundle, manifest, *, sealed):
    counts=independent_counts(bundle)
    source_hash=digest(bundle['inputs']['canonical'])
    source_matches=source_hash==manifest['canonical_source_sha256']
    identity_matches=bundle['manifest']['id']==manifest['analysis_id']
    protocol=manifest['protocol_id']
    scope={'version':1,'sources':{f:{'enabled':f=='edna_metabarcoding','filters':{}} for f in FAMILIES}}
    # Rendering must not consult a live publication pointer in an offline replay.
    from unittest.mock import patch
    with patch('ingestion.regional_publication.analysis_publication',lambda _:None):
        en=render_research(bundle,scope,QUESTIONS['fish_frequency'][0],ResearchIntent(kind='fish_frequency',protocol_id=protocol))
        ja=render_research(bundle,scope,FREQUENCY_JA,ResearchIntent(kind='fish_frequency',protocol_id=protocol))
    parity=not en.reason and not ja.reason and [(d['table'],d['result_rows']) for d in en.documents]==[(d['table'],d['result_rows']) for d in ja.documents]
    years=Counter(str(m['year']) for m in bundle['tables']['membership'] if m['protocol_id']==protocol)
    expected=manifest['expected_miseq_year_units']
    year_matches=all(years.get(y,0)==n for y,n in expected.items())
    protocol_matches=counts['protocol_units']==manifest['expected_protocol_units']
    report={'sealed':sealed,'analysis_identity_matches':identity_matches,'canonical_source_matches':source_matches,
            'actual_analysis_id':bundle['manifest']['id'],'expected_analysis_id':manifest['analysis_id'],
            'actual_canonical_source_sha256':source_hash,'protocol_id':protocol,
            'assignment_method':bundle['recipe']['assignment_method'],
            'japanese_english_row_parity':parity,'miseq_year_counts':{y:years.get(y,0) for y in expected},
            'expected_counts_match':year_matches and protocol_matches,**counts,
            'exact_artifact_verification_passed':sealed and identity_matches and source_matches and parity and year_matches and protocol_matches,
            'conference_ready':False,'fresh_production_validation':False,'independent_scientific_approval':False,
            'organizer_examples':manifest['organizer_examples']}
    return report, {'en':en.answer,'ja':ja.answer}, genus_inspection(bundle,protocol)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--bundle',type=Path,help='Downloaded sealed analysis directory named by its ID')
    group.add_argument('--local-preview',type=Path,help='Local result JSON; never marked deployed or ready')
    parser.add_argument('--output',type=Path,required=True,help='Fresh private directory outside the repository')
    parser.add_argument('--artifact-index',type=Path,help='Retained provisional-demos publication index')
    parser.add_argument('--artifact-receipt',type=Path,help='Retained registry receipt for this bundle')
    args=parser.parse_args(argv)
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error('Private evidence output must be outside the repository')
    if args.output.exists():
        parser.error('Refuse to overwrite retained evidence')
    registration = None
    conference_manifest = json.loads(MANIFEST.read_text())
    if args.bundle:
        if not args.artifact_index or not args.artifact_receipt:
            parser.error('Sealed verification requires --artifact-index and --artifact-receipt')
        registration = verify_registration(args.bundle, args.artifact_index, args.artifact_receipt,
            expected_receipt_sha256=conference_manifest['artifact_registration']['receipt_sha256'])
        from ingestion.edna_analysis_bundle import _decode_analysis
        manifest,contents=read_bundle(args.bundle.parent,args.bundle.name)
        bundle=_decode_analysis(args.bundle.name,manifest,contents)
    else:
        if args.artifact_index or args.artifact_receipt:
            parser.error('Publication registration arguments require --bundle')
        from ingestion.provisional_research_bundle import ProvisionalRecipe,build_demo
        from ingestion.artifact_store import BoundedLocalStore
        preview=json.loads(BoundedLocalStore(args.local_preview.resolve().parent).read(
            args.local_preview.name, max_bytes=128 * 1024 * 1024).data)
        expected=build_demo(ProvisionalRecipe.model_validate(preview['recipe']),preview['inputs'])
        if preview!=expected:
            raise ValueError('Local preview does not match its complete inputs')
        bundle={'manifest':{'id':preview['analysis_id'],'schema_version':3},**{k:preview[k] for k in ('recipe','inputs','tables')}}
    report,answers,genus=verify(bundle,conference_manifest,sealed=bool(args.bundle))
    report['artifact_registration'] = registration
    args.output.mkdir(parents=True,mode=0o700)
    for name,value in [('verification.json',report),('genus-inspection.json',genus)]:
        (args.output/name).write_bytes(canonical_bytes(value))
    for language,answer in answers.items():
        (args.output/('fish-frequency-'+language+'.md')).write_text(answer)
    scope={'version':1,'sources':{f:{'enabled':f=='edna_metabarcoding','filters':{}} for f in FAMILIES}}
    from unittest.mock import patch
    with patch('ingestion.regional_publication.analysis_publication',lambda _:None):
        rendered=render_research(bundle,scope,FREQUENCY_JA,ResearchIntent(
            kind='fish_frequency',protocol_id=report['protocol_id']))
    (args.output/'rendered-context-ja.json').write_bytes(canonical_bytes([
        {**d,'doc_id':d['id'],'context_type':'analysis'} for d in rendered.documents]))
    snapshots={'input_path':str((args.bundle or args.local_preview).resolve()),
               'analysis_id':report['actual_analysis_id'],'sealed':report['sealed'],
               'artifact_registration':registration,
               'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in args.output.iterdir() if p.is_file()},
               'production_database_written':False,'paid_model_calls':0}
    (args.output/'package-receipt.json').write_bytes(canonical_bytes(snapshots))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['exact_artifact_verification_passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
