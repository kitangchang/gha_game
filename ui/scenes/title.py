"""Title screen."""
from __future__ import annotations

import random
from collections import namedtuple

import pygame

from game import save

from ..app import Scene
from ..theme import C, H, W
from ..widgets import Button, draw_text, panel
from .help import HelpOverlay

BG_WINDOW = 90.0      # game minutes across the screen
BG_SPEED = 1.2        # game minutes per real second (a slow, calm scroll)
_BgQuake = namedtuple("_BgQuake", "uid t mag lat lon depth")


class TitleScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.help = HelpOverlay()
        self.message = ""
        self.buttons: list = []
        self.last = None
        self.bg_day = None              # background seismogram: a catalogue day replayed slowly
        self.bg_events: list = []
        self.bg_state: dict = {}
        self.bg_now = 0.0
        self.bg_end = 0.0

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
        self.buttons.append(Button((cx - 260, y + 56, 255, 46), "Options", self._options, "ghost", 15,
                                   tooltip="Window size, fullscreen and scaling"))
        self.buttons.append(Button((cx + 5, y + 56, 255, 46), "Quit", self._quit, "ghost", 15))

    def _gallery(self):
        from .gallery import GalleryScene
        self.app.change(GalleryScene(self.app))

    def _options(self):
        from .options import OptionsScene
        self.app.change(OptionsScene(self.app))

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
        self.bg_now += dt * BG_SPEED

    def _draw_traces(self, surf):
        """A real (or synthetic) catalogue day replayed as faint seismic traces behind the menu."""
        from .wall import draw_seismogram
        cat = self.app.catalog
        if cat is None or not cat.days:
            return
        if self.bg_day is None or self.bg_now > self.bg_end:
            self._pick_day(cat)
        area = pygame.Rect(0, 70, W, H - 140)
        draw_seismogram(surf, area, self.bg_events, self.bg_now, self.bg_state, line_col=(34, 52, 66),
                        label_col=None, base_col=None, window=BG_WINDOW, step=3,
                        noise_ref=6.0)

    def _pick_day(self, cat):
        """A random day with something worth seeing in it, started just before its biggest quake."""
        rng = random.Random()
        busy = [d for d in cat.days if d.max_mag >= 3.5] or cat.days
        day = rng.choice(busy)
        self.bg_day = day
        self.bg_events = [_BgQuake(i, e[0], e[1], e[2], e[3], e[4]) for i, e in enumerate(day.events)]
        biggest = max(day.events, key=lambda e: e[1])[0] if day.events else 0.0
        self.bg_now = max(BG_WINDOW * 0.2, biggest - BG_WINDOW * 0.15)
        self.bg_end = max(e[0] for e in day.events) + BG_WINDOW if day.events else BG_WINDOW
        self.bg_state = {}

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
