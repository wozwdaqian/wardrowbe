"""Chat assistant API. Turns stream as server-sent events; actions are confirmed or undone here."""

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.config import get_settings
from app.database import DbSession, async_session_maker
from app.models.assistant import (
    AssistantAction,
    AssistantConversation,
    AssistantImage,
    AssistantMessage,
)
from app.models.user import User
from app.services.assistant_service import MAX_IMAGES, MAX_MESSAGE_CHARS, Assistant, action_view
from app.services.assistant_tools import ToolError
from app.services.image_service import ImageService
from app.utils.auth import get_current_user
from app.utils.rate_limit import check_rate_limit
from app.utils.signed_urls import sign_image_url
from app.utils.uploads import UploadTooLargeError, read_upload_within_limit

router = APIRouter(prefix="/assistant", tags=["Assistant"])
CurrentUser = Annotated[User, Depends(get_current_user)]
# The request's session closes before a streamed body is sent, so turns open their own.
session_factory = async_session_maker


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    content: str = Field("", max_length=MAX_MESSAGE_CHARS)
    image_ids: list[UUID] = Field(default_factory=list, max_length=MAX_IMAGES)

    @model_validator(mode="after")
    def not_empty(self):
        if not self.content and not self.image_ids:
            raise ValueError("send text or at least one image")
        return self


def image_view(image: AssistantImage) -> dict:
    return {
        "id": str(image.id),
        "thumbnail_url": sign_image_url(image.thumbnail_path),
        "url": sign_image_url(image.medium_path),
    }


def conversation_view(conversation: AssistantConversation) -> dict:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


async def own_conversation(db, user: User, conversation_id: UUID) -> AssistantConversation:
    conversation = await db.scalar(
        select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("/conversations", status_code=201)
async def create_conversation(db: DbSession, current_user: CurrentUser) -> dict:
    conversation = AssistantConversation(user_id=current_user.id)
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)
    return conversation_view(conversation)


@router.get("/conversations")
async def list_conversations(
    db: DbSession, current_user: CurrentUser, limit: int = Query(20, ge=1, le=50)
) -> list[dict]:
    rows = (
        await db.scalars(
            select(AssistantConversation)
            .where(AssistantConversation.user_id == current_user.id)
            .order_by(AssistantConversation.updated_at.desc())
            .limit(limit)
        )
    ).all()
    return [conversation_view(c) for c in rows]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: UUID, db: DbSession, current_user: CurrentUser) -> dict:
    conversation = await own_conversation(db, current_user, conversation_id)
    rows = (
        await db.scalars(
            select(AssistantMessage)
            .where(
                AssistantMessage.conversation_id == conversation.id,
                AssistantMessage.role.in_(("user", "assistant")),
            )
            .order_by(AssistantMessage.seq)
        )
    ).all()
    images: dict = {}
    for image in await db.scalars(
        select(AssistantImage)
        .where(AssistantImage.message_id.in_([row.id for row in rows]))
        .order_by(AssistantImage.created_at)
    ):
        images.setdefault(image.message_id, []).append(image_view(image))
    messages = [row for row in rows if row.content or row.id in images]
    actions = (
        await db.scalars(
            select(AssistantAction)
            .where(AssistantAction.conversation_id == conversation.id)
            .order_by(AssistantAction.created_at)
        )
    ).all()
    return {
        **conversation_view(conversation),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content or "",
                "images": images.get(m.id, []),
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "actions": [action_view(a) for a in actions],
    }


def stream(
    user_id: UUID, conversation_id: UUID, text: str | None, image_ids: list[UUID] | None = None
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async with session_factory() as db:
            user = await db.get(User, user_id)
            conversation = await db.get(AssistantConversation, conversation_id)
            async for event in Assistant(db, user).turn(conversation, text, image_ids):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID, data: MessageIn, db: DbSession, current_user: CurrentUser
) -> StreamingResponse:
    conversation = await own_conversation(db, current_user, conversation_id)
    await check_rate_limit(f"assistant:{current_user.id}", limit=10, window_seconds=60)
    if data.image_ids:
        found = await Assistant(db, current_user).unattached_images(data.image_ids)
        if len(found) != len(set(data.image_ids)):
            raise HTTPException(status_code=422, detail="Unknown or already sent image")
    return stream(current_user.id, conversation.id, data.content, data.image_ids)


@router.post("/images", status_code=201)
async def upload_image(
    db: DbSession, current_user: CurrentUser, image: UploadFile = File(...)
) -> dict:
    """Store a photo for the next message; it is linked to that message when sent."""
    await check_rate_limit(f"assistant-image:{current_user.id}", limit=20, window_seconds=60)
    try:
        content = await read_upload_within_limit(image, get_settings().max_upload_size_mb)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None
    service = ImageService()
    if not service.validate_image(content, image.content_type or "application/octet-stream"):
        raise HTTPException(
            status_code=400, detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC"
        )
    try:
        paths = await service.process_and_store(
            current_user.id, content, image.filename or "upload.jpg"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    record = AssistantImage(user_id=current_user.id, **paths)
    db.add(record)
    await db.flush()
    return image_view(record)


@router.post("/conversations/{conversation_id}/continue")
async def continue_conversation(
    conversation_id: UUID, db: DbSession, current_user: CurrentUser
) -> StreamingResponse:
    """Let the model react after the user confirmed or rejected a proposal."""
    conversation = await own_conversation(db, current_user, conversation_id)
    await check_rate_limit(f"assistant:{current_user.id}", limit=10, window_seconds=60)
    return stream(current_user.id, conversation.id, None)


async def act(db, user: User, action_id: UUID, verb: str) -> dict:
    assistant = Assistant(db, user)
    try:
        action = await getattr(assistant, verb)(action_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Action not found") from None
    except ToolError as exc:
        raise HTTPException(
            status_code=409, detail={"code": "action_conflict", "message": str(exc)}
        ) from None
    return action_view(action)


@router.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: UUID, db: DbSession, current_user: CurrentUser) -> dict:
    return await act(db, current_user, action_id, "confirm")


@router.post("/actions/{action_id}/reject")
async def reject_action(action_id: UUID, db: DbSession, current_user: CurrentUser) -> dict:
    return await act(db, current_user, action_id, "reject")


@router.post("/actions/{action_id}/undo")
async def undo_action(action_id: UUID, db: DbSession, current_user: CurrentUser) -> dict:
    return await act(db, current_user, action_id, "undo")
