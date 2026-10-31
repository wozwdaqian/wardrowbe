"""Bridge the body styling vocabulary and the wardrobe's item vocabulary.

Body styling speaks in catalog kinds, color families and fiber codes; wardrobe items use
`garment_vocabulary.json` types, color names and material names. The tables below are the
only place the two meet, for avoidance filtering, wardrobe matching and packing.
"""

from app.schemas.styling_profile import CATALOG, StylingProfile
from app.services.body_style_rules import blocked_materials

# Wardrobe color name -> catalog color family.
COLOR_FAMILY = {
    "black": "black",
    "white": "white",
    "cream": "white",
    "gray": "grey",
    "silver": "grey",
    "navy": "blue",
    "blue": "blue",
    "light-blue": "blue",
    "red": "red",
    "burgundy": "red",
    "pink": "pink",
    "green": "green",
    "olive": "green",
    "yellow": "yellow",
    "gold": "yellow",
    "orange": "orange",
    "purple": "purple",
    "brown": "brown",
    "tan": "beige",
    "beige": "beige",
}
# Wardrobe material -> catalog material code; materials without a clear fiber map to None.
MATERIAL_CODE = {
    "cotton": "cotton",
    "canvas": "cotton",
    "denim": "denim",
    "leather": "leather",
    "suede": "leather",
    "shearling": "leather",
    "wool": "wool",
    "silk": "silk",
    "linen": "linen",
    "polyester": "synthetic",
    "nylon": "synthetic",
    "fleece": "synthetic",
}
# Body styling kind -> (wardrobe types, optional subtype keywords).
KIND_TYPES: dict[str, tuple[set[str], set[str]]] = {
    "tshirt": ({"t-shirt", "tank-top"}, set()),
    "polo": ({"polo"}, set()),
    "shirt": ({"shirt"}, set()),
    "turtleneck": ({"sweater", "top"}, {"turtleneck", "roll neck", "高领"}),
    "knit": ({"sweater"}, set()),
    "sweatshirt": ({"hoodie", "sweater"}, {"sweatshirt", "hoodie", "卫衣"}),
    "cardigan": ({"cardigan"}, set()),
    "vest": ({"vest"}, set()),
    "trousers": ({"pants"}, set()),
    "chinos": ({"pants"}, {"chino", "卡其"}),
    "jeans": ({"jeans"}, set()),
    "shorts": ({"shorts"}, set()),
    "sneakers": ({"sneakers"}, set()),
    "loafers": ({"shoes"}, {"loafer", "乐福"}),
    "derbies": ({"shoes"}, {"derby", "德比"}),
    "oxfords": ({"shoes"}, {"oxford", "牛津"}),
    "boots": ({"boots"}, set()),
    "sandals": ({"sandals"}, set()),
    "blazer": ({"blazer", "suit"}, set()),
    "suit_jacket": ({"suit", "blazer"}, set()),
    "jacket": ({"jacket"}, set()),
    "overshirt": ({"jacket", "shirt"}, {"overshirt", "shacket", "衬衫夹克"}),
    "coat": ({"coat"}, set()),
    "trench": ({"coat"}, {"trench", "风衣"}),
    "down_jacket": ({"coat", "jacket"}, {"down", "puffer", "羽绒"}),
    "scarf": ({"scarf"}, set()),
    "belt": ({"belt"}, set()),
    "bag": ({"bag"}, set()),
    "cap": ({"hat"}, set()),
    "tie": ({"tie"}, set()),
    "watch": ({"accessories"}, {"watch", "手表"}),
    "glasses": ({"accessories"}, {"glasses", "眼镜"}),
}


def item_color_family(item) -> str | None:
    return COLOR_FAMILY.get((item.primary_color or "").lower())


def item_material_code(item) -> str | None:
    return MATERIAL_CODE.get((item.material or "").lower())


def avoided_by_profile(item, profile: StylingProfile) -> bool:
    """True when an item's known color family or fiber is a hard avoidance."""
    material = item_material_code(item)
    family = item_color_family(item)
    return (material is not None and material in blocked_materials(profile)) or (
        family is not None and family in profile.avoided_color_families
    )


def matches_kind(item, kind: str) -> bool:
    types, keywords = KIND_TYPES[kind]
    if item.type not in types:
        return False
    if not keywords:
        return True
    subtype = (item.subtype or "").lower()
    name = (getattr(item, "name", None) or "").lower()
    return any(word in subtype or word in name for word in keywords)


def catalog_family(hex_color: str) -> str:
    return CATALOG["colors"][hex_color]["family"]


# A wardrobe outfit needs one of each of these roles; N counts their combinations.
CORE_ROLES = ("base_top", "bottom", "footwear")


SLOT_ROLE = {
    "top": "base_top",
    "bottom": "bottom",
    "shoes": "footwear",
    "outerwear": "outer_layer",
    "accessory": "accessory",
}


def garment_role(slot: str, kind: str) -> str:
    # Cardigans and vests are worn over a base top, so they never complete a combination.
    return "mid_layer" if kind in {"cardigan", "vest"} else SLOT_ROLE[slot]


def combinations(role_counts: dict[str, int]) -> int:
    total = 1
    for role in CORE_ROLES:
        total *= role_counts.get(role, 0)
    return total


def wardrobe_match(result: dict, items: list, profile: StylingProfile) -> dict:
    """Mark each report garment as owned, similar or missing, and rank what to buy.

    `owned` means the same kind in the same color family; `similar` the same kind in
    another color. Suggestions are missing garments ranked by how many extra
    top x bottom x shoes combinations they would add to the usable wardrobe.
    """
    from app.utils.garment_vocabulary import ITEM_ROLE
    from app.utils.signed_urls import sign_optional

    usable = [item for item in items if not avoided_by_profile(item, profile)]
    role_counts: dict[str, int] = {}
    for item in usable:
        role = ITEM_ROLE.get(item.type)
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1
    base = combinations(role_counts)
    outfits, suggestions, seen = [], [], set()
    for outfit_index, outfit in enumerate(result["outfits"]):
        garments = []
        for garment_index, garment in enumerate(outfit["garments"]):
            kind = garment["kind"]
            family = catalog_family(garment["color"])
            same_kind = [item for item in usable if matches_kind(item, kind)]
            owned = [item for item in same_kind if item_color_family(item) == family]
            matches = owned or same_kind
            status = "owned" if owned else "similar" if same_kind else "missing"
            garments.append(
                {
                    "slot": garment["slot"],
                    "kind": kind,
                    "status": status,
                    "matches": [
                        {
                            "id": str(item.id),
                            "name": item.name,
                            "thumbnail_url": sign_optional(item.thumbnail_path, item.image_path),
                        }
                        for item in matches[:3]
                    ],
                }
            )
            if status == "missing" and (kind, family) not in seen:
                seen.add((kind, family))
                role = garment_role(garment["slot"], kind)
                gain = combinations({**role_counts, role: role_counts.get(role, 0) + 1}) - base
                suggestions.append(
                    {
                        "outfit_index": outfit_index,
                        "garment_index": garment_index,
                        "description": garment["description"],
                        "gain": gain,
                    }
                )
        outfits.append({"garments": garments})
    suggestions.sort(key=lambda s: (-s["gain"], s["outfit_index"], s["garment_index"]))
    return {
        "wardrobe_items": len(usable),
        "combinations": base,
        "outfits": outfits,
        "suggestions": suggestions[:2],
    }
