"""Authenticated scientific decision and operational application routes."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import CurrentUser, get_current_user
from api.classification_review_service import (
    ClassificationReviewDomainError,
    create_draft,
    decide_review,
    get_review,
    list_reviews,
    preview_review,
    record_application,
    update_draft,
)
from api.schemas import (
    ClassificationReviewApplicationRequest,
    ClassificationReviewDecisionRequest,
    ClassificationReviewDraftCreate,
    ClassificationReviewDraftUpdate,
    ClassificationReviewListResponse,
    ClassificationReviewPreviewRequest,
    ClassificationReviewPreviewResponse,
    ClassificationReviewResponse,
)
from db.connection import get_session


router = APIRouter(prefix="/classification-reviews", tags=["classification reviews"])


def _as_http_error(exc: ClassificationReviewDomainError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.detail},
    )


@router.get("", response_model=ClassificationReviewListResponse)
def classification_reviews(
    sample_id: Optional[str] = Query(default=None, pattern=r"^[a-f0-9]{64}$"),
    state: Optional[Literal[
        "draft", "approved", "rejected", "superseded", "applied", "failed"
    ]] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    _actor: CurrentUser = Depends(get_current_user),
) -> ClassificationReviewListResponse:
    try:
        with get_session() as session:
            items, total = list_reviews(
                session,
                sample_id=sample_id,
                state=state,
                limit=limit,
                offset=offset,
            )
            return ClassificationReviewListResponse(
                items=items,
                total=total,
                limit=limit,
                offset=offset,
            )
    except ClassificationReviewDomainError as exc:
        raise _as_http_error(exc) from exc


@router.post("", response_model=ClassificationReviewResponse, status_code=201)
def create_classification_review(
    request: ClassificationReviewDraftCreate,
    actor: CurrentUser = Depends(get_current_user),
) -> ClassificationReviewResponse:
    try:
        with get_session() as session:
            return create_draft(session, request=request, actor=actor)
    except ClassificationReviewDomainError as exc:
        raise _as_http_error(exc) from exc


@router.get("/{review_id}", response_model=ClassificationReviewResponse)
def classification_review(
    review_id: uuid.UUID,
    _actor: CurrentUser = Depends(get_current_user),
) -> ClassificationReviewResponse:
    try:
        with get_session() as session:
            return get_review(session, review_id)
    except ClassificationReviewDomainError as exc:
        raise _as_http_error(exc) from exc


@router.put("/{review_id}/draft", response_model=ClassificationReviewResponse)
def replace_classification_review_draft(
    review_id: uuid.UUID,
    request: ClassificationReviewDraftUpdate,
    actor: CurrentUser = Depends(get_current_user),
) -> ClassificationReviewResponse:
    try:
        with get_session() as session:
            return update_draft(
                session,
                review_id=review_id,
                request=request,
                actor=actor,
            )
    except ClassificationReviewDomainError as exc:
        raise _as_http_error(exc) from exc


@router.post("/{review_id}/decision", response_model=ClassificationReviewResponse)
def submit_classification_review_decision(
    review_id: uuid.UUID,
    request: ClassificationReviewDecisionRequest,
    actor: CurrentUser = Depends(get_current_user),
) -> ClassificationReviewResponse:
    try:
        with get_session() as session:
            return decide_review(
                session,
                review_id=review_id,
                request=request,
                actor=actor,
            )
    except ClassificationReviewDomainError as exc:
        raise _as_http_error(exc) from exc


@router.post(
    "/{review_id}/preview",
    response_model=ClassificationReviewPreviewResponse,
)
def preview_classification_review(
    review_id: uuid.UUID,
    request: ClassificationReviewPreviewRequest,
    actor: CurrentUser = Depends(get_current_user),
) -> ClassificationReviewPreviewResponse:
    try:
        with get_session() as session:
            return preview_review(
                session,
                review_id=review_id,
                request=request,
                actor=actor,
            )
    except ClassificationReviewDomainError as exc:
        raise _as_http_error(exc) from exc


@router.post("/{review_id}/application", response_model=ClassificationReviewResponse)
def record_classification_review_application(
    review_id: uuid.UUID,
    request: ClassificationReviewApplicationRequest,
    actor: CurrentUser = Depends(get_current_user),
) -> ClassificationReviewResponse:
    try:
        with get_session() as session:
            return record_application(
                session,
                review_id=review_id,
                request=request,
                actor=actor,
            )
    except ClassificationReviewDomainError as exc:
        raise _as_http_error(exc) from exc
