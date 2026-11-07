"""Validated, wardrobe-independent styling input and renderable output."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

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
    "rule_top_length",
    "rule_trouser_rise",
    "rule_trouser_leg",
    "rule_outerwear",
    "rule_season",
    "rule_occasion",
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
    # Set from the current temperature for today's outfit; adds that band's limits.
    temperature_band: Literal["hot", "warm", "mild", "cool", "cold", "freezing"] | None = None
    # auto uses AI when it is available and the deterministic rules otherwise.
    mode: Literal["auto", "ai", "rules"] = "auto"
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


SLOT_KINDS = {
    "top": {
        "tshirt",
        "polo",
        "shirt",
        "turtleneck",
        "knit",
        "sweatshirt",
        "hoodie",
        "cardigan",
        "vest",
    },
    "bottom": {"trousers", "chinos", "jeans", "cargo_pants", "shorts"},
    "shoes": {"sneakers", "loafers", "boots", "derbies", "oxfords", "sandals"},
    "outerwear": {
        "blazer",
        "suit_jacket",
        "jacket",
        "overshirt",
        "coat",
        "trench",
        "down_jacket",
        "fleece",
    },
    "accessory": {
        "scarf",
        "belt",
        "bag",
        "cap",
        "bucket_hat",
        "socks",
        "tie",
        "watch",
        "glasses",
    },
}
GarmentKind = Literal[*sorted(set().union(*SLOT_KINDS.values()))]
# A second top is a layer: one base piece worn under one mid layer.
BASE_TOPS = {"tshirt", "polo", "shirt", "turtleneck"}
MID_TOPS = {"knit", "sweatshirt", "hoodie", "cardigan", "vest"}
Pattern = Literal[*CATALOG["patterns"]]
SLOT_LIMITS = {
    "top": (1, 2),
    "bottom": (1, 1),
    "shoes": (1, 1),
    "outerwear": (0, 1),
    "accessory": (0, 2),
}


class GarmentAttributes(StrictModel):
    slot: Literal["top", "bottom", "shoes", "outerwear", "accessory"]
    kind: GarmentKind
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    fit: Literal["slim", "regular", "relaxed", "wide", "tapered"]
    length: Literal["short", "regular", "long"]
    rise: Literal["low", "mid", "high"] | None = None
    pattern: Pattern = "solid"

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
        if self.fit == "tapered" and self.slot != "bottom":
            raise ValueError("tapered fit is only for trousers")
        if self.kind == "shorts" and self.length != "short":
            raise ValueError("shorts must use short length")
        if self.slot == "shoes" and self.pattern != "solid":
            raise ValueError("shoes use a solid pattern")
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


# Wearing techniques Japanese styling guides lean on; each needs the garments that make it possible.
Technique = Literal[
    "front_tuck", "roll_cuffs", "roll_hem", "show_socks", "layered_hem", "tonal_leg"
]
TECHNIQUES: tuple[str, ...] = Technique.__args__
# Silhouette letters used by Japanese guides: I straight, A narrow over wide, Y loose over
# narrow; H is loose over wide, which needs one anchored point to avoid looking sloppy.
Silhouette = Literal["I", "A", "Y", "H"]
TUCKABLE = {"tshirt", "polo", "shirt", "knit", "sweatshirt", "turtleneck"}
SHORT_SLEEVES = {"tshirt", "polo", "vest"}
STIFF_SLEEVES = {"blazer", "suit_jacket", "coat", "trench", "down_jacket"}
ROLLABLE_HEMS = {"jeans", "chinos", "cargo_pants"}
ANCHORS = ("show_socks", "roll_hem", "roll_cuffs", "front_tuck")


def _upper(garments):
    """The outermost upper garment: what sets the silhouette's top half."""
    outer = [g for g in garments if g.slot == "outerwear"]
    tops = [g for g in garments if g.slot == "top"]
    return (outer or tops[::-1])[0]


def outfit_silhouette(garments) -> str:
    upper = _upper(garments)
    bottom = next(g for g in garments if g.slot == "bottom")
    # A waist-length boxy top over wide trousers reads as an A, not a shapeless block.
    loose = (upper.fit in {"relaxed", "wide"} and upper.length != "short") or upper.length == "long"
    if bottom.fit in {"wide", "relaxed"}:
        return "H" if loose else "A"
    if bottom.fit in {"tapered", "slim"} and loose:
        return "Y"
    return "I"


def technique_possible(technique: str, garments, techniques=()) -> bool:
    tops = [g for g in garments if g.slot == "top"]
    bottom = next(g for g in garments if g.slot == "bottom")
    shoes = next(g for g in garments if g.slot == "shoes")
    if technique == "front_tuck":
        return len(tops) == 1 and tops[0].kind in TUCKABLE and tops[0].length != "short"
    if technique == "roll_cuffs":
        upper = _upper(garments)
        return upper.kind not in SHORT_SLEEVES | STIFF_SLEEVES
    if technique == "roll_hem":
        return bottom.kind in ROLLABLE_HEMS and bottom.length != "short"
    if technique == "show_socks":
        exposed = bottom.kind == "shorts" or bottom.length == "short" or "roll_hem" in techniques
        return exposed and any(g.kind == "socks" for g in garments)
    if technique == "layered_hem":
        return len(tops) == 2 or (
            any(g.slot == "outerwear" for g in garments) and tops[-1].length != "short"
        )
    if technique == "tonal_leg":
        a, b = CATALOG["colors"][bottom.color], CATALOG["colors"][shoes.color]
        return (a["family"], a["lightness"]) == (b["family"], b["lightness"])
    return False


