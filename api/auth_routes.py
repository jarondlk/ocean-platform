"""Authenticated profile, invitation, and user administration routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.auth import (
    CurrentUser,
    VALID_ACCOUNT_TYPES,
    VALID_ROLES,
    VALID_USER_STATUSES,
    get_current_user,
    normalize_email,
)
from api.schemas import (
    CurrentUserResponse,
    InvitationCreate,
    InvitationResponse,
    UserSummary,
    UserUpdate,
)
from db.app_models import AppUser, AuditEvent, UserInvitation
from db.connection import get_session


router = APIRouter()


def _user_response(user: AppUser) -> UserSummary:
    return UserSummary(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        account_type=user.account_type,
        status=user.status,
        auth_provider=user.auth_provider,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _invitation_response(invitation: UserInvitation) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        account_type=invitation.account_type,
        status=invitation.status,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        created_at=invitation.created_at,
    )


@router.get("/me", response_model=CurrentUserResponse)
def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        account_type=user.account_type,
        status=user.status,
        permissions=sorted(user.permissions),
    )


@router.get("/admin/users", response_model=List[UserSummary])
def list_users(
    limit: int = Query(default=100, ge=1, le=500),
    _actor: CurrentUser = Depends(get_current_user),
) -> List[UserSummary]:
    with get_session() as session:
        users = session.scalars(
            select(AppUser).order_by(AppUser.created_at.desc()).limit(limit)
        ).all()
        return [_user_response(user) for user in users]


@router.patch("/admin/users/{user_id}", response_model=UserSummary)
def update_user(
    user_id: uuid.UUID,
    request: UserUpdate,
    actor: CurrentUser = Depends(get_current_user),
) -> UserSummary:
    if request.role is not None and request.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Unknown role")
    if (
        request.account_type is not None
        and request.account_type not in VALID_ACCOUNT_TYPES
    ):
        raise HTTPException(status_code=422, detail="Unknown account type")
    if request.status is not None and request.status not in VALID_USER_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown user status")
    if user_id == actor.id and (
        (request.role is not None and request.role != "admin")
        or request.status == "suspended"
    ):
        raise HTTPException(
            status_code=400,
            detail="Administrators cannot demote or suspend their own account",
        )

    with get_session() as session:
        user = session.get(AppUser, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        changes = {}
        for field in ("role", "account_type", "status"):
            value = getattr(request, field)
            if value is not None and value != getattr(user, field):
                changes[field] = {"from": getattr(user, field), "to": value}
                setattr(user, field, value)
        if changes:
            session.add(
                AuditEvent(
                    actor_user_id=(
                        actor.id if actor.auth_provider != "disabled" else None
                    ),
                    action="admin.user_updated",
                    target_type="user",
                    target_id=str(user.id),
                    metadata_json={"changes": changes},
                )
            )
        session.flush()
        return _user_response(user)


@router.get("/admin/invitations", response_model=List[InvitationResponse])
def list_invitations(
    limit: int = Query(default=100, ge=1, le=500),
    _actor: CurrentUser = Depends(get_current_user),
) -> List[InvitationResponse]:
    with get_session() as session:
        invitations = session.scalars(
            select(UserInvitation)
            .order_by(UserInvitation.created_at.desc())
            .limit(limit)
        ).all()
        return [_invitation_response(invitation) for invitation in invitations]


@router.post(
    "/admin/invitations",
    response_model=InvitationResponse,
    status_code=201,
)
def create_invitation(
    request: InvitationCreate,
    actor: CurrentUser = Depends(get_current_user),
) -> InvitationResponse:
    try:
        email = normalize_email(request.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if request.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Unknown role")
    if request.account_type not in VALID_ACCOUNT_TYPES:
        raise HTTPException(status_code=422, detail="Unknown account type")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=request.expires_in_days)
    with get_session() as session:
        if session.scalar(select(AppUser).where(AppUser.email == email)):
            raise HTTPException(
                status_code=409,
                detail="A user with this email already exists",
            )
        invitation = session.scalar(
            select(UserInvitation).where(UserInvitation.email == email)
        )
        if invitation is not None and invitation.status == "accepted":
            raise HTTPException(
                status_code=409,
                detail="This invitation has already been accepted",
            )
        if invitation is None:
            invitation = UserInvitation(email=email)
            session.add(invitation)
        invitation.role = request.role
        invitation.account_type = request.account_type
        invitation.status = "pending"
        invitation.invited_by_user_id = (
            actor.id if actor.auth_provider != "disabled" else None
        )
        invitation.expires_at = expires_at
        invitation.accepted_at = None
        session.flush()
        session.add(
            AuditEvent(
                actor_user_id=(
                    actor.id if actor.auth_provider != "disabled" else None
                ),
                action="admin.invitation_created",
                target_type="invitation",
                target_id=str(invitation.id),
                metadata_json={
                    "email": email,
                    "role": request.role,
                    "account_type": request.account_type,
                },
            )
        )
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="An invitation for this email already exists",
            ) from exc
        return _invitation_response(invitation)


@router.post(
    "/admin/invitations/{invitation_id}/revoke",
    response_model=InvitationResponse,
)
def revoke_invitation(
    invitation_id: uuid.UUID,
    actor: CurrentUser = Depends(get_current_user),
) -> InvitationResponse:
    with get_session() as session:
        invitation = session.get(UserInvitation, invitation_id)
        if invitation is None:
            raise HTTPException(status_code=404, detail="Invitation not found")
        if invitation.status == "revoked":
            return _invitation_response(invitation)
        if invitation.status != "pending":
            raise HTTPException(
                status_code=409,
                detail="Only a pending invitation can be revoked",
            )

        invitation.status = "revoked"
        session.add(
            AuditEvent(
                actor_user_id=(
                    actor.id if actor.auth_provider != "disabled" else None
                ),
                action="admin.invitation_revoked",
                target_type="invitation",
                target_id=str(invitation.id),
                metadata_json={"email": invitation.email},
            )
        )
        session.flush()
        return _invitation_response(invitation)
