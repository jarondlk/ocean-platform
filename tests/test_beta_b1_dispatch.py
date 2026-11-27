"""Canonical task refusal tests use synthetic UUIDs without credentials/network."""
from copy import deepcopy

import pytest

from orchestration.cloud_research_dispatch import CloudResearchQueue
from scripts import beta_b1_dispatch as delivery
from tests.test_beta_b1_rollout import completed, make_material

IDENTITY = "11111111-1111-4111-8111-111111111111"
DELIVERY = "22222222-2222-4222-8222-222222222222"


def task(kind="run"):
    return CloudResearchQueue(settings=delivery.SETTINGS, kind=kind).task(
        delivery_id=DELIVERY, **{"run_id" if kind == "run" else "job_id": IDENTITY})


@pytest.mark.parametrize("kind", ["run", "answer"])
def test_exact_task_is_accepted_without_claiming_an_answer(kind):
    intent = delivery.validate_task(task(kind), kind, IDENTITY)
    assert intent["canonical_target_identity_and_body_verified"]
    assert not intent["automatic_retry_permitted"] and not intent["successful_answer_claimed"]


@pytest.mark.parametrize("field", ["name", "origin", "audience", "invoker", "method", "deadline", "body", "header", "dispatched", "responses", "kind", "identity"])
def test_altered_or_previously_dispatched_task_is_rejected(field):
    value = deepcopy(task())
    kind, identity = "run", IDENTITY
    request = value["httpRequest"]
    if field == "name":
        value["name"] += "-replacement"
    elif field == "origin":
        request["url"] = "https://another-project.run.app/internal/research/run"
    elif field == "audience":
        request["oidcToken"]["audience"] = "https://another-project.run.app"
    elif field == "invoker":
        request["oidcToken"]["serviceAccountEmail"] = "other@example.com"
    elif field == "method":
        request["httpMethod"] = "GET"
    elif field == "deadline":
        value["dispatchDeadline"] = "3600s"
    elif field == "body":
        request["body"] = "not-base64"
    elif field == "header":
        request["headers"]["Authorization"] = "unexpected"
    elif field == "dispatched":
        value["dispatchCount"] = 1
    elif field == "responses":
        value["responseCount"] = 1
    elif field == "kind":
        kind = "answer"
    else:
        identity = DELIVERY
    with pytest.raises((delivery.guard.Rejected, ValueError)):
        delivery.validate_task(value, kind, identity)


def test_uncertain_dispatch_retains_intent_and_cannot_be_repeated(monkeypatch, tmp_path):
    import json
    serving, controller, contract = make_material()
    controller = completed(controller, delivery.rollout.plan_transition(controller, "controller", contract))
    for phase in ["stage", "promote", "admit-stage", "admit-promote"]:
        serving = completed(serving, delivery.rollout.plan_transition(serving, phase, contract))
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    monkeypatch.setattr(delivery.rollout, "CONTRACT_PATH", path)
    class Cloud:
        writes = 0
        def request(self, url, **kwargs):
            if kwargs.get("method") == "POST":
                self.writes += 1
                raise OSError("Synthetic lost acknowledgement")
            if url.endswith(":getIamPolicy"):
                return {"bindings": [{"role": "roles/run.invoker", "members": [
                    "serviceAccount:" + delivery.SETTINGS.task_invoker_email]}]}
            if "/tasks?" in url:
                return {"tasks": [task()]}
            if url.endswith("/queues/ocean-v1-beta-research"):
                return {"state": "PAUSED"}
            return controller if url.endswith("-controller") else serving
    cloud = Cloud()
    with pytest.raises(OSError):
        delivery.execute(cloud, tmp_path, "run", IDENTITY)
    assert (tmp_path / ("manual-run-" + IDENTITY) / "intent.json").is_file()
    with pytest.raises(delivery.guard.Rejected):
        delivery.execute(cloud, tmp_path, "run", IDENTITY)
    assert cloud.writes == 1


def test_repair_dispatch_cannot_use_an_unqualified_candidate(monkeypatch, tmp_path):
    from scripts import beta_b1_repair_rollout as repair
    calls = []

    def reject(*args):
        raise delivery.guard.Rejected('Hosted repair qualification is required')

    monkeypatch.setattr(repair, 'qualify', reject)
    with pytest.raises(delivery.guard.Rejected):
        delivery.execute(type('Cloud', (), {'request': lambda *args, **kwargs: calls.append(args)})(),
                         tmp_path, 'run', IDENTITY, repair_candidate=True)
    assert not calls and not list(tmp_path.iterdir())


