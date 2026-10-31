"""The assistant's tools: everything it can read or change, always scoped to one user.

Each tool declares its JSON-schema parameters and one of three kinds:
- read: answered immediately, changes nothing;
- direct: executed immediately and recorded with the data needed to undo it;
- confirm: stored as a pending action with a human-readable summary, applied only after the
  user confirms, and undoable afterwards.
Tools call the same services and validation as the HTTP API. AI configuration, credentials,
account deletion and family management are deliberately not exposed.
"""

import json
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from arq import create_pool
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.assistant import AssistantImage
from app.models.body_styling import BodyStyleRecommendation
from app.models.item import ClothingItem, ItemHistory
from app.models.user import User
from app.schemas.body_styling import (
    BodyMeasurements,
    BodyStyleRequest,
    OutfitFeedback,
    ReportFeedback,
)
from app.schemas.item import ItemCreate
from app.schemas.styling_profile import (
    CATALOG,
    PROFILE_CATALOGS,
    STYLE_DATA,
    StylingProfile,
    styling_revision,
)
from app.services.body_style_editing import (
    EditError,
    garment_index_for,
    regenerate_outfit,
    replace_garment,
    stored_draft_garment,
)
from app.services.body_style_rendering import FACT_NAMES
from app.services.body_style_today import build_today, current_weather
from app.services.body_styling_service import (
    create_pending_style,
    enqueue_style_job,
    generate_rule_based_style,
    recent_style_feedback,
)
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.services.wardrobe_matching import purchase_fit, wardrobe_match
from app.utils.body_measurements import body_revision
from app.utils.garment_vocabulary import COLORS, MATERIALS, TYPES
from app.utils.signed_urls import sign_optional
from app.utils.timezone import get_user_today
from app.workers.queues import TAGGING_QUEUE
from app.workers.settings import get_redis_settings

Kind = Literal["read", "direct", "confirm"]
STYLE_NAMES = {style["id"]: style["name"] for style in STYLE_DATA}
MEASUREMENT_KEYS = (
    "height",
    "chest",
    "waist",
    "hips",
    "weight",
    "inseam",
    "shoulder_width",
    "thigh",
)


class ToolError(ValueError):
    """A problem the model should see and can react to (bad id, rule violation, conflict)."""


@dataclass
class ToolContext:
    db: AsyncSession
    user: User
    endpoints: list[dict]
    ai_available: bool
    # Callbacks run after the tool's transaction commits (e.g. queueing a worker job).
    after_commit: list = dataclass_field(default_factory=list)

    @property
    def zh(self) -> bool:
        return self.user.locale.startswith("zh")

    def text(self, chinese: str, english: str) -> str:
        return chinese if self.zh else english


@dataclass
class Outcome:
    """What a write produced: a result for the model, a summary for the user, undo data."""

    result: dict
    summary: str
    undo: dict | None = None


@dataclass
class Tool:
    name: str
    kind: Kind
    description: str
    params: type[BaseModel]
    run: Any  # async (ctx, args) -> dict for reads, Outcome for writes
    propose: Any = None  # confirm tools: async (ctx, args) -> (summary, args to store)
    undo: Any = None  # async (ctx, undo_data) -> None

    def schema(self) -> dict:
        parameters = self.params.model_json_schema()
        parameters.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(Args):
    pass


async def own_report(ctx: ToolContext, report_id: str) -> BodyStyleRecommendation:
    try:
        key = UUID(report_id)
    except ValueError:
        raise ToolError("report_id is not a valid id") from None
    record = await ctx.db.scalar(
        select(BodyStyleRecommendation).where(
            BodyStyleRecommendation.id == key,
            BodyStyleRecommendation.user_id == ctx.user.id,
        )
    )
    if record is None:
        raise ToolError("no such report for this user")
    return record


def report_brief(record: BodyStyleRecommendation) -> dict:
    return {
        "id": str(record.id),
        "created_at": record.created_at.isoformat(),
        "status": record.status,
        "mode": record.input_snapshot.get("mode", "ai"),
        "context": record.input_snapshot.get("context"),
        "summary": record.result["summary"] if record.result else None,
        "derived_from": (record.input_snapshot.get("derived_from") or {}).get("id"),
    }


