"""Drawing helpers, buttons and the tooltip."""
from __future__ import annotations

import math

import pygame

from .theme import C, Fonts, render, text_width


# ----------------------------------------------------------------------- text
def ellipsize(text: str, size: int, weight: str, width: int) -> str:
    if width <= 0:
        return ""
    if text_width(text, size, weight) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(text[:mid].rstrip() + "…", size, weight) <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def draw_text(surf, text: str, pos, size: int = 14, color=C.text, weight: str = "regular",
              anchor: str = "topleft", max_width: int | None = None) -> pygame.Rect:
    if max_width is not None:
        text = ellipsize(text, size, weight, max_width)
    img = render(text, size, color, weight)
    rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    surf.blit(img, rect)
    return rect


def wrap(text: str, size: int, weight: str, width: int) -> list:
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        line = ""
        for word in words:
            trial = word if not line else f"{line} {word}"
            if text_width(trial, size, weight) <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def draw_wrapped(surf, text: str, rect, size: int = 14, color=C.text, weight: str = "regular",
                 line_gap: int = 3, max_lines: int | None = None, rich: bool = False) -> int:
    rect = pygame.Rect(rect)
    if rich and weight == "regular":
        from .richtext import get_rich
        rt = get_rich()
        if rt is not None:
            return rt.draw(surf, text, rect.topleft, size, color, rect.width, max_lines, line_gap)
    lines = wrap(text, size, weight, rect.width)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = ellipsize(lines[-1] + "…", size, weight, rect.width)
    y = rect.y
    h = Fonts.get(size, weight).get_linesize()
    for line in lines:
        draw_text(surf, line, (rect.x, y), size, color, weight)
        y += h + line_gap - 4
    return y - rect.y


# --------------------------------------------------------------------- shapes
def panel(surf, rect, fill=C.panel, border=C.border, radius: int = 8, width: int = 1):
    rect = pygame.Rect(rect)
    if fill is not None:
        pygame.draw.rect(surf, fill, rect, border_radius=radius)
    if border is not None and width > 0:
        pygame.draw.rect(surf, border, rect, width, border_radius=radius)


def alpha_rect(surf, rect, color, radius: int = 0):
    rect = pygame.Rect(rect)
    if rect.width <= 0 or rect.height <= 0:
        return
    tmp = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(tmp, color, tmp.get_rect(), border_radius=radius)
    surf.blit(tmp, rect.topleft)


