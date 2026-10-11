"""DART tsunami buoys: which buoys a quake sets off, and how far away they are.
The positions and trigger rule live in data/dart.json."""
from __future__ import annotations

import math

from .util import haversine_km, lon360


def trigger_radius_km(cfg: dict, mag: float) -> float:
    """How far (hypocentral km) a quake of this magnitude can set off a buoy."""
    return cfg["radius_km_at_min_mag"] * cfg["radius_mult_per_mag"] ** (mag - cfg["min_mag"])


def triggered_buoys(data, mag: float, lat: float, lon: float, depth: float) -> list:
    """[(buoy, distance_km)] for every buoy this quake sets off, nearest first."""
    cfg = data.dart_cfg
    if mag < cfg["min_mag"]:
        return []
    radius = trigger_radius_km(cfg, mag)
    hits = []
    for b in data.dart_buoys:
        epi = haversine_km(lat, lon360(lon), b["lat"], b["lon"])
        dist = math.hypot(epi, max(0.0, depth))
        if dist <= radius:
            hits.append((b, dist))
    hits.sort(key=lambda p: p[1])
    return hits


def buoy(data, code: str) -> dict | None:
    for b in data.dart_buoys:
        if b["code"] == code:
            return b
    return None
