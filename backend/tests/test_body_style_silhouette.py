"""Silhouettes, wearing techniques, proportion remedies, temperature bands and warmth."""

from types import SimpleNamespace

import pytest

from app.schemas.body_styling import (
    BodyMeasurements,
    BodyStyleRequest,
    DraftOutfit,
    needs_anchor,
    normalize_techniques,
    outfit_silhouette,
)
from app.schemas.styling_profile import StylingProfile
from app.services.body_style_fallback import direction_for, rule_based_content, today_outfit
from app.services.body_style_rules import (
    apply_remedies,
    build_rules,
    outfit_violations,
    temperature_band,
)
from app.services.body_styling_service import body_facts
from tests.body_style_samples import sample_result

MEASUREMENTS = BodyMeasurements(height=172, chest=96, waist=84, hips=95)


def g(slot, kind, fit="regular", length="regular", color="#111827"):
    return SimpleNamespace(slot=slot, kind=kind, fit=fit, length=length, color=color)


def outfit(top_fit="regular", top_length="regular", bottom_fit="regular", **bottom):
    return [
        g("top", "shirt", top_fit, top_length, "#ffffff"),
        g("bottom", bottom.get("kind", "chinos"), bottom_fit, bottom.get("length", "regular")),
        g("shoes", "sneakers", color=bottom.get("shoe", "#ffffff")),
    ]


@pytest.mark.parametrize(
    ("top_fit", "top_length", "bottom_fit", "letter"),
    [
        ("regular", "regular", "regular", "I"),
        ("regular", "regular", "wide", "A"),
        ("relaxed", "short", "wide", "A"),  # a boxy cropped top over wide trousers
        ("relaxed", "regular", "tapered", "Y"),
        ("regular", "long", "slim", "Y"),
        ("relaxed", "regular", "wide", "H"),
    ],
)
def test_silhouette_letters(top_fit, top_length, bottom_fit, letter):
    assert outfit_silhouette(outfit(top_fit, top_length, bottom_fit)) == letter


def test_outerwear_sets_the_upper_half():
    garments = outfit("regular", "regular", "wide")
    garments.insert(1, g("outerwear", "coat", "relaxed", "long"))
    assert outfit_silhouette(garments) == "H"


def test_impossible_techniques_are_dropped_and_h_gets_an_anchor():
    tshirt = [g("top", "tshirt", "relaxed"), *outfit("relaxed", "regular", "wide")[1:]]
    # A T-shirt has no cuffs to roll; the H shape gets the first anchor that works.
    kept = normalize_techniques(tshirt, ["roll_cuffs", "tonal_leg"])
    assert "roll_cuffs" not in kept
    assert not needs_anchor(tshirt, kept)
    assert kept[0] == "roll_hem"
    # Ankle-length trousers already anchor it.
    cropped = outfit("relaxed", "regular", "wide", length="short")
    assert normalize_techniques(cropped, []) == []
    # Socks only show once the hem is rolled up.
    with_socks = [*outfit("regular"), g("accessory", "socks", color="#ffffff")]
    assert normalize_techniques(with_socks, ["show_socks"]) == []
    assert normalize_techniques(with_socks, ["roll_hem", "show_socks"]) == [
        "roll_hem",
        "show_socks",
    ]


def test_tonal_leg_needs_the_same_family_and_lightness():
    assert normalize_techniques(outfit(shoe="#111827"), ["tonal_leg"]) == ["tonal_leg"]
    assert normalize_techniques(outfit(shoe="#ffffff"), ["tonal_leg"]) == []


def test_unanchored_h_is_a_rule_violation():
    rules = build_rules(MEASUREMENTS, StylingProfile(), BodyStyleRequest())
    loose = [g("top", "tshirt", "relaxed"), g("bottom", "trousers", "wide"), g("shoes", "boots")]
    for item in loose:
        item.fabric, item.material, item.pattern, item.rise = None, "cotton", "solid", "mid"
    errors = outfit_violations(loose, rules)
    assert any("H silhouette" in e for e in errors)


