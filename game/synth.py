"""Synthetic NZ-like earthquake catalogue, used when no real catalogue CSV is
present. Not real data: background seismicity in rough NZ source zones,
Gutenberg-Richter magnitudes, Omori aftershock sequences, volcanic swarms,
plus a handful of scripted large events so SOP days exist."""
from __future__ import annotations

import math
import random

# (name, weight, lat range, lon range, depth model, Mc, Mmax)
ZONES = [
    ("hikurangi", 0.30, (-41.8, -37.0), (174.6, 179.0), "slab", 1.3, 7.2),
    ("tvz", 0.12, None, None, "tvz", 1.2, 6.0),
    ("cook_strait", 0.16, (-42.6, -40.8), (172.8, 175.6), "mixed_shallow", 1.3, 7.2),
    ("canterbury", 0.07, (-43.9, -43.2), (171.6, 173.0), "crustal", 1.3, 6.5),
    ("alpine", 0.07, None, None, "alpine", 1.4, 7.5),
    ("fiordland", 0.10, (-46.6, -44.4), (165.8, 168.2), "fiordland", 1.6, 7.3),
    ("kermadec", 0.03, (-33.0, -25.5), (181.0, 184.0), "kermadec", 3.2, 8.0),
    ("offshore_east", 0.05, (-41.5, -36.5), (178.5, 180.5), "interface", 1.8, 7.5),
    ("bop_deep", 0.04, (-37.8, -36.6), (176.3, 178.2), "deep", 1.9, 6.5),
    ("northland", 0.01, (-36.5, -34.5), (172.8, 175.0), "crustal", 1.5, 5.5),
    ("otago", 0.04, (-46.3, -44.5), (168.5, 171.0), "crustal", 1.4, 6.0),
]

# (fraction through catalogue, lat, lon, depth, mag)
SCRIPTED = [
    (0.08, -41.75, 174.25, 12.0, 6.4),    # Cook Strait, local tsunami SOP
    (0.17, -29.90, 182.30, 35.0, 7.1),    # Kermadec
    (0.22, -38.80, 176.00, 6.0, 5.2),     # Taupō
    (0.29, -21.00, 289.50, 30.0, 7.8),    # Northern Chile, distant SOP
    (0.35, -43.50, 172.30, 8.0, 5.7),     # Canterbury
    (0.41, -38.90, 178.60, 22.0, 6.8),    # offshore Gisborne, local tsunami SOP
    (0.48, -31.60, 181.60, 60.0, 6.7),    # Kermadec
    (0.53, -41.30, 175.00, 25.0, 4.8),    # Wellington
    (0.59, -45.30, 166.90, 25.0, 6.1),    # Fiordland, local tsunami SOP
    (0.64, 38.00, 142.50, 20.0, 7.6),     # Japan, distant SOP
    (0.70, -39.70, 176.60, 30.0, 5.0),    # Hawke's Bay
    (0.75, -39.40, 174.40, 220.0, 6.0),   # deep Taranaki (no tsunami SOP)
    (0.81, -28.50, 182.60, 120.0, 6.9),   # Kermadec
    (0.86, -42.30, 173.80, 15.0, 4.5),    # Kaikōura
    (0.90, -20.00, 186.50, 40.0, 8.0),    # Tonga, distant SOP
    (0.95, -40.60, 176.40, 18.0, 6.3),    # Wairarapa coast, local tsunami SOP
]


def _gr(rng: random.Random, mc: float, mmax: float, b: float = 1.0) -> float:
    u = rng.random()
    return mc - math.log10(1.0 - u * (1.0 - 10 ** (-b * (mmax - mc)))) / b


def _slab_depth(lon: float) -> float:
    return 12.0 + max(0.0, 178.6 - lon) ** 1.3 * 38.0


def _depth(rng: random.Random, model: str, lat: float, lon: float) -> float:
    if model == "slab":
        if rng.random() < 0.6:
            return max(5.0, _slab_depth(lon) + rng.gauss(0, 10))
        return rng.uniform(5, 25)
    if model == "tvz":
        return rng.uniform(2, 9)
    if model == "mixed_shallow":
        return rng.uniform(5, 20) if rng.random() < 0.45 else rng.uniform(20, 80)
    if model in ("crustal", "alpine"):
        return rng.uniform(3, 15)
    if model == "fiordland":
        return rng.uniform(5, 30) if rng.random() < 0.5 else rng.uniform(30, 150)
    if model == "kermadec":
        return rng.uniform(10, 60) if rng.random() < 0.6 else rng.uniform(60, 300)
    if model == "interface":
        return rng.uniform(10, 40)
    if model == "deep":
        return rng.uniform(150, 300)
    return rng.uniform(5, 30)


