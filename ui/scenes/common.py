"""Drawing pieces shared between screens: portraits, analyst chips, skill tags,
tooltips, trust bar."""
from __future__ import annotations

import pygame

from game.util import fmt_money

from ..avatars import get_bank
from ..theme import C, RARITY, TRAIT_COLOURS, TRAIT_LABELS, mix, render, text_width, trust_color
from ..widgets import TIP_BG, TOOLTIP, avatar, bar, draw_text, pill

TEMP_COLOR = (200, 200, 210)
CHIP_H = 56                 # analyst rows on the roster, call-in and training pickers


def team_fill(col, strength: float = 0.2):
    """Dark tint of a team colour, used as a background."""
    return mix(C.bg, col, strength)


def fatigue_color(v: float):
    if v < 40:
        return C.good
    if v < 70:
        return C.warn
    return C.bad


def catalogue_day_label(source: str) -> str:
    """'2016-11-14' -> 'Data: Mon 14 Nov 2016'; synthetic days keep their own label."""
    try:
        from datetime import datetime
        d = datetime.strptime(source, "%Y-%m-%d")
        return f"Data: {d:%a} {d.day} {d:%b %Y}"
    except (ValueError, TypeError):
        return f"Data: {str(source).lower()}" if source else "Data: unknown day"


# ------------------------------------------------------------------- teams
def group_of(run, g) -> str:
    if run is None or g.temp:
        return "bench"
    return run.roster.group_of(g.id)


def team_color_of(data, run, g):
    if g.temp:
        return TEMP_COLOR
    return data.team_color(group_of(run, g))


def group_label(data, group: str) -> str:
    if group == "bench":
        return "Bench"
    if group == "leave":
        return "On leave"
    return f"{data.team_name(group)} team"


# ---------------------------------------------------------------- portraits
def draw_portrait(surf, center, radius: int, g, data, run=None, ring=None, dim: bool = False, team_color=None):
    """Layered avatar in a circle, or an initials disc if there's no art."""
    tcol = team_color if team_color is not None else (team_color_of(data, run, g) if data else None)
    bank = get_bank()
    img = None
    if bank is not None and bank.has_art:
        bg = mix(tcol, C.panel, 0.7) if tcol else C.panel3
        img = bank.portrait(g, radius * 2, tcol, bank.is_tired(g), bg)
    cx, cy = int(center[0]), int(center[1])
    if img is None:
        avatar(surf, (cx, cy), radius, g.color, g.initials, ring=ring, dim=dim)
        return
    if dim:
        img = img.copy()
        img.set_alpha(110)
    surf.blit(img, (cx - radius, cy - radius))
    if ring is not None:
        pygame.draw.circle(surf, ring, (cx, cy), radius + 1, 2)


def draw_sprite(surf, midbottom, height: int, g, data, run=None, alpha: int = 255, team_color=None) -> bool:
    """Full head-and-shoulders sprite (used in the ops room). False if no art."""
    bank = get_bank()
    if bank is None or not bank.has_art:
        return False
    tcol = team_color if team_color is not None else team_color_of(data, run, g)
    img = bank.sprite(g, height, tcol, bank.is_tired(g))
    if img is None:
        return False
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    surf.blit(img, img.get_rect(midbottom=(int(midbottom[0]), int(midbottom[1]))))
    return True


# --------------------------------------------------------------- tooltips
def skill_rows(data, levels: dict, numbers: bool = False, bg=TIP_BG) -> pygame.Surface:
    """One row per skill: its name in the skill colour, then one box per level.
    Fractional levels (team averages) part-fill the last box; numbers=True adds the value."""
    max_level = int(data.config["skill_model"]["max_level"])
    box, gap, row_h, top = 11, 3, 18, 5
    label_w = max(text_width(sk["name"], 12, "semibold") for sk in data.skills) + 12
    boxes_w = max_level * (box + gap)
    out = pygame.Surface((label_w + boxes_w + (34 if numbers else 0), top * 2 + row_h * len(data.skills)),
                         pygame.SRCALPHA)
    for i, sk in enumerate(data.skills):
        y = top + i * row_h
        col = tuple(sk["color"])
        out.blit(render(sk["name"], 12, col, "semibold"), (0, y + 1))
        value = float(levels.get(sk["key"], 1))
        for b in range(max_level):
            r = pygame.Rect(label_w + b * (box + gap), y + 4, box, box)
            pygame.draw.rect(out, mix(col, bg, 0.78), r, border_radius=2)
            part = max(0.0, min(1.0, value - b))
            if part > 0.97:
                pygame.draw.rect(out, col, r, border_radius=2)
            elif part > 0.05:
                pygame.draw.rect(out, col, (r.x, r.y, max(2, round(box * part)), box),
                                 border_top_left_radius=2, border_bottom_left_radius=2)
        if numbers:
            out.blit(render(f"{value:.1f}", 11, C.dim, "semibold"), (label_w + boxes_w + 4, y + 2))
    return out


