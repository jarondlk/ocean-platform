from unittest.mock import patch
import json

import pytest

import config
from ingestion.immutable_bundle import digest
from retrieval.edna_materializer import _write_artifacts, _document_frame
from retrieval.edna_publication import retrieval_path, set_pending, current_manifest
from retrieval.local_retriever import LocalRetriever
from orchestration.unified import build_prompt_with_context
from schema.time_range import matches_time, sql_time_conditions, time_bounds
from tests.test_edna_document_builder import _frames
from retrieval.edna_document_builder import build_edna_documents


@pytest.mark.parametrize('scope', [{'provider': 'anemone'}, {'source_type': 'edna'}, {'is_control': False}])
def test_structured_edna_scope_suppresses_legacy_context_even_without_results(scope):
    with patch('orchestration.unified._read_context_documents') as loader:
        _, context = build_prompt_with_context('Compare diversity', [], evidence_scope=scope)
    assert context == {'analysis': [], 'reliability': []}
    loader.assert_not_called()


def test_edna_results_suppress_generic_legacy_context():
    with patch('orchestration.unified._read_context_documents') as loader:
        build_prompt_with_context('Compare diversity', [{'source_type': 'edna_metabarcoding'}])
    loader.assert_not_called()


def test_utc_end_date_and_unknown_observations():
    assert matches_time('2026-09-01T12:00:00Z', None, '2026-09-01')
    assert matches_time('2026-09-02T01:00:00+09:00', None, '2026-09-01')
    assert not matches_time('2026-09-02T00:00:00Z', None, '2026-09-01')
    assert not matches_time(None, None, '2026-09-01')
    assert matches_time('2024-02-29', '2024-02-29T12:00:00Z', '2024-02-29')
    clauses, params = sql_time_conditions('s.collection_date_utc', None, '2024-02-29')
    assert ' < :utc_to' in clauses[0]
    assert str(params['utc_to']).startswith('2024-03-01')
    with pytest.raises(ValueError):
        time_bounds('2026-09-02', '2026-09-01')


def test_generation_pending_and_corruption_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'SERVING_DIR', tmp_path)
    docs = build_edna_documents(*_frames())
    _write_artifacts(docs, _document_frame(docs))
    original = retrieval_path('jsonl')
    assert len(LocalRetriever().documents) == 0
    set_pending()
    with pytest.raises(ValueError, match='incomplete'):
        LocalRetriever().load()
    _write_artifacts(docs, _document_frame(docs))
    assert retrieval_path('jsonl') == original
    manifest = current_manifest()
    pointer = json.loads((tmp_path / 'edna_current.json').read_text())
    assert pointer['manifest_sha256'] == digest(manifest)
    original.write_text('corrupt')
    with pytest.raises(ValueError, match='integrity'):
        retrieval_path('parquet')


def test_pending_generation_does_not_block_admin_recovery_inventory(tmp_path, monkeypatch):
    from api.main import _pipeline_artifacts, _artifact_status
    monkeypatch.setattr(config, 'SERVING_DIR', tmp_path)
    set_pending()
    artifacts = [a for a in _pipeline_artifacts() if a.id.startswith('serving:edna_retrieval_')]
    assert len(artifacts) == 2
    assert all(not a.exists and 'rerun materialization' in a.note for a in artifacts)
    assert _artifact_status()['edna_publication'] == 'unavailable'
    assert _artifact_status()['edna_retrieval_documents'] is None
