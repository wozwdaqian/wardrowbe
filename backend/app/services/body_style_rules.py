"""Deterministic proportion, season, occasion and avoidance rules.

The model chooses and explains garments only inside these boundaries; `enforce_rules`
rejects drafts that step outside them so the existing repair attempt can fix them.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.body_styling import SLOT_KINDS, BodyMeasurements, BodyStyleRequest
from app.schemas.styling_profile import CATALOG, StylingProfile

Area = Literal["top_length", "trouser_rise", "trouser_leg", "outerwear"]
RULE_EVIDENCE = {
    "top_length": "rule_top_length",
    "trouser_rise": "rule_trouser_rise",
    "trouser_leg": "rule_trouser_leg",
    "outerwear": "rule_outerwear",
}
BOLD_PATTERNS = {"stripe", "check", "dot"}
BLENDS = {
    "cotton": {"cotton_blend", "denim"},
    "wool": {"wool_blend"},
    "linen": {"linen_blend"},
}


class AreaRule(BaseModel):
    """Garment attributes to prefer or avoid for one fit-advice area."""

    slot: Literal["top", "bottom", "outerwear"]
    prefer: dict[str, list[str]] = Field(default_factory=dict)
    avoid: dict[str, list[str]] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class SeasonRule(BaseModel):
    banned_kinds: list[str] = Field(default_factory=list)
    banned_weights: list[str] = Field(default_factory=list)
    banned_constructions: list[str] = Field(default_factory=list)
    banned_materials: list[str] = Field(default_factory=list)
    requires_outerwear: bool = False


class OccasionRule(BaseModel):
    allowed_kinds: dict[str, list[str]]
    taboos: list[Literal["all_white"]] = Field(default_factory=list)


class StyleRules(BaseModel):
    season: str
    occasion: str
    proportion: dict[Area, AreaRule]
    season_rule: SeasonRule
    occasion_rule: OccasionRule
    avoided_materials: list[str]
    avoided_color_families: list[str]

    def evidence_ids(self) -> set[str]:
        ids = {RULE_EVIDENCE[area] for area, rule in self.proportion.items() if rule.reasons}
        if self.season != "all":
            ids.add("rule_season")
        ids.add("rule_occasion")
        return ids

    def prompt_view(self) -> dict:
        return {
            "proportion": {
                area: rule.model_dump() for area, rule in self.proportion.items() if rule.reasons
            },
            "season": self.season_rule.model_dump(),
            "occasion": self.occasion_rule.model_dump(),
            "avoided_materials_including_blends": self.avoided_materials,
            "avoided_color_families": self.avoided_color_families,
            "evidence_ids": sorted(self.evidence_ids()),
        }


def _add(rule: AreaRule, kind: str, attribute: str, values: list[str], reason: str):
    target = getattr(rule, kind)
    target.setdefault(attribute, [])
    target[attribute].extend(v for v in values if v not in target[attribute])
    if reason not in rule.reasons:
        rule.reasons.append(reason)


def proportion_rules(
    measurements: BodyMeasurements, profile: StylingProfile, goals: list[str]
) -> dict[Area, AreaRule]:
    rules: dict[Area, AreaRule] = {
        "top_length": AreaRule(slot="top"),
        "trouser_rise": AreaRule(slot="bottom"),
        "trouser_leg": AreaRule(slot="bottom"),
        "outerwear": AreaRule(slot="outerwear"),
    }
    waist_chest = measurements.waist / measurements.chest
    waist_hips = measurements.waist / measurements.hips
    leg_ratio = measurements.inseam / measurements.height if measurements.inseam else None
    issues = set(profile.fit_issues)

    if "elongate_legs" in goals or (leg_ratio is not None and leg_ratio < 0.45):
        reason = "leg_line_goal" if "elongate_legs" in goals else "short_inseam_ratio"
        _add(rules["trouser_rise"], "prefer", "rise", ["high", "mid"], reason)
        _add(rules["trouser_rise"], "avoid", "rise", ["low"], reason)
        _add(rules["top_length"], "prefer", "length", ["short", "regular"], reason)
        _add(rules["top_length"], "avoid", "length", ["long"], reason)
        _add(rules["outerwear"], "prefer", "length", ["short", "regular"], reason)
    if "midsection" in goals or waist_chest >= 0.92 or "belly_cling" in issues:
        reason = (
            "midsection_goal"
            if "midsection" in goals
            else "belly_cling"
            if "belly_cling" in issues
            else "waist_chest_ratio"
        )
        _add(rules["top_length"], "prefer", "fit", ["regular", "relaxed"], reason)
        _add(rules["top_length"], "avoid", "fit", ["slim"], reason)
        _add(rules["trouser_rise"], "prefer", "rise", ["mid", "high"], reason)
        _add(rules["trouser_rise"], "avoid", "rise", ["low"], reason)
        _add(rules["outerwear"], "prefer", "fit", ["regular"], reason)
    if waist_hips <= 0.85 or "thighs_tight" in issues:
        reason = "thighs_tight" if "thighs_tight" in issues else "hip_room"
        _add(rules["trouser_leg"], "prefer", "fit", ["regular", "relaxed"], reason)
        _add(rules["trouser_leg"], "avoid", "fit", ["slim"], reason)
    if "calves_tight" in issues:
        _add(rules["trouser_leg"], "avoid", "fit", ["slim"], "calves_tight")
    if "hem_bunches" in issues:
        _add(rules["trouser_leg"], "prefer", "length", ["short", "regular"], "hem_bunches")
        _add(rules["trouser_leg"], "avoid", "length", ["long"], "hem_bunches")
    if "shoulders_tight" in issues:
        _add(rules["top_length"], "avoid", "fit", ["slim"], "shoulders_tight")
        _add(rules["outerwear"], "avoid", "fit", ["slim"], "shoulders_tight")
    if measurements.shoulder_type == "narrow" or "shoulders" in goals:
        reason = "narrow_shoulders" if measurements.shoulder_type == "narrow" else "shoulder_goal"
        _add(rules["outerwear"], "prefer", "kind", ["blazer", "suit_jacket", "jacket"], reason)
    elif measurements.shoulder_type == "broad":
        _add(rules["outerwear"], "prefer", "fit", ["regular", "relaxed"], "broad_shoulders")
    return rules


SEASONS = {
    "all": SeasonRule(),
    "spring": SeasonRule(banned_kinds=["down_jacket"], banned_constructions=["fleece"]),
    "summer": SeasonRule(
        banned_kinds=[
            "coat",
            "trench",
            "down_jacket",
            "turtleneck",
            "sweatshirt",
            "hoodie",
            "fleece",
            "boots",
            "scarf",
        ],
        banned_weights=["heavy"],
        banned_constructions=["flannel", "fleece", "corduroy"],
        banned_materials=["wool"],
    ),
    "autumn": SeasonRule(banned_kinds=["sandals"], banned_constructions=["mesh"]),
    "winter": SeasonRule(
        banned_kinds=["shorts", "sandals"],
        banned_constructions=["mesh", "linen_weave"],
        banned_materials=["linen", "linen_blend"],
        requires_outerwear=True,
    ),
}
EVERYTHING = {slot: sorted(kinds) for slot, kinds in SLOT_KINDS.items()}


def _without(*kinds: str) -> dict[str, list[str]]:
    return {slot: [k for k in values if k not in kinds] for slot, values in EVERYTHING.items()}


OCCASIONS = {
    "daily": OccasionRule(allowed_kinds=EVERYTHING),
    "weekend": OccasionRule(allowed_kinds=EVERYTHING),
    "date": OccasionRule(
        allowed_kinds=_without("sweatshirt", "hoodie", "cap", "bucket_hat", "sandals")
    ),
    "work": OccasionRule(
        allowed_kinds=_without(
            "shorts",
            "cap",
            "bucket_hat",
            "sweatshirt",
            "hoodie",
            "cargo_pants",
            "fleece",
            "sandals",
        )
    ),
    "formal": OccasionRule(
        allowed_kinds={
            "top": ["knit", "shirt", "turtleneck", "vest"],
            "bottom": ["trousers"],
            "shoes": ["derbies", "loafers", "oxfords"],
            "outerwear": ["blazer", "suit_jacket", "coat", "trench"],
            "accessory": ["bag", "belt", "glasses", "scarf", "socks", "tie", "watch"],
        },
        taboos=["all_white"],
    ),
}


def blocked_materials(profile: StylingProfile) -> list[str]:
    blocked = set(profile.avoided_materials)
    for base, blends in BLENDS.items():
        if base in blocked:
            blocked |= blends
    return sorted(blocked)


def build_rules(
    measurements: BodyMeasurements | None, profile: StylingProfile, request: BodyStyleRequest
) -> StyleRules:
    return StyleRules(
        season=request.season,
        occasion=request.occasion,
        proportion=proportion_rules(measurements, profile, list(request.goals))
        if measurements
        else {},
        season_rule=SEASONS[request.season],
        occasion_rule=OCCASIONS[request.occasion],
        avoided_materials=blocked_materials(profile),
        avoided_color_families=sorted(profile.avoided_color_families),
    )


def default_rules(profile: StylingProfile) -> StyleRules:
    """Avoidance-only rules for callers that have no measurements or request context."""
    return build_rules(None, profile, BodyStyleRequest())


def outfit_violations(garments: list, rules: StyleRules) -> list[str]:
    """Return readable rule violations for one outfit's draft garments."""
    errors = []
    season, occasion = rules.season_rule, rules.occasion_rule
    for g in garments:
        label = f"{g.slot} {g.kind}"
        if g.kind not in occasion.allowed_kinds.get(g.slot, []):
            errors.append(f"occasion {rules.occasion} does not allow {label}")
        if g.kind in season.banned_kinds:
            errors.append(f"season {rules.season} does not allow {label}")
        if g.material in season.banned_materials:
            errors.append(f"season {rules.season} does not allow {g.material} ({label})")
        if g.fabric and g.fabric.weight in season.banned_weights:
            errors.append(
                f"season {rules.season} does not allow {g.fabric.weight} fabric ({label})"
            )
        if g.fabric and g.fabric.construction in season.banned_constructions:
            errors.append(f"season {rules.season} does not allow {g.fabric.construction} ({label})")
        if g.material in rules.avoided_materials:
            errors.append(f"{label} uses avoided material {g.material} (blends included)")
        if (
            "denim" in rules.avoided_materials
            and g.fabric
            and g.fabric.construction == "denim_weave"
        ):
            errors.append(f"{label} uses denim construction, which the user avoids")
        if CATALOG["colors"][g.color]["family"] in rules.avoided_color_families:
            errors.append(f"{label} uses an avoided color family")
        for area, rule in rules.proportion.items():
            if rule.slot != g.slot:
                continue
            for attribute, values in rule.avoid.items():
                if getattr(g, attribute, None) in values:
                    errors.append(
                        f"{area} rule ({', '.join(rule.reasons)}) avoids "
                        f"{attribute}={getattr(g, attribute)} for {label}"
                    )
    slots = {g.slot for g in garments}
    if season.requires_outerwear and "outerwear" not in slots:
        errors.append(f"season {rules.season} requires outerwear")
    if "all_white" in occasion.taboos and all(
        CATALOG["colors"][g.color]["family"] == "white" for g in garments
    ):
        errors.append(f"occasion {rules.occasion} must not be all white")
    if sum(g.pattern in BOLD_PATTERNS for g in garments) > 1:
        errors.append("use at most one bold pattern (stripe, check or dot) per outfit")
    return errors


def enforce_rules(draft, rules: StyleRules) -> None:
    """Raise a ValueError that names every violated rule, for the repair prompt."""
    errors = [
        f"outfit {index + 1}: {error}"
        for index, outfit in enumerate(draft.outfits)
        for error in outfit_violations(outfit.garments, rules)
    ]
    if errors:
        raise ValueError("style rules violated: " + "; ".join(errors))
