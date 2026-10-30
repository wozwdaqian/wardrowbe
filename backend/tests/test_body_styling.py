import json
from copy import deepcopy
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError

from app.config import get_settings
from app.models.body_styling import BodyStyleRecommendation
from app.models.user import User
from app.schemas.body_styling import BodyMeasurements
from app.schemas.styling_profile import StylingProfile
from app.services import body_styling_service as service
from app.services.ai_service import TextGenerationResult
from app.utils.body_measurements import body_revision
from tests.body_style_samples import sample_result

BASE = "/api/v1/body-styling"
MEASUREMENTS = {"height": 175, "chest": 100, "waist": 90, "hips": 102}


def test_facts_are_computed_without_inventing_missing_fields():
    facts = {f.id: f.value for f in service.body_facts(BodyMeasurements(**MEASUREMENTS))}
    assert facts["waist_chest_ratio"] == 0.9
    assert facts["waist_hips_ratio"] == 0.882
    assert not {"inseam", "inseam_height_ratio", "weight", "shoulder_type"} & facts.keys()
    more = {
        f.id: f.value
        for f in service.body_facts(
            BodyMeasurements(**MEASUREMENTS, inseam=80, shoulder_type="broad")
        )
    }
    assert more["inseam_height_ratio"] == 0.457
    assert more["shoulder_type"] == "broad"


@pytest.mark.parametrize(
    "changes",
    [
        {"height": True},
        {"chest": "100"},
        {"waist": 0},
        {"hips": -1},
        {"weight": float("nan")},
        {"inseam": 175},
    ],
)
def test_invalid_measurements(changes):
    with pytest.raises(ValidationError):
        BodyMeasurements(**(MEASUREMENTS | changes))


@pytest.mark.parametrize(
    "change",
    [
        "unknown_evidence",
        "missing_shoes",
        "invalid_kind",
        "unsafe_color",
        "missing_rise",
        "repeated_outfits",
        "missing_area",
        "unsupported_shoe_fit",
        "shorts_length",
        "unsupported_description",
        "fabricated_number",
        "fabricated_written_number",
        "missing_fact_token",
        "uncited_fact_token",
        "missing_field_claim",
    ],
)
def test_invalid_model_results_are_rejected(change):
    result = sample_result()
    if change == "unknown_evidence":
        result["outfits"][0]["evidence"] = ["inseam_height_ratio"]
    elif change == "missing_shoes":
        result["outfits"][0]["garments"].pop()
    elif change == "invalid_kind":
        result["outfits"][0]["garments"][0]["kind"] = "imaginary-shirt"
    elif change == "unsafe_color":
        result["outfits"][0]["garments"][0]["color"] = "url(https://example.com)"
    elif change == "missing_rise":
        result["outfits"][0]["garments"][1]["rise"] = None
    elif change == "repeated_outfits":
        result["outfits"][1] = deepcopy(result["outfits"][0])
    elif change == "missing_area":
        result["fit_advice"][0]["area"] = "outerwear"
    elif change == "unsupported_shoe_fit":
        result["outfits"][0]["garments"][2]["fit"] = "wide"
    elif change == "shorts_length":
        result["outfits"][0]["garments"][1]["kind"] = "shorts"
    elif change == "unsupported_description":
        result["outfits"][0]["garments"][0]["description"] = "红色修身长款衬衫，下摆覆盖臀部。"
    elif change == "fabricated_number":
        result["observations"][0]["text"] = "你的内腿长为105cm，占身高60%。"
        result["observations"][0]["evidence"] = ["height"]
    elif change == "fabricated_written_number":
        result["observations"][0]["text"] = "你的腰围一百厘米。"
    elif change == "missing_fact_token":
        result["summary"] = "根据{{inseam}}选择裤长。"
    elif change == "uncited_fact_token":
        result["observations"][0]["text"] = "根据{{height}}选择裤长。"
    elif change == "missing_field_claim":
        result["summary"] = "你的内腿长偏长，应选择修身裤。"
    with pytest.raises(ValueError):
        service.parse_result(
            json.dumps(result), service.body_facts(BodyMeasurements(**MEASUREMENTS))
        )


