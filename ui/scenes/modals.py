"""Pop-up decisions on the shift screen: random events, sick cover (with the
week's roster), call-ins, pause menu."""
from __future__ import annotations

import pygame

from game.util import DAY_NAMES, fmt_money

from ..richtext import get_rich
from ..theme import C, H, W, mix
from ..widgets import TOOLTIP, Button, alpha_rect, bar, draw_text, draw_wrapped, panel, wrap
from .common import draw_gha_chip, draw_portrait, fatigue_color, gha_tooltip, group_label, group_of, team_color_of


def _rich_line(surf, text, pos, size, colour, width):
    rt = get_rich()
    if rt is not None:
        rt.draw_line(surf, text, pos, size, colour, width)
    else:
        draw_text(surf, text, pos, size, colour, max_width=width)


def _card(surf, width, height, title, accent=C.accent):
    alpha_rect(surf, (0, 0, W, H), (5, 8, 12, 175))
    rect = pygame.Rect(0, 0, width, height)
    rect.center = (W // 2, H // 2)
    alpha_rect(surf, rect.inflate(16, 16), (0, 0, 0, 90), radius=16)
    panel(surf, rect, C.panel, accent, radius=12, width=2)
    draw_text(surf, title, (rect.x + 26, rect.y + 22), 22, C.text, "bold", max_width=width - 52)
    return rect


def event_modal(scene, surf, mouse) -> list:
    eng, data = scene.eng, scene.data
    ev = data.events[eng.modal["id"]]
    opts = ev["options"]
    width = 760
    rt = get_rich()
    if rt is not None:
        text_img = rt.block(ev["text"], 15, C.dim, width - 52, line_gap=5)
        text_h = text_img.get_height()
    else:
        text_img = None
        text_h = len(wrap(ev["text"], 15, "regular", width - 52)) * 21
    height = 72 + text_h + 18 + len(opts) * 66 + 10
    rect = _card(surf, width, height, ev["title"], C.sop)
    draw_text(surf, "SOMETHING HAPPENED", (rect.x + 26, rect.y + 6), 10, C.sop, "bold")
    y = rect.y + 64
    if text_img is not None:
        surf.blit(text_img, (rect.x + 26, y))
    else:
        draw_wrapped(surf, ev["text"], (rect.x + 26, y, width - 52, text_h), 15, C.dim)
    y += text_h + 14
    buttons = []
    for i, opt in enumerate(opts):
        ok = eng.option_available(opt)
        hint = opt.get("hint", "")
        if not ok:
            req = opt.get("requires", {})
            why = []
            if "budget" in req:
                why.append(f"needs {fmt_money(req['budget'])}")
            if "on_shift_min" in req:
                why.append(f"needs {req['on_shift_min']} analysts on shift")
            hint = "Unavailable: " + ", ".join(why)
        b = Button((rect.x + 26, y, rect.width - 52, 56), opt["label"], lambda idx=i: scene.choose_event(idx),
                   "secondary", 15, enabled=ok, sublabel=hint)
        buttons.append(b)
        y += 66
    for b in buttons:
        b.draw(surf, mouse)
    return buttons


# -------------------------------------------------------------- sick cover
def _schedule(eng) -> dict:
    """gid -> set of slots this week they're on (roster + covers, minus sick calls)."""
    out: dict = {}
    for slot in range(7 * eng.n_shifts):
        for gid in eng.lineup(slot):
            out.setdefault(gid, set()).add(slot)
    return out


def _cover_note(eng, run, g, slot: int, sched: dict) -> tuple:
    """(text, colour, allowed) for one analyst as cover for `slot`."""
    if g.id == eng.modal["sick"]:
        return "Sick", C.bad, False
    if g.id in run.away_week:
        return "Away this week", C.faint, False
    if slot in sched.get(g.id, set()):
        return "Already on that shift", C.faint, False
    mine = sched.get(g.id, set())
    if g.on_shift:
        return "On shift now: makes a double shift", C.warn, True
    if g.id in run.roster.leave:
        return "On leave: cancels their leave recovery", C.warn, True
    if slot - 1 in mine or slot + 1 in mine:
        return "Back-to-back with their own shift", C.warn, True
    return "Off duty", C.good, True


def staffing_modal(scene, surf, mouse) -> list:
    eng, run, data = scene.eng, scene.run, scene.data
    m = eng.modal
    slot, sick_id = m["slot"], m["sick"]
    sick = eng.ghas.get(sick_id) or run.gha(sick_id)
    n_shifts = eng.n_shifts
    slots = 7 * n_shifts
    sched = _schedule(eng)
    order = {key: i for i, key in enumerate(data.team_keys + ["bench", "leave"])}
    people = sorted([g for g in run.active_ghas()], key=lambda g: (order.get(group_of(run, g), 99), g.name))
    if sick is not None and sick not in people:
        people.insert(0, sick)
    row_h = 34
    height = 196 + len(people) * row_h + 84
    rect = _card(surf, 1640, min(H - 40, height), f"Find cover: {eng.slot_label(slot)}", C.warn)
    lineup = [eng.ghas[g].first_name for g in eng.lineup(slot) if g in eng.ghas]
    name = sick.name if sick else "Someone"
    draw_text(surf, f"{name} is sick. Still rostered: {', '.join(lineup) or 'nobody'}.", (rect.x + 26, rect.y + 60),
              15, C.dim, max_width=rect.width - 52)
    draw_text(surf, "Click someone to cover the shift (the highlighted column), or leave it short. The grid shows who "
                    "works when this week.", (rect.x + 26, rect.y + 84), 13, C.faint, max_width=rect.width - 52)
    # columns
    x_name, x_team, x_fat, x_note = rect.x + 26, rect.x + 330, rect.x + 440, rect.x + 580
    gx = rect.x + 860
    cw = (rect.right - 26 - gx) // slots
    head_y = rect.y + 116
    for d in range(7):
        r = pygame.Rect(gx + d * n_shifts * cw, head_y, n_shifts * cw - 3, 20)
        pygame.draw.rect(surf, C.panel2, r, border_radius=4)
        draw_text(surf, DAY_NAMES[d].upper(), r.center, 11, C.text, "bold", anchor="center")
        for s in range(n_shifts):
            sh = data.shifts[s]
            cx = gx + (d * n_shifts + s) * cw + cw // 2 - 1
            draw_text(surf, sh["name"][0], (cx, head_y + 30), 10, sh["color"], "bold", anchor="center")
    for label, x in (("ANALYST", x_name), ("TEAM", x_team), ("FATIGUE / LT", x_fat), ("AS COVER", x_note)):
        draw_text(surf, label, (x, head_y + 24), 10, C.faint, "bold")
    top = head_y + 44
    col_rect = pygame.Rect(gx + slot * cw - 2, head_y - 4, cw + 1, top - head_y + len(people) * row_h + 6)
    pygame.draw.rect(surf, mix(C.warn, C.panel, 0.82), col_rect, border_radius=5)
    pygame.draw.rect(surf, C.warn, col_rect, 2, border_radius=5)
    if 0 <= eng.slot < slots:
        now_x = gx + eng.slot * cw + cw // 2 - 1
        draw_text(surf, "now", (now_x, head_y - 16), 10, C.accent, "bold", anchor="center")
    buttons = []
    hovered = None
    y = top
    for g in people:
        row = pygame.Rect(rect.x + 16, y, rect.width - 32, row_h - 4)
        note, note_col, allowed = _cover_note(eng, run, g, slot, sched)
        hover = row.collidepoint(mouse) and allowed
        if hover:
            hovered = g
            pygame.draw.rect(surf, C.hover, row, border_radius=7)
        elif allowed:
            pygame.draw.rect(surf, C.panel2, row, border_radius=7)
        if allowed:
            b = Button(row, "", lambda gid=g.id: scene.choose_cover(gid), "ghost")
            buttons.append(b)
        tcol = team_color_of(data, run, g)
        pygame.draw.rect(surf, tcol, (row.x, row.y + 5, 3, row.height - 10), border_radius=2)
        draw_portrait(surf, (x_name + 13, row.centery), 13, g, data, run, team_color=tcol, dim=not allowed)
        draw_text(surf, g.name, (x_name + 34, row.centery), 14, C.text if allowed else C.faint, "semibold",
                  anchor="midleft", max_width=x_team - x_name - 44)
        draw_text(surf, group_label(data, group_of(run, g)), (x_team, row.centery), 12, tcol, anchor="midleft",
                  max_width=x_fat - x_team - 10)
        bar(surf, (x_fat, row.centery - 6, 56, 5), g.fatigue / 100.0, fatigue_color(g.fatigue))
        bar(surf, (x_fat, row.centery + 2, 56, 4), g.ltf / 100.0, fatigue_color(g.ltf))
        draw_text(surf, f"{g.fatigue:.0f} / {g.ltf:.0f}", (x_fat + 64, row.centery), 12, fatigue_color(max(g.fatigue, g.ltf)),
                  anchor="midleft")
        draw_text(surf, note, (x_note, row.centery), 12, note_col if allowed else C.faint, anchor="midleft",
                  max_width=gx - x_note - 16)
        mine = sched.get(g.id, set())
        for s in range(slots):
            cell = pygame.Rect(gx + s * cw, row.y + 4, cw - 3, row.height - 8)
            past = s < eng.slot
            if s in mine:
                fill = mix(tcol, C.panel, 0.7 if past else 0.35)
                pygame.draw.rect(surf, fill, cell, border_radius=4)
            elif g.id == sick_id and s == slot:
                pygame.draw.rect(surf, mix(C.bad, C.panel, 0.55), cell, border_radius=4)
                draw_text(surf, "sick", cell.center, 9, C.white, "bold", anchor="center")
            else:
                pygame.draw.rect(surf, (28, 33, 44) if not past else (24, 28, 37), cell, border_radius=4)
            if hover and s == slot:
                pygame.draw.rect(surf, C.good, cell, 2, border_radius=4)
                draw_text(surf, "+", cell.center, 13, C.good, "bold", anchor="center")
        y += row_h
    if hovered is not None:
        TOOLTIP.set(gha_tooltip(hovered, data, [("Click to have them cover this shift.", C.good, 12)], run), 330)
    nb = Button((rect.x + 26, rect.bottom - 62, 360, 42), "Leave the shift short", lambda: scene.choose_cover(None),
                "danger", 14)
    nb.draw(surf, mouse)
    buttons.append(nb)
    return buttons


def callin_modal(scene, surf, mouse) -> list:
    eng = scene.eng
    opts = eng.call_in_options()[:10]
    cost = eng.call_in_cost()
    height = 150 + len(opts) * 48 + 60
    rect = _card(surf, 780, height, "Call someone in", C.accent)
    free = None in eng.seats
    msg = (f"Overtime costs {fmt_money(cost)} and adds long-term fatigue. They arrive in "
           f"{eng.cfg['run']['call_in_arrive_minutes']} minutes and stay until the shift ends.")
    draw_wrapped(surf, msg, (rect.x + 26, rect.y + 58, rect.width - 52, 40), 13, C.dim)
    buttons = []
    y = rect.y + 104
    for g in opts:
        row = pygame.Rect(rect.x + 26, y, rect.width - 52, 42)
        ok = free and scene.run.budget >= cost
        b = Button(row, "", lambda gid=g.id: scene.do_call_in(gid), "ghost", enabled=ok)
        b.draw(surf, mouse)
        draw_gha_chip(surf, pygame.Rect(row.x, row.y, 320, 42), g, scene.data, mouse, run=scene.run)
        on_leave = g.id in scene.run.roster.leave
        note = ("On leave: cancels leave recovery" if on_leave
                else f"Off duty · {group_label(scene.data, group_of(scene.run, g))}")
        _rich_line(surf, note, (row.x + 336, row.y + 13), 12, C.warn if on_leave else C.dim, row.width - 350)
        buttons.append(b)
        y += 48
    if not free:
        draw_text(surf, "Every desk is taken.", (rect.x + 26, y + 6), 14, C.warn)
    elif not opts:
        draw_text(surf, "Nobody is available.", (rect.x + 26, y + 6), 14, C.faint)
    cb = Button((rect.x + 26, rect.bottom - 56, rect.width - 52, 38), "Cancel", scene.close_callin, "ghost", 14)
    cb.draw(surf, mouse)
    buttons.append(cb)
    return buttons


def pause_menu(scene, surf, mouse) -> list:
    rect = _card(surf, 440, 300, "Paused", C.border2)
    buttons = [
        Button((rect.x + 30, rect.y + 76, rect.width - 60, 46), "Resume", scene.close_menu, "primary", 15),
        Button((rect.x + 30, rect.y + 132, rect.width - 60, 46), "How to play", scene.open_help, "secondary", 15),
        Button((rect.x + 30, rect.y + 188, rect.width - 60, 46), "Quit to title (this week is lost)",
               scene.quit_to_title, "danger", 14),
    ]
    draw_text(surf, "The game saves at the start of every week.", (rect.centerx, rect.bottom - 26), 12, C.faint,
              anchor="center")
    for b in buttons:
        b.draw(surf, mouse)
    return buttons


def banner(surf, title: str, sub: str, color=C.accent):
    """Pause banner over the wall screens (clear of the desk cards), with a wrapped subtitle."""
    from ..theme import Fonts
    width = 700
    rows = wrap(sub, 13, "regular", width - 40)
    lh = Fonts.get(13).get_linesize()
    rect = pygame.Rect(0, 0, width, 56 + lh * len(rows))
    rect.midtop = (W // 2, 150)
    alpha_rect(surf, rect.inflate(12, 12), (0, 0, 0, 110), radius=14)
    panel(surf, rect, (20, 26, 36), color, radius=10, width=2)
    draw_text(surf, title, (rect.centerx, rect.y + 12), 20, color, "bold", anchor="midtop")
    for i, row in enumerate(rows):
        draw_text(surf, row, (rect.centerx, rect.y + 44 + i * lh), 13, C.dim, anchor="midtop")