def test_list_dispatch_requires_its_own_qualified_contract_and_rejects_ambiguous_mode(monkeypatch, tmp_path):
    from scripts import beta_b1_repair_rollout as repair
    path = tmp_path / 'list-contract.json'
    path.write_text('{"version":"synthetic-list-contract"}')
    monkeypatch.setattr(repair, 'LIST_CONTRACT', path)
    seen, requests = [], []
    def reject(directory, contract):
        seen.append(contract['version'])
        raise delivery.guard.Rejected('List qualification is required')
    monkeypatch.setattr(repair, 'qualify', reject)
    cloud = type('Cloud', (), {'request': lambda *args, **kwargs: requests.append(args)})()
    with pytest.raises(delivery.guard.Rejected):
        delivery.execute(cloud, tmp_path, 'answer', IDENTITY, list_candidate=True)
    assert seen == ['synthetic-list-contract'] and not requests
    with pytest.raises(delivery.guard.Rejected):
        delivery.execute(cloud, tmp_path, 'answer', IDENTITY, repair_candidate=True, list_candidate=True)
    assert seen == ['synthetic-list-contract'] and not requests


@pytest.mark.parametrize('state', [
    'original', 'controller_drift', 'restored', 'unqualified_generation',
    'restored_image_drift', 'restored_config_drift', 'bad_restoration_receipt',
    'changed_baseline', 'sweep_restored', 'sweep_restored_config_drift',
    'layout_deployed', 'layout_wrong_frontend', 'layout_unrelated_change',
    'plex_deployed', 'plex_wrong_baseline_frontend',
    'readable_deployed', 'readable_wrong_baseline_frontend',
    'wait_deployed', 'wait_wrong_baseline_frontend',
    'support_deployed', 'support_wrong_baseline_frontend',
])
def test_b2_dispatch_checks_both_accepted_live_templates_before_delivery(tmp_path, monkeypatch, state):
    import hashlib
    import json

    image = 'synthetic-image-pin'
    support = state.startswith('support_')
    wait = state.startswith('wait_')
    readable = state.startswith('readable_')
    plex = support or wait or readable or state.startswith('plex_')
    layout = plex or state.startswith('layout_')
    receipt = {'image_proof': {'image': image, 'build_status': 'SUCCESS', 'offline_proof': 'success'},
               'initial_cold_discovery_delivery_passed': True}
    services = {}
    traffic = [{'type': 'TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST', 'percent': 100}]
    for key, slug, container in (('serving', 'ocean-v1-beta-serving', 'api'),
                                 ('research_controller', 'ocean-v1-beta-research-controller', 'controller')):
        name = f'{delivery.rollout.PREFIX}/services/{slug}'
        revision = slug + '-fixture'
        env = [{'name': flag, 'value': 'true'} for flag in delivery.rollout.FLAGS] if key == 'serving' else []
        template = {'revision': revision, 'containers': [{'name': container, 'image': image, 'env': env}]}
        if key == 'serving' and layout:
            template['containers'].append({'name': 'frontend', 'image': 'original-frontend'})
        receipt[key] = {'new_image': image, 'revision': revision, 'generation': 1,
                        'configuration_sha256': delivery.rollout.sha({'template': template, 'traffic': traffic})}
        services[name] = {'name': name, 'generation': '1', 'observedGeneration': '1', 'template': template,
                          'traffic': traffic, 'latestCreatedRevision': revision, 'latestReadyRevision': revision,
                          'terminalCondition': {'state': 'CONDITION_SUCCEEDED'},
                          'trafficStatuses': [{'revision': revision, 'percent': 100}]}
    path = tmp_path / 'accepted-b2.json'
    raw = json.dumps(receipt).encode()
    path.write_bytes(raw)
    baseline_sha = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(delivery, 'B2_RECEIPT', path)
    monkeypatch.setattr(delivery, 'B2_RECEIPT_SHA256', baseline_sha)
    controller = f'{delivery.rollout.PREFIX}/services/ocean-v1-beta-research-controller'
    serving = services[f'{delivery.rollout.PREFIX}/services/ocean-v1-beta-serving']
    if state not in ('original', 'controller_drift'):
        sweep = state.startswith('sweep_')
        revision = 'ocean-v1-beta-serving-restored'
        serving.update(generation='3', observedGeneration='3', latestCreatedRevision=revision,
                       latestReadyRevision=revision, trafficStatuses=[{'revision': revision, 'percent': 100}])
        serving['template']['revision'] = revision
        if state == 'changed_baseline':
            # A new configuration digest cannot qualify unrelated changes as a restoration.
            serving['template']['timeout'] = '240s'
        if layout:
            serving['template']['containers'][1]['image'] = 'qualified-frontend'
            field = 'B2_LAYOUT_RECEIPT'
            version = 'ocean-beta-frontend-layout-live-v1'
            proof = {
                'revision': revision, 'generation': 3, 'image': image,
                'frontend_before': 'original-frontend', 'frontend_after': 'qualified-frontend',
                'only_frontend_image_and_revision_changed': True,
                'baseline_configuration_sha256': receipt['serving']['configuration_sha256'],
                'configuration_sha256': delivery.rollout.sha({'template': serving['template'], 'traffic': traffic}),
            }
            if plex:
                name = 'SUPPORT' if support else 'WAIT' if wait else 'READABLE' if readable else 'PLEX'
                field = f'B2_{name}_RECEIPT'
                version = f'ocean-beta-frontend-{name.lower()}-live-v1'
                monkeypatch.setattr(delivery, f'B2_{name}_GENERATION', '3')
                proof['frontend_before'] = 'qualified-layout-frontend'
                proof['baseline_frontend_image'] = (
                    'original-frontend' if state.endswith('_deployed') else 'wrong-baseline-frontend'
                )
            else:
                monkeypatch.setattr(delivery, 'B2_LAYOUT_GENERATION', '3')
        else:
            field = 'B2_SWEEP_RESTORATION_RECEIPT' if sweep else 'B2_RESTORATION_RECEIPT'
            version = 'ocean-beta-b4-research-sweep-live-v1' if sweep else 'ocean-beta-b4-research-trial-live-v1'
            proof = {
                'restored_revision': revision, 'generation': 3, 'image': image,
                'normalized_previous_configuration_matches': True,
                'baseline_configuration_sha256': receipt['serving']['configuration_sha256'],
                'configuration_sha256': delivery.rollout.sha({'template': serving['template'], 'traffic': traffic}),
            }
        restoration = {
            'version': version, 'project': delivery.rollout.PROJECT, 'region': delivery.rollout.REGION,
            'baseline_receipt_sha256': baseline_sha, 'deployment' if layout else 'restoration': proof,
        }
        restoration_path = tmp_path / 'restoration.json'
        restoration_raw = json.dumps(restoration).encode()
        restoration_path.write_bytes(restoration_raw)
        monkeypatch.setattr(delivery, field, restoration_path)
        monkeypatch.setattr(delivery, field + '_SHA256', hashlib.sha256(restoration_raw).hexdigest())
        if sweep:
            monkeypatch.setattr(delivery, 'B2_SWEEP_RESTORATION_GENERATION', '3')
    if state == 'unqualified_generation':
        serving.update(generation='4', observedGeneration='4')
    elif state == 'restored_image_drift':
        serving['template']['containers'][0]['image'] = 'different-image'
    elif state in ('restored_config_drift', 'sweep_restored_config_drift', 'layout_unrelated_change'):
        serving['template']['timeout'] = '240s'
    elif state == 'layout_wrong_frontend':
        serving['template']['containers'][1]['image'] = 'unqualified-frontend'
    elif state == 'bad_restoration_receipt':
        restoration_path.write_bytes(restoration_raw + b'\n')
    elif state == 'controller_drift':
        services[controller]['template']['containers'][0]['env'].append({'name': 'CONFIG', 'value': 'changed'})
    calls = []

    def dispatch(_cloud, _directory, kind, identity, name):
        calls.append((kind, identity, name))
        return 'delivered'

    monkeypatch.setattr(delivery, 'dispatch', dispatch)
    cloud = type('Cloud', (), {'request': lambda _, url: services[url.split('/v2/', 1)[1]]})()
    if state not in ('original', 'restored', 'sweep_restored', 'layout_deployed', 'plex_deployed', 'readable_deployed', 'wait_deployed',
                     'support_deployed'):
        with pytest.raises(delivery.guard.Rejected):
            delivery.execute(cloud, tmp_path, 'run', IDENTITY, b2_candidate=True)
        assert not calls
    else:
        assert delivery.execute(cloud, tmp_path, 'run', IDENTITY, b2_candidate=True) == 'delivered'
        assert calls == [('run', IDENTITY, controller)]


def page_cloud(pages):
    class Cloud:
        def __init__(self):
            self.urls = []
        def request(self, url, **kwargs):
            self.urls.append(url)
            assert kwargs == {"personal": True}
            return pages[len(self.urls) - 1]
    return Cloud()


def test_one_task_requires_complete_pages_and_encodes_token():
    value = task()
    cloud = page_cloud([{"tasks": [value], "nextPageToken": "next+/="}, {}])
    assert delivery.one_queued_task(cloud, "https://cloudtasks.googleapis.com/v2/fixed") == value
    assert len(cloud.urls) == 2 and "pageToken=next%2B%2F%3D" in cloud.urls[1]


@pytest.mark.parametrize("pages", [
    [{"tasks": [task()], "nextPageToken": "next"}, {"tasks": [task()]}],
    [{"nextPageToken": "same"}, {"nextPageToken": "same"}],
    [{"nextPageToken": str(i)} for i in range(10)],
    [{"nextPageToken": "next"}, {}],
])
def test_incomplete_duplicate_looping_or_empty_task_listing_refused(pages):
    with pytest.raises(delivery.guard.Rejected):
        delivery.one_queued_task(page_cloud(pages), "https://cloudtasks.googleapis.com/v2/fixed")
