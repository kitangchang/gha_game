"""Colours, fonts and cached text rendering."""
from __future__ import annotations

import unicodedata
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
RARITY = {"common": (190, 196, 206), "uncommon": (100, 205, 112), "rare": (90, 160, 255), "legendary": (255, 170, 50),
          "boss": (235, 95, 205)}


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


def _font_settings() -> dict:
    """display.font / font_bold / font_scale / fake_bold from data/config.json."""
    import json
    try:
        with open(ROOT / "data" / "config.json", encoding="utf-8") as fh:
            return json.load(fh).get("display", {})
    except (OSError, ValueError):
        return {}


class Fonts:
    """Fonts come from assets/fonts/. Set display.font in data/config.json to use
    your own font (one file for every weight, or display.font_bold /
    display.font_semibold for separate files). font_scale enlarges or shrinks all
    text; fake_bold thickens the semibold and bold text when they share the
    regular file."""
    _cache: dict = {}
    _settings: dict | None = None
    _warned = False

    @classmethod
    def settings(cls) -> dict:
        if cls._settings is None:
            cls._settings = _font_settings()
        return cls._settings

    @classmethod
    def _file(cls, weight: str):
        cfg = cls.settings()
        custom = cfg.get(f"font_{weight}") or cfg.get("font")
        if custom:
            path = FONT_DIR / custom
            if path.exists():
                return path, not cfg.get(f"font_{weight}") and weight != "regular" and cfg.get("fake_bold", True)
            if not cls._warned:
                cls._warned = True
                print(f"Font {path} not found, using Inter")
        return FONT_DIR / FONT_FILES.get(weight, FONT_FILES["regular"]), False

    @classmethod
    def get(cls, size: int, weight: str = "regular") -> pygame.font.Font:
        key = (size, weight)
        font = cls._cache.get(key)
        if font is None:
            path, fake_bold = cls._file(weight)
            scaled = max(6, round(size * float(cls.settings().get("font_scale", 1.0))))
            try:
                font = pygame.font.Font(str(path), scaled)
                # Fake bold is drawn by render() (a gentle 1 px smear), not pygame's set_bold,
                # which fills in the holes of small letters.
                cls._cache[("fake", size, weight)] = fake_bold and (weight == "bold" or scaled >= 15)
            except (OSError, FileNotFoundError, pygame.error):
                font = pygame.font.Font(None, int(scaled * 1.35))
                font.set_bold(weight != "regular")
            cls._cache[key] = font
        return font


_TEXT_CACHE: OrderedDict = OrderedDict()


def _space_gap(size: int, weight: str) -> int | None:
    """None if the font draws a proper (blank) space; otherwise the gap to leave
    between words. Some home-made fonts have no space character, so the space
    comes out as a box."""
    key = ("space", size, weight)
    gap = Fonts._cache.get(key, -1)
    if gap == -1:
        img = Fonts.get(size, weight).render(" ", True, (255, 255, 255))
        drawn = pygame.mask.from_surface(img).count() > 0
        gap = max(2, round(size * 0.3)) if drawn else None
        Fonts._cache[key] = gap
    return gap


# Stand-ins for characters a custom font doesn't have. Anything missing that
# isn't listed falls back to its plain-letter form (ō -> o), or stays as it is.
GLYPH_FALLBACKS = {
    "—": "-", "–": "-", "−": "-", "‑": "-", "…": "...", "→": "->", "←": "<-", "↑": "^", "↓": "v",
    "×": "x", "÷": "/", "½": "1/2", "¼": "1/4", "¾": "3/4", "≥": ">=", "≤": "<=", "±": "+/-", "≈": "~",
    "°": " deg", "·": "-", "•": "-", "▶": ">", "◀": "<", "▲": "^", "▼": "v", "✓": "OK", "✔": "OK",
    "✕": "x", "✖": "x", "’": "'", "‘": "'", "“": '"', "”": '"', "\u00a0": " ", "★": "*", "☆": "*",
}
_MISSING: dict = {}


