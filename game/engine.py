"""WeekEngine: simulates one week of the monitoring centre.

Time is in absolute game minutes since the start of the run (minute 0 = week
1, day 1 at the configured day start hour). The UI calls update(dt) with game
minutes; the engine stops early whenever a decision is needed (self.modal).
"""
from __future__ import annotations

import heapq

from . import effects as fx
from .avatars import random_avatar
from .dart import buoy as dart_buoy
from .dart import triggered_buoys
from .geo import region_of, short_place
from .models import GHA, EqEvent, Task
from .modifiers import Ctx, ModifierSet, collect_specials
from .tasks import (build_bau_task, build_event_tasks, build_sop_checklist, build_sop_task, build_staffing_task,
                    sop_threshold)
from .util import DAY_NAMES, clamp, fmt_clock

# Timeline priorities for items at the same minute (lower runs first).
TL_SLOT, TL_END, TL_EQ, TL_BAU, TL_SICK, TL_RANDOM, TL_DART, TL_UNLOCK = range(8)

# Auto-assign modes: key -> (label, one-line description)
AUTO_MODES = {
    "balanced": ("Balanced", "Weighs finish time against the chance of an error on important tasks."),
    "fastest": ("Fastest finish", "Whoever would finish it soonest, counting what's already in their queue."),
    "safest": ("Lowest error", "Whoever is least likely to make a mistake on it."),
    "freshest": ("Least fatigued", "Whoever is least tired."),
    "shortest": ("Shortest queue", "Whoever has the fewest tasks queued."),
}


