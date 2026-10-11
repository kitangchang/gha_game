"""Drawing for the shift screen: HUD, task cards, the ops room with its wall clocks
and screens, desks, and the right-hand column (tools, SOP tracker, log)."""
from __future__ import annotations

import math

import pygame

from game.geo import region_label, short_place
from game.util import DAY_NAMES, fmt_clock, fmt_minutes, fmt_money

from ..icons import get_icons
from ..richtext import get_rich
from ..theme import C, TONES, H, W, mag_color, mix, render
from ..widgets import TOOLTIP, alpha_rect, bar, check_icon, draw_text, lock_icon, panel, pill, pips
from .common import (catalogue_day_label, draw_portrait, draw_sprite, fatigue_color, gha_tooltip, relic_lines,
                     skill_pill, skill_tags, team_color_of, trust_bar)
from .wall import draw_cams, draw_clocks, draw_dart, draw_traces

HUD_H = 72
TOP = HUD_H
SPRITE_H = 66           # analyst sprite height in the ops room
INBOX = pygame.Rect(0, TOP, 400, H - TOP)
RIGHT = pygame.Rect(W - 410, TOP, 410, H - TOP)
CENTER = pygame.Rect(INBOX.right, TOP, RIGHT.x - INBOX.right, H - TOP)
ROOM = pygame.Rect(CENTER.x, TOP, CENTER.width, 384)
COLS_Y = ROOM.bottom
CLOCK_RECT = pygame.Rect(CENTER.x, ROOM.y + 10, CENTER.width, 42)     # NZ and UTC clocks above the screens
WALL_Y = CLOCK_RECT.bottom + 13
WALL_H = 224
FLOOR_Y = WALL_Y + WALL_H + 13
_GAP = 12
SCREEN_W = (CENTER.width - 28 - 3 * _GAP) // 4                         # four screens, all the same width
_X0 = CENTER.x + (CENTER.width - 4 * SCREEN_W - 3 * _GAP) // 2
CAMS_RECT = pygame.Rect(_X0, WALL_Y, SCREEN_W, WALL_H)
MAP_RECT = CAMS_RECT.move(SCREEN_W + _GAP, 0)
TRACES_RECT = MAP_RECT.move(SCREEN_W + _GAP, 0)
DART_RECT = TRACES_RECT.move(SCREEN_W + _GAP, 0)
DOOR_RECT = pygame.Rect(CENTER.x + 8, FLOOR_Y - 6, 36, 80)
DOOR = (DOOR_RECT.centerx, 422)
SEAT_Y = 406
COL_X, COL_W = RIGHT.x + 8, RIGHT.width - 16
SOP_H = 450
INBOX_HEAD_H = 80       # INBOX title + sort, then the auto-assign row
INBOX_CARD_H = 62
SOP_ORDER = ["prelim", "page_duty", "assess_tsunami", "assess_dart", "send_eat", "activate_tep", "confirm",
             "reassess_tsunami", "send_eat2", "public_comms", "check_dart"]


# ----------------------------------------------------------------- task bits
def task_color(scene, t):
    data = scene.data
    if t.kind == "eq":
        ev = scene.eng.events.get(t.event_uid)
        return mag_color(ev.display_mag()) if ev else C.accent
    if t.kind == "sop":
        sop = data.sop_by_id.get(t.sop_tags[0]) if t.sop_tags else None
        return tuple(sop["color"]) if sop else C.sop
    if t.kind == "staffing":
        return C.bad
    if t.skill in data.skill_by_key:
        return tuple(data.skill_by_key[t.skill]["color"])
    return C.dim


def due_info(eng, t):
    if t.available is None:
        return "locked", C.faint, None
    left = t.available + t.deadline - eng.now
    if left < 0:
        return f"late {fmt_minutes(-left)}", C.bad, 0.0
    frac = left / max(1.0, t.deadline)
    col = C.good if frac > 0.5 else (C.warn if frac > 0.2 else C.bad)
    return fmt_minutes(left), col, frac


def requirement_text(scene, t) -> str:
    eng = scene.eng
    if "available_at" in t.meta and not t.requires:
        return f"from {fmt_clock(t.meta['available_at'], scene.day_start)}"
    names = []
    for rid in t.requires:
        r = eng.tasks.get(rid)
        if r is not None:
            names.append("Prelim" if r.type == "prelim" else "Confirm" if r.type == "confirm" else r.name)
    return "after " + ", ".join(names) if names else "locked"


def sop_label(scene, t, ev) -> str:
    names = [scene.data.sop_by_id[s]["short"] for s in t.sop_tags if s in scene.data.sop_by_id]
    tag = names[0] if names else "SOP"
    if ev is None:
        return tag
    return f"{tag} · {ev.mag_label()} {short_place(ev.description, 16)}"


