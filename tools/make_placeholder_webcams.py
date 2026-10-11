"""Writes placeholder volcano webcam images into assets/webcams/.

    python tools/make_placeholder_webcams.py            # only writes images that don't exist yet
    python tools/make_placeholder_webcams.py --force    # overwrite them

The ops room shows the first six PNGs in assets/webcams/ (sorted by file name);
the label comes from the name, so '3_ngauruhoe.png' shows as 'Ngauruhoe'.
Night views are made in game by darkening the daytime image.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from ui.webcams import CAM_DIR, PLACEHOLDERS, draw_placeholder  # noqa: E402


def main():
    force = "--force" in sys.argv
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    CAM_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for i, (label, kind) in enumerate(PLACEHOLDERS):
        path = CAM_DIR / f"{i + 1}_{label.lower().replace(' ', '_')}.png"
        if path.exists() and not force:
            continue
        pygame.image.save(draw_placeholder(kind, (480, 300), seed=i), str(path))
        written += 1
    print(f"Wrote {written} image(s) to {CAM_DIR}" + ("" if force else " (existing files kept; --force overwrites)"))


if __name__ == "__main__":
    main()
