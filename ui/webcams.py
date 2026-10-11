"""Volcano webcam images for the ops room wall. PNGs in assets/webcams/ are
loaded at start-up (F5 reloads); the first six (sorted by file name) are shown.
The label comes from the file name: '3_ngauruhoe.png' -> 'Ngauruhoe'.
Missing images are drawn procedurally."""
from __future__ import annotations

import math
import random
import re

import pygame

from game.data import ROOT

CAM_DIR = ROOT / "assets" / "webcams"
CAM_COUNT = 6
SUMMIT = (0.5, 0.42)          # where plumes rise from, as a fraction of the image

_BANK: "WebcamBank | None" = None

# (label, kind) for the generated placeholders
PLACEHOLDERS = [("Whakaari", "island"), ("Ruapehu", "broad"), ("Ngauruhoe", "cone"),
                ("Te Maari", "ridge"), ("Taranaki", "tall"), ("Raoul Island", "low_island")]


def get_webcams() -> "WebcamBank | None":
    return _BANK


def init_webcams() -> "WebcamBank":
    global _BANK
    _BANK = WebcamBank()
    return _BANK


def label_from_file(stem: str) -> str:
    text = re.sub(r"^[0-9]+[ _-]*", "", stem).replace("_", " ").replace("-", " ").strip()
    return text.title() if text else stem


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_placeholder(kind: str, size=(320, 200), seed: int = 0) -> pygame.Surface:
    """A simple daylight webcam view of a volcano."""
    w, h = size
    s = 2
    big = pygame.Surface((w * s, h * s))
    W2, H2 = w * s, h * s
    for y in range(H2):
        k = y / H2
        big.fill(_lerp((96, 150, 205), (198, 218, 232), min(1.0, k * 1.4)), (0, y, W2, 1))
    rng = random.Random(seed)
    for _ in range(4):                                        # clouds
        cx, cy = rng.uniform(0, W2), rng.uniform(H2 * 0.08, H2 * 0.3)
        for k in range(5):
            r = rng.uniform(14, 30) * s
            pygame.draw.ellipse(big, (232, 238, 244), (cx + k * 18 * s - r, cy - r * 0.45, r * 2, r * 0.9))
    sx, sy = SUMMIT[0] * W2, SUMMIT[1] * H2
    ground = int(H2 * 0.78)
    rock, rock_dark, snow = (92, 84, 80), (70, 64, 62), (236, 240, 246)
    if kind in ("island", "low_island"):
        pygame.draw.rect(big, (46, 88, 126), (0, int(H2 * 0.72), W2, H2))
        for y in range(int(H2 * 0.72), H2, 6 * s):
            pygame.draw.line(big, (66, 110, 150), (0, y), (W2, y), 1)
        top = sy if kind == "island" else sy + H2 * 0.14
        pts = [(W2 * 0.12, H2 * 0.74), (sx - 60 * s, top + 20 * s), (sx - 18 * s, top), (sx + 18 * s, top + 4 * s),
               (sx + 70 * s, top + 26 * s), (W2 * 0.9, H2 * 0.74)]
        pygame.draw.polygon(big, rock, pts)
        pygame.draw.polygon(big, rock_dark, [pts[3], pts[4], pts[5], (sx, H2 * 0.74)])
        if kind == "low_island":
            pygame.draw.polygon(big, (70, 110, 70), [(W2 * 0.12, H2 * 0.74), (sx - 60 * s, top + 22 * s),
                                                     (sx, top + 30 * s), (W2 * 0.9, H2 * 0.74)])
    else:
        pygame.draw.rect(big, (78, 96, 70), (0, ground, W2, H2 - ground))
        spread = {"broad": 150, "cone": 95, "ridge": 170, "tall": 80}.get(kind, 110) * s
        top = sy + (12 * s if kind == "broad" else 0)
        if kind == "ridge":
            pts = [(0, ground), (sx - spread, top + 40 * s), (sx - 30 * s, top + 8 * s), (sx + 10 * s, top + 14 * s),
                   (sx + 60 * s, top + 4 * s), (sx + spread, top + 46 * s), (W2, ground)]
        else:
            flat = 26 * s if kind == "broad" else 6 * s
            pts = [(sx - spread * 1.6, ground), (sx - flat, top), (sx + flat, top), (sx + spread * 1.6, ground)]
        pygame.draw.polygon(big, rock, pts)
        pygame.draw.polygon(big, rock_dark, [(sx, top), pts[-2], pts[-1], (sx, ground)])
        if kind in ("broad", "tall", "cone"):
            cap = (spread * (0.42 if kind == "tall" else 0.3))
            cap_y = top + cap * 0.55
            pygame.draw.polygon(big, snow, [(sx - flat - cap * 0.7, cap_y), (sx - flat, top), (sx + flat, top),
                                            (sx + flat + cap * 0.7, cap_y), (sx + 12 * s, cap_y - 6 * s),
                                            (sx - 10 * s, cap_y + 4 * s)])
    return pygame.transform.smoothscale(big, (w, h))