# ---------------------------------------------------------------- read tools


async def get_profile(ctx: ToolContext, args: NoArgs) -> dict:
    user = ctx.user
    return {
        "body_measurements": user.body_measurements or {},
        "styling_profile": StylingProfile.model_validate(user.styling_profile or {}).model_dump(
            exclude_none=True
        ),
        "locale": user.locale,
        "location": user.location_name,
    }


class ListReportsArgs(Args):
    limit: int = Field(5, ge=1, le=10)


async def list_reports(ctx: ToolContext, args: ListReportsArgs) -> dict:
    records = (
        await ctx.db.scalars(
            select(BodyStyleRecommendation)
            .where(BodyStyleRecommendation.user_id == ctx.user.id)
            .order_by(BodyStyleRecommendation.created_at.desc())
            .limit(args.limit)
        )
    ).all()
    return {"reports": [report_brief(r) for r in records]}


class ReportArgs(Args):
    report_id: str


async def get_report(ctx: ToolContext, args: ReportArgs) -> dict:
    record = await own_report(ctx, args.report_id)
    brief = report_brief(record)
    if record.result:
        brief["outfits"] = [
            {
                "outfit_index": index,
                "title": outfit["title"],
                "body_reason": outfit["body_reason"],
                "garments": [
                    {"slot": g["slot"], "kind": g["kind"], "description": g["description"]}
                    for g in outfit["garments"]
                ],
            }
            for index, outfit in enumerate(record.result["outfits"])
        ]
        brief["fit_advice"] = [a["text"] for a in record.result["fit_advice"]]
    brief["feedback"] = record.feedback
    brief["error_code"] = record.error_code
    return brief


class WardrobeArgs(Args):
    type: str | None = Field(None, description="wardrobe type, e.g. shirt, pants, shoes")
    limit: int = Field(30, ge=1, le=60)


async def search_wardrobe(ctx: ToolContext, args: WardrobeArgs) -> dict:
    query = select(ClothingItem).where(
        ClothingItem.user_id == ctx.user.id, ClothingItem.is_archived.is_(False)
    )
    if args.type:
        query = query.where(ClothingItem.type == args.type)
    items = (
        await ctx.db.scalars(query.order_by(ClothingItem.created_at.desc()).limit(args.limit))
    ).all()
    return {
        "items": [
            {
                "id": str(i.id),
                "name": i.name,
                "type": i.type,
                "subtype": i.subtype,
                "color": i.primary_color,
                "material": i.material,
                "wear_count": i.wear_count,
                "last_worn_at": i.last_worn_at.isoformat() if i.last_worn_at else None,
            }
            for i in items
        ]
    }


async def get_weather(ctx: ToolContext, args: NoArgs) -> dict:
    weather = await current_weather(ctx.user)
    if weather is None:
        return {"weather": None, "note": "no saved location or the weather service is down"}
    return {
        "weather": {
            "temperature": weather.temperature,
            "feels_like": weather.feels_like,
            "condition": weather.condition,
            "precipitation_chance": weather.precipitation_chance,
            "location": ctx.user.location_name,
        }
    }


class HistoryArgs(Args):
    days: int = Field(14, ge=1, le=60)


async def get_wear_history(ctx: ToolContext, args: HistoryArgs) -> dict:
    since = get_user_today(ctx.user) - timedelta(days=args.days)
    rows = (
        await ctx.db.execute(
            select(ItemHistory.worn_at, ItemHistory.occasion, ClothingItem.name, ClothingItem.type)
            .join(ClothingItem, ClothingItem.id == ItemHistory.item_id)
            .where(ClothingItem.user_id == ctx.user.id, ItemHistory.worn_at >= since)
            .order_by(ItemHistory.worn_at.desc())
            .limit(100)
        )
    ).all()
    return {
        "wears": [
            {"date": worn.isoformat(), "occasion": occasion, "item": name, "type": kind}
            for worn, occasion, name, kind in rows
        ]
    }


