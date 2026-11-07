"""Rule-based reports and today's outfit follow the Japanese sub-style the quiz found."""

import itertools

import pytest
from pydantic import ValidationError

from app.schemas.body_styling import BodyMeasurements, BodyStyleRequest, DraftGarment
from app.schemas.styling_profile import STYLE_DATA, StylingProfile
from app.services.body_style_fallback import (
    direction_for,
    rule_based_content,
    rule_based_draft,
    today_outfit,
)
from app.services.body_style_rules import build_rules
from app.services.body_styling_service import body_facts

MEASUREMENTS = BodyMeasurements(height=172, chest=96, waist=84, hips=95)
STYLES = {style["id"]: style for style in STYLE_DATA}


def setup(styles, profile=None, **request):
    profile = StylingProfile.model_validate({"preferred_styles": styles, **(profile or {})})
    request = BodyStyleRequest(style=STYLES[styles[0]]["base_style"], **request)
    rules = build_rules(MEASUREMENTS, profile, request)
    return profile, request, rules, body_facts(MEASUREMENTS, profile)


def draft_for(styles, seed=0, profile=None, **request):
    profile, request, rules, facts = setup(styles, profile, **request)
    direction = direction_for(profile, request.style)
    return rule_based_draft(facts, profile, rules, request.style, True, seed, direction)


def kinds(outfit):
    return {g["kind"] for g in outfit["garments"]}


def test_cityboy_report_uses_its_own_looks_not_generic_street():
    draft = draft_for(["cityboy"])
    titles = [o["title"] for o in draft["outfits"]]
    assert titles == [look["title"]["zh"] for look in STYLES["cityboy"]["looks"]]
    first = draft["outfits"][0]
    assert {"overshirt", "bucket_hat", "socks"} <= kinds(first)
    chinos = next(g for g in first["garments"] if g["kind"] == "chinos")
    assert (chinos["fit"], chinos["length"]) == ("tapered", "short")
    assert "Cityboy" in draft["summary"]
    # Ankle-length trousers with socks get the matching tip.
    assert "袜子" in first["styling_tip"]


def test_second_style_supplies_the_third_look():
    draft = draft_for(["amekaji", "workwear"])
    assert draft["outfits"][2]["title"] == STYLES["workwear"]["looks"][0]["title"]["zh"]


def test_an_explicit_other_broad_style_keeps_generic_looks():
    profile = StylingProfile(preferred_styles=["cityboy"])
    assert direction_for(profile, "classic") == []
    assert direction_for(profile, "street") == ["cityboy"]
    assert direction_for(StylingProfile(), "street") == []


def test_corduroy_is_kept_in_autumn_and_swapped_out_in_summer():
    def ivy_chinos(season):
        outfit = draft_for(["ivy"], season=season)["outfits"][2]
        return next(g for g in outfit["garments"] if g["kind"] == "chinos")

    assert ivy_chinos("autumn")["fabric"]["construction"] == "corduroy"
    assert ivy_chinos("summer")["fabric"]["construction"] != "corduroy"


def test_avoided_colour_is_replaced_and_title_no_longer_claims_it():
    draft = draft_for(["amekaji"], profile={"avoided_color_families": ["blue"]})
    for outfit in draft["outfits"]:
        assert all(g["color"] not in {"#2b3a67", "#243b55"} for g in outfit["garments"])
    assert draft["outfits"][0]["title"] != STYLES["amekaji"]["looks"][0]["title"]["zh"]


@pytest.mark.parametrize("style_id", list(STYLES))
def test_every_style_validates_across_occasions_and_seasons(style_id):
    for occasion, season, seed in itertools.product(
        ["daily", "work", "date", "weekend", "formal"],
        ["all", "spring", "summer", "autumn", "winter"],
        [0, 5],
    ):
        profile, request, rules, facts = setup([style_id], occasion=occasion, season=season)
        direction = direction_for(profile, request.style)
        content = rule_based_content(facts, profile, rules, request.style, "zh-CN", seed, direction)
        assert len(content.outfits) == 3
        today = today_outfit(facts, profile, rules, request.style, "en", seed, direction)
        assert today["garments"]


def test_today_outfit_uses_a_style_look():
    profile, request, rules, facts = setup(["kireime"], occasion="work", season="autumn")
    today = today_outfit(
        facts, profile, rules, request.style, "zh-CN", 0, direction_for(profile, request.style)
    )
    assert today["title"] == STYLES["kireime"]["looks"][0]["title"]["zh"]


def test_tapered_is_only_for_trousers():
    base = {
        "color": "#ffffff",
        "length": "regular",
        "material": "cotton",
        "fabric": {
            "construction": "oxford",
            "weight": "medium",
            "drape": "balanced",
            "sheen": "matte",
            "stretch": "none",
        },
        "fabric_reason": "测试。",
    }
    with pytest.raises(ValidationError):
        DraftGarment.model_validate({**base, "slot": "top", "kind": "shirt", "fit": "tapered"})
    DraftGarment.model_validate(
        {
            **base,
            "slot": "bottom",
            "kind": "chinos",
            "fit": "tapered",
            "rise": "mid",
            "fabric": {**base["fabric"], "construction": "twill"},
        }
    )


def test_kireime_looks_follow_their_own_pitfall_against_tight_slim_fits():
    for look in STYLES["kireime"]["looks"]:
        assert all(g.get("fit") != "slim" for g in look["garments"])