class WeekEngine:
    MAX_STEP = 1.0

    def __init__(self, data, run):
        self.data = data
        self.run = run
        self.cfg = data.config
        self.rng = run.rng
        self.plan = run.plan[run.week]
        self.special = data.special_weeks.get(self.plan.special) if self.plan.special else None
        self.t0 = run.week * 7 * 1440.0
        self.now = self.t0
        self.t_end = self.t0 + 7 * 1440.0
        self.shifts = data.shifts
        self.n_shifts = len(self.shifts)
        self.mods = ModifierSet(data)
        self.specials: dict = {}
        self.desks = self.cfg["run"]["desks"]
        self.seats: list = []
        self.refresh_mods()

        self.tasks: dict[int, Task] = {}
        self.open_ids: set = set()
        self.inbox: list = []
        self.dependents: dict = {}
        self.events: dict[int, EqEvent] = {}
        self.ghas: dict[int, GHA] = {g.id: g for g in run.ghas if g.active}
        self.temp_ids: set = set()
        self.slot = -1
        self.timeline: list = []
        self._seq = 0
        self.notes: list = []
        self.log: list = []
        self.modal: dict | None = None
        self.week_done = False
        self.game_over = False
        self.unmanned = False
        self.overrides: dict = {}
        self.leave_cancelled: set = set()
        self.shields = 0
        self.overtime_cost = 0.0
        self.recent_done: list = []
        self.dart_until: dict = {}        # buoy code -> game minute its event mode ends
        self.dart_last: dict = {}         # buoy code -> (minute triggered, event uid)
        self._auto_dirty = True
        self._auto_next = 0.0
        self.stats = {
            "rating_start": run.rating, "tasks_done": 0, "ontime": 0, "late": 0, "errors": 0, "caught": 0,
            "eq_done": 0, "events": 0, "sop_events": 0, "imp_due": 0.0, "imp_ontime": 0.0, "overdue": 0,
            "unmanned_shifts": 0, "sick_calls": 0, "covers": 0, "call_ins": 0, "lost_errors": 0.0,
            "lost_overdue": 0.0, "lost_other": 0.0, "gained": 0.0, "biggest": None, "level_ups": [],
            "burnouts": [], "auto_reviewed": 0, "dart_triggers": 0,
        }
        for g in run.ghas:
            g.reset_runtime()
        self._schedule_week()
        self._restore_carry()
        self._start_slot(0)

    # ------------------------------------------------------------------ setup
    def refresh_mods(self):
        self.mods.rebuild(self.run.relics, self.plan.special)
        growth = self.cfg["difficulty"].get("expectation_growth_per_week", 0.0) * self.run.week
        if growth:
            # Public expectations rise as the season goes on: every trust loss counts for more.
            self.mods.global_mods = self.mods.global_mods + [
                {"stat": "rating_loss", "op": "mult", "value": 1.0 + growth}]
        self.specials = collect_specials(self.data, self.run.relics)
        desks = min(self.cfg["run"]["max_desks"], self.cfg["run"]["desks"] + int(self.specials.get("extra_desks", 0)))
        while len(self.seats) < desks:
            self.seats.append(None)
        self.desks = len(self.seats)

    def _push(self, t: float, kind: int, payload=None):
        self._seq += 1
        heapq.heappush(self.timeline, (t, kind, self._seq, payload))

    def _schedule_week(self):
        for d, day in enumerate(self.plan.days):
            base = self.t0 + d * 1440.0
            for ev in day.events:
                self._push(base + ev[0], TL_EQ, ev)
            for off, bau_id in day.bau:
                self._push(base + off, TL_BAU, bau_id)
            if day.random_event_at is not None:
                self._push(base + day.random_event_at, TL_RANDOM, d)
            for s in range(self.n_shifts):
                slot = d * self.n_shifts + s
                if slot:
                    self._push(self.slot_start(slot), TL_SLOT, slot)
        self._push(self.t_end, TL_END, None)

    def _restore_carry(self):
        for ev in self.run.carry_events.values():
            self.events[ev.uid] = ev
        for t in self.run.carry_tasks:
            t.assignee = None
            self.tasks[t.id] = t
            self.open_ids.add(t.id)
            if not t.hidden:
                self.inbox.append(t.id)
        for t in self.run.carry_tasks:
            for req in t.requires:
                self.dependents.setdefault(req, []).append(t.id)
            if t.available is None and not t.requires and "available_at" in t.meta:
                self._push(max(self.t0, t.meta["available_at"]), TL_UNLOCK, t.id)
        self.run.carry_tasks = []
        self.run.carry_events = {}

    # ------------------------------------------------------------- time helpers
    def slot_start(self, slot: int) -> float:
        day, s = divmod(slot, self.n_shifts)
        return self.t0 + day * 1440.0 + self.shifts[s]["start_offset_hours"] * 60.0

    def slot_end(self, slot: int) -> float:
        return self.slot_start(slot) + self.shifts[slot % self.n_shifts]["hours"] * 60.0

    def slot_label(self, slot: int) -> str:
        day, s = divmod(slot, self.n_shifts)
        return f"{DAY_NAMES[day % 7]} {self.shifts[s]['name'].lower()} shift"

    @property
    def shift(self) -> dict:
        return self.shifts[max(0, self.slot) % self.n_shifts]

    @property
    def day_index(self) -> int:
        return int(min(6, (self.now - self.t0) // 1440))

    def clock(self) -> str:
        return fmt_clock(self.now, self.cfg["time"]["day_start_hour"])

    def shift_progress(self) -> float:
        start, end = self.slot_start(self.slot), self.slot_end(self.slot)
        return clamp((self.now - start) / max(1.0, end - start), 0.0, 1.0)

    @property
    def blocked(self) -> bool:
        return self.modal is not None or self.week_done or self.game_over

    @property
    def on_shift(self) -> list:
        return [gid for gid in self.seats if gid is not None]

    def present(self, g: GHA) -> bool:
        return g.on_shift and self.now >= g.arrive_at and self.now >= g.away_until

    def present_ghas(self) -> list:
        return [self.ghas[gid] for gid in self.on_shift if self.present(self.ghas[gid])]

    # ------------------------------------------------------------- notifications
    def note(self, _type: str, **kw):
        kw["type"] = _type
        kw["t"] = self.now
        self.notes.append(kw)

    def add_log(self, text: str, tone: str = "info"):
        self.log.append((self.now, text, tone))
        if len(self.log) > 250:
            del self.log[:50]

    def drain_notes(self) -> list:
        out, self.notes = self.notes, []
        return out

    # ---------------------------------------------------------------- main loop
    def update(self, dt: float) -> float:
        remaining = dt
        while remaining > 1e-9 and not self.blocked:
            next_t = self.timeline[0][0] if self.timeline else self.t_end
            step = min(remaining, max(0.0, next_t - self.now), self.MAX_STEP)
            if step > 0:
                self._advance(step)
                remaining -= step
            while self.timeline and self.timeline[0][0] <= self.now + 1e-9 and not self.blocked:
                self._handle(heapq.heappop(self.timeline))
            if not self.blocked:
                self._maybe_auto_assign()
        return dt - remaining

    def _handle(self, item):
        t, kind, _, payload = item
        if t > self.now:
            self.now = t
        if kind == TL_SLOT:
            self._start_slot(payload)
        elif kind == TL_EQ:
            self._spawn_event(payload)
        elif kind == TL_BAU:
            self.spawn_bau(payload)
        elif kind == TL_SICK:
            self._sick_call(*payload)
        elif kind == TL_RANDOM:
            self._random_event()
        elif kind == TL_DART:
            self._dart_trigger(*payload)
        elif kind == TL_UNLOCK:
            t = self.tasks.get(payload)
            if t is not None and not t.done and t.available is None and not t.requires:
                self._unlock(t)
        elif kind == TL_END:
            self._end_week()

    def _advance(self, dt: float):
        self.now += dt
        self.mods.prune(self.now)
        fat = self.cfg["fatigue"]
        shift = self.shift
        skey = shift["key"]
        team = [self.ghas[gid] for gid in self.on_shift]
        for g in team:
            working = False
            if self.present(g):
                task = self.current_task(g)
                if task is not None:
                    working = True
                    ctx = self.ctx(g, task, working=True, team=team)
                    task.progress += dt * self._speed(g, task, ctx)
                    g.shift_work_minutes += dt
                    g.stats["minutes"] += dt
                    if task.progress >= task.work - 1e-9:
                        self._complete(task, g, ctx)
            elif self.now < g.away_until:
                working = True
            g.shift_minutes += dt
            rate = fat["gain_working_per_hour"] if working else fat["gain_idle_per_hour"]
            gain = rate * shift["fatigue_mult"] * self.mods.mult(
                "fatigue_gain", Ctx(gha=g, shift=skey, working=working, team=team)) * dt / 60.0
            g.fatigue = min(100.0, g.fatigue + gain)
        for g in self.ghas.values():
            if g.on_shift or not g.active:
                continue
            floor = g.ltf * fat["floor_from_ltf"]
            if g.fatigue > floor:
                rec = fat["recovery_per_hour"] * self.mods.mult("fatigue_recovery", Ctx(gha=g)) * dt / 60.0
                g.fatigue = max(floor, g.fatigue - rec)
        self._check_overdue(dt)
        if self.unmanned:
            self.change_rating(-self.cfg["rating"]["unmanned_drain_per_hour"] * dt / 60.0, "other")
        if self.specials.get("auto_review"):
            self._auto_review()

    # ------------------------------------------------------------ task helpers
    def ctx(self, g: GHA | None, task: Task | None, working=True, team=None) -> Ctx:
        if team is None:
            team = [self.ghas[gid] for gid in self.on_shift]
        ev = self.events.get(task.event_uid) if task is not None and task.event_uid is not None else None
        return Ctx(gha=g, task=task, event=ev, shift=self.shift["key"], working=working, team=team)

    def current_task(self, g: GHA) -> Task | None:
        for tid in g.queue:
            t = self.tasks.get(tid)
            if t is not None and not t.done and t.available is not None:
                return t
        return None

    def skill_level(self, g: GHA, task: Task, ctx: Ctx) -> float:
        return clamp(g.base_skill(task.skill) + self.mods.add("skill", ctx), 0.5, 7.0)

    def _speed(self, g: GHA, task: Task, ctx: Ctx) -> float:
        sm = self.cfg["skill_model"]
        lvl = self.skill_level(g, task, ctx)
        cw = sm["cw_base"] + sm["cw_per"] * task.complexity
        s = max(sm["min_speed"], 1.0 + sm["speed_per_level"] * (lvl - 3.0) * cw)
        s *= 1.0 - self.cfg["fatigue"]["speed_penalty_at_max"] * g.fatigue / 100.0
        s *= self.mods.mult("speed", ctx)
        s /= max(0.05, self.mods.mult("work", ctx))
        return max(0.02, s)

    def _error_chance(self, g: GHA, task: Task, ctx: Ctx) -> float:
        sm = self.cfg["skill_model"]
        lvl = self.skill_level(g, task, ctx)
        p = sm["error_base_per_complexity"] * task.complexity * sm["error_skill_base"] ** (3.0 - lvl)
        p *= 1.0 + (self.cfg["fatigue"]["error_mult_at_max"] - 1.0) * (g.fatigue / 100.0) ** 2
        p *= self.mods.mult("error", ctx)
        return clamp(p, 0.0, sm["error_max"])

    def estimate(self, g: GHA, task: Task) -> tuple:
        """(minutes remaining, error chance) if g did this task now."""
        ctx = self.ctx(g, task)
        speed = self._speed(g, task, ctx)
        err = 0.0 if task.kind == "staffing" else self._error_chance(g, task, ctx)
        return max(0.0, task.work - task.progress) / speed, err

    def queue_eta(self, g: GHA) -> float:
        total = 0.0
        for tid in g.queue:
            t = self.tasks.get(tid)
            if t is not None and not t.done and t.available is not None:
                total += self.estimate(g, t)[0]
        return total

    def _add_task(self, task: Task):
        self.tasks[task.id] = task
        self.open_ids.add(task.id)
        for req in task.requires:
            self.dependents.setdefault(req, []).append(task.id)
        if not task.hidden:
            self.inbox.append(task.id)
        self._auto_dirty = True

    def _detach(self, t: Task):
        if t.assignee is not None:
            g = self.ghas.get(t.assignee)
            if g is not None and t.id in g.queue:
                g.queue.remove(t.id)
        t.assignee = None
        if t.id in self.inbox:
            self.inbox.remove(t.id)

    # ----------------------------------------------------------- player actions
    def assign(self, tid: int, gid: int, index: int | None = None) -> bool:
        t, g = self.tasks.get(tid), self.ghas.get(gid)
        if t is None or g is None or t.done or t.hidden or not g.on_shift:
            return False
        self._detach(t)
        if index is None or index >= len(g.queue):
            g.queue.append(tid)
        else:
            g.queue.insert(max(0, index), tid)
        t.assignee = gid
        t.meta.pop("manual_unassign", None)
        return True

    def unassign(self, tid: int) -> bool:
        t = self.tasks.get(tid)
        if t is None or t.done or t.hidden:
            return False
        self._detach(t)
        self.inbox.append(tid)
        t.meta["manual_unassign"] = True     # auto-assign leaves cards the player pulled back alone
        return True

    def call_in_options(self) -> list:
        lineup = set(self.on_shift)
        return [g for g in self.ghas.values()
                if g.active and not g.temp and g.id not in lineup and g.id not in self.run.away_week]

    def call_in(self, gid: int) -> tuple:
        g = self.ghas.get(gid)
        cost = self.cfg["run"]["call_in_cost"]
        if g is None or g.on_shift:
            return False, "They're already here."
        if None not in self.seats:
            return False, "No free desk."
        if self.run.budget < cost:
            return False, "Not enough budget."
        self.run.budget -= cost
        self.overtime_cost += cost
        self._seat(g, arrive_in=self.cfg["run"]["call_in_arrive_minutes"])
        g.ltf = min(100.0, g.ltf + self.cfg["run"]["call_in_ltf"])
        if g.id in self.run.roster.leave:
            self.leave_cancelled.add(g.id)
        self.overrides.setdefault(self.slot, {"add": [], "remove": []})["add"].append(g.id)
        self.stats["call_ins"] += 1
        self.add_log(f"{g.name} called in (overtime)", "warn")
        self.note("arrive", gha=g.id)
        return True, f"{g.first_name} is on the way in."

    def use_consumable(self, index: int, target=None) -> tuple:
        if not (0 <= index < len(self.run.consumables)):
            return False, "No such item."
        cid = self.run.consumables[index]
        c = self.data.consumables[cid]
        tgt = c.get("target", "none")
        if tgt == "gha" and not (isinstance(target, GHA) and target.on_shift):
            return False, "Pick an analyst who is on shift."
        if tgt == "task" and not (isinstance(target, Task) and not target.done and not target.hidden):
            return False, "Pick an open task."
        if any(e["type"] == "temp_gha" for e in c.get("effects", [])) and None not in self.seats:
            return False, "No free desk for them."
        self.run.consumables.pop(index)
        msgs = fx.apply_effects(self, c.get("effects", []), target)
        self.add_log(f"Used {c['name']}", "good")
        return True, "; ".join(m for m in msgs if m) or c["name"]

    # ------------------------------------------------------------- completion
    def _complete(self, task: Task, g: GHA | None, ctx: Ctx | None = None, external=False):
        task.done = True
        task.done_at = self.now
        task.done_by = g.id if g is not None else None
        self._detach(task)
        self.open_ids.discard(task.id)
        rc = self.cfg["rating"]
        due = task.due_at() if task.available is not None else self.now
        ontime = self.now <= due + 1e-9
        error = False
        if g is not None and not external and task.kind != "staffing":
            if self.rng.random() < self._error_chance(g, task, ctx or self.ctx(g, task)):
                if self.shields > 0:
                    self.shields -= 1
                    self.stats["caught"] += 1
                    self.note("float", gha=g.id, text="Caught!", tone="good")
                    self.add_log(f"Rubber duck caught {g.first_name}'s mistake on {self.task_title(task)}", "good")
                else:
                    error = True
        task.error = error
        if not task.meta.get("counted"):
            task.meta["counted"] = True
            self.stats["imp_due"] += task.importance
        self.stats["tasks_done"] += 1
        if task.kind == "eq":
            self.stats["eq_done"] += 1
        if error:
            mult = rc["prelim_error_mult"] if task.type == "prelim" else 1.0
            loss = task.importance * rc["error_penalty"] * mult
            self.change_rating(-loss, "errors", task)
            self.stats["errors"] += 1
            g.stats["errors"] += 1
            self.note("float", gha=g.id, text=f"Error -{loss:.1f}", tone="bad")
            self.add_log(f"Error: {self.task_title(task)} ({g.first_name}) -{loss:.1f} trust", "bad")
        if ontime:
            self.stats["ontime"] += 1
            self.stats["imp_ontime"] += task.importance
            if not error:
                gain = task.importance * rc["ontime_bonus"]
                self.change_rating(gain, "gain", task)
                if g is not None and gain >= 0.05:
                    self.note("float", gha=g.id, text=f"+{gain:.1f}", tone="good")
        else:
            self.stats["late"] += 1
        if g is not None:
            g.stats["tasks"] += 1
            if not external:
                self._gain_xp(g, task, ctx or self.ctx(g, task))
        if task.event_uid is not None:
            ev = self.events.get(task.event_uid)
            if ev is not None:
                if task.type == "prelim":
                    ev.stage = max(ev.stage, 1)
                elif task.type in ("confirm", "review"):
                    ev.stage = 2
        self.recent_done.append(task.id)
        if len(self.recent_done) > 400:
            del self.recent_done[:100]
        for dep_id in self.dependents.pop(task.id, []):
            dep = self.tasks.get(dep_id)
            if dep is None or dep.done:
                continue
            if task.id in dep.requires:
                dep.requires.remove(task.id)
            if not dep.requires and dep.available is None:
                self._unlock(dep, follow_to=g)
        if task.kind == "staffing" and not task.failed:
            self.modal = {"type": "staffing", "task": task.id, "slot": task.meta["slot"], "sick": task.meta["sick"]}
            self.note("modal", kind="staffing")
        self.note("done", task=task.id, gha=g.id if g else None)

    def complete_external(self, task: Task):
        if task.done:
            return
        if task.available is None:
            task.available = self.now
        task.progress = task.work
        self._complete(task, None, external=True)

    def _unlock(self, dep: Task, follow_to: GHA | None = None):
        """Make a task available. Hidden follow-ups (e.g. 'Send EAT' after the
        assessment) go straight to the front of the queue of whoever did the
        step before, because that's who would naturally send it."""
        was_hidden = dep.hidden
        dep.available = self.now
        dep.hidden = False
        if was_hidden and follow_to is not None and follow_to.on_shift and follow_to.active and dep.assignee is None:
            dep.assignee = follow_to.id
            follow_to.queue.insert(0, dep.id)
            self.note("float", gha=follow_to.id, text=f"Next: {dep.name}", tone="accent")
        elif dep.assignee is None and dep.id not in self.inbox:
            self.inbox.append(dep.id)
        self._auto_dirty = True
        self.note("unlock", task=dep.id)

    def _gain_xp(self, g: GHA, task: Task, ctx: Ctx):
        if task.skill == "any" or g.temp:
            return
        sm = self.cfg["skill_model"]
        gain = task.complexity * sm["xp_per_complexity"] * self.mods.mult("xp", ctx)
        g.xp[task.skill] = g.xp.get(task.skill, 0.0) + gain
        level = g.skills.get(task.skill, 1)
        thresholds = sm["xp_to_next"]
        while level < sm["max_level"] and g.xp[task.skill] >= thresholds[min(level - 1, len(thresholds) - 1)]:
            g.xp[task.skill] -= thresholds[min(level - 1, len(thresholds) - 1)]
            level += 1
            g.skills[task.skill] = level
            name = self.data.skill_name(task.skill)
            self.stats["level_ups"].append(f"{g.name}: {name} {level}")
            self.note("float", gha=g.id, text=f"{self.data.skill_abbr(task.skill)} up!", tone="accent")
            self.note("toast", text=f"{g.first_name} levelled up: {name} {level}", tone="accent")
            self.add_log(f"{g.name} reached {name} {level}", "accent")

    # ---------------------------------------------------------------- trust
    def change_rating(self, delta: float, reason: str = "other", task: Task | None = None):
        if delta == 0:
            return
        ctx = self.ctx(None, task) if task is not None else Ctx(shift=self.shift["key"])
        if delta < 0:
            delta *= self.mods.mult("rating_loss", ctx)
            key = {"errors": "lost_errors", "overdue": "lost_overdue"}.get(reason, "lost_other")
            self.stats[key] += -delta
        else:
            delta *= self.mods.mult("rating_gain", ctx)
            self.stats["gained"] += delta
        run = self.run
        run.rating = min(float(self.cfg["run"]["max_rating"]), run.rating + delta)
        if run.rating <= self.cfg["run"]["lose_rating"] and not self.game_over:
            run.rating = max(run.rating, float(self.cfg["run"]["lose_rating"]))
            self.game_over = True
            self.note("game_over")

    def _check_overdue(self, dt: float):
        rc = self.cfg["rating"]
        drains = []
        for tid in list(self.open_ids):
            t = self.tasks[tid]
            if t.done or t.available is None or t.hidden:
                continue
            if self.now <= t.available + t.deadline:
                continue
            if not t.overdue:
                t.overdue = True
                self.stats["overdue"] += 1
                if not t.meta.get("counted"):
                    t.meta["counted"] = True
                    self.stats["imp_due"] += t.importance
                self.change_rating(-t.importance * rc["miss_penalty"], "overdue", t)
                if t.importance >= 1.5:
                    self.note("toast", text=f"Missed deadline: {self.task_title(t)}", tone="bad")
                self.add_log(f"Overdue: {self.task_title(t)}", "bad")
            cap = t.importance * rc["overdue_cap_mult"]
            if t.overdue_penalty < cap:
                drains.append((t, min(cap - t.overdue_penalty, t.importance * rc["overdue_drain_per_hour"] * dt / 60.0)))
        if drains:
            total = sum(d for _, d in drains)
            # The cap is on the trust actually lost per hour, after modifiers like rising expectations.
            loss_mult = max(0.01, self.mods.mult("rating_loss", Ctx(shift=self.shift["key"])))
            limit = rc.get("overdue_drain_cap_per_hour", 1e9) * dt / 60.0 / loss_mult
            scale = min(1.0, limit / total) if total > 0 else 1.0
            for t, d in drains:
                t.overdue_penalty += d * scale
            self.change_rating(-total * scale, "overdue")

    def _auto_review(self):
        spec = self.specials["auto_review"]
        for tid in list(self.inbox):
            t = self.tasks.get(tid)
            if t is None or t.type != "review" or t.assignee is not None or t.available is None:
                continue
            ev = self.events.get(t.event_uid)
            if ev is None or ev.mag > spec["max_mag"]:
                continue
            if self.now - t.available >= spec["after_minutes"]:
                self.complete_external(t)
                self.stats["auto_reviewed"] += 1

    # ---------------------------------------------------------------- spawning
    def _spawn_event(self, ev_tuple):
        _, mag, lat, lon, depth, desc, eid, otime = ev_tuple
        eq = self.cfg["eq"]
        ev = EqEvent(uid=self.run.new_id("event"), event_id=eid, t=self.now, mag=mag, lat=lat, lon=lon,
                     depth=depth, region=region_of(self.data, lat, lon), description=desc, origin_time=otime,
                     noise_initial=0.0,
                     noise_prelim=self.rng.uniform(-eq["display_noise_prelim"], eq["display_noise_prelim"]))
        self.events[ev.uid] = ev
        tasks = build_event_tasks(self.run, self.data, ev, self.now)
        # The automatic magnitude is fuzzy (+-display_noise_initial) but stays consistent with the
        # workflow it triggered: two-stage events look bigger than the threshold, SOP events meet
        # their trigger, single-stage events stay below it.
        lo, hi = -eq["display_noise_initial"], eq["display_noise_initial"]
        if ev.two_stage:
            lo = max(lo, eq["two_stage_above"] + 0.05 - mag)
        else:
            hi = min(hi, eq["two_stage_above"] - mag)
        thr = sop_threshold(self.data, mag, depth, ev.region)
        if thr is not None:
            lo = max(lo, thr - mag)
        ev.noise_initial = self.rng.uniform(lo, hi) if hi > lo else lo
        for t in tasks:
            self._add_task(t)
        self._schedule_dart(ev)
        self.stats["events"] += 1
        big = self.stats["biggest"]
        if big is None or mag > big[0]:
            self.stats["biggest"] = (mag, desc)
        self.note("eq", uid=ev.uid)
        if ev.sops:
            self.stats["sop_events"] += 1
            names = ", ".join(self.data.sop_by_id[s]["name"] for s in ev.sops)
            self.note("toast", text=f"SOP: {names} — {ev.mag_label()} {short_place(desc, 30)}", tone="sop", big=True)
            self.add_log(f"SOP activated ({names}) for {ev.mag_label()} {desc}", "sop")
            if self.cfg["time"].get("pause_on_sop", True):
                self.note("pause", reason="sop")
        spec = self.specials.get("auto_assign")
        if spec and not ev.two_stage and mag <= spec["max_mag"]:
            avail = self.present_ghas()
            if avail:
                review = self.tasks[ev.task_ids["review"]]
                best = min(avail, key=lambda g: self.queue_eta(g))
                self.assign(review.id, best.id)

    def spawn_bau(self, bau_id: str) -> Task:
        task = build_bau_task(self.run, self.data, bau_id, self.now)
        self._add_task(task)
        return task

    # -------------------------------------------------------------------- DART
    def _schedule_dart(self, ev: EqEvent):
        hits = triggered_buoys(self.data, ev.mag, ev.lat, ev.lon, ev.depth)
        speed = max(1.0, self.data.dart_cfg["wave_speed_km_per_min"])
        for b, dist in hits:
            self._push(self.now + dist / speed, TL_DART, (ev.uid, b["code"]))

    def dart_active(self, code: str) -> bool:
        return self.now < self.dart_until.get(code, -1.0)

    def running_sop_event(self, prefer: EqEvent | None = None) -> EqEvent | None:
        active = [ev for ev, tasks in self.active_sop_events(keep_minutes=0.0) if any(not t.done for t in tasks)]
        if prefer is not None and prefer in active:
            return prefer
        return max(active, key=lambda e: e.t) if active else None

    def _dart_trigger(self, uid: int, code: str):
        cfg = self.data.dart_cfg
        b = dart_buoy(self.data, code)
        if b is None:
            return
        self.dart_until[code] = self.now + cfg["event_mode_hours"] * 60.0
        self.dart_last[code] = (self.now, uid)
        self.stats["dart_triggers"] += 1
        self.note("dart", code=code, uid=uid)
        self.add_log(f"DART {b['id']} ({b['name']}) triggered", "sop")
        ev = self.events.get(uid)
        if ev is None or ev.meta.get("dart_handled"):
            return
        ev.meta["dart_handled"] = True
        assess = cfg["assess_task"]
        running = self.running_sop_event(prefer=ev)
        if running is not None:
            if assess in running.task_ids:
                return
            task = build_sop_task(self.run, self.data, running, assess, self.now, list(running.sops))
            self._add_task(task)
            running.task_ids[assess] = task.id
            sop_name = self.data.sop_by_id[running.sops[0]]["name"] if running.sops else "SOP"
            self.note("toast", text=f"DART {b['id']} triggered: '{task.name}' added to the {sop_name} SOP",
                      tone="sop", big=True)
            self.add_log(f"{task.name} added to the {sop_name} SOP ({running.mag_label()})", "sop")
            if self.cfg["time"].get("pause_on_sop", True):
                self.note("pause", reason="dart")
            return
        sop = self.data.sop_by_id[cfg["sop"]]
        ev.sops.append(sop["id"])
        tasks = build_sop_checklist(self.run, self.data, ev, sop, self.now)
        for t in tasks:
            t.requires = [r for r in t.requires if r in self.tasks and not self.tasks[r].done]
            if not t.requires and t.available is None and "available_at" not in t.meta:
                t.available = self.now
            self._add_task(t)
            if "available_at" in t.meta and not t.requires:
                self._push(t.meta["available_at"], TL_UNLOCK, t.id)
        self.stats["sop_events"] += 1
        self.note("toast", text=f"SOP: {sop['name']} — DART {b['id']} after {ev.mag_label()} "
                                f"{short_place(ev.description, 24)}", tone="sop", big=True)
        self.add_log(f"SOP activated ({sop['name']}) after DART {b['id']} triggered", "sop")
        if self.cfg["time"].get("pause_on_sop", True):
            self.note("pause", reason="sop")

    # -------------------------------------------------------------- auto-assign
    @property
    def auto(self) -> dict:
        st = self.run.flags.get("auto_assign")
        if not isinstance(st, dict):
            st = {"on": False, "mode": self.cfg.get("auto_assign", {}).get("default_mode", "balanced")}
            self.run.flags["auto_assign"] = st
        if st.get("mode") not in AUTO_MODES:
            st["mode"] = "balanced"
        return st

    def set_auto(self, on: bool | None = None, mode: str | None = None):
        st = self.auto
        if on is not None:
            st["on"] = bool(on)
        if mode is not None and mode in AUTO_MODES:
            st["mode"] = mode
        if st["on"]:
            self._auto_dirty = True
            self._auto_assign()

    def urgency(self, t: Task) -> tuple:
        """Sort key: overdue first, then by deadline pulled forward by importance."""
        due = t.due_at()
        if due is None:
            due = self.now + t.deadline + 30.0
        return (0 if t.overdue else 1, due - t.importance * 40.0)

    def _maybe_auto_assign(self):
        if not self.auto["on"]:
            return
        if self._auto_dirty or self.now >= self._auto_next:
            self._auto_assign()

    def _auto_assign(self):
        cfg = self.cfg.get("auto_assign", {})
        self._auto_dirty = False
        self._auto_next = self.now + cfg.get("check_every_minutes", 1.0)
        staff = [self.ghas[gid] for gid in self.on_shift if gid in self.ghas]
        if not staff:
            return
        todo = [self.tasks[tid] for tid in self.inbox if tid in self.tasks]
        todo = [t for t in todo if not t.done and not t.hidden and t.available is not None and t.assignee is None
                and not t.meta.get("manual_unassign")]
        if not todo:
            return
        todo.sort(key=self.urgency)
        mode = self.auto["mode"]
        horizon = cfg.get("horizon_minutes", 120.0)
        loads, counts = {}, {}
        for g in staff:
            wait = max(0.0, g.arrive_at - self.now) + max(0.0, g.away_until - self.now)
            loads[g.id] = self.queue_eta(g) + wait
            counts[g.id] = sum(1 for q in g.queue if q in self.tasks and not self.tasks[q].done)
        for t in todo:
            pool = staff
            if mode not in ("fastest", "balanced"):
                roomy = [g for g in staff if loads[g.id] <= horizon]
                pool = roomy or staff
            best, best_key = None, None
            for g in pool:
                eta, err = self.estimate(g, t)
                finish = loads[g.id] + eta
                if mode == "fastest":
                    key = (finish,)
                elif mode == "safest":
                    key = (round(err, 3), finish)
                elif mode == "freshest":
                    key = (round(g.fatigue), finish)
                elif mode == "shortest":
                    key = (counts[g.id], finish)
                else:
                    key = (finish + err * t.importance * 200.0,)
                if best_key is None or key < best_key:
                    best, best_key = g, key
            if best is None:
                continue
            mine = self.urgency(t)
            index = len(best.queue)
            for i, qid in enumerate(best.queue):
                q = self.tasks.get(qid)
                if q is None or q.done or q.progress > 0:
                    continue
                if self.urgency(q) > mine:
                    index = i
                    break
            self.assign(t.id, best.id, index)
            loads[best.id] += self.estimate(best, t)[0]
            counts[best.id] += 1

    # ------------------------------------------------------------------ shifts
    def lineup(self, slot: int) -> list:
        roster = self.run.roster
        ov = self.overrides.get(slot, {})
        added = ov.get("add", [])
        ids = [i for i in roster.lineup(slot) if i not in ov.get("remove", [])]
        ids += [i for i in added if i not in ids]
        out = []
        for gid in ids:
            g = self.ghas.get(gid)
            if g is None or not g.active or g.temp:
                continue
            if gid not in added and (gid in self.run.away_week or gid in roster.leave):
                continue
            out.append(gid)
        return out[: self.desks]

    def _seat(self, g: GHA, arrive_in: float | None = None) -> bool:
        if g.on_shift:
            return True
        if None not in self.seats:
            return False
        idx = self.seats.index(None)
        self.seats[idx] = g.id
        g.seat = idx
        g.on_shift = True
        g.arrive_at = self.now + (self.cfg["time"]["handover_minutes"] if arrive_in is None else arrive_in)
        g.away_until = 0.0
        g.shift_minutes = 0.0
        g.shift_work_minutes = 0.0
        return True

    def _unseat(self, g: GHA):
        self._return_queue(g)
        if 0 <= g.seat < len(self.seats) and self.seats[g.seat] == g.id:
            self.seats[g.seat] = None
        g.seat = -1
        g.on_shift = False
        g.away_until = 0.0
        g.double_shift = False

    def _return_queue(self, g: GHA):
        for tid in list(g.queue):
            t = self.tasks.get(tid)
            if t is None:
                continue
            t.assignee = None
            if not t.done and not t.hidden and tid not in self.inbox:
                self.inbox.append(tid)
        g.queue = []
        self._auto_dirty = True

    def _close_shift(self, g: GHA):
        """Long-term fatigue for the shift just worked."""
        if g.temp or g.shift_minutes <= 0:
            return
        lt = self.cfg["long_term"]
        shift = self.shift
        length = shift["hours"] * 60.0
        busy = g.shift_work_minutes / max(1.0, g.shift_minutes)
        gain = (lt["per_shift_base"] * min(1.0, g.shift_minutes / length) + lt["per_shift_busy"] * busy) * shift["ltf_mult"]
        if g.double_shift:
            gain *= lt["double_shift_mult"]
        gain *= self.mods.mult("ltf_gain", Ctx(gha=g, shift=shift["key"]))
        g.ltf = min(100.0, g.ltf + gain)
        g.stats["shifts"] += 1
        g.shift_minutes = 0.0
        g.shift_work_minutes = 0.0
        if g.ltf >= lt["warn_level"] and not g.ltf_warned:
            g.ltf_warned = True
            self.note("toast", text=f"{g.first_name} is close to burning out. Give them leave.", tone="warn")
            self.add_log(f"{g.name}: long-term fatigue {g.ltf:.0f}", "warn")

    def _burnout(self, g: GHA):
        g.active = False
        g.left_reason = "Burned out"
        self.run.roster.remove(g.id)
        self._unseat(g)
        self.stats["burnouts"].append(g.name)
        self.note("toast", text=f"{g.name} has burned out and resigned.", tone="bad", big=True)
        self.add_log(f"{g.name} burned out and resigned", "bad")

    def _start_slot(self, slot: int):
        prev = list(self.on_shift)
        if self.slot >= 0:
            for gid in prev:
                self._close_shift(self.ghas[gid])
        self.slot = slot
        new = self.lineup(slot)
        leaving = [gid for gid in prev if gid not in new]
        staying = [gid for gid in prev if gid in new]
        for gid in leaving:
            g = self.ghas[gid]
            self._unseat(g)
            if g.temp:
                g.active = False
                self.ghas.pop(gid, None)
                if g in self.run.ghas:
                    self.run.ghas.remove(g)
            self.note("leave", gha=gid)
        for gid in staying:
            self.ghas[gid].double_shift = True
        for gid in new:
            g = self.ghas[gid]
            if not g.on_shift:
                self._seat(g)
                if slot == 0 and gid in self.run.last_slot_lineup:
                    g.double_shift = True
                self.note("arrive", gha=gid)
        burn = self.cfg["long_term"]["burnout_level"]
        for gid in list(self.on_shift):
            g = self.ghas[gid]
            if g.ltf >= burn and not g.temp:
                self._burnout(g)
        for g in list(self.ghas.values()):
            if g.active and not g.on_shift and not g.temp and g.ltf >= burn:
                self._burnout(g)

        self.unmanned = not self.on_shift
        label = self.slot_label(slot)
        if self.unmanned:
            self.stats["unmanned_shifts"] += 1
            self.change_rating(-self.cfg["rating"]["unmanned_shift_penalty"], "other")
            self.note("toast", text=f"UNMANNED SHIFT: nobody is rostered for the {label}!", tone="bad", big=True)
            self.add_log(f"{label}: unmanned", "bad")
        else:
            names = ", ".join(self.ghas[g].first_name for g in self.on_shift)
            self.add_log(f"{label}: {names}", "info")
        self.note("shift", slot=slot, label=label)

        for bau in self.data.bau.values():
            if bau.get("schedule", {}).get("type") == "every_shift" and not self.unmanned:
                self.spawn_bau(bau["id"])
        for tid in list(self.open_ids):
            t = self.tasks[tid]
            if t.kind == "staffing" and t.meta.get("slot") == slot and not t.done:
                t.failed = True
                t.done = True
                self._detach(t)
                self.open_ids.discard(tid)
                self.add_log("No cover was arranged in time", "bad")
        self.shields = int(self.specials.get("error_shield_per_shift", 0))
        self._roll_sick(slot)
        start, length = self.slot_start(slot), self.shift["hours"] * 60.0
        for rt in self.specials.get("random_tasks", []):
            if self.rng.random() < rt["chance_per_shift"]:
                self._push(start + self.rng.uniform(0.1, 0.9) * length, TL_BAU, rt["task"])

    def _roll_sick(self, slot: int):
        nxt = slot + 1
        if nxt >= 7 * self.n_shifts:
            return
        sick = self.cfg["sick"]
        probs = []
        for gid in self.lineup(nxt):
            g = self.ghas[gid]
            p = sick["base_chance_per_person_shift"] * (1.0 + g.ltf / sick["ltf_divisor"])
            p *= self.mods.mult("sick_chance", Ctx(gha=g))
            probs.append((gid, p))
        if not probs:
            return
        none = 1.0
        for _, p in probs:
            none *= (1.0 - min(0.95, p))
        if self.rng.random() >= 1.0 - none:
            return
        pick = self.rng.random() * sum(p for _, p in probs)
        acc, chosen = 0.0, probs[-1][0]
        for gid, p in probs:
            acc += p
            if pick <= acc:
                chosen = gid
                break
        length = self.shift["hours"] * 60.0
        self._push(self.slot_start(slot) + self.rng.uniform(0.1, 0.75) * length, TL_SICK, (nxt, chosen))

    def _sick_call(self, slot: int, gid: int):
        if gid not in self.lineup(slot):
            return
        g = self.ghas[gid]
        self.overrides.setdefault(slot, {"add": [], "remove": []})["remove"].append(gid)
        task = build_staffing_task(self.run, self.data, self.now, self.slot_start(slot) - self.now, g,
                                   slot, self.slot_label(slot))
        self._add_task(task)
        self.stats["sick_calls"] += 1
        self.note("toast", text=f"{g.first_name} called in sick for the {self.slot_label(slot)}", tone="warn")
        self.add_log(f"{g.name} called in sick ({self.slot_label(slot)})", "warn")

    def staffing_options(self) -> list:
        if not self.modal or self.modal.get("type") != "staffing":
            return []
        slot, sick = self.modal["slot"], self.modal["sick"]
        lineup = set(self.lineup(slot))
        opts = [g for g in self.ghas.values()
                if g.active and not g.temp and g.id != sick and g.id not in lineup and g.id not in self.run.away_week]
        return sorted(opts, key=lambda g: (g.on_shift, g.id in self.run.roster.leave, g.fatigue))

    def resolve_staffing(self, gid: int | None):
        if not self.modal or self.modal.get("type") != "staffing":
            return
        slot = self.modal["slot"]
        label = self.slot_label(slot)
        if gid is not None and gid in self.ghas:
            g = self.ghas[gid]
            self.overrides.setdefault(slot, {"add": [], "remove": []})["add"].append(gid)
            if gid in self.run.roster.leave:
                self.leave_cancelled.add(gid)
            self.stats["covers"] += 1
            self.add_log(f"{g.name} will cover the {label}", "good")
        else:
            self.add_log(f"No cover for the {label}", "warn")
        self.modal = None

    def send_away(self, g: GHA, hours: float, reason: str):
        if not g.on_shift:
            return
        self._return_queue(g)
        g.away_until = max(self.now, g.arrive_at) + hours * 60.0
        g.away_reason = reason
        self.note("away", gha=g.id)
        self.add_log(f"{g.first_name}: {reason} ({hours:g} h)", "info")

    def add_temp_gha(self, name: str, skills: dict) -> GHA | None:
        if None not in self.seats:
            return None
        color = (200, 200, 210)
        g = GHA(id=self.run.new_id("gha"), name=name, color=color, skills=dict(skills), traits=[], salary=0.0,
                fatigue=10.0, ltf=0.0, temp=True)
        g.avatar = random_avatar(self.rng)
        for key in self.data.skill_keys:
            g.skills.setdefault(key, 1)
        self.run.ghas.append(g)
        self.ghas[g.id] = g
        self._seat(g, arrive_in=15)
        self.note("arrive", gha=g.id)
        return g

    # ------------------------------------------------------------ random events
    def _random_event(self):
        used = set(self.run.used_events)
        pool = [e for e in self.data.events.values() if e["id"] not in used]
        if not pool:
            self.run.used_events = []
            pool = list(self.data.events.values())
        pool = [e for e in pool if any(self.option_available(o) for o in e["options"])]
        if not pool:
            return
        pick = self.rng.random() * sum(e.get("weight", 1.0) for e in pool)
        acc, chosen = 0.0, pool[-1]
        for e in pool:
            acc += e.get("weight", 1.0)
            if pick <= acc:
                chosen = e
                break
        self.run.used_events.append(chosen["id"])
        self.modal = {"type": "event", "id": chosen["id"]}
        self.note("modal", kind="event")

    def option_available(self, opt: dict) -> bool:
        req = opt.get("requires", {})
        if "on_shift_min" in req and len(self.present_ghas()) < req["on_shift_min"]:
            return False
        if "budget" in req and self.run.budget < req["budget"]:
            return False
        return True

    def resolve_event(self, index: int) -> list:
        if not self.modal or self.modal.get("type") != "event":
            return []
        ev = self.data.events[self.modal["id"]]
        opt = ev["options"][index]
        if not self.option_available(opt):
            return []
        msgs = fx.apply_effects(self, opt.get("effects", []), None)
        self.add_log(f"{ev['title']}: {opt['label']}", "info")
        self.modal = None
        return [m for m in msgs if m]

    # ---------------------------------------------------------------- week end
    def _end_week(self):
        self.run.last_slot_lineup = [gid for gid in self.on_shift if not self.ghas[gid].temp]
        for gid in list(self.on_shift):
            g = self.ghas[gid]
            self._close_shift(g)
            self._unseat(g)
            if g.temp:
                g.active = False
                if g in self.run.ghas:
                    self.run.ghas.remove(g)
        carry = [t for t in self.tasks.values() if not t.done and not t.failed]
        for t in carry:
            t.assignee = None
        uids = {t.event_uid for t in carry if t.event_uid is not None}
        self.run.carry_tasks = carry
        self.run.carry_events = {uid: self.events[uid] for uid in uids if uid in self.events}
        self.week_done = True
        self.note("week_done")

    # ----------------------------------------------------------------- display
    def task_title(self, t: Task) -> str:
        if t.kind == "eq":
            ev = self.events.get(t.event_uid)
            if ev is not None:
                return f"{t.name} {ev.mag_label()} {short_place(ev.description, 18)}"
        return t.name

    def visible_inbox(self) -> list:
        return [self.tasks[tid] for tid in self.inbox if tid in self.tasks and not self.tasks[tid].done]

    def active_sop_events(self, keep_minutes: float = 120.0) -> list:
        out = []
        for ev in self.events.values():
            if not ev.sops:
                continue
            tasks = [self.tasks[tid] for tid in ev.task_ids.values() if tid in self.tasks]
            if any(not t.done for t in tasks) or any(t.done_at and self.now - t.done_at < keep_minutes for t in tasks):
                out.append((ev, tasks))
        out.sort(key=lambda p: p[0].t)
        return out
