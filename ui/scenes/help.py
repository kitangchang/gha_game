"""'How to play' overlay, shared by the title, planning and shift screens."""
from __future__ import annotations

import pygame

from game.data import get_data

from ..richtext import get_rich
from ..theme import RARITY, C, Fonts, H, W, render
from ..widgets import alpha_rect, draw_text, panel, wrap
from .common import rarity_gem, skill_pill

SECTIONS = [
    ("The job", "Run a virtual monitoring centre for a season. Each week you sort analysts into five teams, send "
     "worn-out people on leave and visit the shop. Then you survive seven days of real (or synthetic) earthquakes "
     "plus business-as-usual work. If public trust hits zero, the run is over."),
    ("Your centre", "Each save slot is a monitoring centre. Analysts belong to one run, but the centre keeps its XP: "
     "every week survived, SOP event handled and task done earns some, and finishing a season earns a lot. Centre "
     "levels unlock new tools, supplies and training in the shop."),
    ("Shifts", "Three 8-hour shifts a day: morning shift 0600–1400, late shift 1400–2200 and night shift 2200–0600. "
     "Each team works two mornings, two lates and two nights, then has four days off, so one team is on at a time. "
     "The Roster tab lets you move people between teams and override the grid for a week. Hover a team's box there "
     "for its week and average skills."),
    ("Ops room", "The red wall clocks show New Zealand time (left) and UTC (right). Below them: volcano webcams, the "
     "map, the seismic traces and the DARTS board. Your tools are listed above the SOP tracker on the right."),
    ("Money", "Funding arrives at the end of each week: a base grant plus bonuses for on-time work and public trust. "
     "Salaries come out weekly. Spend the rest on new analysts, tools (permanent), supplies (one use) and training."),
    ("Tasks", "Everything arrives in the INBOX on the left. Drag a card onto an analyst's desk to add it to their "
     "queue; drop it near the top to make it the next thing they do. Earthquakes above M2.7 have a quick PRELIM and a "
     "longer CONFIRM. The magnitude is fuzzy (~M) until the prelim is done, and exact after the confirm. Routine "
     "checks (webcams, tide gauges, handovers) arrive at set times every day."),
    ("Auto-assign", "Switch AUTO-ASSIGN on under the inbox header (or press A) and new tasks are handed out for you, "
     "using the rule you pick: balanced, fastest finish, lowest error, least fatigued or shortest queue. You can still "
     "drag and reorder; cards you pull back to the inbox are left for you."),
    ("SOPs", "Big events trigger SOP checklists (paging, tsunami assessment, EATs to NEMA, TEP, public comms). The game "
     "pauses when one fires. Locked steps can be queued in advance; follow-up steps like the EAT go straight to whoever "
     "did the assessment."),
    ("DART buoys", "Large quakes near a DART buoy put it into event mode (its column turns red on the wall). That adds "
     "'Assess DART signals' to the SOP that's running, or, if none is, starts a DART Trigger SOP: page the duty "
     "officers, assess the signals, then check the DART data every hour for six hours."),
    ("Trust", "Late tasks and errors cost trust; the more important the task, the more it costs. Small events barely "
     "matter, SOP steps matter a lot. Triage: do the big things first and let the M1.5s wait."),
    ("Analysts", "Skills set speed and error chance. Fatigue builds on shift (fastest on the night shift), slows people "
     "down and recovers on days off. Long-term fatigue creeps up with every shift and only drops with a week of leave. "
     "At 100 the analyst burns out and leaves for good."),
    ("Surprises", "'?' days bring a random event with a choice. Someone may call in sick for the next shift: a "
     "'Find staffing solution' task appears, and when it's done you pick who covers from the week's roster. Call in "
     "lets you add an off-duty analyst for overtime."),
    ("Controls", "Drag cards, or hover a card and press 1-6 to send it to that desk. Shift/Ctrl-click to select several. "
     "Right-click a queued card to send it back. Space = pause, +/- = speed, Tab = inbox sort, A = auto-assign, "
     "Esc = menu, H = this help, F5 = reload art, F11 = fullscreen/window."),
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
    label("EVERYTHING ELSE")
    cx = x + label_w
    for text, colour in (("Supplies", C.supply), ("Training", C.training), ("Good trait", C.good),
                         ("Bad trait", C.bad), ("SOP", C.sop), ("$ money", C.gold), ("Fatigue", C.warn),
                         ("Long-term fatigue", C.ltf)):
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
        key_h = KEY_ROW_H * 4 + 30
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
