"""Colours, fonts and cached text rendering."""
from __future__ import annotations

from collections import OrderedDict

import pygame

from game.data import ROOT

W, H = 1920, 1080
FONT_DIR = ROOT / "assets" / "fonts"
FONT_FILES = {"regular": "Inter-Regular.otf", "semibold": "Inter-SemiBold.otf", "bold": "Inter-Bold.otf"}


class C:
    bg = (13, 16, 22)
    bg2 = (18, 22, 30)
    panel = (24, 29, 39)
    panel2 = (31, 37, 49)
    panel3 = (41, 48, 63)
    hover = (48, 56, 74)
    border = (48, 56, 72)
    border2 = (72, 82, 104)
    text = (232, 236, 242)
    dim = (163, 171, 186)
    faint = (110, 118, 135)
    accent = (86, 180, 233)
    good = (126, 211, 106)
    warn = (240, 180, 70)
    bad = (236, 88, 76)
    sop = (176, 140, 245)
    gold = (240, 200, 90)
    supply = (240, 140, 205)
    training = (110, 220, 170)
    trust = (236, 240, 248)
    ltf = (245, 128, 92)
    ocean = (17, 27, 40)
    land = (52, 64, 58)
    land_edge = (92, 110, 98)
    white = (255, 255, 255)
    black = (0, 0, 0)


TONES = {"info": C.dim, "good": C.good, "bad": C.bad, "warn": C.warn, "sop": C.sop, "accent": C.accent}
TRAIT_COLOURS = {"good": C.good, "balanced": C.warn, "bad": C.bad}
TRAIT_LABELS = {"good": "Positive trait", "balanced": "Balanced trait (upside and downside)", "bad": "Negative trait"}
RARITY = {"common": (190, 196, 206), "uncommon": (100, 205, 112), "rare": (90, 160, 255), "legendary": (255, 170, 50)}


def mag_color(m: float) -> tuple:
    if m < 2.0:
        return (126, 168, 150)
    if m < 3.0:
        return (140, 205, 110)
    if m < 4.0:
        return (235, 205, 80)
    if m < 5.0:
        return (245, 150, 60)
    if m < 6.0:
        return (236, 88, 76)
    return (232, 92, 205)


def depth_color(d: float) -> tuple:
    if d < 15:
        return (245, 110, 80)
    if d < 40:
        return (245, 180, 70)
    if d < 100:
        return (150, 210, 110)
    if d < 300:
        return (86, 180, 233)
    return (160, 130, 240)


def trust_color(v: float) -> tuple:
    if v >= 60:
        return C.good
    if v >= 30:
        return C.warn
    return C.bad


def mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Fonts:
    _cache: dict = {}

    @classmethod
    def get(cls, size: int, weight: str = "regular") -> pygame.font.Font:
        key = (size, weight)
        font = cls._cache.get(key)
        if font is None:
            path = FONT_DIR / FONT_FILES.get(weight, FONT_FILES["regular"])
            try:
                font = pygame.font.Font(str(path), size)
            except (OSError, FileNotFoundError, pygame.error):
                font = pygame.font.Font(None, int(size * 1.35))
                font.set_bold(weight != "regular")
            cls._cache[key] = font
        return font


_TEXT_CACHE: OrderedDict = OrderedDict()


def render(text: str, size: int = 14, color: tuple = C.text, weight: str = "regular") -> pygame.Surface:
    color = tuple(color)
    key = (text, size, color, weight)
    surf = _TEXT_CACHE.get(key)
    if surf is None:
        surf = Fonts.get(size, weight).render(text, True, color)
        _TEXT_CACHE[key] = surf
        if len(_TEXT_CACHE) > 5000:
            _TEXT_CACHE.popitem(last=False)
    else:
        _TEXT_CACHE.move_to_end(key)
    return surf


def text_width(text: str, size: int = 14, weight: str = "regular") -> int:
    return Fonts.get(size, weight).size(text)[0]
