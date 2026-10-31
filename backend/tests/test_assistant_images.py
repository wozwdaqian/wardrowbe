import json
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.models.assistant import AssistantImage
from app.models.item import ClothingItem
from app.models.user import User
from app.schemas.styling_profile import StylingProfile
from app.services import assistant_tools
from app.services.image_service import ImageService
from app.services.wardrobe_matching import purchase_fit
from tests import test_assistant
from tests.test_assistant import BASE, call, run, say, setup

pytestmark = pytest.mark.asyncio
ai = test_assistant.ai  # the scripted-model fixture


def add_item(**arguments):
    # `call` takes the tool name as `name`, which is also one of this tool's arguments.
    step = call("add_wardrobe_item")
    step["tool_calls"][0]["function"]["arguments"] = json.dumps(arguments)
    return step


def jpeg(color=(30, 60, 120), size=(320, 400)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return output.getvalue()


async def upload(client, auth_headers, data=None, name="shirt.jpg", kind="image/jpeg"):
    files = {"image": (name, data if data is not None else jpeg(), kind)}
    return await client.post(f"{BASE}/images", files=files, headers=auth_headers)


async def attached(db_session, user, conversation, ai, *colors, text="帮我看看"):
    """Upload images directly and send them with one message."""
    images = []
    for color in colors:
        paths = await ImageService().process_and_store(user.id, jpeg(color), "x.jpg")
        image = AssistantImage(user_id=user.id, **paths)
        db_session.add(image)
        images.append(image)
    await db_session.commit()
    return images, await run_with_images(db_session, user, conversation, text, images)


async def run_with_images(db_session, user, conversation, text, images):
    from app.services.assistant_service import Assistant

    turn = Assistant(db_session, user).turn(conversation, text, [i.id for i in images])
    return [event async for event in turn]


async def test_upload_returns_signed_urls_and_rejects_non_images(client, auth_headers, db_session):
    response = await upload(client, auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert "/api/v1/images/" in body["thumbnail_url"] and "sig=" in body["url"]
    image = await db_session.get(AssistantImage, body["id"])
    assert image.message_id is None
    bad = await upload(client, auth_headers, b"not an image", "notes.txt", "text/plain")
    assert bad.status_code == 400


async def test_message_accepts_only_own_unsent_images(
    ai, db_session, test_user, client, auth_headers
):
    conversation = await setup(db_session, test_user)
    url = f"{BASE}/conversations/{conversation.id}/messages"
    assert (await client.post(url, json={"content": ""}, headers=auth_headers)).status_code == 422
    unknown = {"content": "看看", "image_ids": [str(uuid4())]}
    assert (await client.post(url, json=unknown, headers=auth_headers)).status_code == 422

    other = User(id=uuid4(), email=f"{uuid4()}@example.com", display_name="Other")
    db_session.add(other)
    await db_session.flush()
    paths = await ImageService().process_and_store(other.id, jpeg(), "x.jpg")
    foreign = AssistantImage(user_id=other.id, **paths)
    db_session.add(foreign)
    await db_session.commit()
    stolen = {"content": "看看", "image_ids": [str(foreign.id)]}
    assert (await client.post(url, json=stolen, headers=auth_headers)).status_code == 422

    own = (await upload(client, auth_headers)).json()["id"]
    ai.script = [say("这件衬衫颜色很稳。")]
    response = await client.post(url, json={"image_ids": [own]}, headers=auth_headers)
    assert response.status_code == 200 and "这件衬衫颜色很稳" in response.text
    # A sent image is attached to its message and cannot be sent again.
    again = await client.post(url, json={"image_ids": [own]}, headers=auth_headers)
    assert again.status_code == 422
    detail = (
        await client.get(f"{BASE}/conversations/{conversation.id}", headers=auth_headers)
    ).json()
    photo_message = next(m for m in detail["messages"] if m["images"])
    assert photo_message["role"] == "user" and photo_message["content"] == ""
    assert photo_message["images"][0]["id"] == own


async def test_model_sees_the_latest_photos_with_the_vision_model(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    ai.script = [say("第一张")]
    first, _ = await attached(db_session, test_user, conversation, ai, (200, 0, 0))
    assert ai.calls[-1]["vision"] is True
    content = ai.calls[-1]["messages"][-1]["content"]
    assert content[0]["type"] == "text" and str(first[0].id) in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    ai.script = [say("第二张")]
    await attached(db_session, test_user, conversation, ai, (0, 200, 0))
    ai.script = [say("第三张")]
    await attached(db_session, test_user, conversation, ai, (0, 0, 200), (9, 9, 9))
    messages = ai.calls[-1]["messages"]
    oldest = next(m for m in messages if m["role"] == "user")
    # Only the two latest photo messages carry pixels; the first is referred to by id.
    assert isinstance(oldest["content"], str) and str(first[0].id) in oldest["content"]
    latest = messages[-1]["content"]
    assert sum(part["type"] == "image_url" for part in latest) == 2

    ai.script = [say("好的")]
    await run(db_session, test_user, conversation, "谢谢")
    assert ai.calls[-1]["vision"] is True  # earlier photos are still in the history


async def test_text_only_conversations_keep_the_text_model(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    ai.script = [say("你好")]
    await run(db_session, test_user, conversation, "你好")
    assert ai.calls[-1]["vision"] is False


async def test_add_wardrobe_item_copies_the_photo_and_undo_removes_it(
    ai, db_session, test_user, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_internal_enabled", True)
    monkeypatch.setattr(settings, "ai_vision_enabled", True)
    queued = []

    async def fake_queue(item_id, image_path):
        queued.append((item_id, image_path))

    monkeypatch.setattr(assistant_tools, "queue_tagging", fake_queue)
    conversation = await setup(db_session, test_user)
    image = AssistantImage(
        user_id=test_user.id,
        **await ImageService().process_and_store(test_user.id, jpeg(), "x.jpg"),
    )
    db_session.add(image)
    await db_session.commit()
    ai.script = [
        add_item(
            image_id=str(image.id),
            type="shirt",
            primary_color="navy",
            material="cotton",
            name="藏青牛津纺衬衫",
        ),
        say("已加入衣橱。"),
    ]
    events = await run_with_images(db_session, test_user, conversation, "把这件加进衣橱", [image])
    action = next(e["action"] for e in events if e["type"] == "action")
    assert action["status"] == "applied" and action["summary"] == "已加入衣橱：藏青牛津纺衬衫"
    assert "id" not in action["result"]  # the card's report link keys on `id`
    item = await db_session.get(ClothingItem, action["result"]["item_id"])
    assert (item.type, item.primary_color, item.material) == ("shirt", "navy", "cotton")
    assert item.image_path != image.image_path
    storage = ImageService()
    assert storage.get_image_path(item.image_path).exists()
    assert queued and queued[0][0] == item.id

    # The same photo again is reported to the model as a duplicate.
    ai.script = [
        call("add_wardrobe_item", image_id=str(image.id), type="shirt"),
        say("这件已经在衣橱里了。"),
    ]
    await run(db_session, test_user, conversation, "再加一次")
    assert "already in the wardrobe" in ai.calls[-1]["messages"][-1]["content"]

    from app.services.assistant_service import Assistant

    path = item.image_path
    undone = await Assistant(db_session, test_user).undo(action["id"])
    assert undone.status == "undone"
    assert await db_session.scalar(select(ClothingItem).where(ClothingItem.id == item.id)) is None
    assert not storage.get_image_path(path).exists()
    assert storage.get_image_path(image.image_path).exists()  # the chat photo stays


async def test_add_wardrobe_item_rejects_foreign_images(ai, db_session, test_user):
    conversation = await setup(db_session, test_user)
    other = User(id=uuid4(), email=f"{uuid4()}@example.com", display_name="Other")
    db_session.add(other)
    await db_session.flush()
    paths = await ImageService().process_and_store(other.id, jpeg(), "x.jpg")
    foreign = AssistantImage(user_id=other.id, **paths)
    db_session.add(foreign)
    await db_session.commit()
    ai.script = [call("add_wardrobe_item", image_id=str(foreign.id), type="shirt"), say("没找到")]
    await run(db_session, test_user, conversation, "加进衣橱")
    assert "no attached image" in ai.calls[-1]["messages"][-1]["content"]
    assert (
        await db_session.scalar(select(ClothingItem.id).where(ClothingItem.user_id == test_user.id))
        is None
    )


def owned(item_type, color, material=None, name=None):
    return SimpleNamespace(
        id=uuid4(), type=item_type, primary_color=color, material=material, name=name or item_type
    )


def test_purchase_fit_flags_avoidances_duplicates_and_new_combinations():
    items = [
        owned("shirt", "white"),
        owned("t-shirt", "navy"),
        owned("pants", "gray"),
        owned("jeans", "blue", "denim"),
        owned("sneakers", "white"),
        owned("sweater", "gray", "wool", "灰色羊毛衫"),
    ]
    profile = StylingProfile(avoided_materials=["wool"], avoided_color_families=["orange"])
    fit = purchase_fit(items, profile, "shirt", "light-blue", "linen")
    assert fit["avoided_by_profile"] == [] and fit["role"] == "base_top"
    # 2 usable tops x 2 bottoms x 1 shoe = 4; a third top adds 2 more.
    assert fit["wardrobe_combinations"] == 4 and fit["adds_combinations"] == 2
    assert fit["similar_owned"] == []
    assert {i["type"] for i in fit["pairs_with"]["bottom"]} == {"pants", "jeans"}
    assert "base_top" not in fit["pairs_with"]

    wool = purchase_fit(items, profile, "sweater", "orange", "wool")
    assert wool["avoided_by_profile"] == ["material:wool", "color:orange"]
    twin = purchase_fit(items, profile, "t-shirt", "blue", "cotton")
    assert [i["type"] for i in twin["similar_owned"]] == ["t-shirt"]
    shoes = purchase_fit(items, profile, "boots", "brown", "leather")
    assert shoes["adds_combinations"] == 4
