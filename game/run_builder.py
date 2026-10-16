"""Precomputes a whole run when it starts: which catalogue day plays on each
game day (by workload percentile, ramping up through the run), special weeks,
'?' event days and the business-as-usual schedule."""
from __future__ import annotations

import random

from .forecast import classify
from .geo import describe, region_of
from .models import DayPlan, WeekPlan
from .tasks import estimate_event_work, sops_for
from .util import DAY_NAMES, clamp, lerp, parse_hhmm, poisson, weighted_choice

BURST_WINDOW = 180.0   # minutes


def score_days(data, catalog):
    """Workload score per catalogue day = total expected analyst-minutes plus
    half the busiest 3-hour window (bursty days are harder)."""
    if catalog.scored:
        return
    for day in catalog.days:
        works = []
        sop_count = 0
        for ev in day.events:
            region = region_of(data, ev[2], ev[3])
            works.append((ev[0], estimate_event_work(data, ev[1], ev[4], region)))
            if sops_for(data, ev[1], ev[4], region):
                sop_count += 1
        total = sum(w for _, w in works)
        peak, acc, lo = 0.0, 0.0, 0
        for hi in range(len(works)):
            acc += works[hi][1]
            while works[hi][0] - works[lo][0] > BURST_WINDOW:
                acc -= works[lo][1]
                lo += 1
            peak = max(peak, acc)
        day.score = total + 0.5 * peak
        day.sop_count = sop_count
    ranked = sorted(catalog.days, key=lambda d: d.score)
    n = max(1, len(ranked) - 1)
    for i, day in enumerate(ranked):
        day.percentile = i / n
    catalog.scored = True


def _pick_day(rng, ranked, used, target, window):
    w = window
    while w < 1.5:
        cands = [d for d in ranked if d.key not in used and abs(d.percentile - target) <= w]
        if cands:
            return rng.choice(cands)
        w *= 2
    free = [d for d in ranked if d.key not in used]
    if not free:
        used.clear()
        free = ranked
    return min(free, key=lambda d: abs(d.percentile - target))


def _pick_boss(rng, ranked, used, boss_pct, boss_max):
    top = [d for d in ranked if boss_pct <= d.percentile <= boss_max and d.key not in used]
    with_sop = [d for d in top if d.sop_count > 0]
    dramatic = [d for d in with_sop if classify(d.events)["kind"] in ("large", "swarm")]
    if dramatic:
        return rng.choice(dramatic)
    if with_sop:
        return rng.choice(with_sop)
    any_sop = [d for d in ranked if d.sop_count > 0 and d.key not in used]
    if any_sop:
        return max(any_sop, key=lambda d: d.score)
    return top[-1] if top else ranked[-1]


def _on_day(sched: dict, weekday: int, minute: int, day_start: int) -> bool:
    """Does a 'days'-limited schedule fire at this clock time in this game day?
    A game day runs from day_start to day_start next morning, so e.g. Tue 02:00
    falls in Monday's game day."""
    days = sched.get("days")
    if not days:
        return True
    calendar_day = (weekday + (1 if minute < day_start else 0)) % 7
    return DAY_NAMES[calendar_day] in {d[:3].title() for d in days}


def _bau_schedule(data, rng, rate_scale: float, special, weekday: int = 0) -> list:
    day_start = data.config["time"]["day_start_hour"] * 60
    items = []
    for bau in data.bau.values():
        sched = bau.get("schedule", {})
        kind = sched.get("type")
        if kind in ("daily", "times"):
            times = [sched["at"]] if kind == "daily" else sched.get("at", [])
            for at in times:
                minute = parse_hhmm(at)
                if _on_day(sched, weekday, minute, day_start):
                    items.append(((minute - day_start) % 1440, bau["id"]))
        elif kind == "random":
            for _ in range(poisson(rng, sched.get("per_day", 0) * rate_scale)):
                items.append((rng.random() * 1440.0, bau["id"]))
    if special and special.get("spawn_daily"):
        sd = special["spawn_daily"]
        items.append(((parse_hhmm(sd.get("at", "12:00")) - day_start) % 1440, sd["task"]))
    items.sort()
    return items


