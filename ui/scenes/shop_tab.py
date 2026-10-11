"""Shop tab: hire analysts, buy tools, supplies and training."""
from __future__ import annotations

import pygame

from game import shop
from game.run import consumable_slots
from game.util import fmt_money

from ..theme import C, H, RARITY, W, mix, text_width
from ..widgets import TOOLTIP, Button, alpha_rect, draw_text, draw_wrapped, panel, pill, pips
from .layout import CONTENT_Y
from ..icons import get_icons
from .common import (consumable_lines, trait_colour, draw_gha_chip, draw_portrait, fatigue_color, gha_tooltip, rarity_gem,
                     relic_lines, trait_lines, training_lines)

CARD_W = 336
GAP = 12
SIDE_X = 16 + 4 * (CARD_W + GAP) + 12


def _item_card(surf, rect, accent, hover: bool):
    """Card with a coloured stripe down the left edge and a faint coloured border."""
    panel(surf, rect, C.panel2 if hover else C.panel, mix(accent, C.border, 0.62), radius=8)
    pygame.draw.rect(surf, accent, (rect.x, rect.y + 8, 4, rect.height - 16), border_radius=2)


def _row(n: int, y: int, h: int) -> list:
    """Card rects for one shop row: at least three columns, filling the space left of the side panel."""
    cols = max(3, n)
    w = (SIDE_X - 12 - 16 - (cols - 1) * GAP) // cols
    return [pygame.Rect(16 + i * (w + GAP), y, w, h) for i in range(cols)]


def _card_icon(surf, rect, category: str, item_id: str) -> int:
    """Item icon at the top-left of a shop card; returns the x where text can start."""
    icons = get_icons()
    if icons is None:
        return rect.x + 14
    icons.draw(surf, category, item_id, (rect.x + 14, rect.y + 10), 40)
    return rect.x + 64


