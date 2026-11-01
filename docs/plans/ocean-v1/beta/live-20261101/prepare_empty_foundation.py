"""Explicit beta-only empty foundation; no runtime, secret values or IAM grants."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

DIRECTORY = Path(__file__).resolve().parent
PROJECT = 'ocean-v1-beta-20261101'
NUMBER = '534831104543'
REGION = 'asia-northeast1'


def commands(plan):
    jobs = [
        ('registry', ['artifacts', 'repositories', 'create', plan['registry'],
            '--repository-format=docker', '--location=' + REGION],
            ['artifacts', 'repositories', 'describe', plan['registry'], '--location=' + REGION]),
        ('network', ['compute', 'networks', 'create', plan['network'],
            '--subnet-mode=custom', '--bgp-routing-mode=regional'],
            ['compute', 'networks', 'describe', plan['network']]),
        ('subnet', ['compute', 'networks', 'subnets', 'create', plan['subnet'],
            '--network=' + plan['network'], '--range=' + plan['subnet_cidr'],
            '--region=' + REGION, '--enable-private-ip-google-access'],
            ['compute', 'networks', 'subnets', 'describe', plan['subnet'], '--region=' + REGION]),
    ]
    for name in plan['identities']:
        jobs.append(('identity-' + name, ['iam', 'service-accounts', 'create', name,
            '--display-name=' + name], ['iam', 'service-accounts', 'describe',
                name + '@' + PROJECT + '.iam.gserviceaccount.com']))
    for kind, name in plan['buckets'].items():
        jobs.append(('bucket-' + kind, ['storage', 'buckets', 'create', 'gs://' + name,
            '--location=' + REGION, '--default-storage-class=STANDARD',
            '--uniform-bucket-level-access', '--public-access-prevention'],
            ['storage', 'buckets', 'describe', 'gs://' + name, '--raw']))
    for name in plan['secrets']:
        jobs.append(('secret-' + name, ['secrets', 'create', name,
            '--replication-policy=user-managed', '--locations=' + REGION],
            ['secrets', 'describe', name]))
    queue = plan['queue']
    jobs.append(('queue', ['tasks', 'queues', 'create', queue['name'],
        '--location=' + REGION, '--max-concurrent-dispatches=1',
        '--max-dispatches-per-second=1', '--max-attempts=3',
        '--max-retry-duration=3600s', '--min-backoff=10s', '--max-backoff=300s'],
        ['tasks', 'queues', 'describe', queue['name'], '--location=' + REGION]))
    return jobs


def call(arguments):
    return subprocess.run(['gcloud', *arguments, '--project=' + PROJECT, '--quiet'],
        capture_output=True, text=True, timeout=240)


def validate(name, value, plan):
    if name == 'registry':
        assert value['name'] == f'projects/{PROJECT}/locations/{REGION}/repositories/' + plan['registry']
        assert value['format'] == 'DOCKER'
    elif name == 'network':
        assert value['selfLink'].endswith(f'/projects/{PROJECT}/global/networks/' + plan['network'])
        assert value['autoCreateSubnetworks'] is False
    elif name == 'subnet':
        assert value['selfLink'].endswith(f'/projects/{PROJECT}/regions/{REGION}/subnetworks/' + plan['subnet'])
        assert value['network'].endswith(f'/projects/{PROJECT}/global/networks/' + plan['network'])
        assert value['ipCidrRange'] == plan['subnet_cidr'] and value['privateIpGoogleAccess'] is True
    elif name.startswith('identity-'):
        assert value['email'] == name.removeprefix('identity-') + '@' + PROJECT + '.iam.gserviceaccount.com'
        assert value['projectId'] == PROJECT and not value.get('disabled', False)
    elif name.startswith('bucket-'):
        assert value['name'] == plan['buckets'][name.removeprefix('bucket-')]
        assert str(value.get('project_number', value.get('projectNumber'))) == NUMBER
        assert value['location'].lower() == REGION
        configuration = value.get('iamConfiguration', {})
        uniform = value.get('uniform_bucket_level_access', configuration.get('uniformBucketLevelAccess', {}).get('enabled'))
        public = value.get('public_access_prevention', configuration.get('publicAccessPrevention'))
        assert uniform is True and public == 'enforced'
    elif name.startswith('secret-'):
        assert value['name'] == f'projects/{NUMBER}/secrets/' + name.removeprefix('secret-')
        assert value['replication']['userManaged']['replicas'] == [{'location': REGION}]
    elif name == 'queue':
        assert value['name'] == f'projects/{PROJECT}/locations/{REGION}/queues/' + plan['queue']['name']
        assert value['state'] == 'PAUSED'
        assert value['rateLimits']['maxConcurrentDispatches'] == 1
        assert value['rateLimits']['maxDispatchesPerSecond'] == 1.0
        assert value['retryConfig']['maxAttempts'] == 3
    else:
        raise ValueError('Unknown foundation resource')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plan = json.loads((DIRECTORY / 'resources-plan.json').read_text())
    assert plan['project_id'] == PROJECT and plan['project_number'] == NUMBER
    assert plan['region'] == REGION and plan['queue']['target_state'] == 'PAUSED'
    jobs = commands(plan)
    if not args.apply:
        print(json.dumps({'project': PROJECT, 'mode': 'plan-only',
            'operations': [name for name, _, _ in jobs], 'runtime_creation': False}, indent=2))
        return
    identity = call(['projects', 'describe', PROJECT, '--format=json'])
    identity.check_returncode()
    assert json.loads(identity.stdout)['projectNumber'] == NUMBER
    path = DIRECTORY / 'empty-foundation-execution.json'
    receipt = json.loads(path.read_text()) if path.exists() else {
        'version': 'beta-empty-foundation-execution-v1', 'project_id': PROJECT,
        'project_number': NUMBER, 'operations': {}, 'status': 'in_progress',
        'runtime_resources_created': False, 'IAM_runtime_grants_created': False,
        'secret_versions_created': False,
    }
    assert receipt['project_id'] == PROJECT and receipt['project_number'] == NUMBER

    def save():
        receipt['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        temporary.replace(path)

    for name, create, describe in jobs:
        if receipt['operations'].get(name, {}).get('status') == 'verified':
            continue
        row = receipt['operations'].setdefault(name, {
            'create_command': ['gcloud', *create, '--project=' + PROJECT, '--quiet'],
            'describe_command': ['gcloud', *describe, '--format=json', '--project=' + PROJECT, '--quiet']})
        row['active_describe_command'] = ['gcloud', *describe, '--format=json', '--project=' + PROJECT, '--quiet']
        save()
        found = call([*describe, '--format=json'])
        if found.returncode != 0:
            if not any(word in found.stderr.lower() for word in
                    ('not_found', 'not found', 'does not exist', 'not exist', '404')):
                row.update(status='blocked', error=found.stderr)
                save()
                raise RuntimeError('Readback failed for ' + name + '; no blind create/retry')
            created = call(create)
            row.update(create_returncode=created.returncode,
                create_stdout=created.stdout, create_stderr=created.stderr)
            save()
            if created.returncode != 0:
                row['status'] = 'failed'
                save()
                raise RuntimeError('Creation failed for ' + name)
        else:
            row['preexisting_readback'] = json.loads(found.stdout)
        if name == 'queue':
            paused = call(['tasks', 'queues', 'pause', plan['queue']['name'], '--location=' + REGION])
            row.update(pause_returncode=paused.returncode, pause_stdout=paused.stdout, pause_stderr=paused.stderr)
            save()
            paused.check_returncode()
        for attempt in range(6):
            readback = call([*describe, '--format=json'])
            if readback.returncode == 0:
                break
            row.setdefault('readback_errors', []).append({
                'returncode': readback.returncode, 'stderr': readback.stderr})
            save()
            if attempt == 5 or not any(word in readback.stderr.lower() for word in
                    ('not_found', 'not found', 'does not exist', 'not exist', '404')):
                break
            time.sleep(2)
        readback.check_returncode()
        row['readback'] = json.loads(readback.stdout)
        save()
        validate(name, row['readback'], plan)
        row['status'] = 'verified'
        save()
        print(json.dumps({'operation': name, 'status': 'verified'}), flush=True)
    receipt['status'] = 'verified_empty_foundation'
    save()


if __name__ == '__main__':
    main()
