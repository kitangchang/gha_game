"""'How to play' overlay, shared by the title, planning and shift screens."""
from __future__ import annotations

import pygame

from game.data import get_data

from ..richtext import get_rich
from ..theme import RARITY, C, Fonts, H, W, render
from ..widgets import TOOLTIP, alpha_rect, draw_text, panel, wrap
from .common import rarity_gem, skill_pill

SECTIONS = [
    ("The job", "Run a monitoring centre for a season. Plan your roster and shop between weeks, then get through "
     "seven days of quakes and routine work. Lose all public trust and the run ends."),
    ("Your centre", "Your centre keeps its XP between runs. Survive weeks, handle SOPs and finish seasons to level up "
     "and unlock new shop items."),
    ("Shifts", "There are 3 shifts a day, Mornings run 0600-1400, lates 1400-2200 and nights 2200-0600. Each team works two of each, then gets "
     "four days off. Use the Roster tab to move people between teams."),
    ("Money", "Funding arrives at the end of each week, with bonuses for on-time work and high trust."),
    ("Tasks", "Drag cards from the INBOX onto a desk. Drop them near the top to jump the queue. Quakes above M2.7 "
     "need a PRELIM, then a CONFIRM. The magnitude stays fuzzy until the prelim is done."),
    ("Auto-assign", "Key: [A] Hands out new tasks automatically, using the rule you pick. You can still drag cards "
     "around yourself."),
    ("SOPs", "Big quakes start an SOP checklist and pause the game. Some steps will be locked until their prerequisites "
     "are completed."),
    ("DART buoys", "A big quake near a buoy will activate it, turning its column red. This starts the DART SOP. There are"
     "12 DARTS around NZ"),
    ("Trust", "Overdue work and errors cost trust, and important tasks cost more. Prioritise the important stuff."),
    ("Analysts", "Skills set speed and accuracy. Fatigue builds on shift and recovers when off. Fatigue can only recover up to half of long-term fatigue.  Long-term fatigue "
     "only drops with a week of leave. At 100, they quit."),
    ("Boss days", "The final day of the week is always a boss day, usually a big quake or a swarm."
     "Each week you will be rewarded with a choice of rare item"),
    ("Tags", "Traits, tools and supplies carry tags (e.g., Science). Some tools get stronger with every "
     "matching tag."),
    ("Surprises", "'?' days bring a random event. If someone calls in sick, there will be a staffing cover task. "
     "Use Call in to bring in someone on overtime at any time."),
    ("Controls", "Drag cards, or hover one and press 1-6 to send it to a desk. Shift/Ctrl-click selects several. "
     "Right-click sends one back. Space pause, +/- speed, Tab sort, A auto-assign, Esc menu, H help, F5 reload art, "
     "F11 fullscreen."),
]
KEY_ROW_H = 26
LABEL_W = 150


def _plain_block(text: str, size: int, colour, width: int) -> pygame.Surface:
    rows = wrap(text, size, "regular", width)
    lh = Fonts.get(size).get_linesize()
    img = pygame.Surface((width, max(1, lh * len(rows))), pygame.SRCALPHA)
    for i, row in enumerate(rows):
        img.blit(render(row, size, colour), (0, i * lh))
    return img


def draw_colour_key(surf, x: int, y: int, label_w: int = LABEL_W) -> int:
    """Legend of the colours used for skills, teams, tool rarity and the rest. Returns the height."""
    data = get_data()
    top = y

    def label(text):
        draw_text(surf, text, (x, y + 4), 11, C.faint, "bold")

    def entry(cx, text, colour, weight="semibold"):
        r = draw_text(surf, text, (cx, y + 3), 13, colour, weight)
        return r.right + 18

    label("SKILLS")
    cx = x + label_w
    for sk in data.skills:
        r = skill_pill(surf, (cx, y + 3), sk["key"], data, size=10)
        cx = entry(r.right + 6, sk["name"], sk["color"])
    y += KEY_ROW_H
    label("TEAMS")
    cx = x + label_w
    for team in data.teams:
        pygame.draw.circle(surf, team["color"], (cx + 5, y + 12), 5)
        cx = entry(cx + 15, f"{team['name']} team", team["color"])
    pygame.draw.circle(surf, data.bench_color, (cx + 5, y + 12), 5)
    cx = entry(cx + 15, "Bench", data.bench_color)
    pygame.draw.circle(surf, data.leave_color, (cx + 5, y + 12), 5)
    entry(cx + 15, "On leave", data.leave_color)
    y += KEY_ROW_H
    label("TOOL RARITY")
    cx = x + label_w
    for rarity, colour in RARITY.items():
        rarity_gem(surf, (cx + 6, y + 12), rarity, 6)
        cx = entry(cx + 18, rarity.title(), colour)
    y += KEY_ROW_H
    label("TAGS (AND TRAITS)")
    cx = x + label_w
    for tag in data.tags.values():
        cx = entry(cx, tag["name"], tag["color"])
    y += KEY_ROW_H
    label("EVERYTHING ELSE")
    cx = x + label_w
    for text, colour in (("Supplies", C.supply), ("Training", C.training), ("SOP", C.sop), ("$ money", C.gold),
                         ("Fatigue", C.warn), ("Long-term fatigue", C.ltf)):
        cx = entry(cx, text, colour)
    y += KEY_ROW_H
    return y - top


class HelpOverlay:
    def __init__(self):
        self.visible = False

    def toggle(self):
        self.visible = not self.visible

    def handle(self, event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN or (event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3)):
            self.visible = False
        return True

    def _layout(self, width: int):
        rt = get_rich()
        body_w = width - 64 - LABEL_W
        key_h = KEY_ROW_H * 5 + 30
        for size in (14, 13, 12):
            if rt is not None:
                blocks = [rt.block(body, size, C.text, body_w, line_gap=4) for _, body in SECTIONS]
            else:
                blocks = [_plain_block(body, size, C.text, body_w) for _, body in SECTIONS]
            height = 76 + sum(b.get_height() + 12 for b in blocks) + key_h + 44
            if height <= H - 24:
                break
        return blocks, height

    def draw(self, surf):
        if not self.visible:
            return
        TOOLTIP.clear()             # nothing underneath should show a tooltip through the overlay
        alpha_rect(surf, (0, 0, W, H), (5, 8, 12, 200))
        width = 1440
        blocks, height = self._layout(width)
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (W // 2, H // 2)
        panel(surf, rect, C.panel, C.border2, radius=12)
        draw_text(surf, "How to play", (rect.x + 32, rect.y + 22), 28, C.text, "bold")
        y = rect.y + 76
        for (title, _), block in zip(SECTIONS, blocks):
            draw_text(surf, title.upper(), (rect.x + 32, y + 2), 12, C.accent, "bold")
            surf.blit(block, (rect.x + 32 + LABEL_W, y))
            y += block.get_height() + 12
        pygame.draw.line(surf, C.border, (rect.x + 32, y + 6), (rect.right - 32, y + 6))
        draw_text(surf, "COLOUR KEY", (rect.x + 32, y + 16), 12, C.accent, "bold")
        draw_colour_key(surf, rect.x + 32, y + 36)
        draw_text(surf, "Click or press any key to close", (rect.centerx, rect.bottom - 22), 13, C.faint,
                  anchor="center")