Occasion = Literal["daily", "work", "date", "weekend", "formal"]
Style = Literal["minimal", "smart_casual", "street", "sporty", "classic"]


class TodayArgs(Args):
    occasion: Occasion | None = None
    reroll: int = Field(0, ge=0, le=50)


async def get_today_outfit(ctx: ToolContext, args: TodayArgs) -> dict:
    today = await build_today(ctx.db, ctx.user, args.occasion, None, args.reroll)
    return {key: value for key, value in today.items() if not key.startswith("_")}


async def wardrobe_gaps(ctx: ToolContext, args: ReportArgs) -> dict:
    record = await own_report(ctx, args.report_id)
    if record.status != "done":
        raise ToolError("the report is not finished yet")
    items = (
        await ctx.db.scalars(
            select(ClothingItem).where(
                ClothingItem.user_id == ctx.user.id, ClothingItem.is_archived.is_(False)
            )
        )
    ).all()
    profile = StylingProfile.model_validate(record.input_snapshot.get("styling_profile") or {})
    match = wardrobe_match(record.result, list(items), profile)
    for outfit in match["outfits"]:
        for garment in outfit["garments"]:
            garment["matches"] = [m["name"] for m in garment["matches"]]
    return match


# ---------------------------------------------------------------- direct (undoable) tools


async def delete_report_row(ctx: ToolContext, undo: dict) -> None:
    await ctx.db.execute(
        delete(BodyStyleRecommendation).where(
            BodyStyleRecommendation.id == UUID(undo["report_id"]),
            BodyStyleRecommendation.user_id == ctx.user.id,
        )
    )


class CreateReportArgs(Args):
    occasion: Occasion = "daily"
    style: Style = "minimal"
    season: Literal["all", "spring", "summer", "autumn", "winter"] = "all"
    goals: list[Literal["balance", "elongate_legs", "midsection", "shoulders", "comfort"]] = Field(
        default_factory=lambda: ["balance", "comfort"], min_length=1, max_length=5
    )
    mode: Literal["auto", "rules"] = "auto"


async def create_report(ctx: ToolContext, args: CreateReportArgs) -> Outcome:
    try:
        measurements = BodyMeasurements.model_validate(ctx.user.body_measurements or {})
    except ValidationError:
        raise ToolError("height, chest, waist and hips must be saved first") from None
    request = BodyStyleRequest(**args.model_dump())
    feedback = await recent_style_feedback(ctx.db, ctx.user.id)
    if args.mode == "rules" or not ctx.ai_available:
        record = await generate_rule_based_style(ctx.db, ctx.user, measurements, request, feedback)
        note = ctx.text("（基础规则版）", " (rule-based)")
    else:
        record = await create_pending_style(ctx.db, ctx.user, measurements, request, feedback)
        await ctx.db.commit()
        try:
            record.job_id = await enqueue_style_job(record.id)
        except Exception:
            record.status, record.error_code = "failed", "queue_failed"
        note = ctx.text("（AI 正在后台生成）", " (AI is generating it in the background)")
    return Outcome(
        result=report_brief(record),
        summary=ctx.text("生成了一份新报告", "Created a new report") + note,
        undo={"report_id": str(record.id)},
    )


class RegenerateArgs(Args):
    report_id: str
    outfit_index: int = Field(ge=0, le=2)
    instruction: str = Field(min_length=1, max_length=500)


async def regenerate(ctx: ToolContext, args: RegenerateArgs) -> Outcome:
    record = await own_report(ctx, args.report_id)
    if record.status != "done":
        raise ToolError("the report is not finished yet")
    try:
        child = await regenerate_outfit(
            ctx.db,
            ctx.user,
            record,
            args.outfit_index,
            args.instruction,
            ctx.endpoints,
            ctx.ai_available,
        )
    except EditError as exc:
        raise ToolError(str(exc)) from None
    return Outcome(
        result={
            **report_brief(child),
            "new_outfit": [
                g["description"] for g in child.result["outfits"][args.outfit_index]["garments"]
            ],
        },
        summary=ctx.text(
            f"按“{clip(args.instruction)}”重新生成了第 {args.outfit_index + 1} 套，存为新报告",
            f'Regenerated look {args.outfit_index + 1} ("{clip(args.instruction)}") as a new report',
        ),
        undo={"report_id": str(child.id)},
    )


