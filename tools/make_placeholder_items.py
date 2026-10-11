"""Writes placeholder item icons into assets/items/<tools|supplies|training>/<item id>.png.

    python tools/make_placeholder_items.py            # only writes icons that don't exist yet
    python tools/make_placeholder_items.py --force    # overwrite them

Each icon is a 64x64 PNG named after the item id in data/relics.json (tools),
consumables.json (supplies) or training.json. Replace them with your own art;
any size works (they're scaled), square looks best.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from game.data import get_data  # noqa: E402
from ui.icons import CATEGORIES, ITEM_DIR, draw_placeholder, items_for  # noqa: E402

SIZE = 64


def main():
    force = "--force" in sys.argv
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    data = get_data()
    written = 0
    for cat in CATEGORIES:
        folder = ITEM_DIR / cat
        folder.mkdir(parents=True, exist_ok=True)
        for item_id in items_for(data, cat):
            path = folder / f"{item_id}.png"
            if path.exists() and not force:
                continue
            pygame.image.save(draw_placeholder(data, cat, item_id, SIZE), str(path))
            written += 1
    print(f"Wrote {written} icon(s) to {ITEM_DIR}" + ("" if force else " (existing files kept; --force overwrites)"))


if __name__ == "__main__":
    main()
