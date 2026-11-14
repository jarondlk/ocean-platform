"""Guarded rollout of the fixed, separately qualified B1 repair candidate.

The original writer/receipts remain unchanged. Only image/revision/traffic and
the two existing Research admission flags may change; never retry a PATCH.
"""

import argparse
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import time
import urllib.parse

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import beta_b0_preflight as guard
from scripts import beta_b1_apply as apply
from scripts import beta_b1_rollout as original

ROOT = original.ROOT
PROOF = ROOT / 'docs/plans/ocean-v1/beta/b1-20261114'
CONTRACT = ROOT / 'deploy/gcp/beta/b1/repair-contract.json'
PHASES = ('controller', 'stage', 'promote', 'admit-stage', 'admit-promote')


def baseline(service, kind, contract):
    image = original.main_container(service, kind)['image']
    guard.require(image in {original.NEW, contract['image']})
    normalized = deepcopy(service)
    original.main_container(normalized, kind)['image'] = original.NEW
    # Original full config hashes still bind all sidecars, identities, secrets,
    # networking, ingress, scaling and timeouts. Only the selected image differs.
    return original.verify_baseline(normalized, kind, contract)


def plan(service, phase, contract):
    guard.require(phase in PHASES)
    kind = 'controller' if phase == 'controller' else 'serving'
    baseline(service, kind, contract)
    before = original.configuration(service)
    expected = deepcopy(before)
    ready, created = (service[key].split('/')[-1] for key in ('latestReadyRevision', 'latestCreatedRevision'))
    image = original.main_container(service, kind)['image']
    revision = contract['revisions']['controller' if kind == 'controller' else 'live' if phase.startswith('admit') else 'stage']
    guard.require(revision.startswith(service['name'].split('/')[-1] + '-') and len(revision) <= 63)
    new_revision = phase in {'controller', 'stage', 'admit-stage'}
    if new_revision:
        guard.require(created == ready)
    if phase in {'controller', 'stage'}:
        guard.require(image == original.NEW and ready == contract['initial_revisions'][kind])
        guard.require(service['traffic'] == [{'type': 'TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST', 'percent': 100}])
        original.main_container(expected, kind)['image'] = contract['image']
        if kind == 'serving':
            guard.require(not original.flag_state(service))
            expected['traffic'] = original.fixed_traffic(ready)
    elif phase == 'promote':
        guard.require(image == contract['image'] and not original.flag_state(service)
                      and created == contract['revisions']['stage']
                      and ready in {contract['initial_revisions']['serving'], created}
                      and service['traffic'] == original.fixed_traffic(contract['initial_revisions']['serving']))
        expected['traffic'] = original.fixed_traffic(revision)
    elif phase == 'admit-stage':
        guard.require(image == contract['image'] and not original.flag_state(service)
                      and ready == contract['revisions']['stage']
                      and service['traffic'] == original.fixed_traffic(ready))
        for item in original.main_container(expected, kind)['env']:
            if item['name'] in original.FLAGS:
                item['value'] = 'true'
    else:
        guard.require(image == contract['image'] and original.flag_state(service)
                      and created == contract['revisions']['live']
                      and ready in {contract['revisions']['stage'], created}
                      and service['traffic'] == original.fixed_traffic(contract['revisions']['stage']))
        expected['traffic'] = original.fixed_traffic(revision)
    body = {'name': service['name'], 'etag': service['etag']}
    mask = []
    if new_revision:
        body['template'] = {'containers': deepcopy(expected['template']['containers']), 'revision': revision}
        mask += ['template.containers', 'template.revision']
    if before['traffic'] != expected['traffic']:
        body['traffic'] = expected['traffic']
        mask.append('traffic')
    return {'phase': phase, 'kind': kind, 'body': body, 'update_mask': ','.join(mask),
            'before_configuration_sha256': original.sha(before), 'expected_configuration': expected,
            'expected_ready_revision': revision}


def readback(before, after, proposal, contract, staged=None):
    baseline(after, proposal['kind'], contract)
    guard.require(original.sha(original.configuration(before)) == proposal['before_configuration_sha256']
                  and original.configuration(after) == proposal['expected_configuration']
                  and int(after['generation']) > int(before['generation']))
    expected = proposal['expected_ready_revision']
    guard.require(after['latestCreatedRevision'].split('/')[-1] == expected)
    idle = proposal['phase'] in {'stage', 'admit-stage'}
    if idle and after['latestReadyRevision'].split('/')[-1] != expected:
        guard.require(after['latestReadyRevision'] == before['latestReadyRevision'] and staged is not None)
        guard.require(original.verify_revision(after, staged, expected)['retired'])
    else:
        guard.require(after['latestReadyRevision'].split('/')[-1] == expected)
    return {'phase': proposal['phase'], 'generation': after['generation'], 'image': contract['image'],
            'ready_revision': after['latestReadyRevision'].split('/')[-1],
            'runtime_startup_verified': not idle, 'all_other_configuration_preserved': True}


