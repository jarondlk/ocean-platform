"""Selection choices match local evidence and full active canonical taxonomy."""
from dataclasses import asdict
import json
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import config
from retrieval import filter_options as choices
from retrieval.edna_document_builder import build_edna_documents
from retrieval.edna_materializer import _document_frame, _merge_documents, _read_active_frames
from scripts.load_db import _upsert_anemone_bundle
from tests.integration.test_anemone_catalogue_postgres import database as catalogue_database
from tests.integration.test_anemone_postgres import _frames
from tests.test_chat_source_scope import scope

pytestmark = pytest.mark.skipif(os.environ.get('RUN_POSTGRES_INTEGRATION') != '1', reason='requires disposable PostgreSQL')


@pytest.fixture
def database(tmp_path, monkeypatch):
    yield from catalogue_database.__wrapped__(tmp_path, monkeypatch)


def test_available_choices_match_local_corpus_and_restrict_pinned_members(database, monkeypatch, tmp_path):
    frames, ids = _frames(uuid.uuid4().hex)
    frames['edna_detection']['assigned_taxon_name'] = 'Rare fish'
    frames['edna_detection']['genus'] = 'Rare genus'
    frames['edna_detection']['kingdom'] = 'Animalia'
    with database.begin() as connection:
        _upsert_anemone_bundle(connection, frames=frames, manifest={'source_scope_level': 'sample'})
        documents = build_edna_documents(*_read_active_frames(connection))
        _merge_documents(connection, _document_frame(documents))
        connection.execute(text("INSERT INTO retrieval_document (doc_id,source_type,title,text,bay,station,sample_id,active) VALUES "
                                "('ctd1','ctd','a','a','O','s1','sample1',true),"
                                "('ctd2','ctd','b','b','O','s2','sample2',true),"
                                "('ctd3','ctd','c','c','I','s3','sample3',true),"
                                "('hidden','ctd','hidden','hidden','O','hidden','hidden',false)"))
    monkeypatch.setattr(choices, 'get_session', lambda: Session(database))
    local = [asdict(d) for d in documents] + [
        {'doc_id': 'ctd1', 'source_type': 'ctd', 'bay': 'O', 'station': 's1', 'sample_id': 'sample1'},
        {'doc_id': 'ctd2', 'source_type': 'ctd', 'bay': 'O', 'station': 's2', 'sample_id': 'sample2'},
        {'doc_id': 'ctd3', 'source_type': 'ctd', 'bay': 'I', 'station': 's3', 'sample_id': 'sample3'},
    ]
    serving = tmp_path / 'local'
    serving.mkdir()
    (serving / 'retrieval_documents.jsonl').write_text('\n'.join(json.dumps(d, default=str) for d in local))
    monkeypatch.setattr(config, 'SERVING_DIR', serving)
    envelope = scope()
    envelope['sources']['ctd']['filters'] = {'bay': 'O', 'station': 's1'}
    for field, search in ((None, ''), ('taxon', 'RARE'), ('provider', "' OR TRUE --")):
        options = dict(family='edna_metabarcoding', field=field, search=search, members=[ids['sample_id']], methods=['qcauto_target'])
        sql = choices.filter_options(envelope, pg_available=True, **options)
        fallback = choices.filter_options(envelope, pg_available=False, **options)
        assert sql['sources'] == fallback['sources']
    sql = choices.filter_options(envelope, pg_available=True)
    assert sql['sources']['ctd']['fields']['station']['values'] == ['s1', 's2']
    assert sql['sources']['ctd']['fields']['sample_id']['values'] == ['sample1']
    assert sql['sources']['edna_metabarcoding']['fields']['taxon']['values'] == ['Animalia', 'Rare fish', 'Rare genus']
    assert sql['sources']['edna_metabarcoding']['fields']['is_control']['values'] == ['false']
    assert choices.filter_options(envelope, pg_available=True, family='edna_metabarcoding', members=[], methods=[])['sources']['edna_metabarcoding']['fields']['taxon']['values'] == []
    with database.begin() as connection:
        connection.execute(text('UPDATE edna_detection SET active = false'))
    assert choices.filter_options(envelope, pg_available=True, family='edna_metabarcoding')['sources']['edna_metabarcoding']['fields']['taxon']['values'] == []