def test_accepts_json_fence_and_preserves_visual_attributes():
    result = service.parse_result(
        "```json\n" + json.dumps(sample_result()) + "\n```",
        service.body_facts(BodyMeasurements(**MEASUREMENTS)),
    )
    assert result.outfits[0].garments[1].rise == "high"
    assert len(result.outfits) == 3


def test_fact_tokens_and_garment_captions_are_resolved_from_the_same_data():
    facts = service.body_facts(BodyMeasurements(**(MEASUREMENTS | {"height": 188, "waist": 82})))
    result = service.parse_result(json.dumps(sample_result(188, 82)), facts)
    assert "身高 188cm" in result.summary
    assert "腰围 82cm" in result.outfits[0].body_reason
    assert "175" not in result.summary
    top = result.outfits[0].garments[0]
    assert top.color == "#718575"
    assert top.color_name == "鼠尾草绿"
    assert "鼠尾草绿" in top.description and "合体" in top.description
    assert "下摆至腰线" in top.description
    assert "红色" not in top.description and "修身" not in top.description
    assert len(result.unknowns) == 6
    english = service.parse_result(json.dumps(sample_result()), facts, "en")
    assert "height 188cm" in english.summary
    assert "sage green" in english.outfits[0].garments[0].description.lower()


def test_body_revision_normalizes_jsonb_numbers_and_key_order():
    assert body_revision({"height": 175, "waist": 82}) == body_revision(
        {"waist": 82.0, "height": 175.0}
    )
    assert body_revision({"waist": 82}) != body_revision({"waist": 90})


@pytest_asyncio.fixture
async def setup_style(monkeypatch, db_session, test_user):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_internal_enabled", True)
    monkeypatch.setattr(settings, "ai_text_enabled", True)
    monkeypatch.setattr(settings, "ai_base_url", "http://styling-test.invalid/v1")
    monkeypatch.setattr(settings, "ai_text_model", "fixture-text")
    test_user.body_measurements = MEASUREMENTS.copy()
    test_user.locale = "zh-CN"
    await db_session.commit()
    mocked = Mock()
    mocked.generate_text = AsyncMock(
        return_value=TextGenerationResult(
            content=json.dumps(sample_result()), model="fixture-text", endpoint="fixture"
        )
    )
    monkeypatch.setattr(service, "AIService", Mock(return_value=mocked))
    return mocked


