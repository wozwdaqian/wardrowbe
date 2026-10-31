import pytest

from app.services.body_style_fallback import rule_based_content
from app.services.body_styling_service import body_facts
from tests.body_style_eval.checks import PERSONAS, mentions, persona_inputs, quality_failures


def test_persona_set_covers_seasons_occasions_and_styles():
    assert len(PERSONAS) == 24
    requests = [p["request"] for p in PERSONAS]
    for field, values in {
        "season": {"spring", "summer", "autumn", "winter"},
        "occasion": {"work", "date", "weekend", "formal"},
        "style": {"minimal", "smart_casual", "street", "sporty", "classic"},
    }.items():
        assert values <= {r.get(field) for r in requests}


@pytest.mark.parametrize("persona", PERSONAS, ids=[p["id"] for p in PERSONAS])
@pytest.mark.parametrize("locale", ["zh-CN", "en"])
@pytest.mark.parametrize("seed", [0, 3])
def test_rule_based_looks_pass_quality_checks(persona, locale, seed):
    measurements, profile, request, rules = persona_inputs(persona)
    facts = body_facts(measurements, profile)
    content = rule_based_content(facts, profile, rules, request.style, locale, seed)
    assert quality_failures(content, rules, locale.startswith("zh")) == []
    for outfit in content.outfits:
        tops = [g.kind for g in outfit.garments if g.slot == "top"]
        assert 1 <= len(tops) <= 2
        if rules.season_rule.requires_outerwear:
            assert any(g.slot == "outerwear" for g in outfit.garments)


@pytest.mark.parametrize(
    ("text", "fact_id", "zh", "expected"),
    [
        ("中腰直筒裤为臀部留出空间。", "hips", True, True),
        ("胸腰之间存在围度差，上衣不收腰。", "waist_chest_ratio", True, True),
        ("上衣不收腰，线条更干净。", "waist_chest_ratio", True, False),
        ("裤长根据内侧腿长试穿调整。", "inseam", True, True),
        ("A clean line from collar to hem.", "chest", False, False),
        ("Room through the seat and hips.", "hips", False, True),
    ],
)
def test_body_reason_paraphrases_count_as_mentioning_evidence(text, fact_id, zh, expected):
    assert mentions(text, fact_id, zh) is expected
