"""Explicit beta Cloud Tasks transport; no questions or credentials in tasks.

The durable C20/C21 outboxes own retries. A lost create acknowledgement uses the
same hashed task name; a conflict is accepted only after the retained task's
target, identity and body are read back. A tombstone is not delivery proof.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Literal
from urllib.parse import urlsplit
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROJECT = "ocean-v1-beta-20261101"
REGION = "asia-northeast1"
KINDS = {"run": ("run_id", "/internal/research/run"),
         "answer": ("job_id", "/internal/research/answer")}


class CloudDispatchError(RuntimeError):
    def __init__(self):
        super().__init__("Beta research task delivery is unavailable")


class CloudResearchSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    version: Literal["ocean-v1-beta-research-cloud-v1"]
    project_id: Literal["ocean-v1-beta-20261101"]
    region: Literal["asia-northeast1"]
    queue_id: Literal["ocean-v1-beta-research"]
    controller_origin: str
    task_invoker_email: Literal["ocean-v1-beta-task-invoker@ocean-v1-beta-20261101.iam.gserviceaccount.com"]
    task_invoker_subject: str = Field(pattern=r"^[0-9]{10,30}$")

    @model_validator(mode="after")
    def isolated_target(self):
        u = urlsplit(self.controller_origin)
        if (u.scheme != "https" or u.username or u.password or u.port
                or u.path or u.query or u.fragment or not u.hostname
                or not re.fullmatch(r"(?:ocean-v1-beta-research-[a-z0-9-]+\.a\.run\.app|ocean-v1-beta-research-[a-z0-9-]+-534831104543\.asia-northeast1\.run\.app)", u.hostname)
                or self.controller_origin != "https://" + u.hostname):
            raise ValueError("Exact private beta controller origin required")
        return self

    @property
    def queue_path(self):
        return f"projects/{self.project_id}/locations/{self.region}/queues/{self.queue_id}"


def delivery_body(kind, identity, delivery_id):
    if kind not in KINDS:
        raise ValueError("Unknown research delivery kind")
    for value in (identity, delivery_id):
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError("Canonical delivery UUID required")
    return {"version": "research-cloud-delivery-v1", KINDS[kind][0]: identity,
            "delivery_id": delivery_id}


class CloudResearchQueue:
    def __init__(self, *, settings, kind, session=None):
        if not isinstance(settings, CloudResearchSettings) or kind not in KINDS:
            raise ValueError("Explicit beta queue binding required")
        self.settings, self.kind, self._session = settings, kind, session

    def _transport(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            self._session = AuthorizedSession(credentials)
        return self._session

    def task(self, *, delivery_id, run_id=None, job_id=None):
        identity = run_id if self.kind == "run" else job_id
        if (job_id is not None if self.kind == "run" else run_id is not None):
            raise ValueError("Delivery kind mismatch")
        body = delivery_body(self.kind, identity, delivery_id)
        digest = hashlib.sha256((self.kind + ":" + identity + ":" + delivery_id).encode()).hexdigest()
        return {"name": self.settings.queue_path + "/tasks/research-" + digest,
            "dispatchDeadline": "240s", "httpRequest": {
                "httpMethod": "POST", "url": self.settings.controller_origin + KINDS[self.kind][1],
                "headers": {"Content-Type": "application/json"},
                "body": base64.b64encode(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).decode(),
                "oidcToken": {"serviceAccountEmail": self.settings.task_invoker_email,
                              "audience": self.settings.controller_origin}}}

    def enqueue(self, **address):
        task = self.task(**address)
        try:
            session = self._transport()
            response = session.post("https://cloudtasks.googleapis.com/v2/" + self.settings.queue_path + "/tasks",
                json={"task": task}, timeout=10, allow_redirects=False)
            if response.status_code in {200, 201}:
                if response.json().get("name") != task["name"]:
                    raise CloudDispatchError()
                return
            if response.status_code != 409:
                raise CloudDispatchError()
            existing = session.get("https://cloudtasks.googleapis.com/v2/" + task["name"],
                params={"responseView": "FULL"}, timeout=10, allow_redirects=False)
            if existing.status_code != 200:
                raise CloudDispatchError()
            observed = existing.json()
            request = observed.get("httpRequest", {})
            expected = task["httpRequest"]
            if (observed.get("name") != task["name"]
                    or observed.get("dispatchDeadline") != task["dispatchDeadline"]
                    or any(request.get(k) != expected[k] for k in ("url", "httpMethod", "body", "oidcToken"))
                    or {k.lower(): v for k, v in request.get("headers", {}).items()}.get("content-type") != "application/json"):
                raise CloudDispatchError()
        except Exception:
            raise CloudDispatchError() from None


def accepted_delivery_background(service, identity):
    """Nudge only the accepted mutation's own outbox after its response commits.

    Other users' pending or revoked rows cannot delay this question. The private
    scheduled sweep retries transport failures; it uses the original delivery ID.
    """
    if not isinstance(getattr(service, "queue", None), CloudResearchQueue):
        return None
    from starlette.background import BackgroundTask

    def dispatch():
        key = "run_id" if service.queue.kind == "run" else "job_id"
        try:
            service.dispatch_outbox(limit=1, **{key: identity})
        except Exception:
            # Keep the authoritative outbox pending; private SQL/provider details
            # never enter the successful mutation response or application log.
            pass

    return BackgroundTask(dispatch)
