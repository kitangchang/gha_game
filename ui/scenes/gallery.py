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
BOTTOM = "__bottom"          # pick key for a palette's gradient (second) colour
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
            Button((W - 16 - 420 - 10 - 130, y, 130, 36), "Shuffle", self.shuffle_or_random, "primary", 14,
                   tooltip="Space: roll a new set of analysts"),
            Button((W - 16 - 560 - 10 - 190, y, 190, 36), "Build your own", self.toggle_builder, "secondary", 14,
                   tooltip="B: pick every piece yourself with the arrows"),
        ]
        # Builder mode: one avatar where you choose each piece.
        self.builder = False
        self.rows: list = []          # (kind, key) for each control row
        self.row = 0                  # selected row (up/down keys)
        self.pick: dict = {}          # layer -> index into its options; palette -> colour index; "team" -> index
        self.arrows: list = []        # (rect, row, delta) for clicks
        self.custom = GHA(id=9999, name="Custom analyst", color=(120, 160, 255), skills={}, traits=[], salary=0.0)
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
        for g in self.ghas + [self.custom]:
            g.fatigue = 90.0 if self.tired else 10.0

    def on_art_reloaded(self):
        self.shuffle(keep_seed=True)
        if self.builder:
            self._load_custom(self._custom_files())

    def shuffle_or_random(self):
        if self.builder:
            self.randomise_custom()
        else:
            self.shuffle()

    # ---------------------------------------------------------------- builder
    def toggle_builder(self):
        self.builder = not self.builder
        if self.builder:
            g = self.ghas[self.focus] if self.ghas else None
            self._load_custom(self._files_of(g) if g is not None else {})

    def _options(self, layer: dict) -> list:
        """Pieces to cycle through for a layer: every file (gender ignored), plus
        'none' for layers that can be left empty."""
        bank = get_bank()
        files = bank.files(layer["name"]) if bank else []
        if not files:
            return []
        if layer.get("required") or layer.get("condition"):
            return files
        return [None] + files

    def _palettes(self) -> list:
        bank = get_bank()
        out = []
        for layer in (bank.layers if bank else []):
            mode = layer.get("tint")
            if mode and mode != "team" and mode not in out:
                out.append(mode)
        return out

    def _palette(self, name: str) -> list:
        bank = get_bank()
        return (bank.manifest.get("palettes", {}).get(name) if bank else None) or [[255, 255, 255]]

    def _gradient_palettes(self) -> list:
        """Palettes that can fade to a second colour (avatar_config.json "gradients")."""
        bank = get_bank()
        return list((bank.manifest.get("gradients") or {}) if bank else [])

    def _build_rows(self):
        bank = get_bank()
        self.rows = [("layer", layer["name"]) for layer in (bank.layers if bank else []) if self._options(layer)]
        for p in self._palettes():
            self.rows.append(("palette", p))
            if p in self._gradient_palettes():
                self.rows.append(("fade", p + BOTTOM))
        self.rows.append(("team", "team"))
        self.row = min(self.row, len(self.rows) - 1)

    def _files_of(self, g) -> dict:
        """{layer: file or None, palette: colour} as an analyst is actually drawn."""
        bank = get_bank()
        out: dict = {}
        if bank is None or g is None:
            return out
        drawn = {}
        for name, file, tint, _cond in bank._parts(g, None):
            drawn[name] = (file, tint)
        for layer in bank.layers:
            name = layer["name"]
            file, tint = drawn.get(name, (None, None))
            out[name] = file
            mode = layer.get("tint")
            if mode and mode != "team" and tint and mode not in out:
                if isinstance(tint[0], (list, tuple)):
                    out[mode], out[mode + BOTTOM] = list(tint[0]), list(tint[1])
                else:
                    out[mode] = list(tint)
        return out

    def _custom_files(self) -> dict:
        out: dict = {}
        bank = get_bank()
        for layer in (bank.layers if bank else []):
            opts = self._options(layer)
            if opts:
                out[layer["name"]] = opts[self.pick.get(layer["name"], 0) % len(opts)]
        for p in self._palettes():
            pal = self._palette(p)
            out[p] = list(pal[self.pick.get(p, 0) % len(pal)])
            b = self.pick.get(p + BOTTOM, 0)
            if b:
                out[p + BOTTOM] = list(pal[(b - 1) % len(pal)])
        out["team"] = self.pick.get("team", 0)
        return out

    def _load_custom(self, files: dict):
        bank = get_bank()
        self._build_rows()
        self.pick = {"team": files.get("team", self.pick.get("team", 0))}
        for layer in (bank.layers if bank else []):
            opts = self._options(layer)
            want = files.get(layer["name"])
            self.pick[layer["name"]] = opts.index(want) if want in opts else 0
        for p in self._palettes():
            pal = [list(c) for c in self._palette(p)]
            want = files.get(p)
            self.pick[p] = pal.index(list(want)) if want and list(want) in pal else 0
            bottom = files.get(p + BOTTOM)
            self.pick[p + BOTTOM] = pal.index(list(bottom)) + 1 if bottom and list(bottom) in pal else 0
        self._apply_custom()

    def randomise_custom(self):
        rng = random.Random()
        for kind, key in self.rows:
            n = self._row_count(kind, key)
            if kind == "fade":
                chance = float((get_bank().manifest.get("gradients") or {}).get(key[:-len(BOTTOM)], 0.0))
                self.pick[key] = rng.randrange(1, n) if n > 1 and rng.random() < max(chance, 0.25) else 0
            elif n:
                self.pick[key] = rng.randrange(n)
        self._apply_custom()

    def _row_count(self, kind: str, key: str) -> int:
        bank = get_bank()
        if kind == "layer":
            layer = next((l for l in bank.layers if l["name"] == key), None) if bank else None
            return len(self._options(layer)) if layer else 0
        if kind == "palette":
            return len(self._palette(key))
        if kind == "fade":
            return len(self._palette(key[:-len(BOTTOM)])) + 1     # 0 = no fade
        return len(self._team_keys())

    def _team_keys(self) -> list:
        return self.data.team_keys + ["bench"]

    def step(self, row: int, delta: int):
        if not (0 <= row < len(self.rows)):
            return
        kind, key = self.rows[row]
        n = self._row_count(kind, key)
        if n:
            self.pick[key] = (self.pick.get(key, 0) + delta) % n
        self.row = row
        self._apply_custom()

    def _apply_custom(self):
        """Turn the picks into the custom analyst's avatar dict."""
        bank = get_bank()
        avatar = {}
        for layer in (bank.layers if bank else []):
            opts = self._options(layer)
            if not opts:
                continue
            file = opts[self.pick.get(layer["name"], 0) % len(opts)]
            if file is None:
                avatar[layer["name"]] = None
                continue
            mode = layer.get("tint")
            tint = None
            if mode and mode != "team":
                pal = self._palette(mode)
                tint = list(pal[self.pick.get(mode, 0) % len(pal)])
                b = self.pick.get(mode + BOTTOM, 0)
                if b:
                    tint = [tint, list(pal[(b - 1) % len(pal)])]
            avatar[layer["name"]] = {"file": file, "tint": tint}
        self.custom.avatar = avatar
        self.custom.fatigue = 90.0 if self.tired else 10.0

    def back(self):
        if self.back_to is not None:
            self.app.change(self.back_to)
        else:
            from .title import TitleScene
            self.app.change(TitleScene(self.app))

    def handle(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.builder:
                    self.toggle_builder()
                else:
                    self.back()
            elif event.key == pygame.K_SPACE:
                self.shuffle_or_random()
            elif event.key == pygame.K_t:
                self.toggle_tired()
            elif event.key == pygame.K_b:
                self.toggle_builder()
            elif self.builder and self.rows:
                if event.key in (pygame.K_UP, pygame.K_w):
                    self.row = (self.row - 1) % len(self.rows)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.row = (self.row + 1) % len(self.rows)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self.step(self.row, -1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.step(self.row, 1)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for b in self.buttons:
                if b.handle(event):
                    return
            if self.builder:
                for rect, row, delta in self.arrows:
                    if rect.collidepoint(event.pos):
                        if delta:
                            self.step(row, delta)
                        else:
                            self.row = row
                        return
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
        self.buttons[3].label = "Randomise" if self.builder else "Shuffle"
        self.buttons[3].tooltip = "Space: random pieces" if self.builder else "Space: roll a new set of analysts"
        self.buttons[4].label = "Back to the gallery" if self.builder else "Build your own"
        self.buttons[4].selected = self.builder
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
        if self.builder:
            self._draw_builder(surf, bank, mouse)
            self._draw_strip(surf, bank, self.custom)
        else:
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
            if tint and isinstance(tint[0], (list, tuple)):
                tint_txt = f"  (gradient {tint[0]} to {tint[1]})"
            else:
                tint_txt = f"  (tint {tint[0]}, {tint[1]}, {tint[2]})" if tint else ""
            lines.append((f"{layer}: {file}{tint_txt}", C.dim, 12))
        for layer in bank.layers:
            if g.avatar.get(layer["name"], "missing") is None:
                lines.append((f"{layer['name']}: none", C.faint, 12))
        return lines

    def _draw_builder(self, surf, bank, mouse):
        if not self.rows:
            self._build_rows()
        preview = pygame.Rect(GRID.x, GRID.y, 560, GRID.height)
        controls = pygame.Rect(preview.right + 12, GRID.y, GRID.right - preview.right - 12, GRID.height)
        team = self._team_keys()[self.pick.get("team", 0) % len(self._team_keys())]
        tcol = self.data.team_color(team)
        panel(surf, preview, mix(tcol, C.panel, 0.86), C.border, radius=10)
        img = bank.sprite(self.custom, preview.height - 40, tcol, self.tired)
        if img is not None:
            surf.blit(img, img.get_rect(midbottom=(preview.centerx, preview.bottom - 8)))
        panel(surf, controls, C.panel, C.border, radius=10)
        x = controls.x + 20
        draw_text(surf, "BUILD YOUR OWN", (x, controls.y + 14), 12, C.faint, "bold")
        draw_text(surf, "Up/down picks a row, left/right changes it. Every piece is available, whatever the "
                        "gender prefix.", (x + 150, controls.y + 14), 12, C.dim, max_width=controls.width - 190)
        self.arrows = []
        y = controls.y + 44
        row_h = min(46, (controls.bottom - 12 - y) // max(1, len(self.rows)))
        name_w = 170
        box = pygame.Rect(0, 0, 360, row_h - 8)
        for i, (kind, key) in enumerate(self.rows):
            rect = pygame.Rect(controls.x + 10, y, controls.width - 20, row_h - 4)
            sel = i == self.row
            if sel or rect.collidepoint(mouse):
                pygame.draw.rect(surf, C.panel3 if sel else C.panel2, rect, border_radius=6)
            if sel:
                pygame.draw.rect(surf, C.accent, rect, 1, border_radius=6)
            self.arrows.append((rect, i, 0))
            n = self._row_count(kind, key)
            idx = self.pick.get(key, 0) % max(1, n)
            label = {"palette": f"{key.replace('_', ' ')}", "team": "team colour",
                     "fade": "  fades to"}.get(kind, f"{key}/")
            draw_text(surf, label, (x, rect.centery), 14, C.text if kind == "layer" else C.dim, "bold",
                      anchor="midleft", max_width=name_w - 10)
            box.midleft = (x + name_w + 34, rect.centery)
            left = pygame.Rect(0, 0, 30, box.height)
            left.midright = (box.x - 4, rect.centery)
            right = pygame.Rect(0, 0, 30, box.height)
            right.midleft = (box.right + 4, rect.centery)
            for arrow, d in ((left, -1), (right, 1)):
                over = arrow.collidepoint(mouse)
                pygame.draw.rect(surf, C.hover if over else C.panel3, arrow, border_radius=5)
                cx, cy = arrow.center
                pts = [(cx + 5 * d, cy), (cx - 4 * d, cy - 7), (cx - 4 * d, cy + 7)]
                pygame.draw.polygon(surf, C.text if over else C.dim, pts)
                self.arrows.insert(0, (arrow, i, d))
            pygame.draw.rect(surf, C.bg2, box, border_radius=5)
            if kind == "layer":
                layer = next(l for l in bank.layers if l["name"] == key)
                opts = self._options(layer)
                val = opts[idx] if opts else None
                text = "none" if val is None else val[:-4]
                draw_text(surf, text, box.center, 13, C.text if val else C.faint, "semibold", anchor="center",
                          max_width=box.width - 12)
                note = []
                if layer.get("condition"):
                    note.append(f"only when {layer['condition']}")
                mode = layer.get("tint")
                if mode == "team":
                    note.append("team colour")
                elif mode:
                    note.append(mode.replace("_", " "))
                if val and "_fixed" in val:
                    note = [n for n in note if n.startswith("only")] + ["own colours"]
                draw_text(surf, f"{idx + 1}/{n}" + (f"  ·  {', '.join(note)}" if note else ""),
                          (right.right + 14, rect.centery), 12, C.faint, anchor="midleft",
                          max_width=rect.right - right.right - 24)
            elif kind == "fade":
                pal_name = key[:-len(BOTTOM)]
                pal = self._palette(pal_name)
                sw = box.inflate(-12, -10)
                if idx == 0:
                    draw_text(surf, "no gradient", box.center, 13, C.faint, "semibold", anchor="center")
                    draw_text(surf, f"{idx + 1}/{n}", (right.right + 14, rect.centery), 12, C.faint, anchor="midleft")
                else:
                    top = pal[self.pick.get(pal_name, 0) % len(pal)][:3]
                    bot = pal[(idx - 1) % len(pal)][:3]
                    for k in range(sw.width):
                        t = k / max(1, sw.width - 1)
                        col = tuple(int(top[j] + (bot[j] - top[j]) * t) for j in range(3))
                        pygame.draw.line(surf, col, (sw.x + k, sw.y), (sw.x + k, sw.bottom - 1))
                    pygame.draw.rect(surf, C.border2, sw, 1, border_radius=4)
                    draw_text(surf, f"{idx + 1}/{n}  ·  top to bottom", (right.right + 14, rect.centery), 12,
                              C.faint, anchor="midleft")
            elif kind == "palette":
                col = tuple(self._palette(key)[idx][:3])
                sw = box.inflate(-12, -10)
                pygame.draw.rect(surf, col, sw, border_radius=4)
                pygame.draw.rect(surf, C.border2, sw, 1, border_radius=4)
                draw_text(surf, f"{idx + 1}/{n}  ·  {col[0]}, {col[1]}, {col[2]}", (right.right + 14, rect.centery),
                          12, C.faint, anchor="midleft")
            else:
                name = "Bench" if team == "bench" else f"{self.data.team_name(team)} team"
                pygame.draw.circle(surf, tcol, (box.x + 18, box.centery), 7)
                draw_text(surf, name, box.center, 13, tcol, "semibold", anchor="center")
                draw_text(surf, f"{idx + 1}/{n}", (right.right + 14, rect.centery), 12, C.faint, anchor="midleft")
            y += row_h

    def _draw_strip(self, surf, bank, g=None):
        panel(surf, STRIP, C.panel, C.border, radius=10)
        if g is None:
            g = self.ghas[self.focus] if self.ghas else None
        if g is None:
            return
        title = "YOUR AVATAR" if g is self.custom else g.name.upper()
        draw_text(surf, f"{title} IN EVERY TEAM COLOUR", (STRIP.x + 16, STRIP.y + 12), 12, C.faint, "bold")
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
