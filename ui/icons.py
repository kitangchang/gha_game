"""Item icons: tools, supplies and training. PNGs live in
assets/items/<tools|supplies|training>/<item id>.png and are loaded at start-up
(F5 reloads). Anything without a PNG gets a generated badge so new items always
have an icon."""
from __future__ import annotations

import pygame

from game.art_check import png_files
from game.data import ROOT

from .theme import C, RARITY, Fonts, mix

ITEM_DIR = ROOT / "assets" / "items"
CATEGORIES = ("tools", "supplies", "training")

_BANK: "IconBank | None" = None


def get_icons() -> "IconBank | None":
    return _BANK


def init_icons(data) -> "IconBank":
    global _BANK
    _BANK = IconBank(data)
    return _BANK


def items_for(data, category: str) -> dict:
    return {"tools": data.relics, "supplies": data.consumables, "training": data.training}[category]


def category_colour(data, category: str, item_id: str):
    if category == "tools":
        return RARITY.get(data.relics.get(item_id, {}).get("rarity", "common"), C.text)
    return C.supply if category == "supplies" else C.training


def initials(name: str) -> str:
    words = [w for w in name.replace("-", " ").replace("&", " ").split() if w[:1].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].title()
    return (words[0][0] + words[1][0]).upper()


def draw_placeholder(data, category: str, item_id: str, size: int) -> pygame.Surface:
    """A simple badge: category/rarity colour, item initials. Also used to write the
    placeholder PNGs (tools/make_placeholder_items.py)."""
    item = items_for(data, category).get(item_id, {"name": item_id})
    col = category_colour(data, category, item_id)
    s = 4
    big = pygame.Surface((size * s, size * s), pygame.SRCALPHA)
    rect = big.get_rect().inflate(-2 * s, -2 * s)
    dark = mix(col, (14, 17, 23), 0.78)
    if category == "supplies":
        pygame.draw.ellipse(big, col, rect)
        pygame.draw.ellipse(big, dark, rect.inflate(-6 * s, -6 * s))
    elif category == "training":
        pygame.draw.rect(big, col, rect, border_radius=4 * s)
        pygame.draw.rect(big, dark, rect.inflate(-6 * s, -6 * s), border_radius=3 * s)
        spine = pygame.Rect(rect.x + 3 * s, rect.y + 3 * s, 3 * s, rect.height - 6 * s)
        pygame.draw.rect(big, mix(col, dark, 0.4), spine)
    else:
        pygame.draw.rect(big, col, rect, border_radius=7 * s)
        pygame.draw.rect(big, dark, rect.inflate(-6 * s, -6 * s), border_radius=5 * s)
        shine = pygame.Rect(rect.x + 6 * s, rect.y + 6 * s, rect.width - 12 * s, rect.height // 3)
        pygame.draw.rect(big, mix(dark, (255, 255, 255), 0.06), shine, border_radius=4 * s)
    img = pygame.transform.smoothscale(big, (size, size))
    text = initials(item.get("name", item_id))
    font = Fonts.get(max(8, int(size * 0.36)), "bold")
    label = font.render(text, True, col)
    img.blit(label, label.get_rect(center=(size // 2 + (1 if category == "training" else 0), size // 2 + 1)))
    return img


class IconBank:
    def __init__(self, data):
        self.data = data
        self.images: dict = {}
        self.errors: list = []
        self._cache: dict = {}
        self.reload()

    def reload(self):
        self.images.clear()
        self._cache.clear()
        self.errors = []
        for cat in CATEGORIES:
            folder = ITEM_DIR / cat
            if not folder.is_dir():
                continue
            for path in png_files(folder):
                try:
                    self.images[(cat, path.stem.lower())] = pygame.image.load(str(path)).convert_alpha()
                except (pygame.error, OSError) as exc:
                    self.errors.append(f"{cat}/{path.name}: {exc}")

    def counts(self) -> dict:
        out = {}
        for cat in CATEGORIES:
            ids = items_for(self.data, cat)
            out[cat] = (sum(1 for i in ids if (cat, i.lower()) in self.images), len(ids))
        return out

    def icon(self, category: str, item_id: str, size: int) -> pygame.Surface:
        key = (category, item_id, size)
        img = self._cache.get(key)
        if img is None:
            src = self.images.get((category, item_id.lower()))
            if src is None:
                img = draw_placeholder(self.data, category, item_id, size)
            elif src.get_size() == (size, size):
                img = src
            else:
                img = pygame.transform.smoothscale(src, (size, size))
            self._cache[key] = img
        return img

    def draw(self, surf, category: str, item_id: str, pos, size: int, dim: bool = False, anchor: str = "topleft"):
        img = self.icon(category, item_id, size)
        if dim:
            img = img.copy()
            img.fill((90, 90, 90, 255), special_flags=pygame.BLEND_RGBA_MULT)
        rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
        surf.blit(img, rect)
        return rect
