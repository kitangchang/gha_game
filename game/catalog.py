"""Earthquake catalogue loading.

Looks in data/catalog/ for a CSV. Understands:
  * the NGMC eq_stats archive.csv (event_id, solution_key, event_type, status,
    origin_time, description, longitude, latitude, depth, author,
    creation_time, magnitude, mag_type). Multiple solutions per event are
    collapsed to the latest one.
  * GeoNet quakesearch CSV exports (publicid, eventtype, origintime, ...).
  * FDSN text output ('|' separated, #EventID|Time|Latitude|...).
If nothing is found, a synthetic NZ-like catalogue is generated instead.
"""
from __future__ import annotations

import csv
import math
import pickle
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .data import ROOT
from .tz import local_minutes

LOADER_VERSION = 5

ALIASES = {
    "event_id": ["event_id", "publicid", "eventid", "id"],
    "origin_time": ["origin_time", "origintime", "time", "origin time", "datetime"],
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "long"],
    "depth": ["depth", "depth/km", "depth_km", "depthkm"],
    "magnitude": ["magnitude", "mag"],
    "description": ["description", "eventlocationname", "location", "place"],
    "event_type": ["event_type", "eventtype"],
    "creation_time": ["creation_time", "modificationtime", "updated", "creationtime"],
}
KEEP_TYPES = {"", "earthquake", "induced or triggered event", "nan", "none", "null"}


class CatalogDay:
    __slots__ = ("key", "label", "events", "score", "percentile", "max_mag", "sop_count")

    def __init__(self, key: int, label: str, events: list):
        self.key = key
        self.label = label
        self.events = events          # tuples (offset_min, mag, lat, lon, depth, desc, event_id, origin_time)
        self.score = 0.0
        self.percentile = 0.0
        self.max_mag = max((e[1] for e in events), default=0.0)
        self.sop_count = 0


class Catalog:
    def __init__(self, events: list, label: str, source: str, synthetic: bool, day_start_hour: int, min_events: int):
        self.events = events          # tuples (local_minute, mag, lat, lon, depth, desc, event_id, origin_time)
        self.label = label
        self.source = source
        self.synthetic = synthetic
        self.days = self._split_days(day_start_hour, min_events)
        self.scored = False

    def _split_days(self, day_start_hour: int, min_events: int) -> list:
        start = day_start_hour * 60
        buckets: dict = {}
        for ev in self.events:
            rel = ev[0] - start
            key = int(math.floor(rel / 1440.0))
            buckets.setdefault(key, []).append((rel - key * 1440.0,) + tuple(ev[1:]))
        if not buckets:
            return []
        keys = sorted(buckets)
        first_key = keys[0]
        if len(keys) > 2:
            keys = keys[1:-1]      # first/last windows are usually partial
        days = []
        for key in keys:
            evs = buckets[key]
            if len(evs) < min_events:
                continue
            evs.sort(key=lambda e: e[0])
            if self.synthetic:
                label = f"Synthetic day {key - first_key + 1}"
            else:
                dt = datetime(1970, 1, 1) + timedelta(minutes=key * 1440 + start)
                label = dt.strftime("%Y-%m-%d")
            days.append(CatalogDay(key, label, evs))
        return days

    def summary(self) -> str:
        n_days = len(self.days)
        per_day = (sum(len(d.events) for d in self.days) / n_days) if n_days else 0
        return f"{self.label} · {len(self.events):,} events · {n_days:,} usable days · ~{per_day:.0f}/day"


# ----------------------------------------------------------------------- parsing
_FRACTION = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)(\.\d+)?(.*)$")


def parse_time(text: str) -> float | None:
    """Parse an ISO-ish timestamp to UTC epoch seconds."""
    s = (text or "").strip()
    if not s:
        return None
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    m = _FRACTION.match(s)
    if m:
        base, frac, tail = m.groups()
        frac = (frac or ".0")[1:7].ljust(6, "0")
        s = f"{base.replace(' ', 'T')}.{frac}{tail.strip()}"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _norm(name: str) -> str:
    return name.strip().lstrip("#").strip().lower()


def _column_map(header: list) -> dict:
    normed = [_norm(h) for h in header]
    found = {}
    for key, options in ALIASES.items():
        for opt in options:
            if opt in normed:
                found[key] = normed.index(opt)
                break
    return found


def _to_float(text, default=None):
    try:
        value = float(text)
        if math.isnan(value):
            return default
        return value
    except (TypeError, ValueError):
        return default


