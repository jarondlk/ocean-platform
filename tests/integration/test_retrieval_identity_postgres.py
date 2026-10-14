"""C05 result acceptance on an explicitly owned disposable pgvector database."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import ipaddress
import os
import re
import subprocess
import sys
import types
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import config
from db import vector_store
from db.embedding_identity import EmbeddingIdentity, IdentifiedEmbedding
from db.models import RetrievalDocument
from retrieval import hybrid_retriever
from tests.test_chat_source_scope import scope

pytestmark = pytest.mark.skipif(
    os.environ.get('RUN_POSTGRES_INTEGRATION') != '1',
    reason='requires explicit disposable C05_TEST_DATABASE_URL with pgvector',
)
BASELINE = '58ee4b4fc3770fdc3c334aca592b6b5d0b39a0d8'
PROVIDER = 'c05-synthetic-provider'
MODEL = 'c05-synthetic-model'


def _verified_server(address):
    observed = ipaddress.ip_address(address or '')
    if observed.is_loopback:
        return True
    pinned = os.environ.get('C05_TEST_SERVER_ADDRESS', '')
    if os.environ.get('GITHUB_ACTIONS') != 'true' or not pinned:
        return False
    private = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
    return observed == ipaddress.ip_address(pinned) and any(observed in network for network in private)


@pytest.fixture(scope='module')
def disposable_database():
    raw = os.environ.get('C05_TEST_DATABASE_URL')
    if not raw:
        pytest.fail('C05_TEST_DATABASE_URL is required; DATABASE_URL is never used')
    url = make_url(raw)
    if (url.get_backend_name() != 'postgresql' or url.host not in {'127.0.0.1', 'localhost', '::1'}
            or not re.fullmatch(r'ocean_c05_[a-z0-9_]+', url.database or '')):
        pytest.fail('C05 requires a dedicated ocean_c05_* loopback PostgreSQL database')
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            identity = connection.execute(text(
                "SELECT current_database(), host(inet_server_addr()), inet_server_port(), "
                "current_setting('server_version'), current_setting('transaction_isolation'), "
                "(SELECT extversion FROM pg_extension WHERE extname='vector')"
            )).one()
            assert identity[0] == url.database and _verified_server(identity[1])
            assert identity[4] == 'read committed' and identity[5]
        print(f'C05 disposable pgvector identity: database={identity[0]} address={identity[1]} '
              f'port={identity[2]} PostgreSQL={identity[3]} isolation={identity[4]} pgvector={identity[5]}')
        yield engine, url
    finally:
        engine.dispose()


@dataclass
class IsolatedStore:
    engine: object
    factory: object

    @contextmanager
    def session(self):
        with self.factory.begin() as session:
            yield session

    def query_vector(self, dimension=None):
        dimension = dimension or config.EMBEDDING_DIM
        return IdentifiedEmbedding([1.0] + [0.0] * (dimension - 1),
                                   EmbeddingIdentity(PROVIDER, MODEL, dimension))

    def seed(self, doc_id, *, provider=PROVIDER, model=MODEL, dimension=None,
             source='metagenome', sample='allowed', active=True, aligned=True, body='c05identitytoken'):
        vector = [1.0, 0.0] if aligned else [0.0, 1.0]
        vector += [0.0] * (config.EMBEDDING_DIM - 2)
        with self.engine.begin() as connection:
            connection.execute(text(
                'INSERT INTO retrieval_document '
                '(doc_id,source_type,sample_id,title,text,text_tsv,embedding,embedding_provider,'
                'embedding_model,embedding_dim,active,metadata_json) VALUES '
                "(:id,:source,:sample,'Synthetic C05 fixture',:body,to_tsvector('english',:body),"
                "CAST(:vector AS vector),:provider,:model,:dimension,:active,'{}')"
            ), {'id': doc_id, 'source': source, 'sample': sample, 'body': body,
                'vector': str(vector), 'provider': provider, 'model': model,
                'dimension': config.EMBEDDING_DIM if dimension is None else dimension, 'active': active})


@pytest.fixture
def isolated(disposable_database, monkeypatch):
    observer, url = disposable_database
    schema = 'c05_' + uuid.uuid4().hex
    with observer.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={
        'options': f'-csearch_path={schema},public -cstatement_timeout=15000',
    })
    try:
        RetrievalDocument.__table__.create(engine)
        store = IsolatedStore(engine, sessionmaker(bind=engine, expire_on_commit=False))
        monkeypatch.setattr(vector_store, 'get_session', store.session)
        monkeypatch.setattr(hybrid_retriever, 'get_session', store.session)
        monkeypatch.setattr(vector_store, 'embed_query', lambda _query: store.query_vector())
        monkeypatch.setattr(hybrid_retriever, 'embed_query', lambda _query: store.query_vector())
        monkeypatch.setattr(config, 'EDNA_ARTIFACT_URI', '')
        yield store
    finally:
        engine.dispose()
        with observer.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.mark.parametrize('entry', ['standalone', 'hybrid'])
def test_same_dimension_wrong_identity_and_missing_identity_never_rank(isolated, entry):
    isolated.seed('compatible', aligned=False)
    cases = [
        ('wrong-provider', {'provider': 'another-provider'}),
        ('wrong-model', {'model': 'another-model'}),
        ('wrong-dimension', {'dimension': config.EMBEDDING_DIM + 1}),
        ('missing-provider', {'provider': None}),
        ('missing-model', {'model': None}),
    ]
    for name, values in cases:
        isolated.seed(name, **values)
    isolated.seed('missing-dimension')
    with isolated.engine.begin() as connection:
        connection.execute(text("UPDATE retrieval_document SET embedding_dim=NULL WHERE doc_id='missing-dimension'"))
    isolated.seed('inactive', active=False)
    isolated.seed('wrong-source', source='ctd')
    if entry == 'standalone':
        rows = vector_store.search_similar('synthetic', k=25, source_type='metagenome')
        assert [row['doc_id'] for row in rows] == ['compatible']
    else:
        rows = hybrid_retriever.hybrid_search('synthetic', k=25, source_type='metagenome',
                                            vector_weight=1, fts_weight=0)
        assert [row.doc_id for row in rows] == ['compatible']


def test_no_compatible_vectors_retains_scoped_fts_and_reports_limitation(isolated):
    isolated.seed('legacy', provider='legacy-provider')
    isolated.seed('outside-sample', sample='outside')
    isolated.seed('outside-source', source='ctd')
    isolated.seed('inactive', active=False)
    envelope = scope('metagenome')
    envelope['sources']['metagenome']['filters']['sample_id'] = 'allowed'
    diagnostics = {}
    rows = hybrid_retriever.hybrid_search('c05identitytoken', evidence_scope=envelope,
                                        branch_diagnostics=diagnostics)
    assert [row.doc_id for row in rows] == ['legacy']
    assert rows[0].rank_sources == {'fts': 1}
    assert diagnostics['failed_branches'] == []
    assert diagnostics['vector']['status'] == 'no_compatible_candidates'
    assert diagnostics['vector']['compatible_result_count'] == 0


def test_unidentified_callback_never_uses_vector_but_preserves_fts(isolated):
    isolated.seed('text-only')
    diagnostics = {}
    rows = hybrid_retriever.hybrid_search('c05identitytoken', source_type='metagenome',
                                        query_embedding=lambda: [1.0, 0.0], branch_diagnostics=diagnostics)
    assert [row.doc_id for row in rows] == ['text-only']
    assert rows[0].rank_sources == {'fts': 1}
    assert diagnostics['failed_branches'] == ['vector']


def test_physical_vector_dimension_error_does_not_poison_fts_transaction(isolated):
    isolated.seed('dimension-error', dimension=1)
    diagnostics = {}
    rows = hybrid_retriever.hybrid_search('c05identitytoken', source_type='metagenome',
                                        query_embedding=lambda: isolated.query_vector(1),
                                        branch_diagnostics=diagnostics)
    assert [row.doc_id for row in rows] == ['dimension-error']
    assert rows[0].rank_sources == {'fts': 1}
    assert diagnostics['failed_branches'] == ['vector']


@pytest.mark.parametrize('entry', ['standalone', 'hybrid'])
def test_exact_git_baseline_selects_incompatible_equal_dimensional_vector(isolated, entry):
    """A passing red probe means the exact pre-C05 source exhibits F06."""
    isolated.seed('compatible', aligned=False)
    isolated.seed('wrong-space', model='another-model')
    source_path = 'db/vector_store.py' if entry == 'standalone' else 'retrieval/hybrid_retriever.py'
    module_name = 'db._c05_baseline_vector' if entry == 'standalone' else 'retrieval._c05_baseline_hybrid'
    module = types.ModuleType(module_name)
    module.__package__ = module_name.rsplit('.', 1)[0]
    sys.modules[module_name] = module
    try:
        source = subprocess.check_output(['git', 'show', f'{BASELINE}:{source_path}'], text=True)
        exec(compile(source, source_path, 'exec'), module.__dict__)
        module.get_session = isolated.session
        module.embed_text = lambda _query: list(isolated.query_vector())
        if entry == 'standalone':
            rows = module.search_similar('synthetic', k=1, source_type='metagenome')
            assert rows[0]['doc_id'] == 'wrong-space'
        else:
            rows = module.hybrid_search('synthetic', k=1, source_type='metagenome', vector_weight=1, fts_weight=0)
            assert rows[0].doc_id == 'wrong-space'
    finally:
        sys.modules.pop(module_name, None)


def _synthetic_metagenome_documents(abundance=10.0):
    import json
    import pandas as pd
    from preprocessing.metagenome import build_sample_multisource_context
    from retrieval.document_builder import build_metagenome_docs

    sid = '2024-04-O-s1'
    registry = pd.DataFrame([{'sample_id': sid, 'has_kraken': True, 'has_metaeuk': True}])
    ctd = pd.DataFrame([{'sample_id': sid}])
    kraken = pd.DataFrame([{'sample_id': sid, 'top_genus_10_json': json.dumps([
        {'genus': 'C05Kraken', 'abundance_value': abundance}])}])
    metaeuk = pd.DataFrame([{'sample_id': sid, 'top_genus_10_json': json.dumps([
        {'genus': 'C05MetaEuk', 'abundance_value': 5.0}])}])
    groups = pd.DataFrame([{'sample_id': sid}])
    return build_metagenome_docs(build_sample_multisource_context(registry, ctd, kraken, metaeuk, groups))


def _merge_metagenome(connection, documents):
    from retrieval.document_builder import documents_to_dataframe
    from preprocessing.metagenome_contract import metagenome_replacement_scope
    from scripts.load_db import _upsert_dataframe, _inactivate_superseded_metagenome_documents

    frame = documents_to_dataframe(documents)
    metagenome_replacement_scope(frame)
    result = _upsert_dataframe(connection, table_name='retrieval_document', incoming=frame, key_columns=['doc_id'])
    retired = _inactivate_superseded_metagenome_documents(connection, frame)
    return result, retired


def test_versioned_metagenome_rebuild_retains_history_and_repeat_embedding(isolated):
    import json

    sid = '2024-04-O-s1'
    isolated.seed('meta_' + sid, sample=sid, body='Legacy metagenome evidence')
    isolated.seed('unrelated-metagenome', sample='another-sample')
    isolated.seed('same-sample-ctd', source='ctd', sample=sid)
    first = _synthetic_metagenome_documents()
    repeated = _synthetic_metagenome_documents()
    assert first[0].doc_id == repeated[0].doc_id and first[0].metadata == repeated[0].metadata
    with isolated.engine.begin() as connection:
        result, retired = _merge_metagenome(connection, first)
        assert result['inserted'] == 1 and retired == 1
        previous = connection.execute(text('SELECT text,active,embedding IS NOT NULL FROM retrieval_document WHERE doc_id=:id'),
                                      {'id': 'meta_' + sid}).one()
        assert tuple(previous) == ('Legacy metagenome evidence', False, True)
        replacement = connection.execute(text('SELECT active,embedding,embedding_provider,embedding_model,embedding_dim FROM retrieval_document WHERE doc_id=:id'),
                                         {'id': first[0].doc_id}).one()
        assert replacement[0] is True and all(value is None for value in replacement[1:])
        connection.execute(text('UPDATE retrieval_document SET embedding=CAST(:vector AS vector), '
                                'embedding_provider=:provider,embedding_model=:model,embedding_dim=:dimension WHERE doc_id=:id'),
                           {'vector': str(list(isolated.query_vector())), 'provider': PROVIDER,
                            'model': MODEL, 'dimension': config.EMBEDDING_DIM, 'id': first[0].doc_id})
        result, retired = _merge_metagenome(connection, repeated)
        assert result['unchanged'] == 1 and result['updated'] == 0 and retired == 0
        assert connection.scalar(text('SELECT embedding IS NOT NULL FROM retrieval_document WHERE doc_id=:id'),
                                 {'id': first[0].doc_id}) is True
        assert connection.scalar(text("SELECT count(*) FROM retrieval_document WHERE doc_id IN ('unrelated-metagenome','same-sample-ctd') AND active")) == 2

    changed = _synthetic_metagenome_documents(11.0)
    assert changed[0].doc_id != first[0].doc_id
    with isolated.engine.begin() as connection:
        result, retired = _merge_metagenome(connection, changed)
        assert result['inserted'] == 1 and retired == 1
        assert connection.scalar(text('SELECT embedding IS NOT NULL FROM retrieval_document WHERE doc_id=:id'),
                                 {'id': first[0].doc_id}) is True
        assert connection.scalar(text('SELECT active FROM retrieval_document WHERE doc_id=:id'),
                                 {'id': first[0].doc_id}) is False
        assert connection.scalar(text('SELECT embedding IS NULL FROM retrieval_document WHERE doc_id=:id'),
                                 {'id': changed[0].doc_id}) is True
        witness = connection.scalar(text('SELECT metadata_json FROM retrieval_document WHERE doc_id=:id'),
                                    {'id': changed[0].doc_id})
        assert json.loads(witness) == changed[0].metadata


def test_failed_retirement_rolls_back_replacement_and_preserves_prior_history(isolated):
    sid = '2024-04-O-s1'
    isolated.seed('meta_' + sid, sample=sid, body='Legacy held-in-transaction fixture')
    replacement = _synthetic_metagenome_documents()
    with pytest.raises(RuntimeError, match='forced rollback'):
        with isolated.engine.begin() as connection:
            _merge_metagenome(connection, replacement)
            raise RuntimeError('forced rollback')
    with isolated.engine.connect() as connection:
        assert connection.scalar(text('SELECT active FROM retrieval_document WHERE doc_id=:id'),
                                 {'id': 'meta_' + sid}) is True
        assert connection.scalar(text('SELECT count(*) FROM retrieval_document WHERE doc_id=:id'),
                                 {'id': replacement[0].doc_id}) == 0


@pytest.mark.parametrize('mutation', ['method_coverage', 'missing_version', 'source_family'])
def test_immutable_replacement_tampering_cannot_rewrite_stored_evidence(isolated, mutation):
    from copy import deepcopy

    original = _synthetic_metagenome_documents()
    with isolated.engine.begin() as connection:
        _merge_metagenome(connection, original)
    changed = deepcopy(original)
    if mutation == 'method_coverage':
        changed[0].metadata['method_coverage']['kraken'] = False
    elif mutation == 'missing_version':
        changed[0].metadata.pop('document_version')
    else:
        changed[0].source_type = 'ctd'
    with pytest.raises(ValueError):
        with isolated.engine.begin() as connection:
            _merge_metagenome(connection, changed)
    with isolated.engine.connect() as connection:
        import json
        row = connection.execute(text('SELECT source_type,metadata_json,active FROM retrieval_document WHERE doc_id=:id'),
                                 {'id': original[0].doc_id}).one()
        assert row[0] == 'metagenome' and json.loads(row[1]) == original[0].metadata and row[2] is True
