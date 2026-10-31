import json
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest

from app.api import assistant as assistant_api
from app.config import get_settings
from app.models.assistant import AssistantAction, AssistantConversation
from app.models.body_styling import BodyStyleRecommendation
from app.models.item import ClothingItem
from app.models.user import User
from app.schemas.body_styling import BodyMeasurements, BodyStyleRequest
from app.services import assistant_service, assistant_tools
from app.services.assistant_service import MAX_TOOL_CALLS, Assistant
from app.services.body_styling_service import generate_rule_based_style

BASE = "/api/v1/assistant"
MEASUREMENTS = {"height": 175, "chest": 100, "waist": 90, "hips": 102}


def call(name, **arguments):
    return {
        "content": None,
        "tool_calls": [
            {
                "id": f"call-{uuid4().hex[:6]}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def say(text):
    return {"content": text, "tool_calls": None}


class ScriptedAI:
    """Stands in for AIService.chat: replays scripted assistant messages and records calls."""

    script: list = []
    calls: list = []
    reject_tools = False

    def __init__(self, endpoints=None):
        pass

    async def chat(self, messages, tools=None, vision=False):
        ScriptedAI.calls.append({"messages": messages, "tools": tools, "vision": vision})
        if tools and ScriptedAI.reject_tools:
            request = httpx.Request("POST", "http://ai.invalid")
            raise httpx.HTTPStatusError(
                "tools unsupported", request=request, response=httpx.Response(400, request=request)
            )
        step = ScriptedAI.script.pop(0) if ScriptedAI.script else say("ok")
        return {"message": step, "model": "scripted"}


@pytest.fixture
def ai(monkeypatch, db_session, test_user):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_base_url", "http://assistant-test.invalid/v1")
    monkeypatch.setattr(settings, "ai_text_model", "fixture-text")
    monkeypatch.setattr(assistant_service, "AIService", ScriptedAI)
    ScriptedAI.script, ScriptedAI.calls, ScriptedAI.reject_tools = [], [], False

    @asynccontextmanager
    async def same_session():
        yield db_session

    monkeypatch.setattr(assistant_api, "session_factory", same_session)
    return ScriptedAI


async def setup(db_session, user, locale="zh-CN"):
    user.body_measurements = dict(MEASUREMENTS)
    user.locale = locale
    conversation = AssistantConversation(user_id=user.id)
    db_session.add(conversation)
    await db_session.commit()
    return conversation


async def run(db_session, user, conversation, text):
    return [event async for event in Assistant(db_session, user).turn(conversation, text)]


async def report(db_session, user):
    record = await generate_rule_based_style(
        db_session, user, BodyMeasurements(**MEASUREMENTS), BodyStyleRequest()
    )
    await db_session.commit()
    return record


@pytest.mark.asyncio
async def test_profile_change_is_saved_at_once_and_can_be_undone(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    ai.script = [
        call("update_profile", body_measurements={"waist": 88}),
        say("已把腰围更新为 88。"),
    ]
    events = await run(db_session, test_user, conversation, "我腰围变成 88 了")
    action = next(e["action"] for e in events if e["type"] == "action")
    assert action["status"] == "applied" and "腰围 90 → 88" in action["summary"]
    assert "88.0" not in action["summary"]
    await db_session.refresh(test_user)
    assert test_user.body_measurements["waist"] == 88
    # The model hears the change was saved, not that it waits for a confirmation.
    tool_result = json.loads(ai.calls[-1]["messages"][-1]["content"])["data"]
    assert "done" in tool_result and "proposed" not in tool_result

    undone = await Assistant(db_session, test_user).undo(action["id"])
    assert undone.status == "undone"
    await db_session.refresh(test_user)
    assert test_user.body_measurements["waist"] == 90


@pytest.mark.asyncio
async def test_undo_refuses_when_profile_changed_again(
    ai, db_session, test_user, client, auth_headers
):
    conversation = await setup(db_session, test_user)
    ai.script = [call("update_profile", body_measurements={"waist": 88}), say("ok")]
    events = await run(db_session, test_user, conversation, "腰围 88")
    action_id = next(e["action"]["id"] for e in events if e["type"] == "action")
    test_user.body_measurements = {**test_user.body_measurements, "waist": 86}
    await db_session.commit()
    response = await client.post(f"{BASE}/actions/{action_id}/undo", headers=auth_headers)
    assert response.status_code == 409
    await db_session.refresh(test_user)
    assert test_user.body_measurements["waist"] == 86


@pytest.mark.asyncio
async def test_profile_proposal_saved_before_the_change_cannot_be_confirmed(
    ai, db_session, test_user, client, auth_headers
):
    conversation = await setup(db_session, test_user)
    legacy = AssistantAction(
        conversation_id=conversation.id,
        user_id=test_user.id,
        tool="update_profile",
        args={"body_measurements": {"waist": 70}},
        status="pending",
        summary="修改资料：腰围 90 → 70",
    )
    db_session.add(legacy)
    await db_session.commit()
    response = await client.post(f"{BASE}/actions/{legacy.id}/confirm", headers=auth_headers)
    assert response.status_code == 409
    await db_session.refresh(test_user)
    assert test_user.body_measurements["waist"] == 90


@pytest.mark.asyncio
async def test_rejected_proposal_changes_nothing(ai, db_session, test_user, client, auth_headers):
    conversation = await setup(db_session, test_user)
    record = await report(db_session, test_user)
    ai.script = [call("delete_report", report_id=str(record.id)), say("确认后会删除。")]
    events = await run(db_session, test_user, conversation, "删掉那份报告")
    action_id = next(e["action"]["id"] for e in events if e["type"] == "action")
    response = await client.post(f"{BASE}/actions/{action_id}/reject", headers=auth_headers)
    assert response.json()["status"] == "rejected"
    assert await db_session.get(BodyStyleRecommendation, record.id) is not None
    # A decided proposal cannot be confirmed afterwards.
    assert (
        await client.post(f"{BASE}/actions/{action_id}/confirm", headers=auth_headers)
    ).status_code == 409


@pytest.mark.asyncio
async def test_confirmed_delete_can_be_restored(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    record = await report(db_session, test_user)
    record_id, summary = record.id, record.result["summary"]
    ai.script = [call("delete_report", report_id=str(record_id)), say("ok")]
    events = await run(db_session, test_user, conversation, "删除")
    action_id = next(e["action"]["id"] for e in events if e["type"] == "action")
    await Assistant(db_session, test_user).confirm(action_id)
    db_session.expunge_all()
    assert await db_session.get(BodyStyleRecommendation, record_id) is None
    user = await db_session.get(User, test_user.id)
    await Assistant(db_session, user).undo(action_id)
    restored = await db_session.get(BodyStyleRecommendation, record_id)
    assert restored is not None and restored.result["summary"] == summary


@pytest.mark.asyncio
async def test_direct_edit_creates_new_report_and_undo_removes_it(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    record = await report(db_session, test_user)
    original = json.dumps(record.result)
    ai.script = [
        call(
            "replace_garment",
            report_id=str(record.id),
            outfit_index=0,
            slot="shoes",
            changes={"kind": "loafers"},
        ),
        say("第一套的鞋换成了乐福鞋。"),
    ]
    events = await run(db_session, test_user, conversation, "第一套鞋换成乐福鞋")
    action = next(e["action"] for e in events if e["type"] == "action")
    assert action["status"] == "applied" and action["undoable"]
    child_id = action["result"]["id"]
    child = await db_session.get(BodyStyleRecommendation, child_id)
    shoes = next(g for g in child.result["outfits"][0]["garments"] if g["slot"] == "shoes")
    assert shoes["kind"] == "loafers" and child.parent_id == record.id
    assert child.seen_at is not None
    await db_session.refresh(record)
    assert json.dumps(record.result) == original
    await Assistant(db_session, test_user).undo(action["id"])
    db_session.expunge_all()
    assert await db_session.get(BodyStyleRecommendation, child_id) is None
    assert await db_session.get(BodyStyleRecommendation, record.id) is not None


@pytest.mark.asyncio
async def test_rule_breaking_edit_is_reported_to_the_model(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    record = await report(db_session, test_user)
    record.input_snapshot = {
        **record.input_snapshot,
        "context": {**record.input_snapshot["context"], "occasion": "formal"},
    }
    await db_session.commit()
    ai.script = [
        call(
            "replace_garment",
            report_id=str(record.id),
            outfit_index=0,
            slot="bottom",
            changes={"kind": "shorts", "length": "short"},
        ),
        say("正式场合不能穿短裤。"),
    ]
    events = await run(db_session, test_user, conversation, "换成短裤")
    assert not any(e["type"] == "action" for e in events)
    tool_result = ai.calls[-1]["messages"][-1]["content"]
    assert "occasion formal does not allow bottom shorts" in tool_result


@pytest.mark.asyncio
async def test_feedback_and_wear_undo_restore_previous_values(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    record = await report(db_session, test_user)
    record.feedback = {
        "outfits": [{"outfit_index": 0, "overall": "like", "colors": None, "fabrics": None}]
    }
    item = ClothingItem(user_id=test_user.id, type="shirt", image_path="s.jpg", wear_count=2)
    db_session.add(item)
    await db_session.commit()
    ai.script = [
        call("set_feedback", report_id=str(record.id), outfit_index=0, overall="dislike"),
        call("log_wear", item_ids=[str(item.id)]),
        say("记下了。"),
    ]
    events = await run(db_session, test_user, conversation, "第一套不喜欢；今天穿了那件衬衫")
    actions = [e["action"] for e in events if e["type"] == "action"]
    await db_session.refresh(record)
    await db_session.refresh(item)
    assert record.feedback["outfits"][0]["overall"] == "dislike" and item.wear_count == 3
    for action in actions:
        await Assistant(db_session, test_user).undo(action["id"])
    await db_session.refresh(record)
    await db_session.refresh(item)
    assert record.feedback["outfits"][0]["overall"] == "like"
    assert item.wear_count == 2 and item.last_worn_at is None


@pytest.mark.asyncio
async def test_other_users_data_is_out_of_reach(ai, db_session, test_user, client, auth_headers):
    conversation = await setup(db_session, test_user)
    other = User(id=uuid4(), email=f"{uuid4()}@example.com", display_name="Other")
    db_session.add(other)
    await db_session.flush()
    foreign = await report(db_session, other)
    ai.script = [call("get_report", report_id=str(foreign.id)), say("找不到这份报告。")]
    await run(db_session, test_user, conversation, "看看那份报告")
    assert "no such report" in ai.calls[-1]["messages"][-1]["content"]
    other_conversation = AssistantConversation(user_id=other.id)
    db_session.add(other_conversation)
    await db_session.flush()
    foreign_action = AssistantAction(
        conversation_id=other_conversation.id,
        user_id=other.id,
        tool="delete_report",
        args={"report_id": str(foreign.id)},
        status="pending",
        summary="x",
    )
    db_session.add(foreign_action)
    await db_session.commit()
    assert (
        await client.post(f"{BASE}/actions/{foreign_action.id}/confirm", headers=auth_headers)
    ).status_code == 404
    assert (
        await client.get(f"{BASE}/conversations/{other_conversation.id}", headers=auth_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_tool_calls_are_capped_per_turn(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    ai.script = [call("get_profile") for _ in range(10)] + [say("done")]
    events = await run(db_session, test_user, conversation, "loop")
    assert sum(e["type"] == "tool" for e in events) == MAX_TOOL_CALLS
    # The last call offers no tools, so the model has to answer.
    assert ai.calls[-1]["tools"] is None
    assert events[-1]["type"] == "message"


@pytest.mark.asyncio
async def test_json_protocol_when_tools_are_not_supported(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    ai.reject_tools = True
    ai.script = [
        say(json.dumps({"tool": "get_profile", "arguments": {}})),
        say(json.dumps({"reply": "你的腰围是记录里的数值。"})),
    ]
    events = await run(db_session, test_user, conversation, "我的资料？")
    assert [e["type"] for e in events] == ["tool", "message"]
    assert events[-1]["content"] == "你的腰围是记录里的数值。"
    assert "Tool result" in ai.calls[-1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_sse_endpoint_streams_events_and_history(
    ai, db_session, test_user, client, auth_headers
):
    test_user.body_measurements = dict(MEASUREMENTS)
    await db_session.commit()
    conversation = (await client.post(f"{BASE}/conversations", headers=auth_headers)).json()
    ai.script = [call("get_weather"), say("今天适合穿外套。")]
    response = await client.post(
        f"{BASE}/conversations/{conversation['id']}/messages",
        headers=auth_headers,
        json={"content": "今天穿什么？"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert [e["type"] for e in events] == ["tool", "message", "done"]
    detail = (
        await client.get(f"{BASE}/conversations/{conversation['id']}", headers=auth_headers)
    ).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["title"] == "今天穿什么？"
    too_long = await client.post(
        f"{BASE}/conversations/{conversation['id']}/messages",
        headers=auth_headers,
        json={"content": "x" * 2001},
    )
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_unavailable_ai_is_reported(ai, db_session, test_user, monkeypatch):
    conversation = await setup(db_session, test_user)
    monkeypatch.setattr(get_settings(), "ai_base_url", "")
    events = await run(db_session, test_user, conversation, "hi")
    assert events == [{"type": "error", "code": "ai_unavailable"}]


@pytest.mark.asyncio
async def test_regenerate_outfit_with_rules_and_with_ai(db_session, test_user, monkeypatch):
    from unittest.mock import AsyncMock, Mock

    from app.services import body_style_editing as editing
    from app.services.ai_service import TextGenerationResult
    from tests.body_style_samples import sample_result

    test_user.body_measurements = dict(MEASUREMENTS)
    test_user.locale = "zh-CN"
    record = await report(db_session, test_user)
    by_rules = await editing.regenerate_outfit(
        db_session, test_user, record, 1, "更休闲", None, use_ai=False
    )
    assert by_rules.parent_id == record.id
    assert by_rules.result["outfits"][0] == record.result["outfits"][0]
    assert by_rules.result["outfits"][1] != record.result["outfits"][1]

    replacement = sample_result()["outfits"][2]
    replacement["garments"][0]["color"] = "#b54040"
    mocked = Mock()
    mocked.generate_text = AsyncMock(
        side_effect=[
            TextGenerationResult(content="not json", model="m", endpoint="e"),
            TextGenerationResult(content=json.dumps(replacement), model="m", endpoint="e"),
        ]
    )
    monkeypatch.setattr(editing, "AIService", Mock(return_value=mocked))
    by_ai = await editing.regenerate_outfit(
        db_session, test_user, record, 2, "红色上衣", None, use_ai=True
    )
    assert by_ai.result["outfits"][2]["garments"][0]["color"] == "#b54040"
    assert "身高 175cm" in by_ai.result["outfits"][2]["body_reason"]
    assert mocked.generate_text.call_count == 2
    assert "Fix these problems" in mocked.generate_text.call_args.args[0]
    assert by_ai.input_snapshot["derived_from"]["instruction"] == "红色上衣"

    mocked.generate_text = AsyncMock(
        return_value=TextGenerationResult(content="{}", model="m", endpoint="e")
    )
    with pytest.raises(editing.EditError):
        await editing.regenerate_outfit(db_session, test_user, record, 2, "x", None, use_ai=True)


def test_long_instructions_are_clipped_in_summaries():
    assert assistant_tools.clip("短指令") == "短指令"
    clipped = assistant_tools.clip("将第二套改为更适合约会的搭配：保留简约风格，兼顾比例平衡和舒适")
    assert len(clipped) == 24 and clipped.endswith("…")


@pytest.mark.asyncio
async def test_delete_proposal_names_the_looks(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    record = await report(db_session, test_user)
    ai.script = [call("delete_report", report_id=str(record.id)), say("ok")]
    events = await run(db_session, test_user, conversation, "删除")
    summary = next(e["action"]["summary"] for e in events if e["type"] == "action")
    assert record.result["outfits"][0]["title"][:10] in summary


@pytest.mark.asyncio
async def test_profile_summary_names_catalog_values(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    ai.script = [call("update_profile", styling_profile={"avoided_materials": ["wool"]}), say("ok")]
    events = await run(db_session, test_user, conversation, "别给我推荐羊毛")
    summary = next(e["action"]["summary"] for e in events if e["type"] == "action")
    assert summary.endswith("— → 羊毛") and "wool" not in summary


@pytest.mark.asyncio
async def test_skin_is_summarised_by_its_everyday_name(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    ai.script = [
        call("update_profile", styling_profile={"skin_depth": "tan", "undertone": "warm"}),
        say("ok"),
    ]
    events = await run(db_session, test_user, conversation, "我是黄黑皮")
    summary = next(e["action"]["summary"] for e in events if e["type"] == "action")
    assert summary == "更新资料：肤色: — → 黄黑皮"
    # A pair without an everyday name falls back to the two separate fields.
    ai.script = [call("update_profile", styling_profile={"undertone": "cool"}), say("ok")]
    events = await run(db_session, test_user, conversation, "其实我偏冷")
    summary = next(e["action"]["summary"] for e in events if e["type"] == "action")
    assert "自述底色倾向" in summary and "肤色:" not in summary


def test_every_skin_type_is_a_valid_profile_and_named_in_the_prompt():
    from app.schemas.styling_profile import SKIN_TYPES, StylingProfile, skin_type
    from app.services.assistant_service import SKIN_TYPE_PROMPT

    for key, entry in SKIN_TYPES.items():
        profile = StylingProfile(skin_depth=entry["skin_depth"], undertone=entry["undertone"])
        assert skin_type(profile.model_dump()) == key
        assert entry["zh"] in SKIN_TYPE_PROMPT
    assert len({(e["skin_depth"], e["undertone"]) for e in SKIN_TYPES.values()}) == len(SKIN_TYPES)
