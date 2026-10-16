"""Roster tab: drag analysts into teams; the week grid follows the team rotation
and individual cells can be toggled for one-off changes."""
from __future__ import annotations

import pygame

from game.run import desk_count, roster_issues, rotation_grid, team_shifts
from game.util import DAY_NAMES

from ..richtext import get_rich
from ..theme import C, W, mix, render
from ..widgets import TIP_BG, TOOLTIP, Button, alpha_rect, draw_text, panel, warn_icon
from .common import CHIP_H, draw_gha_chip, draw_portrait, skill_rows, team_fill
from .layout import CONTENT_Y

Y0 = CONTENT_Y
BOX_W, BOX_H = 340, 220
GRID_X = 16 + 2 * BOX_W + 8 + 24
LABEL_W = 140
CHIP_GAP = 4
HEAD_H = 40              # header band of a team box; analyst rows start below it


def shift_hours(data, sh) -> tuple:
    start = (data.config["time"]["day_start_hour"] + sh["start_offset_hours"]) % 24
    return start, (start + sh["hours"]) % 24


def shift_legend(data) -> str:
    """'M 0600-1400 · L 1400-2200 · N 2200-0600'"""
    parts = []
    for sh in data.shifts:
        h0, h1 = shift_hours(data, sh)
        parts.append(f"{sh['name'][0]} {h0:02d}00-{h1:02d}00")
    return " · ".join(parts)