def gha_tooltip(g, data, extra: list | None = None, run=None) -> list:
    lines = [(g.name, C.text, 15, "bold")]
    arche = g.stats.get("archetype")
    if g.temp:
        lines.append(("Temporary contractor", C.dim, 12))
    else:
        bits = [group_label(data, group_of(run, g))] if run is not None else []
        if arche:
            bits.append(arche)
        bits.append(f"{fmt_money(g.salary)}/week")
        lines.append((" · ".join(bits), C.dim, 12))
    lines.append(skill_rows(data, g.skills))
    lines.append((f"Fatigue {g.fatigue:.0f} · long-term fatigue {g.ltf:.0f}", C.dim, 13))
    for tid in g.traits:
        t = data.traits[tid]
        lines.append((f"{t['name']}: {t['desc']}", C.dim, 12))
    st = g.stats
    lines.append((f"Tasks {st.get('tasks', 0)} · errors {st.get('errors', 0)} · shifts {st.get('shifts', 0)}",
                  C.faint, 12))
    if extra:
        lines.extend(extra)
    return lines


def relic_lines(rid: str, data) -> list:
    r = data.relics[rid]
    return [(r["name"], RARITY[r["rarity"]], 14, "bold"), (f"{r['rarity'].title()} tool", C.faint, 11),
            (r["desc"], C.text, 13)]


def consumable_lines(cid: str, data) -> list:
    c = data.consumables[cid]
    tgt = {"gha": "Click it, then click an analyst.", "task": "Click it, then click a task card.",
           "none": "Takes effect immediately."}[c.get("target", "none")]
    return [(c["name"], C.supply, 14, "bold"), ("Supply · one use", C.faint, 11), (c["desc"], C.text, 13),
            (tgt, C.faint, 11)]


def training_lines(tid: str, data) -> list:
    t = data.training[tid]
    return [(t["name"], C.training, 14, "bold"), ("Training", C.faint, 11), (t["desc"], C.text, 13)]


def trait_colour(data, tid: str):
    return TRAIT_COLOURS.get(data.traits[tid].get("kind", "good"), C.good)


def trait_lines(tid: str, data) -> list:
    t = data.traits[tid]
    kind = t.get("kind", "good")
    return [(t["name"], TRAIT_COLOURS.get(kind, C.good), 13, "bold"), (TRAIT_LABELS.get(kind, ""), C.faint, 11),
            (t["desc"], C.text, 12)]


# ------------------------------------------------------------------ pieces
def skill_pill(surf, pos, key: str, data, level=None, size: int = 10, anchor: str = "topleft",
               bright: bool = True) -> pygame.Rect:
    """Skill-coloured tag, e.g. SEI4."""
    if key == "any":
        return pill(surf, "ANY" if level is None else f"ANY{level}", pos, C.text, C.panel3, size=size, pad_x=4,
                    pad_y=1, anchor=anchor)
    col = data.skill_by_key[key]["color"]
    text = data.skill_abbr(key) + ("" if level is None else str(level))
    fg = col if bright else mix(col, C.panel2, 0.45)
    bg = mix(col, C.panel, 0.78 if bright else 0.88)
    return pill(surf, text, pos, fg, bg, size=size, pad_x=4, pad_y=1, anchor=anchor)


def skill_tags(surf, pos, g, data, keys=None, size: int = 10, gap: int = 4) -> int:
    x, y = pos
    for k in keys or data.skill_keys:
        lvl = int(g.skills.get(k, 1))
        r = skill_pill(surf, (x, y), k, data, lvl, size=size, bright=lvl >= 3)
        x = r.right + gap
    return x


def top_skills(g, data, n: int = 2) -> list:
    return sorted(data.skill_keys, key=lambda k: -g.skills.get(k, 1))[:n]


