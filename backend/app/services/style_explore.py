"""Japanese style exploration: a two-round look quiz that finds the user's sub-styles.

Round one shows one look per sub-style; round two shows two more looks for the three
sub-styles the user liked most. Looks come from `japanese_styles.json` and are rendered with
the same garment captions as reports, after the profile's avoidances are applied: blocked
fibres are swapped by the fallback's material choice, and a look in an avoided colour family
is replaced by another look of the same sub-style when one exists.
"""

import random
from types import SimpleNamespace
from uuid import UUID

from pydantic import ValidationError

from app.schemas.body_styling import (
    BodyMeasurements,
    BodyStyleRequest,
    DraftGarment,
    normalize_techniques,
    outfit_silhouette,
)
from app.schemas.styling_profile import CATALOG, STYLE_DATA, StylingProfile
from app.services.body_style_fallback import _garment
from app.services.body_style_rendering import render_garment
from app.services.body_style_rules import StyleRules, build_rules
from app.services.wardrobe_matching import (
    avoided_by_profile,
    catalog_family,
    item_color_family,
    matches_kind,
)

STYLES = {style["id"]: style for style in STYLE_DATA}
ROUND_TWO_STYLES = 3
POINTS = {"like": 2, "neutral": 0, "dislike": -1}
# With no clear favourite, these two are the easiest places for a beginner to start.
BEGINNER_STYLES = ("kireime", "normcore")
SECONDARY_SHARE = 0.6


def _lang(zh: bool) -> str:
    return "zh" if zh else "en"


def explore_rules(profile: StylingProfile) -> StyleRules:
    # Body proportions are left out: the quiz is about taste, and every look keeps its designed cut.
    return build_rules(None, profile, BodyStyleRequest())


def render_spec(spec: dict, rules: StyleRules, zh: bool) -> dict | None:
    """One garment from the style data, or None when the profile rules it out."""
    garment = _garment(
        spec["slot"], spec["kind"], spec["color"], rules, zh, spec.get("pattern", "solid")
    )
    if garment["material"] is None:
        return None
    if spec["slot"] in {"top", "bottom", "outerwear"}:
        garment["fit"] = spec.get("fit", "regular")
        garment["length"] = "short" if spec["kind"] == "shorts" else spec.get("length", "regular")
    if spec["slot"] == "bottom":
        garment["rise"] = spec.get("rise", "mid")
    construction = spec.get("construction")
    if construction and garment["fabric"]:
        garment["fabric"]["construction"] = construction
    try:
        return render_garment(DraftGarment.model_validate(garment), zh)
    except ValidationError:
        return None


def look_card(
    style_id: str, index: int, rules: StyleRules, profile: StylingProfile, zh: bool
) -> dict | None:
    look = STYLES[style_id]["looks"][index]
    avoided = set(profile.avoided_color_families)
    if any(catalog_family(spec["color"]) in avoided for spec in look["garments"]):
        return None
    garments = [render_spec(spec, rules, zh) for spec in look["garments"]]
    if any(g is None for g in garments):
        return None
    lang = _lang(zh)
    shape = [SimpleNamespace(**g) for g in garments]
    return {
        "id": f"{style_id}:{index}",
        "title": look["title"][lang],
        "tags": look["tags"][lang],
        "garments": garments,
        "techniques": normalize_techniques(shape, look.get("techniques", [])),
        "silhouette": outfit_silhouette(shape),
    }


def usable_cards(style_id: str, rules: StyleRules, profile: StylingProfile, zh: bool) -> list:
    cards = [
        look_card(style_id, index, rules, profile, zh)
        for index in range(len(STYLES[style_id]["looks"]))
    ]
    return [card for card in cards if card is not None]


def card_style(card_id: str) -> str | None:
    style_id = card_id.split(":", 1)[0]
    return style_id if style_id in STYLES else None


def shuffled(cards: list, user_id: UUID, salt: str) -> list:
    # Stable per user, so reloading the page keeps the order.
    random.Random(f"{user_id}:{salt}").shuffle(cards)
    return cards


def round_one(user_id: UUID, profile: StylingProfile, zh: bool) -> list[dict]:
    rules = explore_rules(profile)
    cards = []
    for style_id in STYLES:
        usable = usable_cards(style_id, rules, profile, zh)
        if usable:
            cards.append(usable[0])
    return shuffled(cards, user_id, "one")


def points(answers: dict[str, str]) -> dict[str, int]:
    totals = dict.fromkeys(STYLES, 0)
    for card_id, answer in answers.items():
        style_id = card_style(card_id)
        if style_id and answer in POINTS:
            totals[style_id] += POINTS[answer]
    return totals