class GarmentChanges(Args):
    kind: str | None = None
    color: str | None = Field(None, description="hex color from the palette")
    material: str | None = None
    fit: Literal["slim", "regular", "relaxed", "wide"] | None = None
    length: Literal["short", "regular", "long"] | None = None
    rise: Literal["low", "mid", "high"] | None = None
    pattern: Literal["solid", "stripe", "check", "herringbone", "dot"] | None = None


class ReplaceGarmentArgs(Args):
    report_id: str
    outfit_index: int = Field(ge=0, le=2)
    slot: Literal["top", "bottom", "shoes", "outerwear", "accessory"]
    position: int = Field(0, ge=0, le=1, description="0 for the first garment in that slot")
    changes: GarmentChanges


async def replace(ctx: ToolContext, args: ReplaceGarmentArgs) -> Outcome:
    record = await own_report(ctx, args.report_id)
    if record.status != "done":
        raise ToolError("the report is not finished yet")
    changes = args.changes.model_dump(exclude_none=True)
    if not changes:
        raise ToolError("no changes given")
    try:
        outfit = record.result["outfits"][args.outfit_index]
        index = garment_index_for(outfit, args.slot, args.position)
        before = stored_draft_garment(outfit["garments"][index])
        child = await replace_garment(ctx.db, ctx.user, record, args.outfit_index, index, changes)
    except EditError as exc:
        raise ToolError(str(exc)) from None
    new = child.result["outfits"][args.outfit_index]["garments"][index]
    diff = ", ".join(f"{k}: {before.get(k)} → {v}" for k, v in changes.items())
    return Outcome(
        result={**report_brief(child), "new_garment": new["description"]},
        summary=ctx.text(
            f"第 {args.outfit_index + 1} 套的单品改为：{new['description']}（{diff}），存为新报告",
            f"Look {args.outfit_index + 1}: changed to {new['description']} ({diff}) as a new report",
        ),
        undo={"report_id": str(child.id)},
    )


class FeedbackArgs(Args):
    report_id: str
    outfit_index: int = Field(ge=0, le=2)
    overall: Literal["like", "dislike"] | None = None
    colors: Literal["like", "dislike"] | None = None
    fabrics: Literal["like", "dislike"] | None = None


def apply_feedback(record: BodyStyleRecommendation, data: OutfitFeedback) -> None:
    items = [
        item
        for item in (record.feedback or {}).get("outfits", [])
        if item["outfit_index"] != data.outfit_index
    ]
    if data.overall or data.colors or data.fabrics:
        items.append(data.model_dump())
    feedback = ReportFeedback(outfits=sorted(items, key=lambda item: item["outfit_index"]))
    record.feedback = feedback.model_dump() if feedback.outfits else None


async def set_feedback(ctx: ToolContext, args: FeedbackArgs) -> Outcome:
    record = await own_report(ctx, args.report_id)
    if record.status != "done":
        raise ToolError("the report is not finished yet")
    previous = record.feedback
    apply_feedback(record, OutfitFeedback(**args.model_dump(exclude={"report_id"})))
    await ctx.db.flush()
    ratings = {k: v for k, v in args.model_dump().items() if k in {"overall", "colors", "fabrics"}}
    return Outcome(
        result={"feedback": record.feedback},
        summary=ctx.text(
            f"记录了第 {args.outfit_index + 1} 套的反馈：{ratings}",
            f"Saved feedback for look {args.outfit_index + 1}: {ratings}",
        ),
        undo={"report_id": str(record.id), "previous": previous},
    )


async def undo_feedback(ctx: ToolContext, undo: dict) -> None:
    record = await own_report(ctx, undo["report_id"])
    record.feedback = undo["previous"]
    await ctx.db.flush()


class LogWearArgs(Args):
    item_ids: list[str] = Field(min_length=1, max_length=10)
    worn_on: date | None = None