def _location(rng: random.Random, zone) -> tuple:
    name, _, lat_r, lon_r, _, _, _ = zone
    if name == "tvz":
        t = rng.random()
        lat = -39.3 + t * 1.7 + rng.gauss(0, 0.08)
        lon = 175.6 + t * 1.4 + rng.gauss(0, 0.08)
        return lat, lon
    if name == "alpine":
        t = rng.random()
        lat = -44.4 + t * 2.6 + rng.gauss(0, 0.12)
        lon = 168.6 + t * 3.7 + rng.gauss(0, 0.12)
        return lat, lon
    return rng.uniform(*lat_r), rng.uniform(*lon_r)


def _offset(rng: random.Random, lat: float, lon: float, sigma_km: float) -> tuple:
    dlat = rng.gauss(0, sigma_km) / 111.0
    dlon = rng.gauss(0, sigma_km) / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def _omori_time(rng: random.Random, c: float, p: float, t_max: float) -> float:
    """Sample a time (days) from a truncated Omori-Utsu decay."""
    u = rng.random()
    a = (1.0 + t_max / c) ** (1.0 - p)
    return c * ((1.0 - u * (1.0 - a)) ** (1.0 / (1.0 - p)) - 1.0)


def _aftershocks(rng, main_t, lat, lon, depth, mag, mc, out):
    if mag < mc + 2.8:
        return
    n = min(2500, int(round(10 ** (0.85 * (mag - mc - 1.8)))))
    t_max = 60.0 if mag >= 6 else 25.0
    sigma = 10 ** (0.5 * mag - 2.1)
    mc_a = max(mc, 1.5)
    for _ in range(n):
        dt_days = _omori_time(rng, 0.01, 1.1, t_max)
        am = _gr(rng, mc_a, mag - 0.6, 1.05)
        alat, alon = _offset(rng, lat, lon, sigma)
        ad = max(1.0, depth + rng.gauss(0, max(2.0, depth * 0.1)))
        out.append((main_t + dt_days * 1440.0, am, alat, alon, ad))


def generate_synthetic(data, seed: int, years: float, background_per_day: float) -> list:
    rng = random.Random(seed)
    n_days = int(years * 365)
    base = 60 * 24 * 365 * 60          # arbitrary local-minute origin (year 2030)
    raw: list = []                     # (minute_from_start, mag, lat, lon, depth)
    weights = [z[1] for z in ZONES]
    total_w = sum(weights)

    # Background seismicity, with occasional busier periods.
    for day in range(n_days):
        lam = background_per_day * (1.0 + 0.25 * math.sin(day / 37.0) + 0.15 * math.sin(day / 11.0 + 1.3))
        k = max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
        for _ in range(k):
            pick = rng.random() * total_w
            acc = 0.0
            zone = ZONES[-1]
            for z in ZONES:
                acc += z[1]
                if pick <= acc:
                    zone = z
                    break
            lat, lon = _location(rng, zone)
            depth = _depth(rng, zone[4], lat, lon)
            mc = zone[5] + (0.4 if depth > 150 else 0.2 if depth > 60 else 0.0)
            mag = _gr(rng, mc, zone[6], 1.0)
            t = day * 1440.0 + rng.random() * 1440.0
            raw.append((t, mag, lat, lon, depth))
            _aftershocks(rng, t, lat, lon, depth, mag, mc, raw)

    # Teleseismic events that analysts would review.
    for day in range(n_days):
        for _ in range(int(rng.random() < 0.35)):
            place = rng.choice(data.places_global)
            lat = place["lat"] + rng.gauss(0, 1.5)
            lon = place["lon"] + rng.gauss(0, 1.5)
            depth = rng.uniform(10, 60) if rng.random() < 0.8 else rng.uniform(100, 600)
            raw.append((day * 1440.0 + rng.random() * 1440.0, _gr(rng, 5.4, 7.6, 1.0), lat, lon, depth))

    # Volcanic swarms in the TVZ.
    for _ in range(int(years * 3)):
        day = rng.randrange(30, max(31, n_days - 30))
        clat, clon = _location(rng, ZONES[1])
        n = rng.randint(30, 120)
        span = rng.uniform(0.6, 2.5) * 1440.0
        start = day * 1440.0 + rng.random() * 1440.0
        for _ in range(n):
            lat, lon = _offset(rng, clat, clon, 2.5)
            raw.append((start + rng.random() * span, _gr(rng, 1.2, 4.0, 1.2), lat, lon, rng.uniform(3, 8)))

    # Scripted large events.
    for frac, lat, lon, depth, mag in SCRIPTED:
        t = int(frac * n_days) * 1440.0 + rng.random() * 1440.0
        raw.append((t, mag, lat, lon, depth))
        if lat < -25:
            _aftershocks(rng, t, lat, lon, depth, mag, 1.4 if lat < -33 else 3.2, raw)

    events = []
    for i, (t, mag, lat, lon, depth) in enumerate(sorted(raw)):
        if t < 0 or t >= n_days * 1440.0:
            continue
        events.append((base + t, round(mag, 1), round(lat, 3), round(lon % 360.0, 3), round(depth, 1),
                       "", f"syn{i:06d}", ""))
    return events
