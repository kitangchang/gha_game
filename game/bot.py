"""A simple automated player, used for headless balancing (tools/simulate.py).

It is deliberately 'reasonable but not clever': it triages by deadline and
importance, gives people leave when they get worn down, and buys sensible
things in the shop."""
from __future__ import annotations

from . import shop as shopmod
from .run import consumable_slots, rotation_grid, snake_draft

RELIC_PRIORITY = ["picker_upgrade", "espresso", "triage_bot", "auto_locator", "legacy_script", "coffee_machine",
                  "second_monitors", "video_wall", "snack_drawer", "wellness", "comms_team", "rubber_duck",
                  "noise_cancelling", "standing_desks", "circadian", "office_dog", "budget_analyst",
                  "tsunami_db", "eat_autofill", "pager_app", "media_training", "shared_runbook"]


class Bot:
    def __init__(self, data, attention: float = 3.0, horizon: float = 150.0, use_leave: bool = True,
                 use_shop: bool = True, triage: bool = True, max_per_look: int = 999):
        self.data = data
        self.max_per_look = max_per_look  # how many cards a 'human' can drag per look
        self.attention = attention        # game minutes between looks at the inbox
        self.horizon = horizon            # don't stack more than this many minutes on one analyst
        self.use_leave = use_leave
        self.use_shop = use_shop
        self.triage = triage
        self._next_look = 0.0
        self.busy_samples = 0
        self.present_samples = 0

    # ---------------------------------------------------------------- planning
    def plan_week(self, run):
        """Two analysts per team on the rotation; spare analysts cover for whoever is on leave."""
        data = self.data
        roster = run.roster
        teams = data.team_keys
        available = [g for g in run.active_ghas() if g.id not in run.away_week]
        for g in run.active_ghas():
            roster.remove(g.id)
        leave = []
        if self.use_leave:
            # Spare people beyond two per team can rest freely; one more can go if they're
            # getting worn down (their team then runs with one analyst that week).
            spare = max(0, len(available) - 2 * len(teams))
            worn = sorted(available, key=lambda g: -g.ltf)
            for g in worn:
                if len(leave) >= spare + 1:
                    break
                if g.ltf >= 60 or (len(leave) < spare and g.ltf >= 40):
                    leave.append(g)
        roster.leave = [g.id for g in leave]
        working = [g for g in available if g not in leave]
        for team, ids in snake_draft(teams, working).items():
            roster.teams[team] = ids
        roster.grid = rotation_grid(data, run.week)

    def shop(self, run):
        if not self.use_shop or not run.shop:
            return
        data = self.data
        sh = run.shop
        if len(run.active_ghas()) < 12:
            best, best_val = None, 0.0
            for i, item in enumerate(sh["hires"]):
                if item["sold"]:
                    continue
                g = item["gha"]
                value = (sum(g.skills.values()) + 2 * g.skills["seismic"]) / max(1.0, g.salary) - g.ltf / 40
                if value > best_val and run.budget - item["cost"] >= 6:
                    best, best_val = i, value
            if best is not None:
                shopmod.buy_hire(data, run, best)
        offered = {item["id"]: i for i, item in enumerate(sh["relics"]) if not item["sold"]}
        for rid in RELIC_PRIORITY:
            if rid in offered and run.budget >= sh["relics"][offered[rid]]["cost"] + 3:
                shopmod.buy_relic(data, run, offered[rid])
        for i, item in enumerate(sh["consumables"]):
            if (not item["sold"] and item["id"] in ("pizza_night", "focus_hour", "coffee_run")
                    and len(run.consumables) < consumable_slots(data, run) and run.budget >= item["cost"] + 8):
                shopmod.buy_consumable(data, run, i)

    # ------------------------------------------------------------------- shift
    def notify(self, eng, notes):
        """A human gets a pause when an SOP fires, so react straight away."""
        for n in notes:
            if n["type"] in ("pause", "unlock", "modal") or (n["type"] == "toast" and n.get("tone") == "warn"):
                self._next_look = eng.now
                return

    def _priority(self, eng, t):
        due = t.due_at()
        if due is None:   # locked: estimate it will be due a little after now
            due = eng.now + t.deadline + 30.0
        return (0 if t.overdue else 1, due - t.importance * 40.0)

    def act(self, eng):
        if eng.modal:
            self.decide(eng)
            return
        if eng.now < self._next_look:
            return
        self._next_look = eng.now + self.attention
        present = [eng.ghas[gid] for gid in eng.on_shift]
        if not present:
            return
        for g in present:
            if eng.present(g):
                self.present_samples += 1
                if eng.current_task(g) is not None:
                    self.busy_samples += 1
        open_tasks = [t for t in eng.visible_inbox()
                      if not t.locked or t.kind == "sop" or t.type == "confirm"]
        if self.triage:
            open_tasks.sort(key=lambda t: self._priority(eng, t))
        loads = {g.id: eng.queue_eta(g) + max(0.0, g.arrive_at - eng.now) for g in present}
        assigned = 0
        for t in open_tasks:
            if assigned >= self.max_per_look:
                break
            best, best_score = None, None
            for g in present:
                eta, err = eng.estimate(g, t)
                score = loads[g.id] + eta + err * t.importance * 200.0
                if best_score is None or score < best_score:
                    best, best_score = g, score
            if best is None:
                break
            if loads[best.id] > self.horizon and t.importance < 1.5 and not t.overdue:
                continue
            index = None
            if self.triage:
                mine = self._priority(eng, t)
                index = len(best.queue)
                for i, qid in enumerate(best.queue):
                    q = eng.tasks.get(qid)
                    if q is not None and self._priority(eng, q) > mine:
                        index = i
                        break
            eng.assign(t.id, best.id, index)
            assigned += 1
            loads[best.id] += eng.estimate(best, t)[0]
        self._use_items(eng, present)

    def _use_items(self, eng, present):
        run = eng.run
        backlog = sum(1 for t in eng.visible_inbox() if not t.locked)
        if backlog > 25 and None in eng.seats and run.budget > 6 and eng.shift_progress() < 0.7:
            spare = [g for g in eng.call_in_options() if g.id not in run.roster.leave and g.fatigue < 50]
            if spare:
                eng.call_in(min(spare, key=lambda g: g.fatigue).id)
        if "pizza_night" in run.consumables and sum(g.fatigue for g in present) / len(present) > 65:
            eng.use_consumable(run.consumables.index("pizza_night"))
        if "coffee_run" in run.consumables and sum(g.fatigue for g in present) / len(present) > 70:
            eng.use_consumable(run.consumables.index("coffee_run"))
        if "focus_hour" in run.consumables and len(eng.inbox) > 25:
            eng.use_consumable(run.consumables.index("focus_hour"))

    def decide(self, eng):
        m = eng.modal
        if m["type"] == "staffing":
            opts = [g for g in eng.staffing_options() if not g.on_shift and g.id not in eng.run.roster.leave]
            eng.resolve_staffing(opts[0].id if opts else None)
        elif m["type"] == "event":
            ev = eng.data.events[m["id"]]
            best, best_score = None, None
            for i, opt in enumerate(ev["options"]):
                if not eng.option_available(opt):
                    continue
                score = 0.0
                for e in opt.get("effects", []):
                    if e["type"] == "rating":
                        score += e["amount"]
                    elif e["type"] == "budget":
                        score += e["amount"] * 0.8
                    elif e["type"] == "away":
                        score -= 2.0 * e.get("hours", 1)
                    elif e["type"] == "modifier":
                        v = e["modifier"]["value"]
                        stat = e["modifier"]["stat"]
                        sign = 1 if stat in ("speed",) else -1
                        score += sign * (v - 1.0) * e.get("hours", 1) * 0.8
                    elif e["type"] == "relic":
                        score += 4
                if best_score is None or score > best_score:
                    best, best_score = i, score
            eng.resolve_event(best if best is not None else 0)