async def log_wear(ctx: ToolContext, args: LogWearArgs) -> Outcome:
    try:
        keys = [UUID(value) for value in args.item_ids]
    except ValueError:
        raise ToolError("item_ids must be wardrobe item ids") from None
    items = (
        await ctx.db.scalars(
            select(ClothingItem).where(
                ClothingItem.id.in_(keys), ClothingItem.user_id == ctx.user.id
            )
        )
    ).all()
    if len(items) != len(set(keys)):
        raise ToolError("some items do not exist in this wardrobe")
    before = {
        str(i.id): {
            "wear_count": i.wear_count,
            "last_worn_at": i.last_worn_at.isoformat() if i.last_worn_at else None,
            "wears_since_wash": i.wears_since_wash,
            "needs_wash": i.needs_wash,
        }
        for i in items
    }
    # record_wears expires the items, so their names are read first.
    names = ", ".join(i.name or i.type for i in items)
    worn_on = args.worn_on or get_user_today(ctx.user)
    histories = await ItemService(ctx.db).record_wears(ctx.user.id, keys, worn_on)
    return Outcome(
        result={"logged": len(histories), "date": worn_on.isoformat()},
        summary=ctx.text(
            f"记录了 {worn_on} 穿过：{names}", f"Logged as worn on {worn_on}: {names}"
        ),
        undo={"history_ids": [str(h.id) for h in histories], "before": before},
    )


async def undo_wear(ctx: ToolContext, undo: dict) -> None:
    for item_id, values in undo["before"].items():
        last = values["last_worn_at"]
        await ctx.db.execute(
            update(ClothingItem)
            .where(ClothingItem.id == UUID(item_id), ClothingItem.user_id == ctx.user.id)
            .values(
                wear_count=values["wear_count"],
                last_worn_at=date.fromisoformat(last) if last else None,
                wears_since_wash=values["wears_since_wash"],
                needs_wash=values["needs_wash"],
            )
        )
    await ctx.db.execute(
        delete(ItemHistory).where(ItemHistory.id.in_([UUID(h) for h in undo["history_ids"]]))
    )


class AddItemArgs(Args):
    image_id: str = Field(description="id of an image the user attached in this conversation")
    type: Literal[*TYPES]
    primary_color: Literal[*COLORS] | None = None
    material: Literal[*MATERIALS] | None = None
    name: str | None = Field(None, max_length=100, description="short name, e.g. 藏青牛津纺衬衫")


async def own_image(ctx: ToolContext, image_id: str) -> AssistantImage:
    try:
        key = UUID(image_id)
    except ValueError:
        raise ToolError("image_id must be the id of an attached image") from None
    image = await ctx.db.scalar(
        select(AssistantImage).where(
            AssistantImage.id == key, AssistantImage.user_id == ctx.user.id
        )
    )
    if image is None:
        raise ToolError("no attached image with this id")
    return image


async def queue_tagging(item_id: UUID, image_path: str) -> None:
    redis = await create_pool(get_redis_settings())
    try:
        await redis.enqueue_job(
            "tag_item_image", str(item_id), image_path, _queue_name=TAGGING_QUEUE
        )
    finally:
        await redis.aclose()


async def add_wardrobe_item(ctx: ToolContext, args: AddItemArgs) -> Outcome:
    image = await own_image(ctx, args.image_id)
    images = ImageService()
    service = ItemService(ctx.db)
    # The item gets its own copy, so deleting either the chat or the item keeps the other intact.
    original = images.get_image_path(image.image_path).read_bytes()
    paths = await images.process_and_store(ctx.user.id, original, "assistant.jpg")
    existing = await service.find_duplicate_by_hash(ctx.user.id, paths["image_hash"])
    if existing is not None:
        images.delete_images({k: v for k, v in paths.items() if k != "image_hash"})
        raise ToolError(
            f"this photo is already in the wardrobe as {existing.name or existing.type}"
        )
    color = args.primary_color
    item = await service.create(
        ctx.user.id,
        ItemCreate(
            type=args.type, name=args.name, primary_color=color, colors=[color] if color else None
        ),
        paths,
    )
    if args.material:
        item.material = args.material
    if get_settings().effective_ai_vision_enabled:
        # The worker reads the row from its own connection, so it is queued after the commit.
        full_path = str(images.get_image_path(paths["image_path"]))
        ctx.after_commit.append(lambda: queue_tagging(item.id, full_path))
    else:
        item = await service.mark_pending(item, set_ready=True)
    await ctx.db.flush()
    label = args.name or args.type
    return Outcome(
        result={
            "item_id": str(item.id),
            "name": item.name,
            "type": item.type,
            "thumbnail_url": sign_optional(item.thumbnail_path, item.image_path),
        },
        summary=ctx.text(f"已加入衣橱：{label}", f"Added to the wardrobe: {label}"),
        undo={"item_id": str(item.id)},
    )