def is_complete(garments) -> bool:
    slots = {g.slot for g in garments}
    return {"top", "bottom", "shoes"} <= slots


def needs_anchor(garments, techniques) -> bool:
    """An H silhouette with nothing held in: no ankle showing and no anchoring technique."""
    if not is_complete(garments) or outfit_silhouette(garments) != "H":
        return False
    bottom = next(g for g in garments if g.slot == "bottom")
    exposed = bottom.length == "short" or bottom.kind == "shorts"
    return not exposed and not set(techniques) & set(ANCHORS)


def normalize_techniques(garments, techniques) -> list[str]:
    """Keep the possible techniques once each; give an H silhouette its anchor point."""
    kept: list[str] = []
    for t in techniques:
        if t not in kept and technique_possible(t, garments, kept + list(techniques)):
            kept.append(t)
    if needs_anchor(garments, kept):
        extra = next((t for t in ANCHORS if technique_possible(t, garments, kept)), None)
        if extra:
            kept.append(extra)
    return kept[:3]


class BodyOutfit(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=80)]
    garments: list[Garment] = Field(min_length=3, max_length=7)
    body_reason: Text
    evidence: list[EvidenceId] = Field(min_length=1, max_length=5)
    styling_tip: Text
    color_plan: ColorPlan | None = None
    color_reason: StyleExplanation | None = None
    fabric_reason: StyleExplanation | None = None
    # Older reports have neither; the server fills both for new and edited outfits.
    techniques: list[Technique] = Field(default_factory=list, max_length=3)
    silhouette: Silhouette | None = None

    @model_validator(mode="after")
    def complete_outfit(self):
        slots = [g.slot for g in self.garments]
        for slot, (low, high) in SLOT_LIMITS.items():
            if not low <= slots.count(slot) <= high:
                raise ValueError(
                    "each outfit needs one or two tops, one bottom and one pair of shoes, "
                    "at most one outerwear and at most two accessories"
                )
        tops = [g.kind for g in self.garments if g.slot == "top"]
        if len(tops) == 2 and not (set(tops) & BASE_TOPS and set(tops) & MID_TOPS):
            raise ValueError(
                "two tops must be a layer: one of tshirt/polo/shirt/turtleneck under one "
                "of knit/sweatshirt/hoodie/cardigan/vest"
            )
        if tops == ["vest"]:
            raise ValueError("a vest is a layer and needs a base top underneath")
        accessories = [g.kind for g in self.garments if g.slot == "accessory"]
        if len(accessories) != len(set(accessories)):
            raise ValueError("accessories cannot repeat the same kind")
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
                sorted(
                    (g.slot, g.kind, g.color.lower(), g.fit, g.length, g.rise or "", g.pattern)
                    for g in o.garments
                )
            )
            for o in self.outfits
        ]
        if len(set(signatures)) != 3:
            raise ValueError("three outfits must use distinct combinations")
        return self


class DraftOutfit(BodyOutfit):
    garments: list[DraftGarment] = Field(min_length=3, max_length=7)
    color_plan: ColorPlan
    color_reason: StyleExplanation
    fabric_reason: StyleExplanation

    @model_validator(mode="after")
    def settle_shape(self):
        # The silhouette always follows the garments; impossible techniques are dropped.
        self.techniques = normalize_techniques(self.garments, self.techniques)
        self.silhouette = outfit_silhouette(self.garments)
        return self

    @model_validator(mode="after")
    def grounded_palette(self):
        # Slots may hold two garments (layered tops, accessories); compare color sets per slot.
        by_slot: dict[str, set[str]] = {}
        for g in self.garments:
            by_slot.setdefault(g.slot, set()).add(g.color)
        colors = [CATALOG["colors"][g.color] for g in self.garments]
        plan = self.color_plan
        for slots in (plan.accent_slots, plan.echo_slots):
            if len(slots) != len(set(slots)) or not set(slots) <= by_slot.keys():
                raise ValueError("color plan must reference distinct existing garment slots")
        if plan.strategy == "echo":
            if len(plan.echo_slots) < 2 or not set.intersection(
                *(by_slot[slot] for slot in plan.echo_slots)
            ):
                raise ValueError(
                    "color echo requires at least two garments with the same actual color"
                )
        elif plan.echo_slots:
            raise ValueError("only echo strategy uses echo_slots")
        if plan.strategy == "accent":
            if not plan.accent_slots or len(plan.accent_slots) == len(by_slot):
                raise ValueError("accent strategy needs accent and base garments")
            accent_colors = set().union(*(by_slot[slot] for slot in plan.accent_slots))
            base_colors = {g.color for g in self.garments if g.slot not in plan.accent_slots}
            if accent_colors <= base_colors:
                raise ValueError("accent must differ from the base colors")
        elif plan.accent_slots:
            raise ValueError("only accent strategy uses accent_slots")
        chromatic = {color["family"] for color in colors} - {
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
            and len({color["lightness"] for color in colors}) == 1
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
    status: Literal["pending", "done", "failed"] = "done"
    error_code: str | None = None
    result: BodyStyleContent | None = None
    model: str | None = None
    feedback: ReportFeedback | None = None

    @computed_field
    @property
    def mode(self) -> Literal["ai", "rules"]:
        return self.input_snapshot.get("mode", "ai")


class BodyStyleHistoryEntry(BaseModel):
    id: UUID
    created_at: datetime
    summary: str | None
    context: BodyStyleRequest
    status: Literal["pending", "done", "failed"] = "done"
    error_code: str | None = None
    mode: Literal["ai", "rules"] = "ai"


class BodyStyleHistory(BaseModel):
    items: list[BodyStyleHistoryEntry]
    total: int
    limit: int
    offset: int