class ShopTab:
    def __init__(self, scene):
        self.scene = scene
        self.data = scene.data
        self.buttons: list = []
        self.picker: dict | None = None
        self.picker_rects: list = []

    @property
    def run(self):
        return self.scene.run

    def hint(self) -> str:
        return "Funding arrives at the end of each week, based on performance and trust. Salaries are paid weekly."

    def cancel(self) -> bool:
        if self.picker:
            self.picker = None
            return True
        return False

    def update(self, dt):
        pass

    def _result(self, ok_msg):
        ok, msg = ok_msg
        self.scene.flash(msg, C.good if ok else C.bad)

    def handle(self, event):
        if self.picker:
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, gid in self.picker_rects:
                    if rect.collidepoint(event.pos):
                        self._result(shop.buy_training(self.data, self.run, self.picker["index"], gid))
                        self.picker = None
                        return
                self.picker = None
            return
        for b in self.buttons:
            if b.handle(event):
                return

    # ------------------------------------------------------------------- draw
    def draw(self, surf, mouse):
        run, data = self.run, self.data
        sh = run.shop
        self.buttons = []
        live_mouse = mouse if not self.picker else (-1, -1)
        if not sh:
            draw_text(surf, "The shop is closed.", (W // 2, 400), 18, C.dim, anchor="center")
            return
        y = CONTENT_Y
        draw_text(surf, "HIRE ANALYSTS", (16, y), 12, C.faint, "bold")
        draw_text(surf, "New hires start on the bench. Hiring costs 1.5 weeks' salary up front.", (140, y), 12, C.faint)
        for i, (item, rect) in enumerate(zip(sh["hires"][:4], _row(len(sh["hires"][:4]), y + 22, 206))):
            self._hire_card(surf, rect, i, item, live_mouse)
        y = CONTENT_Y + 246
        draw_text(surf, "TOOLS", (16, y), 12, C.faint, "bold")
        r = draw_text(surf, "Permanent for the rest of the run.", (70, y), 12, C.faint)
        x = r.right + 28
        for rarity, colour in RARITY.items():
            rarity_gem(surf, (x, y + 7), rarity, 4)
            r = draw_text(surf, rarity.title(), (x + 8, y), 11, colour, "semibold")
            x = r.right + 16
        for i, (item, rect) in enumerate(zip(sh["relics"][:4], _row(len(sh["relics"][:4]), y + 22, 124))):
            self._relic_card(surf, rect, i, item, live_mouse)
        y = CONTENT_Y + 408
        slots = consumable_slots(data, run)
        draw_text(surf, "SUPPLIES", (16, y), 12, C.supply, "bold")
        draw_text(surf, f"One use each, during a shift. You can carry {slots}.", (90, y), 12, C.faint)
        for i, (item, rect) in enumerate(zip(sh["consumables"][:4], _row(len(sh["consumables"][:4]), y + 22, 112))):
            self._supply_card(surf, rect, i, item, live_mouse, len(run.consumables) >= slots)
        y = CONTENT_Y + 560
        draw_text(surf, "TRAINING", (16, y), 12, C.training, "bold")
        draw_text(surf, "Applied to one analyst straight away.", (92, y), 12, C.faint)
        for i, (item, rect) in enumerate(zip(sh["training"][:4], _row(max(3, len(sh["training"][:4])), y + 22, 112))):
            self._training_card(surf, rect, i, item, live_mouse)
        self._side(surf, live_mouse)
        for b in self.buttons:
            b.draw(surf, live_mouse)
        if self.picker:
            self._draw_picker(surf, mouse)

    def _sold(self, surf, rect, text):
        alpha_rect(surf, rect, (10, 12, 16, 170), radius=8)
        draw_text(surf, text, rect.center, 16, C.dim, "bold", anchor="center")

    def _hire_card(self, surf, rect, i, item, mouse):
        data = self.data
        g = item["gha"]
        tag_col = C.gold if item["tag"] == "Keen graduate" else C.accent
        panel(surf, rect, C.panel, C.border, radius=8)
        rad = 54                                    # big portrait down the left of the card
        draw_portrait(surf, (rect.x + 12 + rad, rect.y + 12 + rad), rad, g, data, team_color=data.bench_color)
        tx = rect.x + 24 + 2 * rad
        draw_text(surf, g.name, (tx, rect.y + 10), 15, C.text, "bold", max_width=rect.right - tx - 10)
        r = pill(surf, item["tag"], (tx, rect.y + 32), C.bg, tag_col, size=10)
        draw_text(surf, f"{fmt_money(g.salary)}/wk", (r.right + 8, rect.y + 32), 12, C.gold)
        draw_text(surf, f"Long-term fatigue {g.ltf:.0f}", (tx, rect.y + 50), 11, fatigue_color(g.ltf))
        col_w = (rect.right - 10 - tx) // 2
        for j, k in enumerate(data.skill_keys):
            col, row = j // 3, j % 3
            sx, sy = tx + col * col_w, rect.y + 74 + row * 20
            lvl = g.skills.get(k, 1)
            sk_col = data.skill_by_key[k]["color"]
            draw_text(surf, data.skill_abbr(k), (sx, sy), 11, sk_col, "bold")
            pips(surf, (sx + 34, sy + 4), lvl, 5, sk_col, 8, 3, off=mix(sk_col, C.panel, 0.82))
        tx, ty = rect.x + 14, rect.y + 138
        for n, tid in enumerate(g.traits):
            t = data.traits[tid]
            w_needed = text_width(t["name"], 10, "semibold") + 12
            more = len(g.traits) - n - 1
            if tx + w_needed > rect.right - (40 if more else 10):
                pill(surf, f"+{len(g.traits) - n}", (tx, ty), C.text, C.panel3, size=10)
                break
            tr = pill(surf, t["name"], (tx, ty), C.bg, trait_colour(data, tid), size=10)
            if tr.collidepoint(mouse):
                TOOLTIP.set(trait_lines(tid, data), 260)
            tx = tr.right + 5
        if not g.traits:
            draw_text(surf, "No notable traits", (tx, ty), 11, C.faint)
        head = pygame.Rect(rect.x, rect.y, tx - rect.x, 12 + 2 * rad)
        if head.collidepoint(mouse) and not item["sold"]:
            TOOLTIP.set(gha_tooltip(g, data, [("Joins the bench when hired.", C.faint, 11)]), 330)
        if item["sold"]:
            self._sold(surf, rect, "HIRED")
            return
        afford = self.run.budget >= item["cost"]
        self.buttons.append(Button((rect.x + 10, rect.bottom - 38, rect.width - 20, 30),
                                   f"Hire · {fmt_money(item['cost'])}",
                                   lambda idx=i: self.scene_result(shop.buy_hire(self.data, self.run, idx)),
                                   "primary" if afford else "secondary", 13, enabled=afford))

    def scene_result(self, res):
        self._result(res)

    def _relic_card(self, surf, rect, i, item, mouse):
        r = self.data.relics[item["id"]]
        col = RARITY.get(r["rarity"], C.text)
        hover = rect.collidepoint(mouse)
        _item_card(surf, rect, col, hover)
        tx = _card_icon(surf, rect, "tools", item["id"])
        rarity_gem(surf, (tx + 6, rect.y + 18), r["rarity"], 5)
        draw_text(surf, r["name"], (tx + 16, rect.y + 9), 14, col, "bold", max_width=rect.right - tx - 110)
        draw_text(surf, r["rarity"].upper(), (rect.right - 12, rect.y + 11), 10, col, "bold", anchor="topright")
        draw_wrapped(surf, r["desc"], (tx, rect.y + 32, rect.right - tx - 12, 50), 12, C.dim, max_lines=2,
                     rich=True)
        if hover:
            TOOLTIP.set(relic_lines(item["id"], self.data), 300)
        if item["sold"]:
            self._sold(surf, rect, "BOUGHT")
            return
        afford = self.run.budget >= item["cost"]
        self.buttons.append(Button((rect.x + 10, rect.bottom - 38, rect.width - 20, 28),
                                   f"Buy · {fmt_money(item['cost'])}",
                                   lambda idx=i: self.scene_result(shop.buy_relic(self.data, self.run, idx)),
                                   "primary" if afford else "secondary", 13, enabled=afford))

    def _supply_card(self, surf, rect, i, item, mouse, full):
        c = self.data.consumables[item["id"]]
        hover = rect.collidepoint(mouse)
        _item_card(surf, rect, C.supply, hover)
        tx = _card_icon(surf, rect, "supplies", item["id"])
        draw_text(surf, c["name"], (tx, rect.y + 9), 14, C.supply, "bold", max_width=rect.right - tx - 12)
        draw_wrapped(surf, c["desc"], (tx, rect.y + 30, rect.right - tx - 12, 40), 12, C.dim, max_lines=2,
                     rich=True)
        if hover:
            TOOLTIP.set(consumable_lines(item["id"], self.data), 280)
        if item["sold"]:
            self._sold(surf, rect, "BOUGHT")
            return
        afford = self.run.budget >= item["cost"] and not full
        label = "Cupboard full" if full else f"Buy · {fmt_money(item['cost'])}"
        self.buttons.append(Button((rect.x + 10, rect.bottom - 36, rect.width - 20, 28), label,
                                   lambda idx=i: self.scene_result(shop.buy_consumable(self.data, self.run, idx)),
                                   "secondary", 13, enabled=afford))

    def _training_card(self, surf, rect, i, item, mouse):
        t = self.data.training[item["id"]]
        hover = rect.collidepoint(mouse)
        _item_card(surf, rect, C.training, hover)
        tx = _card_icon(surf, rect, "training", item["id"])
        draw_text(surf, t["name"], (tx, rect.y + 9), 14, C.training, "bold", max_width=rect.right - tx - 12)
        draw_wrapped(surf, t["desc"], (tx, rect.y + 30, rect.right - tx - 12, 40), 12, C.dim, max_lines=2,
                     rich=True)
        if hover:
            TOOLTIP.set(training_lines(item["id"], self.data), 280)
        if item["sold"]:
            self._sold(surf, rect, "DONE")
            return
        targets = shop.training_targets(self.data, self.run, i)
        afford = self.run.budget >= item["cost"] and bool(targets)
        label = f"Choose analyst · {fmt_money(item['cost'])}" if targets else "Nobody can use this"
        self.buttons.append(Button((rect.x + 10, rect.bottom - 36, rect.width - 20, 28), label,
                                   lambda idx=i: self._open_picker(idx), "secondary", 13, enabled=afford))

    def _open_picker(self, index):
        self.picker = {"index": index}

    def _side(self, surf, mouse):
        run, data = self.run, self.data
        rect = pygame.Rect(SIDE_X, CONTENT_Y, W - SIDE_X - 16, H - CONTENT_Y - 16)
        panel(surf, rect, C.panel, C.border, radius=8)
        draw_text(surf, f"YOUR TOOLS ({len(run.relics)})", (rect.x + 14, rect.y + 12), 12, C.faint, "bold")
        y = rect.y + 34
        if not run.relics:
            draw_text(surf, "None yet.", (rect.x + 14, y), 13, C.faint)
            y += 24
        for rid in run.relics[:20]:
            r = data.relics[rid]
            row = pygame.Rect(rect.x + 8, y - 2, rect.width - 16, 24)
            if row.collidepoint(mouse):
                pygame.draw.rect(surf, C.panel2, row, border_radius=5)
                TOOLTIP.set(relic_lines(rid, data), 300)
            icons = get_icons()
            if icons is not None:
                icons.draw(surf, "tools", rid, (rect.x + 12, y - 1), 22)
            else:
                rarity_gem(surf, (rect.x + 19, y + 9), r["rarity"], 5)
            draw_text(surf, r["name"], (rect.x + 42, y + 1), 13, RARITY.get(r["rarity"], C.text), "semibold",
                      max_width=rect.width - 60)
            y += 26
        if len(run.relics) > 20:
            draw_text(surf, f"+{len(run.relics) - 20} more", (rect.x + 42, y), 12, C.faint)
            y += 22
        y += 12
        slots = consumable_slots(data, run)
        draw_text(surf, f"SUPPLIES ({len(run.consumables)}/{slots})", (rect.x + 14, y), 12, C.faint, "bold")
        y += 22
        if not run.consumables:
            draw_text(surf, "Empty cupboard.", (rect.x + 14, y), 13, C.faint)
        for cid in run.consumables:
            row = pygame.Rect(rect.x + 8, y - 2, rect.width - 16, 24)
            if row.collidepoint(mouse):
                pygame.draw.rect(surf, C.panel2, row, border_radius=5)
                TOOLTIP.set(consumable_lines(cid, data), 280)
            icons = get_icons()
            if icons is not None:
                icons.draw(surf, "supplies", cid, (rect.x + 12, y - 1), 22)
            draw_text(surf, data.consumables[cid]["name"], (rect.x + 42, y + 1), 13, C.supply, "semibold")
            y += 26
        sh = run.shop
        self.buttons.append(Button((rect.x + 14, rect.bottom - 48, rect.width - 28, 34),
                                   f"Reroll shop · {fmt_money(sh['reroll_cost'])}",
                                   lambda: self.scene_result(shop.reroll(self.data, self.run)), "ghost", 13,
                                   enabled=run.budget >= sh["reroll_cost"],
                                   tooltip="Replace everything on offer. Gets pricier each time this week."))

    def _draw_picker(self, surf, mouse):
        idx = self.picker["index"]
        t = self.data.training[self.run.shop["training"][idx]["id"]]
        targets = shop.training_targets(self.data, self.run, idx)
        alpha_rect(surf, (0, 0, W, H), (5, 8, 12, 170))
        cols = 2
        rows = (len(targets) + cols - 1) // cols
        rect = pygame.Rect(0, 0, 620, 110 + rows * 44)
        rect.center = (W // 2, H // 2)
        panel(surf, rect, C.panel, C.training, radius=12, width=2)
        draw_text(surf, f"{t['name']}: who gets it?", (rect.x + 20, rect.y + 18), 18, C.training, "bold")
        draw_wrapped(surf, t["desc"], (rect.x + 20, rect.y + 46, rect.width - 40, 20), 13, C.dim, max_lines=1,
                     rich=True)
        self.picker_rects = []
        for i, g in enumerate(targets):
            r = pygame.Rect(rect.x + 20 + (i % cols) * 294, rect.y + 76 + (i // cols) * 44, 286, 38)
            draw_gha_chip(surf, r, g, self.data, mouse, run=self.run)
            self.picker_rects.append((r, g.id))
        draw_text(surf, "Click an analyst, or click outside to cancel", (rect.centerx, rect.bottom - 18), 12, C.faint,
                  anchor="center")