@pytest.mark.asyncio
async def test_empty_wardrobe_generation_history_snapshot_and_ownership(
    client, db_session, test_user, auth_headers, setup_style
):
    response = await client.post(BASE + "/recommendations", headers=auth_headers, json={})
    assert response.status_code == 201, response.text
    report = response.json()
    assert len(report["result"]["outfits"]) == 3
    assert report["input_snapshot"]["context"]["goals"] == ["balance", "comfort"]
    sent = json.loads(setup_style.generate_text.call_args.args[0])
    assert sent["input"]["measurements"] == MEASUREMENTS
    assert sent["language"] == "Simplified Chinese"
    assert "wardrobe" not in sent["input"]
    test_user.body_measurements = MEASUREMENTS | {"waist": 80}
    await db_session.commit()
    detail = await client.get(BASE + "/recommendations/" + report["id"], headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["input_snapshot"]["measurements"]["waist"] == 90
    history = (await client.get(BASE + "/recommendations", headers=auth_headers)).json()
    assert history["total"] == 1
    assert history["items"][0]["id"] == report["id"]
    assert (
        await client.get(BASE + "/recommendations/" + str(uuid4()), headers=auth_headers)
    ).status_code == 404
    # Another owner cannot read, even when the UUID is known.
    record = await db_session.get(BodyStyleRecommendation, report["id"])
    other = User(id=uuid4(), email=f"{uuid4()}@example.com", display_name="Other")
    db_session.add(other)
    await db_session.flush()
    record.user_id = other.id
    await db_session.commit()
    assert (
        await client.get(BASE + "/recommendations/" + report["id"], headers=auth_headers)
    ).status_code == 404
    assert (await client.get(BASE + "/recommendations", headers=auth_headers)).json()["total"] == 0


@pytest.mark.asyncio
async def test_body_inputs_change_actual_prompt_facts(
    client, db_session, test_user, auth_headers, setup_style
):
    test_user.body_measurements = {
        "height": 188,
        "chest": 110,
        "waist": 82,
        "hips": 100,
        "inseam": 93,
    }
    await db_session.commit()
    assert (
        await client.post(
            BASE + "/recommendations", headers=auth_headers, json={"goals": ["elongate_legs"]}
        )
    ).status_code == 201
    sent = json.loads(setup_style.generate_text.call_args.args[0])
    values = {f["id"]: f["value"] for f in sent["facts"]}
    assert values["waist_chest_ratio"] == 0.745
    assert values["inseam_height_ratio"] == 0.495
    assert sent["input"]["context"]["goals"] == ["elongate_legs"]


@pytest.mark.asyncio
async def test_repairs_bad_model_json_once(client, auth_headers, setup_style):
    setup_style.generate_text.side_effect = [
        TextGenerationResult(content="not json", model="fixture-text", endpoint="fixture"),
        setup_style.generate_text.return_value,
    ]
    assert (
        await client.post(BASE + "/recommendations", headers=auth_headers, json={})
    ).status_code == 201
    assert setup_style.generate_text.call_count == 2
    assert "Repair this invalid response" in setup_style.generate_text.call_args.args[0]


@pytest.mark.asyncio
async def test_repairs_fabricated_measurement_before_saving(client, auth_headers, setup_style):
    bad = sample_result()
    bad["observations"][0] = {"text": "你的内腿长为105cm，占身高60%。", "evidence": ["height"]}
    setup_style.generate_text.side_effect = [
        TextGenerationResult(content=json.dumps(bad), model="fixture-text", endpoint="fixture"),
        setup_style.generate_text.return_value,
    ]
    response = await client.post(BASE + "/recommendations", headers=auth_headers, json={})
    assert response.status_code == 201
    assert setup_style.generate_text.call_count == 2
    assert "105" not in json.dumps(response.json())
    assert (await client.get(BASE + "/recommendations", headers=auth_headers)).json()["total"] == 1


@pytest.mark.asyncio
async def test_stale_profile_cannot_overwrite_new_values_or_generate(
    client, auth_headers, setup_style
):
    original = (await client.get("/api/v1/users/me", headers=auth_headers)).json()
    revision = original["body_measurements_revision"]
    latest = MEASUREMENTS | {"waist": 82, "weight": 78, "shirt_size": "L"}
    response = await client.patch(
        "/api/v1/users/me", headers=auth_headers, json={"body_measurements": latest}
    )
    assert response.status_code == 200
    new_revision = response.json()["body_measurements_revision"]
    assert revision != new_revision
    stale = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={
            "body_measurements": MEASUREMENTS,
            "expected_body_measurements_revision": revision,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "body_measurements_conflict"
    assert (await client.get("/api/v1/users/me", headers=auth_headers)).json()[
        "body_measurements"
    ] == latest
    # An update between save and generation must also refuse the stale generation.
    response = await client.post(
        BASE + "/recommendations",
        headers=auth_headers,
        json={"body_measurements_revision": revision},
    )
    assert response.status_code == 409
    setup_style.generate_text.assert_not_called()
    # Unrelated language changes do not invalidate the body revision.
    response = await client.patch("/api/v1/users/me", headers=auth_headers, json={"locale": "en"})
    assert response.json()["body_measurements_revision"] == new_revision
    response = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={
            "body_measurements": latest | {"waist": 84},
            "expected_body_measurements_revision": new_revision,
        },
    )
    assert response.status_code == 200
    generated = await client.post(
        BASE + "/recommendations",
        headers=auth_headers,
        json={
            "body_measurements_revision": response.json()["body_measurements_revision"],
        },
    )
    assert generated.status_code == 201
    assert generated.json()["input_snapshot"]["measurements"]["waist"] == 84


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,code,status",
    [
        ("invalid", "invalid_ai_response", 502),
        ("timeout", "ai_timeout", 504),
        ("service", "ai_failed", 502),
    ],
)
async def test_failed_generation_does_not_save_history(
    client, db_session, test_user, auth_headers, setup_style, failure, code, status
):
    if failure == "invalid":
        setup_style.generate_text.return_value = TextGenerationResult(
            content="{}", model="fixture-text", endpoint="fixture"
        )
    elif failure == "timeout":
        setup_style.generate_text.side_effect = httpx.ReadTimeout("test")
    else:
        setup_style.generate_text.side_effect = RuntimeError("provider failed")
    response = await client.post(BASE + "/recommendations", headers=auth_headers, json={})
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert (await client.get(BASE + "/recommendations", headers=auth_headers)).json()["total"] == 0
    assert setup_style.generate_text.call_count == (2 if failure == "invalid" else 1)


