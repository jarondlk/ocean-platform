import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text

import config
from db.models import CorpusBase
from ingestion.edna_analysis_bundle import read_canonical, run_analysis, load_analysis, analysis_status
from preprocessing.edna_recipe import AnalysisRecipe
from retrieval import edna_materializer as materializer
from retrieval.edna_publication import current_manifest
from scripts.load_db import _upsert_anemone_bundle
from tests.integration.test_anemone_postgres import _frames
from ingestion.immutable_bundle import digest

pytestmark = pytest.mark.skipif(os.environ.get('RUN_POSTGRES_INTEGRATION') != '1', reason='requires disposable PostgreSQL')


def test_snapshot_queries_and_serialized_publication(tmp_path, monkeypatch):
    engine = create_engine(config.DATABASE_URL)
    CorpusBase.metadata.create_all(engine)
    monkeypatch.setattr(config, 'SERVING_DIR', tmp_path/'serving')
    monkeypatch.setattr(config, 'ANALYSIS_DIR', tmp_path/'analysis')
    monkeypatch.setattr(materializer, 'get_engine', lambda: engine)
    monkeypatch.setattr('ingestion.edna_analysis_bundle.get_engine', lambda: engine)
    frames, _ = _frames('pr4-integration')
    # Unique canonical IDs isolate this committed concurrency fixture from the
    # rollback-based PR2 tests, including repeat runs against one test database.
    seed = uuid.uuid4().hex
    identities = ('snapshot_id', 'source_file_id', 'source_snapshot_id', 'first_seen_snapshot_id', 'last_seen_snapshot_id', 'sample_id', 'assay_id', 'detection_id', 'internal_standard_id')
    for frame in frames.values():
        for column in identities:
            if column in frame:
                frame[column] = frame[column].map(lambda value: digest([seed, value]))
    project = 'project-pr4-'+seed
    frames['edna_sample']['provider_project_id'] = project
    frames['edna_detection']['genus'] = 'Scomber'
    frames['edna_sample']['collection_date_utc'] = '2026-09-01T12:00:00+00:00'
    with engine.begin() as connection:
        _upsert_anemone_bundle(connection, frames=frames, manifest={'source_scope_level':'sample'})
    recipe = AnalysisRecipe.model_validate(dict(cohort={'provider_project_id':project, 'time_to':'2026-09-01'},
        assignment_methods=['qcauto_target'], rank='genus', control_policy='environmental_only'))
    assert len(read_canonical(recipe)['edna_sample']) == 1
    outcome = run_analysis(recipe, execute=True)
    assert outcome['table_counts']['diversity'] == 1
    assert analysis_status(load_analysis(outcome['analysis_id'])) == 'current'
    entered, release, second_read = threading.Event(), threading.Event(), threading.Event()
    real_ready, real_read = materializer.set_ready, materializer._read_active_frames
    count = 0

    def gate_ready(manifest):
        nonlocal count
        count += 1
        if count == 1:
            entered.set()
            assert release.wait(10)
        real_ready(manifest)

    def observe_read(connection):
        if entered.is_set():
            second_read.set()
        return real_read(connection)

    monkeypatch.setattr(materializer, 'set_ready', gate_ready)
    monkeypatch.setattr(materializer, '_read_active_frames', observe_read)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(materializer.materialize_edna_retrieval, execute=True)
        assert entered.wait(10)
        second = executor.submit(materializer.materialize_edna_retrieval, execute=True)
        try:
            assert not second_read.wait(0.2), 'Second snapshot started before first publication completed'
        finally:
            release.set()
        assert first.result(timeout=10)['documents'] == second.result(timeout=10)['documents']
    manifest = current_manifest()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT generation_id FROM corpus_publication WHERE channel='edna'")).scalar() == manifest['id']
    monkeypatch.setattr(materializer, '_write_artifacts', lambda *a, **kw: (_ for _ in ()).throw(OSError('fixture disk failure')))
    with pytest.raises(OSError, match='fixture disk'):
        materializer.materialize_edna_retrieval(execute=True)
    with pytest.raises(ValueError, match='incomplete'):
        current_manifest()
    engine.dispose()


def test_pr5_import_rollback_and_replay_are_edna_only(monkeypatch):
    import scripts.load_db as loader
    from scripts.run_anemone_job import import_normalized
    frames, _ = _frames('pr5-import')
    seed = uuid.uuid4().hex
    identifiers = ('snapshot_id', 'source_file_id', 'source_snapshot_id', 'first_seen_snapshot_id',
                   'last_seen_snapshot_id', 'sample_id', 'assay_id', 'detection_id', 'internal_standard_id')
    for frame in frames.values():
        for column in identifiers:
            if column in frame:
                frame[column] = frame[column].map(lambda value: digest([seed, value]))
    project = 'project-pr5-'+seed
    frames['edna_sample']['provider_project_id'] = project
    monkeypatch.setattr(loader, '_load_anemone_bundle_frames',
        lambda *a, **kw: (frames, {'source_scope_level':'sample'}))
    engine = create_engine(config.DATABASE_URL)
    def counts():
        with engine.connect() as connection:
            return (connection.execute(text('SELECT count(*) FROM app_user')).scalar(),
                    connection.execute(text('SELECT count(*) FROM edna_sample WHERE provider_project_id=:p'), {'p':project}).scalar())
    before = counts()
    assert import_normalized('a'*64, execute=False)['committed'] is False
    assert counts() == before
    assert import_normalized('a'*64, execute=True)['committed'] is True
    assert counts() == (before[0], 1)
    import_normalized('a'*64, execute=True)
    assert counts() == (before[0], 1)
    engine.dispose()
