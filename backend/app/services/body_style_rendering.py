"""Resolve measured values and clothing captions from trusted structured data."""

import re

from app.schemas.body_styling import BodyFact, DraftGarment
from app.schemas.styling_profile import CATALOG, PROFILE_CATALOGS

COLORS = {
    "#ffffff": ("白色", "white"),
    "#efe8dd": ("米白色", "ivory"),
    "#d3be97": ("燕麦色", "oatmeal"),
    "#b69b79": ("驼色", "camel"),
    "#744f37": ("棕色", "brown"),
    "#363c41": ("深灰色", "charcoal"),
    "#111827": ("近黑色", "near black"),
    "#465b70": ("灰蓝色", "slate blue"),
    "#243b55": ("藏蓝色", "navy"),
    "#718575": ("鼠尾草绿", "sage green"),
    "#3e5143": ("深绿色", "dark green"),
    "#803e47": ("酒红色", "burgundy"),
    "#aeb4bb": ("浅灰色", "light grey"),
    "#b5ccd4": ("浅蓝色", "light blue"),
    "#d7b8b1": ("浅粉色", "dusty pink"),
}
KINDS = {
    "tshirt": ("T 恤", "T-shirt"),
    "polo": ("Polo 衫", "polo"),
    "shirt": ("衬衫", "shirt"),
    "knit": ("针织衫", "knitwear"),
    "sweatshirt": ("卫衣", "sweatshirt"),
    "trousers": ("长裤", "trousers"),
    "jeans": ("牛仔裤", "jeans"),
    "shorts": ("短裤", "shorts"),
    "sneakers": ("运动鞋", "sneakers"),
    "loafers": ("乐福鞋", "loafers"),
    "boots": ("短靴", "boots"),
    "derbies": ("德比鞋", "derbies"),
    "blazer": ("西装外套", "blazer"),
    "jacket": ("夹克", "jacket"),
    "coat": ("大衣", "coat"),
    "scarf": ("围巾", "scarf"),
    "belt": ("腰带", "belt"),
    "bag": ("包", "bag"),
    "cap": ("帽子", "cap"),
}
MATERIALS = {
    "cotton": ("棉", "cotton"),
    "cotton_blend": ("棉混纺", "cotton blend"),
    "linen": ("亚麻", "linen"),
    "wool": ("羊毛", "wool"),
    "wool_blend": ("羊毛混纺", "wool blend"),
    "denim": ("牛仔布", "denim"),
    "leather": ("皮革", "leather"),
    "synthetic": ("合成纤维", "synthetic fabric"),
}
FITS = {
    "slim": ("修身", "slim"),
    "regular": ("合体", "regular"),
    "relaxed": ("宽松", "relaxed"),
    "wide": ("宽廓形", "wide"),
}
LENGTHS = {
    "short": ("下摆至腰线", "hem at waist"),
    "regular": ("下摆至臀部", "hem at hips"),
    "long": ("下摆低于臀部", "hem below hips"),
}
PANT_LENGTHS = {
    "short": ("九分裤长", "ankle length"),
    "regular": ("常规裤长", "full length"),
    "long": ("较长裤脚", "longer break"),
}
RISES = {"low": ("低腰", "low rise"), "mid": ("中腰", "mid rise"), "high": ("高腰", "high rise")}
FACT_NAMES = {
    "height": ("身高", "height"),
    "chest": ("胸围", "chest"),
    "waist": ("腰围", "waist"),
    "hips": ("臀围", "hips"),
    "weight": ("体重", "weight"),
    "inseam": ("内腿长", "inseam"),
    "shoulder_type": ("自述肩部特点", "self-reported shoulders"),
    "waist_chest_ratio": ("腰胸比", "waist/chest ratio"),
    "waist_hips_ratio": ("腰臀比", "waist/hips ratio"),
    "inseam_height_ratio": ("内腿长与身高之比", "inseam/height ratio"),
}
SHOULDERS = {
    "narrow": ("偏窄", "narrow"),
    "balanced": ("适中", "balanced"),
    "broad": ("偏宽", "broad"),
}
TOKEN = re.compile(r"\{\{([a-z_]+)\}\}")
COLORS.update({key: (value["zh"], value["en"]) for key, value in CATALOG["colors"].items()})
MATERIALS.update({key: (value["zh"], value["en"]) for key, value in CATALOG["materials"].items()})
FACT_NAMES.update(
    {
        "shoulder_width": ("肩宽", "shoulder width"),
        "thigh": ("大腿围", "thigh circumference"),
        "skin_depth": ("自述肤色深浅", "self-reported skin depth"),
        "undertone": ("自述底色倾向", "self-reported undertone"),
        "hair_color": ("发色", "hair color"),
        "eye_color": ("眼睛颜色", "eye color"),
        "contrast_preference": ("偏好配色对比", "preferred contrast"),
        "preferred_color_families": ("喜欢色系", "preferred colors"),
        "avoided_color_families": ("避用色系", "avoided colors"),
        "avoided_materials": ("避用材质", "avoided materials"),
        "fabric_preferences": ("面料偏好", "fabric preferences"),
        "fit_issues": ("穿衣困扰", "fit concerns"),
        "previous_feedback": ("此前穿搭反馈", "previous outfit feedback"),
    }
)


