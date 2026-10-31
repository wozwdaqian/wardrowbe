from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.models.item import ClothingItem
from app.schemas.body_styling import BodyMeasurements
from app.schemas.styling_profile import StylingProfile
from app.services import body_style_packing as packing

BASE = "/api/v1/body-styling/packing"
MEASUREMENTS = BodyMeasurements(height=175, chest=100, waist=90, hips=102)


def trip(start: date, occasions: list[str], season: str, temp_min=None):
    return [
        {
            "date": (start + timedelta(days=n)).isoformat(),
            "occasion": occasions[n % len(occasions)],
            "season": season,
            "temp_min": temp_min,
            "temp_max": None if temp_min is None else temp_min + 6,
        }
        for n in range(5)
    ]


@pytest.mark.parametrize("season,temp", [("winter", 0), ("summer", 25), ("autumn", 12)])
def test_every_day_is_dressed_within_its_rules_with_fewer_pieces_than_outfits(season, temp):
    days = trip(date(2026, 10, 5), ["work", "work", "formal", "weekend"], season, temp)
    plan = packing.plan_trip(MEASUREMENTS, StylingProfile(), "minimal", days, "en")
    assert [d["warnings"] for d in plan["days"]] == [[]] * 5
    worn = sum(len(d["pieces"]) for d in plan["days"])
    assert len(plan["pieces"]) < worn
    for day in plan["days"]:
        slots = {plan["pieces"][i]["slot"] for i in day["pieces"]}
        assert {"top", "bottom", "shoes"} <= slots
    # Every piece lists exactly the days it is worn.
    for piece in plan["pieces"]:
        assert piece["days"] == [d["date"] for d in plan["days"] if piece["index"] in d["pieces"]]


def test_avoidances_hold_for_every_packed_piece():
    profile = StylingProfile(avoided_materials=["wool"], avoided_color_families=["blue"])
    plan = packing.plan_trip(
        MEASUREMENTS, profile, "classic", trip(date(2026, 1, 5), ["formal"], "winter", 0), "en"
    )
    assert plan["pieces"] and all(not d["warnings"] for d in plan["days"])
    for piece in plan["pieces"]:
        assert packing.catalog_family(piece["color"]) != "blue"
        assert piece["material"] not in {"wool", "wool_blend"}


def test_owned_items_are_matched_by_kind_and_color_family():
    pieces = [
        {"kind": "trousers", "color": "#363c41"},
        {"kind": "loafers", "color": "#744f37"},
    ]
    items = [
        SimpleNamespace(
            id=1, type="pants", subtype=None, name="Grey trousers", primary_color="gray"
        ),
        SimpleNamespace(id=2, type="pants", subtype=None, name="Navy", primary_color="navy"),
    ]
    packing.match_owned(pieces, items)
    assert pieces[0]["owned"] == {"id": "1", "name": "Grey trousers", "same_color": True}
    assert pieces[1]["owned"] is None


@pytest.mark.asyncio
async def test_packing_endpoint_validates_and_uses_wardrobe(
    client, db_session, test_user, auth_headers, monkeypatch
):
    async def no_forecast(*args):
        return {}

    monkeypatch.setattr(packing, "trip_forecast", no_forecast)
    db_session.add(
        ClothingItem(user_id=test_user.id, type="pants", primary_color="gray", image_path="p.jpg")
    )
    await db_session.commit()
    start = date(2026, 12, 1)
    response = await client.post(
        BASE,
        headers=auth_headers,
        json={
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=3)).isoformat(),
            "occasions": ["work", "weekend"],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["days"]) == 4 and data["forecast_days"] == 0
    assert {d["season"] for d in data["days"]} == {"winter"}
    assert any(p["owned"] for p in data["pieces"])
    too_long = await client.post(
        BASE,
        headers=auth_headers,
        json={"start_date": "2026-12-01", "end_date": "2027-01-30"},
    )
    assert too_long.status_code == 422
    backwards = await client.post(
        BASE,
        headers=auth_headers,
        json={"start_date": "2026-12-05", "end_date": "2026-12-01"},
    )
    assert backwards.status_code == 422
