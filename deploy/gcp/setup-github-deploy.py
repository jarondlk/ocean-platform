#!/usr/bin/env python3
"""Print the GitHub deployment IAM plan; apply only with explicit --apply."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

PROJECT = 'data-infra-infobio'
NUMBER = '469489188516'
REPO_ID = '1224179187'
OWNER_ID = '82869981'
POOL = 'ocean-github'
PROVIDER = 'release-workflow'
DEPLOYER = f'ocean-release-deployer@{PROJECT}.iam.gserviceaccount.com'
BUILDER = f'ocean-release-build@{PROJECT}.iam.gserviceaccount.com'
WORKFLOW = 'jarondlk/ocean-platform/.github/workflows/deploy-release.yml@refs/heads/main'
CONDITION = (f"assertion.repository_id == '{REPO_ID}' && assertion.repository_owner_id == '{OWNER_ID}'"
             f" && assertion.ref == 'refs/heads/main' && assertion.workflow_ref == '{WORKFLOW}'"
             " && assertion.event_name == 'workflow_dispatch'"
             " && assertion.sub == 'repo:jarondlk/ocean-platform:environment:production'")
ROLES = {
    'oceanReleaseSubmitter': ['cloudbuild.builds.create', 'cloudbuild.builds.get', 'cloudbuild.builds.list',
                             'serviceusage.services.use', 'resourcemanager.projects.get', 'run.operations.get'],
    'oceanReleaseRuntime': ['run.services.get', 'run.services.update', 'run.revisions.get', 'run.revisions.list',
                           'run.jobs.get', 'run.jobs.update', 'run.executions.get', 'run.executions.list', 'run.operations.get'],
    'oceanReleaseJobRunner': ['run.jobs.run', 'run.jobs.runWithOverrides'],
    'oceanReleaseSource': ['storage.buckets.get', 'storage.objects.create', 'storage.objects.get'],
}


def commands(role_dir):
    member = 'serviceAccount:' + DEPLOYER
    yield ['services', 'enable', 'sts.googleapis.com']
    for account in ['ocean-release-deployer', 'ocean-release-build']:
        yield ['iam', 'service-accounts', 'create', account, '--display-name=' + account]
    yield ['iam', 'workload-identity-pools', 'create', POOL, '--location=global', '--display-name=OCEAN GitHub releases']
    yield ['iam', 'workload-identity-pools', 'providers', 'create-oidc', PROVIDER, '--location=global',
           '--workload-identity-pool=' + POOL, '--issuer-uri=https://token.actions.githubusercontent.com',
           '--attribute-mapping=google.subject=assertion.sub,attribute.repository_id=assertion.repository_id',
           '--attribute-condition=' + CONDITION]
    principal = f'principalSet://iam.googleapis.com/projects/{NUMBER}/locations/global/workloadIdentityPools/{POOL}/attribute.repository_id/{REPO_ID}'
    yield ['iam', 'service-accounts', 'add-iam-policy-binding', DEPLOYER, '--member=' + principal,
           '--role=roles/iam.workloadIdentityUser']
    for role in ROLES:
        yield ['iam', 'roles', 'create', role, '--file=' + str(role_dir / (role + '.json'))]
    yield ['projects', 'add-iam-policy-binding', PROJECT, '--member=' + member,
           '--role=projects/' + PROJECT + '/roles/oceanReleaseSubmitter', '--condition=None']
    yield ['run', 'services', 'add-iam-policy-binding', 'ocean-platform', '--region=asia-northeast1',
           '--member=' + member, '--role=projects/' + PROJECT + '/roles/oceanReleaseRuntime']
    for job in ['ocean-migrate', 'ocean-pipeline', 'ocean-embedding', 'ocean-evaluation', 'ocean-anemone-process']:
        yield ['run', 'jobs', 'add-iam-policy-binding', job, '--region=asia-northeast1', '--member=' + member,
               '--role=projects/' + PROJECT + '/roles/oceanReleaseRuntime']
    for job in ['ocean-migrate', 'ocean-pipeline']:
        yield ['run', 'jobs', 'add-iam-policy-binding', job, '--region=asia-northeast1', '--member=' + member,
               '--role=projects/' + PROJECT + '/roles/oceanReleaseJobRunner']
    for account in [BUILDER, f'ocean-platform@{PROJECT}.iam.gserviceaccount.com', f'ocean-jobs@{PROJECT}.iam.gserviceaccount.com']:
        yield ['iam', 'service-accounts', 'add-iam-policy-binding', account, '--member=' + member, '--role=roles/iam.serviceAccountUser']
    bucket = f'gs://{PROJECT}_cloudbuild'
    yield ['storage', 'buckets', 'add-iam-policy-binding', bucket, '--member=' + member,
           '--role=projects/' + PROJECT + '/roles/oceanReleaseSource']
    yield ['storage', 'buckets', 'add-iam-policy-binding', bucket, '--member=serviceAccount:' + BUILDER, '--role=roles/storage.objectViewer']
    yield ['artifacts', 'repositories', 'add-iam-policy-binding', 'ocean-platform', '--location=asia-northeast1',
           '--member=serviceAccount:' + BUILDER, '--role=roles/artifactregistry.writer']
    yield ['artifacts', 'repositories', 'add-iam-policy-binding', 'ocean-platform', '--location=asia-northeast1',
           '--member=' + member, '--role=roles/artifactregistry.reader']
    yield ['projects', 'add-iam-policy-binding', PROJECT, '--member=serviceAccount:' + BUILDER,
           '--role=roles/logging.logWriter', '--condition=None']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ocean-github-roles-') as directory:
        root = Path(directory)
        for name, permissions in ROLES.items():
            (root / (name + '.json')).write_text(json.dumps({'title': name, 'stage': 'GA', 'includedPermissions': permissions}))
        for command in commands(root):
            if not args.apply:
                print(json.dumps(['gcloud', *command, '--project=' + PROJECT]))
                continue
            result = subprocess.run(['gcloud', *command, '--project=' + PROJECT, '--quiet', '--format=json'], capture_output=True, text=True)
            if result.returncode:
                # Existing resources must be inspected against this definition before
                # considering a resumed setup complete; never silently replace their IAM.
                if 'ALREADY_EXISTS' not in result.stderr and 'already exists' not in result.stderr:
                    raise SystemExit(result.stderr)
            print('Configured: ' + ' '.join(command[:4]), flush=True)
    print(f'GCP_RELEASE_IDENTITY_PROVIDER=projects/{NUMBER}/locations/global/workloadIdentityPools/{POOL}/providers/{PROVIDER}')
    print('GCP_RELEASE_SERVICE_ACCOUNT=' + DEPLOYER)


if __name__ == '__main__':
    main()
