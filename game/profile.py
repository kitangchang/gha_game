"""Centre profiles: the meta-progression kept in each save slot. Analysts are
never carried between runs, but centre XP, levels and unlocked items are."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

CATEGORIES = (("tools", "relics"), ("supplies", "consumables"), ("training", "training"))


@dataclass
class Profile:
    slot: int
    name: str = ""
    xp: float = 0.0
    runs: int = 0
    wins: int = 0
    best_score: int = 0
    total_weeks: int = 0
    history: list = field(default_factory=list)    # newest last: dicts from finish_run()
    run: object = None                             # RunState in progress (or None)
    created: str = ""
    last_played: str = ""

    @property
    def title(self) -> str:
        return self.name or f"Monitoring Centre {self.slot}"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def new_profile(slot: int) -> Profile:
    stamp = now_stamp()
    return Profile(slot=slot, created=stamp, last_played=stamp)


# ------------------------------------------------------------------ levels
def level_table(data) -> list:
    return list(data.config["centre"]["level_xp"])


def max_level(data) -> int:
    return len(level_table(data))


def level_for_xp(data, xp: float) -> int:
    level = 1
    for i, need in enumerate(level_table(data)):
        if xp >= need:
            level = i + 1
    return level


def xp_progress(data, xp: float) -> tuple:
    """(level, xp into this level, xp needed for the next level or None at max)."""
    table = level_table(data)
    level = level_for_xp(data, xp)
    if level >= len(table):
        return level, xp - table[-1], None
    return level, xp - table[level - 1], table[level] - table[level - 1]


def unlock_level(item: dict) -> int:
    return int(item.get("unlock_level", 1))


def unlocked_ids(data, attr: str, level: int) -> list:
    return [i for i, item in getattr(data, attr).items() if unlock_level(item) <= level]


def unlock_track(data) -> dict:
    """{level: [(category, item id), ...]} for every item that needs a centre level above 1."""
    track: dict = {}
    for cat, attr in CATEGORIES:
        for iid, item in getattr(data, attr).items():
            lvl = unlock_level(item)
            if lvl > 1:
                track.setdefault(lvl, []).append((cat, iid))
    return dict(sorted(track.items()))


def unlocks_between(data, old_level: int, new_level: int) -> list:
    out = []
    for lvl, items in unlock_track(data).items():
        if old_level < lvl <= new_level:
            out.extend(items)
    return out


# ---------------------------------------------------------------- run end
def run_score(run) -> int:
    t = run.totals
    return int(run.rating * 10 + t["ontime"] * 0.5 + t["sops"] * 25 - t["errors"] * 3)


def run_xp(data, weeks_completed: int, weeks_total: int, tasks: int, sops: int, won: bool, trust: float) -> list:
    """[(label, xp)] breakdown."""
    cfg = data.config["centre"]["xp"]
    rows = [(f"{weeks_completed} week{'s' if weeks_completed != 1 else ''} completed",
             weeks_completed * cfg["per_week"]),
            (f"{sops} SOP event{'s' if sops != 1 else ''} handled", sops * cfg["per_sop"]),
            (f"{tasks:,} tasks done", tasks * cfg["per_task"])]
    if won:
        rows.append((f"Season complete ({weeks_total} weeks)", weeks_total * cfg["win_per_week"]))
        rows.append((f"Final public trust {trust:.0f}", trust * cfg["win_trust"]))
    return [(label, round(value)) for label, value in rows]


def finish_run(data, profile: Profile, run, won: bool, extra: dict | None = None) -> dict:
    """Add a finished run to the profile. extra: stats from the week that was cut short
    (tasks, sops) when the run is lost mid-week."""
    extra = extra or {}
    tasks = run.totals["tasks"] + extra.get("tasks", 0)
    sops = run.totals["sops"] + extra.get("sops", 0)
    weeks_completed = run.weeks_total if won else run.week
    breakdown = run_xp(data, weeks_completed, run.weeks_total, tasks, sops, won, run.rating)
    gained = sum(v for _, v in breakdown)
    old_level = level_for_xp(data, profile.xp)
    profile.xp += gained
    new_level = level_for_xp(data, profile.xp)
    score = run_score(run) if won else 0
    profile.runs += 1
    profile.wins += 1 if won else 0
    profile.best_score = max(profile.best_score, score)
    profile.total_weeks += weeks_completed
    result = {"date": now_stamp(), "length": run.length_key, "weeks": weeks_completed, "weeks_total": run.weeks_total,
              "won": won, "score": score, "trust": round(run.rating, 1), "xp": gained, "breakdown": breakdown,
              "old_level": old_level, "new_level": new_level, "unlocks": unlocks_between(data, old_level, new_level),
              "seed": run.seed}
    profile.history.append(result)
    profile.history = profile.history[-30:]
    profile.run = None
    profile.last_played = now_stamp()
    return result
