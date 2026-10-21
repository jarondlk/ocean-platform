"""Independent C22 probes over sealed synthetic sources, with no executor or server.

Create-only output; do not overwrite earlier outcomes after source repairs.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, event  # noqa: E402

from db.app_models import AppBase  # noqa: E402
from ingestion.immutable_bundle import digest  # noqa: E402
from ingestion.scientific_catalogue_inputs import load_registry  # noqa: E402
from orchestration.catalogue_registration import register_scientific_snapshot  # noqa: E402
from orchestration.catalogue_service import CataloguePolicy, CatalogueService, FrozenCatalogueResolver  # noqa: E402
from orchestration.frozen_experiment_export import (  # noqa: E402
    FrozenExperimentExport, FrozenExperimentExporter, FrozenExperimentExportError,
)
from schema.catalogue_adapter import FrozenDataset  # noqa: E402
from schema.catalogue_adapter_fixtures import metagenome_fixture, seal_fixture  # noqa: E402
from schema.context_catalogue import canonical_json  # noqa: E402
from schema.scientific_catalogue import ScientificRegistry  # noqa: E402
from schema.scientific_catalogue_fixtures import seal_scientific_fixture  # noqa: E402
from tests.investigation_support import make_investigation_fixture  # noqa: E402
from tests.test_frozen_experiment_export import (  # noqa: E402
    exporter, frozen, proposal, selection, synthetic_policy, table,
)

SOURCES = [
    'orchestration/frozen_experiment_export.py', 'tests/test_frozen_experiment_export.py',
    'schema/research_experiments.py', 'orchestration/research_controller_scope.py',
    'orchestration/frozen_catalogue.py', 'orchestration/frozen_scientific_catalogue.py',
]


def pins():
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = ROOT / args.output
    if target.exists():
        raise FileExistsError(target)
    before, cases = pins(), []
    old = {key: os.environ.get(key) for key in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS')}
    os.environ.update(ENABLE_V1_CATALOGUE='true', ENABLE_V1_INVESTIGATIONS='true')

    def refuse(name, callback):
        try:
            callback()
        except FrozenExperimentExportError as exc:
            cases.append({'name': name, 'expected': 'refused', 'observed': 'refused', 'reason': exc.reason, 'passed': True})
        else:
            cases.append({'name': name, 'expected': 'refused', 'observed': 'accepted', 'passed': False})

    try:
        with tempfile.TemporaryDirectory(prefix='c22-independent-export-') as directory:
            root = Path(directory)
            engine = create_engine('sqlite+pysqlite:///' + str(root / 'private-v1.sqlite'))

            @event.listens_for(engine, 'connect')
            def foreign_keys(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')

            try:
                AppBase.metadata.create_all(engine)
                fixture = make_investigation_fixture(engine, root)
                context, plan, service = frozen(fixture), proposal(fixture), exporter(fixture)
                complete = service.freeze(frozen=context, proposal=plan, user=fixture.user)
                rows = table(complete)['rows']
                assert len(rows) == 4
                cases.append({'name': 'actual_complete_ctd_baseline', 'passed': True, 'row_count': len(rows)})
                source = complete.manifest['sources']['datasets'][0]
                assert source['source_capture']['publication_generation'] == source['publication']['publication_generation']
                assert source['source_capture']['classification_generation']
                assert {item['object_id']: item['sha256'] for item in source['object_provenance']} == {item['object_id']: item['sha256'] for item in source['objects']}
                assert complete.manifest['tables'][0]['column_schema']
                assert all(type(item['nullable']) is bool and item['arrow_type'] for item in complete.manifest['tables'][0]['column_schema'])
                cases.append({'name': 'exact_selected_capture_object_provenance_and_arrow_schema', 'passed': True})
                scoped_analysis = deepcopy(fixture.scope)
                scoped_analysis['sources']['edna_metabarcoding']['analysis_id'] = 'synthetic:analysis:published'
                frozen_analysis = frozen(fixture, scope=scoped_analysis)
                refuse('C17_published_analysis_selection_cannot_be_ignored_by_native_read', lambda: service.freeze(frozen=frozen_analysis,
                    proposal=proposal(fixture, selection(fixture, 'edna_metabarcoding', 'detections')), user=fixture.user))

                class WrongGeneration:
                    def evaluate(self, **kwargs):
                        witness = synthetic_policy(fixture.store, fixture.registrations).evaluate(**kwargs)
                        return {**witness, 'publication_generation': 'different-nonempty-generation'}

                bad = exporter(fixture, publication_policy=WrongGeneration())
                refuse('host_callback_wrong_publication_generation', lambda: bad.freeze(frozen=context, proposal=plan, user=fixture.user))

                # Source-owned exclusion must remove depth rows by cast FK,
                # rather than only removing the selected identity table row.
                two = proposal(fixture, selection(fixture), selection(fixture, 'ctd', 'depth_observations'))
                original = service.freeze(frozen=context, proposal=two, user=fixture.user)
                depth = table(original, 2)
                support = next(item for item in depth['scientific_support'] if item['table'] == 'casts')
                assert {row['cast_id'] for row in support['rows']} == {row['cast_id'] for row in depth['rows']}
                assert {'collection_date', 'station', 'sample_id'} <= set(support['columns'])
                assert all(item['arrow_type'] and type(item['nullable']) is bool for item in support['column_schema'])
                cases.append({'name': 'dependent_depth_values_keep_exact_source_owned_date_and_identity_support', 'passed': True})
                excluded = table(original)['rows'][0]['cast_id']
                changed = two.model_dump(mode='json')
                changed['cohort']['exclusions'] = [{'dataset_id': fixture.source_dataset_ids['ctd'], 'entity': 'cast', 'ids': [excluded], 'reason': 'Explicit synthetic exclusion'}]
                removed = service.freeze(frozen=context, proposal=changed, user=fixture.user)
                assert len(table(removed)['rows']) == 3 and all(row['cast_id'] != excluded for row in table(removed, 2)['rows'])
                cases.append({'name': 'actual_ctd_exclusion_cascades_cast_fk', 'passed': True, 'remaining_casts': 3})

                pin = {'kind': 'catalogue', 'snapshot_id': fixture.snapshots[0], 'id': fixture.source_dataset_ids['ctd']}
                pinned = frozen(fixture, pins=[pin])
                refuse('ctd_pin_cannot_export_metagenome', lambda: service.freeze(frozen=pinned,
                    proposal=proposal(fixture, selection(fixture, 'metagenome', 'collections')), user=fixture.user))
                fixture.policy[fixture.snapshots[0]].add(fixture.source_dataset_ids['ctd'])
                refuse('current_dataset_revocation_blocks_reuse', lambda: service.verify(frozen=context, proposal=plan, user=fixture.user, exported=complete))
                fixture.policy[fixture.snapshots[0]].clear()

                withdrawn = exporter(fixture, publication_policy=synthetic_policy(fixture.store, fixture.registrations,
                    withdrawn=[fixture.source_dataset_ids['ctd']]))
                refuse('publication_withdrawal_blocks_reuse', lambda: withdrawn.verify(frozen=context, proposal=plan, user=fixture.user, exported=complete))
                refuse('proximity_cannot_establish_physical_identity', lambda: service.freeze(frozen=context,
                    proposal=proposal(fixture, cohort={'selections': [selection(fixture)], 'pairing': {'mode': 'physical_identity', 'relationship_ids': ['synthetic:relationship:proximity']}}), user=fixture.user))

                tampered = dict(complete.files)
                tampered['table-01.json'] += b' '
                refuse('staged_file_tamper_rejected_at_reconstruction', lambda: FrozenExperimentExport(manifest_json=complete.manifest_json, files=tampered))
                metadata = complete.manifest
                metadata['max_input_bytes'] = sum(map(len, complete.files.values()))
                refuse('manifest_and_sidecars_count_toward_input_limit', lambda: FrozenExperimentExport(manifest_json=canonical_json(metadata), files=complete.files))

                # Seal a source whose anchor is explicitly partial while its
                # requested dependent run table is complete. Native C10 must
                # refuse it before any complete-cohort export is claimed.
                child_meta, frames = metagenome_fixture(2, dataset_id='synthetic:c22:partial-anchor', source_id='synthetic-c22-partial-anchor')
                raw_meta = child_meta.model_dump(mode='json')
                next(item for item in raw_meta['tables'] if item['name'] == 'collections')['completeness'] = 'partial'
                child_meta = FrozenDataset.model_validate(raw_meta)
                child = seal_fixture(fixture.store, [(child_meta, frames)])
                registry = load_registry(*fixture.store.read(fixture.snapshots[0])).metadata.model_dump(mode='json')
                registry.update(datasets=[{'dataset_id': child_meta.dataset_id, 'source_id': child_meta.source_id,
                    'source_family': 'metagenome', 'snapshot_id': child}], analyses=[], workflows=[], relationships=[], definitions=[])
                sid = seal_scientific_fixture(fixture.store, ScientificRegistry.model_validate(registry), {})
                registrations = {sid: register_scientific_snapshot(store=fixture.store, snapshot_id=sid, registration_id='synthetic:c22:partial-anchor')}
                catalogue = CatalogueService(resolver=FrozenCatalogueResolver(store=fixture.store, registrations=registrations,
                    policy_resolver=lambda *args: CataloguePolicy(revision='synthetic-c22-partial', dataset_eligible=lambda *args: True, scientific_eligible=lambda *args: True)))
                private_context = {'snapshot_id': sid, 'scope': fixture.scope, 'pins': [], 'attachments': [], 'artifact_bindings': []}
                bound = {'investigation_id': str(uuid.uuid4()), 'conversation_id': str(uuid.uuid4()), 'revision_id': str(uuid.uuid4()),
                    'snapshot_id': sid, 'payload_sha256': digest(private_context), 'context': private_context}
                partial = FrozenExperimentExporter(store=fixture.store, catalogue=catalogue, registrations=registrations,
                    publication_policy=synthetic_policy(fixture.store, registrations))
                refuse('partial_selector_anchor_cannot_claim_complete_dependent_run_cohort', lambda: partial.freeze(frozen=bound,
                    proposal=proposal(fixture, {'target_id': child_meta.dataset_id, 'table': 'run_qc', 'columns': ['reads']}), user=fixture.user))
            finally:
                engine.dispose()
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    after = pins()
    result = {'version': 'c22-independent-export-final-probe-v1', 'synthetic_only': True,
        'qualification': 'Actual sealed C09/C13/C14/C17 code and exporter; separate temporary SQLite only, no server/executor/provider/real data/cloud. Exporter and exporter tests were declared frozen by their owner before this supplemental probe.',
        'source_before_sha256': before, 'source_after_sha256': after, 'source_unchanged': before == after,
        'cases': cases, 'passed': sum(case['passed'] for case in cases), 'failed': sum(not case['passed'] for case in cases)}
    with target.open('x') as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write('\n')
    print(json.dumps({'output': str(target.relative_to(ROOT)), 'passed': result['passed'], 'failed': result['failed'], 'source_unchanged': result['source_unchanged']}))
    return 1 if result['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