async def undo_add_item(ctx: ToolContext, undo: dict) -> None:
    item = await ItemService(ctx.db).get_by_id(UUID(undo["item_id"]), ctx.user.id)
    if item is None:
        raise ToolError("the item is no longer in the wardrobe")
    if item.wear_count:
        raise ToolError("the item has been worn since; remove it from the wardrobe page instead")
    ImageService().delete_images(
        {
            "image_path": item.image_path,
            "thumbnail_path": item.thumbnail_path,
            "medium_path": item.medium_path,
        }
    )
    await ItemService(ctx.db).delete(item)


class AssessArgs(Args):
    type: Literal[*TYPES]
    primary_color: Literal[*COLORS]
    material: Literal[*MATERIALS] | None = None


async def assess_purchase(ctx: ToolContext, args: AssessArgs) -> dict:
    items = (
        await ctx.db.scalars(
            select(ClothingItem).where(
                ClothingItem.user_id == ctx.user.id, ClothingItem.is_archived.is_(False)
            )
        )
    ).all()
    profile = StylingProfile.model_validate(ctx.user.styling_profile or {})
    return purchase_fit(items, profile, args.type, args.primary_color, args.material)


# ---------------------------------------------------------------- tools that need confirmation


class ProfileArgs(Args):
    body_measurements: dict[str, float | str | None] | None = Field(
        None, description="only the fields to change; null removes an optional field"
    )
    styling_profile: dict[str, Any] | None = Field(
        None, description="only the fields to change, using the profile's own vocabulary"
    )


def merged_profile(user: User, args: ProfileArgs) -> tuple[dict, dict]:
    measurements = dict(user.body_measurements or {})
    for key, value in (args.body_measurements or {}).items():
        if key not in (*MEASUREMENT_KEYS, "shoulder_type"):
            raise ToolError(f"{key} is not a body measurement the assistant may change")
        if value is None:
            measurements.pop(key, None)
        else:
            measurements[key] = value
    try:
        BodyMeasurements.model_validate(measurements)
    except ValidationError as exc:
        raise ToolError(
            f"invalid measurements: {exc.errors(include_url=False)[0]['msg']}"
        ) from None
    profile = StylingProfile.model_validate(user.styling_profile or {}).model_dump(
        exclude_none=True
    )
    profile.update(args.styling_profile or {})
    try:
        profile = StylingProfile.model_validate(profile).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise ToolError(
            f"invalid styling profile: {exc.errors(include_url=False)[0]['msg']}"
        ) from None
    return measurements, profile


def clip(text: str, limit: int = 24) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def shown(value) -> str:
    """88.0 -> "88": measurements are floats, but people write whole numbers."""
    if value is None:
        return "—"
    return format(value, "g") if isinstance(value, float) else str(value)


def profile_value(key: str, value, zh: bool) -> str:
    """Catalog codes ("wool") are shown by their names ("羊毛"), lists joined."""
    if value in (None, "", []):
        return "—"
    if key == "preferred_styles":
        names = [STYLE_NAMES.get(v, {}).get("zh" if zh else "en", v) for v in value]
        return ("、" if zh else ", ").join(names)
    if key not in PROFILE_CATALOGS:
        return str(value)
    vocabulary = CATALOG[PROFILE_CATALOGS[key]]
    values = value if isinstance(value, list) else [value]
    names = (vocabulary.get(v, {}).get("zh" if zh else "en", v) for v in values)
    return ("、" if zh else ", ").join(names)


