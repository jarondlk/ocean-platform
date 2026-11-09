"""Explicit independent v1 API entry: authenticated reads, no runtime discovery.

Use ``uvicorn api.v1_host:create_from_environment --factory`` with an explicit
OCEAN_V1_HOST_CONFIG file and prefixed credential variables. This module never
imports api.main, opens the legacy default database, migrates, creates tables,
starts background work or loads scientific fixtures. A trusted host may supply
real policy-bound services programmatically; absent services stay unavailable.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import hmac
import json
import math
import os
from pathlib import Path
import re
from typing import Literal

from anyio.lowlevel import checkpoint
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import jwt
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

import config
from api.auth import (
    AuthenticationFailure, CurrentUser, current_user_from_model, normalize_email,
    route_permission,
)
from api.catalogue_browser_routes import router as browser_router
from api.catalogue_routes import router as catalogue_router
from api.experiment_workspace_routes import router as workspace_router
from api.investigation_routes import router as investigation_router
from api.research_evidence_routes import router as evidence_router
from api.research_experiment_routes import router as experiment_router
from api.research_run_routes import router as run_router
from api.rate_limit import InMemoryRateLimiter, PostgresRateLimiter, RateLimitPolicy, policy_for_request
from api.v1_runtime_routes import V1RuntimeConfiguration, router as runtime_router
from db.app_models import AppUser
from orchestration.catalogue_browser import CatalogueBrowser
from orchestration.catalogue_service import CatalogueService, FrozenCatalogueResolver
from orchestration.experiment_workspace import ExperimentWorkspaceService
from orchestration.frozen_experiment_export import FrozenExperimentExporter
from orchestration.investigations import InvestigationService
from orchestration.research_answers import ResearchAnswerService
from orchestration.research_evidence import ResearchEvidenceService
from orchestration.research_experiments import ResearchExperimentService
from orchestration.research_runs import ResearchRunService

MIGRATION_HEAD = '20261027_0021'
EXECUTION_FLAGS = (
    'ENABLE_V1_RESEARCH_CONTROLLER', 'ENABLE_V1_RESEARCH_DISPATCH',
    'ENABLE_V1_SYNTHESIS', 'ENABLE_V1_EXPERIMENT_DISPATCH',
)
MAX_REQUEST_BYTES = 1024 * 1024
READ_POST_PATHS = frozenset({
    '/catalogue/snapshots', '/catalogue/overview', '/catalogue/list', '/catalogue/open',
    '/catalogue/coverage', '/catalogue/query', '/catalogue/relationships', '/catalogue/analysis/get-published',
    '/research/investigations/list', '/research/investigations/get',
    '/research/investigations/conversations/list', '/research/investigations/conversations/get',
    '/research/investigations/context/get', '/research/investigations/operations/get',
    '/research/runs/status', '/research/runs/events', '/research/runs/list', '/research/runs/cancel',
    '/research/answers/status', '/research/answers/events', '/research/answers/list', '/research/answers/cancel',
    '/research/evidence/list', '/research/evidence/open', '/research/evidence/page', '/research/evidence/export',
    '/research/experiments/get', '/research/experiments/status', '/research/experiments/list', '/research/experiments/events',
    '/research/experiment-executions/capability', '/research/experiment-executions/status',
    '/research/experiment-executions/events', '/research/experiment-executions/cancel',
    '/research/experiment-executions/artifact',
})


class HostConfigurationError(ValueError):
    """Credential-safe startup diagnostic; never contains a DSN or token."""


class V1HostSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)
    version: Literal['ocean-v1-api-host-v1']
    project_id: str = Field(pattern=r'^ocean-v1-beta-[a-z0-9-]{1,20}$')
    site_id: str
    revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    public_origin: Literal['https://beta.oceaninfobio.com']
    database_name: str = Field(pattern=r'^ocean_v1_[a-z0-9_]+$')
    backend_hosts: tuple[str, ...]
    allowed_providers: tuple[Literal['google', 'oidc'], ...]
    internal_issuer: Literal['ocean-v1-frontend']
    internal_audience: Literal['ocean-v1-api']

    @model_validator(mode='after')
    def independent(self):
        if self.site_id != 'v1:' + self.project_id:
            raise ValueError('Exact independent site identity required')
        if not self.allowed_providers or len(set(self.allowed_providers)) != len(self.allowed_providers):
            raise ValueError('Explicit distinct provider allowlist required')
        if (not self.backend_hosts or len(set(self.backend_hosts)) != len(self.backend_hosts)
                or any(host not in {'127.0.0.1:8000', 'localhost:8000'} for host in self.backend_hosts)):
            raise ValueError('Explicit sidecar-only Host allowlist required')
        return self


@dataclass(frozen=True)
class V1ReadServices:
    catalogue_service: CatalogueService | None = None
    catalogue_browser: CatalogueBrowser | None = None
    investigation_service: InvestigationService | None = None
    research_run_service: ResearchRunService | None = None
    research_evidence_service: ResearchEvidenceService | None = None
    research_answer_service: ResearchAnswerService | None = None
    research_experiment_service: ResearchExperimentService | None = None
    experiment_workspace_service: ExperimentWorkspaceService | None = None

    def validate(self, *, session_factory, site_id, allow_test=False, research_execution=False):
        pairs = (
            ('catalogue_service', CatalogueService), ('catalogue_browser', CatalogueBrowser),
            ('investigation_service', InvestigationService), ('research_run_service', ResearchRunService),
            ('research_evidence_service', ResearchEvidenceService), ('research_answer_service', ResearchAnswerService),
            ('research_experiment_service', ResearchExperimentService),
            ('experiment_workspace_service', ExperimentWorkspaceService),
        )
        for name, kind in pairs:
            service = getattr(self, name)
            if service is None:
                continue
            if not isinstance(service, kind):
                raise HostConfigurationError('Explicit typed v1 services required')
            if name not in {'catalogue_service', 'catalogue_browser'}:
                if service.site_id != site_id or service.session_factory is not session_factory:
                    raise HostConfigurationError('Services must share the exact independent database and site')
        if self.catalogue_browser and self.catalogue_browser.service is not self.catalogue_service:
            raise HostConfigurationError('Catalogue browser binding mismatch')
        investigations = self.investigation_service
        if investigations and investigations.catalogue is not self.catalogue_service:
            raise HostConfigurationError('Investigation catalogue binding mismatch')
        for name in ('research_run_service', 'research_evidence_service', 'research_answer_service',
                'research_experiment_service', 'experiment_workspace_service'):
            service = getattr(self, name)
            if service and service.investigations is not investigations:
                raise HostConfigurationError('Retained service investigation binding mismatch')
        runs, answers, experiments = self.research_run_service, self.research_answer_service, self.research_experiment_service
        if not research_execution and runs and (runs.queue is not None or runs.controller_factory is not None):
            raise HostConfigurationError('Read-only host cannot contain research execution wiring')
        if not research_execution and answers and (answers.queue is not None or answers.runtime is not None):
            raise HostConfigurationError('Read-only host cannot contain synthesis wiring')
        if experiments and experiments.executor is not None:
            raise HostConfigurationError('Read-only host cannot contain experiment dispatch wiring')
        evidence, workspace = self.research_evidence_service, self.experiment_workspace_service
        if evidence and evidence.runs is not runs:
            raise HostConfigurationError('Evidence run binding mismatch')
        if answers and answers.evidence is not evidence:
            raise HostConfigurationError('Answer evidence binding mismatch')
        if workspace and workspace.experiments is not experiments:
            raise HostConfigurationError('Workspace experiment binding mismatch')
        if workspace and workspace.port is not None and workspace.port.source != 'retained-operator' and not allow_test:
            raise HostConfigurationError('Production host cannot expose a synthetic execution port')


def compose_read_services(*, session_factory, site_id, snapshot_store, registrations,
                          policy_resolver, snapshots, discovery_policy, policy_revision,
                          cursor_key, experiment_environments=None):
    """Build actual read services from explicitly supplied source authority.

    This is a trusted programmatic composition seam, not configuration-driven
    code loading. The operator must supply reviewed sealed registrations and
    current dataset/scientific/discovery policy; this function never invents
    those decisions or discovers snapshots, data or legacy stores.
    """
    if not registrations:
        raise HostConfigurationError('Explicit sealed registrations are required for configured catalogue access')
    catalogue = CatalogueService(resolver=FrozenCatalogueResolver(store=snapshot_store,
        policy_resolver=policy_resolver, registrations=registrations))
    browser = CatalogueBrowser(service=catalogue, snapshots=snapshots, permitted=discovery_policy,
        revision=policy_revision, cursor_key=cursor_key)
    investigations = InvestigationService(session_factory=session_factory, site_id=site_id,
        catalogue_service=catalogue, snapshot_store=snapshot_store, registrations=registrations)
    runs = ResearchRunService(session_factory=session_factory, site_id=site_id, investigations=investigations,
        enabled=lambda: True, dispatch_enabled=lambda: False)
    evidence = ResearchEvidenceService(session_factory=session_factory, site_id=site_id,
        investigations=investigations, runs=runs, enabled=lambda: True)
    answers = ResearchAnswerService(evidence=evidence, enabled=lambda: True, synthesis_enabled=lambda: False)
    investigations.artifact_resolver = evidence.attachment_resolver()
    investigations.evidence_protection = evidence
    experiments = workspace = None
    if experiment_environments is not None:
        exporter = FrozenExperimentExporter(store=snapshot_store, catalogue=catalogue, registrations=registrations)
        experiments = ResearchExperimentService(session_factory=session_factory, site_id=site_id,
            investigations=investigations, exporter=exporter, environments=experiment_environments,
            enabled=lambda: True, dispatch_enabled=lambda: False)
        workspace = ExperimentWorkspaceService(experiments=experiments, enabled=lambda: True)
    return V1ReadServices(catalogue, browser, investigations, runs, evidence, answers, experiments, workspace)


def _execution_fence():
    # Read routes consult existing independent capability flags. Never set global
    # environment values from host config, and never let ambient dispatch enable.
    try:
        enabled = any(getattr(config, name)() for name in (
            'v1_research_controller_enabled', 'v1_research_dispatch_enabled',
            'v1_synthesis_enabled', 'v1_experiment_dispatch_enabled'))
        if enabled or any(os.environ.get(name, 'false').strip().lower() != 'false' for name in EXECUTION_FLAGS):
            raise ValueError('Execution capability requested')
    except Exception:
        raise HostConfigurationError('Read-only host requires all execution flags false') from None


def _schema_ready(session_factory, settings, *, allow_test=False):
    try:
        with session_factory() as session:
            bind = session.get_bind()
            if bind.dialect.name == 'postgresql':
                if session.execute(text('SELECT current_database()')).scalar_one() != settings.database_name:
                    raise HostConfigurationError('Independent database identity mismatch')
            elif not (allow_test and bind.dialect.name == 'sqlite'):
                raise HostConfigurationError('Production v1 host requires explicit PostgreSQL')
            if session.execute(text('SELECT version_num FROM alembic_version')).scalars().all() != [MIGRATION_HEAD]:
                raise HostConfigurationError('Explicit migration head is not ready')
            return bind
    except HostConfigurationError:
        raise
    except Exception:
        raise HostConfigurationError('Independent database schema is unavailable; run migrations separately') from None


def _authenticate(request, session_factory, settings, secret):
    if len(request.headers.getlist('authorization')) != 1:
        raise AuthenticationFailure(401, 'Authentication required')
    authorization = request.headers.get('authorization', '')
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token or ' ' in token or len(token) > 8192:
        raise AuthenticationFailure(401, 'Authentication required')
    try:
        claims = jwt.decode(token, secret, algorithms=['HS256'], audience=settings.internal_audience,
            issuer=settings.internal_issuer, options={'require': ['exp', 'iat', 'iss', 'aud', 'sub',
                'email', 'provider', 'email_verified']})
        iat, exp = claims['iat'], claims['exp']
        if (type(iat) not in (int, float) or type(exp) not in (int, float)
                or not math.isfinite(iat) or not math.isfinite(exp)
                or not 0 < exp - iat <= 120 or claims['email_verified'] is not True
                or claims['iss'] != settings.internal_issuer or claims['aud'] != settings.internal_audience
                or claims['provider'] not in settings.allowed_providers
                or not isinstance(claims['email'], str)
                or not isinstance(claims['sub'], str) or not 1 <= len(claims['sub']) <= 255):
            raise ValueError('Invalid identity')
        email = normalize_email(claims['email'])
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, OverflowError):
        raise AuthenticationFailure(401, 'Invalid or expired identity token') from None
    try:
        with session_factory() as session:
            # An operator enrolls accounts in this independent database. Reads
            # never import or provision users from the legacy site or by email.
            user = session.scalar(select(AppUser).where(AppUser.auth_provider == claims['provider'],
                AppUser.auth_subject == claims['sub']))
            if user is None or user.status != 'active' or user.email != email:
                raise AuthenticationFailure(403, 'This identity has no active v1 account')
            if user.role not in {'viewer', 'researcher', 'admin'} or user.account_type not in {'research', 'commercial', 'internal'}:
                raise AuthenticationFailure(403, 'This identity has no valid v1 role')
            return current_user_from_model(user)
    except AuthenticationFailure:
        raise
    except Exception:
        raise AuthenticationFailure(503, 'Independent authentication store is unavailable') from None


def _failure(status, code, message):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}},
        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


def create_host_app(*, settings: V1HostSettings, session_factory, internal_secret: SecretStr,
                    services: V1ReadServices | None = None, context_mutations=False,
                    research_execution=False,
                    _allow_test_sqlite=False, _owned_engine=None):
    """Compose trusted explicit dependencies. Only tests may request SQLite."""
    if not isinstance(settings, V1HostSettings) or not callable(session_factory):
        raise HostConfigurationError('Explicit validated settings and independent session factory required')
    if _allow_test_sqlite and os.environ.get('DEPLOYMENT_ENV') != 'test':
        raise HostConfigurationError('SQLite or synthetic host injection requires explicit test environment')
    if not isinstance(internal_secret, SecretStr) or len(internal_secret.get_secret_value()) < 32:
        raise HostConfigurationError('Independent signing secret requires at least 32 characters')
    if type(research_execution) is not bool:
        raise HostConfigurationError('Explicit research mode required')
    execution_fence = _execution_fence
    if research_execution:
        from api.v1_beta_question_services import BetaQuestionServices, question_execution_fence
        if not isinstance(services, BetaQuestionServices):
            raise HostConfigurationError('Explicit durable beta question bundle required')
        execution_fence = question_execution_fence
    execution_fence()
    bind = _schema_ready(session_factory, settings, allow_test=_allow_test_sqlite)
    services = services or V1ReadServices()
    if not isinstance(services, V1ReadServices):
        raise HostConfigurationError('Explicit v1 service bundle required')
    services.validate(session_factory=session_factory, site_id=settings.site_id, allow_test=_allow_test_sqlite,
        research_execution=research_execution)
    mutation_paths = frozenset()
    if type(context_mutations) is not bool:
        raise HostConfigurationError('Explicit context mutation selection required')
    if context_mutations:
        from api.v1_beta_research_host import CONTEXT_MUTATION_PATHS, compose_beta_context_services
        # Validate the exact durable composition, never a feature flag alone.
        expected = compose_beta_context_services(session_factory=session_factory,
            site_id=settings.site_id, catalogue_service=services.catalogue_service,
            catalogue_browser=services.catalogue_browser)
        if (services.investigation_service is None
                or services.investigation_service.store is not expected.investigation_service.store):
            raise HostConfigurationError('Durable context store binding required')
        mutation_paths = CONTEXT_MUTATION_PATHS
    if research_execution:
        from api.v1_beta_question_services import QUESTION_MUTATION_PATHS
        if not context_mutations:
            raise HostConfigurationError('Question mode requires durable context mutations')
        mutation_paths = mutation_paths | QUESTION_MUTATION_PATHS
    limiter = InMemoryRateLimiter() if _allow_test_sqlite else PostgresRateLimiter(engine_factory=lambda: bind)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            if _owned_engine is not None:
                await run_in_threadpool(_owned_engine.dispose)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    for name in services.__dataclass_fields__:
        setattr(app.state, name, getattr(services, name))
    app.state.v1_services = services
    initial = V1RuntimeConfiguration(site_id=settings.site_id, revision=settings.revision)
    capabilities = dict(initial.capabilities)
    if services.catalogue_service and services.catalogue_browser:
        capabilities['catalogue'] = 'ready'
    if services.investigation_service and capabilities['catalogue'] == 'ready':
        capabilities['research'] = 'ready'
    app.state.v1_runtime_configuration = V1RuntimeConfiguration(
        site_id=settings.site_id, revision=settings.revision, capabilities=capabilities)
    app.state.v1_host_settings = settings

    @app.middleware('http')
    async def boundary(request, call_next):
        if len(request.headers.getlist('host')) != 1 or request.headers.get('host') not in settings.backend_hosts:
            return _failure(421, 'host_denied', 'Backend Host is not allowed')
        if request.query_params:
            return _failure(422, 'invalid_request', 'Query parameters are not accepted')
        if request.method in {'GET', 'HEAD'} and request.url.path == '/health/live':
            return JSONResponse({'status': 'live', 'execution_enabled': research_execution})
        try:
            execution_fence()
            user = await run_in_threadpool(_authenticate, request, session_factory, settings,
                internal_secret.get_secret_value())
            await checkpoint()
            if not ((request.method == 'GET' and request.url.path in {'/me', '/v1/runtime'})
                    or request.method == 'POST' and request.url.path in READ_POST_PATHS | mutation_paths):
                return _failure(403, 'readonly_stage', 'This action is unavailable in the read-only v1 stage')
            permission = route_permission(request.method, request.url.path)
            if permission is None or permission not in user.permissions:
                return _failure(403, 'access_denied', 'This identity cannot access the requested operation')
            if request.url.path.startswith('/research/') and not {'chat:use', 'data:read'} <= user.permissions:
                return _failure(403, 'access_denied', 'Research access is denied')
            policy = policy_for_request(request.method, request.url.path) or RateLimitPolicy('v1_read', 240)
            retry = await run_in_threadpool(limiter.retry_after, subject=str(user.id), policy=policy)
            await checkpoint()
            if retry is not None:
                response = _failure(429, 'rate_limited', 'Request rate limit exceeded')
                response.headers['Retry-After'] = str(retry)
                return response
            if request.method == 'POST':
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_REQUEST_BYTES:
                        return _failure(413, 'request_too_large', 'Request body exceeds the host limit')
                    chunks.append(chunk)
                request._body = b''.join(chunks)
            request.state.current_user = user
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response
        except AuthenticationFailure as exc:
            return _failure(exc.status_code, 'authentication_required' if exc.status_code == 401 else 'access_denied', exc.detail)
        except HostConfigurationError:
            return _failure(503, 'host_configuration_unavailable', 'Read-only host configuration is unavailable')

    @app.get('/health/live')
    def live():
        return {'status': 'live', 'execution_enabled': research_execution}

    @app.get('/me')
    def me(request: Request):
        user: CurrentUser = request.state.current_user
        return {'id': str(user.id), 'email': user.email, 'display_name': user.display_name,
            'role': user.role, 'account_type': user.account_type, 'status': user.status,
            'permissions': sorted(user.permissions), 'auth_provider': user.auth_provider}

    for router in (runtime_router, catalogue_router, browser_router, investigation_router,
            run_router, evidence_router, experiment_router, workspace_router):
        app.include_router(router)
    return app


def _unique(items):
    result = {}
    for name, value in items:
        if name in result:
            raise HostConfigurationError('Duplicate host configuration key')
        result[name] = value
    return result


def catalogue_services_from_environment(settings, secret, environ, *, session_factory=None):
    """Bind only an explicitly configured, operator-owned catalogue inventory.

    The initial production registry is empty. It attests no scientific data,
    creates no snapshots or registrations, and enables no research execution.
    Missing configuration retains the existing unavailable-service behavior.
    """
    path = environ.get('OCEAN_V1_CATALOGUE_CONFIG')
    if path is None:
        return None
    from api.v1_catalogue_host import load_empty_catalogue, load_snapshot_catalogue
    mode = environ.get('OCEAN_V1_CATALOGUE_MODE', 'empty')
    if mode not in {'empty', 'sealed-gcs-v1', 'sealed-gcs-context-v1', 'sealed-gcs-research-v1'}:
        raise HostConfigurationError('Explicit supported catalogue mode required')
    key = hmac.digest(secret.get_secret_value().encode('utf-8'),
        b'ocean-v1-beta:catalogue-discovery-cursor:v1', 'sha256')
    loader = load_empty_catalogue if mode == 'empty' else load_snapshot_catalogue
    kwargs = {'context_retention': True} if mode in {'sealed-gcs-context-v1', 'sealed-gcs-research-v1'} else {}
    if mode == 'sealed-gcs-research-v1':
        kwargs['research_retention'] = True
    catalogue, browser = loader(path, project_id=settings.project_id,
        site_id=settings.site_id, cursor_key=key, **kwargs)
    if mode == 'sealed-gcs-research-v1':
        from api.v1_beta_question_services import load_question_configuration, compose_beta_question_services
        cloud_settings, model_settings = load_question_configuration(environ.get('OCEAN_V1_RESEARCH_CONFIG'),
            document_json=environ.get('OCEAN_V1_RESEARCH_CONFIG_JSON'))
        return compose_beta_question_services(session_factory=session_factory,
            catalogue_service=catalogue, catalogue_browser=browser,
            cloud_settings=cloud_settings, model_settings=model_settings)
    if mode == 'sealed-gcs-context-v1':
        from api.v1_beta_research_host import compose_beta_context_services
        return compose_beta_context_services(session_factory=session_factory, site_id=settings.site_id,
            catalogue_service=catalogue, catalogue_browser=browser)
    return V1ReadServices(catalogue_service=catalogue, catalogue_browser=browser)


def create_from_environment():
    """Separate production factory: never reads DATABASE_URL or api.main."""
    engine = None
    try:
        path = Path(os.environ['OCEAN_V1_HOST_CONFIG'])
        if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            raise ValueError('Explicit bounded configuration required')
        document = json.loads(path.read_text(), object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid constant')))
        # JSON arrays become immutable tuples only in this trusted decoding step.
        for name in ('backend_hosts', 'allowed_providers'):
            if type(document.get(name)) is not list:
                raise ValueError('Explicit list required')
            document[name] = tuple(document[name])
        settings = V1HostSettings.model_validate(document)
        dsn = os.environ['OCEAN_V1_DATABASE_URL']
        parsed = make_url(dsn)
        socket = parsed.query.get('host')
        target_allowed = (
            parsed.host in {None, ''} and isinstance(socket, str)
            and re.fullmatch(r'/cloudsql/' + re.escape(settings.project_id) + r':[a-z0-9-]+:[a-z0-9-]+', socket)
        ) if socket is not None else parsed.host in {'127.0.0.1', 'localhost'}
        if (parsed.get_backend_name() != 'postgresql' or parsed.database != settings.database_name
                or not parsed.username or not parsed.username.startswith('ocean_v1_') or not target_allowed):
            raise ValueError('Explicit independent PostgreSQL target required')
        # Socket/connector loopback targets still use the explicitly named beta
        # database/user. Direct public or legacy SQL endpoints are not accepted.
        secret = SecretStr(os.environ['OCEAN_V1_INTERNAL_AUTH_SECRET'])
        engine = create_engine(dsn, pool_pre_ping=True, connect_args={'connect_timeout': 10})
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        services = catalogue_services_from_environment(settings, secret, os.environ, session_factory=factory)
        app = create_host_app(settings=settings, session_factory=factory, internal_secret=secret,
            services=services, _owned_engine=engine,
            context_mutations=os.environ.get('OCEAN_V1_CATALOGUE_MODE') in {'sealed-gcs-context-v1', 'sealed-gcs-research-v1'},
            research_execution=os.environ.get('OCEAN_V1_CATALOGUE_MODE') == 'sealed-gcs-research-v1')
        app.state.v1_owned_engine = engine
        return app
    except Exception:
        if engine is not None:
            engine.dispose()
        raise HostConfigurationError('Independent v1 host startup rejected; check explicit configuration and migration readiness') from None
