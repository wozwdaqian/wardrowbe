import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import get_settings
from app.services import body_style_today as today_service

BASE = "/api/v1/body-styling/today"


@pytest.fixture
def weather(monkeypatch):
    state = {"value": None}

    async def fake(user):
        return state["value"]

    monkeypatch.setattr(today_service, "current_weather", fake)
    return state


@pytest.mark.parametrize(
    "day,temperature,season",
    [
        (date(2026, 7, 10), None, "summer"),
        (date(2026, 1, 10), None, "winter"),
        (date(2026, 4, 10), None, "spring"),
        (date(2026, 10, 10), None, "autumn"),
        (date(2026, 4, 10), 30, "summer"),
        (date(2026, 10, 10), 3, "winter"),
        (date(2026, 7, 10), 14, "spring"),
        (date(2026, 1, 10), 20, "autumn"),
    ],
)
def test_season_follows_weather_then_calendar(day, temperature, season):
    assert today_service.season_for(day, temperature) == season


@pytest.mark.asyncio
async def test_new_user_without_measurements_location_or_ai_gets_a_look(
    client, test_user, auth_headers, weather, db_session
):
    test_user.body_measurements = None
    await db_session.commit()
    response = await client.get(BASE, headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["has_measurements"] is False and data["weather"] is None
    assert data["occasion"] in {"work", "weekend"}
    assert data["wardrobe_ready"] is False
    outfit = data["outfit"]
    assert {"top", "bottom", "shoes"} <= {g["slot"] for g in outfit["garments"]}
    assert outfit["body_reason"] and "{{" not in outfit["body_reason"]
    assert not any(key.startswith("_") for key in data)


@pytest.mark.asyncio
async def test_same_day_is_stable_and_reroll_changes_the_look(
    client, test_user, auth_headers, weather, db_session
):
    test_user.body_measurements = {"height": 175, "chest": 100, "waist": 90, "hips": 102}
    await db_session.commit()
    params = {"occasion": "work", "style": "classic"}
    first = (await client.get(BASE, headers=auth_headers, params=params)).json()
    again = (await client.get(BASE, headers=auth_headers, params=params)).json()
    assert first["outfit"] == again["outfit"]
    assert "175" in first["outfit"]["body_reason"]
    looks = {
        json.dumps(
            (await client.get(BASE, headers=auth_headers, params={**params, "reroll": n})).json()[
                "outfit"
            ]["garments"]
        )
        for n in range(1, 5)
    }
    assert len(looks) > 1


@pytest.mark.asyncio
async def test_hot_weather_never_gets_a_coat(client, auth_headers, weather):
    weather["value"] = SimpleNamespace(temperature=31, condition="sunny")
    for reroll in range(6):
        data = (
            await client.get(
                BASE, headers=auth_headers, params={"occasion": "formal", "reroll": reroll}
            )
        ).json()
        assert data["season"] == "summer" and data["weather"]["temperature"] == 31
        kinds = {g["kind"] for g in data["outfit"]["garments"]}
        assert not kinds & {"coat", "down_jacket", "trench", "turtleneck", "boots"}
        assert data["temperature_band"] == "hot"
        assert data["outfit"]["silhouette"] in {"I", "A", "Y", "H"}


@pytest.mark.asyncio
async def test_freezing_weather_gets_a_coat_or_down(client, auth_headers, weather):
    weather["value"] = SimpleNamespace(temperature=-2, condition="snowy")
    for reroll in range(4):
        data = (
            await client.get(
                BASE, headers=auth_headers, params={"occasion": "daily", "reroll": reroll}
            )
        ).json()
        assert data["temperature_band"] == "freezing"
        outer = [g["kind"] for g in data["outfit"]["garments"] if g["slot"] == "outerwear"]
        assert outer and outer[0] in {"coat", "down_jacket"}


@pytest.mark.asyncio
async def test_explain_needs_ai_and_rejects_fabricated_numbers(
    client, test_user, auth_headers, weather, db_session, monkeypatch
):
    assert (await client.post(BASE + "/explain", headers=auth_headers)).status_code == 503
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_base_url", "http://styling-test.invalid/v1")
    monkeypatch.setattr(settings, "ai_text_model", "fixture-text")
    test_user.body_measurements = {"height": 175, "chest": 100, "waist": 90, "hips": 102}
    await db_session.commit()
    mocked = Mock()
    mocked.generate_text = AsyncMock(
        return_value=json.dumps(
            {"text": "按{{height}}安排上下比例，适合今天的通勤。", "evidence": ["height"]}
        )
    )
    monkeypatch.setattr(today_service, "AIService", Mock(return_value=mocked))
    response = await client.post(BASE + "/explain", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "175cm" in response.json()["text"] and "{{" not in response.json()["text"]
    mocked.generate_text.return_value = json.dumps({"text": "你身高175cm。", "evidence": []})
    assert (await client.post(BASE + "/explain", headers=auth_headers)).status_code == 502
