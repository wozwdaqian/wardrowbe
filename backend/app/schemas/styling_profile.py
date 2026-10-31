"""Optional personal preferences and controlled textile vocabulary."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATALOG = json.loads((Path(__file__).parents[1] / "data/body_styling_catalog.json").read_text())
Color = Literal[*CATALOG["colors"]]
Material = Literal[*CATALOG["materials"]]
ColorFamily = Literal[*CATALOG["color_families"]]
# Japanese sub-styles found by the style quiz (services/style_explore.py).
STYLE_DATA = json.loads((Path(__file__).parents[1] / "data/japanese_styles.json").read_text())[
    "styles"
]
StyleId = Literal[*(style["id"] for style in STYLE_DATA)]
PROFILE_CATALOGS = {
    "skin_depth": "skin_depth",
    "undertone": "undertone",
    "hair_color": "hair_color",
    "eye_color": "eye_color",
    "contrast_preference": "contrast_preference",
    "preferred_color_families": "color_families",
    "avoided_color_families": "color_families",
    "avoided_materials": "materials",
    "fabric_preferences": "fabric_preferences",
    "fit_issues": "fit_issues",
}
# Everyday names such as 冷白皮 or 黄黑皮, each a fixed skin depth + undertone pair.
SKIN_TYPES = CATALOG["skin_types"]


def skin_type(profile: dict) -> str | None:
    """The everyday skin type matching the stored depth and undertone, if any."""
    for key, entry in SKIN_TYPES.items():
        if (entry["skin_depth"], entry["undertone"]) == (
            profile.get("skin_depth"),
            profile.get("undertone"),
        ):
            return key
    return None


class StylingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    skin_depth: Literal[*CATALOG["skin_depth"]] | None = None
    undertone: Literal[*CATALOG["undertone"]] | None = None
    hair_color: Literal[*CATALOG["hair_color"]] | None = None
    eye_color: Literal[*CATALOG["eye_color"]] | None = None
    contrast_preference: Literal[*CATALOG["contrast_preference"]] | None = None
    preferred_color_families: list[ColorFamily] = Field(default_factory=list, max_length=8)
    avoided_color_families: list[ColorFamily] = Field(default_factory=list, max_length=8)
    avoided_materials: list[Material] = Field(default_factory=list, max_length=10)
    fabric_preferences: list[Literal[*CATALOG["fabric_preferences"]]] = Field(
        default_factory=list, max_length=6
    )
    fit_issues: list[Literal[*CATALOG["fit_issues"]]] = Field(default_factory=list, max_length=8)
    # The main sub-style first; a second one when the quiz found two close favourites.
    preferred_styles: list[StyleId] = Field(default_factory=list, max_length=2)

    @field_validator(
        "preferred_color_families",
        "avoided_color_families",
        "avoided_materials",
        "fabric_preferences",
        "fit_issues",
        "preferred_styles",
    )
    @classmethod
    def no_duplicates(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("preference selections must not repeat")
        return values

    @model_validator(mode="after")
    def no_conflicts(self):
        if set(self.preferred_color_families) & set(self.avoided_color_families):
            raise ValueError("a color family cannot be both preferred and avoided")
        if len(self.avoided_color_families) == len(CATALOG["color_families"]):
            raise ValueError("leave at least one color family available")
        return self


class FabricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    construction: Literal[*CATALOG["construction"]]
    weight: Literal[*CATALOG["weight"]]
    drape: Literal[*CATALOG["drape"]]
    sheen: Literal[*CATALOG["sheen"]]
    stretch: Literal[*CATALOG["stretch"]]


def styling_revision(measurements: dict | None, profile: dict | None) -> str:
    from app.utils.body_measurements import body_revision

    normalized = StylingProfile.model_validate(profile or {}).model_dump(exclude_none=True)
    # Added later: an unset value must not change revisions computed before it existed.
    if not normalized.get("preferred_styles"):
        normalized.pop("preferred_styles", None)
    return body_revision({"measurements": measurements or {}, "styling_profile": normalized})
