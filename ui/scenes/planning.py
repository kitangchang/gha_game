"""Between-week planning: roster, shop and team."""
from __future__ import annotations

import pygame

from game.forecast import alert_level, day_hazard, hazard_short, hazard_text
from game.modifiers import collect_specials
from game.profile import level_for_xp
from game.run import roster_issues, start_week, weekly_salaries
from game.util import DAY_NAMES, fmt_money

from ..app import Scene
from ..richtext import get_rich
from ..theme import C, H, W, mix
from ..widgets import TOOLTIP, Button, draw_text, panel, pill, warn_icon
from .boss_reward import BossReward
from .common import draw_tool_strip, trust_bar
from .help import HelpOverlay
from .layout import CONTENT_Y, HEADER_H, TABS_Y, TOOLBAR_H, WEEK_Y
from .roster_tab import RosterTab
from .shop_tab import ShopTab
from .team_tab import TeamTab


ALERT_COLOURS = {1: (240, 210, 70), 2: (245, 150, 60), 3: (236, 80, 70)}
ALERT_WORDS = {1: "Busier than usual", 2: "Heavy activity expected", 3: "Severe activity expected"}


def activity_label(p: float) -> str:
    if p < 0.25:
        return "Quiet"
    if p < 0.5:
        return "Normal"
    if p < 0.72:
        return "Busy"
    if p < 0.9:
        return "Very busy"
    return "Extreme"


