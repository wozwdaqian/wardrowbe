"""Rule-based outfits when no AI is configured, or when a fast, free suggestion is wanted.

The draft is assembled from `StyleRules` and the catalog, then passes through the same
`parse_result` validation and rendering as an AI draft, so both modes share one contract.
"""

import json
import random

from pydantic import ValidationError

from app.schemas.body_styling import SLOT_KINDS, BodyFact, BodyStyleContent, DraftOutfit
from app.schemas.styling_profile import CATALOG, StylingProfile
from app.services.body_style_rendering import COLORS, FITS, KINDS, LENGTHS, RISES
from app.services.body_style_rules import StyleRules, outfit_violations

NEUTRALS = {"white", "grey", "black", "beige", "brown"}
# Ordered fallbacks: the first material/construction that the rules allow is used.
MATERIALS = {
    "tshirt": ["cotton", "lyocell", "synthetic"],
    "polo": ["cotton", "cotton_blend", "synthetic"],
    "shirt": ["cotton", "linen", "lyocell", "synthetic"],
    "turtleneck": ["wool_blend", "cotton", "synthetic"],
    "knit": ["wool", "cotton", "wool_blend", "synthetic"],
    "sweatshirt": ["cotton", "cotton_blend", "synthetic"],
    "hoodie": ["cotton", "cotton_blend", "synthetic"],
    "cargo_pants": ["cotton", "cotton_blend", "synthetic"],
    "fleece": ["synthetic"],
    "cardigan": ["wool_blend", "cotton", "synthetic"],
    "vest": ["wool_blend", "cotton", "synthetic"],
    "trousers": ["wool_blend", "linen_blend", "cotton_blend", "synthetic"],
    "chinos": ["cotton", "cotton_blend", "lyocell", "synthetic"],
    "jeans": ["denim", "cotton", "lyocell"],
    "shorts": ["cotton", "linen", "synthetic"],
    "blazer": ["wool_blend", "linen_blend", "cotton", "synthetic"],
    "suit_jacket": ["wool", "wool_blend", "synthetic"],
    "jacket": ["cotton", "synthetic"],
    "overshirt": ["cotton", "wool_blend", "synthetic"],
    "coat": ["wool", "wool_blend", "synthetic"],
    "trench": ["cotton", "synthetic"],
    "down_jacket": ["synthetic"],
}
LEATHER = ["leather", "vegan_leather", "synthetic"]
CONSTRUCTIONS = {
    "tshirt": ["jersey"],
    "polo": ["pique", "jersey"],
    "shirt": ["oxford", "poplin", "linen_weave"],
    "turtleneck": ["knit", "jersey"],
    "knit": ["knit"],
    "sweatshirt": ["fleece", "jersey"],
    "hoodie": ["fleece", "jersey"],
    "cargo_pants": ["twill", "canvas"],
    "fleece": ["fleece"],
    "cardigan": ["knit"],
    "vest": ["twill", "knit"],
    "trousers": ["twill"],
    "chinos": ["twill"],
    "jeans": ["denim_weave"],
    "shorts": ["twill", "linen_weave"],
    "blazer": ["twill", "linen_weave"],
    "suit_jacket": ["twill"],
    "jacket": ["canvas", "technical"],
    "overshirt": ["flannel", "twill", "canvas"],
    "coat": ["flannel", "twill"],
    "trench": ["twill", "technical"],
    "down_jacket": ["technical"],
    "scarf": ["knit"],
}
# Three looks per style: (base top, mid layer or None, bottom, shoes).
LOOKS = {
    "minimal": [
        ("tshirt", None, "trousers", "sneakers"),
        ("shirt", None, "chinos", "loafers"),
        ("turtleneck", None, "trousers", "derbies"),
    ],
    "smart_casual": [
        ("shirt", None, "chinos", "loafers"),
        ("polo", None, "trousers", "derbies"),
        ("shirt", "knit", "trousers", "loafers"),
    ],
    "street": [
        ("tshirt", None, "jeans", "sneakers"),
        ("tshirt", "sweatshirt", "trousers", "sneakers"),
        ("shirt", None, "jeans", "boots"),
    ],
    "sporty": [
        ("tshirt", None, "trousers", "sneakers"),
        ("polo", None, "shorts", "sneakers"),
        ("tshirt", "sweatshirt", "jeans", "sneakers"),
    ],
    "classic": [
        ("shirt", None, "trousers", "derbies"),
        ("shirt", "vest", "trousers", "oxfords"),
        ("turtleneck", None, "trousers", "loafers"),
    ],
}
OUTERWEAR = {
    "all": ["blazer", "jacket", "overshirt"],
    "spring": ["trench", "jacket", "blazer"],
    "summer": ["overshirt", "blazer"],
    "autumn": ["overshirt", "trench", "blazer"],
    "winter": ["coat", "down_jacket", "blazer"],
}
SUBSTITUTES = {
    "top": ["shirt", "knit", "turtleneck", "polo", "tshirt"],
    "bottom": ["trousers", "chinos", "jeans"],
    "shoes": ["derbies", "loafers", "oxfords", "sneakers", "boots", "sandals"],
}


