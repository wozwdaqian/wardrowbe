from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.item import ClothingItem
from app.schemas.body_styling import BodyMeasurements, DraftGarment
from app.schemas.styling_profile import StylingProfile, styling_revision
from app.services import style_explore
from app.services.body_style_rules import outfit_violations
from app.services.body_styling_service import body_facts, prepare_style
from app.services.style_explore import (
    STYLES,
    explore_result,
    explore_rules,
    round_one,
    round_two,
    usable_cards,
)

BASE = "/api/v1/body-styling/style-explore"


def test_every_look_and_starter_piece_renders_and_follows_the_rules():
    profile = StylingProfile()
    rules = explore_rules(profile)
    for style_id, style in STYLES.items():
        cards = usable_cards(style_id, rules, profile, True)
        assert len(cards) == len(style["looks"]) == 3, style_id
        for card in cards:
            garments = [
                DraftGarment.model_validate(
                    {k: g[k] for k in DraftGarment.model_fields if k in g}
                    | {"material": g["material_code"]}
                )
                for g in card["garments"]
            ]
            assert outfit_violations(garments, rules, card["techniques"]) == [], card["id"]
        assert len(style["starter"]) >= 5
        for lang in ("zh", "en"):
            assert style["name"][lang] and style["description"][lang] and style["tips"][lang]


def test_round_one_has_one_look_per_style_in_a_stable_order():
    user = uuid4()
    cards = round_one(user, StylingProfile(), True)
    assert sorted(c["id"].split(":")[0] for c in cards) == sorted(STYLES)
    assert [c["id"] for c in round_one(user, StylingProfile(), True)] == [c["id"] for c in cards]
    assert all(c["title"] and c["tags"] for c in cards)


def test_avoided_colours_and_fibres_change_the_looks_shown():
    profile = StylingProfile(avoided_color_families=["black"], avoided_materials=["denim"])
    cards = round_one(uuid4(), profile, True)
    shown = {c["id"].split(":")[0]: c for c in cards}
    assert "mode" not in shown  # every mode look is black
    for card in cards:
        assert all(g["color_family"] != "black" for g in card["garments"])
        assert all(g["material_code"] != "denim" for g in card["garments"])
    assert shown["amekaji"]["id"] == "amekaji:2"  # the first two looks use jeans or black


def test_round_two_digs_into_the_three_favourites():
    answers = {
        "cityboy:0": "like",
        "natural:0": "like",
        "workwear:0": "neutral",
        "kireime:0": "dislike",
        "yamakei:0": "like",
        "mode:0": "dislike",
    }
    cards = round_two(uuid4(), StylingProfile(), False, answers)
    styles = {c["id"].split(":")[0] for c in cards}
    assert styles == {"cityboy", "natural", "yamakei"}
    assert len(cards) == 6 and not set(answers) & {c["id"] for c in cards}


def test_result_picks_main_and_close_second_style_with_starter_checklist():
    items = [
        SimpleNamespace(
            id=uuid4(),
            type="shirt",
            subtype=None,
            name="浅蓝衬衫",
            primary_color="light-blue",
            material="cotton",
        ),
        SimpleNamespace(
            id=uuid4(),
            type="sneakers",
            subtype=None,
            name="黑球鞋",
            primary_color="black",
            material="leather",
        ),
    ]
    answers = {
        "cityboy:0": "like",
        "cityboy:1": "like",
        "cityboy:2": "like",
        "natural:0": "like",
        "natural:1": "like",
        "mode:0": "dislike",
    }
    result = explore_result(answers, StylingProfile(), None, items, True)
    assert result["confident"] is True
    assert [s["id"] for s in result["styles"]] == ["cityboy", "natural"]
    assert result["ranking"][0] == {
        "id": "cityboy",
        "name": "Cityboy 城市男孩",
        "tagline": STYLES["cityboy"]["tagline"]["zh"],
        "score": 100,
    }
    assert result["ranking"][1]["score"] == 67
    starter = {p["kind"]: p for p in result["styles"][0]["starter"]}
    assert starter["shirt"]["status"] == "owned"
    assert starter["sneakers"]["status"] == "similar"  # owned, but black not white
    assert starter["chinos"]["status"] == "missing"
    assert result["styles"][0]["sample"]["id"] == "cityboy:0"
    assert result["liked_colors"][0] == "白色系"


