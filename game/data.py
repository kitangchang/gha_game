"""Loads and validates everything in data/*.json."""
from __future__ import annotations

import json
from pathlib import Path

from .modifiers import STATS, TARGETS, WHEN_KEYS

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

EFFECT_TYPES = {
    "rating", "budget", "fatigue", "ltf", "away", "spawn_task", "modifier", "relic",
    "consumable", "chance", "flag", "fatigue_floor", "complete_task", "extend_deadline", "temp_gha",
}
SCHEDULE_TYPES = {"every_shift", "daily", "times", "random", "none"}
TRAIT_KINDS = ("good", "balanced", "bad")


class DataError(Exception):
    pass


def _load(name: str):
    path = DATA_DIR / name
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise DataError(f"Missing data file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"{name}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def _entries(items: list) -> list:
    """Drop documentation-only entries ({"_doc": ...})."""
    return [it for it in items if isinstance(it, dict) and "id" in it]


def _by_id(name: str) -> dict:
    """{id: entry} for a data file. Two entries with the same id would silently
    hide one of them, so that's an error."""
    out: dict = {}
    dupes = []
    for it in _entries(_load(name)):
        if it["id"] in out:
            dupes.append(it["id"])
        out[it["id"]] = it
    if dupes:
        raise DataError(f"{name}: the same id is used more than once: {', '.join(sorted(set(dupes)))}. "
                        "Delete or rename the old entry.")
    return out


class GameData:
    def __init__(self):
        self.config = _load("config.json")
        self.skills = _load("skills.json")
        for sk in self.skills:
            sk["color"] = tuple(sk.get("color", (160, 170, 190)))
        self.skill_keys = [s["key"] for s in self.skills]
        self.skill_by_key = {s["key"]: s for s in self.skills}
        self.traits = _by_id("traits.json")
        for t in self.traits.values():
            # "kind" is good | balanced | bad; older files used "good": true/false.
            t["kind"] = t.get("kind") or ("good" if t.get("good", True) else "bad")
            t["good"] = t["kind"] != "bad"
        self.relics = _by_id("relics.json")
        self.tags = _by_id("tags.json")
        for t in self.tags.values():
            t["color"] = tuple(t.get("color", (180, 180, 190)))
        self.consumables = _by_id("consumables.json")
        self.training = _by_id("training.json")
        self.bau = _by_id("bau_tasks.json")
        sops = _load("sops.json")
        self.regions = sops["regions"]
        self.sop_task_types = sops["task_types"]
        self.sops = sops["sops"]
        for sop in self.sops:
            sop["color"] = tuple(sop.get("color", (176, 140, 245)))
        self.sop_by_id = {s["id"]: s for s in self.sops}
        self.events = {e["id"]: e for e in _entries(_load("events.json"))}
        self.special_weeks = {w["id"]: w for w in _entries(_load("special_weeks.json"))}
        names = _load("names.json")
        neutral = names.get("neutral", [])
        self.names_by_gender = {"f": names.get("female", []) + neutral, "m": names.get("male", []) + neutral}
        self.first_names = names.get("first") or sorted(set(self.names_by_gender["f"] + self.names_by_gender["m"]))
        self.last_names = names["last"]
        self.avatar_colors = [tuple(c) for c in names["colors"]]
        places = _load("places.json")
        self.places_nz = places["nz"]
        self.places_regions = places["regions"]
        self.places_global = places["global"]
        self.coast = _load("nz_coast.json")
        dart = _load("dart.json")
        self.dart_cfg = dart["trigger"]
        self.dart_buoys = [b for b in dart["buoys"] if isinstance(b, dict) and "code" in b]
        self.shifts = [sh for sh in self.config["shifts"] if isinstance(sh, dict) and "key" in sh]
        for sh in self.shifts:
            sh["color"] = tuple(sh.get("color", (200, 200, 210)))
        roster = self.config["roster"]
        self.teams = [t for t in roster["teams"] if isinstance(t, dict) and "key" in t]
        for t in self.teams:
            t["color"] = tuple(t.get("color", (160, 160, 170)))
        self.team_keys = [t["key"] for t in self.teams]
        self.team_by_key = {t["key"]: t for t in self.teams}
        self.rotation_cycle = list(roster["rotation_cycle"])
        self.team_start_days = list(roster["team_start_days"])
        self.bench_color = tuple(roster.get("bench_color", (150, 156, 168)))
        self.leave_color = tuple(roster.get("leave_color", (120, 200, 150)))
        self.validate()

    # ------------------------------------------------------------------ helpers
    def shift_index(self, key: str) -> int:
        for i, s in enumerate(self.shifts):
            if s["key"] == key:
                return i
        raise KeyError(key)

    @property
    def slots_per_day(self) -> int:
        return len(self.shifts)

    @property
    def slots_per_week(self) -> int:
        return 7 * len(self.shifts)

    def team_name(self, key: str) -> str:
        t = self.team_by_key.get(key)
        return t["name"] if t else key.title()

    def first_names_for(self, gender: str = "") -> list:
        return self.names_by_gender.get(gender) or self.first_names

    def team_color(self, key: str) -> tuple:
        if key == "bench":
            return self.bench_color
        if key == "leave":
            return self.leave_color
        t = self.team_by_key.get(key)
        return t["color"] if t else self.bench_color

    def rotation_shift(self, team_index: int, abs_day: int) -> str:
        """Shift key (or 'off') that team n works on absolute day d of the run."""
        start = self.team_start_days[team_index % len(self.team_start_days)]
        return self.rotation_cycle[(abs_day - start) % len(self.rotation_cycle)]

    def skill_name(self, key: str) -> str:
        if key == "any":
            return "Any"
        return self.skill_by_key[key]["name"]

    def skill_abbr(self, key: str) -> str:
        if key == "any":
            return "ANY"
        return self.skill_by_key[key]["abbr"]

    # --------------------------------------------------------------- validation
    def validate(self):
        errors: list[str] = []
        shift_keys = {sh["key"] for sh in self.shifts}

        def check_mod(where: str, m: dict, allow_target=False):
            if m.get("stat") not in STATS:
                errors.append(f"{where}: unknown stat '{m.get('stat')}'")
            if m.get("op", "mult") not in ("mult", "add"):
                errors.append(f"{where}: op must be 'mult' or 'add'")
            for key in (m.get("when") or {}):
                if key not in WHEN_KEYS:
                    errors.append(f"{where}: unknown condition '{key}'")
            sk = (m.get("when") or {}).get("skill")
            for s in (sk if isinstance(sk, list) else [sk] if sk else []):
                if s not in self.skill_keys and s != "any":
                    errors.append(f"{where}: unknown skill '{s}'")
            sh = (m.get("when") or {}).get("shift")
            for s in (sh if isinstance(sh, list) else [sh] if sh else []):
                if s not in shift_keys:
                    errors.append(f"{where}: unknown shift '{s}' (use one of {sorted(shift_keys)})")
            if "per_tag" in m and m["per_tag"] != "any" and m["per_tag"] not in self.tags:
                errors.append(f"{where}: per_tag '{m['per_tag']}' is not a tag in tags.json")
            if "target" in m and (not allow_target or m["target"] not in TARGETS):
                errors.append(f"{where}: bad target '{m['target']}'")

        def check_skill(where: str, skill: str):
            if skill != "any" and skill not in self.skill_keys:
                errors.append(f"{where}: unknown skill '{skill}'")

        def check_effects(where: str, effects: list):
            for e in effects:
                t = e.get("type")
                if t not in EFFECT_TYPES:
                    errors.append(f"{where}: unknown effect type '{t}'")
                    continue
                if t == "spawn_task" and e.get("task") not in self.bau:
                    errors.append(f"{where}: spawn_task refers to unknown task '{e.get('task')}'")
                if t == "relic" and e.get("id") and e["id"] not in self.relics:
                    errors.append(f"{where}: unknown tool '{e['id']}'")
                if t == "relic" and e.get("tag") and e["tag"] not in self.tags:
                    errors.append(f"{where}: unknown tag '{e['tag']}' (add it to tags.json)")
                if t == "consumable" and e.get("id") and e["id"] not in self.consumables:
                    errors.append(f"{where}: unknown consumable '{e['id']}'")
                if t == "modifier":
                    check_mod(where, e.get("modifier", {}))
                if t == "chance":
                    check_effects(where, e.get("success", []))
                    check_effects(where, e.get("failure", []))
                if t == "away" and e.get("skill"):
                    check_skill(where, e["skill"])

        for t in self.traits.values():
            if t["kind"] not in TRAIT_KINDS:
                errors.append(f"traits.json/{t['id']}: kind must be one of {list(TRAIT_KINDS)}")
            for m in t.get("modifiers", []):
                check_mod(f"traits.json/{t['id']}", m, allow_target=True)
        for where, items in (("traits.json", self.traits), ("relics.json", self.relics),
                             ("consumables.json", self.consumables), ("training.json", self.training)):
            for item in items.values():
                for tag in item.get("tags", []):
                    if tag not in self.tags:
                        errors.append(f"{where}/{item['id']}: unknown tag '{tag}' (add it to tags.json)")
        costs = self.config["economy"]["relic_costs"]
        for r in self.relics.values():
            if r.get("rarity") not in costs:
                errors.append(f"relics.json/{r['id']}: rarity must be one of {sorted(costs)}")
            for m in r.get("modifiers", []):
                check_mod(f"relics.json/{r['id']}", m)
            rt = r.get("specials", {}).get("random_task")
            if rt and rt.get("task") not in self.bau:
                errors.append(f"relics.json/{r['id']}: random_task refers to unknown task")
        for w in self.special_weeks.values():
            for m in w.get("modifiers", []):
                check_mod(f"special_weeks.json/{w['id']}", m)
            sd = w.get("spawn_daily")
            if sd and sd.get("task") not in self.bau:
                errors.append(f"special_weeks.json/{w['id']}: spawn_daily refers to unknown task")
        for b in self.bau.values():
            check_skill(f"bau_tasks.json/{b['id']}", b["skill"])
            sched = b.get("schedule", {})
            if sched.get("type") not in SCHEDULE_TYPES:
                errors.append(f"bau_tasks.json/{b['id']}: schedule.type must be one of {sorted(SCHEDULE_TYPES)}")
            times = sched.get("at", []) if sched.get("type") == "times" else (
                [sched.get("at", "")] if sched.get("type") == "daily" else [])
            if sched.get("type") == "times" and not isinstance(times, list):
                errors.append(f"bau_tasks.json/{b['id']}: schedule.at must be a list of 'HH:MM' times")
                times = []
            for day in sched.get("days", []):
                if not (isinstance(day, str) and day[:3].title() in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
                    errors.append(f"bau_tasks.json/{b['id']}: bad day '{day}' in schedule.days (use Mon, Tue, ...)")
            for at in times:
                if not (isinstance(at, str) and len(at.split(":")) == 2 and all(p.isdigit() for p in at.split(":"))):
                    errors.append(f"bau_tasks.json/{b['id']}: bad time '{at}' (use 'HH:MM')")
        for key, tt in self.sop_task_types.items():
            check_skill(f"sops.json/task_types/{key}", tt["skill"])
        if self.dart_cfg.get("sop") not in self.sop_by_id:
            errors.append(f"dart.json: trigger.sop '{self.dart_cfg.get('sop')}' is not an SOP in sops.json")
        if self.dart_cfg.get("assess_task") not in self.sop_task_types:
            errors.append(f"dart.json: trigger.assess_task '{self.dart_cfg.get('assess_task')}' is not a task type")
        for b in self.dart_buoys:
            if not (-90 <= b.get("lat", 999) <= 90 and 0 <= b.get("lon", -1) <= 360):
                errors.append(f"dart.json: buoy {b['code']} needs lat (-90..90) and lon (0..360)")
        for sop in self.sops:
            types = {t["type"] for t in sop["tasks"]}
            for t in sop["tasks"]:
                if t["type"] not in self.sop_task_types:
                    errors.append(f"sops.json/{sop['id']}: unknown task type '{t['type']}'")
                for req in t.get("requires", []):
                    if req not in ("prelim", "confirm") and req not in types:
                        errors.append(f"sops.json/{sop['id']}: '{t['type']}' requires unknown '{req}'")
            for trig in sop["triggers"]:
                if trig["region"] not in self.regions and trig["region"] != "elsewhere":
                    errors.append(f"sops.json/{sop['id']}: unknown region '{trig['region']}'")
        for ev in self.events.values():
            if not ev.get("options"):
                errors.append(f"events.json/{ev['id']}: needs at least one option")
            for i, opt in enumerate(ev.get("options", [])):
                check_effects(f"events.json/{ev['id']}/option {i + 1}", opt.get("effects", []))
        for c in self.consumables.values():
            if c.get("target", "none") not in ("none", "gha", "task"):
                errors.append(f"consumables.json/{c['id']}: target must be none, gha or task")
            check_effects(f"consumables.json/{c['id']}", c.get("effects", []))
        for r in self.relics.values():
            for e in r.get("on_gain", []):
                if e.get("type") not in ("budget", "rating"):
                    errors.append(f"relics.json/{r['id']}: on_gain only supports budget and rating effects")
        for b in self.bau.values():
            if "reward" in b:
                if not isinstance(b["reward"], list):
                    errors.append(f"bau_tasks.json/{b['id']}: reward must be a list of effects")
                else:
                    check_effects(f"bau_tasks.json/{b['id']}/reward", b["reward"])
        for t in self.training.values():
            if t["effect"] == "skill":
                check_skill(f"training.json/{t['id']}", t.get("skill", ""))
            elif t["effect"] == "add_trait" and t.get("trait") not in self.traits:
                errors.append(f"training.json/{t['id']}: unknown trait '{t.get('trait')}'")
            elif t["effect"] not in ("ltf", "remove_bad_trait", "add_trait", "skill"):
                errors.append(f"training.json/{t['id']}: unknown effect '{t['effect']}'")
        for entry in self.rotation_cycle:
            if entry != "off" and entry not in shift_keys:
                errors.append(f"config.json/roster: rotation_cycle entry '{entry}' is not a shift key or 'off'")
        if len(self.team_start_days) < len(self.teams):
            errors.append("config.json/roster: team_start_days needs one entry per team")
        total = sum(sh["hours"] for sh in self.shifts)
        if total != 24:
            errors.append(f"config.json/shifts: shift hours add up to {total}, not 24")
        if errors:
            raise DataError("Problems in the data files:\n  - " + "\n  - ".join(errors))


_DATA: GameData | None = None


def get_data() -> GameData:
    global _DATA
    if _DATA is None:
        _DATA = GameData()
    return _DATA