def ranked(totals: dict[str, int]) -> list[str]:
    order = list(STYLES)
    return sorted(STYLES, key=lambda s: (-totals[s], order.index(s)))


def round_two(
    user_id: UUID, profile: StylingProfile, zh: bool, answers: dict[str, str]
) -> list[dict]:
    rules = explore_rules(profile)
    totals = points(answers)
    liked = [s for s in ranked(totals) if totals[s] > 0][:ROUND_TWO_STYLES]
    # Nothing liked yet: compare the gentlest starting points instead.
    top = liked or [s for s in ranked(totals) if totals[s] >= 0][:ROUND_TWO_STYLES]
    cards = [
        card
        for style_id in top
        for card in usable_cards(style_id, rules, profile, zh)
        if card["id"] not in answers
    ][: ROUND_TWO_STYLES * 2]
    return shuffled(cards, user_id, "two")


def body_note(measurements: BodyMeasurements | None) -> dict | None:
    """Silhouette hints from Japanese style guides; a reference, never a verdict."""
    if measurements is None or not measurements.weight:
        return None
    bmi = measurements.weight / (measurements.height / 100) ** 2
    if bmi >= 26:
        return {"kind": "solid", "styles": ["workwear", "yamakei", "cityboy", "amekaji"]}
    if measurements.height >= 178 and bmi < 21:
        return {"kind": "tall_slim", "styles": ["kireime", "mode", "ivy"]}
    return None


def liked_colors(answers: dict[str, str], zh: bool) -> list[str]:
    counts: dict[str, int] = {}
    for card_id, answer in answers.items():
        style_id = card_style(card_id)
        if answer != "like" or style_id is None:
            continue
        index = int(card_id.split(":", 1)[1])
        for spec in STYLES[style_id]["looks"][index]["garments"]:
            family = catalog_family(spec["color"])
            counts[family] = counts.get(family, 0) + 1
    top = sorted(counts, key=lambda f: -counts[f])[:3]
    return [CATALOG["color_families"][family]["zh" if zh else "en"] for family in top]


def starter_pieces(style_id: str, items: list, profile: StylingProfile, zh: bool) -> list:
    rules = explore_rules(profile)
    usable = [item for item in items if not avoided_by_profile(item, profile)]
    pieces = []
    for spec in STYLES[style_id]["starter"]:
        garment = render_spec(spec, rules, zh)
        if garment is None:
            continue
        same_kind = [item for item in usable if matches_kind(item, spec["kind"])]
        family = catalog_family(spec["color"])
        owned = [item for item in same_kind if item_color_family(item) == family]
        matches = owned or same_kind
        pieces.append(
            {
                "description": garment["description"],
                "kind": spec["kind"],
                "color": spec["color"],
                "status": "owned" if owned else "similar" if same_kind else "missing",
                "matches": [{"id": str(item.id), "name": item.name} for item in matches[:2]],
            }
        )
    return pieces


def style_detail(style_id: str, items: list, profile: StylingProfile, zh: bool) -> dict:
    style = STYLES[style_id]
    lang = _lang(zh)
    rules = explore_rules(profile)
    sample = next(iter(usable_cards(style_id, rules, profile, zh)), None)
    return {
        "id": style_id,
        "base_style": style["base_style"],
        "name": style["name"][lang],
        "name_ja": style["name"]["ja"],
        "tagline": style["tagline"][lang],
        "description": style["description"][lang],
        "keywords": style["keywords"][lang],
        "tips": style["tips"][lang],
        "pitfalls": style["pitfalls"][lang],
        "search": style["search"],
        "brands": style["brands"],
        "starter": starter_pieces(style_id, items, profile, zh),
        "sample": sample,
    }


def explore_result(
    answers: dict[str, str],
    profile: StylingProfile,
    measurements: BodyMeasurements | None,
    items: list,
    zh: bool,
) -> dict:
    totals = points(answers)
    order = ranked(totals)
    best = max(totals[order[0]], 0)
    lang = _lang(zh)
    ranking = [
        {
            "id": style_id,
            "name": STYLES[style_id]["name"][lang],
            "tagline": STYLES[style_id]["tagline"][lang],
            "score": round(100 * max(totals[style_id], 0) / best) if best else 0,
        }
        for style_id in order
    ]
    if best:
        chosen = [order[0]]
        runner_up = totals[order[1]]
        if runner_up > 0 and runner_up >= SECONDARY_SHARE * best:
            chosen.append(order[1])
    else:
        chosen = list(BEGINNER_STYLES)
    return {
        "confident": bool(best),
        "styles": [style_detail(style_id, items, profile, zh) for style_id in chosen],
        "ranking": ranking,
        "liked_colors": liked_colors(answers, zh),
        "body_note": body_note(measurements),
    }
