"""Explicit C26 requirement accounting. Missing observations never pass.

The matrix retains the master wording; local evidence has a stated boundary.
Full operational acceptance remains a separate current-live phase.
"""
from __future__ import annotations

import re

from evaluation.system_acceptance import build_acceptance_report, content_sha256

# Actual integrated checks, curated regression groups and browser journeys.
BINDINGS = {
    'R01': ('english-japanese-incompatible-geo-taxa-clarify', 'regression-scope'),
    'R02': ('sst-independent-numerical-oracle', 'four-source-physical-method-assay-semantics', 'regression-publication'),
    'R03': ('owner-role-source-revocation-and-held-history', 'regression-retention'),
    'R04': ('regression-auth',),
    'R05': ('regression-model',),
    'R06': ('regression-csv',),
    'R07': ('shared-context-inventory-answer', 'four-source-physical-method-assay-semantics', 'regression-catalogue'),
    'R08': ('catalogue-full-scale-parity',),
    'R09': ('catalogue-full-scale-parity', 'shared-context-inventory-answer', 'sst-independent-numerical-oracle'),
    'R10': ('catalogue-full-scale-parity', 'owner-role-source-revocation-and-held-history'),
    'R11': ('durable-ack-cancel-continuation-rollover', 'regression-frozen'),
    'R12': ('known-zero-unknown-and-forged-snapshot', 'regression-catalogue'),
    'R13': ('four-source-physical-method-assay-semantics', 'sst-independent-numerical-oracle', 'regression-frozen'),
    'R14': ('four-source-physical-method-assay-semantics', 'experimental-bytes-and-approval', 'research-and-experiment-attachment-composition'),
    'R15': ('browser-catalogue', 'catalogue-full-scale-parity', 'regression-browser'),
    'R16': ('browser-research',),
    'R17': ('explicit-attach-pin-multichat-and-experiment-history', 'durable-ack-cancel-continuation-rollover', 'browser-catalogue'),
    'R18': ('durable-ack-cancel-continuation-rollover', 'browser-research'),
    'R19': ('known-zero-unknown-and-forged-snapshot', 'regression-controller'),
    'R20': ('durable-ack-cancel-continuation-rollover', 'regression-controller'),
    'R21': ('interrupted-committed-step-replays-without-duplicate-effect', 'durable-ack-cancel-continuation-rollover', 'regression-runs'),
    'R22': ('shared-context-inventory-answer', 'research-and-experiment-attachment-composition', 'regression-evidence'),
    'R23': ('experimental-bytes-and-approval', 'explicit-attach-pin-multichat-and-experiment-history', 'regression-experiments'),
    'R24': ('original-c23-physical-evidence',),
    'R25': ('experimental-bytes-and-approval', 'research-and-experiment-attachment-composition', 'regression-experiments', 'browser-experiments'),
    'R26': ('browser-accessibility',),
    'R27': ('regression-legacy', 'isolation-legacy-denial'),
    'R28': ('matched-controller-comparison', 'regression-framework', 'regression-command'),
    'R29': ('isolation-offline-contract',),
    'R30': ('planning-and-original-receipts',),
    'R31': ('planning-and-original-receipts', 'browser-catalogue', 'browser-research', 'browser-experiments'),
    'R32': ('isolation-offline-contract', 'isolation-legacy-denial'),
    'R33': ('transfer-independent', 'transfer-rejections', 'transfer-withdrawal'),
}
GATE_MEMBERS = {
    'G0': ('R30',),
    'G1': ('R01', 'R02', 'R05', 'R11', 'R13', 'R14', 'R19', 'R22', 'R28', 'R33'),
    'G2': ('R03', 'R04', 'R06', 'R10', 'R23', 'R33'),
    'G3': ('R07', 'R08', 'R09', 'R10', 'R11', 'R12', 'R15', 'R17', 'R28'),
    'G4': ('R05', 'R17', 'R18', 'R19', 'R20', 'R21', 'R22', 'R28'),
    'G5': ('R14', 'R23', 'R24', 'R25'),
    'G6': ('R15', 'R16', 'R17', 'R18', 'R25', 'R26', 'R31'),
    'G7': ('R27', 'R29'), 'G8': ('R31',), 'G9': ('R27', 'R29', 'R32', 'R33'),
}
LIVE_GATES = {
    'authenticated-beta': 'Authenticated beta serving, independent sessions and exact-origin behavior',
    'cloud-queue': 'Actual Cloud Tasks, durable outbox, leases and private invocation',
    'production-worker-port': 'Production retained execution port and supervisor, current containment/admission lifecycle',
    'iam-network-isolation': 'Actual IAM/network/resource isolation and legacy denial',
    'backup-recovery': 'Current live database/storage backup, restore and uncertain-state recovery',
    'dns-tls': 'Authorized beta domain DNS/TLS and origin validation',
    'real-data-science': 'Separately authorized real data transfer, regeneration and scientific approval',
    'live-model-evaluation': 'Paid/live provider comparison with exact matched inputs and telemetry',
    'release-rehearsal': 'C27 independent migration/rollback/promotion rehearsal and operator acceptance',
}

