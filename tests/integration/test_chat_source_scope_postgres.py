"""Exercise source-owned predicates and history constraints on PostgreSQL/pgvector."""
from contextlib import nullcontext, contextmanager
from itertools import product
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import config
from alembic.config import Config
from alembic.script import ScriptDirectory
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
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == ScriptDirectory.from_config(Config('alembic.ini')).get_current_head()
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


def test_chat_lifecycle_independent_readback_retains_scope_effective_settings_and_evidence(monkeypatch):
    """Call the real API/record lifecycle, then read with a fresh ORM session."""
    from fastapi.testclient import TestClient
    import api.auth as auth
    import api.chat_records as records
    import api.main as api
    import config
    from api.auth import CurrentUser, ROLE_PERMISSIONS
    engine = create_engine(config.DATABASE_URL)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            @contextmanager
            def session_scope():
                with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
                    with session.begin():
                        yield session
            with session_scope() as session:
                user = AppUser(id=uuid.uuid4(), email=uuid.uuid4().hex+'@test.invalid', auth_provider='test', auth_subject=uuid.uuid4().hex,
                               role='researcher', account_type='research', status='active')
                session.add(user)
                session.flush()
                current = CurrentUser(id=user.id, email=user.email, display_name=None, auth_provider='test', role=user.role,
                                      account_type=user.account_type, status=user.status, permissions=ROLE_PERMISSIONS[user.role])
            monkeypatch.setattr(records, 'get_session', session_scope)
            monkeypatch.setattr(auth, 'authenticate_request', lambda request: current)
            monkeypatch.setattr(config, 'MODEL_PROVIDER', 'vertex')
            document = {'doc_id': 'ctd-history-qa', 'source_type': 'ctd', 'title': 'CTD fixture', 'text': 'Surface temperature is 12 C.'}
            monkeypatch.setattr(api, 'retrieve_with_expansion', lambda *a, **k: {'primary': [document], 'linked': [], 'diagnostics': {}})
            class Runtime:
                def chat(self, **kwargs):
                    return 'Surface temperature is 12 C [ctd-history-qa].'
            monkeypatch.setattr(api, 'get_model_runtime', lambda: Runtime())
            client = TestClient(api.app)
            cases = [
                ('Explain the recorded temperature', scope('ctd'), 'answered', None),
                ('Has ANEMONE data from last week arrived?', scope('edna_metabarcoding'), 'abstained', 'freshness_unavailable'),
                ('How many ANEMONE samples in Japan?', scope('edna_metabarcoding'), 'abstained', 'aggregate_scope_required'),
                ('Explain the recorded temperature', scope(), 'abstained', 'no_sources_selected'),
            ]
            for query, envelope, outcome, reason in cases:
                response = client.post('/chat', json={'query': query, 'evidence_scope': envelope, 'inject_analysis': False, 'inject_reliability': False, 'repeat_penalty': 1.5, 'num_ctx': 2048})
                assert response.status_code == 200, response.text
                data = response.json()
                with session_scope() as reader:
                    row = reader.get(ChatInteraction, uuid.UUID(data['interaction_id']))
                    assert row.status == 'completed' and row.outcome == outcome and row.abstention_reason == reason
                    assert row.answer == data['answer'] and row.query == query
                    assert row.request_options['evidence_scope'] == data['options']['evidence_scope']
                    assert row.request_options['generation'] == data['options']['generation']
                    assert 'repeat_penalty' not in row.request_options['generation'] and 'num_ctx' not in row.request_options['generation']
                    assert row.corpus_fingerprint == records.content_sha256(row.evidence_snapshot)
                    assert row.prompt_sha256 and row.completed_at and row.latency_ms >= 0
                    assert [d['doc_id'] for d in row.evidence_snapshot['sources']] == ([document['doc_id']] if outcome == 'answered' else [])
                    assert row.answer_audit_snapshot == data['answer_audit']
            monkeypatch.setattr(api, 'retrieve_with_expansion', lambda *a, **k: {'primary': [], 'linked': [], 'diagnostics': {}})
            data = client.post('/chat', json={'query': 'Explain absent temperature records', 'evidence_scope': scope('ctd'), 'inject_analysis': False, 'inject_reliability': False}).json()
            with session_scope() as reader:
                row = reader.get(ChatInteraction, uuid.UUID(data['interaction_id']))
                assert row.outcome == 'abstained' and row.abstention_reason == 'no_matching_evidence'
                assert row.answer == data['answer'] and row.evidence_snapshot['sources'] == []
        finally:
            transaction.rollback()
    engine.dispose()