def fact_display(fact: BodyFact, zh: bool) -> str:
    if fact.id == "shoulder_type":
        return SHOULDERS[str(fact.value)][0 if zh else 1]
    if fact.id in PROFILE_CATALOGS:
        vocabulary = CATALOG[PROFILE_CATALOGS[fact.id]]
        values = fact.value if isinstance(fact.value, list) else [fact.value]
        return ("、" if zh else ", ").join(
            vocabulary[value]["zh" if zh else "en"] for value in values
        )
    if fact.unit == "self_report":
        return str(fact.value)
    return format(float(fact.value), "g")


def resolve_text(text: str, facts: list[BodyFact], evidence: list[str] | None, zh: bool) -> str:
    """Numbers must be server fact tokens, never freehand numerical model claims.

    This is a factual/format guard, not a general proof of natural-language reasoning.
    """
    known = {fact.id: fact for fact in facts}
    references = TOKEN.findall(text)
    plain = TOKEN.sub("", text)
    if (
        "{" in plain
        or "}" in plain
        or re.search(r"\d|[零一二三四五六七八九十百千万两〇点]+\s*(?:厘米|公分|公斤|千克|%)", plain)
    ):
        raise ValueError("write measurements and ratios only as {{fact_id}} tokens; no raw numbers")
    if any(
        ref not in known or (evidence is not None and ref not in evidence) for ref in references
    ):
        raise ValueError("fact tokens must exist in the input and in this entry's evidence")
    # Missing-data explanations are rendered by the server, outside model prose.
    for key, terms in {"inseam": r"内腿长|裆长|\binseam\b", "weight": r"体重|\bweight\b"}.items():
        if key not in known and re.search(terms, plain, re.I):
            raise ValueError(
                "do not describe missing measurements; limitations are server-rendered"
            )
    if (
        "shoulder_type" not in known
        and "shoulder_width" not in known
        and re.search(
            r"你的肩|您(?:的)?肩|肩部偏[宽窄]|your shoulders (?:are|look)|you have (?:broad|narrow) shoulders",
            plain,
            re.I,
        )
    ):
        raise ValueError("do not infer personal shoulder width without the self-report")
    if "skin_depth" not in known and re.search(
        r"你(?:的)?(?:肤色|皮肤)|your skin (?:is|looks|has)|you have .{0,12}skin", plain, re.I
    ):
        raise ValueError("do not claim personal skin depth when it was not provided")
    if "undertone" not in known and re.search(
        r"你(?:的)?[^。.!]{0,12}(?:暖皮|冷皮|冷调皮肤|暖调皮肤)|你(?:的)?(?:肤色|皮肤|底色)[^。.!]{0,8}(?:偏暖|偏冷|暖调|冷调|冷底|暖底)|your (?:warm|cool|neutral) undertone|your skin (?:is|looks) (?:warm|cool)|you have (?:a )?(?:warm|cool) undertone",
        plain,
        re.I,
    ):
        raise ValueError("do not infer personal undertone")
    if "hair_color" not in known and re.search(
        r"(?:你|您)的(?:黑发|金发|红发|棕发|灰发|白发)|your (?:black|brown|blond|red|grey|gray) hair",
        plain,
        re.I,
    ):
        raise ValueError("do not infer personal hair color")

    def replace(match):
        fact = known[match[1]]
        index = 0 if zh else 1
        value = fact_display(fact, zh)
        unit = fact.unit if fact.unit in {"cm", "kg"} else ""
        return f"{FACT_NAMES[fact.id][index]} {value}{unit}"

    rendered = TOKEN.sub(replace, text)
    # Resolve evidence IDs that a model repeats in prose into readable labels.
    for identifier in re.findall(r"\b[a-z]+_[a-z_]+\b", rendered):
        if identifier not in known or identifier not in FACT_NAMES:
            raise ValueError("prose contains an unknown internal field name")
    keys = [key for key in known if zh or "_" in key]
    pattern = r"\b(?:" + "|".join(re.escape(key) for key in keys) + r")\b"
    return re.sub(pattern, lambda match: FACT_NAMES[match[0]][0 if zh else 1], rendered)


