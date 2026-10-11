"""Team tab: full details for every analyst."""
from __future__ import annotations

import pygame

from game import shop
from game.util import fmt_money

from ..theme import C, H, W, mix
from ..widgets import TOOLTIP, Button, bar, draw_text, panel, pill, pips
from .layout import CONTENT_Y
from .common import draw_portrait, fatigue_color, group_label, group_of, team_color_of, trait_colour, trait_lines

CARD_W = 620
CARD_H = 206
GAP = 12


class TeamTab:
    def __init__(self, scene):
        self.scene = scene
        self.data = scene.data
        self.buttons: list = []
        self.confirm: int | None = None
        self.scroll = 0

    @property
    def run(self):
        return self.scene.run

    def hint(self) -> str:
        return "Analysts gain XP in the skills they use. Skills level up during shifts."

    def cancel(self) -> bool:
        if self.confirm is not None:
            self.confirm = None
            return True
        return False

    def update(self, dt):
        pass

    def handle(self, event):
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y * 60)
            return
        for b in self.buttons:
            if b.handle(event):
                return

    def _let_go(self, gid):
        if self.confirm != gid:
            self.confirm = gid
            return
        ok, msg = shop.let_go(self.data, self.run, gid)
        self.scene.flash(msg, C.good if ok else C.bad)
        self.confirm = None

    def draw(self, surf, mouse):
        run, data = self.run, self.data
        self.buttons = []
        order = {key: i for i, key in enumerate(data.team_keys + ["bench", "leave"])}
        ghas = sorted(run.active_ghas(), key=lambda g: (order.get(group_of(run, g), 99), g.name))
        area = pygame.Rect(16, CONTENT_Y, W - 32, H - CONTENT_Y - 12)
        rows = (len(ghas) + 2) // 3
        max_scroll = max(0, rows * (CARD_H + GAP) - area.height)
        self.scroll = min(self.scroll, max_scroll)
        surf.set_clip(area)
        for i, g in enumerate(ghas):
            col, row = i % 3, i // 3
            rect = pygame.Rect(16 + col * (CARD_W + GAP), CONTENT_Y + row * (CARD_H + GAP) - self.scroll, CARD_W, CARD_H)
            if rect.bottom < area.top or rect.top > area.bottom:
                continue
            self._card(surf, rect, g, mouse)
        surf.set_clip(None)
        for b in self.buttons:
            b.draw(surf, mouse)
        if max_scroll:
            draw_text(surf, "Scroll for more", (W - 20, H - 14), 11, C.faint, anchor="bottomright")

    def _card(self, surf, rect, g, mouse):
        run, data = self.run, self.data
        tcol = team_color_of(data, run, g)
        panel(surf, rect, C.panel, C.border, radius=10)
        pygame.draw.rect(surf, tcol, (rect.x, rect.y + 10, 4, rect.height - 20), border_radius=2)
        rad = 56                                    # big portrait down the left of the card
        draw_portrait(surf, (rect.x + 14 + rad, rect.y + 12 + rad), rad, g, data, run, team_color=tcol)
        tx = rect.x + 28 + 2 * rad
        draw_text(surf, g.name, (tx, rect.y + 12), 17, C.text, "bold", max_width=rect.right - tx - 12)
        label = group_label(data, group_of(run, g))
        r = pill(surf, label, (tx, rect.y + 37), C.bg, tcol, size=10)
        sub = f"{g.stats.get('archetype', 'Analyst')} · {fmt_money(g.salary)}/wk"
        if g.id in run.away_week:
            sub += " · away this week"
        draw_text(surf, sub, (r.right + 8, rect.y + 37), 12, C.dim, max_width=rect.right - r.right - 24)
        sm = data.config["skill_model"]
        col_w = (rect.right - 12 - tx) // 2
        for j, k in enumerate(data.skill_keys):
            col, row = j // 3, j % 3
            sx, sy = tx + col * col_w, rect.y + 66 + row * 22
            lvl = g.skills.get(k, 1)
            sk_col = data.skill_by_key[k]["color"]
            draw_text(surf, data.skill_by_key[k]["name"], (sx, sy), 12, sk_col, "semibold")
            pips(surf, (sx + 76, sy + 3), lvl, sm["max_level"], sk_col, 9, 3, off=mix(sk_col, C.panel, 0.82))
            bar_x, bar_w = sx + 142, max(30, col_w - 152)
            if lvl < sm["max_level"]:
                need = sm["xp_to_next"][min(lvl - 1, len(sm["xp_to_next"]) - 1)]
                bar(surf, (bar_x, sy + 6, bar_w, 4), g.xp.get(k, 0.0) / need, mix(sk_col, C.panel, 0.45))
            else:
                draw_text(surf, "MAX", (bar_x, sy), 10, C.good, "bold")
        y = rect.y + 146
        draw_text(surf, "Fatigue", (rect.x + 18, y), 12, C.dim)
        bar(surf, (rect.x + 90, y + 4, 180, 7), g.fatigue / 100.0, fatigue_color(g.fatigue))
        draw_text(surf, f"{g.fatigue:.0f}", (rect.x + 278, y), 12, C.dim)
        draw_text(surf, "Long-term", (rect.x + 318, y), 12, C.dim)
        bar(surf, (rect.x + 390, y + 4, 180, 7), g.ltf / 100.0, fatigue_color(g.ltf))
        draw_text(surf, f"{g.ltf:.0f}", (rect.x + 578, y), 12, C.dim)
        tx, ty = rect.x + 18, rect.y + 172
        for tid in g.traits:
            t = data.traits[tid]
            tr = pill(surf, t["name"], (tx, ty), C.bg, trait_colour(data, tid), size=10)
            if tr.collidepoint(mouse):
                TOOLTIP.set(trait_lines(tid, data), 260)
            tx = tr.right + 5
        st = g.stats
        draw_text(surf, f"{st.get('tasks', 0)} tasks · {st.get('errors', 0)} errors · {st.get('shifts', 0)} shifts",
                  (rect.right - 130, rect.y + 174), 11, C.faint, anchor="topright")
        confirm = self.confirm == g.id
        self.buttons.append(Button((rect.right - 118, rect.y + 168, 104, 26), "Confirm?" if confirm else "Let go",
                                   lambda gid=g.id: self._let_go(gid), "danger" if confirm else "ghost", 12,
                                   tooltip="Removes them from the team for good (no more salary)."))
