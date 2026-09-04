"""Read-only verified analysis artifacts; generation is a manual batch operation."""
import csv
import io
import json
import zipfile
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
import config
from ingestion.provenance_snapshot import SnapshotError, SnapshotNotFound

from ingestion.edna_analysis_bundle import TABLES, analysis_catalog, analysis_root, analysis_status, load_analysis
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
    if table not in TABLES:
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


@router.get('/catalog')
def catalog():
    try:
        return {'runs': analysis_catalog()}
    except (ValueError, OSError, KeyError, SnapshotError) as exc:
        raise HTTPException(409, 'Analysis catalog integrity check failed') from exc


@router.get('/runs/{analysis_id}')
def detail(analysis_id: str):
    bundle = _load(analysis_id)
    return dict(analysis_id=analysis_id, status=analysis_status(bundle), recipe=bundle['recipe'],
                manifest=bundle['manifest'], tables=list(TABLES))


@router.get('/runs/{analysis_id}/tables/{table}')
def table(analysis_id: str, table: str, assignment_method: str | None = None,
          result_id: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0, le=10000000)):
    bundle = _load(analysis_id)
    rows = table_rows(bundle, table, assignment_method, result_id)
    return dict(analysis_id=analysis_id, total=len(rows), limit=limit, offset=offset, rows=rows[offset:offset+limit])


@router.get('/runs/{analysis_id}/provenance')
def provenance(analysis_id: str, table: str, result_id: str):
    bundle = _load(analysis_id)
    row = table_rows(bundle, table, result_id=result_id)[0]
    return dict(analysis_id=analysis_id, result=row, recipe=bundle['recipe'], manifest=bundle['manifest'],
                inputs=bundle['inputs'], status=analysis_status(bundle))


@router.get('/runs/{analysis_id}/export')
def export(analysis_id: str, table: str = 'diversity', assignment_method: str | None = None,
           result_id: str | None = None, format: Literal['csv', 'bundle'] = 'csv'):
    bundle = _load(analysis_id)
    if format == 'bundle':
        if assignment_method or result_id:
            raise HTTPException(400, 'Bundle export is the complete immutable analysis')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in ['manifest.json', *sorted(bundle['manifest']['files'])]:
                archive.writestr(name, bundle['files'][name])
        return Response(stream.getvalue(), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="edna-{analysis_id}.zip"'})
    rows = table_rows(bundle, table, assignment_method, result_id)
    fixed = ['analysis_id', 'table', 'recipe_sha256', 'input_sha256', 'rank', 'control_policy', 'min_read_count', 'recipe_methods', 'cohort', 'result_id']
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
        writer.writerow({k:safe(v) for k,v in dict(row, analysis_id=analysis_id, table=table,
            recipe_sha256=bundle['manifest']['recipe_sha256'], input_sha256=bundle['manifest']['input_sha256'],
            rank=bundle['recipe']['rank'], control_policy=bundle['recipe']['control_policy'],
            min_read_count=bundle['recipe']['min_read_count'], recipe_methods=bundle['recipe']['assignment_methods'],
            cohort=bundle['recipe']['cohort']).items()})
    return Response(stream.getvalue(), media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename="edna-{analysis_id}-{table}.csv"',
        'X-Export-Truncated': str(len(rows) > 25000).lower(), 'X-Analysis-Id': analysis_id,
    })
