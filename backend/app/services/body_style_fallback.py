"""Rule-based outfits when no AI is configured, or when a fast, free suggestion is wanted.

The draft is assembled from `StyleRules` and the catalog, then passes through the same
`parse_result` validation and rendering as an AI draft, so both modes share one contract.
"""

import json
import random
from types import SimpleNamespace

from pydantic import ValidationError

from app.schemas.body_styling import (
    ANCHORS,
    SLOT_KINDS,
    BodyFact,
    BodyStyleContent,
    DraftOutfit,
    needs_anchor,
    normalize_techniques,
    technique_possible,
)
from app.schemas.styling_profile import CATALOG, STYLE_DATA, StylingProfile
from app.services.body_style_rendering import COLORS, FITS, KINDS, LENGTHS, PANT_LENGTHS, RISES
from app.services.body_style_rules import StyleRules, apply_remedies, outfit_violations

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
    "shirt": ["oxford", "poplin", "linen_weave", "corduroy"],
    "turtleneck": ["knit", "jersey"],
    "knit": ["knit"],
    "sweatshirt": ["fleece", "jersey"],
    "hoodie": ["fleece", "jersey"],
    "cargo_pants": ["twill", "canvas"],
    "fleece": ["fleece"],
    "cardigan": ["knit"],
    "vest": ["twill", "knit"],
    "trousers": ["twill", "corduroy"],
    "chinos": ["twill", "corduroy"],
    "jeans": ["denim_weave"],
    "shorts": ["twill", "linen_weave"],
    "blazer": ["twill", "linen_weave"],
    "suit_jacket": ["twill"],
    "jacket": ["canvas", "technical", "corduroy"],
    "overshirt": ["flannel", "twill", "canvas", "corduroy"],
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
    warm_enough = rules.season_rule.outerwear_kinds
    if slot == "outerwear" and warm_enough and kind not in warm_enough:
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
    if kind == "bucket_hat":
        options = ["cotton", "synthetic"]
    if kind == "socks":
        options = ["cotton", "wool_blend", "synthetic"]
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
    season, band = rules.season, rules.temperature_band
    hot = season == "summer" or band in {"hot", "warm"}
    cold = (season == "winter" and band not in {"mild", "warm", "hot"}) or band in {
        "cold",
        "freezing",
    }
    weight = "light" if hot else "heavy" if cold and slot == "outerwear" else "medium"
    if weight in rules.season_rule.banned_weights:
        weight = "medium"
    return {
        "construction": construction,
        "weight": weight,
        "drape": "crisp" if slot == "outerwear" or kind == "shirt" else "balanced",
        "sheen": "matte",
        "stretch": "slight" if slot == "bottom" else "none",
    }


def _anchor_cut(garments: list[dict], rules: StyleRules) -> None:
    """Crop the trousers to ankle length when a loose-over-wide outfit has nothing else to anchor it."""
    shape = [SimpleNamespace(**g) for g in garments]
    possible = [t for t in ANCHORS if technique_possible(t, shape)]
    if needs_anchor(shape, possible):
        bottom = next(g for g in garments if g["slot"] == "bottom")
        if "short" not in _avoided(rules, "bottom", "length"):
            bottom["length"] = "short"


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
    _anchor_cut(garments, rules)
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
        "techniques": ["layered_hem"] if mid else ["front_tuck"],
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


STYLES = {style["id"]: style for style in STYLE_DATA}
BOLD = {"stripe", "check", "dot"}
COLOR_TEXTS = {
    "accent": (
        "一件单品承担重点色，其余用中性色衔接，避免多种颜色抢眼。",
        "One piece carries the accent; neutrals connect the rest so colors do not compete.",
    ),
    "tonal": (
        "整套用相近的色调，靠深浅变化区分层次。",
        "Close tones keep the look calm; depth changes separate the layers.",
    ),
    "contrast": (
        "深浅分明的单品形成明暗对比，上下分界清楚。",
        "Light and dark pieces give a clear split between top and bottom.",
    ),
    "echo": (
        "两处单品用同一颜色前后呼应，让整套更有整体感。",
        "Two pieces share one color so the outfit reads as a whole.",
    ),
}


