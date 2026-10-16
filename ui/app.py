"""Window, main loop and scene switching."""
from __future__ import annotations

import json
import os
import threading
import traceback

import pygame

from game.catalog import load_catalog
from game.data import ROOT, get_data

from .theme import C, H, W
from .widgets import TOOLTIP


class Scene:
    def __init__(self, app):
        self.app = app

    def on_enter(self):
        pass

    def handle(self, event):
        pass

    def update(self, dt: float):
        pass

    def draw(self, surf):
        pass


SETTINGS_FILE = ROOT / "settings.json"
RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1080), (2560, 1440), (3440, 1440), (3840, 2160)]


def load_settings(config: dict) -> dict:
    """Player display settings (settings.json next to main.py), falling back to config.json."""
    out = {"fullscreen": bool(config.get("display", {}).get("start_fullscreen", True)),
           "resolution": [W, H], "smooth": True}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            out.update(json.load(fh))
    except (OSError, ValueError):
        pass
    return out


class App:
    def __init__(self, headless: bool = False):
        pygame.display.init()
        pygame.font.init()
        self.data = get_data()
        self.headless = headless
        self.settings = load_settings(self.data.config)
        self.smooth_at_start = self.settings.get("smooth", True)
        if headless:
            self.screen = pygame.display.set_mode((W, H))
        else:
            self.apply_display(first=True)
        pygame.display.set_caption("Seismic Shift")
        pygame.key.set_repeat(350, 40)
        self.clock = pygame.time.Clock()
        from .avatars import init_bank
        from .icons import init_icons
        from .richtext import init_rich
        from .webcams import init_webcams
        self.avatars = init_bank()
        self.icons = init_icons(self.data)
        if not headless:
            from game.art_check import summary_lines
            print("\n".join(summary_lines(self.data)))
        self.webcams = init_webcams()
        self.rich = init_rich(self.data)
        self.profile = None             # the centre (save slot) being played
        self.toast_text = ""
        self.toast_time = 0.0
        self.catalog = None
        self.catalog_error: str | None = None
        self.catalog_status = "Loading catalogue…"
        self.running = True
        self._loader = threading.Thread(target=self._load_catalog, daemon=True)
        self._loader.start()
        from .scenes.title import TitleScene
        self.scene: Scene = TitleScene(self)
        self.scene.on_enter()

    # ------------------------------------------------------------- display
    def apply_display(self, first: bool = False):
        """Create the window (first=True) or adjust it to self.settings. The game always
        draws at 1920x1080 and SDL scales it to the window, with black bars if the shape
        differs. The window is only ever created once: calling set_mode again on a
        scaled window can crash SDL on Windows, so later changes go through the window."""
        st = self.settings
        if first:
            # SDL reads this when it creates the scaled texture: 1 = smooth, 0 = sharp pixels
            os.environ["SDL_RENDER_SCALE_QUALITY"] = "1" if st.get("smooth", True) else "0"
            flags = pygame.SCALED | pygame.RESIZABLE
            if st.get("fullscreen"):
                flags |= pygame.FULLSCREEN
            self.screen = pygame.display.set_mode((W, H), flags)
            if st.get("fullscreen"):
                return
        try:
            is_full = pygame.display.is_fullscreen() if hasattr(pygame.display, "is_fullscreen") else False
            if bool(st.get("fullscreen")) != bool(is_full):
                pygame.display.toggle_fullscreen()
            if st.get("fullscreen") or not hasattr(pygame, "Window"):
                return
            w, h = st.get("resolution", [W, H])
            desk = pygame.display.get_desktop_sizes()[0]
            if w > desk[0] or h > desk[1]:              # never bigger than the monitor
                k = min(desk[0] / w, desk[1] / h) * 0.95
                w, h = int(w * k), int(h * k)
            win = pygame.Window.from_display_module()
            win.size = (w, h)
            win.position = pygame.WINDOWPOS_CENTERED
        except Exception:  # resizing is a nicety; the game keeps running at its current size
            traceback.print_exc()

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.settings, fh, indent=2)
        except OSError:
            pass

    def set_display(self, **changes):
        self.settings.update(changes)
        self.save_settings()
        if not self.headless:
            self.apply_display()

    def _set_status(self, text: str):
        self.catalog_status = text

    def _load_catalog(self):
        try:
            self.catalog = load_catalog(self.data, progress=self._set_status)
            self.catalog_status = self.catalog.summary()
        except Exception as exc:  # show the problem on the title screen instead of crashing
            traceback.print_exc()
            self.catalog_error = f"Couldn't load the catalogue: {exc}"
            self.catalog_status = self.catalog_error

    def wait_for_catalog(self, timeout: float = 30.0):
        self._loader.join(timeout)

    def change(self, scene: Scene):
        self.scene = scene
        scene.on_enter()

    def frame(self, dt: float, events: list):
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self.set_display(fullscreen=not self.settings.get("fullscreen"))
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F5:
                self.reload_art()
            else:
                self.scene.handle(event)
        TOOLTIP.clear()
        self.scene.update(dt)
        self.screen.fill(C.bg)
        self.scene.draw(self.screen)
        TOOLTIP.draw(self.screen, pygame.mouse.get_pos())
        if self.toast_time > 0:
            self.toast_time -= dt
            from .widgets import pill
            pill(self.screen, self.toast_text, (16, H - 16), C.bg, C.accent, size=13, anchor="bottomleft",
                 pad_x=12, pad_y=6)

    def save(self) -> bool:
        """Save the current centre (and its run in progress) to its slot."""
        if self.profile is None:
            return False
        from game import save
        from game.profile import now_stamp
        self.profile.last_played = now_stamp()
        return save.save_profile(self.profile)

    def reload_art(self):
        """F5: reload avatar pieces, item icons and webcam images from assets/."""
        self.avatars.reload()
        self.icons.reload()
        self.webcams.reload()
        total = sum(self.avatars.counts().values())
        icons = sum(found for found, _ in self.icons.counts().values())
        errors = len(self.avatars.errors) + len(self.icons.errors) + len(self.webcams.errors)
        self.toast_text = f"Reloaded art: {total} avatar pieces, {icons} item icons" + (
            f", {errors} errors" if errors else "")
        self.toast_time = 2.5
        hook = getattr(self.scene, "on_art_reloaded", None)
        if hook is not None:
            hook()

    def run(self):
        while self.running:
            dt = min(0.1, self.clock.tick(60) / 1000.0)
            self.frame(dt, pygame.event.get())
            pygame.display.flip()
        pygame.quit()