def render_garment(garment: DraftGarment, zh: bool) -> dict:
    index = 0 if zh else 1
    color = COLORS[garment.color][index]
    material = MATERIALS[garment.material][index]
    fabric_labels = []
    if garment.fabric:
        fabric_labels = [
            CATALOG[key][value]["zh" if zh else "en"]
            for key, value in garment.fabric.model_dump().items()
        ]
    parts = [color, material, KINDS[garment.kind][index]]
    if garment.slot not in {"shoes", "accessory"}:
        parts.append(FITS[garment.fit][index])
        if garment.slot == "bottom":
            parts.extend(
                [
                    RISES[garment.rise][index],
                    ("短裤裤长" if zh else "shorts length")
                    if garment.kind == "shorts"
                    else PANT_LENGTHS[garment.length][index],
                ]
            )
        else:
            parts.append(LENGTHS[garment.length][index])
    return {
        **garment.model_dump(),
        "material_code": garment.material,
        "color_family": CATALOG["colors"][garment.color]["family"],
        "color_name": color,
        "material": material,
        "fabric_summary": (" · " if zh else "; ").join(fabric_labels) if fabric_labels else None,
        "description": ("，" if zh else ", ").join(parts) + ("。" if zh else "."),
    }


def missing_information(
    facts: list[BodyFact], zh: bool, include_styling: bool = False
) -> list[str]:
    available = {fact.id for fact in facts}
    warnings = {
        "inseam": (
            "未填写内腿长，不能据此判断腿长比例或确定裤内长。",
            "Inseam was not provided; leg proportions and trouser inseam cannot be determined.",
        ),
        "weight": (
            "未填写体重，不推测体重或身体成分。",
            "Weight was not provided; weight and body composition are not inferred.",
        ),
        "shoulder_type": (
            "未自述肩部特点，不能判断个人肩宽。",
            "Shoulder characteristics were not provided; personal shoulder width is unknown.",
        ),
    }
    result = [message[0 if zh else 1] for key, message in warnings.items() if key not in available]
    if include_styling:
        if "skin_depth" not in available or "undertone" not in available:
            result.append(
                "肤色深浅或底色倾向尚不明确；配色供比较尝试，不据此判断冷暖皮或规定禁色。"
                if zh
                else "Skin depth or undertone is unknown; colors are suggestions to compare, not a personal color diagnosis or a ban."
            )
        if "hair_color" not in available:
            result.append(
                "未填写发色，无法完整评估面部周围的颜色对比。"
                if zh
                else "Hair color is unknown, so contrast around the face cannot be fully assessed."
            )
        result.append(
            "面料特性是选款目标；实际成分、手感、弹性和洗护方式需查看商品标签并试穿。"
            if zh
            else "Fabric characteristics are selection targets; check actual fiber content, feel, stretch and care labels, and try the garment on."
        )
    return result
