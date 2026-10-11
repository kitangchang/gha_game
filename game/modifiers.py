"""Data-driven modifiers.

A modifier is a dict like
    {"stat": "speed", "op": "mult", "value": 1.2, "when": {"skill": "comms"}, "target": "self"}

Sources: analyst traits (target "self" or "team"), tools (relics), the week's
special modifiers, and temporary modifiers from events and supplies.
"""
from __future__ import annotations

STATS = {
    "speed",            # task speed multiplier
    "work",             # task work multiplier (lower = less work)
    "error",            # error chance multiplier
    "skill",            # additive skill level bonus (use op "add")
    "fatigue_gain",     # short-term fatigue gain on shift
    "fatigue_recovery", # short-term fatigue recovery off shift
    "ltf_gain",         # long-term fatigue gain per shift
    "sick_chance",      # chance of calling in sick
    "xp",               # XP gain
    "rating_loss",      # public trust losses
    "rating_gain",      # public trust gains
    "payout",           # weekly funding
    "shop_price",       # shop prices
}

WHEN_KEYS = {
    "shift", "skill", "kind", "task_type", "min_complexity", "max_complexity",
    "min_mag", "max_mag", "region", "working", "base_skill_max",
}

TARGETS = {"self", "team"}


class Ctx:
    """Everything a modifier condition might look at."""
    __slots__ = ("gha", "task", "event", "shift", "working", "team")

    def __init__(self, gha=None, task=None, event=None, shift=None, working=None, team=()):
        self.gha = gha
        self.task = task
        self.event = event
        self.shift = shift
        self.working = working
        self.team = team


def _in(value, wanted) -> bool:
    if isinstance(wanted, (list, tuple, set)):
        return value in wanted
    return value == wanted


def matches(when: dict | None, ctx: Ctx) -> bool:
    if not when:
        return True
    task = ctx.task
    for key, wanted in when.items():
        if key == "shift":
            if ctx.shift is None or not _in(ctx.shift, wanted):
                return False
        elif key == "working":
            if bool(ctx.working) != bool(wanted):
                return False
        elif key in ("skill", "kind", "task_type", "min_complexity", "max_complexity", "base_skill_max"):
            if task is None:
                return False
            if key == "skill" and not _in(task.skill, wanted):
                return False
            if key == "kind" and not _in(task.kind, wanted):
                return False
            if key == "task_type" and not _in(task.type, wanted):
                return False
            if key == "min_complexity" and task.complexity < wanted:
                return False
            if key == "max_complexity" and task.complexity > wanted:
                return False
            if key == "base_skill_max":
                if ctx.gha is None or ctx.gha.base_skill(task.skill) > wanted:
                    return False
        elif key in ("min_mag", "max_mag", "region"):
            ev = ctx.event
            if ev is None:
                return False
            if key == "min_mag" and ev.mag < wanted:
                return False
            if key == "max_mag" and ev.mag > wanted:
                return False
            if key == "region" and not _in(ev.region, wanted):
                return False
        else:
            return False
    return True


class ModifierSet:
    """Collects modifiers from every source and answers stat queries."""

    def __init__(self, data):
        self.data = data
        self.global_mods: list[dict] = []
        self.temp: list[tuple[float, dict]] = []   # (expires_at, modifier)
        self.now = 0.0

    def rebuild(self, relic_ids, special_week_id=None):
        mods = []
        for rid in relic_ids:
            mods.extend(self.data.relics[rid].get("modifiers", []))
        if special_week_id:
            mods.extend(self.data.special_weeks[special_week_id].get("modifiers", []))
        self.global_mods = mods

    def add_temp(self, modifier: dict, expires_at: float):
        self.temp.append((expires_at, modifier))

    def prune(self, now: float):
        self.now = now
        if self.temp:
            self.temp = [(t, m) for (t, m) in self.temp if t > now]

    def _iter(self, ctx: Ctx):
        yield from self.global_mods
        for _, m in self.temp:
            yield m
        gha = ctx.gha
        if gha is not None:
            traits = self.data.traits
            for tid in gha.traits:
                for m in traits[tid].get("modifiers", ()):
                    if m.get("target", "self") == "self":
                        yield m
            for mate in ctx.team:
                if mate is gha:
                    continue
                for tid in mate.traits:
                    for m in traits[tid].get("modifiers", ()):
                        if m.get("target") == "team":
                            yield m

    def mult(self, stat: str, ctx: Ctx | None = None) -> float:
        ctx = ctx or Ctx()
        value = 1.0
        for m in self._iter(ctx):
            if m["stat"] == stat and m.get("op", "mult") == "mult" and matches(m.get("when"), ctx):
                value *= m["value"]
        return value

    def add(self, stat: str, ctx: Ctx | None = None) -> float:
        ctx = ctx or Ctx()
        value = 0.0
        for m in self._iter(ctx):
            if m["stat"] == stat and m.get("op") == "add" and matches(m.get("when"), ctx):
                value += m["value"]
        return value


def collect_specials(data, relic_ids) -> dict:
    """Merge the 'specials' blocks of owned tools. Numbers add up, lists merge,
    anything else: last one wins."""
    out: dict = {}
    for rid in relic_ids:
        for key, val in data.relics[rid].get("specials", {}).items():
            if isinstance(val, bool):
                out[key] = out.get(key, False) or val
            elif isinstance(val, (int, float)):
                out[key] = out.get(key, 0) + val
            elif key == "random_task":
                out.setdefault("random_tasks", []).append(val)
            else:
                out[key] = val
    return out