def _pick_weekly_boss(rng, ranked, used, target, window):
    """A hard day near the target, preferring a large quake or a swarm."""
    w = window
    while w < 0.6:
        cands = [d for d in ranked if d.key not in used and abs(d.percentile - target) <= w]
        dramatic = [d for d in cands if classify(d.events)["kind"] in ("large", "swarm")]
        if dramatic:
            return rng.choice(dramatic)
        if len(cands) >= 6:
            return rng.choice(cands)
        w *= 2
    return _pick_day(rng, ranked, used, target, window)


def build_plan(data, catalog, rng: random.Random, weeks: int) -> list:
    score_days(data, catalog)
    diff = data.config["difficulty"]
    ev_cfg = data.config["events"]
    day_start = data.config["time"]["day_start_hour"]
    ranked = sorted(catalog.days, key=lambda d: d.score)
    used: set = set()
    desc_cache: dict = {}
    plan = []

    specials = list(data.special_weeks.values())
    for w in range(weeks):
        special = None
        if specials and w + 1 >= ev_cfg["special_week_first_week"] and rng.random() < ev_cfg["special_week_chance"]:
            pool = [s for s in specials if w < weeks - 1 or s.get("final_week", True)]
            special = weighted_choice(rng, pool, [s.get("weight", 1.0) for s in pool]) if pool else None
        shift = special.get("difficulty_shift", 0.0) if special else 0.0
        week_base = lerp(diff["start_percentile"], diff["end_percentile"], w / max(1, weeks - 1))
        n_rand = rng.randint(ev_cfg["random_event_days_min"], ev_cfg["random_event_days_max"])
        rand_days = set(rng.sample(range(7), min(7, n_rand)))
        days = []
        for d in range(7):
            mult = float(special.get("difficulty_mult", 1.0)) if special else 1.0      # Quiet Week: 0.8
            target = clamp((week_base + diff["within_week_ramp"] * (d / 6.0 - 0.5)
                            + rng.gauss(0, diff["noise"])) * mult + shift,
                           0.01, diff.get("max_target_percentile", 0.95))
            final = diff.get("boss_final_day", True) and w == weeks - 1 and d == 6
            weekly = diff.get("weekly_boss", True) and d == 6 and not final
            boss = final or weekly
            if final:
                day = _pick_boss(rng, ranked, used, diff["boss_percentile"], diff.get("boss_max_percentile", 1.0))
            elif weekly:
                target = clamp(target + diff.get("weekly_boss_boost", 0.15), 0.01,
                               diff.get("max_target_percentile", 0.95))
                day = _pick_weekly_boss(rng, ranked, used, target, diff["pick_window"])
            else:
                day = _pick_day(rng, ranked, used, target, diff["pick_window"])
            used.add(day.key)

            scale = diff["event_volume_scale"]
            events = []
            for ev in day.events:
                if scale < 1.0 and ev[1] <= diff["volume_scale_max_mag"] and rng.random() > scale:
                    continue
                desc = ev[5]
                if not desc:
                    key = (round(ev[2], 2), round(ev[3], 2))
                    desc = desc_cache.get(key)
                    if desc is None:
                        desc = describe(data, ev[2], ev[3])
                        desc_cache[key] = desc
                events.append((ev[0], ev[1], ev[2], ev[3], ev[4], desc, ev[6], ev[7]))
            cap = diff.get("max_events_per_day", 0)
            if cap and len(events) > cap:
                # Thin out the smallest events so no single day is impossible.
                small = [e for e in events if e[1] < 2.5]
                rng.shuffle(small)
                drop = set(id(e) for e in small[: len(events) - cap])
                events = [e for e in events if id(e) not in drop]

            rate_scale = lerp(diff["bau_rate_min"], diff["bau_rate_max"], clamp(target, 0, 1))
            random_at = None
            if d in rand_days:
                lo, hi = ev_cfg["random_event_hours"]
                hour = rng.uniform(lo, hi)
                random_at = ((hour - day_start) * 60.0) % 1440.0
            days.append(DayPlan(
                index=w * 7 + d, source=day.label, events=events,
                bau=_bau_schedule(data, rng, rate_scale, special, d),
                score=day.score, percentile=day.percentile, target=target, boss=boss, final=final,
                random_event_at=random_at, max_mag=day.max_mag, sop_count=day.sop_count,
            ))
        plan.append(WeekPlan(index=w, days=days, special=special["id"] if special else None))
    return plan
