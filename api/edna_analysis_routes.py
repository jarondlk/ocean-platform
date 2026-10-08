"""Read-only verified analysis artifacts; generation is a manual batch operation."""
import csv
import io
import json
import zipfile
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
import config
from ingestion.provenance_snapshot import SnapshotError, SnapshotNotFound

from ingestion.edna_analysis_bundle import analysis_catalog, analysis_root, analysis_status, load_analysis
from ingestion.immutable_bundle import validate_id

router = APIRouter(prefix='/data/edna/analysis')


def _load(identity):
    try:
        validate_id(identity)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not config.EDNA_ARTIFACT_URI and not (analysis_root()/identity).exists():
        raise HTTPException(404, 'Unknown eDNA analysis')
    try:
        return load_analysis(identity)
    except SnapshotNotFound as exc:
        raise HTTPException(404, 'Unknown eDNA analysis') from exc
    except (ValueError, KeyError, OSError, SnapshotError) as exc:
        raise HTTPException(409, 'Analysis integrity check failed') from exc


def table_rows(bundle, table, method=None, result_id=None):
    if table not in bundle['tables']:
        raise HTTPException(400, 'Unknown analysis table')
    if method not in {None, 'qcauto_target', 'qcauto_95pct_3nn_target'}:
        raise HTTPException(400, 'Invalid assignment method')
    if result_id:
        try:
            validate_id(result_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    rows = bundle['tables'][table]
    if method:
        rows = [r for r in rows if r.get('assignment_method') == method]
    if result_id:
        rows = [r for r in rows if r['result_id'] == result_id]
        if not rows:
            raise HTTPException(404, 'Unknown result in this analysis table/method')
    return rows


def research_filter_rows(bundle, rows, filters):
    if any(value is not None for value in filters.values()):
        if bundle['manifest'].get('schema_version') not in {2, 3}:
            raise HTTPException(400, 'Research filters require a detection-frequency analysis')
        rows = [r for r in rows if all(value is None or r.get(key) == value for key,value in filters.items())]
    return rows


@router.get('/catalog')
def catalog():
    try:
        return {'runs': analysis_catalog()}
    except (ValueError, OSError, KeyError, SnapshotError) as exc:
        raise HTTPException(409, 'Analysis catalog integrity check failed') from exc


@router.get('/runs/{analysis_id}')
def detail(analysis_id: str):
    bundle = _load(analysis_id)
    from ingestion.regional_publication import analysis_publication
    return dict(analysis_id=analysis_id, operational_publication=analysis_publication(bundle), status=analysis_status(bundle), recipe=bundle['recipe'],
                manifest=bundle['manifest'], tables=list(bundle['tables']))


@router.get('/runs/{analysis_id}/tables/{table}')
def table(analysis_id: str, table: str, assignment_method: str | None = None,
          result_id: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0, le=10000000),
          protocol_id: Annotated[str | None, Query(pattern=r'^[a-f0-9]{64}$')] = None, taxon_key: Annotated[str | None, Query(pattern=r'^[a-f0-9]{64}$')] = None,
          area_id: Annotated[str | None, Query(max_length=255)] = None, period_kind: Literal['year','season','month'] | None = None,
          bin: Annotated[str | None, Query(max_length=32)] = None):
    bundle = _load(analysis_id)
    rows = table_rows(bundle, table, assignment_method, result_id)
    filters = {'protocol_id': protocol_id, 'taxon_key': taxon_key, 'area_id': area_id, 'period_kind': period_kind, 'bin': bin}
    rows = research_filter_rows(bundle, rows, filters)
    return dict(analysis_id=analysis_id, total=len(rows), limit=limit, offset=offset, rows=rows[offset:offset+limit])


@router.get('/runs/{analysis_id}/choices')
def choices(analysis_id: str):
    from ingestion.immutable_bundle import digest
    from preprocessing.edna_analysis import protocol, taxon_key
    bundle = _load(analysis_id)
    if bundle['manifest'].get('schema_version') not in {2, 3}:
        raise HTTPException(400, 'Research choices require a detection-frequency analysis')
    definition = bundle['inputs']['provisional_sampling'] if bundle['manifest'].get('schema_version') == 3 else bundle['inputs']['sampling_registry']['definition']
    taxa, protocols = {}, {}
    for row in bundle['inputs']['canonical']['edna_detection']:
        lineage = taxon_key(row, 'species')
        if lineage and row.get('class') in bundle['recipe']['fish_classes']:
            taxa[digest(lineage)] = row['species']
    for assay in bundle['inputs']['canonical']['edna_assay']:
        value = protocol(assay)
        protocols[digest(value)] = {key:value[key] for key in ('target_gene','primer_set','sequencing_method','library_layout')}
    tables = {name:{field:sorted({r[field] for r in rows if r.get(field) is not None}) for field in ('protocol_id','taxon_key','area_id','period_kind','bin') if any(r.get(field) is not None for r in rows)} for name,rows in bundle['tables'].items()}
    return {'areas': [{key:area[key] for key in ('area_id','label','geometry_type','west','east','south','north','coordinate_uncertainty_km')} for area in definition['areas']],
            'taxa': [{'taxon_key':key,'species':value} for key,value in sorted(taxa.items())],
            'protocols': [{'protocol_id':key,**value} for key,value in sorted(protocols.items())], 'tables':tables}


