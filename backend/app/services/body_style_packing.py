"""Trip packing: the fewest pieces that dress every day of a trip within the style rules.

Everything here is computed; no model is involved. Each day gets a season from its forecast
(or the calendar when the trip is beyond the forecast range), the pieces are drawn from a small
neutral capsule that is reworn across days, and every day's outfit is checked against that
day's own rules. A day the capsule cannot dress (a formal dinner, a cold evening) adds the
missing piece instead of breaking a rule.
"""

import logging
import math
import random
from datetime import date, timedelta

from pydantic import ValidationError

from app.models.user import User
from app.schemas.body_styling import BodyMeasurements, BodyStyleRequest, DraftGarment
from app.schemas.styling_profile import StylingProfile
from app.services.body_style_fallback import Palette, _allowed, _garment, _kind
from app.services.body_style_rendering import render_garment
from app.services.body_style_rules import StyleRules, build_rules, outfit_violations
from app.services.body_style_today import season_for
from app.services.wardrobe_matching import catalog_family, item_color_family, matches_kind
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)
MAX_DAYS = 21
# Base kinds per occasion, tried in order; the rules decide what is actually allowed.
DAY_TOPS = {
    "formal": ["shirt", "turtleneck", "knit"],
    "work": ["shirt", "polo", "knit"],
    "date": ["shirt", "knit", "polo"],
    "weekend": ["tshirt", "polo", "shirt"],
    "daily": ["tshirt", "shirt", "polo"],
}
DAY_BOTTOMS = {
    "formal": ["trousers"],
    "work": ["trousers", "chinos"],
    "date": ["chinos", "trousers", "jeans"],
    "weekend": ["jeans", "chinos", "shorts"],
    "daily": ["chinos", "jeans", "trousers"],
}
DAY_SHOES = {
    "formal": ["derbies", "oxfords", "loafers"],
    "work": ["loafers", "derbies"],
    "date": ["loafers", "derbies", "sneakers"],
    "weekend": ["sneakers", "loafers"],
    "daily": ["sneakers", "loafers"],
}


async def trip_forecast(lat: float | None, lon: float | None, start: date, days: int) -> dict:
    """Map ISO date -> (min, max) temperature for the days the forecast covers."""
    if lat is None or lon is None:
        return {}
    horizon = (start - date.today()).days + days
    if horizon > 16 or start < date.today():
        return {}
    try:
        forecast = await WeatherService().get_daily_forecast(lat, lon, days=max(horizon, 1))
    except Exception:
        logger.warning("Forecast unavailable for packing; using calendar seasons")
        return {}
    return {f.date: (f.temp_min, f.temp_max) for f in forecast}


def _key(g: dict) -> tuple:
    fabric = g["fabric"] or {}
    return (g["slot"], g["kind"], g["color"], fabric.get("weight"), g["material"])


class Capsule:
    """Pieces packed so far, reused across days whenever a day's rules allow them."""

    def __init__(self, profile: StylingProfile, zh: bool):
        self.pieces: list[dict] = []
        self.zh = zh
        self.profile = profile

        self.uses: list[int] = []

    def add(self, slot: str, kind: str, color: str, rules: StyleRules) -> int:
        garment = _garment(slot, kind, color, rules, self.zh)
        for index, piece in enumerate(self.pieces):
            if _key(piece) == _key(garment):
                return self.use(index)
        self.pieces.append(garment)
        self.uses.append(0)
        return self.use(len(self.pieces) - 1)

    def use(self, index: int) -> int:
        self.uses[index] += 1
        return index

    def piece(
        self, slot: str, rules: StyleRules, kinds: list[str], colors: list[str], target: int
    ) -> int:
        reused = self.reuse(slot, rules, kinds, target)
        if reused is not None:
            return reused
        packed = sum(p["slot"] == slot for p in self.pieces)
        return self.add(slot, _pick(kinds, rules, slot), colors[packed % len(colors)], rules)

    def reuse(self, slot: str, rules: StyleRules, kinds: list[str], target: int) -> int | None:
        """The least-worn packed piece for this slot that today's rules allow, once the
        slot already holds `target` pieces; otherwise None so a new piece is packed."""
        fitting = [
            index
            for index, piece in enumerate(self.pieces)
            if piece["slot"] == slot
            and not [
                e
                for e in outfit_violations([DraftGarment.model_validate(piece)], rules)
                if "requires outerwear" not in e
            ]
        ]
        if sum(piece["slot"] == slot for piece in self.pieces) < target:
            return None
        preferred = [i for i in fitting if self.pieces[i]["kind"] in kinds] or fitting
        if not preferred:
            return None
        return self.use(min(preferred, key=lambda i: self.uses[i]))


