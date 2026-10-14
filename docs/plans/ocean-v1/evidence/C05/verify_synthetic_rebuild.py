"""Record a synthetic rebuild and read-only inventory; never use models or a DB."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from preprocessing.metagenome import build_sample_multisource_context
    from preprocessing.metagenome_contract import (
        KRAKEN_TOP_COLUMN, KRAKEN_UPPER_COLUMN, METAEUK_TOP_COLUMN,
    )
    from retrieval.document_builder import build_metagenome_docs, documents_to_jsonl

    output = Path(__file__).resolve().parent
    sample = '2024-04-O-c05synthetic'
    registry = pd.DataFrame([{'sample_id': sample, 'has_kraken': True,
                              'has_metaeuk': True, 'has_ctd': False}])
    kraken = pd.DataFrame([{'sample_id': sample, 'top_genus_10_json': json.dumps([
        {'genus': 'SyntheticKrakenGenus', 'abundance_value': 12.0}])}])
    metaeuk = pd.DataFrame([{'sample_id': sample, 'top_genus_10_json': json.dumps([
        {'genus': 'SyntheticMetaEukGenus', 'abundance_value': 7.0}])}])
    upper = pd.DataFrame([{'sample_id': sample, 'top_upper_group_10_json': '[]'}])
    produced = build_sample_multisource_context(
        registry, pd.DataFrame(columns=['sample_id']), kraken, metaeuk, upper)
    first = build_metagenome_docs(produced)
    repeat = build_metagenome_docs(produced)
    legacy = produced.drop(columns=['metagenome_source_version', 'metagenome_mapping_version']).rename(
        columns={KRAKEN_TOP_COLUMN: 'top_genus_10_json_x',
                 METAEUK_TOP_COLUMN: 'top_genus_10_json_y',
                 KRAKEN_UPPER_COLUMN: 'top_upper_group_10_json'})
    adapted = build_metagenome_docs(legacy)
    assert first == repeat == adapted
    changed_kraken = kraken.copy()
    changed_kraken['top_genus_10_json'] = json.dumps([
        {'genus': 'SyntheticKrakenGenus', 'abundance_value': 13.0}])
    changed_context = build_sample_multisource_context(
        registry, pd.DataFrame(columns=['sample_id']), changed_kraken, metaeuk, upper)
    changed = build_metagenome_docs(changed_context)
    assert first[0].doc_id != changed[0].doc_id
    assert first[0].text.count('SyntheticKrakenGenus') == 1
    assert first[0].text.count('SyntheticMetaEukGenus') == 1
    produced.to_json(output / 'synthetic-context.json', orient='records', indent=2)
    documents_to_jsonl(first, output / 'synthetic-documents.jsonl')
    documents_to_jsonl(repeat, output / 'synthetic-documents-repeat.jsonl')
    documents_to_jsonl(changed, output / 'synthetic-documents-changed.jsonl')
    assert sha256(output / 'synthetic-documents.jsonl') == sha256(output / 'synthetic-documents-repeat.jsonl')
    inventory = {}
    for relative in ('data/serving/retrieval_documents.parquet',
                     'data/serving/sample_multisource_context.parquet'):
        path = ROOT / relative
        frame = pd.read_parquet(path)
        item = {'path': relative, 'sha256': sha256(path), 'rows': len(frame),
                'columns': frame.columns.tolist(), 'read_only': True}
        if 'source_type' in frame:
            affected = frame[frame['source_type'].eq('metagenome')]
            item.update({'affected_legacy_count': len(affected),
                         'affected_legacy_doc_ids': affected['doc_id'].tolist(),
                         'with_kraken_taxa_label': int(affected['text'].str.contains('Top Kraken genera:', regex=False).sum()),
                         'with_metaeuk_taxa_label': int(affected['text'].str.contains('Top MetaEuk genera:', regex=False).sum()),
                         'metadata_present': 'metadata_json' in frame})
        else:
            item['paired_legacy_fields'] = {'top_genus_10_json_x', 'top_genus_10_json_y'}.issubset(frame.columns)
            item['both_methods_count'] = int((frame['has_kraken'] & frame['has_metaeuk']).sum())
        assert sha256(path) == item['sha256']
        inventory[relative] = item
    receipt = {
        'mode': 'synthetic generation plus read-only local inventory',
        'database_access': False, 'provider_calls': False, 'real_artifacts_regenerated': False,
        'repeat_equal': first == repeat, 'legacy_equal': first == adapted,
        'original_doc_id': first[0].doc_id, 'changed_doc_id': changed[0].doc_id,
        'original_metadata': first[0].metadata, 'changed_metadata': changed[0].metadata,
        'outputs': {name: sha256(output / name) for name in (
            'synthetic-context.json', 'synthetic-documents.jsonl',
            'synthetic-documents-repeat.jsonl', 'synthetic-documents-changed.jsonl')},
        'local_inventory': inventory,
    }
    (output / 'synthetic-rebuild.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'repeat_equal': receipt['repeat_equal'], 'legacy_equal': receipt['legacy_equal'],
                      'fresh_identity_on_change': first[0].doc_id != changed[0].doc_id,
                      'affected_local_legacy_documents': len(inventory['data/serving/retrieval_documents.parquet']['affected_legacy_doc_ids'])}))


if __name__ == '__main__':
    main()
