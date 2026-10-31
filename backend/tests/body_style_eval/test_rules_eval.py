import pytest

from app.services.body_style_fallback import rule_based_content
from app.services.body_styling_service import body_facts
from tests.body_style_eval.checks import PERSONAS, persona_inputs, quality_failures


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
