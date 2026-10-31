"""Quality checks shared by the offline rule evaluation and the real-model script."""

import json
from pathlib import Path

from app.schemas.body_styling import BodyMeasurements, BodyStyleContent, BodyStyleRequest
from app.schemas.styling_profile import StylingProfile
from app.services.body_style_rendering import FACT_NAMES
from app.services.body_style_rules import StyleRules, build_rules, outfit_violations

PERSONAS = json.loads((Path(__file__).parent / "personas.json").read_text())
BODY_EVIDENCE = {
    "height",
    "chest",
    "waist",
    "hips",
    "weight",
    "inseam",
    "shoulder_type",
    "shoulder_width",
    "thigh",
    "waist_chest_ratio",
    "waist_hips_ratio",
    "inseam_height_ratio",
}
GENERIC = ["适合你", "很适合", "suits you", "looks great", "flattering"]


def persona_inputs(persona: dict):
    measurements = BodyMeasurements(**persona["measurements"])
    profile = StylingProfile(**persona["styling_profile"])
    request = BodyStyleRequest(**persona["request"])
    return measurements, profile, request, build_rules(measurements, profile, request)


def _draft_garment(garment):
    # Stored garments carry display names; rule checks need the material code.
    return garment.model_copy(update={"material": garment.material_code})


def quality_failures(content: BodyStyleContent, rules: StyleRules, zh: bool) -> list[str]:
    failures = []
    for index, outfit in enumerate(content.outfits, 1):
        garments = [_draft_garment(g) for g in outfit.garments]
        failures += [f"outfit {index}: {e}" for e in outfit_violations(garments, rules)]
        if not set(outfit.evidence) & BODY_EVIDENCE:
            failures.append(f"outfit {index}: cites no body measurement or proportion")
        labels = [FACT_NAMES[e][0 if zh else 1] for e in outfit.evidence if e in FACT_NAMES]
        if not any(label in outfit.body_reason for label in labels):
            failures.append(f"outfit {index}: body_reason does not mention its evidence")
        if len(outfit.body_reason) < 20 or any(g in outfit.body_reason for g in GENERIC):
            failures.append(f"outfit {index}: body_reason is generic")
    if len({o.title for o in content.outfits}) < 2:
        failures.append("outfit titles are not distinct")
    return failures