@pytest.mark.asyncio
async def test_disabled_ai_still_allows_profile_and_history(
    client, test_user, auth_headers, setup_style, monkeypatch
):
    monkeypatch.setattr(get_settings(), "ai_text_enabled", False)
    assert (await client.get(BASE + "/status", headers=auth_headers)).json()["available"] is False
    assert (await client.get(BASE + "/recommendations", headers=auth_headers)).status_code == 200
    assert (
        await client.patch(
            "/api/v1/users/me", headers=auth_headers, json={"body_measurements": MEASUREMENTS}
        )
    ).status_code == 200
    response = await client.post(BASE + "/recommendations", headers=auth_headers, json={})
    assert response.status_code == 503
    setup_style.generate_text.assert_not_called()


@pytest.mark.asyncio
async def test_unconfigured_ai_is_reported(client, auth_headers, setup_style, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_base_url", "")
    state = (await client.get(BASE + "/status", headers=auth_headers)).json()
    assert state == {"enabled": True, "configured": False, "available": False}


@pytest.mark.asyncio
async def test_missing_profile_fields_refuse_generation(
    client, db_session, test_user, auth_headers, setup_style
):
    test_user.body_measurements = {"height": 175}
    await db_session.commit()
    response = await client.post(BASE + "/recommendations", headers=auth_headers, json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_measurements"
    setup_style.generate_text.assert_not_called()


@pytest.mark.asyncio
async def test_authentication_and_history_pagination(client, auth_headers, setup_style):
    assert (await client.get(BASE + "/recommendations")).status_code == 401
    assert (await client.post(BASE + "/recommendations", json={})).status_code == 401
    assert (
        await client.get(BASE + "/recommendations?limit=0", headers=auth_headers)
    ).status_code == 422
    assert (
        await client.post(BASE + "/recommendations", headers=auth_headers, json={"goals": []})
    ).status_code == 422


@pytest.mark.parametrize(
    "data",
    [
        {"skin_depth": "infer-from-race"},
        {"undertone": "definitely-yellow"},
        {"preferred_color_families": ["red"], "avoided_color_families": ["red"]},
        {"avoided_materials": ["wool", "wool"]},
        {"fabric_preferences": ["hypoallergenic-guarantee"]},
    ],
)
def test_invalid_styling_preferences_are_rejected(data):
    with pytest.raises(ValidationError):
        StylingProfile(**data)


@pytest.mark.parametrize(
    "case",
    [
        "green_family",
        "avoided_fiber",
        "blend",
        "fabric_missing",
        "jeans_weave",
        "false_echo",
        "missing_accent_slot",
        "missing_color_reason",
        "fake_skin",
        "unprovided_skin_token",
        "fake_undertone",
        "fake_hair",
        "denim_as_cotton",
    ],
)
def test_color_and_fabric_contract_rejects_conflicts(case):
    draft = sample_result()
    profile = StylingProfile()
    if case == "green_family":
        profile = StylingProfile(avoided_color_families=["green"])
        draft["outfits"][0]["garments"][0]["color"] = "#3e5143"
    elif case == "avoided_fiber":
        profile = StylingProfile(avoided_materials=["cotton"])
    elif case == "blend":
        profile = StylingProfile(avoided_materials=["wool"])
        draft["outfits"][0]["garments"][0]["material"] = "wool_blend"
    elif case == "fabric_missing":
        draft["outfits"][0]["garments"][0]["fabric"] = None
    elif case == "jeans_weave":
        draft["outfits"][1]["garments"][1]["fabric"]["construction"] = "poplin"
    elif case == "false_echo":
        draft["outfits"][0]["color_plan"] = {
            "strategy": "echo",
            "accent_slots": [],
            "echo_slots": ["top", "shoes"],
        }
    elif case == "missing_accent_slot":
        draft["outfits"][0]["color_plan"]["accent_slots"] = ["outerwear"]
    elif case == "missing_color_reason":
        del draft["outfits"][0]["color_reason"]
    elif case == "fake_skin":
        draft["color_guidance"]["text"] = "你的肤色很白，适合所有颜色。"
    elif case == "unprovided_skin_token":
        draft["color_guidance"] = {
            "text": "根据{{skin_depth}}安排配色。",
            "evidence": ["skin_depth"],
        }
    elif case == "fake_undertone":
        profile = StylingProfile(skin_depth="medium")
        draft["color_guidance"]["text"] = "你的肤色偏暖，因此只推荐暖色。"
    elif case == "fake_hair":
        draft["color_guidance"]["text"] = "你的黑发适合这组颜色。"
    elif case == "denim_as_cotton":
        profile = StylingProfile(avoided_materials=["denim"])
        draft["outfits"][1]["garments"][1]["material"] = "cotton"
    with pytest.raises(ValueError):
        service.parse_result(
            json.dumps(draft),
            service.body_facts(BodyMeasurements(**MEASUREMENTS), profile),
            profile=profile,
        )


def test_personal_facts_are_self_reported_and_textile_details_remain_controlled():
    profile = StylingProfile(
        skin_depth="medium",
        undertone="warm",
        hair_color="black",
        preferred_color_families=["blue"],
        avoided_materials=["wool"],
        fabric_preferences=["breathable"],
    )
    facts = service.body_facts(
        BodyMeasurements(**MEASUREMENTS, shoulder_width=46, thigh=58), profile
    )
    draft = sample_result()
    draft["color_guidance"] = {
        "text": "参考{{skin_depth}}、{{undertone}}与{{hair_color}}，比较上衣明暗效果。",
        "evidence": ["skin_depth", "undertone", "hair_color"],
    }
    draft["outfits"][0]["garments"][0]["fabric_reason"] = (
        "依据：fabric_preferences，比较厚薄与手感。"
    )
    result = service.parse_result(json.dumps(draft), facts, profile=profile)
    assert "中等" in result.color_guidance.text and "偏暖" in result.color_guidance.text
    assert any(f.id == "shoulder_width" and f.value == 46 for f in facts)
    assert result.outfits[0].garments[0].fabric.construction == "poplin"
    assert "中等厚度" in result.outfits[0].garments[0].fabric_summary
    assert result.outfits[0].garments[0].material_code == "cotton"
    assert "fabric_preferences" not in result.outfits[0].garments[0].fabric_reason
    assert "面料偏好" in result.outfits[0].garments[0].fabric_reason
    assert not any("肤色深浅或底色倾向尚不明确" in item for item in result.unknowns)


@pytest.mark.asyncio
async def test_profile_preferences_are_validated_and_conflict_protected(
    client, auth_headers, setup_style
):
    original = (await client.get("/api/v1/users/me", headers=auth_headers)).json()
    update = {
        "skin_depth": "tan",
        "undertone": "neutral",
        "hair_color": "black",
        "avoided_materials": ["wool"],
        "avoided_color_families": ["red"],
        "fit_issues": ["thighs_tight"],
    }
    saved = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={
            "styling_profile": update,
            "expected_styling_profile_revision": original["styling_profile_revision"],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["body_measurements"] == original["body_measurements"]
    assert saved.json()["styling_profile"]["skin_depth"] == "tan"
    assert saved.json()["styling_profile_revision"] != original["styling_profile_revision"]
    stale = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={
            "styling_profile": {"skin_depth": "fair"},
            "expected_styling_profile_revision": original["styling_profile_revision"],
        },
    )
    assert stale.status_code == 409
    generation = await client.post(
        BASE + "/recommendations",
        headers=auth_headers,
        json={"styling_profile_revision": original["styling_profile_revision"]},
    )
    assert generation.status_code == 409
    setup_style.generate_text.assert_not_called()
    invalid = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={"styling_profile": {"skin_depth": "not-a-choice"}},
    )
    assert invalid.status_code == 422
    generated = await client.post(
        BASE + "/recommendations",
        headers=auth_headers,
        json={"styling_profile_revision": saved.json()["styling_profile_revision"]},
    )
    assert generated.status_code == 201
    report = generated.json()
    assert report["input_snapshot"]["styling_profile"]["undertone"] == "neutral"
    assert report["input_snapshot"]["contract_version"] == 2
    sent = json.loads(setup_style.generate_text.call_args.args[0])
    assert sent["input"]["styling_profile"]["avoided_color_families"] == ["red"]
    await client.patch(
        "/api/v1/users/me", headers=auth_headers, json={"styling_profile": {"undertone": "cool"}}
    )
    old = (await client.get(BASE + "/recommendations/" + report["id"], headers=auth_headers)).json()
    assert old["input_snapshot"]["styling_profile"]["undertone"] == "neutral"


@pytest.mark.asyncio
async def test_feedback_is_owned_preserved_and_used_in_future_prompt(
    client, auth_headers, setup_style, db_session, test_user
):
    report = (await client.post(BASE + "/recommendations", headers=auth_headers, json={})).json()
    url = BASE + "/recommendations/" + report["id"]
    response = await client.patch(
        url + "/feedback", headers=auth_headers, json={"outfit_index": 0, "colors": "like"}
    )
    assert response.status_code == 200
    await client.patch(
        url + "/feedback", headers=auth_headers, json={"outfit_index": 1, "fabrics": "dislike"}
    )
    detail = (await client.get(url, headers=auth_headers)).json()
    assert len(detail["feedback"]["outfits"]) == 2
    assert (
        detail["result"] == report["result"]
        and detail["input_snapshot"] == report["input_snapshot"]
    )
    assert (
        await client.post(BASE + "/recommendations", headers=auth_headers, json={})
    ).status_code == 201
    sent = json.loads(setup_style.generate_text.call_args.args[0])
    assert len(sent["input"]["recent_feedback"]) == 2
    assert sent["input"]["recent_feedback"][0]["ratings"]["colors"] == "like"
    assert (
        await client.patch(
            url + "/feedback", headers=auth_headers, json={"outfit_index": 3, "overall": "like"}
        )
    ).status_code == 422
    await client.patch(url + "/feedback", headers=auth_headers, json={"outfit_index": 0})
    assert len((await client.get(url, headers=auth_headers)).json()["feedback"]["outfits"]) == 1
    await client.patch(url + "/feedback", headers=auth_headers, json={"outfit_index": 1})
    assert (await client.get(url, headers=auth_headers)).json()["feedback"] is None
    assert not await service.recent_style_feedback(db_session, test_user.id)
    await client.patch(
        url + "/feedback", headers=auth_headers, json={"outfit_index": 1, "colors": "like"}
    )
    assert len(await service.recent_style_feedback(db_session, test_user.id)) == 1
    other = User(id=uuid4(), email=f"{uuid4()}@example.com", display_name="Other")
    db_session.add(other)
    await db_session.flush()
    record = await db_session.get(BodyStyleRecommendation, report["id"])
    record.user_id = other.id
    await db_session.commit()
    assert (
        await client.patch(
            url + "/feedback", headers=auth_headers, json={"outfit_index": 0, "colors": "like"}
        )
    ).status_code == 404
    assert not await service.recent_style_feedback(db_session, test_user.id)


@pytest.mark.asyncio
async def test_legacy_reports_still_load_without_new_fields(
    client, auth_headers, db_session, test_user
):
    old = service.parse_result(
        json.dumps(sample_result()), service.body_facts(BodyMeasurements(**MEASUREMENTS))
    ).model_dump()
    for key in ("color_guidance", "fabric_guidance"):
        old.pop(key)
    for outfit in old["outfits"]:
        for key in ("color_plan", "color_reason", "fabric_reason"):
            outfit.pop(key)
        for garment in outfit["garments"]:
            for key in (
                "fabric",
                "fabric_summary",
                "fabric_reason",
                "material_code",
                "color_family",
            ):
                garment.pop(key)
    record = BodyStyleRecommendation(
        user_id=test_user.id,
        input_snapshot={"measurements": MEASUREMENTS, "context": {}},
        facts=[f.model_dump() for f in service.body_facts(BodyMeasurements(**MEASUREMENTS))],
        result=old,
        model="legacy-model",
    )
    db_session.add(record)
    await db_session.commit()
    response = await client.get(BASE + "/recommendations/" + str(record.id), headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["result"]["summary"] == old["summary"]
    assert response.json()["result"]["color_guidance"] is None
    assert response.json()["result"]["outfits"][0]["garments"][0]["fabric"] is None
