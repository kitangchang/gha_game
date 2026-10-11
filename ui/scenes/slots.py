"""Save slot picker: each slot is a monitoring centre with its own level,
unlocks, history and run in progress."""
from __future__ import annotations

import pygame

from game import save
from game.profile import new_profile, xp_progress

from ..app import Scene
from ..theme import C, H, W
from ..widgets import Button, bar, draw_text, panel, pill

CARD_W, CARD_H = 500, 430


class SlotScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.data = app.data
        self.n = int(self.data.config["centre"].get("slots", 3))
        self.profiles: list = []
        self.unreadable: list = []
        self.confirm_delete = None
        self.buttons: list = []

    def on_enter(self):
        self.app.profile = None
        self.refresh()

    def refresh(self):
        self.profiles = [save.load_profile(i + 1) for i in range(self.n)]
        self.unreadable = [save.slot_unreadable(i + 1) for i in range(self.n)]

    # --------------------------------------------------------------- actions
    def open_slot(self, slot: int):
        profile = self.profiles[slot - 1]
        if profile is None:
            profile = new_profile(slot)
            save.save_profile(profile)
        self.app.profile = profile
        from .centre import CentreScene
        self.app.change(CentreScene(self.app))

    def delete_slot(self, slot: int):
        if self.confirm_delete != slot:
            self.confirm_delete = slot
            return
        save.delete_slot(slot)
        self.confirm_delete = None
        self.refresh()

    def back(self):
        from .title import TitleScene
        self.app.change(TitleScene(self.app))

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.confirm_delete is not None:
                self.confirm_delete = None
            else:
                self.back()
            return
        for b in self.buttons:
            if b.handle(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.confirm_delete = None

    # ------------------------------------------------------------------ draw
    def draw(self, surf):
        mouse = pygame.mouse.get_pos()
        self.buttons = []
        draw_text(surf, "CHOOSE A CENTRE", (W // 2, 150), 40, C.text, "bold", anchor="center")
        draw_text(surf, "Each save slot is a monitoring centre. Analysts stay with their run, but centre XP, levels "
                        "and unlocked items carry over from run to run.", (W // 2, 200), 15, C.dim, anchor="center")
        total_w = self.n * CARD_W + (self.n - 1) * 30
        x = (W - total_w) // 2
        for i in range(self.n):
            rect = pygame.Rect(x + i * (CARD_W + 30), 270, CARD_W, CARD_H)
            self._card(surf, rect, i + 1, mouse)
        self.buttons.append(Button((W // 2 - 140, H - 140, 280, 48), "Back", self.back, "ghost", 15))
        for b in self.buttons:
            b.draw(surf, mouse)

    def _card(self, surf, rect, slot: int, mouse):
        profile = self.profiles[slot - 1]
        hover = rect.collidepoint(mouse)
        panel(surf, rect, C.panel2 if hover else C.panel, C.border2 if hover else C.border, radius=14)
        draw_text(surf, f"SLOT {slot}", (rect.x + 28, rect.y + 24), 12, C.faint, "bold")
        if profile is None:
            if self.unreadable[slot - 1]:
                draw_text(surf, "Old save", (rect.x + 28, rect.y + 50), 26, C.dim, "bold")
                draw_text(surf, "This slot was saved by an older version and can't be loaded.",
                          (rect.x + 28, rect.y + 96), 13, C.faint, max_width=rect.width - 56)
                self.buttons.append(Button((rect.x + 28, rect.bottom - 76, rect.width - 56, 48), "Clear and start fresh",
                                           lambda s=slot: self._clear_old(s), "secondary", 15))
                return
            draw_text(surf, "Empty", (rect.x + 28, rect.y + 50), 30, C.dim, "bold")
            draw_text(surf, "Start a new monitoring centre at level 1.", (rect.x + 28, rect.y + 100), 14, C.faint)
            self.buttons.append(Button((rect.x + 28, rect.bottom - 76, rect.width - 56, 48), "New centre",
                                       lambda s=slot: self.open_slot(s), "primary", 16))
            return
        data = self.data
        level, into, need = xp_progress(data, profile.xp)
        draw_text(surf, profile.title, (rect.x + 28, rect.y + 46), 26, C.text, "bold", max_width=rect.width - 140)
        pill(surf, f"LEVEL {level}", (rect.right - 28, rect.y + 50), C.bg, C.gold, size=13, anchor="topright",
             pad_x=10, pad_y=4)
        y = rect.y + 98
        if need:
            bar(surf, (rect.x + 28, y, rect.width - 56, 8), into / need, C.gold, C.panel3, radius=4)
            draw_text(surf, f"{into:.0f} / {need:.0f} XP to level {level + 1}", (rect.x + 28, y + 14), 12, C.dim)
        else:
            bar(surf, (rect.x + 28, y, rect.width - 56, 8), 1.0, C.gold, C.panel3, radius=4)
            draw_text(surf, f"Max level · {profile.xp:.0f} XP", (rect.x + 28, y + 14), 12, C.dim)
        y += 50
        stats = [("Runs", f"{profile.runs}"), ("Seasons won", f"{profile.wins}"),
                 ("Best score", f"{profile.best_score:,}"), ("Weeks survived", f"{profile.total_weeks}")]
        for k, (label, value) in enumerate(stats):
            sx = rect.x + 28 + (k % 2) * 220
            sy = y + (k // 2) * 44
            draw_text(surf, label, (sx, sy), 12, C.faint)
            draw_text(surf, value, (sx, sy + 16), 18, C.text, "semibold")
        y += 100
        run = profile.run
        if run is not None:
            draw_text(surf, f"Run in progress: week {run.week + 1} of {run.weeks_total}", (rect.x + 28, y), 14,
                      C.accent, "semibold")
            draw_text(surf, f"Trust {run.rating:.0f} · {len(run.active_ghas())} analysts", (rect.x + 28, y + 22),
                      13, C.dim)
        else:
            draw_text(surf, "No run in progress", (rect.x + 28, y), 14, C.faint)
        draw_text(surf, f"Last played {profile.last_played}", (rect.x + 28, y + 46), 11, C.faint)
        confirm = self.confirm_delete == slot
        self.buttons.append(Button((rect.x + 28, rect.bottom - 76, rect.width - 56 - 130, 48), "Open",
                                   lambda s=slot: self.open_slot(s), "primary", 16))
        self.buttons.append(Button((rect.right - 28 - 120, rect.bottom - 76, 120, 48),
                                   "Sure?" if confirm else "Delete", lambda s=slot: self.delete_slot(s),
                                   "danger" if confirm else "ghost", 14,
                                   tooltip="Deletes this centre: its level, unlocks, history and run."))

    def _clear_old(self, slot: int):
        save.delete_slot(slot)
        self.refresh()