def alpha_circle(surf, color, center, radius: int, width: int = 0):
    if radius <= 0:
        return
    size = radius * 2 + 4
    tmp = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(tmp, color, (size // 2, size // 2), radius, width)
    surf.blit(tmp, (int(center[0]) - size // 2, int(center[1]) - size // 2))


def bar(surf, rect, frac: float, color, bg=C.panel3, radius: int = 3):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, bg, rect, border_radius=radius)
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        fill = pygame.Rect(rect.x, rect.y, max(2, int(rect.width * frac)), rect.height)
        pygame.draw.rect(surf, color, fill, border_radius=radius)


def pill(surf, text: str, pos, fg=C.text, bg=C.panel3, size: int = 11, weight: str = "semibold",
         pad_x: int = 6, pad_y: int = 2, anchor: str = "topleft") -> pygame.Rect:
    img = render(text, size, fg, weight)
    rect = pygame.Rect(0, 0, img.get_width() + pad_x * 2, img.get_height() + pad_y * 2)
    setattr(rect, anchor, (int(pos[0]), int(pos[1])))
    pygame.draw.rect(surf, bg, rect, border_radius=rect.height // 2)
    surf.blit(img, (rect.x + pad_x, rect.y + pad_y))
    return rect


def avatar(surf, center, radius: int, color, initials: str, ring=None, dim=False):
    col = tuple(int(c * 0.55) for c in color) if dim else color
    pygame.draw.circle(surf, col, center, radius)
    if ring is not None:
        pygame.draw.circle(surf, ring, center, radius + 2, 2)
    size = max(9, int(radius * 0.8))
    draw_text(surf, initials, center, size, C.bg if not dim else C.dim, "bold", anchor="center")


def pips(surf, pos, value: int, maximum: int = 5, color=C.accent, size: int = 5, gap: int = 2, off=C.panel3):
    x, y = pos
    for i in range(maximum):
        pygame.draw.rect(surf, color if i < value else off, (x + i * (size + gap), y, size, size), border_radius=1)
    return maximum * (size + gap)


def lock_icon(surf, center, size: int = 10, color=C.faint):
    cx, cy = center
    body = pygame.Rect(0, 0, size, int(size * 0.75))
    body.center = (cx, cy + size // 5)
    pygame.draw.rect(surf, color, body, border_radius=2)
    pygame.draw.arc(surf, color, (cx - size // 3, cy - size // 2 - 1, size * 2 // 3, size * 2 // 3 + 2),
                    0, math.pi, 2)


def check_icon(surf, center, size: int = 10, color=C.good):
    cx, cy = center
    pts = [(cx - size // 2, cy), (cx - size // 8, cy + size // 3), (cx + size // 2, cy - size // 3)]
    pygame.draw.lines(surf, color, False, pts, 2)


def warn_icon(surf, center, size: int = 12, color=C.warn):
    cx, cy = center
    pts = [(cx, cy - size // 2), (cx + size // 2, cy + size // 2), (cx - size // 2, cy + size // 2)]
    pygame.draw.polygon(surf, color, pts)
    draw_text(surf, "!", (cx, cy + 2), max(8, size - 3), C.bg, "bold", anchor="center")


# -------------------------------------------------------------------- tooltip
TIP_BG = (20, 25, 34)


class Tooltip:
    """Lines are (text, colour, size, weight) tuples, plain strings, ready-drawn
    pygame Surfaces (skill boxes, schedule strips) that are blitted as they are,
    or an int for an extra gap of that many pixels."""

    def __init__(self):
        self.lines: list | None = None
        self.width = 300

    def set(self, lines, width: int = 300):
        if isinstance(lines, str):
            lines = [lines]
        self.lines = lines
        self.width = width

    def clear(self):
        self.lines = None

    def draw(self, surf, mouse):
        if not self.lines:
            return
        from .richtext import get_rich
        rt = get_rich()
        inner = self.width - 20
        blocks = []
        for item in self.lines:
            if isinstance(item, pygame.Surface):
                blocks.append(item)
                continue
            if isinstance(item, int) and not isinstance(item, bool):      # vertical gap in pixels
                blocks.append(pygame.Surface((1, max(0, item - 2)), pygame.SRCALPHA))
                continue
            if isinstance(item, (tuple, list)):
                text = item[0]
                color = item[1] if len(item) > 1 else C.text
                size = item[2] if len(item) > 2 else 13
                weight = item[3] if len(item) > 3 else "regular"
            else:
                text, color, size, weight = item, C.text, 13, "regular"
            if not text:
                continue
            if rt is not None and weight == "regular":
                blocks.append(rt.block(text, size, color, inner))
            else:
                rows = wrap(text, size, weight, inner)
                lh = Fonts.get(size, weight).get_linesize()
                img = pygame.Surface((inner, lh * len(rows)), pygame.SRCALPHA)
                for i, row in enumerate(rows):
                    img.blit(render(row, size, color, weight), (0, i * lh))
                blocks.append(img)
        h = sum(b.get_height() + 2 for b in blocks) + 14
        rect = pygame.Rect(mouse[0] + 16, mouse[1] + 18, self.width, h)
        sw, sh = surf.get_size()
        if rect.right > sw - 6:
            rect.right = mouse[0] - 12
        if rect.bottom > sh - 6:
            rect.bottom = sh - 6
        rect.left = max(6, rect.left)
        rect.top = max(6, rect.top)
        alpha_rect(surf, rect.inflate(6, 6), (0, 0, 0, 90), radius=10)
        panel(surf, rect, TIP_BG, C.border2, radius=8)
        y = rect.y + 8
        for b in blocks:
            surf.blit(b, (rect.x + 10, y))
            y += b.get_height() + 2


TOOLTIP = Tooltip()


# --------------------------------------------------------------------- button
class Button:
    STYLES = {
        "primary": ((52, 128, 186), (64, 148, 210), C.white),
        "secondary": (C.panel3, C.hover, C.text),
        "ghost": (C.panel2, C.panel3, C.dim),
        "danger": ((150, 52, 46), (180, 64, 56), C.white),
        "good": ((60, 128, 64), (72, 150, 76), C.white),
    }

    def __init__(self, rect, label: str, on_click=None, style: str = "secondary", size: int = 14,
                 enabled: bool = True, tooltip=None, sublabel: str = "", selected: bool = False, color=None):
        self.rect = pygame.Rect(rect)
        self.color = color          # optional label colour (e.g. supplies are pink)
        self.label = label
        self.on_click = on_click
        self.style = style
        self.size = size
        self.enabled = enabled
        self.tooltip = tooltip
        self.sublabel = sublabel
        self.selected = selected

    def draw(self, surf, mouse):
        base, hover, fg = self.STYLES.get(self.style, self.STYLES["secondary"])
        if self.color is not None:
            fg = self.color
        over = self.rect.collidepoint(mouse)
        if not self.enabled:
            fill, fg = C.panel2, C.faint
        elif self.selected:
            fill = (52, 128, 186)
            fg = C.white
        else:
            fill = hover if over else base
        pygame.draw.rect(surf, fill, self.rect, border_radius=7)
        if self.selected or (over and self.enabled):
            pygame.draw.rect(surf, C.border2, self.rect, 1, border_radius=7)
        if self.sublabel:
            draw_text(surf, self.label, (self.rect.x + 12, self.rect.y + 8), self.size, fg, "semibold",
                      max_width=self.rect.width - 24)
            from .richtext import get_rich
            rt = get_rich()
            sub_pos = (self.rect.x + 12, self.rect.y + 8 + self.size + 6)
            sub_col = C.dim if self.enabled else C.faint
            if rt is not None and self.enabled:
                rt.draw_line(surf, self.sublabel, sub_pos, 12, sub_col, self.rect.width - 24)
            else:
                draw_text(surf, self.sublabel, sub_pos, 12, sub_col, max_width=self.rect.width - 24)
        else:
            draw_text(surf, self.label, self.rect.center, self.size, fg, "semibold", anchor="center",
                      max_width=self.rect.width - 10)
        if over and self.tooltip:
            TOOLTIP.set(self.tooltip)

    def handle(self, event) -> bool:
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.enabled
                and self.rect.collidepoint(event.pos)):
            if self.on_click:
                self.on_click()
            return True
        return False
