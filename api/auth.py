"""Invite-only authentication and role-based authorization.

The browser authenticates with OIDC through the Next.js application. Next.js
then mints a very short-lived internal JWT for the FastAPI service. FastAPI
verifies that token and resolves role/status from PostgreSQL on every request,
so suspensions and role changes take effect immediately.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, FrozenSet, Mapping, Optional

import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import config
from db.app_models import AppUser, AuditEvent, UserInvitation
from db.connection import get_session


logger = logging.getLogger(__name__)

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "viewer": frozenset(
        {
            "profile:read",
            "overview:read",
            "chat:use",
            "feedback:write",
            "evidence:search",
        }
    ),
    "researcher": frozenset(
        {
            "profile:read",
            "overview:read",
            "chat:use",
            "feedback:write",
            "evidence:search",
            "data:read",
            "data:export",
            "provenance:read",
            "evaluation:read",
            "evaluation:run",
        }
    ),
    "admin": frozenset(
        {
            "profile:read",
            "overview:read",
            "chat:use",
            "feedback:write",
            "feedback:review",
            "feedback:export",
            "evidence:search",
            "data:read",
            "data:export",
            "provenance:read",
            "evaluation:read",
            "evaluation:run",
            "pipeline:read",
            "pipeline:execute",
            "database:read",
            "database:query",
            "system:read",
            "users:manage",
        }
    ),
}

VALID_ROLES = frozenset(ROLE_PERMISSIONS)
VALID_ACCOUNT_TYPES = frozenset({"research", "commercial", "internal"})
VALID_USER_STATUSES = frozenset({"active", "suspended"})


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    display_name: Optional[str]
    role: str
    account_type: str
    status: str
    permissions: FrozenSet[str]
    auth_provider: str


class AuthenticationFailure(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if (
        len(email) > 320
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        raise ValueError("A valid email address is required")
    return email


def permissions_for_role(role: str) -> FrozenSet[str]:
    try:
        return ROLE_PERMISSIONS[role]
    except KeyError as exc:
        raise ValueError(f"Unknown role: {role}") from exc


def current_user_from_model(user: AppUser) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        account_type=user.account_type,
        status=user.status,
        permissions=permissions_for_role(user.role),
        auth_provider=user.auth_provider,
    )


def _disabled_mode_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.UUID(int=0),
        email="local-admin@invalid.test",
        display_name="Local development admin",
        role="admin",
        account_type="internal",
        status="active",
        permissions=ROLE_PERMISSIONS["admin"],
        auth_provider="disabled",
    )


def decode_internal_token(token: str) -> Mapping[str, Any]:
    secret = os.environ.get("INTERNAL_AUTH_SECRET", config.INTERNAL_AUTH_SECRET)
    if len(secret) < 32:
        raise AuthenticationFailure(
            503,
            "Authentication is not configured: INTERNAL_AUTH_SECRET must be at least 32 characters",
        )
    issuer = os.environ.get("INTERNAL_AUTH_ISSUER", config.INTERNAL_AUTH_ISSUER)
    audience = os.environ.get(
        "INTERNAL_AUTH_AUDIENCE",
        config.INTERNAL_AUTH_AUDIENCE,
    )
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=audience,
            issuer=issuer,
            options={
                "require": [
                    "exp",
                    "iat",
                    "iss",
                    "aud",
                    "sub",
                    "email",
                    "provider",
                    "email_verified",
                ]
            },
        )
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if (
            not isinstance(issued_at, (int, float))
            or not isinstance(expires_at, (int, float))
            or expires_at <= issued_at
            or expires_at - issued_at > 120
        ):
            raise AuthenticationFailure(
                401,
                "Invalid or expired identity token",
            )
        return claims
    except AuthenticationFailure:
        raise
    except jwt.PyJWTError as exc:
        raise AuthenticationFailure(401, "Invalid or expired identity token") from exc


def resolve_identity(session: Session, claims: Mapping[str, Any]) -> CurrentUser:
    if claims.get("email_verified") is not True:
        raise AuthenticationFailure(403, "A verified provider email is required")

    provider = str(claims.get("provider") or "").strip()
    subject = str(claims.get("sub") or "").strip()
    if not provider or not subject:
        raise AuthenticationFailure(401, "Identity token is missing its provider subject")
    if len(provider) > 64 or len(subject) > 255:
        raise AuthenticationFailure(401, "Identity token provider subject is invalid")
    try:
        email = normalize_email(str(claims.get("email") or ""))
    except ValueError as exc:
        raise AuthenticationFailure(401, str(exc)) from exc
    display_name = str(claims.get("name") or "").strip()[:255] or None
    now = datetime.now(timezone.utc)

    user = session.scalar(
        select(AppUser).where(
            AppUser.auth_provider == provider,
            AppUser.auth_subject == subject,
        )
    )
    if user is not None:
        if user.email != email:
            raise AuthenticationFailure(
                403,
                "The provider email no longer matches this account",
            )
        if user.status != "active":
            raise AuthenticationFailure(403, "This account is suspended")
        user.display_name = display_name or user.display_name
        last_login_at = user.last_login_at
        if last_login_at is not None and last_login_at.tzinfo is None:
            last_login_at = last_login_at.replace(tzinfo=timezone.utc)
        if (
            last_login_at is None
            or (now - last_login_at).total_seconds() >= 15 * 60
        ):
            user.last_login_at = now
        return current_user_from_model(user)

    email_owner = session.scalar(select(AppUser).where(AppUser.email == email))
    if email_owner is not None:
        raise AuthenticationFailure(
            403,
            "This email is already linked to another provider identity",
        )

    invitation = session.scalar(
        select(UserInvitation).where(UserInvitation.email == email)
    )
    if invitation is None or invitation.status != "pending":
        raise AuthenticationFailure(403, "This account has not been invited")
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise AuthenticationFailure(403, "This invitation has expired")

    user = AppUser(
        auth_provider=provider,
        auth_subject=subject,
        email=email,
        display_name=display_name,
        role=invitation.role,
        account_type=invitation.account_type,
        status="active",
        invited_by_user_id=invitation.invited_by_user_id,
        last_login_at=now,
    )
    session.add(user)
    session.flush()
    invitation.status = "accepted"
    invitation.accepted_at = now
    session.add(
        AuditEvent(
            actor_user_id=user.id,
            action="auth.invitation_accepted",
            target_type="user",
            target_id=str(user.id),
            metadata_json={
                "provider": provider,
                "invitation_id": str(invitation.id),
            },
        )
    )
    return current_user_from_model(user)


def authenticate_request(request: Request) -> CurrentUser:
    try:
        config.validate_security_configuration()
    except config.SecurityConfigurationError as exc:
        logger.error("Unsafe authentication configuration rejected: %s", exc)
        raise AuthenticationFailure(
            503,
            "Authentication security configuration is invalid",
        ) from exc

    auth_mode = os.environ.get("AUTH_MODE", config.AUTH_MODE).strip().lower()
    if auth_mode == "disabled":
        return _disabled_mode_user()
    if auth_mode != "required":
        raise AuthenticationFailure(503, f"Unsupported AUTH_MODE: {auth_mode}")

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token:
        raise AuthenticationFailure(401, "Authentication required")
    if len(token) > 8192:
        raise AuthenticationFailure(401, "Invalid identity token")

    claims = decode_internal_token(token)
    try:
        with get_session() as session:
            return resolve_identity(session, claims)
    except AuthenticationFailure:
        raise
    except SQLAlchemyError as exc:
        logger.exception("Authentication database lookup failed")
        raise AuthenticationFailure(
            503,
            "Authentication database is unavailable",
        ) from exc


def route_permission(method: str, path: str) -> Optional[str]:
    """Return the permission required for a known API route.

    ``None`` means no authorization policy matched and is denied by default.
    """
    method = method.upper()
    if path == "/me":
        return "profile:read"
    if path in {"/health", "/stats"}:
        return "overview:read"
    if path == "/models":
        return "chat:use"
    if path == "/chat" and method == "POST":
        return "chat:use"
    if path.startswith("/chat/interactions/"):
        return "feedback:write"
    if path == "/retrieve" or path == "/documents":
        return "evidence:search"
    if path.startswith("/data/") or path == "/analysis":
        return "data:read"
    if path.startswith("/explore/"):
        return "data:read"
    if path.startswith("/provenance/"):
        return "provenance:read"
    if path.startswith("/evaluation/"):
        return "evaluation:run" if method == "POST" else "evaluation:read"
    if path.startswith("/pipeline/"):
        return "pipeline:execute" if method == "POST" else "pipeline:read"
    if path.startswith("/database/"):
        return "database:query" if method == "POST" else "database:read"
    if path == "/debug":
        return "system:read"
    if path.startswith("/admin/users") or path.startswith("/admin/invitations"):
        return "users:manage"
    if path == "/admin/feedback/export":
        return "feedback:export"
    if path.startswith("/admin/feedback"):
        return "feedback:review"
    if path.startswith("/docs") or path in {"/redoc", "/openapi.json"}:
        return "system:read"
    return None


async def authorization_middleware(
    request: Request,
    call_next: Callable[..., Any],
):
    if request.method == "OPTIONS" or request.url.path == "/health/live":
        return await call_next(request)

    try:
        user = authenticate_request(request)
        permission = route_permission(request.method, request.url.path)
        if permission is None:
            raise AuthenticationFailure(403, "Access to this route is denied")
        if permission not in user.permissions:
            raise AuthenticationFailure(
                403,
                f"Permission required: {permission}",
            )
        request.state.current_user = user
        return await call_next(request)
    except AuthenticationFailure as exc:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else {}
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )


def get_current_user(request: Request) -> CurrentUser:
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