class PlanningScene(Scene):
    def __init__(self, app, run):
        super().__init__(app)
        self.run = run
        self.data = app.data
        self.tab = "roster"
        self.help = HelpOverlay()
        self.message = ""
        self.message_tone = C.dim
        self.message_t = 0.0
        self.confirm_start = False
        self.tabs = {"roster": RosterTab(self), "shop": ShopTab(self), "team": TeamTab(self)}
        self.tab_buttons = []
        x = 16
        for key, label in (("roster", "Roster"), ("shop", "Shop"), ("team", "Team")):
            self.tab_buttons.append((key, Button((x, TABS_Y, 130, 36), label, lambda k=key: self.set_tab(k), "ghost",
                                                 15)))
            x += 138
        self.start_button = Button((W - 256, 13, 240, 46), "Start week  ▶", self.try_start, "primary", 17)
        self.help_button = Button((W - 360, 19, 90, 34), "Help", self.help.toggle, "ghost", 13)
        self.centre_button = Button((W - 500, 19, 130, 34), "Centre", self.to_centre, "ghost", 13,
                                    tooltip="Back to the centre (the run is saved at the start of the week).")
        # A boss reward left unclaimed (the game was closed on the summary screen).
        self.reward = BossReward(app, run, on_done=self._reward_done, can_close=False)
        self.reward.show()
        # The starting tool for a new run. "Back to planning" closes it; until a tool is picked (or
        # skipped) the Start week button reads "Choose starting tool" and reopens it.
        self.start_pick = BossReward(app, run, on_done=self._reward_done, can_close=True, flag="start_reward")
        if not self.reward.open:
            self.start_pick.show()

    def on_enter(self):
        self.app.save()

    def set_tab(self, key: str):
        self.tab = key
        self.confirm_start = False

    def _reward_done(self, message: str):
        self.flash(message, C.good if message.startswith("New") else C.dim)

    def flash(self, text: str, tone=C.dim):
        self.message = text
        self.message_tone = tone
        self.message_t = 4.0

    def to_centre(self):
        self.app.save()
        if self.app.profile is None:
            from .title import TitleScene
            self.app.change(TitleScene(self.app))
            return
        from .centre import CentreScene
        self.app.change(CentreScene(self.app))

    # ------------------------------------------------------------------ start
    def try_start(self):
        if self.start_pick.pending:
            self.start_pick.show()
            return
        issues = roster_issues(self.data, self.run)
        desk_errors = [t for lvl, t, code in issues if code == "desks"]
        if desk_errors:
            self.flash(desk_errors[0], C.bad)
            self.set_tab("roster")
            return
        unmanned = [t for lvl, t, code in issues if code == "unmanned"]
        if unmanned and not self.confirm_start:
            self.confirm_start = True
            self.flash(f"{unmanned[0]}. Click Start again to go anyway.", C.warn)
            return
        self.app.save()
        eng = start_week(self.data, self.run)
        from .shift import ShiftScene
        self.app.change(ShiftScene(self.app, self.run, eng))

    # ----------------------------------------------------------------- events
    def handle(self, event):
        if self.reward.handle(event) or self.start_pick.handle(event) or self.help.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.tabs[self.tab].cancel():
                return
            self.to_centre()
            return
        if self.start_button.handle(event) or self.help_button.handle(event) or self.centre_button.handle(event):
            return
        for _, b in self.tab_buttons:
            if b.handle(event):
                return
        self.tabs[self.tab].handle(event)

    def update(self, dt: float):
        self.message_t = max(0.0, self.message_t - dt)
        self.tabs[self.tab].update(dt)

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        mouse = pygame.mouse.get_pos()
        run = self.run
        pygame.draw.rect(surf, C.bg2, (0, 0, W, HEADER_H))
        pygame.draw.line(surf, C.border, (0, HEADER_H - 1), (W, HEADER_H - 1))
        draw_text(surf, f"WEEK {run.week + 1} OF {run.weeks_total}", (24, 10), 28, C.text, "bold")
        sub = f"Planning · seed {run.seed} · {run.catalog_label}"
        if self.app.profile is not None:
            sub = f"{self.app.profile.title} (level {level_for_xp(self.data, self.app.profile.xp)}) · " + sub
        draw_text(surf, sub, (24, 48), 12, C.faint, max_width=560)
        trust_bar(surf, (620, 38, 260, 14), run.rating)
        draw_text(surf, "BUDGET", (960, 16), 11, C.faint, "bold")
        draw_text(surf, fmt_money(run.budget), (960, 30), 22, C.gold if run.budget >= 0 else C.bad, "bold")
        draw_text(surf, f"Salaries {fmt_money(weekly_salaries(run))}/wk", (1080, 38), 12, C.dim)
        growth = self.data.config["difficulty"].get("expectation_growth_per_week", 0.0) * run.week
        if growth:
            draw_text(surf, f"Public expectations +{growth * 100:.0f}% (trust losses)", (1080, 18), 12, C.warn)
        if run.rating < 25:
            warn_icon(surf, (606, 44), 12)
        self.centre_button.draw(surf, mouse)
        self.help_button.draw(surf, mouse)
        if self.start_pick.pending:
            self.start_button.label, self.start_button.style = "Choose starting tool", "good"
        else:
            self.start_button.label, self.start_button.style = "Start week  ▶", "primary"
        self.start_button.draw(surf, mouse)
        draw_tool_strip(surf, run, self.data, mouse, HEADER_H, TOOLBAR_H)
        self._draw_week_strip(surf, mouse)
        for key, b in self.tab_buttons:
            b.selected = key == self.tab
            b.draw(surf, mouse)
        hint = self.tabs[self.tab].hint()
        if hint:
            draw_text(surf, hint, (446, TABS_Y + 9), 13, C.faint, max_width=W - 470)
        pygame.draw.line(surf, C.border, (16, CONTENT_Y - 8), (W - 16, CONTENT_Y - 8))
        self.tabs[self.tab].draw(surf, mouse)
        if self.message_t > 0 and self.message:
            rect = pygame.Rect(0, 0, 860, 42)
            rect.midbottom = (W // 2, H - 14)
            panel(surf, rect, C.panel3, self.message_tone, radius=8)
            draw_text(surf, self.message, rect.center, 14, self.message_tone, "semibold", anchor="center",
                      max_width=rect.width - 20)
        self.help.draw(surf)
        if self.reward.open:
            TOOLTIP.clear()
            self.reward.draw(surf, mouse)
        elif self.start_pick.open:
            TOOLTIP.clear()
            self.start_pick.draw(surf, mouse)

    def _draw_week_strip(self, surf, mouse):
        run, data = self.run, self.data
        week = run.plan[run.week]
        special = data.special_weeks.get(week.special) if week.special else None
        y = WEEK_Y
        forecast = collect_specials(data, run.relics).get("forecast", False)
        mean_p = sum(d.target for d in week.days) / len(week.days)
        label = f"Expected activity this week: {activity_label(mean_p)}"
        if special:
            panel(surf, (16, y, W - 32, 28), (52, 40, 70), C.sop, radius=6)
            hr = draw_text(surf, f"SPECIAL WEEK · {special['name'].upper()}", (28, y + 6), 13, C.sop, "bold")
            lr = draw_text(surf, label, (W - 28, y + 6), 13, C.dim, anchor="topright")
            rt = get_rich()
            dx, dw = hr.right + 18, lr.x - 24 - (hr.right + 18)
            if rt is not None:
                rt.draw_line(surf, special["desc"], (dx, y + 6), 13, C.text, dw)
            else:
                draw_text(surf, special["desc"], (dx, y + 6), 13, C.text, max_width=dw)
            y += 34
        else:
            draw_text(surf, label, (16, y + 4), 13, C.dim)
            y += 28
        gap = 10
        w = (W - 32 - gap * 6) // 7
        h = TABS_Y - 12 - y
        levels = data.config["difficulty"].get("alert_levels", [0.5, 0.75, 0.9])
        self.day_rects = []
        for i, day in enumerate(week.days):
            rect = pygame.Rect(16 + i * (w + gap), y, w, h)
            self.day_rects.append(rect)
            hover = rect.collidepoint(mouse)
            panel(surf, rect, C.panel2 if not hover else C.hover, C.border, radius=6)
            name = draw_text(surf, DAY_NAMES[i].upper(), (rect.x + 12, rect.y + 8), 15, C.text, "bold")
            draw_text(surf, f"Day {day.index + 1}", (name.right + 8, rect.y + 11), 11, C.faint)
            hz = day_hazard(day)
            alert = alert_level(day.percentile, levels)
            bx = rect.right - 10
            if day.random_event_at is not None:
                r = pill(surf, " ? ", (bx, rect.y + 8), C.bg, C.sop, size=12, anchor="topright")
                bx = r.x - 4
            if day.boss or alert:
                col = ALERT_COLOURS[3 if day.boss else alert]
                r = pill(surf, " ! ", (bx, rect.y + 8), C.bg, col, size=12, anchor="topright")
                bx = r.x - 4
            if getattr(day, "final", False):
                pill(surf, "FINAL", (bx, rect.y + 8), C.white, C.bad, size=10, anchor="topright")
            elif day.boss:
                pill(surf, "BOSS", (bx, rect.y + 8), C.white, mix(C.bad, C.panel, 0.25), size=10, anchor="topright")
            if forecast:
                frac = 0.1 + 0.9 * day.percentile
                pygame.draw.rect(surf, C.panel3, (rect.x + 12, rect.bottom - 14, rect.width - 24, 6), border_radius=3)
                col = C.good if day.percentile < 0.5 else C.warn if day.percentile < 0.85 else C.bad
                pygame.draw.rect(surf, col, (rect.x + 12, rect.bottom - 14, int((rect.width - 24) * frac), 6),
                                 border_radius=3)
                if day.boss or alert:
                    head, head_col = hazard_short(hz), ALERT_COLOURS[3 if day.boss else alert]
                    sub = f"{len(day.events)} quakes" + (f" · {hz['place']}" if hz["place"] and hz["kind"] != "busy"
                                                         else f" · max M{day.max_mag:.1f}")
                else:
                    head, head_col = f"{activity_label(day.percentile)} day", C.text
                    sub = f"{len(day.events)} quakes · max M{day.max_mag:.1f}"
                draw_text(surf, head, (rect.x + 12, rect.bottom - 52), 12, head_col, "semibold",
                          max_width=rect.width - 24)
                draw_text(surf, sub, (rect.x + 12, rect.bottom - 34), 12, C.dim, max_width=rect.width - 24)
            elif day.boss:
                draw_text(surf, hazard_text(hz, False), (rect.x + 12, rect.bottom - 32), 12,
                          mix(C.bad, C.text, 0.35), "semibold", max_width=rect.width - 24)
            elif alert:
                draw_text(surf, ALERT_WORDS[alert], (rect.x + 12, rect.bottom - 32), 12, ALERT_COLOURS[alert],
                          max_width=rect.width - 24)
            else:
                draw_text(surf, "Normal day", (rect.x + 12, rect.bottom - 32), 12, C.faint)
            if hover:
                on_duty = self._day_teams(i)
                lines = [(f"{DAY_NAMES[i]}, day {day.index + 1} of the run", C.text, 14, "bold")]
                for shift, teams in zip(data.shifts, on_duty):
                    names = " + ".join(f"{data.team_name(t)} team" for t in teams) or "nobody rostered"
                    lines.append((f"{shift['name']}: {names}", C.dim, 12))
                lines.append(6)
                if getattr(day, "final", False):
                    lines.append((f"Final boss day: {hazard_text(hz, forecast)}.", C.bad, 13, "bold"))
                elif day.boss:
                    lines.append((f"Boss day: {hazard_text(hz, forecast)}.", ALERT_COLOURS[3], 13, "bold"))
                    lines.append(("Survive the week to choose a rare or boss-only tool.", C.dim, 12))
                elif alert:
                    lines.append((ALERT_WORDS[alert] + ".", ALERT_COLOURS[alert], 13, "semibold"))
                    if forecast:
                        lines.append((f"Forecast: {hazard_text(hz, True)}", C.text, 12))
                if day.random_event_at is not None:
                    lines.append(("Something unexpected will happen today.", C.sop, 13))
                if forecast:
                    lines.append((f"Forecast activity: {activity_label(day.percentile)} "
                                  f"(busier than {day.percentile * 100:.0f}% of days)", C.dim, 12))
                else:
                    lines.append(("The Aftershock Forecast Model shows what each day holds.", C.faint, 11))
                TOOLTIP.set(lines, 340)

    def _day_teams(self, day: int) -> list:
        """Per shift of a day of this week, the teams rostered (from the roster grid)."""
        run, data = self.run, self.data
        n = data.slots_per_day
        out = []
        for s in range(n):
            slot = day * n + s
            out.append([key for key in data.team_keys
                        if slot < len(run.roster.grid.get(key, [])) and run.roster.grid[key][slot]
                        and run.roster.teams.get(key)])
        return out
