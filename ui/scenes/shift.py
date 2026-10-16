"""The main play screen: one week of shifts."""
from __future__ import annotations

import math

import pygame

from game.engine import AUTO_MODES
from game.run import consumable_slots, finish_week
from game.util import fmt_money

from ..app import Scene
from ..icons import get_icons
from ..theme import C, H, W
from ..widgets import TOOLTIP, Button, alpha_rect, draw_text, panel, pill
from . import modals
from .common import consumable_lines
from .help import HelpOverlay
from .map_panel import MapPanel
from .shift_draw import (CENTER, DOOR, INBOX, INBOX_CARD_H, MAP_RECT, draw_desks, draw_hud, draw_inbox,
                         draw_inbox_card, draw_log, draw_room, draw_sop, draw_toasts, draw_tools, right_column,
                         seat_center)

SORTS = ["urgency", "importance", "newest"]
SUPPLY_MIN_X = 860              # supplies sit right-aligned against the Call in button
AUTO_W, MODE_W = 58, 150
AUTO_MENU_W = 460


class ShiftScene(Scene):
    def __init__(self, app, run, eng):
        super().__init__(app)
        self.run = run
        self.eng = eng
        self.data = app.data
        tcfg = self.data.config["time"]
        self.day_start = tcfg["day_start_hour"]
        self.mps = 1440.0 / tcfg["day_length_seconds"]
        self.speeds = tcfg["speed_options"]
        self.speed_i = min(len(self.speeds) - 1, tcfg.get("default_speed_index", 1))
        self.paused = tcfg.get("pause_on_week_start", True)
        self.banner = None
        if self.paused:
            tip = ("Drag inbox cards onto desks, or hover a card and press a desk number. Space starts the clock."
                   if run.week == 0 else "Press Space (or the play button) to start the clock.")
            self.banner = (f"Week {run.week + 1} begins", tip)
        self.real_t = 0.0
        self.screen_t = 0.0          # wall screens only move while the clock runs
        self.sort_mode = 0
        self.inbox_scroll = 0
        self.inbox_area = INBOX
        self.selected: set = set()
        self.press = None
        self.drag = None
        self.card_rects: list = []
        self.desk_rects: dict = {}
        self.queue_slots: dict = {}
        self.toasts: list = []
        self.floats: list = []
        self.actors: dict = {}
        self.ripples: list = []
        self.activity = 0.0
        self.targeting = None
        self.menu = False
        self.callin = False
        self.auto_menu = False
        self.help = HelpOverlay()
        self.modal_buttons: list = []
        self.end_timer = None
        self.hover_task = None
        self.map_highlight = None
        self.map = MapPanel(self.data, MAP_RECT)
        self.sort_button = Button((INBOX.right - 162, INBOX.y + 9, 150, 26), "Sort: urgency", self.cycle_sort, "ghost",
                                  12, tooltip="Change inbox order (Tab)")
        self.hud_buttons: list = []
        self.inbox_buttons: list = []
        self.supply_buttons: list = []
        self.supply_x = SUPPLY_MIN_X
        self.auto_rects: list = []
        self.tools_rect, self.tool_size, self.tools_per_row, self.sop_rect, self.log_rect = right_column(self)
        self._build_hud()
        for i, gid in enumerate(eng.seats):
            if gid is not None:
                x, y = seat_center(self, i)
                self.actors[gid] = {"x": DOOR[0] + i * 6, "y": DOOR[1], "alpha": 0.0, "tx": x, "ty": y}

    # ----------------------------------------------------------------- HUD
    def _build_hud(self):
        buttons = []
        slots = consumable_slots(self.data, self.run)
        speed_x = W - 16 - 44 - 4 * 50
        callin_x = speed_x - 10 - 96
        avail = callin_x - 10 - SUPPLY_MIN_X
        bw = int(max(70, min(132, (avail + 6) / max(1, slots) - 6)))
        x = self.supply_x = max(SUPPLY_MIN_X, callin_x - 10 - slots * (bw + 6) + 6)
        self.supply_buttons = []
        for i in range(slots):
            if i < len(self.run.consumables):
                cid = self.run.consumables[i]
                b = Button((x, 18, bw, 44), "", lambda idx=i: self.use_item(idx), "secondary", 12,
                           tooltip=consumable_lines(cid, self.data))
                b.selected = self.targeting is not None and self.targeting["index"] == i
                self.supply_buttons.append((b, cid))
            else:
                b = Button((x, 18, bw, 44), "empty", None, "ghost", 11, enabled=False)
            buttons.append(b)
            x += bw + 6
        buttons.append(Button((callin_x, 18, 96, 44), "Call in", self.open_callin, "secondary", 13,
                              tooltip=[("Call in an off-duty analyst for the rest of this shift.", C.text, 13),
                                       (f"Costs {fmt_money(self.eng.call_in_cost())} overtime.", C.dim, 12)]))
        self._build_auto()
        sx = speed_x
        self.pause_button = Button((sx, 16, 44, 44), "", self.toggle_pause, "primary" if self.paused else "secondary")
        buttons.append(self.pause_button)
        sx += 50
        for i, sp in enumerate(self.speeds):
            lab = "½×" if sp == 0.5 else f"{sp:g}×"
            b = Button((sx, 16, 46, 44), lab, lambda idx=i: self.set_speed(idx), "ghost", 13)
            b.selected = i == self.speed_i
            buttons.append(b)
            sx += 50
        self.hud_buttons = buttons

    def _build_auto(self):
        """Auto-assign switch and rule picker, right-aligned under the inbox's Sort button."""
        auto = self.eng.auto
        on = auto["on"]
        label, desc = AUTO_MODES[auto["mode"]]
        y = INBOX.y + 44
        mode_x = INBOX.right - 12 - MODE_W
        auto_b = Button((mode_x - 6 - AUTO_W, y, AUTO_W, 28), "ON" if on else "OFF", self.toggle_auto,
                        "good" if on else "secondary", 12,
                        tooltip=[("Auto-assign (A)", C.text, 13, "bold"),
                                 ("Hands each new task to an analyst using the rule on the right. Cards you "
                                  "drag back to the inbox are left for you. You can still drag and reorder "
                                  "anything.", C.dim, 12)])
        mode_b = Button((mode_x, y, MODE_W, 28), label, self.toggle_auto_menu, "ghost", 12,
                        tooltip=[(label, C.text, 13, "bold"), (desc, C.dim, 12), ("Click to change the rule.", C.faint, 11)])
        mode_b.selected = self.auto_menu
        self.auto_button = auto_b
        self.mode_button = mode_b
        self.inbox_buttons = [auto_b, mode_b]

    def draw_chevron(self, surf):
        r = self.mode_button.rect
        x, y = r.right - 14, r.centery
        pygame.draw.polygon(surf, C.white if self.auto_menu else C.dim, [(x - 4, y - 2), (x + 4, y - 2), (x, y + 3)])

    def draw_supply_icons(self, surf):
        icons = get_icons()
        for b, cid in self.supply_buttons:
            c = self.data.consumables[cid]
            r = b.rect
            x = r.x + 6
            if icons is not None:
                icons.draw(surf, "supplies", cid, (x, r.centery), 28, anchor="midleft")
                x += 34
            draw_text(surf, c.get("short", c["name"]), (x, r.centery), 12, C.supply, "semibold", anchor="midleft",
                      max_width=r.right - x - 6)

    def toggle_pause(self):
        self.paused = not self.paused
        if not self.paused:
            self.banner = None

    def set_speed(self, idx: int):
        self.speed_i = max(0, min(len(self.speeds) - 1, idx))
        if self.paused:
            self.toggle_pause()

    def cycle_sort(self):
        self.sort_mode = (self.sort_mode + 1) % len(SORTS)
        self.sort_button.label = f"Sort: {SORTS[self.sort_mode]}"

    def toggle_auto(self):
        on = not self.eng.auto["on"]
        self.eng.set_auto(on=on)
        self.toast(f"Auto-assign on: {AUTO_MODES[self.eng.auto['mode']][0].lower()}" if on else "Auto-assign off",
                   "accent" if on else "info")
        self._build_hud()

    def toggle_auto_menu(self):
        self.auto_menu = not self.auto_menu
        self._build_hud()

    def set_auto_mode(self, mode: str):
        self.eng.set_auto(mode=mode)
        self.auto_menu = False
        self.toast(f"Auto-assign rule: {AUTO_MODES[mode][0].lower()}" + ("" if self.eng.auto["on"] else " (switch it on)"),
                   "accent")
        self._build_hud()

    def toast(self, text: str, tone: str = "info", big: bool = False):
        self.toasts.append({"text": text, "tone": tone, "t": 6.0 if big else 4.0, "big": big})
        if len(self.toasts) > 8:
            self.toasts = self.toasts[-8:]

    # -------------------------------------------------------------- actions
    def use_item(self, index: int):
        if index >= len(self.run.consumables):
            return
        c = self.data.consumables[self.run.consumables[index]]
        target = c.get("target", "none")
        if target == "none":
            ok, msg = self.eng.use_consumable(index)
            self.toast(msg, "good" if ok else "bad")
        else:
            self.targeting = {"index": index, "kind": target, "name": c["name"]}

    def open_callin(self):
        self.callin = True

    def close_callin(self):
        self.callin = False

    def do_call_in(self, gid: int):
        ok, msg = self.eng.call_in(gid)
        self.toast(msg, "good" if ok else "bad")
        if ok:
            self.callin = False

    def close_menu(self):
        self.menu = False

    def open_help(self):
        self.menu = False
        self.help.visible = True

    def quit_to_title(self):
        from .title import TitleScene
        self.app.change(TitleScene(self.app))

    def choose_event(self, idx: int):
        for msg in self.eng.resolve_event(idx):
            self.toast(msg, "accent")

    def choose_cover(self, gid):
        self.eng.resolve_staffing(gid)

    # ---------------------------------------------------------------- inbox
    def sorted_inbox(self) -> list:
        eng = self.eng
        tasks = eng.visible_inbox()

        def left(t):
            if t.available is None:
                return 1e9
            return t.available + t.deadline - eng.now
        if SORTS[self.sort_mode] == "urgency":
            tasks.sort(key=lambda t: (t.locked, not t.overdue, left(t)))
        elif SORTS[self.sort_mode] == "importance":
            tasks.sort(key=lambda t: (t.locked, -t.importance, left(t)))
        else:
            tasks.sort(key=lambda t: (t.locked, -t.created))
        return tasks

    def card_at(self, pos):
        for rect, tid, origin in reversed(self.card_rects):
            if rect.collidepoint(pos):
                return rect, tid, origin
        return None

    def drop_index(self, gid: int, y: int) -> int:
        g = self.eng.ghas.get(gid)
        if g is None:
            return 0
        slots = self.queue_slots.get(gid, [])
        for rect, tid in slots:
            if y < rect.centery and tid in g.queue:
                return g.queue.index(tid)
        return len(g.queue)

    def assign_many(self, tids: list, gid: int, index: int | None = None):
        eng = self.eng
        g = eng.ghas.get(gid)
        if g is None:
            return
        order = {t.id: i for i, t in enumerate(self.sorted_inbox())}
        tids = sorted(tids, key=lambda t: order.get(t, 10_000))
        if index is None:
            for tid in tids:
                eng.assign(tid, gid, by_player=True)
            return
        base = index - sum(1 for q in g.queue[:index] if q in tids)
        for k, tid in enumerate(tids):
            eng.assign(tid, gid, base + k, by_player=True)

    # --------------------------------------------------------------- update
    def running(self) -> bool:
        return not (self.paused or self.menu or self.callin or self.help.visible or self.eng.modal or self.targeting
                    or self.end_timer is not None)

    def update(self, dt: float):
        self.real_t += dt
        eng = self.eng
        if self.end_timer is not None:
            self.end_timer -= dt
            self._tick_effects(dt, False)
            self._update_actors(dt)
            if self.end_timer <= 0:
                self._finish()
            return
        running = self.running()
        if running:
            eng.update(dt * self.mps * self.speeds[self.speed_i])
            self.screen_t += dt
        for note in eng.drain_notes():
            self._on_note(note)
        self._tick_effects(dt, running)
        self._update_actors(dt)
        if eng.game_over and self.end_timer is None:
            self.end_timer = 2.5
            self.toast("Public trust has collapsed.", "bad", big=True)
        elif eng.week_done and self.end_timer is None:
            self.end_timer = 1.2
            self.toast("End of the week. Handing over…", "accent", big=True)
        self._build_hud()

    def _on_note(self, n: dict):
        kind = n["type"]
        if kind == "toast":
            self.toast(n["text"], n.get("tone", "info"), n.get("big", False))
        elif kind == "float":
            self.floats.append({"gha": n["gha"], "text": n["text"], "tone": n.get("tone", "info"), "t": 1.6, "life": 1.6})
        elif kind == "eq":
            ev = self.eng.events.get(n["uid"])
            self.ripples.append((n["uid"], self.screen_t))
            if ev is not None:
                self.activity = min(40.0, self.activity + max(0.0, ev.mag - 1.0) ** 1.5 * 2.0)
        elif kind == "pause":
            self.paused = True
            if n.get("reason") == "dart":
                self.banner = ("DART triggered", "Clock paused. 'Assess DART signals' was added to the running SOP.")
            else:
                self.banner = ("SOP activated", "Clock paused. Queue the SOP steps (locked ones too), then press Space.")
        elif kind == "shift":
            self.toast(f"{n['label'][0].upper()}{n['label'][1:]} begins", "info")

    def _tick_effects(self, dt: float, running: bool = True):
        for t in self.toasts:
            t["t"] -= dt
        self.toasts = [t for t in self.toasts if t["t"] > 0]
        for f in self.floats:
            f["t"] -= dt
        self.floats = [f for f in self.floats if f["t"] > 0]
        self.ripples = [r for r in self.ripples if self.screen_t - r[1] < 1.5]
        if running:
            self.activity *= math.exp(-dt * 0.7)

    def _update_actors(self, dt: float):
        eng = self.eng
        wanted = {}
        for i, gid in enumerate(eng.seats):
            if gid is None:
                continue
            g = eng.ghas.get(gid)
            if g is None or eng.now < g.away_until:
                continue
            wanted[gid] = seat_center(self, i)
        for gid, pos in wanted.items():
            a = self.actors.get(gid)
            if a is None:
                a = self.actors[gid] = {"x": float(DOOR[0]), "y": float(DOOR[1]), "alpha": 0.0}
            a["tx"], a["ty"], a["leaving"] = pos[0], pos[1], False
        for gid, a in list(self.actors.items()):
            if gid not in wanted:
                a["tx"], a["ty"], a["leaving"] = DOOR[0], DOOR[1], True
            dx, dy = a["tx"] - a["x"], a["ty"] - a["y"]
            dist = math.hypot(dx, dy)
            step = min(dist, 640.0 * dt)
            if dist > 0.01:
                a["x"] += dx / dist * step
                a["y"] += dy / dist * step
            if a.get("leaving"):
                if dist < 40:
                    a["alpha"] = max(0.0, a["alpha"] - dt * 3)
                if a["alpha"] <= 0.0 and dist < 2:
                    del self.actors[gid]
                    continue
            else:
                a["alpha"] = min(1.0, a["alpha"] + dt * 3)
            g = eng.ghas.get(gid)
            a["seated"] = dist < 2 and not a.get("leaving")
            a["working"] = bool(a["seated"] and g is not None and eng.present(g) and eng.current_task(g) is not None)

    def _finish(self):
        from .summary import GameOverScene, SummaryScene
        if self.eng.game_over:
            self.run.phase = "over"
            self.app.change(GameOverScene(self.app, self.run, self.eng))
            return
        summary = finish_week(self.data, self.run, self.eng)
        if self.run.phase == "planning":
            self.app.save()
        self.app.change(SummaryScene(self.app, self.run, summary))

    # ---------------------------------------------------------------- input
    def handle(self, event):
        if self.help.handle(event) or self.end_timer is not None:
            return
        if self.menu or self.callin or self.eng.modal:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.menu = False
                self.callin = False
                return
            for b in self.modal_buttons:
                if b.handle(event):
                    return
            return
        if self.auto_menu:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, mode in self.auto_rects:
                    if rect.collidepoint(event.pos):
                        self.set_auto_mode(mode)
                        return
                self.auto_menu = False
                self._build_hud()
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.auto_menu = False
                self._build_hud()
                return
        if event.type == pygame.KEYDOWN:
            self._key(event)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not self.targeting:
            for b in self.hud_buttons + self.inbox_buttons + [self.sort_button]:
                if b.handle(event):
                    return
        if event.type == pygame.MOUSEWHEEL:
            if self.inbox_area.collidepoint(pygame.mouse.get_pos()):
                self.inbox_scroll = max(0, self.inbox_scroll - event.y * 50)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._left_down(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._right_down(event.pos)
        elif event.type == pygame.MOUSEMOTION:
            self._motion(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._left_up(event.pos)

    def _key(self, event):
        k = event.key
        if k == pygame.K_SPACE:
            self.toggle_pause()
        elif k in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_RIGHTBRACKET):
            self.set_speed(self.speed_i + 1)
        elif k in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFTBRACKET):
            self.set_speed(self.speed_i - 1)
        elif k == pygame.K_TAB:
            self.cycle_sort()
        elif k == pygame.K_a:
            self.toggle_auto()
        elif k in (pygame.K_h, pygame.K_F1):
            self.help.toggle()
        elif k == pygame.K_ESCAPE:
            if self.drag or self.press:
                self.drag = self.press = None
            elif self.targeting:
                self.targeting = None
            elif self.selected:
                self.selected.clear()
            else:
                self.menu = True
        elif pygame.K_1 <= k <= pygame.K_9:
            self._assign_to_seat(k - pygame.K_1)
        elif pygame.K_KP1 <= k <= pygame.K_KP9:
            self._assign_to_seat(k - pygame.K_KP1)

    def _assign_to_seat(self, seat: int):
        eng = self.eng
        if seat >= len(eng.seats) or eng.seats[seat] is None:
            self.toast(f"Nobody at desk {seat + 1}", "warn")
            return
        tids = list(self.selected) or ([self.hover_task] if self.hover_task is not None else [])
        if not tids:
            return
        self.assign_many(tids, eng.seats[seat])
        self.selected.clear()

    def _left_down(self, pos):
        if self.targeting:
            self._apply_target(pos)
            return
        hit = self.card_at(pos)
        if hit:
            rect, tid, origin = hit
            self.press = {"tid": tid, "pos": pos, "off": (pos[0] - rect.x, pos[1] - rect.y), "origin": origin}
        elif not (pygame.key.get_mods() & (pygame.KMOD_SHIFT | pygame.KMOD_CTRL)):
            self.selected.clear()

    def _apply_target(self, pos):
        tgt = self.targeting
        self.targeting = None
        eng = self.eng
        target = None
        if tgt["kind"] == "gha":
            for rect, gid in self.desk_rects.values():
                if pygame.Rect(rect.x, rect.y, rect.width, 96).collidepoint(pos):
                    target = eng.ghas.get(gid)
        else:
            hit = self.card_at(pos)
            if hit:
                target = eng.tasks.get(hit[1])
        if target is None:
            self.toast("Cancelled", "info")
            return
        ok, msg = eng.use_consumable(tgt["index"], target)
        self.toast(msg, "good" if ok else "bad")

    def _right_down(self, pos):
        if self.targeting:
            self.targeting = None
            return
        hit = self.card_at(pos)
        if hit and hit[2] is not None:
            self.eng.unassign(hit[1])
            self.selected.discard(hit[1])

    def _motion(self, pos):
        if self.press and not self.drag:
            sx, sy = self.press["pos"]
            if abs(pos[0] - sx) + abs(pos[1] - sy) > 6:
                tid = self.press["tid"]
                tids = sorted(self.selected) if (tid in self.selected and len(self.selected) > 1) else [tid]
                self.drag = {"tids": tids, "off": self.press["off"]}

    def _left_up(self, pos):
        if self.drag:
            self._drop(pos)
        elif self.press:
            tid = self.press["tid"]
            if pygame.key.get_mods() & (pygame.KMOD_SHIFT | pygame.KMOD_CTRL):
                if tid in self.selected:
                    self.selected.discard(tid)
                else:
                    self.selected.add(tid)
            else:
                self.selected = set() if self.selected == {tid} else {tid}
        self.press = None
        self.drag = None

    def _drop(self, pos):
        tids = self.drag["tids"]
        for rect, gid in self.desk_rects.values():
            if rect.collidepoint(pos):
                self.assign_many(tids, gid, self.drop_index(gid, pos[1]))
                self.selected.clear()
                return
        if self.inbox_area.collidepoint(pos) or INBOX.collidepoint(pos):
            for tid in tids:
                t = self.eng.tasks.get(tid)
                if t is not None and t.assignee is not None:
                    self.eng.unassign(tid)
            self.selected.clear()

    # ----------------------------------------------------------------- draw
    def draw(self, surf):
        mouse = pygame.mouse.get_pos()
        blocking = self.menu or self.callin or self.eng.modal or self.help.visible or self.auto_menu
        live = (-1, -1) if blocking else mouse
        self.card_rects = []
        draw_room(self, surf, live, self.real_t)
        draw_desks(self, surf, live)
        draw_inbox(self, surf, live)
        hit = self.card_at(live) if not self.drag else None
        self.hover_task = hit[1] if hit else None
        hover = self.eng.tasks.get(self.hover_task) if self.hover_task is not None else None
        self.map_highlight = (self.eng.events.get(hover.event_uid)
                              if hover is not None and hover.event_uid is not None else None)
        self.tools_rect, self.tool_size, self.tools_per_row, self.sop_rect, self.log_rect = right_column(self)
        draw_tools(self, surf, live)
        draw_sop(self, surf, live)
        draw_log(self, surf, live)
        draw_hud(self, surf, live)
        self._draw_pause_icon(surf)
        draw_toasts(self, surf)
        if self.paused and self.banner:
            modals.banner(surf, *self.banner, C.sop if self.banner[0].startswith(("SOP", "DART")) else C.accent)
        if self.paused and not blocking:
            speed_group = self.pause_button.rect.union(self.hud_buttons[-1].rect)
            pill(surf, "PAUSED", (speed_group.centerx, 1), C.bg, C.warn, size=9, pad_y=1, anchor="midtop")
        if self.targeting:
            what = "an analyst's desk" if self.targeting["kind"] == "gha" else "a task card"
            pill(surf, f"{self.targeting['name']}: click {what} (Esc to cancel)", (CENTER.centerx, H - 16), C.bg,
                 C.gold, size=14, anchor="midbottom", pad_x=12, pad_y=6)
        if self.drag:
            self._draw_drag(surf, mouse)
        if self.auto_menu:
            self._draw_auto_menu(surf, mouse)
        self.modal_buttons = []
        if self.eng.modal and self.end_timer is None:
            if self.eng.modal["type"] == "event":
                self.modal_buttons = modals.event_modal(self, surf, mouse)
            elif self.eng.modal["type"] == "staffing":
                self.modal_buttons = modals.staffing_modal(self, surf, mouse)
        elif self.callin:
            self.modal_buttons = modals.callin_modal(self, surf, mouse)
        elif self.menu:
            self.modal_buttons = modals.pause_menu(self, surf, mouse)
        self.help.draw(surf)

    def _draw_auto_menu(self, surf, mouse):
        rect = pygame.Rect(8, self.mode_button.rect.bottom + 6, AUTO_MENU_W, 12 + len(AUTO_MODES) * 52)
        alpha_rect(surf, rect.inflate(10, 10), (0, 0, 0, 110), radius=12)
        panel(surf, rect, (22, 27, 36), C.border2, radius=9)
        self.auto_rects = []
        current = self.eng.auto["mode"]
        for i, (key, (label, desc)) in enumerate(AUTO_MODES.items()):
            r = pygame.Rect(rect.x + 6, rect.y + 6 + i * 52, rect.width - 12, 48)
            hover = r.collidepoint(mouse)
            if hover or key == current:
                pygame.draw.rect(surf, C.hover if hover else C.panel3, r, border_radius=7)
            if key == current:
                pygame.draw.rect(surf, C.accent, (r.x, r.y + 8, 3, r.height - 16), border_radius=2)
            draw_text(surf, label, (r.x + 14, r.y + 6), 14, C.text if key != current else C.accent, "semibold")
            draw_text(surf, desc, (r.x + 14, r.y + 27), 11, C.dim, max_width=r.width - 24)
            self.auto_rects.append((r, key))

    def _draw_pause_icon(self, surf):
        r = self.pause_button.rect
        cx, cy = r.center
        col = C.white
        if self.paused:
            pygame.draw.polygon(surf, col, [(cx - 6, cy - 9), (cx - 6, cy + 9), (cx + 9, cy)])
        else:
            pygame.draw.rect(surf, col, (cx - 8, cy - 9, 5, 18), border_radius=1)
            pygame.draw.rect(surf, col, (cx + 3, cy - 9, 5, 18), border_radius=1)

    def _draw_drag(self, surf, mouse):
        tids = self.drag["tids"]
        off = self.drag["off"]
        base = pygame.Rect(mouse[0] - min(off[0], 120), mouse[1] - off[1], INBOX.width - 16, INBOX_CARD_H)
        for k, tid in enumerate(reversed(tids[:3])):
            t = self.eng.tasks.get(tid)
            if t is None:
                continue
            rect = base.move(6 * (min(3, len(tids)) - 1 - k), 6 * (min(3, len(tids)) - 1 - k))
            alpha_rect(surf, rect.inflate(10, 10), (0, 0, 0, 90), radius=10)
            draw_inbox_card(self, surf, rect, t, (-1, -1), True)
        if len(tids) > 1:
            pill(surf, f"{len(tids)} tasks", (base.right - 4, base.y - 8), C.bg, C.accent, size=12, anchor="topright")
        TOOLTIP.clear()