def task_tooltip(scene, t) -> list:
    eng, data = scene.eng, scene.data
    ev = eng.events.get(t.event_uid) if t.event_uid is not None else None
    lines = [(eng.task_title(t), C.text, 14, "bold")]
    if ev is not None:
        lines.append((ev.description, C.dim, 13))
        stage = ["automatic solution only", "prelim done", "confirmed"][ev.stage]
        lines.append((f"{ev.mag_label()} ({stage}) · depth {ev.depth:.0f} km · {region_label(ev.region)}", C.dim, 12))
        if ev.origin_time:
            lines.append((f"Real event {ev.event_id} · {ev.origin_time}", C.faint, 11))
        if ev.sops:
            lines.append(("SOP: " + ", ".join(data.sop_by_id[s]["name"] for s in ev.sops), C.sop, 12))
    elif t.subtitle:
        lines.append((t.subtitle, C.dim, 13))
    if t.desc:
        lines.append((t.desc, C.dim, 12))
    due, col, _ = due_info(eng, t)
    lines.append((f"{data.skill_name(t.skill)} · complexity {t.complexity} · importance {t.importance:.2f}", C.faint, 12))
    if t.locked:
        lines.append((f"Locked: {requirement_text(scene, t)}. You can queue it already.", C.warn, 12))
    else:
        lines.append((f"Due in {due}" if not t.overdue else f"Overdue ({due})", col, 12, "semibold"))
    present = [eng.ghas[gid] for gid in eng.on_shift]
    if present:
        lines.append(("If assigned now:", C.faint, 11))
        for g in present:
            eta, err = eng.estimate(g, t)
            lines.append((f"  {g.first_name}: {fmt_minutes(eta)}, {err * 100:.0f}% error", C.text, 12))
    return lines


def draw_inbox_card(scene, surf, rect, t, mouse, selected=False):
    eng = scene.eng
    hover = rect.collidepoint(mouse)
    locked = t.locked
    bg = C.hover if hover else (C.panel2 if not locked else (27, 32, 42))
    pygame.draw.rect(surf, bg, rect, border_radius=7)
    col = task_color(scene, t)
    stripe = col if not locked else mix(col, C.panel, 0.55)
    pygame.draw.rect(surf, stripe, (rect.x, rect.y, 5, rect.height), border_top_left_radius=7, border_bottom_left_radius=7)
    text_col = C.text if not locked else C.faint
    dim_col = C.dim if not locked else C.faint
    due, due_col, frac = due_info(eng, t)
    right = rect.right - 10
    if locked:
        lock_icon(surf, (right - 8, rect.y + 16), 11)
    else:
        draw_text(surf, due, (right, rect.y + 7), 13, due_col, "bold", anchor="topright")
    r = skill_pill(surf, (right, rect.y + 27), t.skill, scene.data, size=10, anchor="topright", bright=not locked)
    pips(surf, (r.x - 36, rect.y + 32), t.complexity, 5, col if not locked else C.faint, 5, 2)
    ev = eng.events.get(t.event_uid) if t.event_uid is not None else None
    text_right = r.x - 44
    if t.kind == "eq" and ev is not None:
        mag_col = mag_color(ev.display_mag()) if not locked else C.faint
        draw_text(surf, ev.mag_label(), (rect.x + 13, rect.y + 9), 20, mag_col, "bold")
        stage = {"prelim": "PRELIM", "confirm": "CONFIRM", "review": "REVIEW"}.get(t.type, t.type.upper())
        x = rect.x + 88
        img = render(stage, 12, text_col, "bold")
        surf.blit(img, (x, rect.y + 7))
        draw_text(surf, region_label(ev.region).upper(), (x + img.get_width() + 6, rect.y + 8), 10, C.faint, "bold")
        draw_text(surf, ev.description, (x, rect.y + 25), 12, dim_col, max_width=text_right - x)
        sub = f"{ev.depth:.0f} km deep · {fmt_clock(ev.t, scene.day_start)}"
        if locked:
            sub = requirement_text(scene, t)
        draw_text(surf, sub, (x, rect.y + 42), 11, C.faint, max_width=text_right - x)
        if ev.sops:
            pill(surf, "SOP", (rect.x + 13, rect.y + 40), C.bg, C.sop, size=9)
    else:
        x = rect.x + 14
        draw_text(surf, t.name, (x, rect.y + 7), 13, text_col, "bold", max_width=text_right - x)
        if t.kind == "sop":
            sub, sub_col = sop_label(scene, t, ev), (C.sop if not locked else C.faint)
        elif t.kind == "staffing":
            sub, sub_col = t.subtitle, C.warn
        else:
            sub, sub_col = t.desc or t.subtitle, dim_col
        draw_text(surf, sub, (x, rect.y + 26), 12, sub_col, max_width=text_right - x)
        kind = {"sop": "SOP step", "bau": "Business as usual", "staffing": "Staffing"}.get(t.kind, "")
        third = requirement_text(scene, t) if locked else kind
        draw_text(surf, third, (x, rect.y + 43), 11, C.faint, max_width=text_right - x)
    if frac is not None:
        w = int((rect.width - 10) * frac)
        pygame.draw.rect(surf, C.panel3, (rect.x + 6, rect.bottom - 4, rect.width - 12, 2))
        if w > 0:
            pygame.draw.rect(surf, due_col, (rect.x + 6, rect.bottom - 4, w, 2))
    if t.overdue:
        pygame.draw.rect(surf, C.bad, rect, 2, border_radius=7)
    if selected:
        pygame.draw.rect(surf, C.accent, rect, 2, border_radius=7)
    elif hover:
        pygame.draw.rect(surf, C.border2, rect, 1, border_radius=7)
    if hover and not scene.drag:
        TOOLTIP.set(task_tooltip(scene, t), 340)


