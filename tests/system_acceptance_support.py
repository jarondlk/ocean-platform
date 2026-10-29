"""C26 explicit shared synthetic stack; actual services, no live runtime fallback.

Only test/QA callers construct this fixture. Controller actions use retained
C17/C14 services, C20 journals/outbox and C21 immutable evidence/answers. C25's
port is the explicit durable synthetic adapter; it never executes Python.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
from pathlib import Path
import uuid

from sqlalchemy import select

from api.investigation_routes import investigation_response
from db.app_models import AppUser, ResearchAnswerOutbox, ResearchInvestigation, ResearchRun
from model_runtime import GenerationResult
from orchestration.catalogue_browser import CatalogueBrowser
from orchestration.experiment_artifacts import ExperimentArtifactProvider
from orchestration.experiment_workspace import ExperimentWorkspaceService
from orchestration.research_answers import FakeAnswerQueue, ResearchAnswerService
from orchestration.research_controller import ControllerAdmissionError, ResearchController
from orchestration.research_dispatch import FakeResearchQueue
from orchestration.research_evidence import ResearchEvidenceService
from orchestration.research_runs import ResearchRunService, RunJournal
from schema.context_catalogue import canonical_json
from tests.experiment_workspace_support import DurableSyntheticExecutionPort
from tests.research_experiment_support import make_experiment_fixture
from tests.research_run_support import RunClock, RunFixture

ORACLE_DATASET_IDS = (
    'synthetic:ctd:campaign-a', 'synthetic:edna:project-a',
    'synthetic:metagenome:collection-a', 'synthetic:sst:mur-final',
)
ORACLE = {'dataset_count': 4, 'ctd_casts': 4, 'ctd_depth_observations': 8,
    'sst_raw_rows': 8, 'sst_accepted_nonnull_rows': 5,
    'int64_maximum': '9223372036854775807'}
ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    'api/investigation_routes.py', 'db/app_models.py',
    'orchestration/catalogue_service.py', 'orchestration/investigations.py',
    'orchestration/research_controller.py', 'orchestration/research_runs.py',
    'orchestration/research_evidence.py', 'orchestration/research_answers.py',
    'orchestration/research_experiments.py', 'orchestration/experiment_workspace.py',
    'orchestration/retained_artifacts.py', 'orchestration/experiment_artifacts.py',
    'tests/experiment_workspace_support.py', 'tests/research_experiment_support.py',
    'tests/investigation_support.py',
    'tests/system_acceptance_support.py',
)


def source_revision():
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_PATHS}
    return 'sha256:' + hashlib.sha256(canonical_json(files).encode()).hexdigest(), files


class ScriptedActionRuntime:
    """Explicit action fixture, not provider quality/timing or live-model evidence."""
    def __init__(self, actions=()):
        self.actions, self.calls = list(actions), []

    def structured_chat_result(self, **request):
        self.calls.append(request)
        value = self.actions.pop(0) if self.actions else {'kind': 'finish'}
        return GenerationResult(canonical_json(value), 'synthetic', 'c26-scripted-test-only', 'completed', 'stop', 0.0)


def action(name, **arguments):
    return {'kind': 'tool', 'tool': name, 'arguments': arguments}


def check(identity, owners, expected, observed, **evidence):
    return {'id': identity, 'owner_components': owners, 'expected': expected, 'observed': observed,
        'status': 'passed' if expected == observed else 'failed', 'evidence': evidence}


def denied(callback):
    try:
        callback()
    except Exception as error:
        return getattr(error, 'status_code', None)
    return None


def canonical_dataset_inputs(rows):
    """Invert only independently declared C13 dataset witness IDs.

    Unknown dataset witnesses remain visible as opaque IDs so an extra source
    cannot silently disappear from the exact membership comparison.
    """
    expected = {'c13:input:' + hashlib.sha256(identity.encode()).hexdigest(): identity for identity in ORACLE_DATASET_IDS}
    return sorted(expected.get(row['object_id'], row['object_id']) for row in rows
        if row.get('object_id', '').startswith('c13:input:'))


@dataclass
class SystemAcceptanceFixture:
    experiments: object
    runs: RunFixture
    evidence: ResearchEvidenceService
    answers: ResearchAnswerService
    port: DurableSyntheticExecutionPort
    workspace: ExperimentWorkspaceService
    browser: CatalogueBrowser
    state: dict

    @property
    def retained(self):
        return self.experiments.retained

    @property
    def user(self):
        return self.retained.user

    def context(self, *, snapshot_id=None, selected_scope=None):
        initial = self.retained.service.invoke('create', {
            'name': 'C26 integrated synthetic investigation', 'snapshot_id': snapshot_id or self.retained.snapshots[0],
            'scope': selected_scope or self.retained.scope, 'idempotency_key': str(uuid.uuid4())}, self.user)
        conversations = [self.retained.service.invoke('conversations/create', {
            'investigation_id': initial['investigation']['id'], 'name': name,
            'idempotency_key': str(uuid.uuid4())}, self.user)['conversation']
            for name in ('C26 shared research and experiment', 'C26 independent conversation')]
        return {**initial, 'conversations': conversations}

    @staticmethod
    def binding(context, conversation=0):
        return {'investigation_id': context['investigation']['id'],
            'conversation_id': context['conversations'][conversation]['id'],
            'context_revision_id': context['context']['id'], 'snapshot_id': context['context']['snapshot_id'],
            'context_payload_sha256': context['context']['payload_sha256']}

    def run_request(self, context, question='Count all datasets', *, conversation=0):
        binding = self.binding(context, conversation)
        return {'investigation_id': binding['investigation_id'], 'conversation_id': binding['conversation_id'],
            'revision_id': binding['context_revision_id'], 'expected_snapshot_id': binding['snapshot_id'],
            'expected_payload_sha256': binding['context_payload_sha256'], 'question': question,
            'idempotency_key': str(uuid.uuid4())}

    def finish_run(self, context, question='Count all datasets', *, conversation=0):
        request = self.run_request(context, question, conversation=conversation)
        submitted = self.runs.service.invoke('submit', request, self.user)['run']
        finished = self.runs.service.execute_delivery(**self.runs.delivery(submitted))['run']
        return request, finished

    def answer(self, run, locale='en'):
        discovery = self.answers.invoke('list', self.runs.address(run), self.user)
        request = {**self.runs.address(run), 'input_version': discovery['input_version'], 'locale': locale,
            'idempotency_key': str(uuid.uuid4())}
        queued = self.answers.invoke('submit', request, self.user)['job']
        with self.retained.factory() as session:
            outbox = session.scalar(select(ResearchAnswerOutbox).where(
                ResearchAnswerOutbox.job_id == uuid.UUID(queued['id'])))
            delivery = {'job_id': queued['id'], 'delivery_id': str(outbox.delivery_id)}
        return self.answers.execute_delivery(**delivery)['job']

    def experiment(self, context, *, completed=False):
        binding = self.binding(context)
        proposal = {'question': 'Inspect the same frozen synthetic CTD cohort',
            'cohort': {'selections': [{'kind': 'dataset', 'target_id': ORACLE_DATASET_IDS[0],
                'table': 'casts', 'columns': ['cast_id']}]},
            'method': 'Retained synthetic identity review only',
            'assumptions': ['Synthetic source; no independent scientific approval'],
            'python_code': '# Retained review only; this fixture never executes Python.\nprint("C26")\n',
            'expected_outputs': [{'name': 'summary.json', 'kind': 'table', 'description': 'Synthetic result display'}],
            'environment_id': self.experiments.environment.identity_sha256,
            'limitations': ['No live execution or scientific publication'], 'seeds': {'numpy': 7}}
        created = self.experiments.service.invoke('create', {**binding, 'proposal': proposal,
            'idempotency_key': str(uuid.uuid4())}, self.user)['experiment']
        approved = self.experiments.service.invoke('approve', self.experiments.decision(created), self.user)['experiment']
        request = self.experiments.decision(approved)
        request.pop('idempotency_key')
        access = self.workspace._access(request, self.user)
        raw = b'{"columns":["cast_count","int64"],"rows":[[4,9223372036854775807]]}'
        execution = self.port.seed(access, state='completed' if completed else 'running',
            files=[('summary.json', 'application/json', raw)] if completed else None)
        return approved, request, execution, raw


def make_system_acceptance_fixture(engine, directory):
    experiments = make_experiment_fixture(engine, directory)
    retained = experiments.retained
    clock, queue = RunClock(), FakeResearchQueue()
    state = {'runtime': None, 'factory_calls': 0}
    def controller_factory(identity_provider):
        state['factory_calls'] += 1
        return ResearchController(investigations=retained.service, catalogue=retained.service.catalogue,
            identity_provider=identity_provider, runtime=state['runtime'],
            model='c26-scripted-test-only' if state['runtime'] is not None else None,
            runtime_identity={'fixture': 'C26-explicit-synthetic-local'})
    service = ResearchRunService(session_factory=retained.factory, site_id=retained.service.site_id,
        investigations=retained.service, controller_factory=controller_factory, queue=queue,
        enabled=lambda: True, dispatch_enabled=lambda: True, db_clock=clock, lease_seconds=5)
    runs = RunFixture(retained, service, queue, clock, state)
    port = DurableSyntheticExecutionPort(experiments=experiments.service, path=directory / 'c26-synthetic-executions.sqlite')
    workspace = ExperimentWorkspaceService(experiments=experiments.service, port=port, enabled=lambda: True)
    provider = ExperimentArtifactProvider(workspace=workspace)
    evidence = ResearchEvidenceService(session_factory=retained.factory, site_id=retained.service.site_id,
        investigations=retained.service, runs=service, enabled=lambda: True,
        external_artifact_providers=(provider,))
    answers = ResearchAnswerService(evidence=evidence, queue=FakeAnswerQueue(), enabled=lambda: True,
        synthesis_enabled=lambda: True, lease_seconds=5)
    # Use the explicitly authorized owning-component composition; no test-only
    # resolver/protection mux or fallback replaces the production contract.
    retained.service.artifact_resolver = evidence.attachment_resolver()
    retained.service.evidence_protection = evidence
    browser = CatalogueBrowser(service=retained.service.catalogue,
        snapshots=[{'snapshot_id': sid, 'label': {'en': f'C26 synthetic snapshot {i + 1}',
            'ja': f'C26合成スナップショット{i + 1}'}} for i, sid in enumerate(retained.snapshots)],
        permitted=lambda actor, descriptor: descriptor.snapshot_id in retained.snapshots,
        revision=lambda actor: 'c26:' + hashlib.sha256(canonical_json({k: sorted(v) for k, v in retained.policy.items()}).encode()).hexdigest(),
        cursor_key=b'c26-explicit-synthetic-cursor-key-0000')
    return SystemAcceptanceFixture(experiments, runs, evidence, answers, port, workspace, browser, state)


def seed_integrated_browser(fixture):
    """Real services on one context; explicit synthetic execution observation."""
    context = fixture.context()
    _, run = fixture.finish_run(context)
    verified = fixture.evidence.ensure_retained(run['id'], 1, fixture.user)
    answer = fixture.answer(run)
    experiment, request, execution, _ = fixture.experiment(context, completed=True)
    return {'binding': fixture.binding(context), 'context': context, 'run': run,
        'answer_job': answer, 'receipts': [r.model_dump(mode='json') for r in verified.receipts],
        'agent_input_manifest': list(verified.input_manifests_by_receipt[verified.receipts[0].id]),
        'experiment': experiment, 'execution_request': request, 'execution': execution}


def run_integrated_acceptance(fixture):
    """Return raw expected/observed evidence; a failed integration stays failed."""
    seed = seed_integrated_browser(fixture)
    run, request, execution = seed['run'], seed['execution_request'], seed['execution']
    catalogue = fixture.retained.service.catalogue
    listed = catalogue.list({'snapshot_id': request['snapshot_id'], 'scope': fixture.retained.scope,
        'filters': {'kinds': ['dataset']}, 'limit': 500}, fixture.user)
    observed_ids = sorted(item['id'] for item in listed['items'])
    receipt = seed['receipts'][0]
    value = fixture.evidence.invoke('open', {'receipt_id': receipt['id'], 'expected_sha256': receipt['sha256']}, fixture.user)['receipt']
    count = next(c['value'] for c in value['counts'] if c['entity'] == 'datasets')
    item = execution['artifacts'][0]
    artifact = fixture.workspace.invoke('artifact', {**request, 'execution_id': execution['id'],
        'artifact_id': item['id'], 'expected_sha256': item['sha256']}, fixture.user)
    checks = [
        {'id': 'shared-context-inventory-answer', 'owner_components': ['C14', 'C17', 'C19', 'C20', 'C21'],
            'expected': {'inventory_ids': list(ORACLE_DATASET_IDS), 'agent_inventory_ids': list(ORACLE_DATASET_IDS), 'datasets': 4, 'model_used': False,
                'snapshot_id': request['snapshot_id']},
            'observed': {'inventory_ids': observed_ids, 'agent_inventory_ids': canonical_dataset_inputs(seed['agent_input_manifest']), 'datasets': count,
                'model_used': seed['answer_job']['answer']['model_used'], 'snapshot_id': receipt['binding']['snapshot_id']},
            'evidence': {'run_id': run['id'], 'answer_id': seed['answer_job']['answer']['id'], 'receipt_id': receipt['id'], 'sha256': receipt['sha256']}},
        {'id': 'experimental-bytes-and-approval', 'owner_components': ['C22', 'C25'],
            'expected': {'approval_status': 'current', 'execution_performed': False, 'termination_verified': False,
                'sha256': item['sha256'], 'display_int64': ORACLE['int64_maximum'], 'scientific_approval': 'not_independently_verified'},
            'observed': {'approval_status': seed['experiment']['approval']['status'],
                'execution_performed': artifact['execution']['execution_performed'],
                'termination_verified': artifact['execution']['termination_verified'],
                'sha256': hashlib.sha256(base64.b64decode(artifact['content_base64'])).hexdigest(),
                'display_int64': artifact['preview']['rows'][0][1], 'scientific_approval': artifact['artifact']['scientific_approval']},
            'evidence': {'experiment_id': seed['experiment']['id'], 'artifact_id': item['id'], 'sha256': item['sha256']}},
    ]
    expected = {'attachment': item['attachment_reference'], 'available': True,
        'subsequent_count': 4, 'subsequent_answer_scientific_verification': 'not_independently_verified'}
    attachment_request = {'investigation_id': request['investigation_id'], 'expected_revision_id': request['context_revision_id'],
        'idempotency_key': str(uuid.uuid4()), 'change': {'op': 'attach', 'reference': item['attachment_reference']}}
    response = investigation_response(fixture.user, fixture.retained.service, 'context/change', attachment_request)
    body = json.loads(response.body)
    if response.status_code == 200 and body.get('context') and body['context'].get('attachments'):
        attached_context = {**seed['context'], 'context': body['context']}
        _, following = fixture.finish_run(attached_context)
        verified = fixture.evidence.ensure_retained(following['id'], 1, fixture.user)
        following_count = next(x.value for receipt in verified.receipts for x in receipt.counts if x.entity == 'datasets')
        observed = {'attachment': body['context']['attachments'][0],
            'available': body['context']['resolution'][0]['status'] == 'available',
            'subsequent_count': following_count,
            'subsequent_answer_scientific_verification': fixture.answer(following)['answer']['scientific_verification']}
    else:
        observed = {'http_status': response.status_code, 'response': body, 'available': False}
    checks.append({'id': 'research-and-experiment-attachment-composition', 'owner_components': ['C17', 'C21', 'C25'],
        'expected': expected, 'observed': observed, 'evidence': {'artifact_id': item['id'],
            'resolver_validates': fixture.port.resolve_artifact(fixture.user, item['attachment_reference']) is not None,
            'protection': type(fixture.retained.service.evidence_protection).__name__,
            'public_path': '/research/investigations/context/change', 'public_request': attachment_request,
            'http_status': response.status_code, 'public_response': body,
            'source': {'path': 'orchestration/research_evidence.py', 'method': 'ResearchEvidenceService.prepare_context'},
            'provider': 'ExperimentArtifactProvider',
            'original_failed_evidence': '/private/tmp/ocean-c26-shared-first-20261029.json'}})
    for check in checks:
        check['status'] = 'passed' if check['expected'] == check['observed'] else 'failed'
    checks.extend(observe_lifecycle(fixture, seed))
    checks.extend(observe_interrupted_journal(fixture))
    checks.extend(observe_context_and_history(fixture, seed))
    checks.extend(observe_scientific_boundaries(fixture))
    checks.extend(observe_four_source_semantics(fixture))
    checks.extend(observe_incompatible_questions(fixture))
    checks.extend(observe_access_and_retention(fixture, seed))
    revision, sources = source_revision()
    return {'version': 'c26-integrated-observations-v1',
        'fixture': {'classification': 'synthetic-local-actual-services', 'site_id': fixture.retained.service.site_id,
            'snapshot_ids': list(fixture.retained.snapshots), 'input_manifest_sha256': hashlib.sha256(canonical_json(ORACLE).encode()).hexdigest(),
            'live_calls_performed': False, 'source_revision': revision, 'source_files': sources},
        'checks': checks, 'browser_seed': seed,
        'comparison_observations': [controller_observation(fixture, seed, count, canonical_dataset_inputs(seed['agent_input_manifest']))]}


def observe_lifecycle(fixture, seed):
    """Same frozen scope survives lost queue ACK, cancel, continue and rollover."""
    service, actor = fixture.runs.service, fixture.user
    # Drain only the explicitly supplied fake queue's older outbox messages so
    # the next accept-then-fail fault deterministically concerns this new run.
    service.dispatch_outbox()
    fixture.runs.queue.deliveries.clear()
    context = fixture.context()
    request = fixture.run_request(context, conversation=1)
    queued = service.invoke('submit', request, actor)['run']
    fixture.runs.queue.accept_then_fail = True
    lost = False
    try:
        service.dispatch_outbox()
    except RuntimeError:
        lost = True
    finally:
        fixture.runs.queue.accept_then_fail = False
    service.dispatch_outbox()
    deliveries = [x for x in fixture.runs.queue.deliveries if x['run_id'] == queued['id']]
    cancellation = {**fixture.runs.address(queued), 'idempotency_key': str(uuid.uuid4())}
    cancelled = service.invoke('cancel', cancellation, actor)['run']
    replay = service.invoke('cancel', cancellation, actor)['run']
    child = service.invoke('continue', {**fixture.runs.address(cancelled), 'idempotency_key': str(uuid.uuid4())}, actor)['run']
    completed = service.execute_delivery(**fixture.runs.delivery(child))['run']
    reopened = fixture.evidence.ensure_retained(completed['id'], 1, actor)
    receipt = reopened.receipts[0]
    page = fixture.evidence.invoke('page', {'receipt_id': receipt.id, 'expected_sha256': receipt.sha256, 'section': 'inputs', 'limit': 2}, actor)
    rows = list(page['rows'])
    while page['next_offset'] is not None:
        page = fixture.evidence.invoke('page', {'receipt_id': receipt.id, 'expected_sha256': receipt.sha256,
            'section': 'inputs', 'limit': 2, 'offset': page['next_offset']}, actor)
        rows.extend(page['rows'])
    agent_ids = canonical_dataset_inputs(rows)
    refresh = fixture.retained.service.invoke('refresh', {'investigation_id': context['investigation']['id'],
        'expected_revision_id': context['context']['id'], 'target_snapshot_id': fixture.retained.snapshots[1],
        'name': 'C26 explicit rollover branch', 'idempotency_key': str(uuid.uuid4())}, actor)
    after = service.invoke('status', fixture.runs.address(completed), actor)['run']
    opened = fixture.evidence.invoke('open', {'receipt_id': receipt.id, 'expected_sha256': receipt.sha256}, actor)['receipt']
    return [check('durable-ack-cancel-continuation-rollover', ['C17', 'C20', 'C21'],
        {'lost_ack': True, 'delivery_count': 2, 'one_delivery_identity': True, 'cancel_replay': True,
         'cancelled': 'cancelled', 'continued': 'completed', 'same_frozen_context': True,
         'new_snapshot_branch': True, 'old_snapshot_preserved': True, 'receipt_unchanged': True,
         'agent_inventory_ids': list(ORACLE_DATASET_IDS)},
        {'lost_ack': lost, 'delivery_count': len(deliveries),
         'one_delivery_identity': len({x['delivery_id'] for x in deliveries}) == 1,
         'cancel_replay': replay == cancelled, 'cancelled': cancelled['status'], 'continued': completed['status'],
         'same_frozen_context': child['context'] == queued['context'],
         'new_snapshot_branch': refresh['investigation']['id'] != context['investigation']['id'] and refresh['context']['snapshot_id'] == fixture.retained.snapshots[1],
         'old_snapshot_preserved': after['context']['binding']['snapshot_id'] == fixture.retained.snapshots[0],
         'receipt_unchanged': opened == receipt.model_dump(mode='json'), 'agent_inventory_ids': agent_ids},
        run_id=queued['id'], continued_run_id=completed['id'], receipt_id=receipt.id,
        snapshot_before=fixture.retained.snapshots[0], snapshot_after=refresh['context']['snapshot_id'])]


def observe_context_and_history(fixture, seed):
    actor = fixture.user
    context = fixture.context()
    ref = {'kind': 'catalogue', 'id': ORACLE_DATASET_IDS[0], 'snapshot_id': context['context']['snapshot_id']}
    original_context = context['context']['id']
    counts = []
    for operation, conversation in [('attach', 0), ('pin', 1)]:
        changed = fixture.retained.service.invoke('context/change', {'investigation_id': context['investigation']['id'],
            'expected_revision_id': context['context']['id'], 'idempotency_key': str(uuid.uuid4()),
            'change': {'op': operation, 'reference': ref}}, actor)
        context['context'] = changed['context']
        _, run = fixture.finish_run(context, conversation=conversation)
        verified = fixture.evidence.ensure_retained(run['id'], 1, actor)
        counts.append(next(x.value for receipt in verified.receipts for x in receipt.counts if x.entity == 'datasets'))
    approved = seed['experiment']
    revision = {**approved['binding'], 'experiment_id': approved['id'], 'expected_version': approved['version'],
        'expected_proposal_revision_id': approved['proposal_revision_id'],
        'proposal': {**approved['proposal'], 'method': 'C26 new proposal revision requires new approval'}, 'idempotency_key': str(uuid.uuid4())}
    latest_context = fixture.retained.service.invoke('context/get', {'investigation_id': approved['binding']['investigation_id']}, actor)['context']
    revision.update(context_revision_id=latest_context['id'], context_payload_sha256=latest_context['payload_sha256'],
        snapshot_id=latest_context['snapshot_id'])
    current = fixture.experiments.service.invoke('revise', revision, actor)['experiment']
    historical = fixture.experiments.service.invoke('get', {'experiment_id': approved['id'],
        'proposal_revision_id': approved['proposal_revision_id']}, actor)['experiment']
    request = fixture.experiments.decision(historical)
    request.pop('idempotency_key')
    execution = fixture.workspace.invoke('status', request, actor)['execution']
    item = execution['artifacts'][0]
    output = fixture.workspace.invoke('artifact', {**request, 'execution_id': execution['id'],
        'artifact_id': item['id'], 'expected_sha256': item['sha256']}, actor)
    return [check('explicit-attach-pin-multichat-and-experiment-history', ['C17', 'C19', 'C20', 'C21', 'C22', 'C25'],
        {'supplementary_count': 4, 'pinned_count': 1, 'new_context_revisions': True,
         'proposal_hashes_preserved': True, 'historical_execution_preserved': True,
         'fresh_head_version': True, 'experimental_label': 'experimental', 'int64': ORACLE['int64_maximum']},
        {'supplementary_count': counts[0], 'pinned_count': counts[1], 'new_context_revisions': context['context']['id'] != original_context,
         'proposal_hashes_preserved': historical['hashes'] == approved['hashes'],
         'historical_execution_preserved': execution == seed['execution'], 'fresh_head_version': historical['version'] == current['version'] == approved['version'] + 1,
         'experimental_label': output['artifact']['authority'], 'int64': output['preview']['rows'][0][1]},
        context_revision=context['context']['id'], conversations=[x['id'] for x in context['conversations']],
        experiment_id=approved['id'], original_proposal_revision=approved['proposal_revision_id'], new_proposal_revision=current['proposal_revision_id'])]


def observe_interrupted_journal(fixture):
    """Lose a commit acknowledgement, then replay actual retained tool bytes."""
    context = fixture.context()
    queued = fixture.runs.service.invoke('submit', fixture.run_request(context), fixture.user)['run']
    delivery = fixture.runs.delivery(queued)
    original_commit = RunJournal.commit_step
    original_execute = fixture.retained.service.catalogue.execute
    committed, calls = [], []
    def interrupted(journal, *args, **kwargs):
        value = original_commit(journal, *args, **kwargs)
        if not committed:
            committed.append(True)
            raise RuntimeError('C26 synthetic lost durable-step acknowledgement')
        return value
    def observed(name, *args, **kwargs):
        if name == 'catalogue.query':
            calls.append(name)
        return original_execute(name, *args, **kwargs)
    RunJournal.commit_step = interrupted
    fixture.retained.service.catalogue.execute = observed
    caught = False
    try:
        try:
            fixture.runs.service.execute_delivery(**delivery)
        except ControllerAdmissionError:
            caught = True
        finally:
            RunJournal.commit_step = original_commit
        fixture.runs.clock.advance(6)
        final = fixture.runs.service.execute_delivery(**delivery)['run']
        evidence = fixture.evidence.ensure_retained(final['id'], 1, fixture.user)
        receipt = evidence.receipts[0]
        reopened = fixture.evidence.invoke('open', {'receipt_id': receipt.id, 'expected_sha256': receipt.sha256}, fixture.user)['receipt']
    finally:
        RunJournal.commit_step = original_commit
        fixture.retained.service.catalogue.execute = original_execute
    return [check('interrupted-committed-step-replays-without-duplicate-effect', ['C19', 'C20', 'C21'],
        {'interrupted': True, 'physical_tool_calls': 1, 'charged_actions': 1, 'status': 'completed',
         'datasets': 4, 'receipt_reopens': True},
        {'interrupted': caught, 'physical_tool_calls': len(calls), 'charged_actions': evidence.anchor.run_budget_high_water.tool_actions,
         'status': final['status'], 'datasets': receipt.counts[0].value,
         'receipt_reopens': reopened == receipt.model_dump(mode='json')},
        run_id=final['id'], delivery_id=delivery['delivery_id'], receipt_id=receipt.id)]


def observe_scientific_boundaries(fixture):
    context = fixture.context()
    identity = 'synthetic:sst:mur-final'
    fixture.state['runtime'] = ScriptedActionRuntime([action('catalogue.query', operation_id='c13.operation',
        operation_version='c13-v1', input_ids=[identity], parameters={'operation_id': 'c11.summary', 'operation_version': 'c11-v1'})])
    _, run = fixture.finish_run(context, f'Run operation "c11.summary" version "c11-v1" on dataset "{identity}"')
    verified = fixture.evidence.ensure_retained(run['id'], 1, fixture.user)
    scientific = next(x for x in verified.receipts if x.operation_id == 'c13.operation')
    row = fixture.evidence.invoke('page', {'receipt_id': scientific.id, 'expected_sha256': scientific.sha256}, fixture.user)['rows'][0]
    answer = fixture.answer(run)
    numerical = check('sst-independent-numerical-oracle', ['C11', 'C13', 'C19', 'C20', 'C21'],
        {'n_observed': 5, 'n_zero': 1, 'n_missing': 1, 'minimum': 0, 'maximum': 7, 'mean': 4.4,
         'authority': 'descriptive', 'unconfigured_model_answer_available': False},
        {**{k: row[k] for k in ('n_observed', 'n_zero', 'n_missing', 'minimum', 'maximum', 'mean')},
         'authority': scientific.authority, 'unconfigured_model_answer_available': answer['answer'] is not None},
        run_id=run['id'], receipt_id=scientific.id, content_sha256=scientific.result_content_sha256,
        independent_oracle='Eight declared fixture rows: exclude invalid100 and excluded999; retain missing separately; accepted nonnull0,4,5,6,7 => sum22/n5=4.4')
    fixture.state['runtime'] = ScriptedActionRuntime([action('catalogue.coverage', object_id='synthetic:edna:project-a')])
    _, unknown = fixture.finish_run(fixture.context(), 'Show coverage for dataset "synthetic:edna:project-a"')
    unknown_verified = fixture.evidence.ensure_retained(unknown['id'], 1, fixture.user)
    last = unknown_verified.anchor.controller_result.observations[-1]
    empty_question = ('Count datasets where ctd.station="C26-absent-station" and metagenome.enabled=false '
        'and remote_sensing.enabled=false and edna_metabarcoding.enabled=false')
    fixture.state['runtime'] = None
    _, empty = fixture.finish_run(fixture.context(), empty_question)
    empty_verified = fixture.evidence.ensure_retained(empty['id'], 1, fixture.user)
    empty_count = empty_verified.receipts[0].counts[0].value
    fixture.state['runtime'] = ScriptedActionRuntime([action('catalogue.open', object_id=identity, snapshot_id='0' * 64)] * 2)
    _, forged = fixture.finish_run(fixture.context(), f'Find object "{identity}"')
    forged_verified = fixture.evidence.ensure_retained(forged['id'], 1, fixture.user)
    fixture.state['runtime'] = None
    return [numerical, check('known-zero-unknown-and-forged-snapshot', ['C12', 'C19', 'C20', 'C21'],
        {'unknown_status': 'partial', 'coverage_known': False, 'unknown_complete': False,
         'known_empty_status': 'completed', 'known_empty_count': 0,
         'forged_status': 'partial', 'forged_tool_actions': 1, 'forged_complete': False},
        {'unknown_status': unknown['status'], 'coverage_known': 'coverage_known' in last.known_fields,
         'unknown_complete': unknown_verified.anchor.controller_result.completion.complete,
         'known_empty_status': empty['status'], 'known_empty_count': empty_count,
         'forged_status': forged['status'], 'forged_tool_actions': forged_verified.anchor.run_budget_high_water.tool_actions,
         'forged_complete': forged_verified.anchor.controller_result.completion.complete},
        unknown_run_id=unknown['id'], empty_run_id=empty['id'], forged_run_id=forged['id'])]


def observe_access_and_retention(fixture, seed):
    actor, retained = fixture.user, fixture.retained
    run_address = fixture.runs.address(seed['run'])
    receipt = seed['receipts'][0]
    evidence_address = {'receipt_id': receipt['id'], 'expected_sha256': receipt['sha256']}
    with retained.factory() as session:
        before = {c.name: getattr(session.get(ResearchRun, uuid.UUID(seed['run']['id'])), c.name) for c in ResearchRun.__table__.columns}
    cross_owner = [denied(lambda other=other: fixture.evidence.invoke('open', evidence_address, other)) for other in (retained.other, retained.admin)]
    with retained.factory.begin() as session:
        session.get(AppUser, actor.id).role = 'viewer'
    try:
        revoked = [denied(lambda: fixture.runs.service.invoke('status', run_address, actor)),
            denied(lambda: fixture.evidence.invoke('open', evidence_address, actor)),
            denied(lambda: fixture.workspace.invoke('status', seed['execution_request'], actor))]
    finally:
        with retained.factory.begin() as session:
            session.get(AppUser, actor.id).role = actor.role
    retained.policy[seed['binding']['snapshot_id']].add('c26-publication-epoch-withdrawal')
    try:
        withdrawn = denied(lambda: fixture.evidence.invoke('open', evidence_address, actor))
    finally:
        retained.policy[seed['binding']['snapshot_id']].clear()
    hold_context = fixture.context()
    retained.service.set_hold(investigation_id=hold_context['investigation']['id'], held=True, user=retained.admin)
    current = retained.service.invoke('get', {'investigation_id': hold_context['investigation']['id']}, actor)
    retained.service.invoke('archive', {'investigation_id': hold_context['investigation']['id'],
        'expected_version': current['investigation']['metadata_version'], 'idempotency_key': str(uuid.uuid4())}, actor)
    retirement = retained.service.retire_expired(retention_days=30, user=retained.admin,
        now=datetime.now(timezone.utc) + timedelta(days=100), dry_run=False)
    reopened = fixture.evidence.invoke('open', evidence_address, actor)['receipt']
    with retained.factory() as session:
        after = {c.name: getattr(session.get(ResearchRun, uuid.UUID(seed['run']['id'])), c.name) for c in ResearchRun.__table__.columns}
        investigation = session.get(ResearchInvestigation, uuid.UUID(hold_context['investigation']['id']))
        held = investigation.legal_hold and investigation.status == 'archived'
    return [check('owner-role-source-revocation-and-held-history', ['C03', 'C17', 'C20', 'C21', 'C25'],
        {'cross_owner_denials': [404, 404], 'role_revoked_denials': [403, 403, 403],
         'withdrawn_evidence_denial': 403, 'held_archived': True, 'retired': 0,
         'receipt_unchanged': True, 'terminal_run_unchanged': True},
        {'cross_owner_denials': cross_owner, 'role_revoked_denials': revoked, 'withdrawn_evidence_denial': withdrawn,
         'held_archived': held, 'retired': retirement['retired_count'], 'receipt_unchanged': reopened == receipt,
         'terminal_run_unchanged': before == after}, run_id=seed['run']['id'], receipt_id=receipt['id'])]


def observe_four_source_semantics(fixture):
    """Actual C14→C13→C10/C12 paths; independent small-population arithmetic."""
    def query(identity, operation, version, **parameters):
        return fixture.retained.service.catalogue.query({'snapshot_id': fixture.retained.snapshots[0],
            'scope': fixture.retained.scope, 'operation_id': 'c13.operation', 'operation_version': 'c13-v1',
            'input_ids': [identity], 'parameters': {'operation_id': operation, 'operation_version': version,
                'parameters': parameters}}, fixture.user)
    ctd = query('synthetic:ctd:campaign-a', 'c10.summary', 'c10-v1', table='depth_observations', column='temperature')
    casts = query('synthetic:ctd:campaign-a', 'c10.count', 'c10-v1', table='casts')
    kraken = query('synthetic:metagenome:collection-a', 'c10.summary', 'c10-v1',
        table='kraken_abundance', column='abundance', taxon='BeyondTopTen')
    metaeuk = query('synthetic:metagenome:collection-a', 'c10.summary', 'c10-v1',
        table='metaeuk_abundance', column='abundance', taxon='BeyondTopTen')
    details = fixture.retained.service.catalogue.open({'snapshot_id': fixture.retained.snapshots[0],
        'scope': fixture.retained.scope, 'object_id': 'synthetic:metagenome:collection-a',
        'include_details': True}, fixture.user)['details']
    tables = {table['name']: table for table in details['tables']}
    edna = query('synthetic:edna:project-a', 'c12.count', 'c12-v1', population='raw')
    data, methods = edna['rows'][0], edna['rows'][0]['methods']
    return [check('four-source-physical-method-assay-semantics', ['C10', 'C12', 'C13', 'C14'],
        {'casts': 4, 'depth_n': 8, 'negative_temperature': -1.5, 'temperature_mean': 1.8125,
         'temperature_unit': 'degC', 'kraken': 0.05, 'metaeuk': 0.15, 'method_denominators_differ': True,
         'raw_occurrences': 11, 'assays': 10, 'physical_samples': None, 'controls': 1, 'unknown_controls': 1,
         'assignment_rows': 35, 'unique_method_protocol_groups': True, 'authority': 'descriptive'},
        {'casts': casts['rows'][0]['count'], 'depth_n': ctd['rows'][0]['n_observed'],
         'negative_temperature': ctd['rows'][0]['minimum'], 'temperature_mean': ctd['rows'][0]['mean'],
         'temperature_unit': next(c['unit'] for c in ctd['columns'] if c['key'] == 'mean'),
         'kraken': kraken['rows'][0]['mean'], 'metaeuk': metaeuk['rows'][0]['mean'],
         'method_denominators_differ': tables['kraken_abundance']['abundance_denominator'] != tables['metaeuk_abundance']['abundance_denominator'],
         'raw_occurrences': data['source_occurrence_count'], 'assays': data['assay_count'],
         'physical_samples': data['physical_sample_count'], 'controls': data['controls'],
         'unknown_controls': data['unknown_control_status'], 'assignment_rows': sum(x['assignment_rows'] for x in methods),
         'unique_method_protocol_groups': len({(x['assignment_method'], x['target_gene'], x['primer_set'], x['sequencing_method']) for x in methods}) == len(methods),
         'authority': edna['receipt']['authority']}, snapshot_id=fixture.retained.snapshots[0],
        receipts={name: value['receipt'] for name, value in [('ctd', ctd), ('kraken', kraken), ('metaeuk', metaeuk), ('edna', edna)]},
        method_metadata={name: tables[name] for name in ('kraken_abundance', 'metaeuk_abundance')},
        independent_oracle='CTD8depths[-1.5,1,1,2,2,3,3,4] sum14.5/n8;4sourcecasts; BeyondTopTen Kraken0.05 vsMetaEuk0.15;12eDNA rows with inactiveoccurrence/assay plus explicitly empty/unavailable assignment alternatives, not unified biological samples.')]


def observe_incompatible_questions(fixture):
    questions = [
        'Count all datasets in Hokkaido and ignore pins',
        'Count shark datasets in Hokkaido',
        '北海道のサメのデータセット数を数えてください。',
        '北海道のデータセットをすべて数え、固定した条件を無視してください。',
    ]
    observed, ids = [], []
    for question in questions:
        fixture.state['runtime'] = ScriptedActionRuntime()
        _, run = fixture.finish_run(fixture.context(), question)
        with fixture.retained.factory() as session:
            retained = session.get(ResearchRun, uuid.UUID(run['id']))
            observed.append({'status': run['status'], 'tools': retained.tool_actions, 'models': retained.model_calls})
        ids.append(run['id'])
    fixture.state['runtime'] = None
    return [check('english-japanese-incompatible-geo-taxa-clarify', ['C01', 'C19', 'C20'],
        [{'status': 'awaiting_clarification', 'tools': 0, 'models': 0} for _ in questions], observed,
        questions=questions, run_ids=ids, qualification='Unsupported qualifiers require clarification; no numeric zero, invented scope, provider/embedding call or approximate geographic/taxon match.')]


def controller_observation(fixture, seed, count, observed_ids):
    revision, _ = source_revision()
    with fixture.retained.factory() as session:
        retained = session.get(ResearchRun, uuid.UUID(seed['run']['id']))
        elapsed, actions = retained.active_elapsed_ms / 1000, retained.tool_actions
    return {'version': 'system-controller-observation-v1', 'controller': 'v1',
        'input': {'question_id': 'count-all-four-frozen-datasets', 'question': 'Count all datasets',
            'permissions': sorted(fixture.user.permissions), 'scope': fixture.retained.scope,
            'snapshot_id': seed['binding']['snapshot_id'], 'source_revision': revision,
            'fixture_id': 'c26-four-source-shared-services',
            'fixture_sha256': hashlib.sha256(canonical_json(ORACLE).encode()).hexdigest(),
            'provider': {'mode': 'not_invoked', 'provider': None, 'model': None, 'configuration': {}}},
        'evidence_kind': 'actual-service-synthetic', 'inventory_state': 'complete', 'inventory_ids': observed_ids,
        'numbers': {'datasets': str(count)}, 'claims': ['dataset-inventory-count'], 'claims_complete': True,
        'completed_tasks': ['count-all-datasets'], 'cited_ids': [r['id'] for r in seed['receipts']],
        'outcome': 'completed' if seed['answer_job']['status'] == 'completed' else 'failed',
        'telemetry': {'timing': {'basis': 'fixture', 'value': elapsed}, 'tool_calls': {'basis': 'measured', 'value': actions},
            **{k: {'basis': 'unknown', 'value': None} for k in ('input_tokens', 'output_tokens', 'cost')}},
        'evidence': [{'id': r['id'], 'sha256': r['sha256'], 'source_revision': revision, 'kind': 'actual-service-synthetic'} for r in seed['receipts']]}
