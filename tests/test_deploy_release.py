"""Release gates and rollback behavior, without contacting cloud services."""
import copy

import pytest

from scripts import deploy_release as deploy

SHA = 'a' * 40


def service():
    return {'metadata': {'resourceVersion': '1'}, 'spec': {'template': {'spec': {'containers': [
        {'name': 'api', 'image': 'old-api', 'env': [
            {'name': 'SOURCE_COMMIT', 'value': SHA}, {'name': 'AUTH_MODE', 'value': 'required'},
            {'name': 'JOB_EXECUTION_MODE', 'value': 'external'}, {'name': 'PROVENANCE_READ_MODE', 'value': 'snapshot'}]},
        {'name': 'frontend', 'image': 'old-ui', 'env': [{'name': 'SOURCE_COMMIT', 'value': SHA}]}
    ]}}}, 'status': {'traffic': [{'revisionName': 'old', 'percent': 100}]}}


@pytest.mark.parametrize('tag', ['main', 'v1.2.3;echo hacked', '-v1.2.3', 'v1.2.3-rc1', '../v1.2.3', 'v1.2.3\n'])
def test_reject_untrusted_or_unstable_release_inputs(tag):
    with pytest.raises(deploy.DeploymentError):
        deploy.validate_tag(tag)


def test_stable_tag():
    assert deploy.validate_tag('v0.4.5') == 'v0.4.5'


def test_split_traffic_ignores_tags_and_resolves_revisions():
    data = service()
    data['status']['traffic'] = [{'revisionName': 'a', 'percent': 60}, {'revisionName': 'b', 'percent': 40},
                                {'revisionName': 'candidate', 'tag': 'release-candidate'}]
    assert deploy.traffic_map(data) == {'a': 60, 'b': 40}
    data['status']['traffic'][0]['percent'] = 50
    with pytest.raises(deploy.DeploymentError):
        deploy.traffic_map(data)


def test_required_boundaries_and_source_agreement():
    data = service()
    deploy.check_service(data)
    changed = copy.deepcopy(data)
    changed['spec']['template']['spec']['containers'][0]['env'][1]['value'] = 'disabled'
    with pytest.raises(deploy.DeploymentError):
        deploy.check_service(changed)
    data['spec']['template']['spec']['containers'][1]['env'][0]['value'] = 'b' * 40
    with pytest.raises(deploy.DeploymentError):
        deploy.check_service(data)


def test_configuration_comparison_allows_only_image_and_source_change():
    before = service()
    after = copy.deepcopy(before)
    api = after['spec']['template']['spec']['containers'][0]
    api['image'] = 'new-api'
    api['env'][0]['value'] = 'b' * 40
    assert deploy.service_spec(after) == deploy.service_spec(before)
    api['resources'] = {'limits': {'memory': '8Gi'}}
    assert deploy.service_spec(after) != deploy.service_spec(before)


def test_build_requires_success_and_both_expected_digests():
    build = {'id': 'build1', 'status': 'SUCCESS', 'results': {'images': [
        {'name': f'{deploy.REGION}-docker.pkg.dev/{deploy.PROJECT}/ocean-platform/{name}:build1',
         'digest': 'sha256:' + 'b' * 64} for name in ('api', 'frontend')]}}
    assert set(deploy.image_digests(build)) == {'api', 'frontend'}
    build['results']['images'][0]['name'] = 'attacker/api:build1'
    with pytest.raises(deploy.DeploymentError):
        deploy.image_digests(build)
    build['status'] = 'FAILURE'
    with pytest.raises(deploy.DeploymentError):
        deploy.image_digests(build)


def test_data_changes_stop_before_build_or_resource_changes(tmp_path, monkeypatch):
    release = deploy.Release(tmp_path)
    monkeypatch.setattr(deploy, 'github', lambda _: {'tag_name': 'v0.4.6', 'published_at': 'today', 'draft': False, 'prerelease': False})
    monkeypatch.setattr(release, 'describe', service)
    calls = []

    def cloud(*args):
        calls.append(args)
        assert args[:3] == ('run', 'revisions', 'describe')
        return {'spec': service()['spec']['template']['spec']}

    monkeypatch.setattr(deploy, 'cloud', cloud)
    monkeypatch.setattr(deploy, 'run', lambda args: 'b' * 40 if args[1] == 'rev-parse' else 'migrations/new.py' if args[1] == 'diff' else '')
    with pytest.raises(deploy.DeploymentError, match='coordinated rollout'):
        release.preflight('v0.4.6')
    assert len(calls) == 1


def test_concurrent_service_edit_blocks_all_deploy_mutations(tmp_path, monkeypatch):
    release = deploy.Release(tmp_path)
    release.state = {'before': service()}
    now = service()
    now['metadata']['resourceVersion'] = '2'
    monkeypatch.setattr(release, 'describe', lambda: now)
    monkeypatch.setattr(deploy, 'cloud', lambda *args: pytest.fail('Unexpected cloud mutation'))
    with pytest.raises(deploy.DeploymentError, match='changed after preflight'):
        release.deploy()


def test_rollback_attempts_all_jobs_even_when_one_fails(tmp_path, monkeypatch):
    release = deploy.Release(tmp_path)
    container = service()['spec']['template']['spec']['containers'][0]
    job = {'spec': {'template': {'spec': {'template': {'spec': {'containers': [container]}}}}}}
    release.state = {'revision': 'new', 'promotion_attempted': True, 'traffic': {'old': 100}, 'job_updates': ['one', 'two'], 'jobs': {'one': job, 'two': job}}
    calls = []
    monkeypatch.setattr(release, 'describe', service)
    monkeypatch.setattr(release, 'traffic', lambda mapping: calls.append(('traffic', mapping)))

    def update(name, image, sha):
        calls.append((name, image, sha))
        if name == 'two':
            raise deploy.DeploymentError('permission failure')

    monkeypatch.setattr(release, 'update_job', update)
    release.rollback()
    assert [c[0] for c in calls] == ['traffic', 'two', 'one']
    assert release.state['rollback_failures'] == ['two']