@router.get('/runs/{analysis_id}/provenance')
def provenance(analysis_id: str, table: str, result_id: str):
    bundle = _load(analysis_id)
    row = table_rows(bundle, table, result_id=result_id)[0]
    return dict(analysis_id=analysis_id, result=row, recipe=bundle['recipe'], manifest=bundle['manifest'],
                inputs=bundle['inputs'], status=analysis_status(bundle))


@router.get('/runs/{analysis_id}/export')
def export(analysis_id: str, table: str = 'diversity', assignment_method: str | None = None,
           result_id: str | None = None, format: Literal['csv', 'bundle'] = 'csv',
           protocol_id: Annotated[str | None, Query(pattern=r'^[a-f0-9]{64}$')] = None, taxon_key: Annotated[str | None, Query(pattern=r'^[a-f0-9]{64}$')] = None,
           area_id: Annotated[str | None, Query(max_length=255)] = None, period_kind: Literal['year','season','month'] | None = None,
           bin: Annotated[str | None, Query(max_length=32)] = None):
    bundle = _load(analysis_id)
    filters = {'protocol_id': protocol_id, 'taxon_key': taxon_key, 'area_id': area_id, 'period_kind': period_kind, 'bin': bin}
    if format == 'bundle':
        if assignment_method or result_id or any(value is not None for value in filters.values()):
            raise HTTPException(400, 'Bundle export is the complete immutable analysis')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in ['manifest.json', *sorted(bundle['manifest']['files'])]:
                archive.writestr(name, bundle['files'][name])
        return Response(stream.getvalue(), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="edna-{analysis_id}.zip"'})
    rows = table_rows(bundle, table, assignment_method, result_id)
    rows = research_filter_rows(bundle, rows, filters)
    fixed = ['analysis_id', 'table', 'recipe_sha256', 'input_sha256', 'rank', 'control_policy', 'min_read_count', 'recipe_methods', 'cohort', 'result_id']
    research = bundle['manifest'].get('schema_version') in {2, 3}
    metadata = {key:bundle['recipe'][key] for key in ('analysis_kind','analysis_unit','threshold_level','calendar','sst_panel_id','sst_max_time_hours','sst_min_month_day_fraction') if key in bundle['recipe']} if research else {}
    if research:
        from ingestion.immutable_bundle import digest
        metadata['sampling_registry_id'] = digest(bundle['inputs']['provisional_sampling'] if bundle['manifest'].get('schema_version') == 3 else bundle['inputs']['sampling_registry'])
        fixed += list(metadata)
    from ingestion.regional_publication import analysis_publication
    accepted = analysis_publication(bundle)
    if accepted:
        metadata['operational_publication_id'] = accepted['publication_id']
        metadata['operational_approval_basis'] = accepted['approval_basis']
        fixed.extend(['operational_publication_id', 'operational_approval_basis'])
    columns = fixed + sorted({k for r in rows for k in r if k not in fixed})
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    def safe(value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))):
            return "'" + value
        return value
    for row in rows[:25000]:
        writer.writerow({k:safe(v) for k,v in dict(row, **metadata, analysis_id=analysis_id, table=table,
            recipe_sha256=bundle['manifest']['recipe_sha256'], input_sha256=bundle['manifest']['input_sha256'],
            rank=bundle['recipe']['rank'], control_policy=bundle['recipe']['control_policy'],
            min_read_count=bundle['recipe']['min_read_count'], recipe_methods=bundle['recipe'].get('assignment_methods', [bundle['recipe'].get('assignment_method')]),
            cohort=bundle['recipe'].get('cohort', {k:bundle['recipe'][k] for k in ('region_id','region_version','identity_version','time_from','time_to','calendar') if k in bundle['recipe']})).items()})
    return Response(stream.getvalue(), media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename="edna-{analysis_id}-{table}.csv"',
        'X-Export-Truncated': str(len(rows) > 25000).lower(), 'X-Analysis-Id': analysis_id,
    })
