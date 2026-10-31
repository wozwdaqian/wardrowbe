from types import SimpleNamespace

from app.schemas.body_styling import SLOT_KINDS
from app.schemas.styling_profile import StylingProfile
from app.services.recommendation_service import body_style_rule_lines
from app.services.wardrobe_matching import (
    KIND_TYPES,
    avoided_by_profile,
    matches_kind,
    wardrobe_match,
)


def item(**values):
    defaults = {"type": "shirt", "subtype": None, "name": None, "primary_color": None}
    return SimpleNamespace(**{**defaults, "material": None, **values})


def test_every_body_styling_kind_has_a_wardrobe_mapping():
    assert set(KIND_TYPES) == set().union(*SLOT_KINDS.values())


def test_avoidances_cover_blends_and_color_families():
    profile = StylingProfile(avoided_materials=["cotton"], avoided_color_families=["green"])
    assert avoided_by_profile(item(material="denim"), profile)
    assert avoided_by_profile(item(material="canvas"), profile)
    assert avoided_by_profile(item(primary_color="olive"), profile)
    assert not avoided_by_profile(item(material="wool", primary_color="navy"), profile)
    # Unknown vocabulary is never treated as an avoidance.
    assert not avoided_by_profile(item(material="velvet", primary_color="teal"), profile)


def test_kind_matching_uses_subtype_keywords_where_types_are_shared():
    assert matches_kind(item(type="shoes", subtype="penny loafer"), "loafers")
    assert not matches_kind(item(type="shoes", subtype="penny loafer"), "derbies")
    assert matches_kind(item(type="pants"), "trousers")
    assert matches_kind(item(type="coat", name="Beige trench"), "trench")
    assert not matches_kind(item(type="coat"), "trench")


def test_rule_lines_summarise_proportion_and_avoidances():
    lines = body_style_rule_lines(
        {"height": 175, "chest": 100, "waist": 96, "hips": 102},
        StylingProfile(avoided_materials=["wool"], avoided_color_families=["pink"]),
        "office",
        "fall",
    )
    text = "\n".join(lines)
    assert "avoid fit slim" in text and "avoid rise low" in text
    assert "pink" in text and "wool_blend" in text
    # Without measurements only the avoidances remain, and nothing raises.
    assert body_style_rule_lines(None, None, None, None) == []


def report_result():
    from tests.body_style_samples import sample_result

    # Rendered garments only need what matching reads: slot, kind, color and description.
    result = sample_result()
    for outfit in result["outfits"]:
        for garment in outfit["garments"]:
            garment["description"] = f"{garment['kind']} {garment['color']}"
    return result


def owned(kind, color, **values):
    from uuid import uuid4

    return item(
        id=uuid4(),
        type=kind,
        primary_color=color,
        thumbnail_path=None,
        image_path="x.jpg",
        **values,
    )


def test_wardrobe_match_marks_owned_similar_missing_and_ranks_gain():
    # Sample report: green shirt / oatmeal knit / slate polo tops, charcoal trousers & jeans,
    # ivory sneakers and loafers.
    items = [
        owned("shirt", "green", name="Sage shirt"),
        owned("pants", "gray", name="Charcoal trousers"),
        owned("pants", "black"),
        owned("sneakers", "white"),
        owned("shirt", "red", material="wool"),  # avoided below, so unusable
    ]
    match = wardrobe_match(report_result(), items, StylingProfile(avoided_materials=["wool"]))
    assert match["wardrobe_items"] == 4
    assert match["combinations"] == 1 * 2 * 1
    first = match["outfits"][0]["garments"]
    assert [g["status"] for g in first] == ["owned", "owned", "owned"]
    assert first[0]["matches"][0]["name"] == "Sage shirt"
    second = match["outfits"][1]["garments"]
    assert [g["status"] for g in second] == ["missing", "missing", "missing"]
    # A second top doubles the combinations (2x2x1); new shoes too (1x2x2); jeans add one bottom.
    gains = {s["description"].split()[0]: s["gain"] for s in match["suggestions"]}
    assert len(match["suggestions"]) == 2 and set(gains.values()) == {2}
    assert set(gains) <= {"knit", "loafers", "polo"}
