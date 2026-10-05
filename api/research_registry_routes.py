"""Bounded review endpoints. Application changes only the immutable review ledger."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from api.auth import CurrentUser, get_current_user
from api.classification_review_service import ClassificationReviewDomainError
from api import research_registry_service as service
from db.app_models import ResearchRegistryReview
from db.connection import get_session
from preprocessing.research_recipe import Hash, ResearchModel

router = APIRouter(
    prefix="/research-registry-reviews", tags=["research registry reviews"]
)


class RegistryDraft(ResearchModel):
    kind: Literal["sampling", "sst_product"]
    definition: dict


class RegistryApproval(ResearchModel):
    approve: bool
    version: int = Field(ge=1, le=3)
    content_sha256: Hash
    rationale: str = Field(min_length=1, max_length=4000)


class RegistryApplication(ResearchModel):
    version: int = Field(ge=1, le=3)
    content_sha256: Hash


def call(operation):
    try:
        with get_session() as session:
            return operation(session)
    except ClassificationReviewDomainError as exc:
        raise HTTPException(
            exc.status_code, detail={"code": exc.code, "message": exc.detail}
        ) from exc
    except IntegrityError as exc:
        raise HTTPException(
            409, "Registry transaction conflict; reload the current review"
        ) from exc
    except ValueError as exc:
        raise HTTPException(400, "Invalid research registry definition") from exc


@router.get("")
def catalog(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    actor: CurrentUser = Depends(get_current_user),
):
    def operation(session):
        rows = session.scalars(
            select(ResearchRegistryReview)
            .order_by(ResearchRegistryReview.id)
            .limit(limit)
            .offset(offset)
        )
        return {
            "total": session.scalar(
                select(func.count()).select_from(ResearchRegistryReview)
            ),
            "limit": limit,
            "offset": offset,
            "items": [service.response(row) for row in rows],
        }

    return call(operation)


@router.post("", status_code=201)
def create(request: RegistryDraft, actor: CurrentUser = Depends(get_current_user)):
    return call(
        lambda session: service.create_draft(
            session, kind=request.kind, payload=request.definition, actor=actor
        )
    )


@router.get("/{review_id}")
def detail(review_id: uuid.UUID, actor: CurrentUser = Depends(get_current_user)):
    def operation(session):
        review, events = service.load_review(session, review_id)
        return {
            **service.response(review, details=True),
            "events": [
                {"event_sha256": event.event_sha256, **event.payload_json}
                for event in events
            ],
        }

    return call(operation)


@router.get("/versions/{registry_id}")
def version(registry_id: str, actor: CurrentUser = Depends(get_current_user)):
    return call(lambda session: service.read_registry(session, registry_id))


@router.post("/{review_id}/preview")
def preview(review_id: uuid.UUID, actor: CurrentUser = Depends(get_current_user)):
    def operation(session):
        review, _ = service.load_review(session, review_id)
        return {
            **service.response(review),
            "preview": service.preview_definition(
                session, review.kind, review.definition_json
            ),
        }

    return call(operation)


@router.post("/{review_id}/decision")
def decision(
    review_id: uuid.UUID,
    request: RegistryApproval,
    actor: CurrentUser = Depends(get_current_user),
):
    return call(
        lambda session: service.decide(
            session, review_id, actor=actor, **request.model_dump()
        )
    )


@router.post("/{review_id}/apply")
def apply(
    review_id: uuid.UUID,
    request: RegistryApplication,
    actor: CurrentUser = Depends(get_current_user),
):
    return call(
        lambda session: service.apply(
            session, review_id, actor=actor, **request.model_dump()
        )
    )
