import logging
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select

from app.database import DbSession
from app.models.body_styling import BodyStyleRecommendation
from app.models.item import ClothingItem
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
from app.schemas.styling_profile import (
    Budget,
    DressCode,
    StyleId,
    StylingProfile,
    styling_revision,
)
from app.services.body_style_packing import MAX_DAYS, build_packing
from app.services.body_style_today import build_today, explain_today
from app.services.body_styling_service import (
    ai_status,
    create_pending_style,
    enqueue_style_job,
    generate_rule_based_style,
    recent_style_feedback,
    user_endpoints,
)
from app.services.style_explore import explore_result, round_one, round_two
from app.services.wardrobe_matching import wardrobe_match
from app.services.weather_service import WeatherService
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
    request: BodyStyleRequest, response: Response, db: DbSession, current_user: CurrentUser
):
    """Rule-based reports return at once (201); AI reports are queued (202) and polled."""
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
    use_ai = request.mode == "ai" or (request.mode == "auto" and state["available"])
    if use_ai and not state["available"]:
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
    feedback = await recent_style_feedback(db, current_user.id)
    if not use_ai:
        return await generate_rule_based_style(db, current_user, measurements, request, feedback)
    record = await create_pending_style(db, current_user, measurements, request, feedback)
    # Commit before enqueuing: the worker reads the row on its own connection.
    await db.commit()
    try:
        record.job_id = await enqueue_style_job(record.id)
    except Exception:
        logger.error("Failed to queue body styling generation")
        record.status, record.error_code = "failed", "queue_failed"
    await db.commit()
    await db.refresh(record)
    response.status_code = 202
    return record


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
                summary=r.result["summary"] if r.result else None,
                context=r.input_snapshot["context"],
                mode=r.input_snapshot.get("mode", "ai"),
                status=r.status,
                error_code=r.error_code,
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
    if record.status != "pending" and record.seen_at is None:
        record.seen_at = datetime.now(UTC)
        await db.flush()
    return record


@router.get("/unread")
async def unread(db: DbSession, current_user: CurrentUser) -> dict[str, int]:
    """Finished background reports the user has not opened yet, and those still running."""
    own = BodyStyleRecommendation.user_id == current_user.id
    rows = (
        await db.execute(
            select(BodyStyleRecommendation.status, func.count())
            .where(own, BodyStyleRecommendation.seen_at.is_(None))
            .group_by(BodyStyleRecommendation.status)
        )
    ).all()
    counts = dict(rows)
    return {
        "unread": counts.get("done", 0) + counts.get("failed", 0),
        "pending": counts.get("pending", 0),
    }


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
    if record.status != "done":
        raise error(409, "report_not_ready", "Feedback is only possible on a finished report.")
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