def qualify(directory, contract):
    guard.require(contract['hosted_acceptance_pending'] is False)
    manifest = guard.document((PROOF / 'repair-production-source-manifest.json').read_bytes())
    pins = manifest['sources']
    guard.require(manifest['revision'] == contract['runtime_commit'] and len(pins) == 180
                  and all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest for path, digest in pins.items()))
    old = guard.document((ROOT / 'docs/plans/ocean-v1/beta/research-20261109/provider-amendment06/production-source-manifest.json').read_bytes())['sources']
    guard.require(set(pins) == set(old) and sorted(p for p in pins if pins[p] != old[p]) ==
                  ['orchestration/beta_vertex_research.py', 'orchestration/research_evidence.py'])
    build = guard.document((directory / 'build.json').read_bytes())
    wanted = guard.document((PROOF / 'repair-cloudbuild.json').read_bytes())
    guard.require(build['id'] == contract['build_id'] and build['status'] == 'SUCCESS'
                  and build['projectId'] == original.PROJECT and build['serviceAccount'] == wanted['serviceAccount']
                  and build['images'] == wanted['images'] and build['timeout'] == wanted.get('timeout', '3600s')
                  and not any(k in build for k in ('secrets', 'availableSecrets', 'substitutions', 'buildTriggerId')))
    options = deepcopy(build['options'])
    guard.require(options.pop('pool', {}) == {} and options.pop('workerRelease', 'legacy') == 'legacy')
    options['diskSizeGb'] = int(options['diskSizeGb'])
    guard.require(options == wanted['options'] and len(build['steps']) == len(wanted['steps']) == 4)
    for actual, expected in zip(build['steps'], wanted['steps']):
        guard.require(actual['status'] == 'SUCCESS')
        value = {k: v for k, v in actual.items() if k not in {'status', 'timing', 'pullTiming'}}
        expected = deepcopy(expected)
        if expected['id'] == 'immutable-source-label-proof':
            expected['args'] = [v.replace('$$', '$') for v in expected['args']]
        guard.require(value == expected)
    images = build['results']['images']
    guard.require(len(images) == 1 and images[0]['digest'] == contract['image'].split('@')[1])
    source = build['sourceProvenance']['resolvedStorageSource']
    guard.require(source['bucket'] == original.PROJECT + '-build-source' and source['object'].startswith('source/')
                  and str(source['generation']).isdecimal() and build['source'] == {'storageSource': source})
    archive = directory / 'staged-source.tgz'
    digest = hashlib.sha256(archive.read_bytes()).digest()
    uri = 'gs://' + source['bucket'] + '/' + source['object'] + '#' + str(source['generation'])
    hashes = build['sourceProvenance']['fileHashes'][uri]['fileHash']
    guard.require(any(item['type'] == 'SHA256' and base64.urlsafe_b64decode(item['value']) == digest for item in hashes))
    expected_files = guard.document((PROOF / 'repair-build-context.json').read_bytes())
    guard.require(original.sha(expected_files) == contract['build_context_sha256'])
    with tarfile.open(archive, 'r:gz') as tar:
        files = {}
        for member in tar.getmembers():
            guard.require(not member.name.startswith('/') and '..' not in Path(member.name).parts
                          and (member.isdir() or member.isfile()))
            if member.isfile():
                guard.require(member.name not in files and member.size <= 1048576)
                files[member.name] = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
        guard.require(files == expected_files)
    run = guard.document((directory / 'focused-run.json').read_bytes())
    jobs = guard.document((directory / 'focused-jobs.json').read_bytes())['jobs']
    guard.require(run['id'] == contract['ci_run_id'] and run['head_sha'] == contract['ci_source_commit']
                  and run['status'] == 'completed' and run['conclusion'] == 'success'
                  and len(jobs) == 1 and jobs[0]['id'] == contract['ci_job_id']
                  and jobs[0]['run_id'] == run['id'] and jobs[0]['conclusion'] == 'success'
                  and jobs[0]['status'] == 'completed'
                  and all(s['status'] == 'completed' and (s['conclusion'] == 'success' or
                      s['name'] == 'Verify repair, privacy and unchanged host contracts' and s['conclusion'] == 'skipped')
                      for s in jobs[0]['steps']))
    guard.require(hashlib.sha256((directory / 'focused.log').read_bytes()).hexdigest() == contract['ci_log_sha256'])
    units_run = guard.document((directory / 'units-run.json').read_bytes())
    units_jobs = guard.document((directory / 'units-jobs.json').read_bytes())['jobs']
    guard.require(units_run['id'] == 43619074592 and units_run['head_sha'] == contract['runtime_commit']
                  and units_run['status'] == 'completed' and units_run['conclusion'] == 'failure'
                  and len(units_jobs) == 1 and units_jobs[0]['id'] == 132520434482
                  and any(s['name'] == 'Verify repair, privacy and unchanged host contracts'
                          and s['status'] == 'completed' and s['conclusion'] == 'success' for s in units_jobs[0]['steps']))
    guard.require(hashlib.sha256((directory / 'units-native-setup.log').read_bytes()).hexdigest() == contract['unit_ci_log_sha256'])
    return {'source_paths': 180, 'intentional_runtime_supersessions': 2, 'build_id': build['id'],
            'ci_run_id': run['id'], 'focused_source_bound_delivery_verified': True}


