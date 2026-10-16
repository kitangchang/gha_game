"""Colour-coded text. Descriptions anywhere in the UI get skills, rarities, tool,
supply, training and trait names, teams, SOPs, trust, fatigue and money
highlighted in their colours, with no markup needed in the data files."""
from __future__ import annotations

import re
from collections import OrderedDict

import pygame

from .theme import C, RARITY, TRAIT_COLOURS, Fonts, mix, render, text_width

_RICH: "RichText | None" = None


def get_rich() -> "RichText | None":
    return _RICH


def init_rich(data) -> "RichText":
    global _RICH
    _RICH = RichText(data)
    return _RICH


class RichText:
    def __init__(self, data):
        rules = []    # (regex, colour, case_insensitive)

        def literal(text, colour, ci=False):
            rules.append((re.escape(text), colour, ci))

        for sk in data.skills:
            literal(sk["name"], sk["color"], True)
            literal(sk["abbr"], sk["color"])
        seismic = data.skill_by_key.get("seismic", {}).get("color", C.accent)
        rules.append((r"earthquakes?|quakes?", seismic, True))
        for rarity, colour in RARITY.items():
            literal(rarity.title(), colour)
            literal(rarity.upper(), colour)
        for relic in data.relics.values():
            literal(relic["name"], RARITY.get(relic["rarity"], C.text))
        for c in data.consumables.values():
            literal(c["name"], C.supply)
        for t in data.training.values():
            literal(t["name"], C.training)
        for t in data.traits.values():
            tags = t.get("tags") or []
            colour = data.tags[tags[0]]["color"] if tags and tags[0] in data.tags else \
                TRAIT_COLOURS.get(t.get("kind", "good"), C.good)
            literal(t["name"], colour)
        for tag in getattr(data, "tags", {}).values():
            rules.append((re.escape(tag["name"]) + r" tags?", tag["color"], True))
        for team in data.teams:
            name = team["name"]
            for form in (f"{name} team", f"Team {name}", f"{name.upper()} TEAM", name):
                literal(form, team["color"])
        for shift in data.shifts:
            rules.append((re.escape(shift["name"]) + r" shifts?", shift["color"], True))
        rules.append((r"SOPs?", C.sop, False))
        rules.append((r"long-term fatigue", C.ltf, True))
        rules.append((r"fatigue", C.warn, True))
        rules.append((r"public trust|trust", C.trust, True))
        rules.append((r"[+\-]?\$\d+(?:\.\d+)?k", C.gold, False))
        rules.sort(key=lambda r: -len(r[0]))
        parts = []
        self.colours = [None]
        for pattern, colour, ci in rules:
            body = f"(?i:{pattern})" if ci else pattern
            parts.append(f"(?<![\\w$])({body})(?![\\w])")
            self.colours.append(tuple(colour))
        self.regex = re.compile("|".join(parts))
        self._blocks: OrderedDict = OrderedDict()

    # --------------------------------------------------------------- tokenise
    def tokens(self, text: str, colour) -> list:
        """[(text, colour, weight, space_before)] word by word."""
        out: list = []
        trailing = [False]    # did the previous chunk end in a space?

        def add(chunk, col, weight):
            i, n = 0, len(chunk)
            space = trailing[0]
            while i < n:
                while i < n and chunk[i] == " ":
                    space = True
                    i += 1
                if i >= n:
                    break
                j = i
                while j < n and chunk[j] != " ":
                    j += 1
                out.append((chunk[i:j], col, weight, space))
                space = False
                i = j
            trailing[0] = space

        pos = 0
        for m in self.regex.finditer(text):
            if m.start() > pos:
                add(text[pos:m.start()], colour, "regular")
            colour_kw = self.colours[m.lastindex] if m.lastindex else colour
            add(m.group(0), colour_kw, "semibold")
            pos = m.end()
        if pos < len(text):
            add(text[pos:], colour, "regular")
        return out

    def layout(self, text: str, size: int, colour, width: int, max_lines: int | None = None) -> list:
        lines: list = []
        for para in str(text).split("\n"):
            line: list = []
            x = 0
            space_w = text_width(" ", size)
            group = 0               # where the current unbreakable run of tokens starts in `line`
            for word, col, weight, space in self.tokens(para, colour):
                w = text_width(word, size, weight)
                gap = space_w if (space and line) else 0
                if space or not line:
                    group = len(line)
                if line and x + gap + w > width:
                    if space:
                        lines.append(line)
                        line, x, gap, group = [], 0, 0, 0
                    elif group > 0:
                        # e.g. "(Volcano" - take the whole run to the next line, not just this piece
                        carry = line[group:]
                        lines.append(line[:group])
                        base = carry[0][3]
                        line = [[t[0], t[1], t[2], t[3] - base] for t in carry]
                        x -= base
                        group = 0
                line.append([word, col, weight, x + gap])
                x += gap + w
            lines.append(line)
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            ell = text_width("…", size)
            while last and last[-1][3] + text_width(last[-1][0], size, last[-1][2]) + ell > width:
                last.pop()
            if last:
                last[-1][0] = last[-1][0] + "…"
        return lines

    # ----------------------------------------------------------------- render
    def block(self, text: str, size: int = 13, colour=C.text, width: int = 300, max_lines: int | None = None,
              line_gap: int = 2) -> pygame.Surface:
        key = (text, size, tuple(colour), width, max_lines, line_gap)
        surf = self._blocks.get(key)
        if surf is not None:
            self._blocks.move_to_end(key)
            return surf
        lines = self.layout(text, size, colour, width, max_lines)
        lh = Fonts.get(size).get_linesize() - 3 + line_gap
        height = max(1, lh * len(lines))
        surf = pygame.Surface((max(1, width), height), pygame.SRCALPHA)
        y = 0
        for line in lines:
            for word, col, weight, x in line:
                surf.blit(render(word, size, col, weight), (x, y))
            y += lh
        self._blocks[key] = surf
        if len(self._blocks) > 1500:
            self._blocks.popitem(last=False)
        return surf

    def draw(self, surf, text: str, pos, size: int = 13, colour=C.text, width: int = 300,
             max_lines: int | None = None, line_gap: int = 2) -> int:
        img = self.block(text, size, colour, width, max_lines, line_gap)
        surf.blit(img, pos)
        return img.get_height()

    def draw_line(self, surf, text: str, pos, size: int = 13, colour=C.text, max_width: int = 400) -> int:
        return self.draw(surf, text, pos, size, colour, max_width, max_lines=1)


def dim(colour, amount: float = 0.45):
    return mix(colour, C.panel, amount)
