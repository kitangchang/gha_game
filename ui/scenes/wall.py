"""The ops room wall: red LED clocks (NZ time and UTC) above four screens:
volcano webcams, the map (MapPanel in map_panel.py), seismic traces and DART
buoy status. Everything animates off the scene's screen clock, which stops while
the game is paused."""
from __future__ import annotations

import math
import random

import pygame

from game.tz import day_utc_offset
from game.util import fmt_clock

from ..theme import C, mix, render
from ..webcams import SUMMIT, get_webcams, plume
from ..widgets import TOOLTIP, draw_text, ellipsize

BEZEL = (30, 34, 42)
BEZEL_EDGE = (54, 60, 74)
SCREEN_BG = (8, 11, 16)
PLUME_TASKS = ("webcam_review", "volcanic_tremor", "unrest_assessment", "val_review", "hydro_check")
WHAKAARI_SHARE = 0.92          # share of volcano tasks that show on Whakaari; the rest are spread thinly
STATIONS = ["WEL  HHZ", "SNZO HHZ", "KHZ  HHZ", "BKZ  HHZ", "URZ  HHZ", "RAO  HHZ"]
DART_OK = (46, 170, 76)
DART_ALERT = (226, 52, 44)
LED_ON = (255, 46, 34)
LED_OFF = (36, 10, 10)
LED_HOUSING = (12, 12, 15)


def screen_frame(surf, rect, title: str = "", title_col=None):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, BEZEL, rect.inflate(10, 10), border_radius=7)
    pygame.draw.rect(surf, BEZEL_EDGE, rect.inflate(10, 10), 1, border_radius=7)
    pygame.draw.rect(surf, SCREEN_BG, rect, border_radius=3)
    if title:
        draw_text(surf, title, (rect.x + 6, rect.y + 4), 9, title_col or (96, 118, 128), "bold")


def screen_glare(surf, rect):
    """A faint diagonal reflection so the screens read as glass."""
    rect = pygame.Rect(rect)
    glare = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.polygon(glare, (255, 255, 255, 9), [(0, 0), (rect.width * 0.45, 0), (rect.width * 0.18, rect.height),
                                                    (0, rect.height)])
    surf.blit(glare, rect.topleft)


# ------------------------------------------------------------------- clocks
_SEGMENTS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
             "7": "abc", "8": "abcdefg", "9": "abcdfg"}
_LED_CACHE: dict = {}


def _digit_polys(x: float, y: float, w: float, h: float, t: float, slant: float) -> dict:
    """Segment polygons a-g of one seven-segment digit in the box (x, y, w, h)."""
    g = max(1.0, t * 0.22)                  # gap between segments

    def sx(px, py):                         # lean the digit forward a little
        return (px + (y + h - py) * slant, py)

    def horiz(cy):
        x0, x1 = x + t / 2 + g, x + w - t / 2 - g
        return [sx(x0, cy), sx(x0 + t / 2, cy - t / 2), sx(x1 - t / 2, cy - t / 2), sx(x1, cy),
                sx(x1 - t / 2, cy + t / 2), sx(x0 + t / 2, cy + t / 2)]

    def vert(cx, y0, y1):
        ya, yb = y0 + g, y1 - g
        return [sx(cx, ya), sx(cx + t / 2, ya + t / 2), sx(cx + t / 2, yb - t / 2), sx(cx, yb),
                sx(cx - t / 2, yb - t / 2), sx(cx - t / 2, ya + t / 2)]

    top, mid, bottom = y + t / 2, y + h / 2, y + h - t / 2
    left, right = x + t / 2, x + w - t / 2
    return {"a": horiz(top), "g": horiz(mid), "d": horiz(bottom), "f": vert(left, top, mid),
            "b": vert(right, top, mid), "e": vert(left, mid, bottom), "c": vert(right, mid, bottom)}