C24_LIVE_GATES = ('whole_site_target_and_live_action_authorization', 'authenticated_v1_host_proxy_and_bootstrap', 'real_cloud_tasks_adapter_outbox_and_private_invocation', 'production_experiment_supervisor_health_and_drain', 'worker_boot_image_unique_id_and_disk_sourceImageId', 'DNS_TLS_Host_OAuth_cookie_and_cross_origin_validation', 'inherited_IAM_and_network_legacy_access_denials', 'two_simultaneous_sandboxes_and_measured_host_capacity', 'crash_reboot_uncertain_ACK_recovery_and_physical_proof_release', 'independent_backup_restore_retention_budget_and_alert_readbacks', 'C26_C27_integrated_acceptance_and_release_promotion')


def combine(values):
    if any(value not in {'passed', 'failed', 'blocked', 'not_run'} for value in values):
        raise ValueError('Unknown acceptance observation status')
    return ('failed' if 'failed' in values else 'blocked' if 'blocked' in values
        else 'not_run' if not values or 'not_run' in values else 'passed')


def master_requirements(text):
    rows = {}
    for line in text.splitlines():
        if re.match(r'\| R[0-9]{2} \|', line):
            fields = [field.strip() for field in line.split('|')[1:-1]]
            if len(fields) != 4 or fields[0] in rows:
                raise ValueError('Master requirement table is malformed')
            rows[fields[0]] = dict(zip(('description', 'owner', 'gates'), fields[1:]))
    if set(rows) != set(BINDINGS):
        raise ValueError('Every master R01-R33 must have an explicit current binding')
    gates = {match.group(1) for match in re.finditer(r'^\| (G[0-9]) —', text, re.MULTILINE)}
    if gates != set(GATE_MEMBERS):
        raise ValueError('Every master G0-G9 must have an explicit current binding')
    return rows


def build_matrix(*, master_text, source_revision, checks, comparisons=()):
    """Build local observations and distinct live gates without claiming full R acceptance.

    Check entries carry actual capture digests. A schema/report cannot itself
    certify caller-supplied observations: the runner verifies sources and files.
    """
    masters = master_requirements(master_text)
    requirements, results, matrix, local = [], [], [], {}
    for identity, spec in masters.items():
        ids = BINDINGS[identity]
        observations = [checks.get(key, {'id': key, 'status': 'not_run',
            'reason': 'No attributable current observation supplied'}) for key in ids]
        status = combine([item['status'] for item in observations])
        kind = 'original-physical' if identity == 'R24' else 'actual-service-synthetic'
        refs = []
        for item in observations:
            if item.get('sha256'):
                refs.append({'id': item['id'], 'sha256': item['sha256'],
                    'source_revision': item.get('source_revision', source_revision), 'kind': kind})
        reasons = [item.get('reason') or item['id'] + ': ' + item['status']
            for item in observations if item['status'] != 'passed']
        requirements.append({'id': identity + '.preparation', 'phase': 'preparation',
            'owner': spec['owner'], 'evidence_kind': kind})
        results.append({'requirement_id': identity + '.preparation', 'status': status,
            'reason': '; '.join(reasons)[:4000] if reasons else None, 'evidence': refs})
        local[identity] = status
        matrix.append({'id': identity, **spec, 'preparation_status': status, 'check_ids': list(ids),
            'qualification': ('Historical C23 physical observations at their original source/host; no current rerun'
                if identity == 'R24' else 'Local deterministic preparation only; full operational wording is retained above'),
            'full_operational_acceptance': 'not_run'})
    for identity, members in GATE_MEMBERS.items():
        status = combine([local[key] for key in members])
        if identity == 'G3':
            status = combine([status, checks.get('catalogue-scale-lab-budget', {}).get('status', 'not_run')])
        requirements.append({'id': identity + '.preparation', 'phase': 'preparation',
            'owner': 'C26', 'evidence_kind': 'actual-service-synthetic'})
        summary = {'members': {key: local[key] for key in members}, 'status': status}
        if identity == 'G3':
            summary['performance'] = checks.get('catalogue-scale-lab-budget', {'status': 'not_run'})
        results.append({'requirement_id': identity + '.preparation', 'status': status,
            'reason': None if status == 'passed' else 'One or more mapped local checks or the declared G3 lab budget remain open',
            'evidence': [{'id': identity + '-accounting', 'sha256': content_sha256(summary),
                'source_revision': source_revision, 'kind': 'actual-service-synthetic'}]})
        matrix.append({'id': identity, 'requirement_ids': list(members), 'preparation_status': status,
            'full_operational_acceptance': 'not_run'})
    for identity, description in LIVE_GATES.items():
        requirements.append({'id': identity, 'phase': 'release', 'owner': 'C24/C27/operator', 'evidence_kind': 'live-service'})
        results.append({'requirement_id': identity, 'status': 'not_run',
            'reason': description + '; local synthetic observations cannot establish this gate', 'evidence': []})
    for identity in C24_LIVE_GATES:
        requirements.append({'id': 'C24.' + identity, 'phase': 'release', 'owner': 'C24/C27/operator', 'evidence_kind': 'live-service'})
        results.append({'requirement_id': 'C24.' + identity, 'status': 'not_run',
            'reason': 'Original C24 live gate remains unrun: ' + identity, 'evidence': []})
    report = build_acceptance_report(source_revision=source_revision, requirements=requirements,
        results=results, comparisons=comparisons)
    return {'master_sha256': content_sha256(master_text), 'matrix': matrix,
        'acceptance_report': report.model_dump(mode='json')}