def _text(zh: bool, chinese: str, english: str) -> str:
    return chinese if zh else english


def _allowed(rules: StyleRules, slot: str, kind: str) -> bool:
    if kind == "jeans" and "denim" in rules.avoided_materials:
        return False
    if _material(kind, slot, rules) is None:
        return False
    return (
        kind in rules.occasion_rule.allowed_kinds.get(slot, [])
        and kind not in rules.season_rule.banned_kinds
    )


def _kind(rules: StyleRules, slot: str, wanted: str) -> str:
    if _allowed(rules, slot, wanted):
        return wanted
    for kind in SUBSTITUTES[slot]:
        if _allowed(rules, slot, kind):
            return kind
    return next(k for k in sorted(SLOT_KINDS[slot]) if _allowed(rules, slot, k))


def _avoided(rules: StyleRules, slot: str, attribute: str) -> set[str]:
    return {
        v
        for rule in rules.proportion.values()
        if rule.slot == slot
        for v in rule.avoid.get(attribute, [])
    }


def _choose(values: list[str], rules: StyleRules, slot: str, attribute: str, default: str) -> str:
    avoid = _avoided(rules, slot, attribute)
    prefer = [
        v
        for rule in rules.proportion.values()
        if rule.slot == slot
        for v in rule.prefer.get(attribute, [])
    ]
    for value in [*prefer, default, *values]:
        if value in values and value not in avoid:
            return value
    return default


def _material(kind: str, slot: str, rules: StyleRules) -> str | None:
    options = LEATHER if slot in {"shoes", "accessory"} else MATERIALS[kind]
    if kind == "scarf":
        options = ["wool", "cotton", "synthetic"]
    if kind == "tie":
        options = ["silk", "wool", "synthetic"]
    if kind in {"cap", "bag"}:
        options = ["cotton", "leather", "synthetic"]
    if kind == "glasses":
        options = ["synthetic"]
    if rules.season == "summer":
        # Breathable fibers first in summer; the order is otherwise kept.
        cool = ["linen", "linen_blend", "cotton", "lyocell"]
        options = [m for m in cool if m in options] + [m for m in options if m not in cool]
    blocked = set(rules.avoided_materials) | set(rules.season_rule.banned_materials)
    return next((m for m in options if m not in blocked), None)


def _fabric(kind: str, slot: str, material: str, rules: StyleRules) -> dict | None:
    if slot in {"shoes", "accessory"} or material in {"leather", "vegan_leather"}:
        return None
    banned = set(rules.season_rule.banned_constructions)
    if "denim" in rules.avoided_materials:
        banned.add("denim_weave")
    options = [c for c in CONSTRUCTIONS[kind] if c not in banned]
    if material in {"linen", "linen_blend"} and "linen_weave" not in banned:
        options.insert(0, "linen_weave")
    elif "linen_weave" in options and len(options) > 1:
        options.remove("linen_weave")
    construction = options[0] if options else "technical"
    season = rules.season
    weight = (
        "light"
        if season == "summer"
        else "heavy"
        if season == "winter" and slot == "outerwear"
        else "medium"
    )
    return {
        "construction": construction,
        "weight": weight,
        "drape": "crisp" if slot == "outerwear" or kind == "shirt" else "balanced",
        "sheen": "matte",
        "stretch": "slight" if slot == "bottom" else "none",
    }