@router.delete("/recommendations/{recommendation_id}", status_code=204)
async def delete_recommendation(
    recommendation_id: UUID, db: DbSession, current_user: CurrentUser
) -> None:
    record = await db.scalar(
        select(BodyStyleRecommendation).where(
            BodyStyleRecommendation.id == recommendation_id,
            BodyStyleRecommendation.user_id == current_user.id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    await db.delete(record)
    await db.flush()


Occasion = Literal["daily", "work", "date", "weekend", "formal"]
Style = Literal["minimal", "smart_casual", "street", "sporty", "classic"]


def public_today(today: dict) -> dict:
    return {key: value for key, value in today.items() if not key.startswith("_")}


@router.get("/today")
async def today_outfit(
    db: DbSession,
    current_user: CurrentUser,
    occasion: Occasion | None = None,
    style: Style | None = None,
    reroll: int = Query(0, ge=0, le=50),
) -> dict:
    """A rule-based look for today; no AI call, so it is instant and free."""
    return public_today(await build_today(db, current_user, occasion, style, reroll))


@router.post("/today/explain")
async def explain_today_outfit(
    db: DbSession,
    current_user: CurrentUser,
    occasion: Occasion | None = None,
    style: Style | None = None,
    reroll: int = Query(0, ge=0, le=50),
) -> dict[str, str]:
    endpoints = await user_endpoints(db, current_user)
    if not ai_status(endpoints)["available"]:
        raise error(503, "ai_unavailable", "Enable and configure a text AI service first.")
    await check_rate_limit(f"body_styling_today:{current_user.id}", limit=10, window_seconds=60)
    today = await build_today(db, current_user, occasion, style, reroll)
    try:
        text = await explain_today(today, endpoints, current_user.locale)
    except Exception:
        logger.warning("Today's outfit explanation failed for the configured AI service")
        raise error(502, "ai_failed", "The AI could not explain this look. Try again.") from None
    return {"text": text}


@router.get("/recommendations/{recommendation_id}/wardrobe-match")
async def recommendation_wardrobe_match(
    recommendation_id: UUID, db: DbSession, current_user: CurrentUser
) -> dict:
    record = await db.scalar(
        select(BodyStyleRecommendation).where(
            BodyStyleRecommendation.id == recommendation_id,
            BodyStyleRecommendation.user_id == current_user.id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if record.status != "done":
        raise error(409, "report_not_ready", "The report is not finished yet.")
    items = (
        await db.scalars(
            select(ClothingItem).where(
                ClothingItem.user_id == current_user.id,
                ClothingItem.is_archived.is_(False),
            )
        )
    ).all()
    profile = StylingProfile.model_validate(record.input_snapshot.get("styling_profile") or {})
    return wardrobe_match(record.result, list(items), profile)


class PackingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    occasions: list[Occasion] = Field(default_factory=lambda: ["daily"], min_length=1, max_length=7)
    style: Style = "minimal"
    # Destination; omitted means the saved home location (or none, using calendar seasons).
    city: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def check_dates(self):
        days = (self.end_date - self.start_date).days + 1
        if days < 1 or days > MAX_DAYS:
            raise ValueError(f"the trip must last between 1 and {MAX_DAYS} days")
        return self


@router.post("/packing")
async def packing_list(data: PackingRequest, db: DbSession, current_user: CurrentUser) -> dict:
    """Computed packing list for a trip; no AI involved."""
    location = None
    if data.city:
        location = await WeatherService().geocode_location_name(data.city)
        if location is None:
            raise error(422, "unknown_city", "That city could not be found.")
    elif current_user.location_lat is not None and current_user.location_lon is not None:
        location = (
            float(current_user.location_lat),
            float(current_user.location_lon),
            current_user.location_name,
        )
    items = (
        await db.scalars(
            select(ClothingItem).where(
                ClothingItem.user_id == current_user.id,
                ClothingItem.is_archived.is_(False),
            )
        )
    ).all()
    return await build_packing(
        current_user,
        data.start_date,
        data.end_date,
        list(data.occasions),
        data.style,
        location,
        list(items),
    )


AnswerValue = Literal["like", "neutral", "dislike"]


class StyleAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, AnswerValue] = Field(max_length=40)
    # Lifestyle answers shown on the result page; when left out, the saved ones are used.
    dress_code: DressCode | None = None
    budget: Budget | None = None


class StyleChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    styles: list[StyleId] = Field(min_length=1, max_length=2)
    dress_code: DressCode | None = None
    budget: Budget | None = None


def current_profile(user: User) -> StylingProfile:
    return StylingProfile.model_validate(user.styling_profile or {})


def zh_locale(user: User) -> bool:
    return (user.locale or "").startswith("zh")


@router.get("/style-explore/round-one")
async def style_round_one(current_user: CurrentUser) -> dict:
    cards = round_one(current_user.id, current_profile(current_user), zh_locale(current_user))
    return {"cards": cards}


@router.post("/style-explore/round-two")
async def style_round_two(data: StyleAnswers, current_user: CurrentUser) -> dict:
    profile = current_profile(current_user)
    return {"cards": round_two(current_user.id, profile, zh_locale(current_user), data.answers)}


@router.post("/style-explore/result")
async def style_result(data: StyleAnswers, db: DbSession, current_user: CurrentUser) -> dict:
    try:
        measurements = BodyMeasurements.model_validate(current_user.body_measurements or {})
    except ValidationError:
        measurements = None
    items = (
        await db.scalars(
            select(ClothingItem).where(
                ClothingItem.user_id == current_user.id, ClothingItem.is_archived.is_(False)
            )
        )
    ).all()
    profile = current_profile(current_user)
    profile.dress_code = data.dress_code or profile.dress_code
    profile.budget = data.budget or profile.budget
    return explore_result(
        data.answers,
        profile,
        measurements,
        list(items),
        zh_locale(current_user),
    )


@router.patch("/style-explore/styles")
async def save_preferred_styles(
    data: StyleChoice, db: DbSession, current_user: CurrentUser
) -> dict:
    """Save the quiz result as the profile's style direction."""
    await db.refresh(current_user, with_for_update=True)
    profile = current_profile(current_user)
    profile.preferred_styles = list(dict.fromkeys(data.styles))
    profile.dress_code = data.dress_code or profile.dress_code
    profile.budget = data.budget or profile.budget
    current_user.styling_profile = profile.model_dump(exclude_none=True)
    await db.flush()
    return {
        "preferred_styles": profile.preferred_styles,
        "dress_code": profile.dress_code,
        "budget": profile.budget,
        "styling_profile_revision": styling_revision(
            current_user.body_measurements, current_user.styling_profile
        ),
    }
