"""End-of-week summary, game over and season complete screens."""
from __future__ import annotations

import pygame

from game.profile import finish_run, run_score, xp_progress
from game.util import fmt_money

from ..app import Scene
from ..icons import get_icons
from ..richtext import get_rich
from ..theme import RARITY, C, H, W, trust_color
from ..widgets import TOOLTIP, Button, bar, draw_text, panel, pill
from .boss_reward import BossReward
from .common import draw_portrait, fatigue_color, group_label, group_of, skill_pill, team_color_of

BOX_W, BOX_GAP = 580, 30


def _loss(v: float) -> str:
    return f"-{v:.1f}" if v > 0.05 else "0.0"


def _note(surf, text, pos, size, col, width):
    rt = get_rich()
    if rt is not None:
        rt.draw_line(surf, text, pos, size, col, width)
    else:
        draw_text(surf, text, pos, size, col, max_width=width)


def _row(surf, x, y, label, value, w=520, col=C.text, size=15):
    draw_text(surf, label, (x, y), size - 1, C.dim)
    draw_text(surf, value, (x + w, y), size, col, "semibold", anchor="topright")
    return y + size + 12


def _boxes(top: int, height: int) -> list:
    total = 3 * BOX_W + 2 * BOX_GAP
    x0 = (W - total) // 2
    return [pygame.Rect(x0 + i * (BOX_W + BOX_GAP), top, BOX_W, height) for i in range(3)]