# Styles that already work in an office; anything else gets a kireime weekday look when work
# asks for more than casual clothes.
OFFICE_READY = {
    "suit": {"kireime"},
    "business_casual": {"kireime", "ivy"},
    "smart_casual": {"kireime", "ivy", "normcore", "natural", "mode", "amekaji"},
}


def weekday_style(main: str, dress_code: str | None) -> str:
    if dress_code in OFFICE_READY and main not in OFFICE_READY[dress_code]:
        return "kireime"
    return main


def styles_for(profile: StylingProfile, occasion: str | None = None) -> list[str]:
    """The style direction for an occasion: work days may switch to the weekday style."""
    styles = list(profile.preferred_styles)
    if styles and occasion == "work":
        weekday = weekday_style(styles[0], profile.dress_code)
        if weekday != styles[0]:
            return [weekday]
    return styles


def direction_for(profile: StylingProfile, style: str, occasion: str | None = None) -> list[str]:
    """The quiz's sub-styles, when the requested broad style is the main one's family.

    An explicit different broad style (say classic for a Cityboy) keeps the generic looks. On
    work days the weekday style also accepts the main style's family, which forms default to.
    """
    styles = styles_for(profile, occasion)
    if not styles:
        return []
    families = {STYLES[styles[0]]["base_style"]}
    if profile.preferred_styles:
        families.add(STYLES[profile.preferred_styles[0]]["base_style"])
    return styles if style in families else []


def direction_looks(direction: list[str]) -> list[tuple[str, int]]:
    """Three (style, look index) templates: the main style's looks, the last from the second."""
    main = [(direction[0], i) for i in range(len(STYLES[direction[0]]["looks"]))][:3]
    if len(direction) > 1 and STYLES[direction[1]]["looks"]:
        main[-1] = (direction[1], 0)
    return main


def _keep(
    value: str,
    values: list[str],
    rules: StyleRules,
    slot: str,
    attribute: str,
    remedy: bool = False,
) -> str:
    """The template's own cut unless a proportion rule avoids it without a remedy to try."""
    if value not in _avoided(rules, slot, attribute):
        return value
    if remedy and any(
        rule.remedy_for(attribute, value) for rule in rules.proportion.values() if rule.slot == slot
    ):
        return value
    return _choose(values, rules, slot, attribute, "regular" if attribute != "rise" else "mid")


def _similar(palette: Palette, color: str, exclude=()) -> str:
    """The template color, or one of the same lightness when the user avoids its family."""
    if color in palette.lightness:
        return color
    wanted = CATALOG["colors"][color]["lightness"]
    return palette._pick(lambda h: palette.lightness[h] == wanted, exclude)


def _template_garment(
    spec: dict, kind: str, color: str, rules: StyleRules, zh: bool, remedy: bool
) -> dict:
    slot = spec["slot"]
    g = _garment(slot, kind, color, rules, zh, spec.get("pattern", "solid"))

    def keep(attribute, default, values):
        return _keep(spec.get(attribute, default), values, rules, slot, attribute, remedy)

    if slot in {"top", "outerwear"}:
        g["fit"] = keep("fit", "regular", ["slim", "regular", "relaxed"])
        g["length"] = keep("length", g["length"], ["short", "regular", "long"])
    if slot == "bottom":
        g["fit"] = keep("fit", "regular", ["slim", "regular", "relaxed", "wide", "tapered"])
        g["length"] = (
            "short" if kind == "shorts" else keep("length", "regular", ["short", "regular", "long"])
        )
        g["rise"] = keep("rise", "mid", ["low", "mid", "high"])
    construction = spec.get("construction")
    banned = set(rules.season_rule.banned_constructions)
    if construction and g["fabric"] and construction not in banned and kind == spec["kind"]:
        g["fabric"]["construction"] = construction
    return g