def rarity_gem(surf, center, rarity: str, size: int = 5):
    cx, cy = int(center[0]), int(center[1])
    col = RARITY.get(rarity, C.text)
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    pygame.draw.polygon(surf, col, pts)
    pygame.draw.polygon(surf, mix(col, C.white, 0.45), [(cx, cy - size), (cx + size // 2, cy - size // 2), (cx, cy)])


def fatigue_rows(surf, x: int, y: int, width: int, g, label_col=C.faint, num_col=C.dim, track=C.panel3):
    """'F ▬▬▬ 14' over 'L ▬▬ 28', the same pair as on the desk cards. About 28 px tall."""
    num_w = 24
    bw = max(10, width - 12 - num_w - 2)
    draw_text(surf, "F", (x, y), 10, label_col, "bold")
    bar(surf, (x + 12, y + 4, bw, 6), g.fatigue / 100.0, fatigue_color(g.fatigue), track)
    draw_text(surf, f"{g.fatigue:.0f}", (x + width, y), 11, num_col, "semibold", anchor="topright")
    draw_text(surf, "L", (x, y + 15), 10, label_col, "bold")
    bar(surf, (x + 12, y + 19, bw, 4), g.ltf / 100.0, fatigue_color(g.ltf), track)
    draw_text(surf, f"{g.ltf:.0f}", (x + width, y + 14), 11, num_col, "semibold", anchor="topright")


def draw_gha_chip(surf, rect, g, data, mouse, away: bool = False, note: str = "", wide: bool = True, run=None):
    """An analyst row on a background in their team's colour: portrait, name and
    fatigue bars with numbers. Skills are in the hover tooltip."""
    rect = pygame.Rect(rect)
    hover = rect.collidepoint(mouse)
    tcol = team_color_of(data, run, g)
    base = team_fill(tcol, 0.44 if hover else 0.34)
    pygame.draw.rect(surf, base, rect, border_radius=8)
    if hover:
        pygame.draw.rect(surf, mix(tcol, C.white, 0.35), rect, 1, border_radius=8)
    rad = max(10, rect.height // 2 - 4)
    draw_portrait(surf, (rect.x + 8 + rad, rect.centery), rad, g, data, run, dim=away, team_color=tcol)
    x = rect.x + 16 + 2 * rad
    fw = 112 if wide else max(64, min(112, rect.width // 2 - 22))
    fx = rect.right - 10 - fw
    flag = note or ("AWAY" if away else "")
    ny = rect.centery - (8 if flag else 0)
    draw_text(surf, g.name if wide else g.first_name, (x, ny), 14, C.text if not away else mix(C.text, base, 0.4),
              "semibold", anchor="midleft", max_width=fx - 8 - x)
    if flag:
        pill(surf, flag, (x, ny + 9), C.bg, C.warn, size=9)
    fatigue_rows(surf, fx, rect.centery - 14, fw, g, mix(C.text, base, 0.45), mix(C.text, base, 0.12),
                 team_fill(tcol, 0.12))
    if hover:
        TOOLTIP.set(gha_tooltip(g, data, None, run), 340)
    return hover


def draw_tool_strip(surf, run, data, mouse, y: int, height: int = 34, right_text: str = "", right_lines=None):
    """Slay-the-Spire style row of the tools a run owns, with tooltips."""
    from ..icons import get_icons
    from ..theme import W
    rect = pygame.Rect(0, y, W, height)
    pygame.draw.rect(surf, (15, 19, 26), rect)
    pygame.draw.line(surf, C.border, (0, rect.bottom - 1), (W, rect.bottom - 1))
    draw_text(surf, "TOOLS", (16, rect.y + height // 2), 10, C.faint, "bold", anchor="midleft")
    icons = get_icons()
    x = 66
    size = height - 8
    owned = [rid for rid in run.relics if rid in data.relics]
    if not owned:
        draw_text(surf, "None yet. Buy tools in the shop between weeks.", (x, rect.centery), 12, C.faint,
                  anchor="midleft")
    for rid in owned:
        r = pygame.Rect(x, rect.y + 4, size, size)
        if icons is not None:
            icons.draw(surf, "tools", rid, r.topleft, size)
        if r.collidepoint(mouse):
            pygame.draw.rect(surf, C.white, r.inflate(4, 4), 1, border_radius=6)
            TOOLTIP.set(relic_lines(rid, data), 300)
        x += size + 6
    if right_text:
        rr = draw_text(surf, right_text, (W - 16, rect.centery), 11, C.sop, "bold", anchor="midright")
        if right_lines and rr.collidepoint(mouse):
            TOOLTIP.set(right_lines, 320)


def trust_bar(surf, rect, value: float, label: bool = True):
    rect = pygame.Rect(rect)
    if label:
        draw_text(surf, "PUBLIC TRUST", (rect.x, rect.y - 16), 11, C.faint, "bold")
    col = trust_color(value)
    bar(surf, rect, value / 100.0, col, C.panel3, radius=rect.height // 2)
    draw_text(surf, f"{value:.0f}", (rect.right + 10, rect.centery), 18, col, "bold", anchor="midleft")


def section_title(surf, text: str, pos, color=C.faint):
    img = render(text, 12, color, "bold")
    surf.blit(img, pos)
    return img.get_width()
