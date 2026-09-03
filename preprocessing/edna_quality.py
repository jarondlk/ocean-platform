"""Descriptive controls/standards reports; never edits or decontaminates rows."""
from collections import defaultdict

from ingestion.immutable_bundle import digest
from preprocessing.edna_analysis import protocol, taxon_key


def quality_reports(recipe, inputs):
    samples = {s['sample_id']: s for s in inputs['edna_sample']}
    assays = {a['assay_id']: a for a in inputs['edna_assay']}
    negatives = defaultdict(list)
    control_inventory, overlap, standards = [], [], []

    def partition(aid, method):
        assay = assays[aid]
        sample = samples[assay['sample_id']]
        return digest([sample['provider'], sample['provider_project_id'], sample['provider_run_id'], protocol(assay), method])

    for d in inputs['edna_detection']:
        if d['assignment_method'] not in recipe.assignment_methods or d['read_count'] <= 0:
            continue
        sample = samples[assays[d['assay_id']]['sample_id']]
        if sample.get('sample_kind') == 'negative_control' and sample.get('is_control') is True:
            base = partition(d['assay_id'], d['assignment_method'])
            negatives[(base, 'sequence', d['sequence_sha256'])].append(d)
            taxon = taxon_key(d, recipe.rank)
            if taxon:
                negatives[(base, 'taxon', digest(taxon))].append(d)
    negative_partitions = {key[0] for key in negatives}
    for aid, assay in sorted(assays.items()):
        sample = samples[assay['sample_id']]
        for method in recipe.assignment_methods:
            environmental = sample.get('sample_kind') == 'environmental' and sample.get('is_control') is False
            control_inventory.append(dict(sample_id=sample['sample_id'], assay_id=aid, assignment_method=method,
                sample_kind=sample.get('sample_kind'), is_control=sample.get('is_control'),
                classification_basis=sample.get('classification_basis'),
                status='same_run_context_only' if environmental and partition(aid, method) in negative_partitions else 'not_assessed',
                expected_composition_status='not_supplied', pairing_basis='provider_run_and_protocol',
                source_file_id=sample.get('source_file_id'), source_row_hash=sample.get('source_row_hash')))
        rows = [s for s in inputs['edna_internal_standard'] if s['assay_id'] == aid]
        supplied = [d for d in inputs['edna_detection'] if d['assay_id'] == aid and d.get('copies_per_ml') is not None]
        if rows:
            for row in rows:
                standards.append({**row, 'sample_id': sample['sample_id'], 'status': 'observed' if row['read_count'] > 0 else 'zero_reads',
                                  'calibration_status': 'not_assessed', 'copies_per_ml_records': len(supplied)})
        else:
            standards.append(dict(assay_id=aid, sample_id=sample['sample_id'], status='not_supplied', calibration_status='not_assessed', copies_per_ml_records=len(supplied)))
    for row in inputs['edna_detection']:
        sample = samples[assays[row['assay_id']]['sample_id']]
        if sample.get('sample_kind') != 'environmental' or sample.get('is_control') is not False or row['read_count'] <= 0 or row['assignment_method'] not in recipe.assignment_methods:
            continue
        keys = [('sequence', row['sequence_sha256'])]
        taxon = taxon_key(row, recipe.rank)
        if taxon:
            keys.append(('taxon', digest(taxon)))
        for kind, key in keys:
            for control in negatives.get((partition(row['assay_id'], row['assignment_method']), kind, key), []):
                if len(overlap) >= recipe.max_comparisons:
                    raise ValueError('Control comparison resource limit exceeded')
                overlap.append(dict(sample_id=sample['sample_id'], assay_id=row['assay_id'], assignment_method=row['assignment_method'],
                    detection_id=row['detection_id'], control_detection_id=control['detection_id'], control_assay_id=control['assay_id'],
                    read_count=row['read_count'], control_read_count=control['read_count'], match_basis=kind,
                    status='shared_record_not_contamination_diagnosis'))
    return dict(controls=control_inventory, control_overlap=overlap, standards=standards)
