"""Work dress code and budget from the quiz: weekday styles and brands by price tier."""

import pytest

from app.schemas.body_styling import BodyMeasurements, BodyStyleRequest
from app.schemas.styling_profile import STYLE_DATA, StylingProfile
from app.services.body_style_fallback import direction_for, styles_for, weekday_style
from app.services.body_styling_service import body_facts, prepare_style
from app.services.style_explore import ranked_brands, style_plan

BASE = "/api/v1/body-styling/style-explore"
STYLES = {style["id"]: style for style in STYLE_DATA}


def test_every_brand_has_a_tier():
    for style in STYLE_DATA:
        assert style["brands"]
        assert all(b["tier"] in {"budget", "mid", "premium"} and b["name"] for b in style["brands"])


def test_brands_start_from_the_users_budget_then_the_nearest_tier():
    tiers = [b["tier"] for b in ranked_brands("cityboy", "budget")]
    assert tiers[: tiers.count("budget")] == ["budget"] * tiers.count("budget")
    assert tiers.index("mid") < tiers.index("premium")
    assert ranked_brands("cityboy", None) == STYLES["cityboy"]["brands"]


@pytest.mark.parametrize(
    ("main", "dress_code", "weekday"),
    [
        ("cityboy", "suit", "kireime"),
        ("cityboy", "business_casual", "kireime"),
        ("ivy", "business_casual", "ivy"),
        ("ivy", "suit", "kireime"),
        ("amekaji", "smart_casual", "amekaji"),
        ("ura_street", "smart_casual", "kireime"),
        ("ura_street", "casual", "ura_street"),
        ("cityboy", None, "cityboy"),
    ],
)
def test_weekday_style(main, dress_code, weekday):
    assert weekday_style(main, dress_code) == weekday


def test_plan_names_weekday_and_weekend():
    plan = style_plan("cityboy", "business_casual", True)
    assert plan["weekday"]["id"] == "kireime" and plan["weekend"]["id"] == "cityboy"
    assert plan["switches"]
    assert style_plan("cityboy", None, True) is None
    assert not style_plan("cityboy", "casual", False)["switches"]


def test_work_occasion_follows_the_weekday_style():
    profile = StylingProfile(preferred_styles=["cityboy"], dress_code="business_casual")
    assert styles_for(profile, "work") == ["kireime"]
    assert styles_for(profile, "weekend") == ["cityboy"]
    # Forms default to the main style's family, which still reaches the weekday style.
    assert direction_for(profile, "street", "work") == ["kireime"]
    assert direction_for(profile, "smart_casual", "work") == ["kireime"]
    assert direction_for(profile, "classic", "work") == []
    measurements = BodyMeasurements(height=175, chest=100, waist=90, hips=102)
    _, _, _, snapshot = prepare_style(
        type("U", (), {"styling_profile": profile.model_dump(exclude_none=True)})(),
        measurements,
        BodyStyleRequest(occasion="work", style="street"),
        None,
        "ai",
    )
    assert [s["id"] for s in snapshot["style_direction"]] == ["kireime"]


def test_lifestyle_answers_are_not_body_facts():
    profile = StylingProfile(dress_code="suit", budget="premium", preferred_styles=["mode"])
    measurements = BodyMeasurements(height=175, chest=100, waist=90, hips=102)
    ids = {fact.id for fact in body_facts(measurements, profile)}
    assert not ids & {"dress_code", "budget", "preferred_styles"}


@pytest.mark.asyncio
async def test_result_uses_and_saves_the_lifestyle(client, auth_headers, db_session, test_user):
    answers = {"cityboy:0": "like", "mode:0": "dislike"}
    body = (
        await client.post(
            f"{BASE}/result",
            json={"answers": answers, "dress_code": "suit", "budget": "budget"},
            headers=auth_headers,
        )
    ).json()
    assert body["plan"]["weekday"]["id"] == "kireime" and body["plan"]["switches"]
    assert body["styles"][0]["brands"][0]["tier"] == "budget"
    bad = await client.post(
        f"{BASE}/result", json={"answers": answers, "budget": "cheap"}, headers=auth_headers
    )
    assert bad.status_code == 422

    saved = await client.patch(
        f"{BASE}/styles",
        json={"styles": ["cityboy"], "dress_code": "suit", "budget": "budget"},
        headers=auth_headers,
    )
    assert saved.json()["dress_code"] == "suit"
    await db_session.refresh(test_user)
    assert test_user.styling_profile["dress_code"] == "suit"
    assert test_user.styling_profile["budget"] == "budget"
    # Saving only the styles keeps the lifestyle answers.
    await client.patch(f"{BASE}/styles", json={"styles": ["ivy"]}, headers=auth_headers)
    await db_session.refresh(test_user)
    assert test_user.styling_profile["dress_code"] == "suit"

    today = (
        await client.get(
            "/api/v1/body-styling/today", params={"occasion": "work"}, headers=auth_headers
        )
    ).json()
    assert today["style_direction"] == "kireime"