def _pick(options: list[str], rules: StyleRules, slot: str) -> str:
    for kind in options:
        if _allowed(rules, slot, kind):
            return kind
    return _kind(rules, slot, options[0])


def plan_trip(
    measurements: BodyMeasurements | None,
    profile: StylingProfile,
    style: str,
    days: list[dict],
    locale: str,
) -> dict:
    zh = locale.startswith("zh")
    capsule = Capsule(profile, zh)
    count = len(days)
    # Rewear: a top every other day at most, a bottom every three days, as on most trips.
    top_slots = max(2, math.ceil(count / 1.5)) if count > 1 else 1
    bottom_slots = max(1, math.ceil(count / 3))
    plans = []
    for day in days:
        rules = build_rules(
            measurements,
            profile,
            BodyStyleRequest(occasion=day["occasion"], style=style, season=day["season"]),
        )
        palette = Palette(profile, rules, random.Random(0))
        neutrals_light = [palette.light(exclude=[]), palette.light(exclude=[palette.light()])]
        accent = palette.chromatic[0] if palette.chromatic else neutrals_light[1]
        top_colors = [neutrals_light[0], accent, neutrals_light[1]]
        bottom_colors = [palette.dark(), palette.dark(exclude=[palette.dark()])]
        occasion = day["occasion"]

        chosen = [
            capsule.piece("top", rules, DAY_TOPS[occasion], top_colors, top_slots),
            capsule.piece("bottom", rules, DAY_BOTTOMS[occasion], bottom_colors, bottom_slots),
            capsule.piece("shoes", rules, DAY_SHOES[occasion], [palette.dark()], 1),
        ]
        cold = day["temp_min"] is not None and day["temp_min"] < 15
        if rules.season_rule.requires_outerwear or cold or occasion == "formal":
            options = ["coat", "down_jacket", "trench", "jacket", "blazer"]
            if occasion in {"formal", "work"}:
                options = ["suit_jacket", "blazer", "coat", "trench", *options]
            if rules.season == "summer":
                options = ["blazer", "overshirt"]
            allowed = [k for k in options if _allowed(rules, "outerwear", k)]
            if allowed:
                chosen.append(capsule.piece("outerwear", rules, allowed, [palette.dark()], 1))
        if occasion == "formal" and _allowed(rules, "accessory", "tie"):
            chosen.append(capsule.add("accessory", "tie", accent, rules))
        drafts = [DraftGarment.model_validate(capsule.pieces[i]) for i in chosen]
        errors = outfit_violations(drafts, rules)
        plans.append({**day, "pieces": chosen, "warnings": errors})
    pieces = []
    for index, garment in enumerate(capsule.pieces):
        rendered = render_garment(DraftGarment.model_validate(garment), zh)
        pieces.append(
            {
                "index": index,
                "slot": garment["slot"],
                "kind": garment["kind"],
                "color": garment["color"],
                "material": garment["material"],
                "description": rendered["description"],
                "days": [p["date"] for p in plans if index in p["pieces"]],
            }
        )
    return {"days": plans, "pieces": pieces}


def match_owned(pieces: list[dict], items: list) -> None:
    """Point each piece at an owned item of the same kind and color family, if there is one."""
    used: set = set()
    for piece in pieces:
        family = catalog_family(piece["color"])
        candidates = [i for i in items if i.id not in used and matches_kind(i, piece["kind"])]
        best = next((i for i in candidates if item_color_family(i) == family), None)
        best = best or (candidates[0] if candidates else None)
        piece["owned"] = (
            {"id": str(best.id), "name": best.name, "same_color": item_color_family(best) == family}
            if best
            else None
        )
        if best:
            used.add(best.id)


async def build_packing(
    user: User,
    start: date,
    end: date,
    occasions: list[str],
    style: str,
    location: tuple[float, float, str | None] | None,
    items: list,
) -> dict:
    count = (end - start).days + 1
    lat, lon, name = location if location else (None, None, None)
    forecast = await trip_forecast(lat, lon, start, count)
    days = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        temps = forecast.get(day.isoformat())
        middle = (temps[0] + temps[1]) / 2 if temps else None
        days.append(
            {
                "date": day.isoformat(),
                "occasion": occasions[offset % len(occasions)],
                "season": season_for(day, middle),
                "temp_min": temps[0] if temps else None,
                "temp_max": temps[1] if temps else None,
            }
        )
    profile = StylingProfile.model_validate(user.styling_profile or {})
    try:
        measurements = BodyMeasurements.model_validate(user.body_measurements or {})
    except ValidationError:
        measurements = None
    plan = plan_trip(measurements, profile, style, days, user.locale)
    match_owned(plan["pieces"], items)
    return {
        "location": name,
        "forecast_days": len(forecast),
        **plan,
    }