async def propose_profile(ctx: ToolContext, args: ProfileArgs) -> tuple[str, dict]:
    measurements, profile = merged_profile(ctx.user, args)
    old_m = ctx.user.body_measurements or {}
    old_p = StylingProfile.model_validate(ctx.user.styling_profile or {}).model_dump(
        exclude_none=True
    )
    index = 0 if ctx.zh else 1
    lines = []
    for key in sorted(set(old_m) | set(measurements)):
        if old_m.get(key) != measurements.get(key):
            label = FACT_NAMES.get(key, (key, key))[index]
            lines.append(f"{label} {shown(old_m.get(key))} → {shown(measurements.get(key))}")
    for key in sorted(set(old_p) | set(profile)):
        if old_p.get(key) != profile.get(key):
            label = FACT_NAMES.get(key, (key, key))[index]
            before, after = (
                profile_value(key, v, ctx.zh) for v in (old_p.get(key), profile.get(key))
            )
            lines.append(f"{label}: {before} → {after}")
    if not lines:
        raise ToolError("these values are already saved")
    stored = {
        **args.model_dump(exclude_none=True),
        "expected_styling_profile_revision": styling_revision(
            ctx.user.body_measurements, ctx.user.styling_profile
        ),
    }
    return ctx.text("更新资料：", "Updated profile: ") + "; ".join(lines), stored


async def apply_profile(ctx: ToolContext, args: dict) -> Outcome:
    await ctx.db.refresh(ctx.user, with_for_update=True)
    if args["expected_styling_profile_revision"] != styling_revision(
        ctx.user.body_measurements, ctx.user.styling_profile
    ):
        raise ToolError("the profile changed elsewhere since this was proposed; propose again")
    before = {
        "body_measurements": ctx.user.body_measurements,
        "styling_profile": ctx.user.styling_profile,
    }
    measurements, profile = merged_profile(
        ctx.user,
        ProfileArgs.model_validate({k: v for k, v in args.items() if not k.startswith("expected")}),
    )
    ctx.user.body_measurements = measurements
    ctx.user.styling_profile = profile
    await ctx.db.flush()
    return Outcome(
        result={
            "body_measurements_revision": body_revision(measurements),
            "styling_profile_revision": styling_revision(measurements, profile),
        },
        summary="",
        undo={
            **before,
            "revision_after": styling_revision(measurements, profile),
        },
    )


async def update_profile(ctx: ToolContext, args: ProfileArgs) -> Outcome:
    summary, stored = await propose_profile(ctx, args)
    outcome = await apply_profile(ctx, stored)
    outcome.summary = summary
    return outcome


async def undo_profile(ctx: ToolContext, undo: dict) -> None:
    await ctx.db.refresh(ctx.user, with_for_update=True)
    if undo["revision_after"] != styling_revision(
        ctx.user.body_measurements, ctx.user.styling_profile
    ):
        raise ToolError("the profile was changed again after this edit, so it cannot be undone")
    ctx.user.body_measurements = undo["body_measurements"]
    ctx.user.styling_profile = undo["styling_profile"]
    await ctx.db.flush()


async def propose_delete(ctx: ToolContext, args: ReportArgs) -> tuple[str, dict]:
    record = await own_report(ctx, args.report_id)
    when = record.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
    # Reports made in the same minute need their looks to be told apart.
    titles = clip(" / ".join(o["title"] for o in (record.result or {}).get("outfits", [])), 40)
    zh = f"删除 {when} 的报告" + (f"（{titles}）" if titles else "")
    en = f"Delete the report from {when}" + (f" ({titles})" if titles else "")
    return ctx.text(zh, en), args.model_dump()


ROW_FIELDS = (
    "id",
    "input_snapshot",
    "facts",
    "result",
    "model",
    "feedback",
    "status",
    "job_id",
    "error_code",
    "seen_at",
    "parent_id",
    "created_at",
)


async def apply_delete(ctx: ToolContext, args: dict) -> Outcome:
    record = await own_report(ctx, args["report_id"])
    # Kept as JSON so undo can restore the exact row, id and timestamps included.
    row = json.loads(json.dumps({f: getattr(record, f) for f in ROW_FIELDS}, default=str))
    await ctx.db.delete(record)
    await ctx.db.flush()
    return Outcome(result={"deleted": args["report_id"]}, summary="", undo={"row": row})


