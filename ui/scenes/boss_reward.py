"""Choosing a tool: for surviving a boss day (opened from the week summary, or on
the planning screen if the game was closed before choosing), or the starting tool
at the beginning of a run."""
from __future__ import annotations

import pygame

from game.run import claim_boss_reward

from ..icons import get_icons
from ..theme import C, RARITY, W, mix
from ..widgets import Button, alpha_rect, draw_text, line_blocks, panel
from .common import relic_lines

CARD_W, CARD_H, CARD_GAP = 410, 500, 32
TOP = 260

# flag in run.flags -> (title, line 1, line 2, title colour key, back button label)
KINDS = {
    "boss_reward": ("BOSS DAY SURVIVED", "Choose one tool to keep for the rest of the run.",
                    "Boss tools only come from boss days. Many grow with your tags.", "boss", "Back to the summary"),
    "start_reward": ("CHOOSE A STARTING TOOL", "Pick one tool to start the run with. You keep it all season.",
                     "Many of these grow with your tags, so they can shape who you hire and what you buy.",
                     "accent", "Back to planning"),
}


class BossReward:
    """Modal overlay. handle() swallows every event while it is open."""

    def __init__(self, app, run, on_done=None, can_close: bool = True, flag: str = "boss_reward"):
        self.app, self.run, self.data = app, run, app.data
        self.on_done = on_done            # called with the result message
        self.can_close = can_close
        self.flag = flag
        self.title, self.line1, self.line2, colour_key, back_label = KINDS[flag]
        self.colour = RARITY["boss"] if colour_key == "boss" else C.accent
        self.open = False
        self.options = [rid for rid in run.flags.get(flag, []) if rid in self.data.relics]
        n = max(1, len(self.options))
        x0 = (W - (n * CARD_W + (n - 1) * CARD_GAP)) // 2
        self.cards = [pygame.Rect(x0 + i * (CARD_W + CARD_GAP), TOP, CARD_W, CARD_H)
                      for i in range(len(self.options))]
        by = TOP + CARD_H + 36
        skip = "Skip the reward" if flag == "boss_reward" else "Start without one"
        self.skip_button = Button((W // 2 - 120, by, 240, 44), skip, lambda: self.choose(None), "ghost",
                                  14, tooltip="Take nothing. The offer won't come back.")
        self.back_button = Button((W // 2 - 380, by, 240, 44), back_label, self.close, "ghost", 14,
                                  tooltip="Look around first (Esc). You can come back to this choice.")
        self._blocks: dict = {}

    @property
    def pending(self) -> bool:
        return bool(self.options) and self.flag in self.run.flags

    def show(self):
        if self.pending:
            self.open = True

    def close(self):
        if self.can_close:
            self.open = False

    def choose(self, rid):
        msg = claim_boss_reward(self.data, self.run, rid, self.flag)
        self.open = False
        self.app.save()
        if self.on_done:
            self.on_done(msg)

    # ------------------------------------------------------------------ input
    def handle(self, event) -> bool:
        if not self.open:
            return False
        if self.skip_button.handle(event):
            return True
        if self.can_close and self.back_button.handle(event):
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rid, rect in zip(self.options, self.cards):
                if rect.collidepoint(event.pos):
                    self.choose(rid)
                    return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
            elif pygame.K_1 <= event.key <= pygame.K_9:
                i = event.key - pygame.K_1
                if i < len(self.options):
                    self.choose(self.options[i])
        return True

    # ------------------------------------------------------------------- draw
    def _card_blocks(self, rid: str) -> list:
        """The tool's tooltip lines minus the name and rarity (drawn bigger on the card)."""
        if rid not in self._blocks:
            lines = []
            for item in relic_lines(rid, self.data, self.run, icon=False)[2:]:
                if isinstance(item, tuple) and len(item) > 2:          # a touch bigger than in a tooltip
                    item = (item[0], item[1], item[2] + 2) + tuple(item[3:])
                lines.append(item)
            self._blocks[rid] = line_blocks(lines, CARD_W - 52)
        return self._blocks[rid]

    def draw(self, surf, mouse):
        if not self.open:
            return
        alpha_rect(surf, surf.get_rect(), (6, 8, 12, 236))
        draw_text(surf, self.title, (W // 2, 120), 44, self.colour, "bold", anchor="midtop")
        draw_text(surf, self.line1, (W // 2, 184), 19, C.text, anchor="midtop")
        draw_text(surf, self.line2, (W // 2, 214), 14, C.dim, anchor="midtop")
        icons = get_icons()
        for i, (rid, rect) in enumerate(zip(self.options, self.cards)):
            r = self.data.relics[rid]
            col = RARITY.get(r["rarity"], C.text)
            hover = rect.collidepoint(mouse)
            alpha_rect(surf, rect.move(0, 6).inflate(6, 6), (0, 0, 0, 110), radius=14)
            panel(surf, rect, C.panel2 if hover else C.panel, col if hover else C.border2, radius=12,
                  width=2 if hover else 1)
            pygame.draw.rect(surf, col, (rect.x + 1, rect.y + 1, rect.width - 2, 8),
                             border_top_left_radius=12, border_top_right_radius=12)
            cx = rect.centerx
            glow = 58 if hover else 52
            pygame.draw.circle(surf, mix(col, C.panel, 0.82), (cx, rect.y + 86), glow)
            if icons is not None:
                icons.draw(surf, "tools", rid, (cx, rect.y + 86), 88, anchor="center")
            y = rect.y + 156
            name = draw_text(surf, r["name"], (cx, y), 22, col, "bold", anchor="midtop", max_width=CARD_W - 40)
            label = "Boss tool" if r["rarity"] == "boss" else f"{r['rarity'].title()} tool"
            if r.get("repeatable"):
                n = self.run.relics.count(rid)
                label += f" · repeatable" + (f" (you have {n})" if n else "")
            draw_text(surf, label, (cx, name.bottom + 4), 13, C.faint, anchor="midtop")
            y = name.bottom + 34
            for b in self._card_blocks(rid):
                if y + b.get_height() > rect.bottom - 44:
                    break
                bx = cx - b.get_width() // 2 if b.get_width() < CARD_W - 140 else rect.x + 26
                surf.blit(b, (bx, y))
                y += b.get_height() + 6
            hint = "Click to take it" if hover else f"Press {i + 1}"
            draw_text(surf, hint, (cx, rect.bottom - 30), 13, col if hover else C.faint, "semibold" if hover else
                      "regular", anchor="midtop")
        self.skip_button.draw(surf, mouse)
        if self.can_close:
            self.back_button.draw(surf, mouse)