def load_csv(path: Path, utc_offset_hours: float, daylight_saving: bool = True) -> list:
    """Events as (local_minute, ...) tuples. Local time is NZ time (NZST/NZDT) when
    daylight_saving is on, otherwise UTC + utc_offset_hours."""
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        first = fh.readline()
        fh.seek(0)
        delim = "|" if first.count("|") > first.count(",") else ("\t" if "\t" in first else ",")
        reader = csv.reader(fh, delimiter=delim)
        header = next(reader)
        cols = _column_map(header)
        missing = [k for k in ("origin_time", "latitude", "longitude", "magnitude") if k not in cols]
        if missing:
            raise ValueError(f"{path.name}: missing column(s) {', '.join(missing)}")
        best: dict = {}
        anon = 0
        for row in reader:
            if not row:
                continue
            try:
                get = lambda k: row[cols[k]] if k in cols and cols[k] < len(row) else ""  # noqa: E731
                etype = get("event_type").strip().lower()
                if etype not in KEEP_TYPES:
                    continue
                mag = _to_float(get("magnitude"))
                lat = _to_float(get("latitude"))
                lon = _to_float(get("longitude"))
                if mag is None or lat is None or lon is None:
                    continue
                t = parse_time(get("origin_time"))
                if t is None:
                    continue
                depth = _to_float(get("depth"), 10.0)
                eid = get("event_id").strip()
                if not eid:
                    anon += 1
                    eid = f"row{anon}"
                created = get("creation_time").strip()
                desc = get("description").strip()
                prev = best.get(eid)
                if prev is not None and created and prev[0] and created < prev[0]:
                    if desc and not prev[1][5]:   # keep a place name from an older solution
                        best[eid] = (prev[0], prev[1][:5] + (desc,) + prev[1][6:])
                    continue
                if prev is not None and not desc:
                    desc = prev[1][5]
                local_min = local_minutes(t, daylight_saving, utc_offset_hours)
                best[eid] = (created, (local_min, round(mag, 2), lat, lon % 360.0, max(0.0, depth),
                                       desc, eid, get("origin_time").strip()))
            except IndexError:
                continue
    events = [v[1] for v in best.values()]
    events.sort(key=lambda e: e[0])
    return events


def _candidates(folder: Path) -> list:
    """Catalogue files, newest first (README files are ignored)."""
    if not folder.exists():
        return []
    files = [p for pattern in ("*.csv", "*.txt") for p in folder.glob(pattern)
             if p.is_file() and not p.name.startswith(".") and not p.name.lower().startswith("readme")]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def load_catalog(data, progress=None) -> Catalog:
    cfg = data.config["catalog"]
    folder = ROOT / cfg["folder"]
    cache_dir = folder / ".cache"
    day_start = data.config["time"]["day_start_hour"]
    min_events = cfg["min_events_per_day"]
    for path in _candidates(folder):
        stat = path.stat()
        dst = bool(cfg.get("nz_daylight_saving", True))
        cache_key = (f"{path.name}-{stat.st_size}-{int(stat.st_mtime)}-{cfg['utc_offset_hours']}-dst{int(dst)}"
                     f"-v{LOADER_VERSION}")
        cache_file = cache_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", cache_key) + ".pkl")
        events = None
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as fh:
                    events = pickle.load(fh)
            except Exception:
                events = None
        if events is None:
            if progress:
                progress(f"Reading {path.name}…")
            try:
                events = load_csv(path, cfg["utc_offset_hours"], dst)
            except (ValueError, StopIteration, UnicodeDecodeError) as exc:
                if progress:
                    progress(f"Skipping {path.name}: {exc}")
                continue
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                for old in cache_dir.glob(re.sub(r"[^A-Za-z0-9_.-]", "_", path.name) + "-*.pkl"):
                    old.unlink()
                with open(cache_file, "wb") as fh:
                    pickle.dump(events, fh)
            except OSError:
                pass
        if events:
            first = datetime(1970, 1, 1) + timedelta(minutes=events[0][0])
            last = datetime(1970, 1, 1) + timedelta(minutes=events[-1][0])
            label = f"{path.name} ({first:%Y}-{last:%Y})"
            return Catalog(events, label, str(path), False, day_start, min_events)

    from .synth import generate_synthetic
    seed = cfg["synthetic_seed"]
    cache_file = cache_dir / f"synthetic-{seed}-{cfg['synthetic_years']}-{cfg['synthetic_background_per_day']}-v{LOADER_VERSION}.pkl"
    events = None
    if cache_file.exists():
        try:
            with open(cache_file, "rb") as fh:
                events = pickle.load(fh)
        except Exception:
            events = None
    if events is None:
        if progress:
            progress("Generating a synthetic catalogue…")
        events = generate_synthetic(data, seed, cfg["synthetic_years"], cfg["synthetic_background_per_day"])
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "wb") as fh:
                pickle.dump(events, fh)
        except OSError:
            pass
    return Catalog(events, "Synthetic NZ catalogue", "synthetic", True, day_start, min_events)