def draw_queue_card(scene, surf, rect, t, g, active: bool, mouse, selected=False):
    eng = scene.eng
    hover = rect.collidepoint(mouse)
    locked = t.locked
    col = task_color(scene, t)
    bg = C.hover if hover else (C.panel3 if active else C.panel2)
    pygame.draw.rect(surf, bg, rect, border_radius=6)
    pygame.draw.rect(surf, col if not locked else mix(col, C.panel, 0.55),
                     (rect.x, rect.y, 4, rect.height), border_top_left_radius=6, border_bottom_left_radius=6)
    ev = eng.events.get(t.event_uid) if t.event_uid is not None else None
    eta, err = eng.estimate(g, t)
    due, due_col, frac = due_info(eng, t)
    text_col = C.text if not locked else C.faint
    x = rect.x + 10
    right = rect.right - 8
    draw_text(surf, due if not locked else "", (right, rect.y + 5), 11, due_col, "bold", anchor="topright")
    if locked:
        lock_icon(surf, (right - 6, rect.y + 12), 9)
    if t.kind == "eq" and ev is not None:
        img = render(ev.mag_label(), 13, mag_color(ev.display_mag()) if not locked else C.faint, "bold")
        surf.blit(img, (x, rect.y + 4))
        stage = {"prelim": "PRELIM", "confirm": "CONFIRM", "review": ""}.get(t.type, "")
        tx = x + img.get_width() + 6
        if stage:
            s_img = render(stage, 10, text_col, "bold")
            surf.blit(s_img, (tx, rect.y + 7))
            tx += s_img.get_width() + 6
        draw_text(surf, short_place(ev.description, 30), (tx, rect.y + 6), 11, C.dim, max_width=right - tx - 40)
    else:
        draw_text(surf, t.name, (x, rect.y + 5), 12, text_col, "semibold", max_width=right - x - 44)
    if active:
        prog = t.progress / max(0.01, t.work)
        bar(surf, (x, rect.y + 26, rect.width - 20, 6), prog, col, C.panel)
        draw_text(surf, f"{fmt_minutes(eta)} left · {err * 100:.0f}% err", (x, rect.y + 37), 11, C.dim)
        if t.kind == "sop" or (ev is not None and ev.sops):
            pill(surf, "SOP", (right, rect.y + 36), C.bg, C.sop, size=9, anchor="topright")
    else:
        sub = requirement_text(scene, t) if locked else f"~{fmt_minutes(eta)} · {err * 100:.0f}% err"
        draw_text(surf, sub, (x, rect.y + 22), 11, C.faint, max_width=rect.width - 20)
    if t.overdue:
        pygame.draw.rect(surf, C.bad, rect, 2, border_radius=6)
    elif selected:
        pygame.draw.rect(surf, C.accent, rect, 2, border_radius=6)
    elif hover:
        pygame.draw.rect(surf, C.border2, rect, 1, border_radius=6)
    if hover and not scene.drag:
        TOOLTIP.set(task_tooltip(scene, t) + [("Right-click to send back to the inbox", C.faint, 11)], 340)


# ---------------------------------------------------------------------- HUD
def shift_teams(scene) -> list:
    """Teams rostered for the current shift (normally exactly one)."""
    slot = max(0, scene.eng.slot)
    roster = scene.run.roster
    return [key for key in scene.data.team_keys
            if slot < len(roster.grid.get(key, [])) and roster.grid[key][slot] and roster.teams.get(key)]


def shift_tooltip(scene, shift, start: int, end: int, teams: list) -> list:
    eng, run, data = scene.eng, scene.run, scene.data
    lines = [(f"{shift['name']} shift, {start:02d}00–{end:02d}00", tuple(shift["color"]), 14, "bold")]
    rostered = set()
    for key in teams:
        members = [g for gid in run.roster.teams.get(key, []) if (g := run.gha(gid)) is not None and g.active]
        rostered.update(g.id for g in members)
        names = ", ".join(g.first_name for g in members) or "nobody"
        lines.append((f"{data.team_name(key)} team: {names}", C.text, 13))
    extra = [eng.ghas[gid].first_name for gid in eng.on_shift if gid not in rostered and gid in eng.ghas]
    if extra:
        lines.append((f"Also on shift (cover, call-ins, contractors): {', '.join(extra)}", C.dim, 12))
    if shift.get("fatigue_mult", 1.0) > 1.0:
        lines.append((f"Fatigue builds {shift['fatigue_mult']:.1f}× faster on this shift.", C.faint, 12))
    return lines