class Palette:
    def __init__(self, profile: StylingProfile, rules: StyleRules, rng: random.Random):
        avoided = set(rules.avoided_color_families)
        colors = [(hex_, c) for hex_, c in CATALOG["colors"].items() if c["family"] not in avoided]
        preferred = set(profile.preferred_color_families)
        self.neutrals = [h for h, c in colors if c["family"] in NEUTRALS]
        chromatic = [h for h, c in colors if c["family"] not in NEUTRALS]
        rng.shuffle(chromatic)
        rng.shuffle(self.neutrals)
        chromatic.sort(key=lambda h: CATALOG["colors"][h]["family"] not in preferred)
        self.chromatic = chromatic
        self.lightness = {h: c["lightness"] for h, c in colors}

    def dark(self, exclude=()):
        return self._pick(lambda h: self.lightness[h] == "dark", exclude)

    def light(self, exclude=()):
        return self._pick(lambda h: self.lightness[h] == "light", exclude)

    def _pick(self, condition, exclude):
        # Neutrals first; when the user avoids them, a matching chromatic color stands in.
        candidates = [h for h in [*self.neutrals, *self.chromatic] if h not in exclude]
        candidates = candidates or [*self.neutrals, *self.chromatic]
        return next((h for h in candidates if condition(h)), candidates[0])


def _garment(slot, kind, color, rules, zh, pattern="solid"):
    fits = ["slim", "regular", "relaxed", "wide"]
    lengths = ["short", "regular", "long"]
    material = _material(kind, slot, rules)
    g = {
        "slot": slot,
        "kind": kind,
        "color": color,
        "fit": "regular",
        "length": "regular",
        "rise": None,
        "material": material,
        "pattern": pattern,
        "fabric": _fabric(kind, slot, material, rules),
        "fabric_reason": _text(
            zh,
            "按季节和场合选择厚薄与组织，购买时核对标签和手感。",
            "Weight and weave follow the season and occasion; check the label and hand-feel when buying.",
        ),
    }
    if slot in {"top", "outerwear"}:
        g["fit"] = _choose(fits[:3], rules, slot, "fit", "regular")
        g["length"] = _choose(lengths, rules, slot, "length", "regular")
    if kind in {"coat", "trench"}:
        g["length"] = "regular" if "long" in _avoided(rules, slot, "length") else "long"
    if slot == "bottom":
        g["fit"] = _choose(fits, rules, slot, "fit", "regular")
        g["length"] = (
            "short" if kind == "shorts" else _choose(lengths, rules, slot, "length", "regular")
        )
        g["rise"] = _choose(["low", "mid", "high"], rules, slot, "rise", "mid")
    return g


