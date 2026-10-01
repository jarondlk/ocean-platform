"""Exercise source-owned predicates and history constraints on PostgreSQL/pgvector."""
from contextlib import nullcontext
from itertools import product
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import config
from db.models import CorpusBase
from db.app_models import AppUser, ChatInteraction
from retrieval import hybrid_retriever
from retrieval.local_retriever import LocalRetriever
from tests.test_chat_source_scope import scope
from retrieval.source_scope import FAMILIES

pytestmark = pytest.mark.skipif(os.environ.get('RUN_POSTGRES_INTEGRATION') != '1', reason='requires disposable PostgreSQL')


def test_sixteen_subsets_and_independent_filters_match_both_rankers(monkeypatch):
    engine = create_engine(config.DATABASE_URL)
    CorpusBase.metadata.create_all(engine)
    unique = uuid.uuid4().hex
    query = 'sourcecheck'+unique
    docs = []
    for family in FAMILIES:
        for matching in (True, False):
            docs.append({'doc_id': unique+family+str(matching), 'source_type': family,
                         'event_id': unique+family+str(matching), 'sample_id': unique+str(matching),
                         'title': query, 'text': query, 'time': '2026-01-01T23:00:00Z' if matching else '2026-01-02',
                         'bay': 'O' if matching else 'I', 'station': 's1' if matching else 's2',
                         'lat': 0 if matching else -1, 'lon': 0 if matching else 1,
                         'provider_project_id': 'p' if matching else 'outside', 'is_control': False if matching else None})
    local = LocalRetriever()
    local.documents = docs
    local.bm25.fit([d['text'] for d in docs])
    monkeypatch.setattr(config, 'EDNA_ARTIFACT_URI', '')
    embedding = [1.0] * config.EMBEDDING_DIM
    monkeypatch.setattr(hybrid_retriever, 'embed_text', lambda q: embedding)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            for doc in docs:
                connection.execute(text('''INSERT INTO retrieval_document
                    (doc_id, source_type, event_id, sample_id, title, text, time, bay, station, lat, lon,
                     provider_project_id, is_control, embedding, embedding_provider, embedding_model, embedding_dim, text_tsv)
                    VALUES (:doc_id,:source_type,:event_id,:sample_id,:title,:text,:time,:bay,:station,:lat,:lon,
                            :provider_project_id,:is_control,CAST(:embedding AS vector),:embedding_provider,:embedding_model,:embedding_dim,to_tsvector('english',:text))'''),
                    {**doc, 'embedding': str(embedding), 'embedding_provider': config.MODEL_PROVIDER,
                     'embedding_model': config.EMBEDDING_MODEL, 'embedding_dim': config.EMBEDDING_DIM})
            monkeypatch.setattr(hybrid_retriever, 'get_session', lambda: nullcontext(connection))
            for bits in product((False, True), repeat=4):
                enabled = [family for family, bit in zip(FAMILIES, bits) if bit]
                envelope = scope(*enabled)
                envelope['sources']['ctd']['filters'] = {'bay': 'O', 'station': 's1', 'time_to': '2026-01-01'}
                envelope['sources']['metagenome']['filters'] = {'bay': 'O'}
                envelope['sources']['remote_sensing']['filters'] = {'lat_min': 0, 'lon_max': 0}
                envelope['sources']['edna_metabarcoding']['filters'] = {'provider_project_id': 'p', 'is_control': False}
                for family in ('ctd', 'metagenome', 'edna_metabarcoding'):
                    envelope['sources'][family]['filters']['sample_id'] = unique+'True'
                expected = {d['doc_id'] for d in docs if d['source_type'] in enabled and d['doc_id'].endswith('True')}
                results = hybrid_retriever.hybrid_search(query, k=25, evidence_scope=envelope, vector_weight=0, fts_weight=1)
                assert {r.doc_id for r in results} == expected
                assert {r['doc_id'] for r in local.search(query, k=25, evidence_scope=envelope, vector_weight=0, fts_weight=1)} == expected
                vector_results = hybrid_retriever.hybrid_search(query, k=25, evidence_scope=envelope, vector_weight=1, fts_weight=0)
                assert {r.doc_id for r in vector_results} == expected
            from orchestration.unified import _expand_linked_evidence
            monkeypatch.setattr('db.connection.get_session', lambda: nullcontext(connection))
            ctd = next(d for d in docs if d['source_type'] == 'ctd' and d['doc_id'].endswith('True'))
            satellite = next(d for d in docs if d['source_type'] == 'remote_sensing' and d['doc_id'].endswith('True'))
            connection.execute(text("INSERT INTO cross_source_link(source_event_id,target_event_id,link_type) VALUES (:a,:b,'same_day')"), {'a': ctd['event_id'], 'b': satellite['event_id']})
            assert _expand_linked_evidence([ctd], 10, scope('ctd')) == []
            assert [d['doc_id'] for d in _expand_linked_evidence([ctd], 10, scope('ctd', 'remote_sensing'))] == [satellite['doc_id']]
        finally:
            transaction.rollback()
    engine.dispose()


def test_migrated_history_retains_new_abstention_reasons():
    engine = create_engine(config.DATABASE_URL)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20261001_0014'
            with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
                user = AppUser(id=uuid.uuid4(), email=uuid.uuid4().hex+'@test.invalid', auth_provider='test', auth_subject=uuid.uuid4().hex,
                               role='researcher', account_type='research', status='active')
                session.add(user)
                session.flush()
                for reason in ('no_sources_selected', 'source_disabled', 'freshness_unavailable'):
                    interaction = ChatInteraction(user_id=user.id, query='source check', model='test', status='completed',
                        request_options={'evidence_scope': scope()}, outcome='abstained', abstention_reason=reason)
                    session.add(interaction)
                    session.flush()
                    assert session.get(ChatInteraction, interaction.id).abstention_reason == reason
        finally:
            transaction.rollback()
    engine.dispose()