async def undo_delete(ctx: ToolContext, undo: dict) -> None:
    row = dict(undo["row"])
    for field in ("created_at", "seen_at"):
        if row.get(field):
            row[field] = datetime.fromisoformat(row[field])
    for field in ("id", "parent_id"):
        if row.get(field):
            row[field] = UUID(row[field])
    if row.get("parent_id") and not await ctx.db.get(BodyStyleRecommendation, row["parent_id"]):
        row["parent_id"] = None
    ctx.db.add(BodyStyleRecommendation(user_id=ctx.user.id, **row))
    await ctx.db.flush()


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in [
        Tool(
            "get_profile",
            "read",
            "Read the user's body measurements and styling profile.",
            NoArgs,
            get_profile,
        ),
        Tool(
            "list_reports",
            "read",
            "List the user's recent body styling reports.",
            ListReportsArgs,
            list_reports,
        ),
        Tool(
            "get_report",
            "read",
            "Read one report: its outfits, garments, fit advice and feedback.",
            ReportArgs,
            get_report,
        ),
        Tool(
            "search_wardrobe",
            "read",
            "List wardrobe items, optionally of one type.",
            WardrobeArgs,
            search_wardrobe,
        ),
        Tool(
            "get_weather",
            "read",
            "Current weather at the user's saved location.",
            NoArgs,
            get_weather,
        ),
        Tool(
            "get_wear_history",
            "read",
            "What the user wore in the last days.",
            HistoryArgs,
            get_wear_history,
        ),
        Tool(
            "get_today_outfit",
            "read",
            "Today's rule-based look for an occasion.",
            TodayArgs,
            get_today_outfit,
        ),
        Tool(
            "wardrobe_gaps",
            "read",
            "Which garments of a report the wardrobe already has, and what to buy first.",
            ReportArgs,
            wardrobe_gaps,
        ),
        Tool(
            "create_report",
            "direct",
            "Create a new three-look report (undoable).",
            CreateReportArgs,
            create_report,
            undo=delete_report_row,
        ),
        Tool(
            "regenerate_outfit",
            "direct",
            "Regenerate one look of a report from an instruction; saves a new report (undoable).",
            RegenerateArgs,
            regenerate,
            undo=delete_report_row,
        ),
        Tool(
            "replace_garment",
            "direct",
            "Change one garment's attributes in a look; saves a new report (undoable).",
            ReplaceGarmentArgs,
            replace,
            undo=delete_report_row,
        ),
        Tool(
            "set_feedback",
            "direct",
            "Record like/dislike feedback on a look (undoable).",
            FeedbackArgs,
            set_feedback,
            undo=undo_feedback,
        ),
        Tool(
            "log_wear",
            "direct",
            "Log wardrobe items as worn (undoable).",
            LogWearArgs,
            log_wear,
            undo=undo_wear,
        ),
        Tool(
            "assess_purchase",
            "read",
            "Check a garment the user is considering (e.g. from a shop photo) against their "
            "profile's avoidances and their wardrobe: near-duplicates, owned items it pairs with, "
            "and how many more outfits it would make.",
            AssessArgs,
            assess_purchase,
        ),
        Tool(
            "add_wardrobe_item",
            "direct",
            "Add the single garment shown in an attached photo to the wardrobe (undoable). "
            "Use only when the user asks to add it.",
            AddItemArgs,
            add_wardrobe_item,
            undo=undo_add_item,
        ),
        Tool(
            "update_profile",
            "direct",
            "Save changes to body measurements or the styling profile (undoable). Use it whenever "
            "the user states a new value, even in passing.",
            ProfileArgs,
            update_profile,
            undo=undo_profile,
        ),
        Tool(
            "delete_report",
            "confirm",
            "Propose deleting a report; the user must confirm.",
            ReportArgs,
            apply_delete,
            propose=propose_delete,
            undo=undo_delete,
        ),
    ]
}