def test_long_top_is_allowed_for_longer_legs_only_with_a_remedy():
    rules = build_rules(MEASUREMENTS, StylingProfile(), BodyStyleRequest(goals=["elongate_legs"]))
    long_top = outfit("regular", "long")
    for item in long_top:
        item.fabric, item.material, item.pattern, item.rise = None, "cotton", "solid", "mid"
    assert any("top_length" in e for e in outfit_violations(long_top, rules))
    techniques = apply_remedies(long_top, [], rules)
    assert techniques == ["front_tuck"]
    assert not any("top_length" in e for e in outfit_violations(long_top, rules, techniques))


@pytest.mark.parametrize(
    ("temperature", "band"),
    [
        (30, "hot"),
        (26, "hot"),
        (23, "warm"),
        (18, "mild"),
        (12, "cool"),
        (8, "cold"),
        (0, "freezing"),
    ],
)
def test_temperature_bands(temperature, band):
    assert temperature_band(temperature) == band


def test_bands_tighten_the_season_rules():
    freezing = build_rules(
        None, StylingProfile(), BodyStyleRequest(season="winter", temperature_band="freezing")
    )
    assert freezing.season_rule.outerwear_kinds == ["coat", "down_jacket"]
    assert freezing.temperature_band == "freezing"
    assert "rule_season" in freezing.evidence_ids()
    assert freezing.prompt_view()["temperature_band"] == "freezing"
    cool = build_rules(None, StylingProfile(), BodyStyleRequest(temperature_band="cool"))
    assert cool.season_rule.requires_outerwear
    assert "shorts" in cool.season_rule.banned_kinds


@pytest.mark.parametrize("band", ["hot", "warm", "mild", "cool", "cold", "freezing"])
def test_rule_based_outfits_dress_for_the_band(band):
    season = {"hot": "summer", "warm": "summer", "mild": "spring", "cool": "autumn"}.get(
        band, "winter"
    )
    profile = StylingProfile(preferred_styles=["cityboy"])
    request = BodyStyleRequest(style="street", season=season, temperature_band=band)
    rules = build_rules(MEASUREMENTS, profile, request)
    facts = body_facts(MEASUREMENTS, profile)
    content = rule_based_content(
        facts, profile, rules, "street", "zh-CN", 0, direction_for(profile, "street")
    )
    for look in content.outfits:
        outer = [x for x in look.garments if x.slot == "outerwear"]
        if band in {"cold", "freezing"}:
            assert outer and outer[0].kind in rules.season_rule.outerwear_kinds
        if band == "hot":
            assert not outer or outer[0].kind not in {"jacket", "coat"}
        assert look.silhouette in {"I", "A", "Y", "H"}
    today = today_outfit(facts, profile, rules, "street", "zh-CN", 0, ["cityboy"])
    assert today["silhouette"] and isinstance(today["techniques"], list)


def test_warmth_must_agree_across_the_outfit():
    rules = build_rules(None, StylingProfile(), BodyStyleRequest())
    mixed = [
        g("top", "tshirt"),
        g("outerwear", "down_jacket"),
        g("bottom", "shorts", length="short"),
        g("shoes", "sandals"),
    ]
    for item in mixed:
        item.fabric, item.material, item.pattern, item.rise = None, "synthetic", "solid", "mid"
    assert any("warmth" in e for e in outfit_violations(mixed, rules))


def test_draft_outfit_settles_its_own_shape():
    """Whatever the model claims, the silhouette follows the garments and bad techniques go."""
    source = sample_result()["outfits"][0]
    draft = DraftOutfit.model_validate(
        {**source, "silhouette": "H", "techniques": ["show_socks", "show_socks"]}
    )
    shape = [SimpleNamespace(**x.model_dump()) for x in draft.garments]
    assert draft.silhouette == outfit_silhouette(shape)
    assert "show_socks" not in draft.techniques