def _outfit(index, look, rules, palette, zh, available, used_tops):
    base, mid, bottom, shoes = look
    base = _kind(rules, "top", base)
    bottom = _kind(rules, "bottom", bottom)
    shoes = _kind(rules, "shoes", shoes)
    if mid and not _allowed(rules, "top", mid):
        mid = None
    strategy = ["accent", "tonal", "contrast"][index]
    if strategy == "accent" and not palette.chromatic:
        strategy = "contrast"
    # The accent is chosen first so that no base garment can repeat it.
    reserved = [palette.chromatic[0]] if strategy == "accent" else []
    bottom_color = palette.dark(exclude=reserved)
    shoe_color = (
        palette.dark(exclude=[bottom_color, *reserved])
        if index != 1
        else palette.light(exclude=reserved)
    )
    if strategy == "accent":
        top_color = reserved[0]
    elif strategy == "tonal":
        top_color = palette.light(exclude=[shoe_color, *used_tops])
    else:
        top_color = palette.light(exclude=used_tops)
    used_tops.append(top_color)
    garments = [_garment("top", base, top_color, rules, zh)]
    if mid:
        mid_color = palette.dark(exclude=[bottom_color, *reserved])
        garments.append(_garment("top", mid, mid_color, rules, zh))
    garments.append(_garment("bottom", bottom, bottom_color, rules, zh))
    garments.append(_garment("shoes", shoes, shoe_color, rules, zh))
    wants_outer = rules.season_rule.requires_outerwear or (
        rules.occasion in {"work", "formal"} and rules.season != "summer"
    )
    if wants_outer:
        prefer = [
            k
            for r in rules.proportion.values()
            if r.slot == "outerwear"
            for k in r.prefer.get("kind", [])
        ]
        if rules.occasion == "formal":
            prefer = ["suit_jacket", "blazer", "coat", *prefer]
        options = [*prefer, *OUTERWEAR[rules.season], *sorted(SLOT_KINDS["outerwear"])]
        kind = next(k for k in options if _allowed(rules, "outerwear", k))
        outer_color = (
            palette.dark(exclude=[bottom_color, *reserved]) if strategy != "tonal" else bottom_color
        )
        garments.insert(len(garments) - 1, _garment("outerwear", kind, outer_color, rules, zh))
    if rules.occasion in {"work", "formal"} and _allowed(rules, "accessory", "belt"):
        belt = _garment("accessory", "belt", shoe_color, rules, zh)
        garments.append(belt)
    if strategy == "contrast" and len({palette.lightness[g["color"]] for g in garments}) == 1:
        garments[0]["color"] = palette.light(exclude=[garments[0]["color"]])
    if rules.occasion == "formal" and all(
        CATALOG["colors"][g["color"]]["family"] == "white" for g in garments
    ):
        garments[-1]["color"] = palette.dark()
    i = 0 if zh else 1
    color = COLORS[top_color]
    title = _text(
        zh,
        f"{color[0]}{KINDS[base][0]}与{KINDS[bottom][0]}",
        f"{color[1].capitalize()} {KINDS[base][1]} with {KINDS[bottom][1]}",
    )
    top_hint = garments[0]
    bottom_hint = next(g for g in garments if g["slot"] == "bottom")
    rule_evidence = [e for e in ("rule_trouser_rise", "rule_top_length") if e in available]
    top_name, bottom_name = KINDS[base][i], KINDS[bottom][i]
    measured = {"height", "waist"} <= available
    lead = _text(zh, "结合{{height}}与{{waist}}，", "With {{height}} and {{waist}} in mind, ")
    body_reason = (lead if measured else "") + _text(
        zh,
        f"{top_name}选{LENGTHS[top_hint['length']][0]}、"
        f"{FITS[top_hint['fit']][0]}，{bottom_name}用{RISES[bottom_hint['rise']][0]}和"
        f"{FITS[bottom_hint['fit']][0]}裤型，"
        + ("内外两层让上身更有层次，" if mid else "")
        + "保持腰线清楚、行动舒适。",
        f"the {top_name} is {FITS[top_hint['fit']][1]} with "
        f"{LENGTHS[top_hint['length']][1]}, and the {bottom_name} are {RISES[bottom_hint['rise']][1]} and "
        f"{FITS[bottom_hint['fit']][1]}"
        + (", with a layer adding depth on top" if mid else "")
        + ", keeping a clear, comfortable waistline.",
    )
    outfit = {
        "title": title,
        "garments": garments,
        "body_reason": body_reason,
        "evidence": ((["height", "waist"] if measured else ["rule_occasion"]) + rule_evidence)[:5],
        "styling_tip": _text(
            zh,
            "上衣前摆轻塞或自然垂下，以坐下时腰部不紧为准。",
            "Tuck the front hem lightly or leave it out; the waist should stay easy when seated.",
        )
        if not mid
        else _text(
            zh,
            "内层领口和袖口略露出外层，形成清楚的层次。",
            "Let the base layer's collar and cuffs show slightly for a clean layered look.",
        ),
        "color_reason": {
            "text": {
                "accent": _text(
                    zh,
                    "上衣作为重点色，其余用中性色衔接，避免多种颜色抢眼。",
                    "The top carries the accent; neutrals connect the rest so colors do not compete.",
                ),
                "tonal": _text(
                    zh,
                    "整套用相近的中性色，靠深浅变化区分层次。",
                    "Close neutral tones keep the look calm; depth changes separate the layers.",
                ),
                "contrast": _text(
                    zh,
                    "浅色上衣与深色下装形成明暗对比，上下分界清楚。",
                    "A light top against darker bottoms gives a clear light-dark split.",
                ),
            },
            "evidence": [
                e for e in ("preferred_color_families", "contrast_preference") if e in available
            ],
        },
        "fabric_reason": {
            "text": _text(
                zh,
                "整套保持哑光表面和相近的厚薄，让轮廓自然衔接。",
                "Matte surfaces and similar weights keep the silhouette continuous.",
            ),
            "evidence": [e for e in ("fabric_preferences",) if e in available],
        },
    }
    texts = outfit["color_reason"]["text"]
    # Fall back to another strategy when the chosen colors cannot support the planned one.
    for candidate in dict.fromkeys([strategy, "contrast", "tonal"]):
        outfit["color_plan"] = {
            "strategy": candidate,
            "accent_slots": ["top"] if candidate == "accent" else [],
            "echo_slots": [],
        }
        outfit["color_reason"]["text"] = texts[candidate]
        try:
            DraftOutfit.model_validate(outfit)
            return outfit
        except ValidationError:
            continue
    return outfit


