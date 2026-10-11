"""Region classification and place descriptions."""
from __future__ import annotations

from .util import bearing_deg, compass, haversine_km, lon360


def region_of(data, lat: float, lon: float) -> str:
    lon = lon360(lon)
    for key, reg in data.regions.items():
        lat_lo, lat_hi = sorted(reg["lat"])
        lon_lo, lon_hi = sorted(reg["lon"])
        if lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi:
            return key
    return "elsewhere"


def region_label(region: str) -> str:
    return {"local": "Local", "kermadec": "Kermadec", "elsewhere": "Distant"}.get(region, region.title())


def describe(data, lat: float, lon: float) -> str:
    """GeoNet-style description: '23 km north-east of Seddon'."""
    lon = lon360(lon)
    best, best_d = None, 1e12
    for p in data.places_nz:
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        if d < best_d:
            best, best_d = p, d
    if best is not None and best_d <= 120:
        if best_d < 5:
            return f"Within 5 km of {best['name']}"
        direction = compass(bearing_deg(best["lat"], best["lon"], lat, lon))
        return f"{int(round(best_d / 5.0) * 5)} km {direction} of {best['name']}"
    pools = data.places_regions + data.places_global
    best, best_d = None, 1e12
    for p in pools:
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        if d < best_d:
            best, best_d = p, d
    return best["name"] if best else "Unknown region"


def short_place(description: str, limit: int = 22) -> str:
    """Trim '23 km north-east of Seddon' down to 'Seddon' for compact labels."""
    text = description
    if " of " in text:
        text = text.split(" of ", 1)[1]
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text