def _glyph_sig(font, ch: str):
    img = font.render(ch, True, (255, 255, 255), (0, 0, 0))
    return img.get_size(), pygame.image.tobytes(img, "RGB")


def glyph_missing(ch: str, weight: str = "regular") -> bool:
    """True if the font for this weight draws ch as its 'missing' box. Checked by
    comparing with a private-use character no font has, then remembered."""
    key = (weight, ch)
    hit = _MISSING.get(key)
    if hit is None:
        font = Fonts.get(24, weight)
        blank = _MISSING.get((weight, None))
        if blank is None:
            blank = _MISSING[(weight, None)] = _glyph_sig(font, "\ue000")
        hit = _MISSING[key] = _glyph_sig(font, ch) == blank
    return hit


def clean_text(text: str, weight: str = "regular") -> str:
    """Swap characters the font can't draw for plain stand-ins."""
    if text.isascii():
        return text
    out = []
    for ch in text:
        if ch.isascii() or ch == " " or not glyph_missing(ch, weight):
            out.append(ch)
            continue
        rep = GLYPH_FALLBACKS.get(ch)
        if rep is None:
            rep = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode() or ch
        out.append(rep)
    return "".join(out)


def _fake_bold(size: int, weight: str) -> bool:
    Fonts.get(size, weight)
    return bool(Fonts._cache.get(("fake", size, weight)))


def _render_raw(text: str, size: int, color: tuple, weight: str) -> pygame.Surface:
    img = _render_plain(text, size, color, weight)
    if not _fake_bold(size, weight):
        return img
    # The shifted copy is drawn faded, so the stroke grows by about half a pixel.
    # display.fake_bold_strength in config.json: 0 = off, 1 = a full extra pixel.
    strength = max(0.0, min(1.0, float(Fonts.settings().get("fake_bold_strength", 0.45))))
    shadow = img.copy()
    shadow.fill((255, 255, 255, int(255 * strength)), special_flags=pygame.BLEND_RGBA_MULT)
    out = pygame.Surface((img.get_width() + 1, img.get_height()), pygame.SRCALPHA)
    out.blit(shadow, (1, 0))
    out.blit(img, (0, 0))
    return out


def _render_plain(text: str, size: int, color: tuple, weight: str) -> pygame.Surface:
    text = clean_text(text, weight)
    font = Fonts.get(size, weight)
    gap = _space_gap(size, weight)
    if gap is None or " " not in text:
        return font.render(text, True, color)
    parts = [font.render(w, True, color) if w else None for w in text.split(" ")]
    width = sum(p.get_width() for p in parts if p) + gap * (len(parts) - 1)
    out = pygame.Surface((max(1, width), font.get_height()), pygame.SRCALPHA)
    x = 0
    for p in parts:
        if p:
            out.blit(p, (x, 0))
            x += p.get_width()
        x += gap
    return out


def render(text: str, size: int = 14, color: tuple = C.text, weight: str = "regular") -> pygame.Surface:
    color = tuple(color)
    key = (text, size, color, weight)
    surf = _TEXT_CACHE.get(key)
    if surf is None:
        surf = _render_raw(text, size, color, weight)
        _TEXT_CACHE[key] = surf
        if len(_TEXT_CACHE) > 5000:
            _TEXT_CACHE.popitem(last=False)
    else:
        _TEXT_CACHE.move_to_end(key)
    return surf


def text_width(text: str, size: int = 14, weight: str = "regular") -> int:
    return _plain_width(text, size, weight) + (1 if _fake_bold(size, weight) else 0)


def _plain_width(text: str, size: int, weight: str) -> int:
    text = clean_text(text, weight)
    gap = _space_gap(size, weight)
    font = Fonts.get(size, weight)
    if gap is None or " " not in text:
        return font.size(text)[0]
    words = text.split(" ")
    return sum(font.size(w)[0] for w in words if w) + gap * (len(words) - 1)
