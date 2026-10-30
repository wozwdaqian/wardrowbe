import logging
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select

from app.database import DbSession
from app.models.body_styling import BodyStyleRecommendation
from app.models.user import User
from app.schemas.body_styling import (
    BodyMeasurements,
    BodyStyleHistory,
    BodyStyleHistoryEntry,
    BodyStyleRequest,
    BodyStyleResponse,
    OutfitFeedback,
    ReportFeedback,
)
from app.schemas.styling_profile import styling_revision
from app.services.body_styling_service import (
    InvalidStyleResponse,
    ai_status,
    generate_body_style,
    recent_style_feedback,
    user_endpoints,
)
from app.utils.auth import get_current_user
from app.utils.body_measurements import body_revision
from app.utils.rate_limit import check_rate_limit

router = APIRouter(prefix="/body-styling", tags=["Body styling"])
logger = logging.getLogger(__name__)
CurrentUser = Annotated[User, Depends(get_current_user)]


def error(status: int, code: str, message: str):
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/status")
async def status(db: DbSession, current_user: CurrentUser) -> dict[str, bool]:
    return ai_status(await user_endpoints(db, current_user))


@router.post("/recommendations", response_model=BodyStyleResponse, status_code=201)
async def create_recommendation(
    request: BodyStyleRequest, db: DbSession, current_user: CurrentUser
):
    if (
        request.styling_profile_revision is not None
        and request.styling_profile_revision
        != styling_revision(current_user.body_measurements, current_user.styling_profile)
    ):
        raise error(
            409, "body_measurements_conflict", "Styling profile changed. Reload before generating."
        )
    if request.body_measurements_revision is not None and (
        request.body_measurements_revision != body_revision(current_user.body_measurements)
    ):
        raise error(
            409,
            "body_measurements_conflict",
            "Body measurements changed. Reload before generating.",
        )
    endpoints = await user_endpoints(db, current_user)
    state = ai_status(endpoints)
    if not state["available"]:
        raise error(
            503,
            "ai_unavailable",
            "Enable and configure a text AI service to generate body styling recommendations.",
        )
    try:
        measurements = BodyMeasurements.model_validate(current_user.body_measurements or {})
    except ValidationError:
        raise error(
            422,
            "invalid_measurements",
            "Save valid height, chest, waist and hips measurements first; inseam must be shorter than height.",
        ) from None
    await check_rate_limit(f"body_styling:{current_user.id}", limit=5, window_seconds=60)
    try:
        feedback = await recent_style_feedback(db, current_user.id)
        return await generate_body_style(
            db, current_user, measurements, request, endpoints, feedback
        )
    except InvalidStyleResponse:
        raise error(
            502,
            "invalid_ai_response",
            "The AI returned an incomplete recommendation. Please try again.",
        ) from None
    except (TimeoutError, httpx.TimeoutException):
        raise error(504, "ai_timeout", "The AI service took too long. Please try again.") from None
    except Exception:
        # Provider errors may include URLs; do not log prompts, body data, credentials or raw replies.
        logger.warning("Body styling generation failed for the configured AI service")
        raise error(
            502,
            "ai_failed",
            "The AI service could not generate a recommendation. Check the service and try again.",
        ) from None


@router.get("/recommendations", response_model=BodyStyleHistory)
async def list_recommendations(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    own = BodyStyleRecommendation.user_id == current_user.id
    total = await db.scalar(select(func.count()).select_from(BodyStyleRecommendation).where(own))
    records = (
        await db.scalars(
            select(BodyStyleRecommendation)
            .where(own)
            .order_by(BodyStyleRecommendation.created_at.desc(), BodyStyleRecommendation.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return BodyStyleHistory(
        items=[
            BodyStyleHistoryEntry(
                id=r.id,
                created_at=r.created_at,
                summary=r.result["summary"],
                context=r.input_snapshot["context"],
            )
            for r in records
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/recommendations/{recommendation_id}", response_model=BodyStyleResponse)
async def get_recommendation(recommendation_id: UUID, db: DbSession, current_user: CurrentUser):
    record = await db.scalar(
        select(BodyStyleRecommendation).where(
            BodyStyleRecommendation.id == recommendation_id,
            BodyStyleRecommendation.user_id == current_user.id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return record


@router.patch("/recommendations/{recommendation_id}/feedback", response_model=ReportFeedback)
async def update_feedback(
    recommendation_id: UUID, data: OutfitFeedback, db: DbSession, current_user: CurrentUser
):
    record = await db.scalar(
        select(BodyStyleRecommendation)
        .where(
            BodyStyleRecommendation.id == recommendation_id,
            BodyStyleRecommendation.user_id == current_user.id,
        )
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    items = [
        item
        for item in (record.feedback or {}).get("outfits", [])
        if item["outfit_index"] != data.outfit_index
    ]
    if data.overall or data.colors or data.fabrics:
        items.append(data.model_dump())
    feedback = ReportFeedback(outfits=sorted(items, key=lambda item: item["outfit_index"]))
    record.feedback = feedback.model_dump() if feedback.outfits else None
    await db.flush()
    return feedback
