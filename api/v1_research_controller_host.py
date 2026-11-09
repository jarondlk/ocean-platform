"""Private Cloud Tasks delivery host, separate from browser authentication.

Cloud Run IAM and internal ingress are required deployment boundaries. Google
OIDC is also verified here against the exact audience and pinned invoker subject;
task headers alone never authenticate. Owners are loaded by the durable services.
"""
from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from orchestration.cloud_research_dispatch import CloudResearchQueue, CloudResearchSettings, delivery_body
from orchestration.research_answers import ResearchAnswerService
from orchestration.research_runs import ResearchRunService

MAX_BODY = 1024


def verify_google_invoker(token, audience):
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.id_token import verify_oauth2_token
    return verify_oauth2_token(token, GoogleRequest(), audience=audience)


def _unique(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("Duplicate delivery field")
        output[key] = value
    return output


def create_controller_app(*, settings, runs, answers, token_verifier=verify_google_invoker, owned_engine=None):
    if (not isinstance(settings, CloudResearchSettings)
            or not isinstance(runs, ResearchRunService) or not isinstance(answers, ResearchAnswerService)
            or answers.runs is not runs or not callable(token_verifier)
            or runs.site_id != "v1:" + settings.project_id):
        raise ValueError("Explicit shared beta research services required")
    for service, kind in ((runs, "run"), (answers, "answer")):
        if (not isinstance(service.queue, CloudResearchQueue) or service.queue.settings != settings
                or service.queue.kind != kind):
            raise ValueError("Actual matching Cloud Tasks transports required")
    if not runs.dispatch_available or not answers.dispatch_available:
        raise ValueError("Explicit execution wiring required")
    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            if owned_engine is not None:
                await run_in_threadpool(owned_engine.dispose)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def failure(code, status):
        return JSONResponse({"error": {"code": code}}, status_code=status,
                            headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.url.path == "/health/live" and request.method == "GET":
            return JSONResponse({"status": "live"})
        if request.method != "POST" or request.url.path not in {
                "/internal/research/run", "/internal/research/answer", "/internal/research/dispatch"} or request.query_params:
            return failure("route_unavailable", 404)
        try:
            if len(request.headers.getlist("authorization")) != 1:
                raise ValueError("Missing identity")
            header = request.headers["authorization"]
            if not header.startswith("Bearer ") or not 1 <= len(header[7:]) <= 8192 or " " in header[7:]:
                raise ValueError("Invalid identity")
            claims = await run_in_threadpool(token_verifier, header[7:], settings.controller_origin)
            now = time.time()
            if (claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
                    or claims.get("aud") != settings.controller_origin
                    or claims.get("sub") != settings.task_invoker_subject
                    or claims.get("email") != settings.task_invoker_email or claims.get("email_verified") is not True
                    or type(claims.get("exp")) not in (int, float) or not now < claims["exp"] <= now + 3700
                    or type(claims.get("iat")) not in (int, float) or not now - 3700 <= claims["iat"] <= now + 30):
                raise ValueError("Wrong invoker")
        except Exception:
            return failure("invoker_denied", 401)
        try:
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                return failure("invalid_media_type", 415)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BODY:
                    return failure("invalid_delivery", 413)
                chunks.append(chunk)
            body = b"".join(chunks)
            payload = json.loads(body.decode("utf-8"), object_pairs_hook=_unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite")))
            if request.url.path.endswith("/dispatch"):
                if payload != {"version": "research-cloud-dispatch-v1"}:
                    raise ValueError("Exact dispatch request required")
                from api.v1_beta_question_services import dispatch_pending_questions
                from types import SimpleNamespace
                complete = await run_in_threadpool(dispatch_pending_questions,
                    SimpleNamespace(research_run_service=runs, research_answer_service=answers))
                if not complete:
                    return failure("dispatch_unavailable", 503)
                return JSONResponse({"status": "dispatched"}, headers={"Cache-Control": "no-store"})
            kind = "run" if request.url.path.endswith("/run") else "answer"
            key = "run_id" if kind == "run" else "job_id"
            if type(payload) is not dict or payload != delivery_body(kind, payload.get(key), payload.get("delivery_id")):
                raise ValueError("Exact delivery binding required")
        except Exception:
            return failure("invalid_delivery", 422)
        try:
            service = runs if kind == "run" else answers
            # No task-supplied owner, question, model or scientific inputs enter
            # execution. C20/C21 reload them from the current durable authority.
            outcome = await run_in_threadpool(service.execute_delivery,
                **{key: payload[key], "delivery_id": payload["delivery_id"]})
            status = outcome["run" if kind == "run" else "job"]["status"]
            if status in {"queued", "running"}:
                # A duplicate can arrive while an older lease still runs. Do
                # not ACK/delete its task before that lease has published a
                # terminal/wait outcome; otherwise a crash can strand the run.
                return failure("delivery_in_progress", 503)
        except Exception:
            # A retry retains the exact delivery identity and C20/C21 lease fence.
            return failure("delivery_unavailable", 503)
        return JSONResponse({"status": "processed"}, headers={"Cache-Control": "no-store"})

    return app


def create_from_environment():
    """Production factory with the same explicit, source-bound beta composition.

    The private service is never mounted in the public host. No queue polling or
    provider calls start at import, startup or health checks.
    """
    import os
    from api.v1_host import HostConfigurationError, create_from_environment as create_api
    if os.environ.get("OCEAN_V1_CATALOGUE_MODE") != "sealed-gcs-research-v1":
        raise HostConfigurationError("Explicit private beta research mode required")
    host = create_api()
    try:
        services = host.state.v1_services
        return create_controller_app(settings=services.cloud_settings, runs=services.research_run_service,
            answers=services.research_answer_service, owned_engine=host.state.v1_owned_engine)
    except Exception:
        host.state.v1_owned_engine.dispose()
        raise HostConfigurationError("Private beta research host unavailable") from None
