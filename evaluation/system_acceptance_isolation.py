"""C26 actual local copy/configuration composition, never live isolation evidence."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.catalogue_snapshot_fixtures import fixture_snapshot
from ingestion.catalogue_snapshot_transfer import TransferRejected, build_transfer, import_quarantined
from schema.catalogue_snapshot import manifest_id
from scripts import render_gcp_v1 as renderer


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def run_isolation_acceptance(directory):
    """Return actual observations from disposable local stores and renderer contracts.

    The source is authored synthetic fixture bytes. No input URI, origin or
    rendered target is contacted. A source withdrawal is not automatically
    propagated across independent copies; an explicit destination action is tested.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    site = renderer.load_site(renderer.DIRECTORY / 'examples/site.synthetic.json')
    artifacts = renderer.render(site)
    destination = site.target.project_id
    snapshot, contents = fixture_snapshot()
    source = LocalCatalogueSnapshotStore(root=directory / 'origin', access_gate=lambda value: True)
    source_id = source.seal(snapshot, contents)
    transfer = build_transfer(snapshot, contents, destination_id=destination,
        authorization_ref='C26 explicitly authorized synthetic fixture only',
        origin_system='c26-synthetic-origin',
        qualifications={key: ('Synthetic descriptive source; no scientific approval',
            'Synthetic permitted cohort only') for key in contents},
        encodings={key: 'json-rows-v1' for key in contents})
    target = LocalCatalogueSnapshotStore(root=directory / 'target', access_gate=lambda value: True)
    checks = []

    def record(identity, status, expected, observed, owners, reason=None):
        payload = {'id': identity, 'status': status, 'owner_components': owners,
            'expected': expected, 'observed': observed, 'reason': reason}
        payload['evidence'] = {'sha256': _digest(payload), 'kind': 'actual-service-synthetic',
            'fixture_sha256': _digest({'source': manifest_id(snapshot), 'destination': destination})}
        checks.append(payload)

    result = import_quarantined(transfer, contents, destination_id=destination, store=target,
        quarantine_root=directory / 'quarantine', authorize=lambda value: True,
        eligible=lambda obj, origin: True)
    restored, copied = target.read(result.snapshot_id)
    expected = {'objects': 8, 'independent': True, 'exact_bytes': True,
        'latest': [None, 0], 'live_dependency': False, 'origin_retained': True}
    observed = {'objects': result.object_count, 'independent': result.snapshot_id != source_id,
        'exact_bytes': copied == contents, 'latest': list(target.latest()),
        'live_dependency': any(obj.provenance.origin.live_dependency for obj in restored.objects),
        'origin_retained': all(obj.provenance.origin.source_snapshot_id == source_id for obj in restored.objects)}
    record('transfer-independent', 'passed' if observed == expected else 'failed', expected,
        observed, ['C09', 'C24', 'C26'])

    rejected = []
    for failure in ['wrong-destination', 'source-bytes', 'authorization', 'eligibility']:
        supplied = dict(contents)
        if failure == 'source-bytes':
            key = next(iter(supplied))
            supplied[key] += b' altered'
        store = LocalCatalogueSnapshotStore(root=directory / ('rejected-' + failure), access_gate=lambda value: True)
        try:
            import_quarantined(transfer, supplied,
                destination_id='legacy-site' if failure == 'wrong-destination' else destination,
                store=store, quarantine_root=directory / ('quarantine-' + failure),
                authorize=lambda value: failure != 'authorization',
                eligible=lambda obj, origin: failure != 'eligibility')
        except (TransferRejected, ValueError, PermissionError):
            rejected.append(failure)
        if store.latest() != (None, 0):
            rejected.append('unexpected-publication')
    expected = ['wrong-destination', 'source-bytes', 'authorization', 'eligibility']
    record('transfer-rejections', 'passed' if rejected == expected else 'failed', expected,
        rejected, ['C09', 'C26'])

    # Independent copies cannot know an origin changed without an explicit operator process.
    source.revoke(source_id)
    independent_read = target.read(result.snapshot_id)[1] == contents
    target.revoke(result.snapshot_id)
    withdrawn = False
    try:
        target.read(result.snapshot_id)
    except PermissionError:
        withdrawn = True
    expected = {'origin_change_is_not_auto_sync': True, 'explicit_withdrawal_denies': True}
    observed = {'origin_change_is_not_auto_sync': independent_read, 'explicit_withdrawal_denies': withdrawn}
    record('transfer-withdrawal', 'passed' if observed == expected else 'failed', expected,
        observed, ['C09', 'C24', 'C26'])

    policy = artifacts['site-policy.json']
    expected = {'artifacts': 7, 'apply_allowed': False, 'provider_schema_validated': False,
        'unrun_live_gates': 11, 'same_origin_only': True, 'guest_network': 'none'}
    observed = {'artifacts': len(artifacts),
        'apply_allowed': any(value['apply_allowed'] for value in artifacts.values()),
        'provider_schema_validated': any(value['provider_schema_validated'] for value in artifacts.values()),
        'unrun_live_gates': sum(gate['status'] == 'not_run' for gate in policy['gates']),
        'same_origin_only': policy['browser']['cors_origins'] == [site.target.public_origin],
        'guest_network': policy['guest_network']}
    record('isolation-offline-contract', 'passed' if observed == expected else 'failed', expected,
        observed, ['C24', 'C26'])
    rejected_targets = []
    for field, value in [('project_id', 'data-infra-infobio'), ('public_origin', 'https://oceaninfobio.com')]:
        changed = deepcopy(site.model_dump(mode='json'))
        changed['target'][field] = value
        try:
            renderer.Site.model_validate(changed)
        except ValidationError:
            rejected_targets.append(field)
    record('isolation-legacy-denial', 'passed' if rejected_targets == ['project_id', 'public_origin'] else 'failed',
        ['project_id', 'public_origin'], rejected_targets, ['C24', 'C26'])
    record('live-site-isolation', 'not_run', {'live_IAM_network_sessions': 'actual observations required'},
        None, ['C24', 'C26'], 'No concrete live target or authorization/configuration in this local fixture; no cloud operation performed')
    return {'version': 'c26-isolation-observations-v1', 'fixture': {
        'classification': 'synthetic-local-actual-services', 'source_snapshot_id': source_id,
        'copy_snapshot_id': result.snapshot_id, 'destination': destination,
        'input_manifest_sha256': _digest(transfer.model_dump(mode='json')),
        'live_calls_performed': False}, 'checks': checks}
