"""Draws simple placeholder avatar pieces into assets/avatars/<layer>/.

    python tools/make_placeholder_avatars.py            # only writes files that don't exist yet
    python tools/make_placeholder_avatars.py --force    # overwrite the placeholders

Every piece is a 128x128 PNG on the same canvas, so layers line up when stacked.
Greyscale pieces (skin, clothes, hair) are tinted in game: skin tones, team
colours and hair colours come from assets/avatars/avatar_config.json. Use these
files as templates for your own art.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from game.avatars import AVATAR_DIR  # noqa: E402

N = 128          # final canvas size
S = 4            # drawn at 4x, then smooth-scaled down for anti-aliasing

LINE = (40, 36, 40, 255)
BROW = (66, 52, 44, 255)


def R(x, y, w, h):
    return pygame.Rect(round(x * S), round(y * S), round(w * S), round(h * S))


def P(x, y):
    return (round(x * S), round(y * S))


def new():
    return pygame.Surface((N * S, N * S), pygame.SRCALPHA)


def ellipse(surf, color, rect, width=0):
    pygame.draw.ellipse(surf, color, R(*rect), round(width * S) if width else 0)


def blend_ellipse(surf, color, rect):
    """Translucent ellipse blended over what's already there. (pygame.draw writes
    straight into the alpha channel, which would punch see-through holes.)"""
    layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    pygame.draw.ellipse(layer, color, R(*rect))
    surf.blit(layer, (0, 0))


def outlined_ellipse(surf, fill, edge, rect, edge_w=1.4):
    x, y, w, h = rect
    ellipse(surf, edge, (x - edge_w, y - edge_w, w + 2 * edge_w, h + 2 * edge_w))
    ellipse(surf, fill, rect)


def poly(surf, color, pts, width=0):
    pygame.draw.polygon(surf, color, [P(*p) for p in pts], round(width * S) if width else 0)


def line(surf, color, a, b, width=1.5):
    pygame.draw.line(surf, color, P(*a), P(*b), max(1, round(width * S)))


def lines(surf, color, pts, width=1.5):
    pygame.draw.lines(surf, color, False, [P(*p) for p in pts], max(1, round(width * S)))


def arc(surf, color, rect, start, stop, width=1.5):
    pygame.draw.arc(surf, color, R(*rect), start, stop, max(1, round(width * S)))


def cut(surf, rect):
    """Make an elliptical area transparent."""
    pygame.draw.ellipse(surf, (0, 0, 0, 0), R(*rect))


def cut_poly(surf, pts):
    pygame.draw.polygon(surf, (0, 0, 0, 0), [P(*p) for p in pts])


def save(surf, layer, name, force):
    folder = AVATAR_DIR / layer
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if path.exists() and not force:
        return False
    pygame.image.save(pygame.transform.smoothscale(surf, (N, N)), str(path))
    return True


# ------------------------------------------------------------------- skin
SKIN = (250, 250, 250, 255)
SKIN_EDGE = (206, 206, 206, 255)
SKIN_SHADE = (0, 0, 0, 34)


def skin(head):
    s = new()
    outlined_ellipse(s, SKIN, SKIN_EDGE, (12, 96, 104, 90))          # shoulders
    outlined_ellipse(s, SKIN, SKIN_EDGE, (53, 74, 22, 32))           # neck
    blend_ellipse(s, SKIN_SHADE, (53, 78, 22, 9))                    # chin shadow
    hx, hy, hw, hh = head
    ear_y = hy + hh * 0.48
    outlined_ellipse(s, SKIN, SKIN_EDGE, (hx - 5, ear_y - 8, 11, 17))
    outlined_ellipse(s, SKIN, SKIN_EDGE, (hx + hw - 6, ear_y - 8, 11, 17))
    outlined_ellipse(s, SKIN, SKIN_EDGE, head)
    blend_ellipse(s, (255, 255, 255, 60), (hx + hw * 0.18, hy + hh * 0.1, hw * 0.35, hh * 0.25))  # highlight
    return s


# ---------------------------------------------------------------- clothes
CLOTH = (236, 236, 236, 255)
CLOTH_EDGE = (176, 176, 176, 255)
CLOTH_DARK = (196, 196, 196, 255)


def torso():
    s = new()
    outlined_ellipse(s, CLOTH, CLOTH_EDGE, (10, 97, 108, 90), 1.2)
    return s


def tee():
    s = torso()
    ellipse(s, CLOTH_EDGE, (50, 91, 28, 17))
    cut(s, (52.5, 92, 23, 14))
    return s


def hoodie():
    s = new()
    outlined_ellipse(s, CLOTH_DARK, CLOTH_EDGE, (34, 84, 60, 26), 1.2)   # hood rim behind the neck
    outlined_ellipse(s, CLOTH, CLOTH_EDGE, (10, 97, 108, 90), 1.2)
    ellipse(s, CLOTH_EDGE, (48, 90, 32, 19))
    cut(s, (51, 91, 26, 15))
    line(s, (150, 150, 150, 255), (58, 104), (57, 118), 1.6)
    line(s, (150, 150, 150, 255), (70, 104), (71, 118), 1.6)
    ellipse(s, (150, 150, 150, 255), (55.5, 117, 3.5, 3.5))
    ellipse(s, (150, 150, 150, 255), (69.5, 117, 3.5, 3.5))
    return s


def collar():
    s = torso()
    cut_poly(s, [(54, 95), (74, 95), (64, 108)])
    poly(s, (252, 252, 252, 255), [(52, 94), (63, 106), (56, 110), (47, 99)])
    poly(s, (252, 252, 252, 255), [(76, 94), (65, 106), (72, 110), (81, 99)])
    poly(s, CLOTH_EDGE, [(52, 94), (63, 106), (56, 110), (47, 99)], 0.8)
    poly(s, CLOTH_EDGE, [(76, 94), (65, 106), (72, 110), (81, 99)], 0.8)
    line(s, CLOTH_EDGE, (64, 108), (64, 128), 1.0)
    for y in (114, 122):
        ellipse(s, (150, 150, 150, 255), (62.6, y, 2.8, 2.8))
    return s


def vneck():
    s = torso()
    poly(s, CLOTH_EDGE, [(51, 93), (77, 93), (64, 113)])
    cut_poly(s, [(53.5, 93), (74.5, 93), (64, 109)])
    for x in (30, 98):
        line(s, (210, 210, 210, 255), (x, 108), (x + (6 if x < 64 else -6), 128), 1.0)
    return s


# ------------------------------------------------------------------- eyes
def brows(s, lift=0.0, thick=2.2, tilt=0.0):
    lines(s, BROW, [(45, 47 - lift + tilt), (51, 45 - lift), (58, 46 - lift)], thick)
    lines(s, BROW, [(70, 46 - lift), (77, 45 - lift), (83, 47 - lift + tilt)], thick)


def eyes_dots():
    s = new()
    brows(s)
    for x in (52, 76):
        ellipse(s, LINE, (x - 3.6, 53.5, 7.2, 7.6))
        ellipse(s, (255, 255, 255, 255), (x - 1.6, 54.6, 2.2, 2.2))
    return s


def eyes_round(iris=(78, 56, 42, 255)):
    s = new()
    brows(s, lift=1, thick=1.8)
    for x in (52, 76):
        ellipse(s, (255, 255, 255, 255), (x - 6, 52, 12, 9.5))
        arc(s, LINE, (x - 6, 51.5, 12, 10), 0.2, 2.94, 1.4)
        ellipse(s, iris, (x - 3.3, 53, 6.6, 7.2))
        ellipse(s, (20, 18, 20, 255), (x - 1.6, 54.8, 3.2, 3.6))
        ellipse(s, (255, 255, 255, 255), (x - 0.4, 54.2, 1.6, 1.6))
    return s


def eyes_happy():
    s = new()
    brows(s, lift=2, thick=2.0)
    for x in (52, 76):
        arc(s, LINE, (x - 5.5, 53, 11, 9), 0.25, 2.9, 2.0)
    return s


def eyes_sleepy():
    s = new()
    brows(s, lift=-0.5, thick=2.0, tilt=-1)
    for x in (52, 76):
        ellipse(s, (255, 255, 255, 255), (x - 6, 54, 12, 7))
        ellipse(s, (60, 44, 36, 255), (x - 3, 55.5, 6, 5.5))
        line(s, LINE, (x - 6.5, 55.2), (x + 6.5, 55.2), 1.8)
    return s


# ------------------------------------------------------------------- nose
NOSE = (0, 0, 0, 70)


def nose_curve():
    s = new()
    lines(s, NOSE, [(63, 60), (66.5, 67), (62, 69.5)], 1.7)
    return s


def nose_button():
    s = new()
    ellipse(s, (0, 0, 0, 34), (59, 63.5, 10, 7))
    ellipse(s, (0, 0, 0, 90), (60.5, 67.5, 2.6, 2))
    ellipse(s, (0, 0, 0, 90), (65, 67.5, 2.6, 2))
    return s


def nose_line():
    s = new()
    lines(s, NOSE, [(64.5, 57), (64.5, 67), (61.5, 69)], 1.6)
    return s


# ------------------------------------------------------------------ mouth
LIP = (132, 62, 62, 255)


def mouth_smile():
    s = new()
    arc(s, LIP, (55, 68, 18, 11), 3.6, 5.85, 2.1)
    return s


def mouth_grin():
    s = new()
    pygame.draw.ellipse(s, (96, 34, 38, 255), R(55, 71, 18, 10))
    cut(s, (53, 66, 22, 9))
    pygame.draw.rect(s, (255, 255, 255, 255), R(57, 75, 14, 2.6))
    return s


def mouth_neutral():
    s = new()
    line(s, LIP, (58, 77), (70, 77), 2.0)
    return s


def mouth_smirk():
    s = new()
    lines(s, LIP, [(57, 77), (64, 77.5), (71, 74)], 2.0)
    return s


# ------------------------------------------------------------------- hair
HAIR = (238, 238, 238, 255)
HAIR_EDGE = (186, 186, 186, 255)
STRAND = (205, 205, 205, 255)


def cap(s, top=15, hairline=40, width=68):
    """Basic hair cap: an ellipse with the face scooped out of the bottom."""
    x = 64 - width / 2
    outlined_ellipse(s, HAIR, HAIR_EDGE, (x, top, width, 50), 1.2)
    cut(s, (38, hairline, 52, 60))
    for dx in (-14, -4, 6, 16):
        arc(s, STRAND, (64 + dx - 10, top + 6, 20, 26), 1.9, 3.0, 1.1)


def hair_short():
    s = new()
    cap(s)
    poly(s, HAIR, [(38, 44), (36, 58), (39.5, 58), (41, 46)])
    poly(s, HAIR, [(90, 44), (92, 58), (88.5, 58), (87, 46)])
    return s


def hair_sidepart():
    s = new()
    cap(s, top=13)
    poly(s, HAIR, [(42, 38), (60, 30), (86, 36), (88, 46), (70, 40), (52, 44), (40, 50)])
    arc(s, HAIR_EDGE, (44, 28, 44, 26), 0.3, 2.6, 1.0)
    return s


def hair_curly():
    s = new()
    for cx, cy, r in [(44, 30, 11), (55, 22, 12), (68, 20, 12), (80, 26, 11), (88, 38, 9), (40, 42, 9),
                      (62, 28, 10)]:
        outlined_ellipse(s, HAIR, HAIR_EDGE, (cx - r, cy - r, 2 * r, 2 * r), 1.0)
    cut(s, (40, 41, 48, 56))
    for cx, cy in [(48, 26), (60, 20), (73, 22), (84, 31)]:
        arc(s, STRAND, (cx - 4, cy - 4, 8, 8), 0.5, 3.6, 1.0)
    return s


def hair_curly_back():
    s = new()
    outlined_ellipse(s, HAIR, HAIR_EDGE, (22, 8, 84, 80), 1.2)
    return s


def hair_bun():
    s = new()
    outlined_ellipse(s, HAIR, HAIR_EDGE, (52, 2, 24, 20), 1.2)
    arc(s, STRAND, (55, 5, 18, 14), 0.6, 2.6, 1.0)
    cap(s, top=15, hairline=38)
    return s


def hair_long():
    s = new()
    cap(s, top=14, hairline=39)
    poly(s, HAIR, [(38, 36), (34, 60), (36, 92), (44, 94), (43, 60), (46, 42)])
    poly(s, HAIR, [(90, 36), (94, 60), (92, 92), (84, 94), (85, 60), (82, 42)])
    lines(s, HAIR_EDGE, [(38, 36), (34, 60), (36, 92), (44, 94)], 1.0)
    lines(s, HAIR_EDGE, [(90, 36), (94, 60), (92, 92), (84, 94)], 1.0)
    return s


def hair_long_back():
    s = new()
    outlined_ellipse(s, HAIR, HAIR_EDGE, (30, 14, 68, 96), 1.2)
    pygame.draw.rect(s, (0, 0, 0, 0), R(0, 104, 128, 30))
    return s


def hair_ponytail():
    s = new()
    cap(s, top=15, hairline=39)
    return s


def hair_ponytail_back():
    s = new()
    outlined_ellipse(s, HAIR, HAIR_EDGE, (84, 30, 20, 52), 1.2)
    outlined_ellipse(s, (120, 120, 128, 255), (90, 90, 96, 255), (84, 30, 10, 8), 0.8)
    return s


def hair_bob():
    s = new()
    cap(s, top=14, hairline=37, width=72)
    poly(s, HAIR, [(36, 38), (32, 70), (40, 82), (45, 74), (44, 46)])
    poly(s, HAIR, [(92, 38), (96, 70), (88, 82), (83, 74), (84, 46)])
    poly(s, HAIR, [(40, 36), (64, 32), (88, 36), (84, 44), (64, 40), (44, 44)])
    return s


def hair_buzz():
    s = new()
    ellipse(s, (232, 232, 232, 170), (35, 19, 58, 44))
    cut(s, (38, 40, 52, 60))
    return s


# ------------------------------------------------------------ accessories
FRAME = (38, 38, 46, 255)


def glasses_round():
    s = new()
    for x in (52, 76):
        ellipse(s, (255, 255, 255, 46), (x - 8, 49.5, 16, 15))
        ellipse(s, FRAME, (x - 8, 49.5, 16, 15), 1.7)
    arc(s, FRAME, (59, 52, 10, 6), 0.3, 2.85, 1.6)
    line(s, FRAME, (44, 55), (37, 53), 1.6)
    line(s, FRAME, (84, 55), (91, 53), 1.6)
    return s


def glasses_square():
    s = new()
    for x in (52, 76):
        pygame.draw.rect(s, (255, 255, 255, 46), R(x - 8.5, 50.5, 17, 12), border_radius=round(3 * S))
        pygame.draw.rect(s, (120, 60, 50, 255), R(x - 8.5, 50.5, 17, 12), round(2.2 * S), border_radius=round(3 * S))
    line(s, (120, 60, 50, 255), (60, 54), (68, 54), 2.0)
    return s


def headset():
    s = new()
    arc(s, (60, 62, 72, 255), (30, 12, 68, 74), 0.05, 3.09, 3.2)
    for x in (27, 90):
        pygame.draw.rect(s, (52, 54, 64, 255), R(x, 47, 11, 20), border_radius=round(4 * S))
        pygame.draw.rect(s, (90, 94, 108, 255), R(x + 2, 50, 7, 14), border_radius=round(3 * S))
    lines(s, (52, 54, 64, 255), [(33, 66), (38, 76), (50, 80)], 2.0)
    ellipse(s, (30, 30, 34, 255), (48, 77.5, 6, 5))
    return s


def beanie():
    s = new()
    knit, dark = (212, 160, 64, 255), (176, 124, 44, 255)
    outlined_ellipse(s, knit, dark, (32, 10, 64, 50), 1.2)
    pygame.draw.rect(s, (0, 0, 0, 0), R(0, 40, 128, 40))
    pygame.draw.rect(s, dark, R(31, 33, 66, 10), border_radius=round(4 * S))
    for x in range(36, 94, 6):
        line(s, (196, 144, 54, 255), (x, 34), (x, 42), 1.0)
    outlined_ellipse(s, (240, 236, 226, 255), (210, 204, 190, 255), (58, 2, 12, 11), 1.0)
    return s


def earrings():
    s = new()
    for x in (33.5, 94.5):
        ellipse(s, (232, 190, 70, 255), (x - 2.5, 64, 5, 5))
        ellipse(s, (255, 236, 170, 255), (x - 1, 64.6, 2, 2))
    return s


def lanyard():
    s = new()
    strap = (64, 170, 120, 255)
    lines(s, strap, [(55, 97), (60, 116)], 2.6)
    lines(s, strap, [(73, 97), (68, 116)], 2.6)
    pygame.draw.rect(s, (250, 250, 250, 255), R(56, 114, 16, 14), border_radius=round(2 * S))
    pygame.draw.rect(s, strap, R(56, 114, 16, 4), border_top_left_radius=round(2 * S),
                     border_top_right_radius=round(2 * S))
    return s


# --------------------------------------------------------------- overlays
def tired():
    s = new()
    for x in (52, 76):
        arc(s, (90, 60, 90, 110), (x - 6, 58, 12, 7), 3.5, 5.9, 1.4)
    pygame.draw.polygon(s, (130, 200, 255, 220), [P(92, 34), P(89, 41), P(95, 41)])
    ellipse(s, (130, 200, 255, 220), (88.6, 38.5, 6.8, 6.8))
    return s


PIECES = {
    "skin": {"base_oval.png": lambda: skin((36, 22, 56, 64)),
             "base_round.png": lambda: skin((34, 24, 60, 60)),
             "base_long.png": lambda: skin((38, 19, 52, 68))},
    "clothes": {"tee.png": tee, "hoodie.png": hoodie, "collar_shirt.png": collar, "vneck.png": vneck},
    "eyes": {"dots.png": eyes_dots, "round_brown.png": eyes_round,
             "round_blue.png": lambda: eyes_round((70, 118, 170, 255)),
             "round_green.png": lambda: eyes_round((80, 130, 80, 255)),
             "happy.png": eyes_happy, "sleepy.png": eyes_sleepy},
    "nose": {"curve.png": nose_curve, "button.png": nose_button, "line.png": nose_line},
    "mouth": {"smile.png": mouth_smile, "grin.png": mouth_grin, "neutral.png": mouth_neutral,
              "smirk.png": mouth_smirk},
    "hair": {"short.png": hair_short, "side_part.png": hair_sidepart, "curly.png": hair_curly,
             "curly_back.png": hair_curly_back, "bun.png": hair_bun, "long.png": hair_long,
             "long_back.png": hair_long_back, "ponytail.png": hair_ponytail,
             "ponytail_back.png": hair_ponytail_back, "bob.png": hair_bob, "buzz.png": hair_buzz},
    "accessories": {"glasses_round.png": glasses_round, "glasses_square.png": glasses_square,
                    "headset.png": headset, "beanie_fixed.png": beanie, "earrings.png": earrings,
                    "lanyard.png": lanyard},
    "overlays": {"tired.png": tired},
}


def main():
    force = "--force" in sys.argv
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    written = 0
    for layer, pieces in PIECES.items():
        for name, fn in pieces.items():
            written += save(fn(), layer, name, force)
    print(f"Wrote {written} file(s) to {AVATAR_DIR}" + ("" if force else " (existing files kept; --force overwrites)"))


if __name__ == "__main__":
    main()
