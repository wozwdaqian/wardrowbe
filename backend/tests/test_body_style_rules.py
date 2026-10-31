import json
from copy import deepcopy

import pytest

from app.schemas.body_styling import BodyMeasurements, BodyStyleDraft, BodyStyleRequest
from app.schemas.styling_profile import StylingProfile
from app.services import body_styling_service as service
from app.services.body_style_rules import build_rules, enforce_rules
from tests.body_style_samples import sample_result

MEASUREMENTS = BodyMeasurements(height=175, chest=100, waist=90, hips=102)
COAT = {
    "slot": "outerwear",
    "kind": "coat",
    "color": "#363c41",
    "fit": "regular",
    "length": "long",
    "rise": None,
    "material": "wool",
    "fabric": {
        "construction": "flannel",
        "weight": "heavy",
        "drape": "crisp",
        "sheen": "matte",
        "stretch": "none",
    },
    "fabric_reason": "厚实面料保暖。",
}


def rules_for(measurements=MEASUREMENTS, profile=None, **request):
    return build_rules(measurements, profile or StylingProfile(), BodyStyleRequest(**request))


def check(draft, rules):
    enforce_rules(BodyStyleDraft.model_validate(draft), rules)


def with_coat(draft, index=0):
    draft["outfits"][index]["garments"].insert(2, deepcopy(COAT))
    return draft


def test_sample_passes_default_rules():
    check(sample_result(), rules_for())


def test_summer_rejects_heavy_wool_coat_and_names_the_rule():
    with pytest.raises(ValueError) as error:
        check(with_coat(sample_result()), rules_for(season="summer"))
    message = str(error.value)
    assert "outfit 1" in message
    assert "season summer does not allow outerwear coat" in message
    assert "heavy fabric" in message and "flannel" in message


def test_winter_requires_outerwear_and_bans_shorts():
    rules = rules_for(season="winter")
    with pytest.raises(ValueError, match="requires outerwear"):
        check(sample_result(), rules)
    draft = with_coat(with_coat(with_coat(sample_result()), 1), 2)
    check(draft, rules)
    shorts = draft["outfits"][0]["garments"][1]
    shorts.update(kind="shorts", length="short")
    with pytest.raises(ValueError, match="does not allow bottom shorts"):
        check(draft, rules)


def test_formal_rejects_casual_kinds_and_all_white():
    rules = rules_for(occasion="formal")
    with pytest.raises(ValueError) as error:
        check(sample_result(), rules)
    message = str(error.value)
    # sneakers, polo and jeans are outside the formal vocabulary.
    assert "does not allow shoes sneakers" in message
    assert "does not allow top polo" in message
    assert "does not allow bottom jeans" in message

    draft = sample_result()
    for outfit, top in zip(draft["outfits"], ["shirt", "knit", "shirt"], strict=True):
        outfit["garments"][0]["kind"] = top
        outfit["garments"][0]["fabric"]["construction"] = "knit" if top == "knit" else "poplin"
        outfit["garments"][1]["kind"] = "trousers"
        outfit["garments"][1]["fabric"]["construction"] = "twill"
        outfit["garments"][2]["kind"] = "derbies"
    check(draft, rules)
    for garment in draft["outfits"][0]["garments"]:
        garment["color"] = "#ffffff"
    draft["outfits"][0]["color_plan"] = {"strategy": "tonal", "accent_slots": [], "echo_slots": []}
    with pytest.raises(ValueError, match="must not be all white"):
        check(draft, rules)


def test_work_rejects_shorts_but_daily_allows_them():
    draft = sample_result()
    draft["outfits"][0]["garments"][1].update(kind="shorts", length="short")
    check(draft, rules_for(occasion="daily"))
    with pytest.raises(ValueError, match="occasion work does not allow bottom shorts"):
        check(draft, rules_for(occasion="work"))


def test_avoided_materials_cover_blends_and_denim_construction():
    rules = rules_for(profile=StylingProfile(avoided_materials=["cotton"]))
    assert {"cotton", "cotton_blend", "denim"} <= set(rules.avoided_materials)
    with pytest.raises(ValueError, match="avoided material cotton_blend"):
        check(sample_result(), rules)
    rules = rules_for(profile=StylingProfile(avoided_materials=["denim"]))
    with pytest.raises(ValueError, match="denim construction"):
        check(sample_result(), rules)


def test_avoided_color_family_is_enforced():
    rules = rules_for(profile=StylingProfile(avoided_color_families=["green"]))
    with pytest.raises(ValueError, match="avoided color family"):
        check(sample_result(), rules)


def test_proportion_rules_follow_goals_ratios_and_fit_issues():
    rules = rules_for(goals=["elongate_legs"])
    assert rules.proportion["trouser_rise"].avoid == {"rise": ["low"]}
    assert rules.proportion["top_length"].avoid["length"] == ["long"]
    draft = sample_result()
    draft["outfits"][1]["garments"][1]["rise"] = "low"
    with pytest.raises(ValueError, match=r"outfit 2: trouser_rise rule \(leg_line_goal\)"):
        check(draft, rules)

    short_legs = MEASUREMENTS.model_copy(update={"inseam": 76})
    assert rules_for(short_legs).proportion["trouser_rise"].reasons == ["short_inseam_ratio"]

    # Waist/chest 0.9 alone stays below the midsection threshold.
    assert not rules_for().proportion["top_length"].reasons
    roomy = rules_for(MEASUREMENTS.model_copy(update={"waist": 96}))
    assert roomy.proportion["top_length"].avoid == {"fit": ["slim"]}

    hips = rules_for(MEASUREMENTS.model_copy(update={"waist": 80, "hips": 100}))
    assert hips.proportion["trouser_leg"].avoid == {"fit": ["slim"]}
    issues = rules_for(profile=StylingProfile(fit_issues=["hem_bunches", "shoulders_tight"]))
    assert issues.proportion["trouser_leg"].avoid == {"length": ["long"]}
    assert issues.proportion["outerwear"].avoid == {"fit": ["slim"]}

    narrow = rules_for(MEASUREMENTS.model_copy(update={"shoulder_type": "narrow"}))
    assert narrow.proportion["outerwear"].prefer == {"kind": ["blazer", "suit_jacket", "jacket"]}


def test_rule_ids_are_citable_evidence_only_when_rules_apply():
    facts = service.body_facts(MEASUREMENTS)
    draft = sample_result()
    draft["fit_advice"][1]["evidence"] = ["height", "rule_trouser_rise"]
    rules = rules_for(goals=["elongate_legs"], season="summer")
    assert {"rule_trouser_rise", "rule_season", "rule_occasion"} <= rules.evidence_ids()
    service.parse_result(json.dumps(draft), facts, rules=rules)
    with pytest.raises(ValueError, match="did not provide"):
        service.parse_result(json.dumps(draft), facts, rules=rules_for())