def execute(cloud, directory, phase, *, validate_only, execution_name=None, not_before=None):
    contract = guard.document(CONTRACT.read_bytes())
    qualification = qualify(directory, contract)
    kind = 'controller' if phase == 'controller' else 'serving'
    endpoint = 'https://run.googleapis.com/v2/' + contract['services'][kind]['name']
    before = cloud.request(endpoint)
    proposal = plan(before, phase, contract)
    target = directory / (phase + ('-validate' if validate_only else '-apply'))
    guard.require(not target.exists())
    target.mkdir(mode=0o700)
    def save(name, data):
        (target / name).write_text(json.dumps(data, indent=2) + '\n')
    save('before.json', before)
    save('plan.json', {**proposal, 'candidate_qualification': qualification})
    if not validate_only:
        guard.require(bool(execution_name) and bool(not_before))
        apply.fresh_entry(cloud, target, execution_name, not_before, phase)
        if kind == 'serving':
            controller = cloud.request('https://run.googleapis.com/v2/' + contract['services']['controller']['name'])
            baseline(controller, 'controller', contract)
            guard.require(original.main_container(controller, 'controller')['image'] == contract['image']
                          and controller['latestReadyRevision'].split('/')[-1] == contract['revisions']['controller'])
        if phase in {'promote', 'admit-promote'}:
            revision = cloud.request(endpoint + '/revisions/' + proposal['expected_ready_revision'])
            original.verify_revision(before, revision, proposal['expected_ready_revision'])
            save('staged-revision-before.json', revision)
    current = cloud.request(endpoint)
    guard.require(current['etag'] == before['etag'] and original.configuration(current) == original.configuration(before))
    params = {'updateMask': proposal['update_mask']}
    if validate_only:
        params['validateOnly'] = 'true'
    operation = cloud.request(endpoint + '?' + urllib.parse.urlencode(params), personal=kind == 'controller',
                              method='PATCH', body=proposal['body'])
    save('operation.json', operation)
    if validate_only:
        after = cloud.request(endpoint)
        guard.require(after == before)
        return {'phase': phase, 'validated_only': True, 'service_unchanged': True}
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        after = cloud.request(endpoint)
        if str(after['generation']) == str(after['observedGeneration']) and after.get('terminalCondition', {}).get('state') in {'CONDITION_SUCCEEDED', 'CONDITION_FAILED'}:
            save('after.json', after)
            staged = None
            if phase in {'stage', 'admit-stage'}:
                staged = cloud.request(endpoint + '/revisions/' + proposal['expected_ready_revision'])
                save('staged-revision-after.json', staged)
            elif after.get('terminalCondition', {}).get('state') == 'CONDITION_SUCCEEDED' and after['latestReadyRevision'].split('/')[-1] != proposal['expected_ready_revision']:
                time.sleep(3)
                continue
            result = readback(before, after, proposal, contract, staged)
            save('result.json', result)
            return result
        time.sleep(3)
    raise guard.Rejected('Inspect uncertain PATCH outcome before any retry')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--phase', choices=PHASES, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--validate-only', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--observer')
    parser.add_argument('--not-before')
    args = parser.parse_args()
    import os
    directory = args.directory.resolve()
    guard.require(ROOT not in directory.parents and directory.is_dir() and directory.stat().st_uid == os.geteuid()
                  and not directory.stat().st_mode & 0o077)
    os.umask(0o077)
    try:
        result = execute(apply.Cloud(), directory, args.phase, validate_only=args.validate_only,
                         execution_name=args.observer, not_before=args.not_before)
    except Exception:
        print('{"state":"repair_rollout_stopped_inspect_private_phase_before_retry"}')
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