class SummaryScene(Scene):
    def __init__(self, app, run, summary: dict):
        super().__init__(app)
        self.run = run
        self.s = summary
        final = run.phase == "won"
        self.reward = BossReward(app, run, on_done=self.next)
        if final:
            label = "See the season results  ▶"
        elif self.reward.pending:
            label = "Choose your boss reward  ▶"
        else:
            label = f"Plan week {run.week + 1}  ▶"
        self.button = Button((W // 2 - 190, H - 96, 380, 56), label, self.advance, "primary", 18)

    def advance(self):
        if self.reward.pending:
            self.reward.show()
        else:
            self.next()

    def next(self, message: str = ""):
        if self.run.phase == "won":
            self.app.change(VictoryScene(self.app, self.run))
        else:
            from .planning import PlanningScene
            scene = PlanningScene(self.app, self.run)
            if message:
                scene.flash(message, C.good if message.startswith("New") else C.dim)
            self.app.change(scene)

    def handle(self, event):
        if self.reward.handle(event):
            return
        if self.button.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.advance()

    def draw(self, surf):
        s = self.s
        mouse = pygame.mouse.get_pos()
        draw_text(surf, f"WEEK {s['week']} COMPLETE", (W // 2, 60), 38, C.text, "bold", anchor="midtop")
        start, end = s["rating_start"], s["rating_end"]
        delta = end - start
        draw_text(surf, f"Public trust {start:.0f} → {end:.0f}  ({delta:+.1f})", (W // 2, 116), 21,
                  trust_color(end), "semibold", anchor="midtop")
        boxes = _boxes(180, 700)
        for b in boxes:
            panel(surf, b, C.panel, C.border, radius=12)
        inner = BOX_W - 56
        # Column 1: the week
        x, y = boxes[0].x + 28, boxes[0].y + 24
        draw_text(surf, "THE WEEK", (x, y), 12, C.faint, "bold")
        y += 32
        done = max(1, s["tasks_done"])
        y = _row(surf, x, y, "Earthquakes", f"{s['events']}", inner)
        y = _row(surf, x, y, "SOP events", f"{s['sop_events']}", inner, col=C.sop if s["sop_events"] else C.text)
        if s.get("dart_triggers"):
            y = _row(surf, x, y, "DART buoy triggers", f"{s['dart_triggers']}", inner, col=C.sop)
        y = _row(surf, x, y, "Tasks completed", f"{s['tasks_done']}", inner)
        y = _row(surf, x, y, "On time", f"{100.0 * s['ontime'] / done:.1f}%", inner)
        y = _row(surf, x, y, "Errors", f"{s['errors']}" + (f"  ({s['caught']} caught)" if s["caught"] else ""), inner,
                 col=C.bad if s["errors"] else C.text)
        y = _row(surf, x, y, "Went overdue", f"{s['overdue']}", inner, col=C.warn if s["overdue"] else C.text)
        y = _row(surf, x, y, "Sick calls / covers", f"{s['sick_calls']} / {s['covers']}", inner)
        y = _row(surf, x, y, "Call-ins", f"{s['call_ins']}", inner)
        y = _row(surf, x, y, "Unmanned shifts", f"{s['unmanned']}", inner, col=C.bad if s["unmanned"] else C.text)
        if s.get("auto_reviewed"):
            y = _row(surf, x, y, "Auto-reviewed events", f"{s['auto_reviewed']}", inner)
        y = _row(surf, x, y, "Carried into next week", f"{s['carried']} tasks", inner)
        if s["biggest"]:
            mag, desc = s["biggest"]
            y += 8
            draw_text(surf, "Biggest event", (x, y), 14, C.dim)
            draw_text(surf, f"M{mag:.1f} {desc}", (x, y + 22), 16, C.text, "semibold", max_width=inner)
        # Column 2: trust and team
        x, y = boxes[1].x + 28, boxes[1].y + 24
        draw_text(surf, "TRUST", (x, y), 12, C.faint, "bold")
        y += 32
        y = _row(surf, x, y, "Gained from on-time work", f"+{s['gained']:.1f}", inner, col=C.good)
        y = _row(surf, x, y, "Lost to errors", _loss(s["lost_errors"]), inner,
                 col=C.bad if s["lost_errors"] > 0.05 else C.text)
        y = _row(surf, x, y, "Lost to late tasks", _loss(s["lost_overdue"]), inner,
                 col=C.bad if s["lost_overdue"] > 0.05 else C.text)
        y = _row(surf, x, y, "Other", _loss(s["lost_other"]), inner, col=C.bad if s["lost_other"] > 0.05 else C.text)
        y += 16
        draw_text(surf, "TEAM", (x, y), 12, C.faint, "bold")
        y += 26
        notes = [(f"Burned out: {n}", C.bad) for n in s["burnouts"]]
        notes += [(f"Level up: {n}", C.accent) for n in s["level_ups"]]
        notes += [(f"Leave: {n}", C.good) for n in s["leave"]]
        if not notes:
            notes = [("Nothing to report.", C.faint)]
        for text, col in notes[:7]:
            _note(surf, text, (x, y), 13, col, inner)
            y += 21
        if len(notes) > 7:
            draw_text(surf, f"…and {len(notes) - 7} more", (x, y), 12, C.faint)
            y += 21
        self._condition(surf, x, max(y + 16, boxes[1].bottom - 30 - 8 * 28), boxes[1].bottom - 6)
        # Column 3: money
        x, y = boxes[2].x + 28, boxes[2].y + 24
        draw_text(surf, "FUNDING", (x, y), 12, C.faint, "bold")
        y += 32
        y = _row(surf, x, y, "Base grant", fmt_money(s["base"]), inner)
        y = _row(surf, x, y, f"Performance bonus ({s['perf_adj'] * 100:.0f}%)", fmt_money(s["bonus"]), inner)
        y = _row(surf, x, y, "Trust bonus", fmt_money(s["trust_bonus"]), inner)
        if abs(s["payout_mult"] - 1.0) > 1e-6:
            y = _row(surf, x, y, "Multiplier", f"×{s['payout_mult']:.2f}", inner)
        if s.get("weekly_bonus", 0) > 0.005:
            y = _row(surf, x, y, "Funding from tools", f"+{fmt_money(s['weekly_bonus'])}", inner, col=C.good)
        y = _row(surf, x, y, "Funding received", fmt_money(s["payout"]), inner, col=C.good)
        y = _row(surf, x, y, "Salaries", f"-{fmt_money(s['salaries'])}", inner, col=C.bad)
        if s["overtime"]:
            y = _row(surf, x, y, "Overtime (already paid)", f"-{fmt_money(s['overtime'])}", inner, col=C.dim)
        pygame.draw.line(surf, C.border, (x, y), (x + inner, y))
        y += 12
        y = _row(surf, x, y, "Net this week", fmt_money(s["net"]), inner, col=C.good if s["net"] >= 0 else C.bad,
                 size=17)
        y = _row(surf, x, y, "Budget now", fmt_money(s["budget_end"]), inner, col=C.gold, size=17)
        draw_text(surf, "Performance bonus = importance-weighted on-time rate, minus a penalty for errors.",
                  (x, boxes[2].bottom - 46), 11, C.faint, max_width=inner)
        if self.reward.pending and not self.reward.open:
            draw_text(surf, "You survived the boss day: a reward is waiting.", (W // 2, H - 128), 15,
                      RARITY["boss"], "semibold", anchor="midtop")
        self.button.draw(surf, mouse)
        if self.reward.open:
            TOOLTIP.clear()
            self.reward.draw(surf, mouse)

    def _condition(self, surf, x, y, bottom):
        """Who's worn out going into next week, worst first."""
        run, data = self.run, self.app.data
        draw_text(surf, "LONG-TERM FATIGUE GOING INTO NEXT WEEK", (x, y), 12, C.faint, "bold")
        y += 22
        team = sorted(run.active_ghas(), key=lambda g: -g.ltf)
        rows = max(1, (bottom - y) // 28)
        for i, g in enumerate(team[: rows * 2]):
            cx = x + (i // rows) * 262
            cy = y + (i % rows) * 28
            tcol = team_color_of(data, run, g)
            draw_portrait(surf, (cx + 11, cy + 11), 11, g, data, run, team_color=tcol)
            draw_text(surf, g.first_name, (cx + 28, cy + 3), 12, C.text, max_width=96)
            bar(surf, (cx + 130, cy + 9, 90, 5), g.ltf / 100.0, fatigue_color(g.ltf))
            draw_text(surf, f"{g.ltf:.0f}", (cx + 228, cy + 3), 12, fatigue_color(g.ltf), "semibold")


# ------------------------------------------------------------------ run end
class _RunEndScene(Scene):
    """Shared by game over and victory: awards centre XP once and shows it."""

    def __init__(self, app, run, won: bool, extra: dict | None = None):
        super().__init__(app)
        self.run = run
        self.result = None
        profile = app.profile
        if profile is not None and profile.run is run:
            self.result = finish_run(app.data, profile, run, won, extra)
            app.save()
        label = "Back to the centre" if profile is not None else "Back to title"
        self.button = Button((W // 2 - 170, H - 104, 340, 54), label, self.back, "primary", 17)

    def back(self):
        if self.app.profile is not None:
            from .centre import CentreScene
            self.app.change(CentreScene(self.app))
        else:
            from .title import TitleScene
            self.app.change(TitleScene(self.app))

    def handle(self, event):
        if self.button.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
            self.back()

    def draw_xp(self, surf, rect, mouse):
        panel(surf, rect, C.panel, C.border, radius=12)
        x, y = rect.x + 28, rect.y + 24
        draw_text(surf, "CENTRE XP", (x, y), 12, C.faint, "bold")
        res, profile, data = self.result, self.app.profile, self.app.data
        if res is None or profile is None:
            draw_text(surf, "No centre is open, so no XP was recorded.", (x, y + 32), 14, C.faint)
            return
        y += 34
        for label, xp in res["breakdown"]:
            y = _row(surf, x, y, label, f"+{xp}", rect.width - 56, col=C.gold, size=14)
        pygame.draw.line(surf, C.border, (x, y), (rect.right - 28, y))
        y += 12
        y = _row(surf, x, y, "Total", f"+{res['xp']} XP", rect.width - 56, col=C.gold, size=17)
        level, into, need = xp_progress(data, profile.xp)
        y += 6
        pill(surf, f"CENTRE LEVEL {level}", (x, y), C.bg, C.gold, size=13, pad_x=10, pad_y=4)
        bar(surf, (x, y + 34, rect.width - 56, 9), (into / need) if need else 1.0, C.gold, C.panel3, radius=4)
        draw_text(surf, f"{into:.0f} / {need:.0f} XP to level {level + 1}" if need else "Max level",
                  (x, y + 48), 12, C.dim)
        y += 78
        if res["new_level"] > res["old_level"]:
            draw_text(surf, f"Level up! {res['old_level']} → {res['new_level']}", (x, y), 18, C.gold, "bold")
            y += 30
            if res["unlocks"]:
                draw_text(surf, "NEW UNLOCKS", (x, y), 11, C.faint, "bold")
                y += 22
                icons = get_icons()
                from .centre import item_colour, item_lines, item_name
                for cat, iid in res["unlocks"][:6]:
                    r = pygame.Rect(x, y, rect.width - 56, 34)
                    if icons is not None:
                        icons.draw(surf, cat, iid, (x, y + 1), 30)
                    draw_text(surf, item_name(data, cat, iid), (x + 40, y + 7), 14, item_colour(data, cat, iid),
                              "semibold")
                    if r.collidepoint(mouse):
                        TOOLTIP.set(item_lines(data, cat, iid), 300)
                    y += 38


class GameOverScene(_RunEndScene):
    def __init__(self, app, run, eng):
        self.eng = eng
        st = eng.stats
        super().__init__(app, run, False, {"tasks": st["tasks_done"], "sops": st["sop_events"]})

    def draw(self, surf):
        run = self.run
        mouse = pygame.mouse.get_pos()
        draw_text(surf, "PUBLIC TRUST COLLAPSED", (W // 2, 120), 54, C.bad, "bold", anchor="midtop")
        day = self.eng.day_index + 1
        draw_text(surf, f"The Minister has ordered a review. You lasted until week {run.week + 1}, day {day}.",
                  (W // 2, 196), 19, C.dim, anchor="midtop")
        left = pygame.Rect(W // 2 - 620, 270, 600, 560)
        right = pygame.Rect(W // 2 + 20, 270, 600, 560)
        panel(surf, left, C.panel, C.border, radius=12)
        x, y = left.x + 28, left.y + 24
        draw_text(surf, "THE RUN", (x, y), 12, C.faint, "bold")
        y += 34
        st = self.eng.stats
        tasks = run.totals["tasks"] + st["tasks_done"]
        w = left.width - 56
        y = _row(surf, x, y, "Weeks completed", f"{run.week}", w)
        y = _row(surf, x, y, "Tasks completed", f"{tasks:,}", w)
        y = _row(surf, x, y, "Earthquakes reviewed", f"{run.totals['eq'] + st['eq_done']:,}", w)
        y = _row(surf, x, y, "SOP events", f"{run.totals['sops'] + st['sop_events']}", w)
        y = _row(surf, x, y, "Errors", f"{run.totals['errors'] + st['errors']}", w)
        y = _row(surf, x, y, "Tasks overdue this week", f"{st['overdue']}", w)
        y = _row(surf, x, y, "Analysts left standing", f"{len(run.active_ghas())}", w)
        draw_text(surf, "Tip: triage. SOP steps and big local events first; small events can wait.",
                  (left.centerx, left.bottom - 40), 13, C.faint, anchor="center")
        self.draw_xp(surf, right, mouse)
        self.button.draw(surf, mouse)


class VictoryScene(_RunEndScene):
    def __init__(self, app, run):
        super().__init__(app, run, True)

    def draw(self, surf):
        run = self.run
        mouse = pygame.mouse.get_pos()
        data = self.app.data
        draw_text(surf, "SEASON COMPLETE", (W // 2, 90), 58, C.good, "bold", anchor="midtop")
        draw_text(surf, f"{run.weeks_total} weeks survived with public trust at {run.rating:.0f}.", (W // 2, 170), 20,
                  C.dim, anchor="midtop")
        draw_text(surf, f"Score {run_score(run):,}", (W // 2, 210), 28, C.gold, "bold", anchor="midtop")
        left = pygame.Rect(W // 2 - 760, 280, 860, 600)
        right = pygame.Rect(W // 2 + 130, 280, 630, 600)
        panel(surf, left, C.panel, C.border, radius=12)
        x, y = left.x + 30, left.y + 24
        t = run.totals
        w = left.width - 60
        y = _row(surf, x, y, "Tasks completed", f"{t['tasks']:,}", w)
        y = _row(surf, x, y, "Completed on time", f"{t['ontime']:,}", w)
        y = _row(surf, x, y, "Earthquakes reviewed", f"{t['eq']:,}", w)
        y = _row(surf, x, y, "SOP events handled", f"{t['sops']}", w)
        y = _row(surf, x, y, "Errors", f"{t['errors']}", w)
        y += 10
        draw_text(surf, "THE TEAM", (x, y), 12, C.faint, "bold")
        y += 24
        team = sorted(run.active_ghas(), key=lambda g: -g.stats.get("tasks", 0))
        cols = 2
        for i, g in enumerate(team[:14]):
            cx = x + (i % cols) * 400
            cy = y + (i // cols) * 34
            tcol = team_color_of(data, run, g)
            draw_portrait(surf, (cx + 14, cy + 14), 14, g, data, run, team_color=tcol)
            draw_text(surf, g.name, (cx + 36, cy + 1), 13, C.text, "semibold", max_width=230)
            draw_text(surf, f"{group_label(data, group_of(run, g))} · {g.stats.get('tasks', 0)} tasks", (cx + 36, cy + 17),
                      11, tcol, max_width=230)
            best = max(g.skills, key=lambda k: g.skills[k])
            skill_pill(surf, (cx + 370, cy + 7), best, data, g.skills[best], size=10, anchor="topright")
        if len(team) > 14:
            draw_text(surf, f"…and {len(team) - 14} more", (x, y + 7 * 34), 12, C.faint)
        self.draw_xp(surf, right, mouse)
        self.button.draw(surf, mouse)
