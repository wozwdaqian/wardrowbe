"""Render-ready responses used only by isolated tests and the browser test server."""


def sample_result(height=175, waist=90):
    looks = []
    for index, (top, color, bottom) in enumerate(
        [
            ("shirt", "#718575", "trousers"),
            ("knit", "#d3be97", "jeans"),
            ("polo", "#465b70", "trousers"),
        ]
    ):
        high = waist >= 90
        pieces = [
            {
                "slot": "top",
                "kind": top,
                "color": color,
                "fit": "relaxed" if high else "regular",
                "length": "short",
                "rise": None,
                "material": "cotton",
            },
            {
                "slot": "bottom",
                "kind": bottom,
                "color": "#363c41",
                "fit": "regular",
                "length": "regular",
                "rise": "high" if high else "mid",
                "material": "cotton_blend",
            },
            {
                "slot": "shoes",
                "kind": "loafers" if index == 1 else "sneakers",
                "color": "#efe8dd",
                "fit": "regular",
                "length": "regular",
                "rise": None,
                "material": "leather",
            },
        ]
        for piece in pieces:
            piece["fabric_reason"] = "按该单品的活动需求与整体松量选择面料，购买时确认标签和手感。"
            piece["fabric"] = (
                None
                if piece["slot"] == "shoes"
                else {
                    "construction": "denim_weave"
                    if piece["kind"] == "jeans"
                    else "knit"
                    if piece["kind"] == "knit"
                    else "pique"
                    if piece["kind"] == "polo"
                    else "poplin"
                    if piece["slot"] == "top"
                    else "twill",
                    "weight": "medium",
                    "drape": "balanced",
                    "sheen": "matte",
                    "stretch": "slight",
                }
            )
        looks.append(
            {
                "title": ["短衬衫与直筒长裤", "针织衫与牛仔裤", "Polo 与利落长裤"][index],
                "garments": pieces,
                "body_reason": "根据{{height}}和{{waist}}，以短上衣与自然直落的裤腿安排腰线。",
                "evidence": ["height", "waist", "waist_chest_ratio"],
                "color_plan": {"strategy": "accent", "accent_slots": ["top"], "echo_slots": []},
                "color_reason": {
                    "text": "上衣作为重点色，深灰裤子和米白鞋作衔接，减少大面积颜色竞争。",
                    "evidence": [],
                },
                "fabric_reason": {
                    "text": "上衣与裤装采用中等厚度和哑光表面，以适中的垂坠感衔接轮廓。",
                    "evidence": [],
                },
                "styling_tip": "前摆轻塞入裤腰，侧面保持自然垂坠。",
            }
        )
    return {
        "summary": "从{{height}}、{{waist}}出发，把重点放在舒适腰部和清晰腰线上。",
        "observations": [
            {
                "text": "腰围与胸围的关系用于安排腰部松量，不据此推断体脂或体型标签。",
                "evidence": ["waist_chest_ratio"],
            },
            {
                "text": "上衣与裤子的分界优先结合身高和腰臀比例安排。",
                "evidence": ["height", "waist_hips_ratio"],
            },
        ],
        "fit_advice": [
            {"area": area, "text": text, "evidence": ["height", "waist_chest_ratio"]}
            for area, text in [
                ("top_length", "上衣下摆靠近腰线，避免在臀下堆积。"),
                ("trouser_rise", "以舒适的中高腰建立腰线，坐下时不勒腰。"),
                ("trouser_leg", "优先尝试直筒裤腿，保持从臀到鞋面的连续线条。"),
                ("outerwear", "选择肩线清楚、腰部有活动量的外套。"),
            ]
        ],
        "color_guidance": {
            "text": "先用上衣重点色与中性色组合比较不同配色，结合实际穿着反馈调整。",
            "evidence": [],
        },
        "fabric_guidance": {
            "text": "优先比较面料厚薄、组织与垂坠；具体商品的成分和手感还需核对。",
            "evidence": [],
        },
        "outfits": looks,
    }