class WebcamBank:
    def __init__(self):
        self.cams: list = []          # [(label, surface)]
        self.errors: list = []
        self._cache: dict = {}
        self.reload()

    def reload(self):
        self.cams = []
        self.errors = []
        self._cache.clear()
        if CAM_DIR.is_dir():
            for path in sorted(CAM_DIR.glob("*.png"))[:CAM_COUNT]:
                try:
                    self.cams.append((label_from_file(path.stem), pygame.image.load(str(path)).convert()))
                except (pygame.error, OSError) as exc:
                    self.errors.append(f"{path.name}: {exc}")
        k = 0
        while len(self.cams) < CAM_COUNT:
            label, kind = PLACEHOLDERS[k % len(PLACEHOLDERS)]
            self.cams.append((label, draw_placeholder(kind, seed=k)))
            k += 1

    @staticmethod
    def light(hour: float) -> float:
        """1 = full daylight, ~0.12 = night."""
        if 7 <= hour < 19:
            return 1.0
        if 5 <= hour < 7:
            return 0.12 + 0.88 * (hour - 5) / 2
        if 19 <= hour < 21:
            return 1.0 - 0.88 * (hour - 19) / 2
        return 0.12

    def frame(self, index: int, size, hour: float) -> pygame.Surface:
        level = round(self.light(hour) * 10) / 10
        key = (index % len(self.cams), tuple(size), level)
        img = self._cache.get(key)
        if img is None:
            src = self.cams[key[0]][1]
            tw, th = max(1, size[0]), max(1, size[1])
            sw, sh = src.get_size()
            if tw / th < sw / sh:                       # cell is narrower: crop the sides, keep the summit
                cw = max(1, int(sh * tw / th))
                crop = pygame.Rect(int((sw - cw) * SUMMIT[0]), 0, cw, sh)
            else:                                       # cell is wider: crop top and bottom
                ch = max(1, int(sw * th / tw))
                crop = pygame.Rect(0, max(0, int((sh - ch) * 0.5)), sw, ch)
            img = pygame.transform.smoothscale(src.subsurface(crop.clip(src.get_rect())), (tw, th))
            if level < 1.0:
                tint = (int(255 * level * 0.9 + 18), int(255 * level * 0.95 + 22), int(255 * level + 40))
                img = img.copy()
                img.fill(tuple(min(255, c) for c in tint), special_flags=pygame.BLEND_RGB_MULT)
                if level < 0.4:
                    rng = random.Random(index * 31 + size[0])
                    for _ in range(max(4, size[0] * size[1] // 900)):
                        x, y = rng.randrange(size[0]), rng.randrange(max(1, int(size[1] * 0.45)))
                        img.set_at((x, y), (200, 205, 220))
            self._cache[key] = img
            if len(self._cache) > 200:
                self._cache.clear()
        return img

    def label(self, index: int) -> str:
        return self.cams[index % len(self.cams)][0]

    def primary_index(self) -> int:
        """The camera that steams the most: Whakaari (White Island) if there is one, else the first."""
        for i, (label, _) in enumerate(self.cams):
            name = label.lower()
            if "whakaari" in name or "white island" in name:
                return i
        return 0


def plume(surf, x: float, y: float, t: float, scale: float = 1.0, alpha: int = 170):
    """Animated steam puffs rising from (x, y)."""
    for k in range(6):
        phase = (t * 0.35 + k / 6.0) % 1.0
        r = (3 + phase * 10) * scale
        px = x + math.sin(phase * 5 + k) * 4 * scale + phase * 6 * scale
        py = y - phase * 26 * scale
        a = int(alpha * (1 - phase))
        tmp = pygame.Surface((int(r * 2 + 2), int(r * 2 + 2)), pygame.SRCALPHA)
        pygame.draw.circle(tmp, (238, 240, 244, a), (int(r + 1), int(r + 1)), int(r))
        surf.blit(tmp, (px - r, py - r))