def shift_times(scene, shift) -> tuple:
    start = (scene.day_start + shift["start_offset_hours"]) % 24
    return start, (start + shift["hours"]) % 24


def draw_hud(scene, surf, mouse):
    eng, run = scene.eng, scene.run
    pygame.draw.rect(surf, C.bg2, (0, 0, W, HUD_H))
    pygame.draw.line(surf, C.border, (0, HUD_H - 1), (W, HUD_H - 1))
    day = eng.day_index
    draw_text(surf, f"WEEK {run.week + 1}/{run.weeks_total}", (16, 7), 11, C.faint, "bold")
    draw_text(surf, f"{DAY_NAMES[day].upper()} · DAY {day + 1}", (16, 21), 20, C.text, "bold")
    plan_day = eng.plan.days[day]
    data_label = catalogue_day_label(plan_day.source)
    r = draw_text(surf, data_label, (16, 49), 11, C.dim, max_width=200)
    if r.collidepoint(mouse):
        TOOLTIP.set([("Earthquake data", C.text, 13, "bold"),
                     (f"Today replays the catalogue day {plan_day.source} from {run.catalog_label}.", C.dim, 12),
                     (f"Workload percentile {plan_day.percentile * 100:.0f}.", C.faint, 11)], 320)
    shift = eng.shift
    s_col = tuple(shift.get("color", C.gold))
    start, end = shift_times(scene, shift)
    sx = 236
    shift_rect = pill(surf, f"{shift['name'].upper()} {start:02d}00–{end:02d}00", (sx, 9), C.bg, s_col, size=11)
    x = sx
    teams = shift_teams(scene)
    for key in teams[:2]:
        col = scene.data.team_color(key)
        pygame.draw.circle(surf, col, (x + 4, 38), 4)
        rr = draw_text(surf, scene.data.team_name(key).upper(), (x + 12, 31), 11, col, "bold")
        x = rr.right + 10
    if not teams:
        draw_text(surf, "NO TEAM ROSTERED", (x, 31), 11, C.faint, "bold")
    bar(surf, (sx, 54, max(130, shift_rect.width), 5), eng.shift_progress(), s_col)
    hud_hover = pygame.Rect(sx - 6, 4, max(140, shift_rect.width + 12, x - sx + 6), 60)
    if hud_hover.collidepoint(mouse):
        TOOLTIP.set(shift_tooltip(scene, shift, start, end, teams), 320)
    trust_bar(surf, (440, 38, 190, 14), run.rating)
    draw_text(surf, "BUDGET", (712, 16), 11, C.faint, "bold")
    draw_text(surf, fmt_money(run.budget), (712, 30), 22, C.gold if run.budget >= 0 else C.bad, "bold")
    draw_text(surf, "SUPPLIES", (scene.supply_x, 5), 9, mix(C.supply, C.faint, 0.4), "bold")
    for b in scene.hud_buttons:
        b.draw(surf, mouse)
    scene.draw_supply_icons(surf)


