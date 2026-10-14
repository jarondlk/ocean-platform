"""Read-only C05 audit: captured SQL and synthetic producer-to-document input."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pandas as pd

import config
from db import vector_store
from preprocessing.metagenome import build_sample_multisource_context
from retrieval import hybrid_retriever
from retrieval.document_builder import build_metagenome_docs


queries = []


class EmptySession:
    def execute(self, statement, parameters):
        queries.append({'sql': str(statement), 'parameters': parameters})
        return self

    def fetchall(self):
        return []


@contextmanager
def empty_session():
    yield EmptySession()


with patch.object(vector_store, 'get_session', empty_session), \
        patch.object(vector_store, 'embed_text', lambda *_args, **_kwargs: [1.0, 0.0]), \
        patch.object(hybrid_retriever, 'get_session', empty_session), \
        patch.object(hybrid_retriever, 'embed_text', lambda *_args, **_kwargs: [1.0, 0.0]), \
        patch.object(config, 'EDNA_ARTIFACT_URI', ''):
    vector_store.search_similar('synthetic', source_type='metagenome')
    hybrid_retriever.hybrid_search('synthetic', source_type='metagenome', vector_weight=1, fts_weight=0)

sid = '2024-04-O-s1'
registry = pd.DataFrame([{'sample_id': sid, 'has_kraken': True, 'has_metaeuk': True}])
ctd = pd.DataFrame([{'sample_id': sid}])
kraken = pd.DataFrame([{'sample_id': sid, 'top_genus_10_json': json.dumps([
    {'genus': 'SyntheticKrakenOnly', 'abundance_value': 10.0},
])}])
metaeuk = pd.DataFrame([{'sample_id': sid, 'top_genus_10_json': json.dumps([
    {'genus': 'SyntheticMetaEukOnly', 'abundance_value': 5.0},
])}])
groups = pd.DataFrame([{'sample_id': sid}])
context = build_sample_multisource_context(registry, ctd, kraken, metaeuk, groups)
documents = build_metagenome_docs(context)
assert len(documents) == 1

report = {
    'scope': 'Synthetic input and mocked empty SQL sessions only; no provider or database calls',
    'vector_sql': [{
        **query,
        'identity_predicates_present': {field: field in query['sql'] for field in
                                        ['embedding_provider', 'embedding_model', 'embedding_dim']},
    } for query in queries],
    'producer_columns': list(context.columns),
    'document': {'id': documents[0].doc_id, 'text': documents[0].text,
                 'metadata': documents[0].metadata},
    'kraken_taxon_present': 'SyntheticKrakenOnly' in documents[0].text,
    'metaeuk_taxon_present': 'SyntheticMetaEukOnly' in documents[0].text,
}
assert all(not any(query['identity_predicates_present'].values()) for query in report['vector_sql'])
assert not report['kraken_taxon_present'] and report['metaeuk_taxon_present']
(Path(__file__).resolve().parent / 'readiness-probes.json').write_text(json.dumps(report, indent=2) + '\n')
print('F06 reproduced in both SQL entry points; F08 reproduced through the actual synthetic producer')
