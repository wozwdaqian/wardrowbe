"""Validated, wardrobe-independent styling input and renderable output."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.styling_profile import CATALOG, Color, ColorFamily, FabricSpec, Material

Text = Annotated[str, Field(min_length=1, max_length=600)]
EvidenceId = Literal[
    "height",
    "chest",
    "waist",
    "hips",
    "weight",
    "inseam",
    "shoulder_type",
    "waist_chest_ratio",
    "waist_hips_ratio",
    "inseam_height_ratio",
    "shoulder_width",
    "thigh",
    "skin_depth",
    "undertone",
    "hair_color",
    "eye_color",
    "contrast_preference",
    "preferred_color_families",
    "avoided_color_families",
    "avoided_materials",
    "fabric_preferences",
    "fit_issues",
    "previous_feedback",
]
Measurement = Annotated[float, Field(gt=0, le=1000, allow_inf_nan=False, strict=True)]


class BodyMeasurements(BaseModel):
    # Existing profiles can also contain clothing sizes, which remain untouched.
    model_config = ConfigDict(extra="ignore")
    height: Measurement
    chest: Measurement
    waist: Measurement
    hips: Measurement
    weight: Measurement | None = None
    inseam: Measurement | None = None
    shoulder_type: Literal["narrow", "balanced", "broad"] | None = None
    shoulder_width: Measurement | None = None
    thigh: Measurement | None = None

    @model_validator(mode="after")
    def check_inseam(self):
        if self.inseam is not None and self.inseam >= self.height:
            raise ValueError("inseam must be less than height")
        return self


Goal = Literal["balance", "elongate_legs", "midsection", "shoulders", "comfort"]


class BodyStyleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occasion: Literal["daily", "work", "date", "weekend", "formal"] = "daily"
    style: Literal["minimal", "smart_casual", "street", "sporty", "classic"] = "minimal"
    goals: list[Goal] = Field(
        default_factory=lambda: ["balance", "comfort"], min_length=1, max_length=5
    )
    season: Literal["all", "spring", "summer", "autumn", "winter"] = "all"
    body_measurements_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    styling_profile_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BodyFact(StrictModel):
    id: EvidenceId
    value: float | str | list[str]
    unit: Literal["cm", "kg", "ratio", "self_report"]


class Observation(StrictModel):
    text: Text
    evidence: list[EvidenceId] = Field(min_length=1, max_length=5)


class FitAdvice(Observation):
    area: Literal["top_length", "trouser_rise", "trouser_leg", "outerwear"]


GarmentKind = Literal[
    "tshirt",
    "polo",
    "shirt",
    "knit",
    "sweatshirt",
    "trousers",
    "jeans",
    "shorts",
    "sneakers",
    "loafers",
    "boots",
    "derbies",
    "blazer",
    "jacket",
    "coat",
    "scarf",
    "belt",
    "bag",
    "cap",
]
SLOT_KINDS = {
    "top": {"tshirt", "polo", "shirt", "knit", "sweatshirt"},
    "bottom": {"trousers", "jeans", "shorts"},
    "shoes": {"sneakers", "loafers", "boots", "derbies"},
    "outerwear": {"blazer", "jacket", "coat"},
    "accessory": {"scarf", "belt", "bag", "cap"},
}


class GarmentAttributes(StrictModel):
    slot: Literal["top", "bottom", "shoes", "outerwear", "accessory"]
    kind: GarmentKind
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    fit: Literal["slim", "regular", "relaxed", "wide"]
    length: Literal["short", "regular", "long"]
    rise: Literal["low", "mid", "high"] | None = None

    @model_validator(mode="after")
    def check_slot(self):
        if self.kind not in SLOT_KINDS[self.slot]:
            raise ValueError("garment kind does not match its slot")
        if self.slot == "bottom" and self.rise is None:
            raise ValueError("bottom garments require a rise")
        if self.slot != "bottom" and self.rise is not None:
            raise ValueError("rise is only applicable to bottom garments")
        if self.slot in {"shoes", "accessory"} and (
            self.fit != "regular" or self.length != "regular"
        ):
            raise ValueError("shoes and accessories use regular fit and length")
        if self.kind == "shorts" and self.length != "short":
            raise ValueError("shorts must use short length")
        return self


class Garment(GarmentAttributes):
    """Stored/public format; also reads existing history without changing snapshots."""

    color_name: Annotated[str, Field(min_length=1, max_length=40)]
    material: Annotated[str, Field(min_length=1, max_length=80)]
    description: Text
    material_code: Material | None = None
    color_family: ColorFamily | None = None
    fabric: FabricSpec | None = None
    fabric_summary: Text | None = None
    fabric_reason: Text | None = None


class DraftGarment(GarmentAttributes):
    """AI selects visual attributes. The server owns their names and description."""

    color: Color
    material: Material
    fabric: FabricSpec | None
    fabric_reason: Text

    @model_validator(mode="after")
    def check_fabric(self):
        textile = self.slot in {"top", "bottom", "outerwear"} and self.material not in {
            "leather",
            "vegan_leather",
        }
        if textile and self.fabric is None:
            raise ValueError(
                "textile garments require construction, weight, drape, sheen and stretch"
            )
        if self.material in {"leather", "vegan_leather"} and self.fabric is not None:
            raise ValueError("leather is not a woven/knitted textile; use fabric=null")
        if self.kind == "jeans" and (
            self.fabric is None or self.fabric.construction != "denim_weave"
        ):
            raise ValueError("jeans require denim_weave construction")
        if (
            self.fabric
            and self.fabric.construction == "denim_weave"
            and self.material not in {"cotton", "cotton_blend", "denim", "lyocell"}
        ):
            raise ValueError("denim construction requires a compatible material")
        return self


class StyleExplanation(StrictModel):
    text: Text
    evidence: list[EvidenceId] = Field(max_length=6)


class ColorPlan(StrictModel):
    strategy: Literal[*CATALOG["color_strategy"]]
    accent_slots: list[Literal["top", "bottom", "shoes", "outerwear", "accessory"]] = Field(
        max_length=2
    )
    echo_slots: list[Literal["top", "bottom", "shoes", "outerwear", "accessory"]] = Field(
        max_length=5
    )


class BodyOutfit(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=80)]
    garments: list[Garment] = Field(min_length=3, max_length=5)
    body_reason: Text
    evidence: list[EvidenceId] = Field(min_length=1, max_length=5)
    styling_tip: Text
    color_plan: ColorPlan | None = None
    color_reason: StyleExplanation | None = None
    fabric_reason: StyleExplanation | None = None

    @model_validator(mode="after")
    def complete_outfit(self):
        slots = [g.slot for g in self.garments]
        if len(slots) != len(set(slots)) or not {"top", "bottom", "shoes"} <= set(slots):
            raise ValueError(
                "each outfit needs exactly one top, bottom and shoes; optional slots cannot repeat"
            )
        return self


class BodyStyleContent(StrictModel):
    summary: Text
    observations: list[Observation] = Field(min_length=2, max_length=6)
    fit_advice: list[FitAdvice] = Field(min_length=4, max_length=4)
    unknowns: list[Text] = Field(max_length=6)
    outfits: list[BodyOutfit] = Field(min_length=3, max_length=3)
    color_guidance: StyleExplanation | None = None
    fabric_guidance: StyleExplanation | None = None

    @model_validator(mode="after")
    def check_variety(self):
        if {a.area for a in self.fit_advice} != {
            "top_length",
            "trouser_rise",
            "trouser_leg",
            "outerwear",
        }:
            raise ValueError("fit advice must cover all four areas once")
        signatures = [
            tuple(
                (g.slot, g.kind, g.color.lower(), g.fit, g.length, g.rise)
                for g in sorted(o.garments, key=lambda x: x.slot)
            )
            for o in self.outfits
        ]
        if len(set(signatures)) != 3:
            raise ValueError("three outfits must use distinct combinations")
        return self


class DraftOutfit(BodyOutfit):
    garments: list[DraftGarment] = Field(min_length=3, max_length=5)
    color_plan: ColorPlan
    color_reason: StyleExplanation
    fabric_reason: StyleExplanation

    @model_validator(mode="after")
    def grounded_palette(self):
        colors = {g.slot: CATALOG["colors"][g.color] for g in self.garments}
        plan = self.color_plan
        for slots in (plan.accent_slots, plan.echo_slots):
            if len(slots) != len(set(slots)) or not set(slots) <= colors.keys():
                raise ValueError("color plan must reference distinct existing garment slots")
        if plan.strategy == "echo":
            if (
                len(plan.echo_slots) < 2
                or len({g.color for g in self.garments if g.slot in plan.echo_slots}) != 1
            ):
                raise ValueError(
                    "color echo requires at least two garments with the same actual color"
                )
        elif plan.echo_slots:
            raise ValueError("only echo strategy uses echo_slots")
        if plan.strategy == "accent":
            if not plan.accent_slots or len(plan.accent_slots) == len(colors):
                raise ValueError("accent strategy needs accent and base garments")
            accent_colors = {g.color for g in self.garments if g.slot in plan.accent_slots}
            base_colors = {g.color for g in self.garments if g.slot not in plan.accent_slots}
            if accent_colors <= base_colors:
                raise ValueError("accent must differ from the base colors")
        elif plan.accent_slots:
            raise ValueError("only accent strategy uses accent_slots")
        chromatic = {color["family"] for color in colors.values()} - {
            "white",
            "grey",
            "black",
            "beige",
            "brown",
        }
        if plan.strategy == "tonal" and len(chromatic) > 1:
            raise ValueError("tonal strategy cannot mix different chromatic families")
        if (
            plan.strategy == "contrast"
            and len({color["lightness"] for color in colors.values()}) == 1
            and len(chromatic) < 2
        ):
            raise ValueError("contrast strategy needs an actual lightness or hue contrast")
        return self


class BodyStyleDraft(StrictModel):
    """Only generation uses this contract; fact tokens are resolved before persistence."""

    summary: Text
    observations: list[Observation] = Field(min_length=2, max_length=6)
    fit_advice: list[FitAdvice] = Field(min_length=4, max_length=4)
    outfits: list[DraftOutfit] = Field(min_length=3, max_length=3)
    color_guidance: StyleExplanation
    fabric_guidance: StyleExplanation


class OutfitFeedback(StrictModel):
    outfit_index: int = Field(ge=0, le=2)
    overall: Literal["like", "dislike"] | None = None
    colors: Literal["like", "dislike"] | None = None
    fabrics: Literal["like", "dislike"] | None = None


class ReportFeedback(StrictModel):
    outfits: list[OutfitFeedback] = Field(max_length=3)

    @model_validator(mode="after")
    def unique_outfits(self):
        if len({item.outfit_index for item in self.outfits}) != len(self.outfits):
            raise ValueError("outfit feedback cannot repeat")
        return self


class BodyStyleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    input_snapshot: dict
    facts: list[BodyFact]
    result: BodyStyleContent
    model: str
    feedback: ReportFeedback | None = None


class BodyStyleHistoryEntry(BaseModel):
    id: UUID
    created_at: datetime
    summary: str
    context: BodyStyleRequest


class BodyStyleHistory(BaseModel):
    items: list[BodyStyleHistoryEntry]
    total: int
    limit: int
    offset: int
