import io
import json
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient

import config
from api.main import app, _context_document
from api.auth import route_permission
from ingestion.edna_analysis_bundle import publish_analysis, provenance_descriptors, analysis_trace
from preprocessing.edna_analysis import build_analysis
from tests.test_edna_analysis import fixture

client = TestClient(app)


def test_analysis_read_export_and_exact_provenance(tmp_path, monkeypatch):
    recipe, source = fixture()
    monkeypatch.setattr(config, 'ANALYSIS_DIR', tmp_path)
    monkeypatch.setattr('ingestion.edna_analysis_bundle.read_canonical', lambda _: source)
    result = build_analysis(recipe, source)
    publish_analysis(result)
    base = '/data/edna/analysis'
    run = base+'/runs/'+result['analysis_id']
    assert client.get(base+'/catalog').json()['runs'][0]['status'] == 'current'
    assert client.get(run).json()['recipe']['rank'] == 'genus'
    rows = client.get(run+'/tables/diversity?assignment_method=qcauto_target').json()
    assert rows['total'] == 1
    rid = rows['rows'][0]['result_id']
    trace = client.get(run+f'/provenance?table=diversity&result_id={rid}').json()
    assert trace['inputs']['canonical']['edna_detection']
    assert client.get(run+'/tables/diversity?result_id='+'f'*64).status_code == 404
    assert client.get(run+'/tables/bad').status_code == 400
    csv = client.get(run+'/export?table=diversity&assignment_method=qcauto_target')
    assert csv.status_code == 200 and csv.headers['x-export-truncated'] == 'false'
    assert 'recipe_sha256' in csv.text
    zipped = client.get(run+'/export?format=bundle')
    with zipfile.ZipFile(io.BytesIO(zipped.content)) as z:
        assert 'inputs.json' in z.namelist()
        assert json.loads(z.read('recipe.json'))['rank'] == 'genus'
    assert client.get(base+'/runs/bad').status_code == 400
    assert client.get(base+'/runs/'+'f'*64).status_code == 404
    descriptor = provenance_descriptors()[0]
    doc_id = f"analysis_edna_{result['analysis_id']}_diversity"
    assert analysis_trace(doc_id, [descriptor])['found']
    ctx = _context_document(dict(id=doc_id, analysis_id=result['analysis_id'], table='diversity'), 'analysis')
    assert ctx.analysis_id == result['analysis_id']
    assert route_permission('GET', run+'/export') == 'data:export'
    assert route_permission('GET', run+'/provenance') == 'provenance:read'


def test_retrieval_analysis_scope_cannot_leak_other_cohorts(tmp_path, monkeypatch):
    recipe, source = fixture()
    monkeypatch.setattr(config, 'ANALYSIS_DIR', tmp_path)
    monkeypatch.setattr('ingestion.edna_analysis_bundle.read_canonical', lambda _: source)
    result = build_analysis(recipe, source)
    publish_analysis(result)
    body = dict(query='Compare diversity', analysis_id=result['analysis_id'])
    with patch('api.main.retrieve_with_expansion', return_value={'primary':[], 'linked':[]}) as retrieve:
        response = client.post('/retrieve', json=body)
        assert response.status_code == 200
        assert retrieve.call_args.kwargs['provider_project_id'] == 'project-science'
        assert retrieve.call_args.kwargs['source_type'] == 'edna_metabarcoding'
        assert retrieve.call_args.kwargs['is_control'] is False
    assert client.post('/retrieve', json={**body, 'provider_project_id':'other'}).status_code == 409
    assert client.post('/retrieve', json={**body, 'taxon':'A'}).status_code == 409
    source['edna_detection'][0]['read_count'] = 100
    assert client.post('/retrieve', json=body).status_code == 409


def test_csv_formula_escaping_and_integrity_errors(tmp_path, monkeypatch):
    recipe, source = fixture()
    source['edna_detection'][0]['genus'] = '=untrusted_formula'
    monkeypatch.setattr(config, 'ANALYSIS_DIR', tmp_path)
    result = build_analysis(recipe, source)
    publish_analysis(result)
    run = '/data/edna/analysis/runs/'+result['analysis_id']
    csv = client.get(run+'/export?table=composition')
    assert "'=untrusted_formula" in csv.text
    assert client.get(run+'/export?format=bundle&assignment_method=qcauto_target').status_code == 400
    assert client.get(run+'/tables/diversity?assignment_method=bad').status_code == 400
    (tmp_path/'edna'/result['analysis_id']/'inputs.json').write_text('{}')
    assert client.get(run).status_code == 409
