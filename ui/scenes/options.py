"""Options: window size, fullscreen and scaling. Saved to settings.json."""
from __future__ import annotations

import pygame

from ..app import RESOLUTIONS, Scene
from ..theme import C, W
from ..widgets import Button, draw_text, panel


class OptionsScene(Scene):
    def __init__(self, app, back_to=None):
        super().__init__(app)
        self.back_to = back_to
        self.buttons: list = []

    def on_enter(self):
        self._build()

    def _build(self):
        st = self.app.settings
        cx = W // 2
        self.buttons = []
        y = 300
        current = tuple(st.get("resolution", (1920, 1080)))
        for i, (w, h) in enumerate(RESOLUTIONS):
            col, row = i % 2, i // 2
            label = f"{w} × {h}" + ("  (ultrawide)" if w / h > 2 else "")
            b = Button((cx - 330 + col * 340, y + row * 58, 320, 48), label,
                       lambda r=(w, h): self._resolution(r), "secondary", 16)
            b.selected = current == (w, h) and not st.get("fullscreen")
            self.buttons.append(b)
        y += ((len(RESOLUTIONS) + 1) // 2) * 58 + 30
        fs = st.get("fullscreen")
        self.buttons.append(Button((cx - 330, y, 320, 48), f"Fullscreen: {'on' if fs else 'off'}", self._fullscreen,
                                   "good" if fs else "secondary", 16,
                                   tooltip="Fills the whole monitor (F11 also toggles it)."))
        sm = st.get("smooth", True)
        self.buttons.append(Button((cx + 10, y, 320, 48), f"Smooth scaling: {'on' if sm else 'off'}" + ("" if sm == self.app.smooth_at_start else " (on restart)"), self._smooth,
                                   "good" if sm else "secondary", 16,
                                   tooltip=[("Smooth: softer text and art when the window isn't 1920 × 1080.", C.text, 13),
                                            ("Off: sharp, blocky pixels.", C.dim, 12),
                                            ("Takes effect next time you start the game.", C.warn, 12)]))
        self.buttons.append(Button((cx - 160, y + 90, 320, 50), "Back", self._back, "primary", 17))

    def _resolution(self, res):
        self.app.set_display(resolution=list(res), fullscreen=False)
        self._build()

    def _fullscreen(self):
        self.app.set_display(fullscreen=not self.app.settings.get("fullscreen"))
        self._build()

    def _smooth(self):
        self.app.set_display(smooth=not self.app.settings.get("smooth", True))
        self._build()

    def _back(self):
        if self.back_to is not None:
            self.app.change(self.back_to)
        else:
            from .title import TitleScene
            self.app.change(TitleScene(self.app))

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
            return
        for b in self.buttons:
            if b.handle(event):
                return

    def update(self, dt):
        self._build()        # picks up F11 changes

    def draw(self, surf):
        mouse = pygame.mouse.get_pos()
        rect = pygame.Rect(0, 0, 760, 580)
        rect.center = (W // 2, 490)
        panel(surf, rect, C.panel, C.border2, radius=14)
        draw_text(surf, "Options", (W // 2, rect.y + 28), 30, C.text, "bold", anchor="midtop")
        draw_text(surf, "WINDOW SIZE", (W // 2 - 330, 272), 12, C.faint, "bold")
        for b in self.buttons:
            b.draw(surf, mouse)
        draw_text(surf, "The game is drawn at 1920 × 1080 and scaled to fit; other shapes (like ultrawide) get "
                        "black bars at the sides.", (W // 2, rect.bottom - 34), 12, C.faint, anchor="midtop",
                  max_width=rect.width - 40)
