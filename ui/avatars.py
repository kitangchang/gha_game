"""Builds analyst avatars from the layered PNGs in assets/avatars/ (see the
README there). Pieces are loaded once at start-up; F5 reloads them."""
from __future__ import annotations

import random

import pygame

from game import avatars as ga

_BANK: "AvatarBank | None" = None


def get_bank() -> "AvatarBank | None":
    return _BANK


def init_bank() -> "AvatarBank":
    global _BANK
    _BANK = AvatarBank()
    return _BANK


def _tint_key(tint):
    """Hashable tint: (r, g, b), or ((r, g, b), (r, g, b)) for a top-to-bottom gradient."""
    if not tint:
        return None
    if isinstance(tint[0], (list, tuple)):
        return tuple(tuple(c[:3]) for c in tint[:2])
    return tuple(tint[:3])


def is_gradient(tint) -> bool:
    return bool(tint) and isinstance(tint[0], (list, tuple))


class AvatarBank:
    MAX_CACHE = 800

    def __init__(self):
        self.images: dict = {}
        self.backs: dict = {}
        self.overlays: dict = {}
        self.errors: list = []
        self._tints: dict = {}
        self._composed: dict = {}
        self._views: dict = {}
        self._masks: dict = {}
        self.reload()

    # ----------------------------------------------------------------- loading
    def reload(self):
        ga.clear_cache()
        self.manifest = ga.load_manifest()
        self.canvas = tuple(self.manifest.get("canvas", (128, 128)))
        self.pixel_art = bool(self.manifest.get("pixel_art", False))
        self.layers = list(self.manifest.get("layers", []))
        self.tired_level = float(self.manifest.get("tired_fatigue", 70))
        self.images.clear()
        self.backs.clear()
        self.overlays.clear()
        self.errors = []
        for layer in self.layers:
            folder = ga.AVATAR_DIR / layer["name"]
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.png")):
                img = self._load(path)
                if img is None:
                    continue
                if path.stem.endswith("_back"):
                    self.backs[(layer["name"], path.stem[:-5] + ".png")] = img
                else:
                    self.images[(layer["name"], path.name)] = img
        for key, rel in (self.manifest.get("overlays") or {}).items():
            path = ga.AVATAR_DIR / rel
            if path.exists():
                img = self._load(path)
                if img is not None:
                    self.overlays[key] = img
        ga.scan(force=True)
        self._tints.clear()
        self._composed.clear()
        self._views.clear()

    def _load(self, path):
        try:
            img = pygame.image.load(str(path)).convert_alpha()
        except (pygame.error, OSError) as exc:
            self.errors.append(f"{path.name}: {exc}")
            return None
        if img.get_size() != self.canvas:
            img = self._scale(img, self.canvas)
        return img

    def _scale(self, img, size):
        size = (max(1, int(size[0])), max(1, int(size[1])))
        if self.pixel_art:
            return pygame.transform.scale(img, size)
        return pygame.transform.smoothscale(img, size)

    # ------------------------------------------------------------------- info
    def files(self, layer: str) -> list:
        return sorted(f for (l, f) in self.images if l == layer)

    def counts(self) -> dict:
        return {layer["name"]: len(self.files(layer["name"])) for layer in self.layers}

    @property
    def has_art(self) -> bool:
        required = [l["name"] for l in self.layers if l.get("required")] or [l["name"] for l in self.layers[:1]]
        return bool(required) and all(self.files(name) for name in required)

    def is_tired(self, g) -> bool:
        return g.fatigue >= self.tired_level

    # -------------------------------------------------------------- composing
    def ensure_avatar(self, g) -> dict:
        if not getattr(g, "avatar", None):
            g.avatar = ga.random_avatar(random.Random(g.id * 7919 + 13), getattr(g, "gender", ""))
        return g.avatar

    def _parts(self, g, team_color) -> tuple:
        avatar = self.ensure_avatar(g)
        parts = []
        palette_tint: dict = {}      # the first layer using a palette sets its colour for all the others
        for layer in self.layers:
            name = layer["name"]
            entry = avatar.get(name, "missing")
            files = self.files(name)
            if not files:
                continue
            cond = layer.get("condition")
            if cond:
                # condition layers belong to everyone and show only when the condition holds;
                # a chosen piece (e.g. from the avatar builder) is kept, otherwise one is picked
                entry = entry if isinstance(entry, dict) else {}
            if entry is None:
                continue
            if entry == "missing":
                if not layer.get("required"):
                    continue
                entry = {}
            gender = getattr(g, "gender", "")
            files = [f for f in files if ga.piece_fits(f, gender)] or files
            file = entry.get("file")
            if (name, file) not in self.images or not ga.piece_fits(file, gender):
                file = files[sum(ord(c) for c in f"{g.id}:{name}") % len(files)]
            tint = entry.get("tint")
            mode = layer.get("tint")
            if mode == "team":
                tint = team_color
            elif mode:
                if mode in palette_tint:
                    tint = palette_tint[mode]
                elif not tint:
                    palette = self.manifest.get("palettes", {}).get(mode) or [[255, 255, 255]]
                    tint = palette[(g.id * 31) % len(palette)]
                palette_tint.setdefault(mode, tint)
            if "_fixed" in file:
                tint = None
            parts.append((name, file, _tint_key(tint), cond))
        return tuple(parts)

    def _span(self, name, file) -> tuple:
        """Top and bottom of a piece (front and back half together), for gradients."""
        key = ("span", name, file)
        span = self._tints.get(key)
        if span is None:
            rects = [img.get_bounding_rect() for img in (self.images.get((name, file)), self.backs.get((name, file)))
                     if img is not None]
            rects = [r for r in rects if r.height > 0]
            if rects:
                top, bottom = min(r.top for r in rects), max(r.bottom for r in rects)
            else:
                top, bottom = 0, self.canvas[1]
            span = self._tints[key] = (top, bottom)
        return span

    def _tinted(self, key, img, tint, span=None):
        if tint is None:
            return img
        cache_key = (key, tint)
        out = self._tints.get(cache_key)
        if out is None:
            out = img.copy()
            if is_gradient(tint):
                out.blit(self._gradient(tint[0], tint[1], out.get_size(), span), (0, 0),
                         special_flags=pygame.BLEND_RGBA_MULT)
            else:
                out.fill(tuple(tint[:3]) + (255,), special_flags=pygame.BLEND_RGBA_MULT)
            self._tints[cache_key] = out
        return out

    @staticmethod
    def _gradient(top, bottom, size, span=None) -> pygame.Surface:
        """Colour 1 at the top of the piece fading to colour 2 at its bottom
        (span = (top row, bottom row); the whole canvas if not given)."""
        w, h = size
        y0, y1 = span if span else (0, h)
        grad = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            t = min(1.0, max(0.0, (y - y0) / max(1, y1 - 1 - y0)))
            col = tuple(int(round(top[i] + (bottom[i] - top[i]) * t)) for i in range(3)) + (255,)
            pygame.draw.line(grad, col, (0, y), (w - 1, y))
        return grad

    def compose(self, g, team_color=None, tired: bool = False) -> pygame.Surface | None:
        if not self.has_art:
            return None
        parts = self._parts(g, tuple(team_color) if team_color else None)
        key = (parts, bool(tired))
        surf = self._composed.get(key)
        if surf is not None:
            return surf
        if len(self._composed) > self.MAX_CACHE:
            self._composed.clear()
            self._views.clear()
        surf = pygame.Surface(self.canvas, pygame.SRCALPHA)
        conditions = {"tired": bool(tired)}
        parts = [p for p in parts if not p[3] or conditions.get(p[3], False)]
        for name, file, tint, _ in parts:
            back = self.backs.get((name, file))
            if back is not None:
                surf.blit(self._tinted((name, file, "back"), back, tint, self._span(name, file)), (0, 0))
        for name, file, tint, _ in parts:
            surf.blit(self._tinted((name, file), self.images[(name, file)], tint, self._span(name, file)), (0, 0))
        if tired and "tired" in self.overlays:
            surf.blit(self.overlays["tired"], (0, 0))
        self._composed[key] = surf
        return surf

    # ------------------------------------------------------------------ views
    def _mask(self, size: int) -> pygame.Surface:
        mask = self._masks.get(size)
        if mask is None:
            big = pygame.Surface((size * 4, size * 4), pygame.SRCALPHA)
            pygame.draw.circle(big, (255, 255, 255, 255), (size * 2, size * 2), size * 2)
            mask = pygame.transform.smoothscale(big, (size, size))
            self._masks[size] = mask
        return mask

    def portrait(self, g, size: int, team_color=None, tired: bool = False, bg=None) -> pygame.Surface | None:
        """Circular head-and-shoulders portrait."""
        composed = self.compose(g, team_color, tired)
        if composed is None:
            return None
        key = ("portrait", id(composed), size, tuple(bg) if bg else None)
        out = self._views.get(key)
        if out is None:
            crop = pygame.Rect(self.manifest.get("portrait_crop") or (0, 0, *self.canvas))
            crop = crop.clip(composed.get_rect())
            face = self._scale(composed.subsurface(crop), (size, size))
            out = pygame.Surface((size, size), pygame.SRCALPHA)
            if bg is not None:
                out.fill(tuple(bg[:3]) + (255,))
            out.blit(face, (0, 0))
            out.blit(self._mask(size), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self._views[key] = out
        return out

    def sprite(self, g, height: int, team_color=None, tired: bool = False) -> pygame.Surface | None:
        """The whole canvas (head, shoulders, clothes) scaled to a height."""
        composed = self.compose(g, team_color, tired)
        if composed is None:
            return None
        key = ("sprite", id(composed), height)
        out = self._views.get(key)
        if out is None:
            w = round(height * self.canvas[0] / self.canvas[1])
            out = self._scale(composed, (w, height))
            self._views[key] = out
        return out