def led_clock(text: str, colon: bool, digit_h: int = 30) -> pygame.Surface:
    """A red seven-segment 'HH:MM' with unlit segments and a soft glow (cached)."""
    key = (text, colon, digit_h)
    img = _LED_CACHE.get(key)
    if img is not None:
        return img
    s = 3                                   # draw big, scale down for smooth edges
    dh = digit_h * s
    dw, t, gap, colon_w, slant = dh * 0.52, dh * 0.15, dh * 0.17, dh * 0.24, 0.07
    width = int(4 * dw + 4 * gap + colon_w + dh * slant + 2 * s)
    lit = pygame.Surface((width, dh + 2 * s), pygame.SRCALPHA)
    unlit = pygame.Surface(lit.get_size(), pygame.SRCALPHA)
    x = s
    for ch in text:
        if ch == ":":
            r = t * 0.62
            for fy in (0.32, 0.7):
                cy = s + dh * fy
                cx = x + colon_w / 2 + (s + dh - cy) * slant
                pts = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
                pygame.draw.polygon(lit if colon else unlit, LED_ON if colon else LED_OFF, pts)
            x += colon_w + gap
            continue
        on = _SEGMENTS.get(ch, "")
        for seg, pts in _digit_polys(x, s, dw, dh, t, slant).items():
            pygame.draw.polygon(lit if seg in on else unlit, LED_ON if seg in on else LED_OFF, pts)
        x += dw + gap
    size = (max(1, width // s), max(1, (dh + 2 * s) // s))
    face = pygame.transform.smoothscale(unlit, size)
    sharp = pygame.transform.smoothscale(lit, size)
    small = pygame.transform.smoothscale(lit, (max(1, size[0] // 3), max(1, size[1] // 3)))
    glow = pygame.transform.smoothscale(small, size)
    glow.fill((255, 255, 255, 120), special_flags=pygame.BLEND_RGBA_MULT)     # a soft, faint halo
    face.blit(glow, (0, 0))
    face.blit(sharp, (0, 0))
    if len(_LED_CACHE) > 256:
        _LED_CACHE.clear()
    _LED_CACHE[key] = face
    return face


def clock_times(scene) -> tuple:
    """('17:04', '04:04', utc_offset_hours) for the moment being replayed."""
    eng, data = scene.eng, scene.data
    cat = data.config["catalog"]
    day = eng.day_index
    minute = eng.now - eng.t0 - day * 1440.0
    offset = day_utc_offset(eng.plan.days[day].source, scene.day_start, minute,
                            bool(cat.get("nz_daylight_saving", True)), cat.get("utc_offset_hours", 12))
    total = math.floor(scene.day_start * 60 + minute - offset * 60) % 1440
    return eng.clock(), f"{total // 60:02d}:{total % 60:02d}", offset


def draw_clocks(scene, surf, rect, mouse):
    """Two wall clocks above the screens: NZ time on the left, UTC on the right."""
    rect = pygame.Rect(rect)
    nz, utc, offset = clock_times(scene)
    colon = (scene.screen_t % 1.0) < 0.5
    faces = [led_clock(nz, colon), led_clock(utc, colon)]
    pad_x, gap = 14, 18
    box_w = max(f.get_width() for f in faces) + 2 * pad_x
    box_h = rect.height
    x = rect.centerx - box_w - gap // 2
    zone = "NZDT" if offset == 13 else "NZST" if offset == 12 else f"UTC+{offset:g}"
    tips = [[("New Zealand time", C.text, 13, "bold"), (f"{zone} · UTC+{offset:g}", C.faint, 11)],
            [("UTC", C.text, 13, "bold"), (f"New Zealand is {offset:g} hours ahead today.", C.faint, 11)]]
    for face, tip in zip(faces, tips):
        box = pygame.Rect(x, rect.y, box_w, box_h)
        pygame.draw.rect(surf, (6, 6, 8), box.inflate(6, 6), border_radius=8)
        pygame.draw.rect(surf, LED_HOUSING, box, border_radius=6)
        pygame.draw.rect(surf, (46, 48, 56), box, 1, border_radius=6)
        surf.blit(face, face.get_rect(center=box.center))
        if box.collidepoint(mouse):
            TOOLTIP.set(tip, 240)
        x += box_w + gap


# ------------------------------------------------------------------ webcams
def plume_camera(task_id: int, main: int, count: int) -> int:
    """Which webcam a volcano task shows on: nearly always Whakaari, which steams
    all the time; the other volcanoes only now and then."""
    rng = random.Random(task_id * 7919 + 13)
    if count <= 1 or rng.random() < WHAKAARI_SHARE:
        return main
    others = [i for i in range(count) if i != main]
    return others[rng.randrange(len(others))]


def volcano_alerts(eng, bank) -> dict:
    """cam index -> open volcano task that 'shows' on that camera."""
    out = {}
    main = bank.primary_index()
    count = min(6, len(bank.cams))
    for tid in sorted(eng.open_ids):
        t = eng.tasks.get(tid)
        if t is None or t.done or t.hidden or t.type not in PLUME_TASKS:
            continue
        out.setdefault(plume_camera(t.id, main, count), t)
    return out


def draw_cams(scene, surf, rect, mouse):
    eng = scene.eng
    rect = pygame.Rect(rect)
    screen_frame(surf, rect)
    bank = get_webcams()
    if bank is None:
        return
    hour = ((eng.now / 60.0) + scene.day_start) % 24
    alerts = volcano_alerts(eng, bank)
    pad, gap = 4, 3
    cw = (rect.width - 2 * pad - 2 * gap) // 3
    ch = (rect.height - 2 * pad - gap) // 2
    clock = fmt_clock(eng.now, scene.day_start)
    hovered = None
    for i in range(6):
        col, row = i % 3, i // 3
        cell = pygame.Rect(rect.x + pad + col * (cw + gap), rect.y + pad + row * (ch + gap), cw, ch)
        surf.blit(bank.frame(i, cell.size, hour), cell.topleft)
        task = alerts.get(i)
        if task is not None:
            plume(surf, cell.x + cell.width * SUMMIT[0], cell.y + cell.height * SUMMIT[1], scene.screen_t,
                  scale=cell.height / 90.0)
        shade = pygame.Surface((cell.width, 13), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 120))
        surf.blit(shade, (cell.x, cell.bottom - 13))
        label = ellipsize(bank.label(i).upper(), 8, "bold", cell.width - 6)
        surf.blit(render(label, 8, (226, 230, 236), "bold"), (cell.x + 3, cell.bottom - 12))
        top = pygame.Surface((cell.width, 12), pygame.SRCALPHA)
        top.fill((0, 0, 0, 90))
        surf.blit(top, cell.topleft)
        surf.blit(render(clock, 8, (226, 230, 236), "semibold"), (cell.x + 3, cell.y + 1))
        if int(scene.screen_t * 1.2 + i * 0.37) % 2 == 0:
            pygame.draw.circle(surf, (230, 60, 50), (cell.right - 6, cell.y + 6), 2)
        if task is not None:
            pygame.draw.rect(surf, C.warn, cell, 1)
        if cell.collidepoint(mouse):
            hovered = (i, task)
    screen_glare(surf, rect)
    if hovered is not None:
        i, task = hovered
        lines = [(f"{bank.label(i)} webcam", C.text, 13, "bold"),
                 ("Night view" if bank.light(hour) < 0.5 else "Daylight", C.faint, 11)]
        if task is not None:
            lines.append((f"Open task: {task.name}", C.warn, 12))
            if task.desc:
                lines.append((task.desc, C.dim, 12))
        lines.append(("Images: assets/webcams/ (F5 reloads)", C.faint, 11))
        TOOLTIP.set(lines, 280)


# ------------------------------------------------------------------- traces
def draw_traces(scene, surf, rect):
    rect = pygame.Rect(rect)
    screen_frame(surf, rect, "SEISMIC TRACES")
    t = scene.screen_t
    rows = len(STATIONS)
    top = rect.y + 18
    row_h = (rect.height - 22) / rows
    clip = surf.get_clip()
    surf.set_clip(rect.inflate(-4, -4))
    for s, label in enumerate(STATIONS):
        cy = top + row_h * (s + 0.5)
        pygame.draw.line(surf, (18, 30, 30), (rect.x + 4, cy), (rect.right - 4, cy))
        pts = []
        amp = scene.activity * (0.6 + 0.4 * math.sin(s * 1.7))
        width = rect.width - 52
        front = (t * 70 + s * 34) % (width + 80)
        for i in range(0, int(width), 2):
            x = rect.x + 48 + i
            k = i * 0.23 + t * (6 + s) + s * 3.1
            wig = math.sin(k) * 1.1 + math.sin(k * 2.7 + s) * 0.8
            burst = amp * math.sin(i * 0.9 + t * 23) * math.exp(-((i - front) / 24.0) ** 2)
            pts.append((x, cy + wig + max(-row_h * 0.45, min(row_h * 0.45, burst))))
        if len(pts) > 1:
            pygame.draw.aalines(surf, (90, 210, 140), False, pts)
        surf.blit(render(label, 8, (70, 120, 96), "bold"), (rect.x + 5, cy - 5))
    surf.set_clip(clip)
    screen_glare(surf, rect)


# --------------------------------------------------------------------- DART
def draw_dart(scene, surf, rect, mouse):
    eng, data = scene.eng, scene.data
    rect = pygame.Rect(rect)
    screen_frame(surf, rect, "DARTS")
    buoys = data.dart_buoys
    n = max(1, len(buoys))
    rows = 7
    pad_x, gap = 8, 3
    head_y = rect.y + 20
    area_top, area_bottom = rect.y + 38, rect.bottom - 22
    cell = max(4, int((rect.width - 2 * pad_x - (n - 1) * gap) / n))
    cell_h = max(4, min(int(cell * 1.35), int((area_bottom - area_top - (rows - 1) * gap) / rows)))
    grid_w = n * cell + (n - 1) * gap
    grid_h = rows * cell_h + (rows - 1) * gap
    x0 = rect.x + (rect.width - grid_w) // 2
    top = area_top + (area_bottom - area_top - grid_h) // 2
    hovered = None
    alerts = 0
    for c, b in enumerate(buoys):
        x = x0 + c * (cell + gap)
        active = eng.dart_active(b["code"])
        alerts += active
        head_col = DART_ALERT if active else (150, 196, 160)
        draw_text(surf, b["code"], (x + cell // 2, head_y), 10, head_col, "bold", anchor="midtop")
        for r in range(rows):
            sq = pygame.Rect(x, top + r * (cell_h + gap), cell, cell_h)
            if active:
                blink = r == 0 and int(scene.screen_t * 2) % 2 == 0
                col = (255, 120, 110) if blink else DART_ALERT
            else:
                col = DART_OK
            pygame.draw.rect(surf, col, sq, border_radius=2)
        column = pygame.Rect(x - 2, head_y - 2, cell + 4, top + grid_h - head_y + 4)
        if column.collidepoint(mouse):
            hovered = b
            pygame.draw.rect(surf, (230, 236, 240), column, 1, border_radius=3)
    if alerts:
        names = ", ".join(b["id"] for b in buoys if eng.dart_active(b["code"]))
        status, col = (f"EVENT MODE: {names}" if alerts <= 3 else f"{alerts} BUOYS IN EVENT MODE"), DART_ALERT
    else:
        status, col = f"ALL {n} REPORTING", (110, 190, 130)
    draw_text(surf, status, (rect.centerx, rect.bottom - 16), 9, col, "bold", anchor="midtop", max_width=rect.width - 12)
    screen_glare(surf, rect)
    if hovered is not None:
        TOOLTIP.set(dart_tooltip(scene, hovered), 300)


def dart_tooltip(scene, b) -> list:
    eng = scene.eng
    lines = [(f"DART {b['id']} · {b['name']}", C.text, 13, "bold"),
             (f"{abs(b['lat']):.1f}°S {b['lon'] if b['lon'] <= 180 else b['lon'] - 360:.1f}°", C.faint, 11)]
    if eng.dart_active(b["code"]):
        start, uid = eng.dart_last.get(b["code"], (eng.now, None))
        ev = eng.events.get(uid) if uid is not None else None
        lines.append((f"Event mode since {fmt_clock(start, scene.day_start)}, until "
                      f"{fmt_clock(eng.dart_until[b['code']], scene.day_start)}", mix(DART_ALERT, C.text, 0.3), 12))
        if ev is not None:
            lines.append((f"Set off by {ev.mag_label()} {ev.description}", C.dim, 12))
    else:
        lines.append(("Normal reporting", (120, 200, 140), 12))
    lines.append(("Big quakes nearby put a buoy into event mode. A trigger adds 'Assess DART signals' to the "
                  "running SOP, or starts the DART Trigger SOP.", C.faint, 11))
    return lines
