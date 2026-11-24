"""Explicit beta Research composition; no cloud provisioning or ambient model.

Used by the serving API and the private delivery host with their independently
configured SQL identities. Experiment reads require a separate explicit binding.
Merely composing these services never dispatches an outbox or calls a provider.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select, text

import config
from api.v1_beta_research_host import SITE_ID, compose_beta_context_services
from api.v1_host import HostConfigurationError, RESEARCH_TRIAL_ENV, V1ReadServices
from db.app_models import ResearchAnswerJob, ResearchRun
from orchestration.beta_vertex_research import BetaVertexResearchRuntime
from orchestration.cloud_research_dispatch import CloudResearchQueue, CloudResearchSettings, PROJECT
from orchestration.research_answers import ResearchAnswerError, ResearchAnswerService
from orchestration.research_controller import ResearchController
from orchestration.research_evidence import ResearchEvidenceService
from orchestration.research_runs import ResearchRunError, ResearchRunService, _utc
from ingestion.beta_catalogue_retention import BetaResearchRetentionStore

QUESTION_MUTATION_PATHS = frozenset({
    "/research/runs/submit", "/research/runs/clarify", "/research/runs/continue",
    "/research/answers/submit",
})


class BetaModelSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    # An explicit model identity is an operator input, not an ambient default.
    model: Literal["gemini-3.8-flash"]
    location: Literal["global"]
    max_output_tokens: Literal[4096]


class BetaResearchTrial(BaseModel):
    """One fixed beta testing window with independent durable admission limits."""
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    version: Literal["ocean-v1-beta-research-trial-v1"]
    opens_at: datetime
    closes_at: datetime
    run_limit: int = Field(ge=1, le=3)
    answer_limit: int = Field(ge=1, le=3)
    sweep_only: bool = False

    @field_validator("opens_at", "closes_at", mode="before")
    @classmethod
    def utc_time(cls, value):
        if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
            raise ValueError("Explicit UTC trial time required")
        return datetime.fromisoformat(value)

    @model_validator(mode="after")
    def finite_window(self):
        if not timedelta(0) < self.closes_at - self.opens_at <= timedelta(days=1):
            raise ValueError("Trial must close within 24 hours")
        return self

    def admit(self, session, clock, kind, run):
        # Serialize new admissions until commit across API instances. The next
        # count must see the preceding transaction's durable rows.
        if session.get_bind().dialect.name == "postgresql":
            if session.connection().get_isolation_level() != "READ COMMITTED":
                raise ResearchRunError()
            session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('ocean-v1-beta-research-trial-v1', 0))"))
        now = clock(session)
        if not self.opens_at <= now < self.closes_at:
            raise ResearchRunError("budget_exhausted", 429)
        if kind == "clarify":
            if run is None or not self.opens_at <= _utc(run.created_at) < self.closes_at:
                raise ResearchRunError("budget_exhausted", 429)
            return now
        model, limit = {"run": (ResearchRun, self.run_limit), "answer": (ResearchAnswerJob, self.answer_limit)}[kind]
        admitted = select(model.created_at).where(model.created_at >= self.opens_at).limit(limit).subquery()
        if session.scalar(select(func.count()).select_from(admitted)) >= limit:
            raise ResearchRunError("budget_exhausted", 429)
        return now


def load_research_trial(environ):
    from api.v1_host import _unique

    if RESEARCH_TRIAL_ENV not in environ:
        return None
    try:
        raw = environ[RESEARCH_TRIAL_ENV]
        if (environ.get("OCEAN_V1_CATALOGUE_MODE") != "sealed-gcs-research-v1"
                or environ.get("OCEAN_V1_DATABASE_USER") != "ocean_v1_serving"
                or type(raw) is not str or len(raw.encode()) > 1024):
            raise ValueError("Explicit serving-only trial required")
        return BetaResearchTrial.model_validate(json.loads(raw, object_pairs_hook=_unique))
    except (KeyError, ValueError, TypeError, RecursionError):
        raise HostConfigurationError("Explicit beta Research trial unavailable") from None


class BetaResearchRunService(ResearchRunService):
    def _list(self, session, actor, data):
        # One request, inside the existing owner-locked SQL transaction. Every
        # run/context/payload is still verified; repeated activation/control
        # reads share a fence that closes before SQL commits. No mutation or
        # other request inherits this authority observation.
        from orchestration.research_runs import ResearchRunError
        try:
            with self.investigations.catalogue.read_scope():
                return super()._list(session, actor, data)
        except ResearchRunError:
            raise
        except Exception:
            raise ResearchRunError() from None


class BetaResearchEvidenceService(ResearchEvidenceService):
    def invoke(self, name, payload, user):
        if name != "list":
            return super().invoke(name, payload, user)
        from orchestration.research_evidence import ResearchEvidenceError
        from schema.research_evidence import EVIDENCE_REQUEST_MODELS, EVIDENCE_RESPONSE_MODELS
        try:
            request = EVIDENCE_REQUEST_MODELS[name].model_validate(payload)
        except (TypeError, ValueError):
            raise ResearchEvidenceError("invalid_request", 422) from None
        try:
            result = self._ready_listing(request, user)
            if result is not None:
                return EVIDENCE_RESPONSE_MODELS[name].model_validate(result).model_dump(mode="json")
            return super().invoke(name, payload, user)
        except ResearchEvidenceError:
            raise
        except Exception:
            raise ResearchEvidenceError() from None

    @contextmanager
    def _transaction(self):
        # Close current activation/control proofs before committing SQL. C09
        # retention writes remain between transactions, outside this read scope.
        with super()._transaction() as session:
            with self.catalogue.read_scope():
                yield session


class BetaResearchAnswerService(ResearchAnswerService):
    def invoke(self, name, payload, user, *, allow_new_submit=True):
        if name not in {"list", "status", "events"}:
            return super().invoke(name, payload, user, allow_new_submit=allow_new_submit)
        try:
            with self.investigations.catalogue.read_scope():
                return super().invoke(name, payload, user, allow_new_submit=allow_new_submit)
        except ResearchAnswerError:
            raise
        except Exception:
            # Closing authority failures happen outside the base invoke guard.
            raise ResearchAnswerError() from None


@dataclass(frozen=True)
class BetaQuestionServices(V1ReadServices):
    cloud_settings: CloudResearchSettings | None = None
    model_settings: BetaModelSettings | None = None

    def validate(self, *, session_factory, site_id, allow_test=False, research_execution=False):
        if not research_execution:
            raise HostConfigurationError("Explicit beta question mode required")
        super().validate(session_factory=session_factory, site_id=site_id,
            allow_test=allow_test, research_execution=True)
        if (site_id != SITE_ID or not isinstance(self.cloud_settings, CloudResearchSettings)
                or not isinstance(self.model_settings, BetaModelSettings)):
            raise HostConfigurationError("Exact beta question services required")
        experiments, workspace = self.research_experiment_service, self.experiment_workspace_service
        if experiments is not None or workspace is not None:
            from api.v1_beta_experiment_reads import BetaReadOnlyExperimentService
            from orchestration.experiment_sandbox.workspace_projection import RetainedExecutionProjection

            if (type(experiments) is not BetaReadOnlyExperimentService or experiments.owner_locker is not lock_research_owner
                    or experiments.dispatch_enabled() is not False or workspace is None
                    or type(workspace.port) is not RetainedExecutionProjection or not workspace.port.uses_read_only_ledger):
                raise HostConfigurationError("Explicit beta experiment read-only composition required")
        runs, answers = self.research_run_service, self.research_answer_service
        if runs is None or answers is None or self.research_evidence_service is None:
            raise HostConfigurationError("Complete durable question services required")
        if runs.owner_locker is not lock_research_owner:
            raise HostConfigurationError("Explicit account-read-only owner lock required")
        for service, kind in ((runs, "run"), (answers, "answer")):
            if (not isinstance(service.queue, CloudResearchQueue) or service.queue.kind != kind
                    or service.queue.settings != self.cloud_settings):
                raise HostConfigurationError("Exact production Cloud Tasks binding required")
        runtime = answers.runtime
        if (not isinstance(runtime, BetaVertexResearchRuntime) or runtime.project != PROJECT
                or runtime.location != self.model_settings.location or runtime.max_attempts != 1
                or runtime.request_timeout_seconds != 45 or answers.model != self.model_settings.model):
            raise HostConfigurationError("Explicit bounded beta Vertex runtime required")
        factory = runs.controller_factory
        if (not isinstance(factory, partial) or factory.func is not _controller
                or factory.keywords.get("runtime") is not runtime
                or factory.keywords.get("model") != answers.model
                or factory.keywords.get("catalogue") is not self.catalogue_service
                or factory.keywords.get("investigations") is not self.investigation_service):
            raise HostConfigurationError("Shared controller model and data binding required")


def question_execution_fence(environ=None):
    """Research flags may be drained. Experiment writes and dispatch stay off."""
    import os
    env = os.environ if environ is None else environ
    try:
        for name in ("ENABLE_V1_EXPERIMENTS", "ENABLE_V1_EXPERIMENT_DISPATCH", "ENABLE_V1_EXPERIMENT_WORKSPACE"):
            if env.get(name, "false").strip().lower() != "false":
                raise ValueError("Experimental execution not selected")
        # Invalid flags never become an enabled or silently drained deployment.
        for gate in (config.v1_research_runs_enabled, config.v1_research_dispatch_enabled,
                     config.v1_research_controller_enabled, config.v1_evidence_enabled, config.v1_synthesis_enabled):
            gate(env)
    except Exception:
        raise HostConfigurationError("Explicit research-only activation required") from None


def compose_beta_question_services(*, session_factory, catalogue_service, catalogue_browser,
                                   cloud_settings, model_settings, experiment_reads=None, trial=None):
    if not isinstance(cloud_settings, CloudResearchSettings) or not isinstance(model_settings, BetaModelSettings):
        raise HostConfigurationError("Explicit beta cloud and model configuration required")
    if trial is not None and type(trial) is not BetaResearchTrial:
        raise HostConfigurationError("Explicit beta Research trial required")
    if not isinstance(catalogue_service.resolver.store, BetaResearchRetentionStore):
        raise HostConfigurationError("Explicit evidence retention authority required")
    from api.v1_catalogue_host import _activation
    try:
        _activation(catalogue_service.resolver.authority.initial.data, research_enabled=True)
    except Exception:
        raise HostConfigurationError("Explicit research-enabled source activation required") from None
    context = compose_beta_context_services(session_factory=session_factory, site_id=SITE_ID,
        catalogue_service=catalogue_service, catalogue_browser=catalogue_browser)
    investigations = context.investigation_service
    runtime = BetaVertexResearchRuntime(project=PROJECT, location=model_settings.location, embedding_dim=768,
        max_attempts=1, request_timeout_seconds=45)
    import hashlib
    from pathlib import Path
    identity = {"provider": "vertex", "project": PROJECT, "location": model_settings.location,
                "model": model_settings.model, "max_attempts": 1, "request_timeout_seconds": 45,
                "thinking_level": "LOW", "max_output_tokens": 4096,
                "runtime_source_sha256": hashlib.sha256((Path(__file__).parents[1] /
                    "orchestration/beta_vertex_research.py").read_bytes()).hexdigest()}
    factory = partial(_controller, investigations=investigations, catalogue=catalogue_service,
        runtime=runtime, model=model_settings.model, runtime_identity=identity)
    nudge_on_accept = trial is None or not trial.sweep_only
    runs = BetaResearchRunService(session_factory=session_factory, site_id=SITE_ID,
        investigations=investigations, controller_factory=factory,
        queue=CloudResearchQueue(settings=cloud_settings, kind="run", nudge_on_accept=nudge_on_accept),
        owner_locker=lock_research_owner,
        admission=trial.admit if trial is not None else None)
    evidence = BetaResearchEvidenceService(session_factory=session_factory, site_id=SITE_ID,
        investigations=investigations, runs=runs)
    answers = BetaResearchAnswerService(evidence=evidence,
        queue=CloudResearchQueue(settings=cloud_settings, kind="answer", nudge_on_accept=nudge_on_accept),
        runtime=runtime, model=model_settings.model, runtime_identity=identity)
    investigations.artifact_resolver = evidence.attachment_resolver()
    investigations.evidence_protection = evidence
    experiments = workspace = None
    if experiment_reads is not None:
        from api.v1_beta_experiment_reads import compose_beta_experiment_reads

        experiments, workspace = compose_beta_experiment_reads(investigations, experiment_reads)
    services = BetaQuestionServices(catalogue_service=catalogue_service, catalogue_browser=catalogue_browser,
        investigation_service=investigations, research_run_service=runs,
        research_evidence_service=evidence, research_answer_service=answers,
        research_experiment_service=experiments, experiment_workspace_service=workspace,
        cloud_settings=cloud_settings, model_settings=model_settings)
    services.validate(session_factory=session_factory, site_id=SITE_ID, research_execution=True)
    return services


def _controller(identity_provider, **bindings):
    return ResearchController(identity_provider=identity_provider, **bindings)


def lock_research_owner(session, identity):
    """Production account-row lock; the runtime receives no account write grant."""
    from sqlalchemy import text
    import uuid
    session.execute(text("SELECT public.ocean_v1_beta_research_owner_lock(:owner_id)"),
        {"owner_id": uuid.UUID(str(identity))})


def load_question_configuration(filename=None, *, document_json=None):
    import json
    from pathlib import Path
    from api.v1_host import _unique
    try:
        if (filename is None) == (document_json is None):
            raise ValueError("Select exactly one explicit configuration")
        if filename is not None:
            path = Path(filename)
            if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
                raise ValueError("Explicit bounded configuration required")
            document_json = path.read_text()
        if type(document_json) is not str or len(document_json.encode()) > 16384:
            raise ValueError("Bounded configuration required")
        data = json.loads(document_json, object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite")))
        if type(data) is not dict or set(data) != {"cloud", "model"}:
            raise ValueError("Exact research configuration required")
        return CloudResearchSettings.model_validate(data["cloud"]), BetaModelSettings.model_validate(data["model"])
    except Exception:
        raise HostConfigurationError("Explicit beta research configuration unavailable") from None


def dispatch_pending_questions(services):
    """Bounded post-response nudge; scheduled sweeps provide durable recovery.

    Preserve pending outbox rows on any uncertain transport/SQL result. Never
    expose a provider/SQL exception in a response or application log.
    """
    outcomes = []
    for service in (services.research_run_service, services.research_answer_service):
        try:
            service.dispatch_outbox(limit=1)
            outcomes.append(True)
        except Exception:
            outcomes.append(False)
    return all(outcomes)