def test_failed_deployment_cannot_be_recorded_successful(tmp_path, monkeypatch):
    release = deploy.Release(tmp_path)
    monkeypatch.setattr(deploy, 'github', lambda *args: pytest.fail('Unexpected publication'))
    with pytest.raises(deploy.DeploymentError):
        release.record()


def test_production_smoke_failure_restores_traffic_and_all_job_images(tmp_path, monkeypatch):
    release = deploy.Release(tmp_path)
    before = service()
    container = before['spec']['template']['spec']['containers'][0]
    job = {'metadata': {'resourceVersion': '1'}, 'spec': {'template': {'spec': {'template': {'spec': {'containers': [container]}}}}}}
    release.state = {'tag': 'v0.4.5', 'sha': SHA, 'before': before, 'traffic': {'old': 100},
                     'jobs': {name: copy.deepcopy(job) for name in deploy.JOBS}, 'job_updates': [],
                     'images': {'api': 'new-api', 'frontend': 'new-ui'}}
    live = copy.deepcopy(before)
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    monkeypatch.setattr(release, 'describe', lambda: copy.deepcopy(live))
    executed = []
    monkeypatch.setattr(release, 'job', lambda name, args: executed.append((name, args)))
    updates = []
    monkeypatch.setattr(release, 'update_job', lambda *args: updates.append(args))

    def cloud(*args):
        if args[:3] == ('run', 'jobs', 'describe'):
            return copy.deepcopy(job)
        assert args[:3] == ('run', 'services', 'update')
        live['metadata']['resourceVersion'] = '2'
        live['status']['latestReadyRevisionName'] = 'ocean-platform-r123-1'
        live['status']['traffic'].append({'revisionName': 'ocean-platform-r123-1',
                                          'tag': 'release-candidate', 'url': 'https://candidate.example'})
        return live

    def traffic(mapping):
        live['status']['traffic'] = [{'revisionName': rev, 'percent': percent} for rev, percent in mapping.items()]

    def smoke(url):
        if url == 'https://oceaninfobio.com':
            raise deploy.DeploymentError('production smoke failed')
        return [{'status': 200}]

    monkeypatch.setattr(deploy, 'cloud', cloud)
    monkeypatch.setattr(release, 'traffic', traffic)
    monkeypatch.setattr(deploy, 'smoke', smoke)
    with pytest.raises(deploy.DeploymentError, match='production smoke failed'):
        release.deploy()
    assert deploy.traffic_map(live) == {'old': 100}
    assert len(updates) == 2 * len(deploy.JOBS)
    assert all(args[1] == 'old-api' for args in updates[len(deploy.JOBS):])
    assert executed[-1] == ('ocean-migrate', ['scripts/bootstrap_database.py', '--check-only', '--json'])
    assert release.state['rollback_complete'] is True
    assert not release.state.get('deployed')


def test_rollback_does_not_overwrite_another_operators_traffic(tmp_path, monkeypatch):
    release = deploy.Release(tmp_path)
    release.state = {'revision': 'new', 'promotion_attempted': True, 'traffic': {'old': 100}, 'job_updates': []}
    other = service()
    other['status']['traffic'] = [{'revisionName': 'other', 'percent': 100}]
    monkeypatch.setattr(release, 'describe', lambda: other)
    monkeypatch.setattr(release, 'traffic', lambda _: pytest.fail('Must not overwrite external traffic changes'))
    release.rollback()
    assert release.state['rollback_failures'] == ['traffic']


def test_workflow_is_manual_scoped_and_uses_pinned_actions():
    from pathlib import Path
    import re
    import yaml
    workflow = yaml.load(Path('.github/workflows/deploy-release.yml').read_text(), Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'workflow_dispatch'}
    assert workflow['on']['workflow_dispatch']['inputs']['mode']['default'] == 'verify'
    job = workflow['jobs']['deploy']
    assert job['if'] == "github.ref == 'refs/heads/main'"
    assert job['environment']['name'] == 'production'
    for step in job['steps']:
        if 'uses' in step:
            assert re.fullmatch(r'.+@[a-f0-9]{40}', step['uses'])
        assert '${{ inputs.' not in step.get('run', '')
    assert workflow['concurrency']['cancel-in-progress'] == 'false'


def test_federation_is_pinned_to_repository_owner_workflow_and_environment():
    import runpy
    setup = runpy.run_path('deploy/gcp/setup-github-deploy.py')
    condition = setup['CONDITION']
    for restriction in ["assertion.repository_id == '1224179187'", "assertion.repository_owner_id == '82869981'",
                        "assertion.ref == 'refs/heads/main'", "assertion.event_name == 'workflow_dispatch'",
                        "assertion.workflow_ref == 'jarondlk/ocean-platform/.github/workflows/deploy-release.yml@refs/heads/main'",
                        "assertion.sub == 'repo:jarondlk/ocean-platform:environment:production'"]:
        assert restriction in condition
    assert not any('delete' in p or 'setIamPolicy' in p for permissions in setup['ROLES'].values() for p in permissions)
    assert 'run.jobs.runWithOverrides' not in setup['ROLES']['oceanReleaseRuntime']