def test_result_without_any_like_suggests_beginner_styles_and_body_hint():
    answers = {"mode:0": "dislike", "ura_street:0": "neutral"}
    heavy = BodyMeasurements(height=172, chest=106, waist=98, hips=104, weight=82)
    result = explore_result(answers, StylingProfile(), heavy, [], False)
    assert result["confident"] is False
    assert [s["id"] for s in result["styles"]] == ["kireime", "normcore"]
    assert result["body_note"]["kind"] == "solid"
    slim = BodyMeasurements(height=182, chest=90, waist=72, hips=88, weight=64)
    assert style_explore.body_note(slim)["kind"] == "tall_slim"
    assert (
        style_explore.body_note(BodyMeasurements(height=175, chest=96, waist=82, hips=95)) is None
    )


def test_preferred_styles_do_not_change_existing_revisions_or_body_facts():
    measurements = {"height": 175, "chest": 100, "waist": 90, "hips": 102}
    assert styling_revision(measurements, {}) == styling_revision(
        measurements, {"preferred_styles": []}
    )
    profile = StylingProfile(preferred_styles=["cityboy"])
    facts = body_facts(BodyMeasurements(**measurements), profile)
    assert "preferred_styles" not in {f.id for f in facts}
    with pytest.raises(ValueError):
        StylingProfile(preferred_styles=["cityboy", "cityboy"])
    with pytest.raises(ValueError):
        StylingProfile(preferred_styles=["not_a_style"])


def test_ai_input_carries_the_style_direction():
    user = SimpleNamespace(styling_profile={"preferred_styles": ["ivy", "kireime"]}, locale="zh-CN")
    from app.schemas.body_styling import BodyStyleRequest

    _, _, _, snapshot = prepare_style(
        user,
        BodyMeasurements(height=175, chest=100, waist=90, hips=102),
        BodyStyleRequest(),
        None,
        "ai",
    )
    assert [d["id"] for d in snapshot["style_direction"]] == ["ivy", "kireime"]
    assert "oxford cloth" in snapshot["style_direction"][0]["keywords"]


@pytest.mark.asyncio
async def test_api_runs_the_quiz_and_saves_the_style(client, auth_headers, db_session, test_user):
    test_user.locale = "zh-CN"
    test_user.body_measurements = {"height": 175, "chest": 100, "waist": 90, "hips": 102}
    db_session.add(
        ClothingItem(
            user_id=test_user.id,
            type="shirt",
            primary_color="light-blue",
            name="浅蓝衬衫",
            image_path="s.jpg",
        )
    )
    await db_session.commit()
    first = (await client.get(f"{BASE}/round-one", headers=auth_headers)).json()["cards"]
    assert len(first) == len(STYLES)
    answers = {card["id"]: "neutral" for card in first}
    answers["ivy:0"] = "like"
    second = await client.post(f"{BASE}/round-two", json={"answers": answers}, headers=auth_headers)
    assert {c["id"].split(":")[0] for c in second.json()["cards"]} >= {"ivy"}
    bad = await client.post(
        f"{BASE}/round-two", json={"answers": {"x": "love"}}, headers=auth_headers
    )
    assert bad.status_code == 422

    result = await client.post(f"{BASE}/result", json={"answers": answers}, headers=auth_headers)
    body = result.json()
    assert body["styles"][0]["id"] == "ivy" and body["styles"][0]["name"] == "日式常春藤 · 学院"
    shirt = next(p for p in body["styles"][0]["starter"] if p["kind"] == "shirt")
    assert shirt["status"] == "owned" and shirt["matches"][0]["name"] == "浅蓝衬衫"

    saved = await client.patch(f"{BASE}/styles", json={"styles": ["ivy"]}, headers=auth_headers)
    assert saved.json()["preferred_styles"] == ["ivy"]
    await db_session.refresh(test_user)
    assert test_user.styling_profile["preferred_styles"] == ["ivy"]
    unknown = await client.patch(f"{BASE}/styles", json={"styles": ["nope"]}, headers=auth_headers)
    assert unknown.status_code == 422

    today = (await client.get("/api/v1/body-styling/today", headers=auth_headers)).json()
    assert today["style"] == "classic" and today["style_direction"] == "ivy"
