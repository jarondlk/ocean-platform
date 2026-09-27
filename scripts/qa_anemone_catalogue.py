#!/usr/bin/env python3
"""Read-only full-candidate QA against an explicit isolated database and serving tree."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
import config
from db.connection import get_engine
from ingestion.anemone_catalogue import file_sha256
from ingestion.immutable_bundle import digest, validate_id
from ingestion.lineage import build_provenance_manifest
from ingestion.provenance_snapshot import prepare_snapshot
from retrieval.edna_publication import current_manifest
from api.edna_service import edna_summary, edna_detections, edna_samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--serving-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    config.DATABASE_URL = args.database_url
    config.SERVING_DIR = args.serving_dir.resolve()
    config.ANEMONE_NORMALIZED_DIR = args.work_dir.resolve() / 'normalized'
    config.RAW_ANEMONE_DIR = args.work_dir.resolve() / 'raw'
    if config.EDNA_ARTIFACT_URI:
        raise ValueError('This QA command requires an isolated local serving directory')
    start = time.monotonic()
    pointer = json.loads((args.work_dir / 'candidate.json').read_text())
    candidate_path = args.work_dir / 'candidates' / validate_id(pointer['candidate_id']) / 'candidate.json'
    assert file_sha256(candidate_path) == pointer['manifest_sha256']
    candidate = json.loads(candidate_path.read_text())
    summary = edna_summary({})
    assert summary['publication']['anemone-canonical']['generation_id'] == candidate['candidate_id']
    assert summary['source_occurrences'] == candidate['source_occurrences']
    assert summary['assays'] == candidate['row_counts']['edna_assay']
    assert {r['assignment_method']: r['assignment_rows'] for r in summary['methods']} == candidate['assignment_rows']
    assert {r['assignment_method']: r['read_count_sum'] for r in summary['methods']} == candidate['read_counts_by_method']
    engine = get_engine()
    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        records = """WITH records AS (
          SELECT jsonb_array_elements(metadata_json::jsonb->'canonical_records') r
          FROM retrieval_document WHERE active IS TRUE AND source_type='edna_metabarcoding')
          SELECT count(*) FROM records
          LEFT JOIN edna_sample s ON r->>'entity_type'='sample' AND s.sample_id=r->>'entity_id'
          LEFT JOIN edna_assay a ON r->>'entity_type'='assay' AND a.assay_id=r->>'entity_id'
          LEFT JOIN edna_detection d ON r->>'entity_type'='detection' AND d.detection_id=r->>'entity_id'
          LEFT JOIN edna_internal_standard i ON r->>'entity_type'='internal_standard' AND i.internal_standard_id=r->>'entity_id'
          WHERE COALESCE(s.source_row_hash,a.source_row_hash,d.source_row_hash,i.source_row_hash) IS DISTINCT FROM r->>'source_row_hash'"""
        mismatches = connection.execute(text(records)).scalar_one()
        assert mismatches == 0
        standards = connection.execute(text('SELECT count(*) FROM edna_internal_standard WHERE active IS TRUE')).scalar_one()
        assert standards == candidate['row_counts']['edna_internal_standard']
        rare = connection.execute(text("""SELECT d.assigned_taxon_name AS taxon, count(*) AS rows
            FROM edna_detection d WHERE active IS TRUE AND assigned_taxon_name IS NOT NULL
            AND assignment_method='qcauto_target' GROUP BY d.assigned_taxon_name
            ORDER BY count(*),d.assigned_taxon_name LIMIT 1""")).mappings().one()
        size = connection.execute(text('SELECT pg_database_size(current_database())')).scalar_one()
    rare_result = edna_detections({'taxon': rare['taxon'], 'assignment_method': 'qcauto_target'}, limit=500, offset=0)
    assert rare_result['total'] >= rare['rows']
    zero_tables = sum(r['empty_tables'] for r in summary['community_availability'])
    for method in candidate['assignment_rows']:
        assert edna_samples({'assignment_method': method}, limit=1, offset=0)['total'] == candidate['source_occurrences']
    publication = current_manifest()
    assert publication['id'] == summary['publication']['edna']['generation_id']
    assert digest(publication) == summary['publication']['edna']['manifest_sha256']
    print(json.dumps({'stage': 'counts_and_canonical_citations_verified', 'empty_tables': zero_tables}), flush=True)
    manifest = build_provenance_manifest(limit_documents=None, include_embeddings=True)
    snapshot = prepare_snapshot(manifest, manifest_id='anemone-catalogue-local-qa', require_embedding_capture=True)
    assert len(snapshot.documents) == publication['document_count']
    assert edna_summary({})['publication'] == summary['publication']
    result = {'passed': True, 'candidate_id': candidate['candidate_id'], 'summary': summary,
              'canonical_citation_mismatches': mismatches, 'validated_document_traces': len(snapshot.documents),
              'source_files_in_provenance': len(snapshot.source_files), 'standards': standards,
              'rare_taxon_query': {'taxon': rare['taxon'], 'total': rare_result['total']},
              'database_bytes': size, 'elapsed_seconds': round(time.monotonic()-start, 2),
              'model_calls': 0, 'production_changed': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str)+'\n')
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