# ------------------------------------------------------------ right column
def right_column(scene) -> tuple:
    """(tools rect, icon size, icons per row, sop rect, log rect). The tools panel
    grows to a second row of icons when needed, then the icons shrink."""
    owned = sum(1 for rid in scene.run.relics if rid in scene.data.relics)
    size, per_row, rows = 30, 1, 1
    for size in (30, 25, 21, 17):
        per_row = max(1, (COL_W - 24 + 6) // (size + 6))
        rows = max(1, -(-owned // per_row))
        if rows <= 2:
            break
    rows = min(rows, 2)
    tools = pygame.Rect(COL_X, TOP + 8, COL_W, 28 + rows * (size + 6) + 6)
    sop = pygame.Rect(COL_X, tools.bottom + 8, COL_W, SOP_H)
    log = pygame.Rect(COL_X, sop.bottom + 8, COL_W, H - sop.bottom - 16)
    return tools, size, per_row, sop, log


def draw_tools(scene, surf, mouse):
    """The tools this run owns (Slay the Spire style), each with a tooltip."""
    run, data = scene.run, scene.data
    rect, size, per_row = scene.tools_rect, scene.tool_size, scene.tools_per_row
    panel(surf, rect, C.panel, C.border, radius=8)
    draw_text(surf, "TOOLS", (rect.x + 12, rect.y + 10), 11, C.faint, "bold")
    special = scene.eng.special
    if special:
        r = draw_text(surf, f"SPECIAL WEEK · {special['name'].upper()}", (rect.right - 12, rect.y + 10), 10, C.sop,
                      "bold", anchor="topright", max_width=rect.width - 90)
        if r.collidepoint(mouse):
            TOOLTIP.set([(special["name"], C.sop, 14, "bold"), (special.get("desc", ""), C.text, 13)], 320)
    owned = [rid for rid in run.relics if rid in data.relics]
    if not owned:
        draw_text(surf, "None yet. Buy tools in the shop between weeks.", (rect.x + 12, rect.y + 32), 12, C.faint)
        return
    icons = get_icons()
    fits = per_row * 2
    for i, rid in enumerate(owned[:fits]):
        row, col = divmod(i, per_row)
        r = pygame.Rect(rect.x + 12 + col * (size + 6), rect.y + 28 + row * (size + 6), size, size)
        if i == fits - 1 and len(owned) > fits:
            draw_text(surf, f"+{len(owned) - fits + 1}", r.center, 11, C.dim, "bold", anchor="center")
            continue
        if icons is not None:
            icons.draw(surf, "tools", rid, r.topleft, size)
        if r.collidepoint(mouse):
            pygame.draw.rect(surf, C.white, r.inflate(4, 4), 1, border_radius=6)
            TOOLTIP.set(relic_lines(rid, data), 300)


# -------------------------------------------------------------------- inbox
def draw_inbox(scene, surf, mouse):
    pygame.draw.rect(surf, C.bg2, INBOX)
    pygame.draw.line(surf, C.border, (INBOX.right - 1, INBOX.y), (INBOX.right - 1, INBOX.bottom))
    tasks = scene.sorted_inbox()
    open_n = sum(1 for t in tasks if not t.locked)
    draw_text(surf, "INBOX", (14, INBOX.y + 12), 15, C.text, "bold")
    draw_text(surf, f"{open_n} open · {len(tasks) - open_n} locked", (80, INBOX.y + 14), 12, C.dim)
    scene.sort_button.draw(surf, mouse)
    auto_b = scene.auto_button
    draw_text(surf, "AUTO-ASSIGN", (auto_b.rect.x - 10, auto_b.rect.centery), 10,
              C.good if scene.eng.auto["on"] else C.faint, "bold", anchor="midright")
    for b in scene.inbox_buttons:
        b.draw(surf, mouse)
    scene.draw_chevron(surf)
    pygame.draw.line(surf, C.border, (12, INBOX.y + INBOX_HEAD_H - 4), (INBOX.right - 12, INBOX.y + INBOX_HEAD_H - 4))
    area = pygame.Rect(8, INBOX.y + INBOX_HEAD_H + 2, INBOX.width - 16, INBOX.height - INBOX_HEAD_H - 8)
    scene.inbox_area = area
    total_h = len(tasks) * (INBOX_CARD_H + 6)
    scene.inbox_scroll = max(0, min(scene.inbox_scroll, total_h - area.height))
    clip = surf.get_clip()
    surf.set_clip(area)
    y = area.y - scene.inbox_scroll
    target = scene.drag is not None and area.collidepoint(mouse)
    for t in tasks:
        rect = pygame.Rect(area.x, y, area.width, INBOX_CARD_H)
        if rect.bottom >= area.top and rect.top <= area.bottom:
            if scene.drag and t.id in scene.drag["tids"]:
                pygame.draw.rect(surf, C.panel, rect, 1, border_radius=7)
            else:
                draw_inbox_card(scene, surf, rect, t, mouse if not scene.drag else (-1, -1), t.id in scene.selected)
            scene.card_rects.append((rect.clip(area), t.id, None))
        y += INBOX_CARD_H + 6
    surf.set_clip(clip)
    if not tasks:
        msg = "Inbox zero. Enjoy it while it lasts."
        if scene.eng.auto["on"]:
            msg = "Auto-assign is handing out new tasks."
        draw_text(surf, msg, area.center, 13, C.faint, anchor="center")
    if total_h > area.height:
        frac = area.height / total_h
        h = max(30, int(area.height * frac))
        y = area.y + int((area.height - h) * (scene.inbox_scroll / max(1, total_h - area.height)))
        pygame.draw.rect(surf, C.panel3, (INBOX.right - 6, y, 3, h), border_radius=2)
    if target:
        pygame.draw.rect(surf, C.accent, area.inflate(4, 4), 2, border_radius=8)


# --------------------------------------------------------------------- room
def seat_center(scene, i: int):
    n = max(1, len(scene.eng.seats))
    col_w = CENTER.width / n
    return CENTER.x + col_w * (i + 0.5), SEAT_Y


def draw_room(scene, surf, mouse, real_t: float):
    eng = scene.eng
    pygame.draw.rect(surf, (19, 24, 32), (ROOM.x, ROOM.y, ROOM.width, FLOOR_Y - ROOM.y))
    pygame.draw.rect(surf, (25, 30, 40), (ROOM.x, FLOOR_Y, ROOM.width, ROOM.bottom - FLOOR_Y))
    pygame.draw.line(surf, C.border, (ROOM.x, FLOOR_Y), (ROOM.right, FLOOR_Y))
    draw_clocks(scene, surf, CLOCK_RECT, mouse)
    draw_cams(scene, surf, CAMS_RECT, mouse)
    scene.map.draw(surf, eng, scene.ripples, scene.screen_t, scene.map_highlight)
    draw_traces(scene, surf, TRACES_RECT)
    draw_dart(scene, surf, DART_RECT, mouse)
    # Door
    pygame.draw.rect(surf, (36, 42, 54), DOOR_RECT, border_radius=3)
    pygame.draw.rect(surf, C.border2, DOOR_RECT, 1, border_radius=3)
    pygame.draw.circle(surf, C.faint, (DOOR_RECT.right - 7, DOOR_RECT.centery + 4), 2)
    # Desks and analysts
    for i, gid in enumerate(eng.seats):
        cx, cy = seat_center(scene, i)
        g = eng.ghas.get(gid) if gid is not None else None
        working = g is not None and eng.present(g) and eng.current_task(g) is not None
        glow = (60, 140, 200) if working else (40, 52, 66)
        for mx in (cx - 54, cx + 30):
            pygame.draw.rect(surf, glow, (mx, cy - 6, 24, 17), border_radius=2)
    for gid, actor in sorted(scene.actors.items(), key=lambda kv: kv[1]["y"]):
        g = eng.ghas.get(gid) or scene.run.gha(gid)
        if g is None or actor["alpha"] <= 0.02:
            continue
        x, y = actor["x"], actor["y"]
        if actor.get("working"):
            bob = math.sin(scene.screen_t * 9 + gid) * 1.2
        elif not actor.get("seated"):
            bob = -abs(math.sin(real_t * 13 + gid)) * 3.0     # walking
        else:
            bob = 0.0
        a = int(255 * actor["alpha"])
        if draw_sprite(surf, (x, y + 24 + bob), SPRITE_H, g, scene.data, scene.run, alpha=a):
            continue
        body = pygame.Surface((44, 46), pygame.SRCALPHA)
        tcol = team_color_of(scene.data, scene.run, g)
        pygame.draw.ellipse(body, tuple(int(c * 0.6) for c in tcol) + (a,), (4, 24, 36, 26))
        pygame.draw.circle(body, tuple(g.color) + (a,), (22, 16), 13)
        surf.blit(body, (x - 22, y - 22 + bob))
        draw_text(surf, g.initials, (x, y - 6 + bob), 10, C.bg, "bold", anchor="center")
        if actor.get("seated") and eng.present(g) and g.fatigue > 70:
            pygame.draw.circle(surf, (120, 190, 255), (int(x + 14), int(y - 16 + bob)), 3)
    for i, gid in enumerate(eng.seats):
        cx, cy = seat_center(scene, i)
        pygame.draw.rect(surf, (62, 56, 50), (cx - 62, cy + 14, 124, 22), border_radius=4)
        pygame.draw.rect(surf, (82, 74, 66), (cx - 62, cy + 14, 124, 4), border_radius=2)
        g = eng.ghas.get(gid) if gid is not None else None
        if g is not None and eng.now < g.away_until:
            pill(surf, g.away_reason[:22], (cx, cy + 25), C.bg, C.warn, size=10, anchor="center")
        elif g is not None and eng.now < g.arrive_at:
            pill(surf, "arriving", (cx, cy + 25), C.bg, C.accent, size=10, anchor="center")
        elif g is not None:
            pill(surf, g.first_name, (cx, cy + 25), team_color_of(scene.data, scene.run, g), (44, 39, 35), size=10,
                 anchor="center")
    for f in scene.floats:
        seat = next((i for i, gid in enumerate(eng.seats) if gid == f["gha"]), None)
        if seat is None:
            continue
        cx, cy = seat_center(scene, seat)
        k = 1.0 - f["t"] / f["life"]
        y = cy - 40 - k * 10
        a = max(0, min(255, int(255 * (1 - k) * 1.8)))
        img = render(f["text"], 14, TONES.get(f["tone"], C.text), "bold").copy()
        img.set_alpha(a)
        rect = img.get_rect(center=(cx, y))
        alpha_rect(surf, rect.inflate(10, 4), (10, 14, 20, int(a * 0.7)), radius=6)
        surf.blit(img, rect)


# -------------------------------------------------------------------- desks
def gha_status(eng, g):
    if eng.now < g.arrive_at:
        return "Arriving…", C.accent
    if eng.now < g.away_until:
        return f"Away: {g.away_reason} (back {fmt_clock(g.away_until, eng.cfg['time']['day_start_hour'])})", C.warn
    cur = eng.current_task(g)
    queued = sum(1 for tid in g.queue if tid in eng.tasks and not eng.tasks[tid].done)
    if cur is None:
        if queued:
            return "Waiting on locked tasks", C.faint
        return "Idle", C.faint
    return f"Working · {queued} queued · {fmt_minutes(eng.queue_eta(g))}", C.good


def draw_desks(scene, surf, mouse):
    eng = scene.eng
    n = max(1, len(eng.seats))
    col_w = CENTER.width / n
    scene.desk_rects = {}
    scene.queue_slots = {}
    for i, gid in enumerate(eng.seats):
        rect = pygame.Rect(int(CENTER.x + i * col_w) + 4, COLS_Y + 6, int(col_w) - 8, H - COLS_Y - 12)
        g = eng.ghas.get(gid) if gid is not None else None
        if g is None:
            panel(surf, rect, (19, 23, 31), C.border, radius=8)
            draw_text(surf, "Empty desk", (rect.centerx, rect.y + 40), 14, C.faint, "semibold", anchor="center")
            draw_text(surf, f"Desk {i + 1}", (rect.centerx, rect.y + 62), 11, C.faint, anchor="center")
            continue
        scene.desk_rects[i] = (rect, gid)
        target = scene.drag is not None and rect.collidepoint(mouse)
        panel(surf, rect, C.panel, C.accent if target else C.border, radius=8, width=2 if target else 1)
        head = pygame.Rect(rect.x, rect.y, rect.width, 96)
        hover_head = head.collidepoint(mouse) and not scene.drag
        if hover_head:
            pygame.draw.rect(surf, C.panel2, head.inflate(-2, -2), border_radius=8)
        targeting = scene.targeting is not None and scene.targeting["kind"] == "gha" and hover_head
        tcol = team_color_of(scene.data, scene.run, g)
        pygame.draw.rect(surf, tcol, (rect.x + 12, rect.y, rect.width - 24, 3), border_bottom_left_radius=2,
                         border_bottom_right_radius=2)
        draw_portrait(surf, (rect.x + 26, rect.y + 28), 18, g, scene.data, scene.run,
                      ring=C.gold if targeting else None, dim=not eng.present(g), team_color=tcol)
        pill(surf, f"{i + 1}", (rect.x + 8, rect.y + 40), C.bg, tcol, size=9, pad_x=4, pad_y=0)
        draw_text(surf, g.name, (rect.x + 52, rect.y + 9), 14, C.text, "bold", max_width=rect.width - 60)
        status, s_col = gha_status(eng, g)
        draw_text(surf, status, (rect.x + 52, rect.y + 29), 11, s_col, max_width=rect.width - 60)
        draw_text(surf, "F", (rect.x + 52, rect.y + 47), 10, C.faint, "bold")
        bar(surf, (rect.x + 64, rect.y + 50, rect.width - 104, 6), g.fatigue / 100.0, fatigue_color(g.fatigue))
        draw_text(surf, f"{g.fatigue:.0f}", (rect.right - 10, rect.y + 46), 10, C.dim, anchor="topright")
        draw_text(surf, "L", (rect.x + 52, rect.y + 59), 10, C.faint, "bold")
        bar(surf, (rect.x + 64, rect.y + 62, rect.width - 104, 4), g.ltf / 100.0, fatigue_color(g.ltf))
        draw_text(surf, f"{g.ltf:.0f}", (rect.right - 10, rect.y + 58), 10, C.dim, anchor="topright")
        compact = rect.width < 200
        keys = scene.data.skill_keys if not compact else sorted(scene.data.skill_keys, key=lambda k: -g.skills.get(k, 1))[:4]
        skill_tags(surf, (rect.x + 8, rect.y + 74), g, scene.data, keys, size=9, gap=3)
        if hover_head:
            extra = [(f"Desk {i + 1}: hover a task and press {i + 1} to queue it here.", C.faint, 11)]
            if g.double_shift:
                extra.insert(0, ("On a double shift.", C.warn, 12))
            TOOLTIP.set(gha_tooltip(g, scene.data, extra, scene.run), 330)
        pygame.draw.line(surf, C.border, (rect.x + 8, rect.y + 96), (rect.right - 8, rect.y + 96))
        y = rect.y + 104
        slots = []
        current = eng.current_task(g)
        shown = 0
        for tid in g.queue:
            t = eng.tasks.get(tid)
            if t is None or t.done:
                continue
            active = t is current and eng.present(g)
            h = 56 if active else 40
            if y + h > rect.bottom - 6:
                remaining = sum(1 for q in g.queue if q in eng.tasks and not eng.tasks[q].done) - shown
                draw_text(surf, f"+{remaining} more", (rect.centerx, rect.bottom - 14), 11, C.dim, anchor="center")
                break
            card = pygame.Rect(rect.x + 6, y, rect.width - 12, h)
            if scene.drag and tid in scene.drag["tids"]:
                pygame.draw.rect(surf, C.panel2, card, 1, border_radius=6)
            else:
                draw_queue_card(scene, surf, card, t, g, active, mouse if not scene.drag else (-1, -1),
                                tid in scene.selected)
            scene.card_rects.append((card, tid, g.id))
            slots.append((card, tid))
            y += h + 5
            shown += 1
        if not shown:
            draw_text(surf, "Drop tasks here", (rect.centerx, rect.y + 130), 12, C.faint, anchor="center")
        scene.queue_slots[g.id] = slots
        if target:
            pos = sum(1 for c, _ in slots if mouse[1] > c.centery)
            if slots:
                line_y = slots[pos][0].y - 3 if pos < len(slots) else slots[-1][0].bottom + 2
            else:
                line_y = rect.y + 102
            pygame.draw.line(surf, C.accent, (rect.x + 8, line_y), (rect.right - 8, line_y), 3)


# --------------------------------------------------------------- SOP + log
def _sop_rows(scene, ev, tasks) -> list:
    """The event's SOP steps in checklist order (repeats sorted by when they appear)."""
    rank = {k: i for i, k in enumerate(SOP_ORDER)}
    rows = [t for t in tasks if t.kind == "sop" or t.type in ("prelim", "confirm")]
    return sorted(rows, key=lambda t: (rank.get(t.type, 50), t.meta.get("available_at", 0.0), t.id))


def draw_sop(scene, surf, mouse):
    eng = scene.eng
    box = scene.sop_rect
    panel(surf, box, C.panel, C.border, radius=8)
    draw_text(surf, "SOP TRACKER", (box.x + 12, box.y + 10), 11, C.faint, "bold")
    active = eng.active_sop_events()
    if not active:
        draw_text(surf, "No active SOPs. Big events trigger checklists here.", (box.x + 12, box.y + 34), 12,
                  C.faint, max_width=box.width - 24)
        return
    clip = surf.get_clip()
    surf.set_clip(box.inflate(-4, -4))
    y = box.y + 30
    for ev, tasks in reversed(active):
        names = " + ".join(scene.data.sop_by_id[s]["short"] for s in ev.sops)
        draw_text(surf, f"{ev.mag_label()} {short_place(ev.description, 22)}", (box.x + 12, y), 12, C.text, "bold")
        draw_text(surf, names, (box.right - 12, y + 1), 10, C.sop, "bold", anchor="topright", max_width=190)
        y += 19
        for t in _sop_rows(scene, ev, tasks):
            row = pygame.Rect(box.x + 10, y, box.width - 20, 17)
            if t.done:
                check_icon(surf, (row.x + 8, row.centery), 9, C.bad if t.error else C.good)
                col = C.faint
            elif t.locked:
                lock_icon(surf, (row.x + 8, row.centery), 8, C.faint)
                col = C.faint
            else:
                g = eng.ghas.get(t.assignee) if t.assignee else None
                working = g is not None and eng.current_task(g) is t
                pygame.draw.circle(surf, C.accent if working else (C.bad if t.overdue else C.warn),
                                   (row.x + 8, row.centery), 4)
                col = C.text
            label = {"prelim": "Prelim solution", "confirm": "Confirm solution"}.get(t.type, t.name)
            if t.locked and "available_at" in t.meta:
                label += f" (at {fmt_clock(t.meta['available_at'], scene.day_start)})"
            elif t.hidden:
                label += " (later)"
            draw_text(surf, label, (row.x + 20, row.y + 1), 12, col, max_width=210)
            if t.done:
                status = "error" if t.error else ("done late" if t.overdue else "done")
                draw_text(surf, status, (row.right, row.y + 1), 11, C.bad if t.error else C.faint, anchor="topright")
            elif not t.locked:
                due, due_col, _ = due_info(eng, t)
                draw_text(surf, due, (row.right, row.y + 1), 11, due_col, "semibold", anchor="topright")
                if t.assignee is not None and t.assignee in eng.ghas:
                    who = eng.ghas[t.assignee]
                    draw_text(surf, who.initials, (row.right - 62, row.y + 1), 11,
                              team_color_of(scene.data, scene.run, who), "bold", anchor="topright")
                else:
                    draw_text(surf, "unassigned", (row.right - 62, row.y + 1), 10, C.warn, anchor="topright")
            if row.collidepoint(mouse):
                TOOLTIP.set(task_tooltip(scene, t), 340)
            y += 17
        y += 10
        if y > box.bottom:
            break
    surf.set_clip(clip)


def draw_log(scene, surf):
    eng = scene.eng
    box = scene.log_rect
    panel(surf, box, C.panel, C.border, radius=8)
    draw_text(surf, "LOG", (box.x + 12, box.y + 10), 11, C.faint, "bold")
    y = box.bottom - 24
    ds = scene.day_start
    rt = get_rich()
    for t, text, tone in reversed(eng.log[-60:]):
        if y < box.y + 28:
            break
        draw_text(surf, fmt_clock(t, ds), (box.x + 12, y), 11, C.faint)
        col = TONES.get(tone, C.dim)
        if rt is not None:
            rt.draw_line(surf, text, (box.x + 56, y), 12, col, box.width - 68)
        else:
            draw_text(surf, text, (box.x + 56, y), 12, col, max_width=box.width - 68)
        y -= 18


def draw_toasts(scene, surf):
    y = WALL_Y + 6          # below the wall clocks, so they stay readable
    for toast in scene.toasts[-4:]:
        k = min(1.0, toast["t"] / 0.4)
        col = TONES.get(toast["tone"], C.text)
        size = 16 if toast.get("big") else 13
        img = render(toast["text"], size, col, "bold" if toast.get("big") else "semibold")
        rect = pygame.Rect(0, 0, img.get_width() + 36, img.get_height() + (18 if toast.get("big") else 12))
        rect.midtop = (CENTER.centerx, y)
        alpha_rect(surf, rect, (16, 20, 28, int(235 * k)), radius=8)
        pygame.draw.rect(surf, col, rect, 1, border_radius=8)
        img = img.copy()
        img.set_alpha(int(255 * k))
        surf.blit(img, img.get_rect(center=rect.center))
        y = rect.bottom + 6
