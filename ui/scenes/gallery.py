"""Avatar gallery: preview random analysts built from the layered art in
assets/avatars/. Handy while drawing new pieces: save a PNG, press F5 here."""
from __future__ import annotations

import random

import pygame

from game.avatars import AVATAR_DIR, random_avatar
from game.models import GHA

from ..app import Scene
from ..avatars import get_bank
from ..theme import C, H, W, mix
from ..widgets import TOOLTIP, Button, draw_text, draw_wrapped, panel
from .common import draw_portrait

COLS, ROWS = 7, 3
GRID = pygame.Rect(392, 84, W - 392 - 16, 3 * 236 - 8)
STRIP = pygame.Rect(392, GRID.bottom + 12, W - 392 - 16, H - GRID.bottom - 12 - 16)
SIDE = pygame.Rect(16, 84, 360, H - 84 - 16)


class GalleryScene(Scene):
    def __init__(self, app, back=None):
        super().__init__(app)
        self.data = app.data
        self.back_to = back
        self.seed = random.randrange(1, 10**9)
        self.tired = False
        self.focus = 0
        self.ghas: list = []
        self.cells: list = []
        y = 16
        self.buttons = [
            Button((W - 16 - 120, y, 120, 36), "Back", self.back, "ghost", 14, tooltip="Esc"),
            Button((W - 16 - 120 - 10 - 150, y, 150, 36), "Reload art", self.app.reload_art, "secondary", 14,
                   tooltip="F5: re-read every PNG in assets/avatars/"),
            Button((W - 16 - 280 - 10 - 130, y, 130, 36), "Tired: off", self.toggle_tired, "secondary", 14,
                   tooltip="T: show the tired overlay (fatigue 70+)"),
            Button((W - 16 - 420 - 10 - 130, y, 130, 36), "Shuffle", self.shuffle, "primary", 14,
                   tooltip="Space: roll a new set of analysts"),
        ]
        self.shuffle(keep_seed=True)

    # --------------------------------------------------------------- actions
    def shuffle(self, keep_seed: bool = False):
        if not keep_seed:
            self.seed = random.randrange(1, 10**9)
        rng = random.Random(self.seed)
        names = random.Random(self.seed + 1)
        self.ghas = []
        for i in range(COLS * ROWS):
            gender = names.choice("fm")
            name = f"{names.choice(self.data.first_names_for(gender))} {names.choice(self.data.last_names)}"
            g = GHA(id=i + 1, name=name, color=names.choice(self.data.avatar_colors), skills={}, traits=[],
                    salary=0.0, gender=gender)
            g.avatar = random_avatar(rng, gender)
            g.fatigue = 90.0 if self.tired else 10.0
            self.ghas.append(g)

    def toggle_tired(self):
        self.tired = not self.tired
        for g in self.ghas:
            g.fatigue = 90.0 if self.tired else 10.0

    def on_art_reloaded(self):
        self.shuffle(keep_seed=True)

    def back(self):
        if self.back_to is not None:
            self.app.change(self.back_to)
        else:
            from .title import TitleScene
            self.app.change(TitleScene(self.app))

    def handle(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.back()
            elif event.key == pygame.K_SPACE:
                self.shuffle()
            elif event.key == pygame.K_t:
                self.toggle_tired()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for b in self.buttons:
                if b.handle(event):
                    return
            for rect, i in self.cells:
                if rect.collidepoint(event.pos):
                    self.focus = i

    # ------------------------------------------------------------------- draw
    def _team_for(self, i: int):
        keys = self.data.team_keys + ["bench"]
        return keys[i % len(keys)]

    def draw(self, surf):
        mouse = pygame.mouse.get_pos()
        bank = get_bank()
        pygame.draw.rect(surf, C.bg2, (0, 0, W, 68))
        pygame.draw.line(surf, C.border, (0, 68), (W, 68))
        draw_text(surf, "AVATAR GALLERY", (24, 12), 26, C.text, "bold")
        draw_text(surf, f"Pieces load from {AVATAR_DIR.parent.name}/{AVATAR_DIR.name}/ at start-up. Save a PNG there, "
                        f"then press F5 to see it.", (24, 44), 12, C.faint)
        self.buttons[2].label = f"Tired: {'on' if self.tired else 'off'}"
        for b in self.buttons:
            b.draw(surf, mouse)
        self._draw_side(surf, bank)
        if bank is None or not bank.has_art:
            panel(surf, GRID, C.panel, C.border, radius=10)
            draw_text(surf, "No avatar art found.", (GRID.centerx, GRID.centery - 20), 20, C.text, "bold",
                      anchor="center")
            draw_text(surf, "Add PNGs to the layer folders (at least one in skin/), or run "
                            "tools/make_placeholder_avatars.py.", (GRID.centerx, GRID.centery + 12), 14, C.dim,
                      anchor="center")
            return
        self._draw_grid(surf, bank, mouse)
        self._draw_strip(surf, bank)

    def _draw_grid(self, surf, bank, mouse):
        self.cells = []
        cw = (GRID.width - (COLS - 1) * 8) // COLS
        ch = (GRID.height - (ROWS - 1) * 8) // ROWS
        hovered = None
        for i, g in enumerate(self.ghas):
            col, row = i % COLS, i // COLS
            rect = pygame.Rect(GRID.x + col * (cw + 8), GRID.y + row * (ch + 8), cw, ch)
            self.cells.append((rect, i))
            team = self._team_for(i)
            tcol = self.data.team_color(team)
            hover = rect.collidepoint(mouse)
            selected = i == self.focus
            panel(surf, rect, mix(tcol, C.panel, 0.86 if not hover else 0.78),
                  C.accent if selected else (C.border2 if hover else C.border), radius=10, width=2 if selected else 1)
            img = bank.sprite(g, ch - 34, tcol, self.tired)
            if img is not None:
                surf.blit(img, img.get_rect(midbottom=(rect.centerx, rect.bottom - 26)))
            draw_text(surf, g.name, (rect.centerx, rect.bottom - 20), 12, C.text, "semibold", anchor="midtop",
                      max_width=rect.width - 12)
            if hover:
                hovered = (g, team)
        if hovered is not None:
            TOOLTIP.set(self._piece_lines(*hovered, bank), 320)

    def _piece_lines(self, g, team, bank) -> list:
        lines = [(g.name, C.text, 14, "bold"), ("Click to preview in every team colour.", C.faint, 11)]
        for layer, file, tint, _cond in bank._parts(g, self.data.team_color(team)):
            tint_txt = f"  (tint {tint[0]}, {tint[1]}, {tint[2]})" if tint else ""
            lines.append((f"{layer}: {file}{tint_txt}", C.dim, 12))
        for layer in bank.layers:
            if g.avatar.get(layer["name"], "missing") is None:
                lines.append((f"{layer['name']}: none", C.faint, 12))
        return lines

    def _draw_strip(self, surf, bank):
        panel(surf, STRIP, C.panel, C.border, radius=10)
        g = self.ghas[self.focus] if self.ghas else None
        if g is None:
            return
        draw_text(surf, f"{g.name.upper()} IN EVERY TEAM COLOUR", (STRIP.x + 16, STRIP.y + 12), 12, C.faint, "bold")
        keys = self.data.team_keys + ["bench", "leave"]
        slot_w = (STRIP.width - 32) // len(keys)
        radius = min(64, (STRIP.height - 70) // 2)
        for k, key in enumerate(keys):
            cx = STRIP.x + 16 + slot_w * k + slot_w // 2
            cy = STRIP.y + 38 + radius
            col = self.data.team_color(key)
            draw_portrait(surf, (cx, cy), radius, g, self.data, team_color=col)
            label = {"bench": "Bench", "leave": "On leave"}.get(key, f"{self.data.team_name(key)} team")
            draw_text(surf, label, (cx, cy + radius + 6), 12, col, "semibold", anchor="midtop")

    def _draw_side(self, surf, bank):
        panel(surf, SIDE, C.panel, C.border, radius=10)
        x, y = SIDE.x + 16, SIDE.y + 14
        draw_text(surf, "LAYERS (BACK TO FRONT)", (x, y), 12, C.faint, "bold")
        y += 24
        if bank is None:
            return
        counts = bank.counts()
        for layer in bank.layers:
            name = layer["name"]
            n = counts.get(name, 0)
            col = C.text if n else (C.bad if layer.get("required") else C.faint)
            draw_text(surf, f"{name}/", (x, y), 14, col, "bold")
            draw_text(surf, f"{n} piece{'s' if n != 1 else ''}", (SIDE.right - 16, y + 1), 12,
                      C.dim if n else C.faint, anchor="topright")
            bits = []
            tint = layer.get("tint")
            if tint == "team":
                bits.append("tinted by team colour")
            elif tint:
                bits.append(f"tinted from '{tint}'")
            if layer.get("required"):
                bits.append("required")
            cn = layer.get("chance_none")
            if isinstance(cn, dict):
                bits.append("none: " + ", ".join(f"{k} {v * 100:.0f}%" for k, v in cn.items()))
            elif cn:
                bits.append(f"{cn * 100:.0f}% have none")
            draw_text(surf, " · ".join(bits) or "drawn as is", (x, y + 19), 11, C.faint, max_width=SIDE.width - 32)
            y += 44
        if bank.overlays:
            draw_text(surf, f"overlays: {', '.join(sorted(bank.overlays))}", (x, y), 12, C.dim)
            y += 22
        y += 8
        pygame.draw.line(surf, C.border, (x, y), (SIDE.right - 16, y))
        y += 12
        draw_text(surf, "TIPS", (x, y), 12, C.faint, "bold")
        y += 20
        canvas = f"{bank.canvas[0]}×{bank.canvas[1]}"
        tips = (f"Every piece is a {canvas} PNG with transparency, drawn in the same frame so the layers line up. "
                "Draw tinted pieces in greyscale (white = full colour). Put _fixed in a file name to keep its own "
                "colours. A piece can have a back half called <name>_back.png that goes behind everything (long "
                "hair, ponytails). Layer order, tints and palettes live in avatar_config.json.")
        y += draw_wrapped(surf, tips, (x, y, SIDE.width - 32, 300), 12, C.dim) + 10
        if bank.errors:
            draw_text(surf, f"{len(bank.errors)} FILE(S) COULDN'T LOAD", (x, y), 12, C.bad, "bold")
            y += 20
            for err in bank.errors[:6]:
                y += draw_wrapped(surf, err, (x, y, SIDE.width - 32, 60), 11, C.bad, max_lines=2) + 2
