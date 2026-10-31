import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.body_styling import BodyMeasurements, BodyStyleDraft, BodyStyleRequest
from app.schemas.styling_profile import StylingProfile
from app.services import body_styling_service as service
from app.services.body_style_rendering import resolve_text
from app.services.body_style_rules import build_rules, enforce_rules
from tests.body_style_samples import sample_result

MEASUREMENTS = BodyMeasurements(height=175, chest=100, waist=90, hips=102)
FACTS = service.body_facts(MEASUREMENTS)


def layer(draft, kind="cardigan", color="#243b55", index=0):
    outfit = draft["outfits"][index]
    mid = deepcopy(outfit["garments"][0])
    mid.update(kind=kind, color=color)
    mid["fabric"]["construction"] = "knit"
    outfit["garments"].insert(1, mid)
    return draft


def accessory(kind, color="#744f37", pattern="solid"):
    return {
        "slot": "accessory",
        "kind": kind,
        "color": color,
        "fit": "regular",
        "length": "regular",
        "rise": None,
        "material": "leather" if kind in {"belt", "watch"} else "synthetic",
        "fabric": None,
        "fabric_reason": "按场合选择。",
        "pattern": pattern,
    }


@pytest.mark.parametrize(
    "text",
    [
        "袖口露出 1 cm 即可。",
        "裤脚卷 2 折即可。",
        "第 1 套更适合通勤。",
        "裤长改短 2.5 厘米，减少堆积。",
        "身高一致的比例更好看。",
    ],
)
def test_tailoring_numbers_and_counts_are_allowed(text):
    assert resolve_text(text, FACTS, None, True) == text


@pytest.mark.parametrize(
    "text",
    [
        "你的腰围一百厘米。",
        "腰围 90 偏宽。",
        "你身高175cm。",
        "腰臀比0.88。",
        "体重 70 公斤。",
        "约占身高60%。",
        "90 厘米的腰围。",
        "The waist is 90 here.",
    ],
)
def test_body_numbers_are_still_rejected(text):
    with pytest.raises(ValueError):
        resolve_text(text, FACTS, None, True)


@pytest.mark.parametrize(
    "text",
    [
        "A light weight jersey keeps the top breathable.",
        "Choose a medium fabric weight for structure.",
        "Check the inseam when trying trousers on.",
    ],
)
def test_garment_weight_and_inseam_words_are_not_body_claims(text):
    assert resolve_text(text, FACTS, None, False) == text


@pytest.mark.parametrize(
    "text", ["Your inseam is short.", "Your weight suits slim cuts.", "You weigh 80 here."]
)
def test_missing_weight_and_inseam_claims_are_rejected(text):
    with pytest.raises(ValueError):
        resolve_text(text, FACTS, None, False)


def test_layered_tops_render_and_count_as_distinct_outfits():
    draft = layer(sample_result())
    result = service.parse_result(json.dumps(draft), FACTS)
    tops = [g for g in result.outfits[0].garments if g.slot == "top"]
    assert [g.kind for g in tops] == ["shirt", "cardigan"]
    assert "开衫" in tops[1].description


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: layer(d, "shirt"), "two tops must be a layer"),
        (lambda d: layer(layer(d)), "one or two tops"),
        (
            lambda d: d["outfits"][0]["garments"][0].update(kind="vest"),
            "vest is a layer",
        ),
        (
            lambda d: d["outfits"][0]["garments"].extend(
                [accessory("belt"), accessory("watch"), accessory("bag")]
            ),
            "at most two accessories",
        ),
        (
            lambda d: d["outfits"][0]["garments"].extend([accessory("belt"), accessory("belt")]),
            "cannot repeat",
        ),
        (
            lambda d: d["outfits"][0]["garments"][2].update(pattern="stripe"),
            "solid pattern",
        ),
    ],
)
def test_layering_accessory_and_pattern_contract(mutate, message):
    draft = sample_result()
    mutate(draft)
    with pytest.raises(ValidationError, match=message):
        BodyStyleDraft.model_validate(draft)


def test_two_accessories_and_new_kinds_are_accepted():
    draft = sample_result()
    garments = draft["outfits"][0]["garments"]
    garments[1].update(kind="chinos")
    garments[2].update(kind="oxfords")
    garments.extend([accessory("watch"), accessory("glasses", "#111827")])
    result = service.parse_result(json.dumps(draft), FACTS)
    kinds = [g.kind for g in result.outfits[0].garments]
    assert kinds == ["shirt", "chinos", "oxfords", "watch", "glasses"]
    assert "卡其裤" in result.outfits[0].garments[1].description


def test_echo_works_across_a_layered_slot():
    draft = layer(sample_result(), color="#efe8dd")
    draft["outfits"][0]["color_plan"] = {
        "strategy": "echo",
        "accent_slots": [],
        "echo_slots": ["top", "shoes"],
    }
    BodyStyleDraft.model_validate(draft)


def test_pattern_is_described_and_limited_to_one_bold_pattern():
    draft = sample_result()
    draft["outfits"][0]["garments"][0]["pattern"] = "stripe"
    result = service.parse_result(json.dumps(draft), FACTS)
    assert result.outfits[0].garments[0].pattern == "stripe"
    assert "条纹" in result.outfits[0].garments[0].description
    draft["outfits"][0]["garments"][1]["pattern"] = "check"
    rules = build_rules(MEASUREMENTS, StylingProfile(), BodyStyleRequest())
    with pytest.raises(ValueError, match="one bold pattern"):
        enforce_rules(BodyStyleDraft.model_validate(draft), rules)
    draft["outfits"][0]["garments"][1]["pattern"] = "herringbone"
    enforce_rules(BodyStyleDraft.model_validate(draft), rules)


def test_new_kinds_follow_season_and_occasion_rules():
    draft = sample_result()
    draft["outfits"][0]["garments"][2]["kind"] = "sandals"
    with pytest.raises(ValueError, match="season winter does not allow shoes sandals"):
        enforce_rules(
            BodyStyleDraft.model_validate(draft),
            build_rules(MEASUREMENTS, StylingProfile(), BodyStyleRequest(season="winter")),
        )
    with pytest.raises(ValueError, match="occasion work does not allow shoes sandals"):
        enforce_rules(
            BodyStyleDraft.model_validate(draft),
            build_rules(MEASUREMENTS, StylingProfile(), BodyStyleRequest(occasion="work")),
        )


def test_old_contract_garments_still_load_without_pattern():
    from app.schemas.body_styling import BodyStyleContent

    stored = service.parse_result(json.dumps(sample_result()), FACTS).model_dump()
    for outfit in stored["outfits"]:
        for garment in outfit["garments"]:
            del garment["pattern"]
    loaded = BodyStyleContent.model_validate(stored)
    assert loaded.outfits[0].garments[0].pattern == "solid"


@pytest.mark.parametrize(
    ("text", "zh", "expected"),
    [
        ("结合腰围{{waist}}与臀围：{{hips}}选裤。", True, "结合腰围 90cm与臀围 102cm选裤。"),
        ("结合{{waist}}选裤。", True, "结合腰围 90cm选裤。"),
        ("Your waist {{waist}} sets the rise.", False, "Your waist 90cm sets the rise."),
    ],
)
def test_label_written_before_its_token_is_not_repeated(text, zh, expected):
    assert resolve_text(text, FACTS, ["waist", "hips"], zh) == expected
