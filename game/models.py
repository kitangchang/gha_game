"""Plain data classes for the game state. Everything here pickles cleanly so a
run can be saved between weeks."""
from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class GHA:
    id: int
    name: str
    color: tuple
    skills: dict
    traits: list
    salary: float
    fatigue: float = 10.0
    ltf: float = 10.0
    xp: dict = field(default_factory=dict)
    hired_week: int = 0
    active: bool = True
    left_reason: str = ""
    temp: bool = False
    stats: dict = field(default_factory=lambda: {"tasks": 0, "errors": 0, "shifts": 0, "minutes": 0.0})
    gender: str = ""            # "f", "m" or "" (any): picks names and gendered avatar pieces
    avatar: dict = field(default_factory=dict)   # layer -> {"file": png name, "tint": [r, g, b] | None} | None
    # Runtime state, managed by the engine during a week.
    queue: list = field(default_factory=list)
    on_shift: bool = False
    seat: int = -1
    arrive_at: float = 0.0
    away_until: float = 0.0
    away_reason: str = ""
    shift_work_minutes: float = 0.0
    shift_minutes: float = 0.0
    double_shift: bool = False
    ltf_warned: bool = False

    @property
    def first_name(self) -> str:
        return self.name.split(" ")[0]

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.replace("'", "").split(" ") if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.name[:2].upper()

    def base_skill(self, key: str) -> float:
        if key == "any":
            vals = list(self.skills.values())
            return sum(vals) / len(vals) if vals else 3.0
        return self.skills.get(key, 1)

    def reset_runtime(self):
        self.queue = []
        self.on_shift = False
        self.seat = -1
        self.arrive_at = 0.0
        self.away_until = 0.0
        self.away_reason = ""
        self.shift_work_minutes = 0.0
        self.shift_minutes = 0.0
        self.double_shift = False


@dataclass
class EqEvent:
    uid: int
    event_id: str
    t: float               # absolute game minute of the origin
    mag: float
    lat: float
    lon: float
    depth: float
    region: str
    description: str
    origin_time: str       # original catalogue timestamp, for the tooltip
    noise_initial: float
    noise_prelim: float
    stage: int = 0         # 0 = automatic only, 1 = prelim done, 2 = confirmed/reviewed
    two_stage: bool = False
    sops: list = field(default_factory=list)
    task_ids: dict = field(default_factory=dict)   # task type -> task id
    meta: dict = field(default_factory=dict)

    def display_mag(self) -> float:
        if self.stage >= 2:
            return self.mag
        if self.stage == 1:
            return max(0.0, self.mag + self.noise_prelim)
        return max(0.0, self.mag + self.noise_initial)

    def mag_label(self) -> str:
        prefix = "~" if self.stage == 0 else ""
        return f"{prefix}M{self.display_mag():.1f}"


@dataclass
class Task:
    id: int
    kind: str              # eq | sop | bau | staffing
    type: str              # review | prelim | confirm | sop task type | bau id | find_cover
    name: str
    skill: str
    work: float
    complexity: int
    importance: float
    deadline: float        # minutes after it becomes available
    created: float
    available: float | None = None   # None while locked
    requires: list = field(default_factory=list)   # task ids still blocking this one
    hidden: bool = False   # hidden tasks are not shown until unlocked
    event_uid: int | None = None
    sop_tags: list = field(default_factory=list)
    subtitle: str = ""
    desc: str = ""
    progress: float = 0.0
    assignee: int | None = None
    done: bool = False
    done_at: float | None = None
    done_by: int | None = None
    error: bool = False
    overdue: bool = False
    overdue_penalty: float = 0.0
    failed: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def locked(self) -> bool:
        return self.available is None

    def due_at(self) -> float | None:
        return None if self.available is None else self.available + self.deadline


@dataclass
class DayPlan:
    index: int                  # day index within the run
    source: str                 # catalogue date label
    events: list                # tuples: (offset_min, mag, lat, lon, depth, desc, event_id, origin_time)
    bau: list                   # tuples: (offset_min, bau_id)
    score: float
    percentile: float
    target: float
    boss: bool = False          # the week's boss day (every Sunday); survive the week for a reward
    final: bool = False         # the run's final boss day
    random_event_at: float | None = None   # offset minutes into the day, if a '?' day
    max_mag: float = 0.0
    sop_count: int = 0


@dataclass
class WeekPlan:
    index: int
    days: list
    special: str | None = None


@dataclass
class Roster:
    teams: dict                 # team key -> list of gha ids
    leave: list
    grid: dict                  # team key -> list[bool] per slot of the week
    return_team: dict = field(default_factory=dict)   # gha id -> team to rejoin after leave
    custom: bool = False        # grid edited by hand this week (resets to the rotation next week)

    def group_of(self, gid: int) -> str:
        if gid in self.leave:
            return "leave"
        for team, members in self.teams.items():
            if gid in members:
                return team
        return "bench"

    def remove(self, gid: int):
        if gid in self.leave:
            self.leave.remove(gid)
        for members in self.teams.values():
            if gid in members:
                members.remove(gid)

    def move(self, gid: int, group: str, index: int | None = None):
        previous = self.group_of(gid)
        self.remove(gid)
        if group == "leave":
            if previous in self.teams:
                self.return_team[gid] = previous
            target = self.leave
        elif group == "bench":
            return
        else:
            target = self.teams.setdefault(group, [])
        if index is None or index >= len(target):
            target.append(gid)
        else:
            target.insert(max(0, index), gid)

    def lineup(self, slot: int) -> list:
        ids: list = []
        for team, cells in self.grid.items():
            if 0 <= slot < len(cells) and cells[slot]:
                for gid in self.teams.get(team, []):
                    if gid not in ids:
                        ids.append(gid)
        return ids


@dataclass
class RunState:
    seed: int
    length_key: str
    weeks_total: int
    plan: list                  # list[WeekPlan]
    ghas: list                  # list[GHA]
    roster: Roster
    rng: random.Random
    catalog_label: str
    week: int = 0
    rating: float = 70.0
    budget: float = 10.0
    relics: list = field(default_factory=list)
    consumables: list = field(default_factory=list)
    next_ids: dict = field(default_factory=lambda: {"task": 1, "gha": 1, "event": 1})
    carry_tasks: list = field(default_factory=list)
    carry_events: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    flags: dict = field(default_factory=dict)
    shop: dict | None = None
    away_week: list = field(default_factory=list)
    used_events: list = field(default_factory=list)
    last_slot_lineup: list = field(default_factory=list)
    phase: str = "planning"     # planning | shift | summary | over | won
    unlock_level: int = 99      # centre level when the run started: items above it stay locked
    totals: dict = field(default_factory=lambda: {"tasks": 0, "eq": 0, "errors": 0, "ontime": 0, "sops": 0})

    def gha(self, gid: int) -> GHA | None:
        for g in self.ghas:
            if g.id == gid:
                return g
        return None

    def active_ghas(self) -> list:
        return [g for g in self.ghas if g.active and not g.temp]

    def new_id(self, kind: str) -> int:
        value = self.next_ids[kind]
        self.next_ids[kind] = value + 1
        return value
