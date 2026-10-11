"""Title screen."""
from __future__ import annotations

import math

import pygame

from game import save

from ..app import Scene
from ..theme import C, H, W
from ..widgets import Button, draw_text, panel
from .help import HelpOverlay


class TitleScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.help = HelpOverlay()
        self.message = ""
        self.buttons: list = []
        self.last = None

    def on_enter(self):
        self.app.profile = None
        slot = save.last_slot()
        self.last = save.load_profile(slot) if slot is not None else None
        self._build_buttons()

    def _build_buttons(self):
        cx = W // 2
        y = 520
        self.buttons = []
        if self.last is not None and self.last.run is not None:
            run = self.last.run
            label = f"Continue · {self.last.title} · week {run.week + 1} of {run.weeks_total}"
            self.buttons.append(Button((cx - 260, y, 520, 56), label, self._continue, "primary", 17))
            y += 70
        self.buttons.append(Button((cx - 260, y, 520, 56), "Play", self._play,
                                   "secondary" if self.buttons else "primary", 18,
                                   tooltip="Choose a save slot: each one is a monitoring centre with its own level "
                                           "and unlocks."))
        y += 76
        self.buttons.append(Button((cx - 260, y, 255, 46), "How to play", self.help.toggle, "ghost", 15))
        self.buttons.append(Button((cx + 5, y, 255, 46), "Avatars", self._gallery, "ghost", 15,
                                   tooltip="Preview the analyst art in assets/avatars/"))
        self.buttons.append(Button((cx - 260, y + 56, 520, 46), "Quit", self._quit, "ghost", 15))

    def _gallery(self):
        from .gallery import GalleryScene
        self.app.change(GalleryScene(self.app))

    def _quit(self):
        self.app.running = False

    def _play(self):
        from .slots import SlotScene
        self.app.change(SlotScene(self.app))

    def _continue(self):
        from .centre import CentreScene
        self.app.profile = self.last
        scene = CentreScene(self.app)
        self.app.change(scene)
        scene.continue_run()

    def handle(self, event):
        if self.help.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.running = False
            return
        for b in self.buttons:
            if b.handle(event):
                return

    def update(self, dt: float):
        self.t += dt

    def _draw_traces(self, surf):
        rows = 10
        for r in range(rows):
            base = 110 + r * (H - 200) / (rows - 1)
            phase = r * 1.7
            pts = []
            burst_c = ((self.t * 0.6 + r * 0.37) % 3.0) * W / 2.2
            for i in range(0, W + 8, 8):
                x = i
                noise = (math.sin(x * 0.051 + phase + self.t * 3.1) * 1.6 + math.sin(x * 0.137 + phase * 2 + self.t * 5.3) * 1.1
                         + math.sin(x * 0.29 + self.t * 7.7 + r) * 0.7)
                d = abs(x - burst_c)
                amp = 20 * math.exp(-d / 70.0) * (0.6 + 0.4 * math.sin(r + 1.3)) if d < 450 else 0
                y = base + noise + amp * math.sin(x * 0.45 + self.t * 9)
                pts.append((x, y))
            col = (28, 40, 54) if r % 2 else (24, 34, 46)
            pygame.draw.aalines(surf, col, False, pts)

    def draw(self, surf):
        self._draw_traces(surf)
        cx = W // 2
        draw_text(surf, "SEISMIC SHIFT", (cx, 300), 92, C.text, "bold", anchor="center")
        draw_text(surf, self.app.data.config.get("subtitle", ""), (cx, 372), 22, C.dim, anchor="center")
        pygame.draw.line(surf, C.accent, (cx - 70, 410), (cx + 70, 410), 2)
        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            b.draw(surf, mouse)
        status_rect = pygame.Rect(cx - 480, H - 120, 960, 76)
        panel(surf, status_rect, C.panel, C.border, radius=10)
        col = C.bad if self.app.catalog_error else (C.dim if self.app.catalog else C.warn)
        draw_text(surf, "Catalogue: " + self.app.catalog_status, (status_rect.x + 18, status_rect.y + 16), 14, col,
                  max_width=status_rect.width - 36)
        hint = ("Using generated events. Drop archive.csv (eq_stats) or a GeoNet quakesearch CSV into "
                "data/catalog/ to play real days.") if (self.app.catalog and self.app.catalog.synthetic) else \
            "Each game day replays a real catalogue day, picked to ramp up the difficulty."
        draw_text(surf, hint, (status_rect.x + 18, status_rect.y + 44), 13, C.faint, max_width=status_rect.width - 36)
        draw_text(surf, "F11 fullscreen / window", (W - 20, H - 18), 11, C.faint, anchor="bottomright")
        if self.message:
            draw_text(surf, self.message, (cx, H - 146), 15, C.warn, anchor="center")
        self.help.draw(surf)