class RosterTab:
    def __init__(self, scene):
        self.scene = scene
        self.data = scene.data
        self.press = None
        self.drag = None
        self.chip_rects: list = []
        self.cell_rects: list = []
        self.group_rects: dict = {}
        self.buttons = [
            Button((GRID_X, Y0 + 432, 210, 34), "Reset to rotation", self.reset, "secondary", 13,
                   tooltip=[("Put every team back on its rotation for this week.", C.text, 13),
                            ("Each team works 2 mornings, 2 lates, 2 nights, then has 4 days off.", C.dim, 12)]),
            Button((GRID_X + 220, Y0 + 432, 130, 34), "Clear grid", self.clear, "ghost", 13),
        ]
        groups = list(self.data.team_keys) + ["bench"]
        for i, key in enumerate(groups[:6]):
            col, row = i % 2, i // 2
            self.group_rects[key] = pygame.Rect(16 + col * (BOX_W + 8), Y0 + row * (BOX_H + 6), BOX_W, BOX_H)
        self.group_rects["leave"] = pygame.Rect(16, Y0 + 3 * (BOX_H + 6), 2 * BOX_W + 8, 1070 - (Y0 + 3 * (BOX_H + 6)))

    @property
    def run(self):
        return self.scene.run

    def hint(self) -> str:
        return "Drag analysts between teams, the bench and leave. Click grid cells for one-off changes this week."

    def cancel(self) -> bool:
        if self.drag or self.press:
            self.drag = self.press = None
            return True
        return False

    def update(self, dt):
        pass

    # ---------------------------------------------------------------- actions
    def reset(self):
        self.run.roster.grid = rotation_grid(self.data, self.run.week)
        self.run.roster.custom = False
        self.scene.flash("Back on the standard rotation.", C.dim)

    def clear(self):
        for cells in self.run.roster.grid.values():
            for i in range(len(cells)):
                cells[i] = False
        self.run.roster.custom = True

    def members(self, group: str) -> list:
        run = self.run
        if group == "leave":
            ids = list(run.roster.leave)
        elif group == "bench":
            ids = [g.id for g in run.active_ghas() if run.roster.group_of(g.id) == "bench"]
        else:
            ids = list(run.roster.teams.get(group, []))
        return [run.gha(i) for i in ids if run.gha(i) is not None and run.gha(i).active]

    # ----------------------------------------------------------------- events
    def handle(self, event):
        for b in self.buttons:
            if b.handle(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, gid in self.chip_rects:
                if rect.collidepoint(event.pos):
                    self.press = (gid, event.pos, (event.pos[0] - rect.x, event.pos[1] - rect.y))
                    return
            for rect, team, slot in self.cell_rects:
                if rect.collidepoint(event.pos):
                    cells = self.run.roster.grid.setdefault(team, [False] * self.data.slots_per_week)
                    cells[slot] = not cells[slot]
                    self.run.roster.custom = True
                    return
        elif event.type == pygame.MOUSEMOTION and self.press and not self.drag:
            gid, start, off = self.press
            if abs(event.pos[0] - start[0]) + abs(event.pos[1] - start[1]) > 5:
                self.drag = {"gid": gid, "off": off}
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.drag:
                for group, rect in self.group_rects.items():
                    if rect.collidepoint(event.pos):
                        self.run.roster.move(self.drag["gid"], group)
                        break
            self.drag = None
            self.press = None

    # ------------------------------------------------------------------- draw
    def draw(self, surf, mouse):
        self.chip_rects = []
        self._draw_groups(surf, mouse)
        self._draw_grid(surf, mouse)
        for b in self.buttons:
            b.draw(surf, mouse)
        if self.run.roster.custom:
            draw_text(surf, "Custom roster this week. It goes back to the rotation next week.",
                      (GRID_X + 366, Y0 + 442), 12, C.warn)
        self._draw_issues(surf)
        if self.drag:
            g = self.run.gha(self.drag["gid"])
            if g is not None:
                rect = pygame.Rect(mouse[0] - self.drag["off"][0], mouse[1] - self.drag["off"][1], BOX_W - 20, CHIP_H)
                alpha_rect(surf, rect.inflate(8, 8), (0, 0, 0, 80), radius=10)
                draw_gha_chip(surf, rect, g, self.data, (-1, -1), run=self.run)

    def _draw_groups(self, surf, mouse):
        """Team, bench and leave boxes, each filled with its own colour."""
        run, data = self.run, self.data
        live = mouse if not self.drag else (-1, -1)
        for group, rect in self.group_rects.items():
            target = self.drag is not None and rect.collidepoint(mouse)
            col = data.team_color(group)
            fill = team_fill(col, 0.2 if group != "leave" else 0.15)
            pygame.draw.rect(surf, fill, rect, border_radius=10)
            if target:
                pygame.draw.rect(surf, C.white, rect, 2, border_radius=10)
            head_col = mix(col, C.white, 0.3)
            sub_col = mix(C.text, fill, 0.42)
            members = self.members(group)
            if group in run.roster.teams:
                draw_text(surf, f"{data.team_name(group).upper()} TEAM", (rect.x + 14, rect.y + 13), 14, head_col, "bold")
                draw_text(surf, f"{len(members)} analyst{'s' if len(members) != 1 else ''}",
                          (rect.right - 14, rect.y + 15), 12, sub_col, anchor="topright")
                chip_w, cols, top, capacity = rect.width - 20, 1, rect.y + HEAD_H, 3
            elif group == "bench":
                draw_text(surf, "BENCH", (rect.x + 14, rect.y + 13), 14, head_col, "bold")
                chip_w, cols, top, capacity = rect.width - 20, 1, rect.y + HEAD_H, 3
            else:
                rec = data.config["long_term"]["leave_recovery"]
                draw_text(surf, "LEAVE", (rect.x + 14, rect.y + 11), 14, head_col, "bold")
                draw_text(surf, f"Away all week. Long-term fatigue -{rec} at the end of it.", (rect.x + 80, rect.y + 13),
                          12, sub_col)
                chip_w, cols, top, capacity = (rect.width - 20 - 12) // 3, 3, rect.y + 34, 3
            chips = []
            for i, g in enumerate(members[:capacity]):
                cx = rect.x + 10 + (i % cols) * (chip_w + 6)
                cy = top + (i // cols) * (CHIP_H + CHIP_GAP)
                chip = pygame.Rect(cx, cy, chip_w, CHIP_H)
                chips.append(chip)
                if self.drag and self.drag["gid"] == g.id:
                    pygame.draw.rect(surf, team_fill(col, 0.32), chip, 1, border_radius=8)
                    continue
                draw_gha_chip(surf, chip, g, data, live, away=g.id in run.away_week, wide=cols == 1, run=run)
                self.chip_rects.append((chip, g.id))
            if len(members) > capacity:
                draw_text(surf, f"+{len(members) - capacity} more", (rect.right - 12, rect.bottom - 5), 11, sub_col,
                          "semibold", anchor="bottomright")
            if not members:
                draw_text(surf, "Drop analysts here", (rect.centerx, top + 40), 12, sub_col, anchor="center")
            if (group in run.roster.teams and rect.collidepoint(live)
                    and not any(c.collidepoint(live) for c in chips)):
                TOOLTIP.set(self._team_tooltip(group, members), 330)

    def _team_tooltip(self, team: str, members: list) -> list:
        """Hovering a team box (not an analyst): its week and its average skills."""
        data, run = self.data, self.run
        n = len(members)
        how = "custom roster this week" if run.roster.custom else "standard rotation"
        lines = [(f"{data.team_name(team)} team", mix(data.team_color(team), C.white, 0.2), 14, "bold"),
                 (f"{n} analyst{'s' if n != 1 else ''} · {how}", C.dim, 12),
                 6, ("THIS WEEK", C.faint, 10, "bold"),
                 self._week_strip(team, 306),
                 (shift_legend(data), C.faint, 11),
                 6, ("AVERAGE SKILLS", C.faint, 10, "bold")]
        if members:
            avg = {k: sum(g.skills.get(k, 1) for g in members) / n for k in data.skill_keys}
            lines.append(skill_rows(data, avg, numbers=True))
        else:
            lines.append(("Nobody in this team yet.", C.warn, 12))
        return lines

    def _week_strip(self, team: str, width: int) -> pygame.Surface:
        """One cell per day with the shift letter(s) the team works, or 'off'."""
        data = self.data
        codes = team_shifts(data, self.run.roster.grid, team)
        by_letter = {sh["name"][0]: sh for sh in data.shifts}
        step = (width + 5) // 7
        out = pygame.Surface((7 * step, 38), pygame.SRCALPHA)
        for d, code in enumerate(codes):
            x = d * step
            day = render(DAY_NAMES[d][:2], 9, C.faint, "bold")
            out.blit(day, day.get_rect(midtop=(x + (step - 5) // 2, 1)))
            cell = pygame.Rect(x, 15, step - 5, 21)
            if code:
                scol = by_letter[code[0]]["color"] if code[0] in by_letter else C.text
                pygame.draw.rect(out, mix(scol, TIP_BG, 0.6), cell, border_radius=4)
                img = render(code, 11, scol, "bold")
            else:
                pygame.draw.rect(out, (32, 38, 50), cell, border_radius=4)
                img = render("off", 10, C.faint)
            out.blit(img, img.get_rect(center=cell.center))
        return out

    def _lineup(self, slot: int) -> list:
        run = self.run
        return [run.gha(gid) for gid in run.roster.lineup(slot)
                if run.gha(gid) and run.gha(gid).active and gid not in run.away_week and gid not in run.roster.leave]

    def _draw_grid(self, surf, mouse):
        run, data = self.run, self.data
        n_shifts = data.slots_per_day
        slots = data.slots_per_week
        gx, label_w = GRID_X, LABEL_W
        cell_w = (W - 16 - gx - label_w) // slots
        x0 = gx + label_w
        week = run.plan[run.week]
        self.cell_rects = []
        for d in range(7):
            rect = pygame.Rect(x0 + d * n_shifts * cell_w, Y0, n_shifts * cell_w - 3, 22)
            panel(surf, rect, C.panel2, None, radius=4)
            name = DAY_NAMES[d].upper() + ("  ?" if week.days[d].random_event_at is not None else "")
            draw_text(surf, name, rect.center, 12, C.sop if week.days[d].random_event_at is not None else C.text,
                      "bold", anchor="center")
            for s in range(n_shifts):
                sx = x0 + (d * n_shifts + s) * cell_w
                shift = data.shifts[s]
                draw_text(surf, shift["name"][0], (sx + cell_w // 2 - 1, Y0 + 33), 11, shift["color"], "bold",
                          anchor="center")
        live = mouse if not self.drag else (-1, -1)
        for r, team in enumerate(data.team_keys):
            y = Y0 + 46 + r * 38
            members = self.members(team)
            available = [g for g in members if g.id not in run.away_week]
            col = data.team_color(team)
            label = pygame.Rect(gx, y, label_w - 6, 34)
            panel(surf, label, mix(col, C.panel, 0.82), None, radius=6)
            pygame.draw.rect(surf, col, (label.x, label.y + 4, 3, label.height - 8), border_radius=2)
            draw_text(surf, data.team_name(team), (label.x + 10, label.y + 7), 13, col, "bold")
            for i, g in enumerate(members[:3]):
                draw_portrait(surf, (label.right - 14 - i * 22, label.centery), 11, g, data, run,
                              bg=mix(col, C.panel, 0.82))
            cells = run.roster.grid.get(team, [False] * slots)
            for s in range(slots):
                rect = pygame.Rect(x0 + s * cell_w, y, cell_w - 3, 34)
                on = s < len(cells) and cells[s]
                hover = rect.collidepoint(live)
                if on:
                    pygame.draw.rect(surf, mix(col, C.panel, 0.45), rect, border_radius=5)
                    pygame.draw.rect(surf, col, rect, 1, border_radius=5)
                    draw_text(surf, str(len(available)), rect.center, 12,
                              C.text if len(available) == len(members) and available else C.warn, "bold",
                              anchor="center")
                else:
                    pygame.draw.rect(surf, C.hover if hover else C.panel, rect, border_radius=5)
                if hover:
                    pygame.draw.rect(surf, C.border2, rect, 1, border_radius=5)
                    names = ", ".join(g.first_name for g in members) or "nobody"
                    day, sh = divmod(s, n_shifts)
                    shift = data.shifts[sh]
                    h0, h1 = shift_hours(data, shift)
                    TOOLTIP.set([(f"{data.team_name(team)} team · {DAY_NAMES[day]} {shift['name'].lower()} shift",
                                  col, 13, "bold"),
                                 (f"{h0:02d}00-{h1:02d}00", C.dim, 12),
                                 (f"Members: {names}", C.dim, 12), ("Click to toggle for this week", C.faint, 11)], 300)
                self.cell_rects.append((rect, team, s))
        y = Y0 + 46 + len(data.team_keys) * 38 + 10
        draw_text(surf, "SKILL COVERAGE", (gx, y), 11, C.faint, "bold")
        y += 18
        desks = desk_count(data, run)
        lineups = [self._lineup(s) for s in range(slots)]
        rows = [("On shift", None)] + [(sk["name"], sk["key"]) for sk in data.skills]
        for label_text, key in rows:
            if key is None:
                draw_text(surf, label_text, (gx + 6, y + 3), 12, C.text, "semibold")
            else:
                draw_text(surf, f"Best {label_text.lower()}", (gx + 6, y + 2), 12, data.skill_by_key[key]["color"])
            for s in range(slots):
                rect = pygame.Rect(x0 + s * cell_w, y, cell_w - 3, 20 if key is None else 17)
                lu = lineups[s]
                if key is None:
                    n = len(lu)
                    col = C.bad if n == 0 or n > desks else (C.warn if n == 1 else C.good)
                    pygame.draw.rect(surf, mix(col, C.panel, 0.65), rect, border_radius=4)
                    draw_text(surf, str(n), rect.center, 12, col, "bold", anchor="center")
                else:
                    best = max((g.skills.get(key, 1) for g in lu), default=0)
                    col = C.bad if best <= 1 else (C.warn if best == 2 else (C.dim if best == 3 else C.good))
                    pygame.draw.rect(surf, C.panel, rect, border_radius=4)
                    draw_text(surf, str(best) if lu else "-", rect.center, 11, col, "semibold", anchor="center")
            y += 22 if key is None else 19

    def _draw_issues(self, surf):
        issues = roster_issues(self.data, self.run)
        x, y = GRID_X, Y0 + 484
        draw_text(surf, "CHECKS", (x, y), 11, C.faint, "bold")
        y += 18
        if not issues:
            draw_text(surf, "No problems spotted. Good luck out there.", (x, y), 13, C.good)
            return
        order = {"error": 0, "warn": 1, "info": 2}
        issues = sorted(issues, key=lambda p: order[p[0]])
        shown = issues[:12]
        rt = get_rich()
        for lvl, text, _ in shown:
            col = {"error": C.bad, "warn": C.warn, "info": C.dim}[lvl]
            if lvl != "info":
                warn_icon(surf, (x + 7, y + 8), 11, col)
            if rt is not None:
                rt.draw_line(surf, text, (x + 20, y), 13, col, W - x - 40)
            else:
                draw_text(surf, text, (x + 20, y), 13, col, max_width=W - x - 40)
            y += 21
        if len(issues) > len(shown):
            draw_text(surf, f"…and {len(issues) - len(shown)} more", (x + 20, y), 12, C.faint)
