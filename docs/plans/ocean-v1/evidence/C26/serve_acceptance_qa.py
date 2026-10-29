"""Owned loopback C26 actual-service harness; synthetic TEST identities only.

The separately launched development frontend proxies this API. This process
never loads an environment file, production database, legacy store or provider.
Local explicit queue adapters perform catalogue research and template answers;
the synthetic retained execution port never starts Python.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

if os.environ.get('DEPLOYMENT_ENV') != 'test' or os.environ.get('AUTH_MODE') != 'disabled':
    raise RuntimeError('Explicit isolated test settings required')
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
# ruff: noqa: E402
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, event, select
from starlette.concurrency import run_in_threadpool
import uvicorn
from api import auth
from api.catalogue_routes import router as catalogue_router
from api.catalogue_browser_routes import router as browser_router
from api.investigation_routes import router as investigation_router
from api.research_run_routes import router as run_router
from api.research_evidence_routes import router as evidence_router
from api.research_experiment_routes import router as experiment_router
from api.experiment_workspace_routes import router as execution_router
from api.v1_runtime_routes import V1RuntimeConfiguration, router as runtime_router
from db.app_models import AppBase, AppUser
from tests.system_acceptance_support import make_system_acceptance_fixture, seed_integrated_browser, source_revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, choices=[3101], default=3101)
    parser.add_argument('--state-file', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    args = parser.parse_args()
    state_path, observations = args.state_file.resolve(), args.observations.resolve()
    for path in (state_path, observations):
        if not path.is_relative_to(Path('/private/tmp')):
            parser.error('QA controls/observations must be explicit private/tmp files')
    if not state_path.is_file() or observations.exists():
        parser.error('Create a TEST control file and choose a new observations path')

    def state():
        value = json.loads(state_path.read_text())
        if (type(value) is not dict or value.get('actor') not in {'owner', 'other', 'admin'}
                or not isinstance(value.get('revision'), str)):
            raise ValueError('Explicit TEST actor and revision required')
        return value

    for name in ('SHELL', 'CATALOGUE', 'CATALOGUE_BROWSER', 'INVESTIGATIONS',
            'RESEARCH_CONTROLLER', 'RESEARCH_RUNS', 'RESEARCH_DISPATCH', 'EVIDENCE',
            'SYNTHESIS', 'EXPERIMENTS', 'EXPERIMENT_DISPATCH', 'EXPERIMENT_WORKSPACE'):
        os.environ['ENABLE_V1_' + name] = 'true'
    with TemporaryDirectory(prefix='ocean-c26-acceptance-') as directory:
        local = Path(directory)
        engine = create_engine('sqlite+pysqlite:///' + str(local / 'owned-app.sqlite'))

        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=10000')

        AppBase.metadata.create_all(engine)
        stack = make_system_acceptance_fixture(engine, local)
        fixture = stack.retained
        seed = seed_integrated_browser(stack)
        stack.workspace.enabled = lambda: state().get('execution_enabled', True) is True
        stack.experiments.service.enabled = lambda: state().get('approval_enabled', True) is True
        stack.experiments.service.dispatch_enabled = lambda: state().get('approval_enabled', True) is True
        ledger, faults, worker_log = [], set(), []

        def drain_local_queues():
            """Explicit synthetic queue delivery; never a provider/runtime fallback."""
            stack.runs.service.dispatch_outbox()
            while stack.runs.queue.deliveries:
                result = stack.runs.queue.deliver_next(stack.runs.service)
                worker_log.append({'service': 'C20', 'status': result.get('run', {}).get('status')})
            stack.answers.dispatch_outbox()
            while stack.answers.queue.deliveries:
                result = stack.answers.execute_delivery(**stack.answers.queue.deliveries.pop(0))
                worker_log.append({'service': 'C21', 'status': result.get('job', {}).get('status')})

        stopping = asyncio.Event()

        async def local_worker():
            while not stopping.is_set():
                try:
                    await run_in_threadpool(drain_local_queues)
                except Exception as error:
                    worker_log.append({'error_type': type(error).__name__, 'message': str(error)})
                await asyncio.sleep(0.2)

        @asynccontextmanager
        async def lifespan(_app):
            task = asyncio.create_task(local_worker())
            try:
                yield
            finally:
                # Finish the owned worker thread before disposing its SQLite
                # connections or deleting its temporary immutable catalogue.
                stopping.set()
                await task

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
        app.state.catalogue_service = fixture.service.catalogue
        app.state.catalogue_browser = stack.browser
        app.state.investigation_service = fixture.service
        app.state.research_run_service = stack.runs.service
        app.state.research_evidence_service = stack.evidence
        app.state.research_answer_service = stack.answers
        app.state.research_experiment_service = stack.experiments.service
        app.state.experiment_workspace_service = stack.workspace

        def configuration(actor):
            initial = V1RuntimeConfiguration(site_id=fixture.service.site_id, revision=state()['revision'])
            capabilities = dict(initial.capabilities)
            capabilities.update(research='ready', catalogue='ready')
            return V1RuntimeConfiguration(site_id=fixture.service.site_id, revision=state()['revision'], capabilities=capabilities)

        app.state.v1_runtime_configuration = configuration
        actors = {'owner': fixture.user, 'other': fixture.other, 'admin': fixture.admin}

        def authenticate(request):
            current = state()
            if current.get('unauthorized') is True:
                raise auth.AuthenticationFailure(401, 'Authentication is required')
            for sid in fixture.snapshots:
                fixture.policy[sid] = set(current.get('blocked_by_snapshot', {}).get(sid, []))
            actor = actors[current['actor']]
            role = current.get('role', actor.role)
            if role not in {'viewer', 'researcher', 'admin'}:
                raise ValueError('Explicit known TEST role required')
            with fixture.factory.begin() as session:
                row = session.scalar(select(AppUser).where(AppUser.id == actor.id))
                row.role = role
                row.status = 'suspended' if current.get('revoked') is True else 'active'
            return replace(actor, role=role, status='suspended' if current.get('revoked') is True else 'active',
                permissions=auth.permissions_for_role(role))

        auth.authenticate_request = authenticate

        @app.middleware('http')
        async def boundary(request, call_next):
            started = time.monotonic()
            if request.headers.get('host') not in {'127.0.0.1:3101', 'localhost:3101'}:
                return JSONResponse(status_code=403, content={'error': 'Loopback TEST host required'})
            path = request.url.path
            if not path.startswith(('/v1/', '/catalogue/', '/research/')):
                return await call_next(request)
            raw = await request.body()
            try:
                payload = json.loads(raw) if raw else None
            except ValueError:
                payload = {'invalid_body_bytes': len(raw)}
            response = await auth.authorization_middleware(request, call_next)
            current = state()
            fault = current.get('lose_write_ack')
            if (fault and fault not in faults and request.method == 'POST'
                    and path.endswith(current.get('lose_write_action', '/approve')) and response.status_code == 200):
                faults.add(fault)
                response = JSONResponse(status_code=503, content={'error': {'code': 'synthetic_ack_lost',
                    'message': 'Synthetic response acknowledgement lost'}}, headers={'Cache-Control': 'no-store'})
            ledger.append({'path': path, 'method': request.method, 'status': response.status_code,
                'actor': current['actor'], 'revision': current['revision'], 'request': payload,
                'wall_seconds': time.monotonic() - started})
            return response

        for router in (runtime_router, catalogue_router, browser_router, investigation_router,
                run_router, evidence_router, experiment_router, execution_router):
            app.include_router(router)

        @app.get('/_ocean/runtime-mode')
        async def mode():
            return JSONResponse(content={'version': 'ocean-v1-mode-v1', 'mode': 'service'})

        revision, files = source_revision()
        for folder in ('api', 'orchestration', 'schema', 'db', 'frontend-v1/src', 'frontend-v1/app'):
            for source in sorted((ROOT / folder).rglob('*')):
                if source.is_file() and source.suffix in {'.py', '.ts', '.tsx', '.css'}:
                    files[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
        for name in ('config.py', 'model_runtime.py', 'frontend-v1/package.json', 'frontend-v1/package-lock.json'):
            files[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        own_paths = ('docs/plans/ocean-v1/evidence/C26/serve_acceptance_qa.py',
            'frontend-v1/development/c26/app/page.tsx', 'frontend-v1/development/c26/app/layout.tsx',
            'frontend-v1/development/c26/next.config.mjs')
        metadata = {'fixture': 'synthetic-local-actual-services', 'source_revision': revision,
            'source_files': files, 'harness_files': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in own_paths},
            'no_live_provider_or_python_execution': True, 'production_queue': False,
            'start_enabled': stack.workspace.capability(fixture.user)['capability']['start_enabled'],
            'directory': directory, 'site_id': fixture.service.site_id, 'seed': seed,
            'snapshots': fixture.snapshots, 'dataset_ids': fixture.dataset_ids,
            'url': 'http://127.0.0.1:' + str(args.port)}
        print(json.dumps(metadata), flush=True)
        try:
            uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
        finally:
            engine.dispose()
            final_files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
            with observations.open('x') as stream:
                json.dump({'metadata': metadata, 'actual_requests': ledger, 'worker_observations': worker_log,
                    'faults_consumed': sorted(faults), 'server_stopped': True,
                    'source_files_after': final_files, 'source_unchanged': final_files == files}, stream, indent=2, ensure_ascii=False)
                stream.write('\n')


if __name__ == '__main__':
    main()