TECHNIQUE_TIPS = {
    "front_tuck": (
        "上衣只把前摆塞进裤腰，侧面和后面自然垂下，腰线和腿长都更清楚。",
        "Tuck just the front of the top into the trousers and leave the sides out for a "
        "clearer waist and longer legs.",
    ),
    "roll_cuffs": (
        "袖口卷起一到两折露出手腕，宽松的上身就有了收住的地方。",
        "Roll the cuffs once or twice to show the wrists, so the loose top is held in somewhere.",
    ),
    "roll_hem": (
        "裤脚向上卷一到两折停在脚踝附近，不在鞋面堆积。",
        "Roll the hems once or twice to stop near the ankle instead of bunching on the shoe.",
    ),
    "show_socks": (
        "裤脚停在脚踝上方露出一截袜子，和帽子或上衣颜色呼应。",
        "Let the hem stop above the ankle so a strip of sock shows, echoing the hat or top.",
    ),
    "layered_hem": (
        "内层领口和下摆略露出外层，形成清楚的层次。",
        "Let the inner layer's collar and hem show slightly for a clean layered look.",
    ),
    "tonal_leg": (
        "裤子和鞋用同一色调，腿部线条从腰一直延伸到脚。",
        "Trousers and shoes in one tone carry the leg line from waist to foot.",
    ),
}


def technique_tip(techniques: list[str], zh: bool) -> str:
    parts = [TECHNIQUE_TIPS[t][0 if zh else 1] for t in techniques[:2]]
    return ("" if zh else " ").join(parts) or _text(
        zh,
        "整套保持干净平整，以坐下和走动时都舒适为准微调。",
        "Keep everything clean and pressed, and adjust until sitting and walking feel easy.",
    )


def _planned_techniques(garments: list[dict], designed=()) -> list[str]:
    """The look's own techniques, then those a stylist would reach for first.

    The schema keeps the first three that are possible with the final garments.
    """
    tops = [g for g in garments if g["slot"] == "top"]
    bottom = next(g for g in garments if g["slot"] == "bottom")
    planned = list(designed)
    if any(g["kind"] == "socks" for g in garments):
        if bottom["length"] != "short" and bottom["kind"] != "shorts":
            planned.append("roll_hem")
        planned.append("show_socks")
    planned.append("layered_hem" if len(tops) == 2 else "front_tuck")
    # Same-tone trousers and shoes count when the colors already match.
    planned.append("tonal_leg")
    shape = [SimpleNamespace(**g) for g in garments]
    if not any(technique_possible(t, shape, planned) for t in planned):
        planned.append("roll_cuffs")
    return normalize_techniques(shape, planned)


def _color_plan(outfit: dict) -> dict | None:
    """The first color strategy the actual garment colors support."""
    by_slot: dict[str, set[str]] = {}
    for g in outfit["garments"]:
        by_slot.setdefault(g["slot"], set()).add(g["color"])
    shared = [
        color
        for color in {g["color"] for g in outfit["garments"]}
        if sum(color in colors for colors in by_slot.values()) >= 2
    ]
    plans = []
    if shared:
        color = sorted(shared)[0]
        slots = [slot for slot, colors in by_slot.items() if color in colors]
        plans.append(("echo", [], slots))
    plans.append(("tonal", [], []))
    chromatic = [
        slot
        for slot, colors in by_slot.items()
        if len(colors) == 1 and CATALOG["colors"][next(iter(colors))]["family"] not in NEUTRALS
    ]
    if len(chromatic) == 1:
        plans.append(("accent", chromatic, []))
    plans.append(("contrast", [], []))
    for strategy, accent, echo in plans:
        candidate = {"strategy": strategy, "accent_slots": accent, "echo_slots": echo}
        try:
            DraftOutfit.model_validate({**outfit, "color_plan": candidate})
            return candidate
        except ValidationError:
            continue
    return None


def _template_outfit(style_id, look_index, rules, palette, zh, available) -> dict | None:
    """One look from the Japanese style data, adapted to the rules; None if it cannot be.

    The template's cut is kept with a remedy technique (a tucked long top) when a proportion
    rule would otherwise change it; without a workable remedy the rule's own cut is used.
    """
    for remedy in (True, False):
        outfit = _template_attempt(style_id, look_index, rules, palette, zh, available, remedy)
        if outfit:
            return outfit
    return None