def rule_based_draft(
    facts: list[BodyFact],
    profile: StylingProfile,
    rules: StyleRules,
    style: str,
    zh: bool,
    seed: int = 0,
) -> dict:
    rng = random.Random(seed)
    palette = Palette(profile, rules, rng)
    available = {f.id for f in facts} | rules.evidence_ids()
    used_tops: list[str] = []
    looks = list(LOOKS[style])
    if seed:
        rng.shuffle(looks)
    outfits = [
        _outfit(i, look, rules, palette, zh, available, used_tops) for i, look in enumerate(looks)
    ]
    fit_texts = {
        "top_length": _text(
            zh,
            "上衣下摆落在腰线到臀部之间，避免在臀下堆积。",
            "Keep top hems between the waist and hips so fabric does not gather below.",
        ),
        "trouser_rise": _text(
            zh,
            "裤腰以坐下时不勒为准，配合上衣长度建立清楚的腰线。",
            "Choose a rise that stays comfortable seated and works with the top length.",
        ),
        "trouser_leg": _text(
            zh,
            "裤腿从臀部自然直落到鞋面，留出活动量。",
            "Let the leg fall straight from the hip to the shoe with room to move.",
        ),
        "outerwear": _text(
            zh,
            "外套选肩线清楚、能盖住内层下摆的长度。",
            "Pick outerwear with a clear shoulder line that covers the inner hem.",
        ),
    }
    fit_advice = []
    for area, text in fit_texts.items():
        rule_id = f"rule_{area}"
        evidence = ["height"] + ([rule_id] if rule_id in available else [])
        fit_advice.append({"area": area, "text": text, "evidence": evidence})
    draft = {
        "summary": _text(
            zh,
            "这是按固定穿搭规则生成的基础建议，从{{height}}和{{waist}}出发，兼顾季节与场合。",
            "These are rule-based starter outfits built from {{height}} and {{waist}}, matched to the season and occasion.",
        ),
        "observations": [
            {
                "text": _text(
                    zh,
                    "腰围与胸围的关系用于安排腰部松量，不据此推断体型标签。",
                    "The waist/chest relation guides room at the waist; it is not a body label.",
                ),
                "evidence": ["waist_chest_ratio"],
            },
            {
                "text": _text(
                    zh,
                    "上衣与裤子的分界结合身高与腰臀比例安排。",
                    "Where the top meets the trousers follows height and the waist/hips relation.",
                ),
                "evidence": ["height", "waist_hips_ratio"],
            },
        ],
        "fit_advice": fit_advice,
        "outfits": outfits,
        "color_guidance": {
            "text": _text(
                zh,
                "先用中性色打底，再加入一件重点色比较效果，按实际穿着反馈调整。",
                "Start from neutrals and add one accent to compare; adjust with real-wear feedback.",
            ),
            "evidence": [
                e for e in ("preferred_color_families", "avoided_color_families") if e in available
            ],
        },
        "fabric_guidance": {
            "text": _text(
                zh,
                "优先比较面料厚薄、组织与垂坠；具体商品的成分和手感还需核对。",
                "Compare weight, weave and drape first; check real fiber content and feel.",
            ),
            "evidence": [e for e in ("fabric_preferences", "avoided_materials") if e in available],
        },
    }
    return draft


def rule_based_content(
    facts: list[BodyFact],
    profile: StylingProfile,
    rules: StyleRules,
    style: str,
    locale: str,
    seed: int = 0,
) -> BodyStyleContent:
    from app.services.body_styling_service import parse_result

    draft = rule_based_draft(facts, profile, rules, style, locale.startswith("zh"), seed)
    return parse_result(json.dumps(draft, ensure_ascii=False), facts, locale, profile, rules)


def today_outfit(
    facts: list[BodyFact],
    profile: StylingProfile,
    rules: StyleRules,
    style: str,
    locale: str,
    seed: int,
) -> dict:
    """One quick rule-based look; measurements are optional, so new users get one too."""
    from app.services.body_style_rendering import render_garment, resolve_text

    zh = locale.startswith("zh")
    rng = random.Random(seed)
    palette = Palette(profile, rules, rng)
    available = {f.id for f in facts} | rules.evidence_ids()
    index = seed % 3
    look = LOOKS[style][rng.randrange(len(LOOKS[style]))]
    outfit = DraftOutfit.model_validate(_outfit(index, look, rules, palette, zh, available, []))
    errors = outfit_violations(outfit.garments, rules)
    if errors:
        raise ValueError("; ".join(errors))
    resolve = lambda text: resolve_text(text, facts, outfit.evidence, zh)  # noqa: E731
    return {
        "title": resolve(outfit.title),
        "garments": [render_garment(g, zh) for g in outfit.garments],
        "body_reason": resolve(outfit.body_reason),
        "styling_tip": resolve(outfit.styling_tip),
        "color_plan": outfit.color_plan.model_dump(),
        "color_reason": resolve(outfit.color_reason.text),
        "evidence": outfit.evidence,
    }
