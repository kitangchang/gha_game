"""Small helpers shared across the game package."""
from __future__ import annotations

import math
import random

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAMES_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lon360(lon: float) -> float:
    return lon % 360.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Bearing from point 1 to point 2, degrees clockwise from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def compass(bearing: float) -> str:
    return _COMPASS[int(((bearing + 22.5) % 360) // 45)]


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def weighted_choice(rng: random.Random, items: list, weights: list):
    total = sum(weights)
    if total <= 0:
        return rng.choice(items)
    pick = rng.random() * total
    acc = 0.0
    for item, w in zip(items, weights):
        acc += w
        if pick <= acc:
            return item
    return items[-1]


def fmt_clock(abs_minutes: float, day_start_hour: int) -> str:
    """Clock time for an absolute game minute (minute 0 = day 1 at day_start_hour)."""
    total = int(abs_minutes) + day_start_hour * 60
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


def fmt_minutes(minutes: float) -> str:
    """Compact duration, e.g. 7m, 1h05, 2d03h."""
    m = int(round(abs(minutes)))
    if m < 60:
        return f"{m}m"
    if m < 1440:
        return f"{m // 60}h{m % 60:02d}"
    return f"{m // 1440}d{(m % 1440) // 60:02d}h"


def fmt_money(k: float) -> str:
    sign = "-" if k < 0 else ""
    return f"{sign}${abs(k):.1f}k"


def parse_hhmm(text: str) -> int:
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)