def _template_attempt(style_id, look_index, rules, palette, zh, available, remedy):
    look = STYLES[style_id]["looks"][look_index]
    garments, changed = [], False
    used: list[str] = []
    for spec in look["garments"]:
        slot, wanted = spec["slot"], spec["kind"]
        layered = slot == "top" and any(g["slot"] == "top" for g in garments)
        if _allowed(rules, slot, wanted):
            kind = wanted
        elif slot in {"accessory", "outerwear"} or layered:
            # An extra layer or accessory the season or occasion rules out is simply left off.
            changed = True
            continue
        else:
            kind, changed = _kind(rules, slot, wanted), True
        color = _similar(palette, spec["color"], used)
        changed |= color != spec["color"]
        used.append(color)
        garments.append(_template_garment(spec, kind, color, rules, zh, remedy))
    slots = {g["slot"] for g in garments}
    wants_outer = rules.season_rule.requires_outerwear or (
        rules.occasion in {"work", "formal"} and rules.season != "summer"
    )
    if wants_outer and "outerwear" not in slots:
        options = [*OUTERWEAR[rules.season], *sorted(SLOT_KINDS["outerwear"])]
        if rules.occasion == "formal":
            options = ["suit_jacket", "blazer", "coat", *options]
        kind = next((k for k in options if _allowed(rules, "outerwear", k)), None)
        if kind is None:
            return None
        bottom = next(g for g in garments if g["slot"] == "bottom")
        color = palette.dark(exclude=[bottom["color"]])
        outer = _garment("outerwear", kind, color, rules, zh)
        garments.insert(next(i for i, g in enumerate(garments) if g["slot"] == "shoes"), outer)
        changed = True
    if sum(g["pattern"] in BOLD for g in garments) > 1:
        return None
    _anchor_cut(garments, rules)
    lang = 0 if zh else 1
    top = next(g for g in garments if g["slot"] == "top")
    bottom = next(g for g in garments if g["slot"] == "bottom")
    if changed:
        title = _text(
            zh,
            f"{COLORS[top['color']][0]}{KINDS[top['kind']][0]}与{KINDS[bottom['kind']][0]}",
            f"{COLORS[top['color']][1].capitalize()} {KINDS[top['kind']][1]} "
            f"with {KINDS[bottom['kind']][1]}",
        )
    else:
        title = look["title"]["zh" if zh else "en"]
    measured = {"height", "waist"} <= available
    lead = _text(zh, "结合{{height}}与{{waist}}，", "With {{height}} and {{waist}} in mind, ")
    style_name = STYLES[style_id]["name"]["zh" if zh else "en"]
    pants = PANT_LENGTHS[bottom["length"]][lang] if bottom["kind"] != "shorts" else ""
    body_reason = (lead if measured else "") + _text(
        zh,
        f"按{style_name}的轮廓，{KINDS[top['kind']][0]}{FITS[top['fit']][0]}、"
        f"{LENGTHS[top['length']][0]}，{KINDS[bottom['kind']][0]}用{RISES[bottom['rise']][0]}"
        f"{FITS[bottom['fit']][0]}" + (f"、{pants}" if pants else "") + "。",
        f"following the {style_name} silhouette, the {KINDS[top['kind']][1]} is "
        f"{FITS[top['fit']][1]} with {LENGTHS[top['length']][1]}, and the "
        f"{KINDS[bottom['kind']][1]} are {RISES[bottom['rise']][1]} and {FITS[bottom['fit']][1]}"
        + (f", {pants}" if pants else "")
        + ".",
    )
    techniques = _planned_techniques(garments, look.get("techniques", []))
    rule_evidence = [e for e in ("rule_trouser_leg", "rule_top_length") if e in available]
    outfit = {
        "title": title[:80],
        "garments": garments,
        "body_reason": body_reason,
        "evidence": ((["height", "waist"] if measured else ["rule_occasion"]) + rule_evidence)[:5],
        "styling_tip": technique_tip(techniques, zh),
        "techniques": techniques,
        "color_reason": {
            "text": COLOR_TEXTS["tonal"][lang],
            "evidence": [
                e for e in ("preferred_color_families", "contrast_preference") if e in available
            ],
        },
        "fabric_reason": {
            "text": _text(
                zh,
                "面料沿用这个风格常见的组织和厚薄，整套保持相近的质感。",
                "Fabrics follow this style's usual weaves and weights so the textures stay close.",
            ),
            "evidence": [e for e in ("fabric_preferences",) if e in available],
        },
    }
    plan = _color_plan(outfit)
    if plan is None:
        return None
    outfit["color_plan"] = plan
    outfit["color_reason"]["text"] = COLOR_TEXTS[plan["strategy"]][lang]
    try:
        draft = DraftOutfit.model_validate(outfit)
    except ValidationError:
        return None
    # The schema settled which techniques are possible (adding an anchor for an H shape);
    # remedies come next, and the tip describes exactly what is left.
    techniques = apply_remedies(draft.garments, draft.techniques, rules)
    if outfit_violations(draft.garments, rules, techniques):
        return None
    outfit["techniques"] = techniques
    outfit["styling_tip"] = technique_tip(techniques, zh)
    return outfit


