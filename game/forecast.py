"""What kind of day a catalogue day is: a large quake, a swarm, a strong quake,
or just busy. Used for the day alerts on the planning screen, the forecast tool
and picking boss days."""
from __future__ import annotations

from collections import Counter

LARGE_MAG = 6.0
STRONG_MAG = 5.0
SWARM_CELL_DEG = 0.25        # events in the same ~25 km box count as one cluster
SWARM_MIN = 25               # at least this many in one box…
SWARM_SHARE = 0.3            # …and at least this share of the day's events

_CACHE: dict = {}


def classify(events: list) -> dict:
    """events: tuples (offset_min, mag, lat, lon, depth, desc, …). Returns
    {"kind": large|swarm|strong|busy, "mag": float, "place": str, "count": int}."""
    if not events:
        return {"kind": "busy", "mag": 0.0, "place": "", "count": 0}
    biggest = max(events, key=lambda e: e[1])
    cells = Counter((round(e[2] / SWARM_CELL_DEG), round((e[3] % 360.0) / SWARM_CELL_DEG)) for e in events)
    cell, n_cell = cells.most_common(1)[0]
    place = biggest[5] if len(biggest) > 5 else ""
    if biggest[1] >= LARGE_MAG:
        kind = "large"
    elif n_cell >= SWARM_MIN and n_cell >= SWARM_SHARE * len(events):
        kind = "swarm"
        in_cell = [e for e in events
                   if (round(e[2] / SWARM_CELL_DEG), round((e[3] % 360.0) / SWARM_CELL_DEG)) == cell]
        place = max(in_cell, key=lambda e: e[1])[5] if len(in_cell[0]) > 5 else place
    elif biggest[1] >= STRONG_MAG:
        kind = "strong"
    else:
        kind = "busy"
    return {"kind": kind, "mag": float(biggest[1]), "place": place or "", "count": n_cell if kind == "swarm" else 0}


def day_hazard(day) -> dict:
    """classify() for a planned day (DayPlan), cached."""
    key = (getattr(day, "index", None), getattr(day, "source", None), len(day.events))
    hz = _CACHE.get(key)
    if hz is None:
        hz = classify(day.events)
        if len(_CACHE) > 2000:
            _CACHE.clear()
        _CACHE[key] = hz
    return hz


def alert_level(percentile: float, levels=(0.5, 0.75, 0.9)) -> int:
    """0 = nothing to flag, 1 = yellow, 2 = orange, 3 = red."""
    return sum(1 for cut in levels if percentile >= cut)


KIND_NAMES = {"large": "Large earthquake", "swarm": "Earthquake swarm", "strong": "Strong earthquake",
              "busy": "Busy day"}


def hazard_text(hz: dict, detailed: bool) -> str:
    """'Earthquake swarm' or, with the forecast tool, 'Earthquake swarm near Taupō (60+ events)'."""
    name = KIND_NAMES.get(hz["kind"], "Busy day")
    if not detailed:
        return name
    if hz["kind"] in ("large", "strong"):
        bucket = int(hz["mag"] * 2) / 2.0
        return f"{name}, M{bucket:.1f}+" + (f" {hz['place']}" if hz["place"] else "")
    if hz["kind"] == "swarm":
        return f"{name}" + (f" {hz['place']}" if hz["place"] else "") + f" ({hz['count']} events)"
    return f"{name}, largest about M{hz['mag']:.1f}"


def hazard_short(hz: dict) -> str:
    """Compact version for a day card: 'Large quake M6.0+', 'Swarm, 60 events', 'Busy, up to M4.1'."""
    kind = hz["kind"]
    if kind in ("large", "strong"):
        word = "Large quake" if kind == "large" else "Strong quake"
        return f"{word} M{int(hz['mag'] * 2) / 2.0:.1f}+"
    if kind == "swarm":
        return f"Swarm, {hz['count']} events"
    return f"Busy, up to M{hz['mag']:.1f}"
