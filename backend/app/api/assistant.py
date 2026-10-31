"""Chat assistant API. Turns stream as server-sent events; actions are confirmed or undone here."""

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.database import DbSession, async_session_maker
from app.models.assistant import AssistantAction, AssistantConversation, AssistantMessage
from app.models.user import User
from app.services.assistant_service import MAX_MESSAGE_CHARS, Assistant, action_view
from app.services.assistant_tools import ToolError
from app.utils.auth import get_current_user
from app.utils.rate_limit import check_rate_limit

router = APIRouter(prefix="/assistant", tags=["Assistant"])
CurrentUser = Annotated[User, Depends(get_current_user)]
# The request's session closes before a streamed body is sent, so turns open their own.
session_factory = async_session_maker


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


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
    messages = (
        await db.scalars(
            select(AssistantMessage)
            .where(
                AssistantMessage.conversation_id == conversation.id,
                AssistantMessage.role.in_(("user", "assistant")),
                AssistantMessage.content.is_not(None),
                AssistantMessage.content != "",
            )
            .order_by(AssistantMessage.seq)
        )
    ).all()
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
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "actions": [action_view(a) for a in actions],
    }


def stream(user_id: UUID, conversation_id: UUID, text: str | None) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async with session_factory() as db:
            user = await db.get(User, user_id)
            conversation = await db.get(AssistantConversation, conversation_id)
            async for event in Assistant(db, user).turn(conversation, text):
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
    return stream(current_user.id, conversation.id, data.content)


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