def _signature(outfit: dict) -> tuple:
    return tuple(
        sorted(
            (g["slot"], g["kind"], g["color"], g["fit"], g["length"], g["rise"] or "", g["pattern"])
            for g in outfit["garments"]
        )
    )


def rule_based_draft(
    facts: list[BodyFact],
    profile: StylingProfile,
    rules: StyleRules,
    style: str,
    zh: bool,
    seed: int = 0,
    direction: list[str] | None = None,
) -> dict:
    rng = random.Random(seed)
    palette = Palette(profile, rules, rng)
    available = {f.id for f in facts} | rules.evidence_ids()
    used_tops: list[str] = []
    looks = list(LOOKS[style])
    if seed:
        rng.shuffle(looks)
    templates = direction_looks(direction) if direction else []
    if seed:
        rng.shuffle(templates)
    outfits = []
    for i, look in enumerate(looks):
        outfit = None
        if i < len(templates):
            outfit = _template_outfit(*templates[i], rules, palette, zh, available)
            if outfit and _signature(outfit) in {_signature(o) for o in outfits}:
                outfit = None
        # A template the rules cannot carry falls back to the generic look for that slot.
        outfits.append(outfit or _outfit(i, look, rules, palette, zh, available, used_tops))
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
    summary = _text(
        zh,
        "这是按固定穿搭规则生成的基础建议，从{{height}}和{{waist}}出发，兼顾季节与场合。",
        "These are rule-based starter outfits built from {{height}} and {{waist}}, matched to the season and occasion.",
    )
    if direction:
        names = [STYLES[s]["name"]["zh" if zh else "en"] for s in direction]
        summary = _text(
            zh,
            f"这是按你的日系风格方向（{'、'.join(names)}）生成的基础建议，"
            "从{{height}}和{{waist}}出发，兼顾季节与场合。",
            f"These rule-based outfits follow your Japanese style direction ({', '.join(names)}), "
            "built from {{height}} and {{waist}} and matched to the season and occasion.",
        )
    draft = {
        "summary": summary,
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
    direction: list[str] | None = None,
) -> BodyStyleContent:
    from app.services.body_styling_service import parse_result

    draft = rule_based_draft(facts, profile, rules, style, locale.startswith("zh"), seed, direction)
    return parse_result(json.dumps(draft, ensure_ascii=False), facts, locale, profile, rules)


def today_outfit(
    facts: list[BodyFact],
    profile: StylingProfile,
    rules: StyleRules,
    style: str,
    locale: str,
    seed: int,
    direction: list[str] | None = None,
) -> dict:
    """One quick rule-based look; measurements are optional, so new users get one too.

    With a Japanese style direction, one of its looks is adapted first; the generic look for
    the broad style is the fallback when the rules cannot carry it.
    """
    from app.services.body_style_rendering import render_garment, resolve_text

    zh = locale.startswith("zh")
    rng = random.Random(seed)
    palette = Palette(profile, rules, rng)
    available = {f.id for f in facts} | rules.evidence_ids()
    index = seed % 3
    look = LOOKS[style][rng.randrange(len(LOOKS[style]))]
    templates = direction_looks(direction) if direction else []
    template = (
        _template_outfit(*templates[seed % len(templates)], rules, palette, zh, available)
        if templates
        else None
    )
    outfit = DraftOutfit.model_validate(
        template or _outfit(index, look, rules, palette, zh, available, [])
    )
    techniques = apply_remedies(outfit.garments, outfit.techniques, rules)
    errors = outfit_violations(outfit.garments, rules, techniques)
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
        "techniques": techniques,
        "silhouette": outfit.silhouette,
    }
