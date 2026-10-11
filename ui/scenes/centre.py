"""The centre hub for a save slot: level and XP, the run in progress, new runs,
recent results and the unlock track."""
from __future__ import annotations

import pygame

from game import save
from game.profile import level_for_xp, unlock_track, unlocked_ids, xp_progress
from game.run import new_run

from ..app import Scene
from ..icons import get_icons
from ..theme import C, H, RARITY, W, mix
from ..widgets import TOOLTIP, Button, bar, draw_text, lock_icon, panel, pill
from .common import consumable_lines, relic_lines, training_lines
from .help import HelpOverlay

LEFT = pygame.Rect(40, 124, 860, H - 124 - 40)
RIGHT = pygame.Rect(940, 124, W - 940 - 40, H - 124 - 40)


def item_lines(data, category: str, iid: str) -> list:
    if category == "tools":
        return relic_lines(iid, data)
    if category == "supplies":
        return consumable_lines(iid, data)
    return training_lines(iid, data)


def item_name(data, category: str, iid: str) -> str:
    src = {"tools": data.relics, "supplies": data.consumables, "training": data.training}[category]
    return src[iid]["name"]


def item_colour(data, category: str, iid: str):
    if category == "tools":
        return RARITY.get(data.relics[iid]["rarity"], C.text)
    return C.supply if category == "supplies" else C.training


class CentreScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.data = app.data
        self.help = HelpOverlay()
        self.buttons: list = []
        self.confirm: str | None = None
        self.pending: str | None = None
        self.message = ""

    @property
    def profile(self):
        return self.app.profile

    def on_enter(self):
        if self.profile is None:
            return
        fresh = save.load_profile(self.profile.slot)
        if fresh is not None:
            self.app.profile = fresh      # the disk copy is the truth (a quit mid-week loses that week)

    # --------------------------------------------------------------- actions
    def continue_run(self):
        run = self.profile.run if self.profile else None
        if run is None:
            return
        from .planning import PlanningScene
        self.app.change(PlanningScene(self.app, run))

    def abandon_run(self):
        if self.confirm != "abandon":
            self.confirm = "abandon"
            return
        self.profile.run = None
        self.app.save()
        self.confirm = None
        self.message = "Run abandoned."

    def start_run(self, length_key: str):
        if self.profile.run is not None and self.confirm != f"new:{length_key}":
            self.confirm = f"new:{length_key}"
            self.message = "You have a run in progress. Click again to abandon it and start a new one."
            return
        if self.app.catalog is None:
            if self.app.catalog_error:
                self.message = self.app.catalog_error
                return
            self.pending = length_key
            self.message = "Waiting for the catalogue to finish loading…"
            return
        self.pending = None
        self.message = "Building your run…"
        self.confirm = None
        self._draw_now()
        level = level_for_xp(self.data, self.profile.xp)
        run = new_run(self.data, self.app.catalog, length_key=length_key, unlock_level=level)
        self.profile.run = run
        self.app.save()
        from .planning import PlanningScene
        self.app.change(PlanningScene(self.app, run))

    def _draw_now(self):
        self.app.screen.fill(C.bg)
        self.draw(self.app.screen)
        pygame.display.flip()

    def to_slots(self):
        from .slots import SlotScene
        self.app.change(SlotScene(self.app))

    def to_title(self):
        from .title import TitleScene
        self.app.change(TitleScene(self.app))

    def handle(self, event):
        if self.help.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.confirm:
                self.confirm = None
                self.message = ""
            else:
                self.to_title()
            return
        for b in self.buttons:
            if b.handle(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.confirm = None

    def update(self, dt: float):
        if self.pending and self.app.catalog is not None:
            self.start_run(self.pending)

    # ------------------------------------------------------------------ draw
    def draw(self, surf):
        if self.profile is None:
            return
        mouse = pygame.mouse.get_pos()
        self.buttons = []
        self._header(surf, mouse)
        self._run_panel(surf, mouse)
        self._new_run_panel(surf, mouse)
        self._history_panel(surf, mouse)
        self._unlocks(surf, mouse)
        for b in self.buttons:
            b.draw(surf, mouse)
        if self.message:
            draw_text(surf, self.message, (LEFT.x, H - 30), 14, C.warn)
        self.help.draw(surf)

    def _header(self, surf, mouse):
        p, data = self.profile, self.data
        pygame.draw.rect(surf, C.bg2, (0, 0, W, 100))
        pygame.draw.line(surf, C.border, (0, 100), (W, 100))
        draw_text(surf, f"SLOT {p.slot}", (40, 18), 12, C.faint, "bold")
        draw_text(surf, p.title, (40, 36), 32, C.text, "bold", max_width=560)
        level, into, need = xp_progress(data, p.xp)
        x = 680
        pill(surf, f"CENTRE LEVEL {level}", (x, 26), C.bg, C.gold, size=14, pad_x=12, pad_y=5)
        bar(surf, (x, 62, 520, 10), (into / need) if need else 1.0, C.gold, C.panel3, radius=5)
        txt = f"{into:.0f} / {need:.0f} XP to level {level + 1}" if need else f"Max level · {p.xp:.0f} XP"
        draw_text(surf, txt, (x + 530, 58), 13, C.dim)
        self.buttons.append(Button((W - 40 - 110, 30, 110, 40), "Title", self.to_title, "ghost", 14))
        self.buttons.append(Button((W - 40 - 110 - 10 - 150, 30, 150, 40), "Change slot", self.to_slots, "ghost", 14))
        self.buttons.append(Button((W - 40 - 270 - 10 - 90, 30, 90, 40), "Help", self.help.toggle, "ghost", 14))

    def _run_panel(self, surf, mouse):
        rect = pygame.Rect(LEFT.x, LEFT.y, LEFT.width, 176)
        panel(surf, rect, C.panel, C.border, radius=12)
        draw_text(surf, "CURRENT RUN", (rect.x + 24, rect.y + 18), 12, C.faint, "bold")
        run = self.profile.run
        if run is None:
            draw_text(surf, "No run in progress. Start one below.", (rect.x + 24, rect.y + 50), 16, C.dim)
            return
        length = next((l["name"] for l in self.data.config["run"]["lengths"] if l["key"] == run.length_key),
                      run.length_key.title())
        draw_text(surf, f"Week {run.week + 1} of {run.weeks_total}", (rect.x + 24, rect.y + 44), 26, C.text, "bold")
        draw_text(surf, f"{length} run · trust {run.rating:.0f} · budget ${run.budget:.1f}k · "
                        f"{len(run.active_ghas())} analysts · {len(run.relics)} tools", (rect.x + 24, rect.y + 82),
                  14, C.dim, max_width=rect.width - 48)
        self.buttons.append(Button((rect.x + 24, rect.bottom - 62, 300, 46), "Continue run  ▶", self.continue_run,
                                   "primary", 16))
        confirm = self.confirm == "abandon"
        self.buttons.append(Button((rect.x + 340, rect.bottom - 62, 190, 46), "Sure? Abandon" if confirm else "Abandon run",
                                   self.abandon_run, "danger" if confirm else "ghost", 14,
                                   tooltip="Throws away this run. It gives no centre XP."))

    def _new_run_panel(self, surf, mouse):
        rect = pygame.Rect(LEFT.x, LEFT.y + 196, LEFT.width, 196)
        panel(surf, rect, C.panel, C.border, radius=12)
        draw_text(surf, "NEW RUN", (rect.x + 24, rect.y + 18), 12, C.faint, "bold")
        level = level_for_xp(self.data, self.profile.xp)
        draw_text(surf, f"A fresh team of analysts. Shop items up to centre level {level}.", (rect.x + 110, rect.y + 17),
                  13, C.faint)
        lengths = self.data.config["run"]["lengths"]
        xp = self.data.config["centre"]["xp"]
        bw = (rect.width - 48 - 20 * (len(lengths) - 1)) // len(lengths)
        for i, spec in enumerate(lengths):
            key = spec["key"]
            win = spec["weeks"] * (xp["per_week"] + xp["win_per_week"])
            confirm = self.confirm == f"new:{key}"
            self.buttons.append(Button((rect.x + 24 + i * (bw + 20), rect.y + 52, bw, 76),
                                       "Click again to confirm" if confirm else spec["name"],
                                       lambda k=key: self.start_run(k), "danger" if confirm else
                                       ("secondary" if self.profile.run else "primary"), 18,
                                       sublabel=f"{spec['weeks']} weeks · {win}+ XP for a win"))
        draw_text(surf, "Centre XP comes from every week you survive, SOP events handled and tasks done, with a big "
                        "bonus for finishing the season.", (rect.x + 24, rect.y + 146), 12, C.faint,
                  max_width=rect.width - 48)

    def _history_panel(self, surf, mouse):
        p = self.profile
        rect = pygame.Rect(LEFT.x, LEFT.y + 412, LEFT.width, LEFT.height - 412)
        panel(surf, rect, C.panel, C.border, radius=12)
        draw_text(surf, "RECENT RUNS", (rect.x + 24, rect.y + 18), 12, C.faint, "bold")
        stats = f"{p.runs} runs · {p.wins} won · best score {p.best_score:,} · {p.total_weeks} weeks survived"
        draw_text(surf, stats, (rect.right - 24, rect.y + 18), 12, C.dim, anchor="topright")
        if not p.history:
            draw_text(surf, "Nothing yet. Your finished runs show up here.", (rect.x + 24, rect.y + 52), 14, C.faint)
            return
        y = rect.y + 50
        cols = [(24, "When"), (190, "Run"), (330, "Result"), (560, "Score"), (680, "Centre XP")]
        for x, label in cols:
            draw_text(surf, label.upper(), (rect.x + x, y), 10, C.faint, "bold")
        y += 22
        for h in reversed(p.history[-12:]):
            if y > rect.bottom - 30:
                break
            row = pygame.Rect(rect.x + 12, y - 4, rect.width - 24, 28)
            if row.collidepoint(mouse):
                pygame.draw.rect(surf, C.panel2, row, border_radius=6)
                TOOLTIP.set([(f"{'Won' if h['won'] else 'Lost'} · seed {h.get('seed', '?')}", C.text, 13, "bold")] +
                            [(f"{label}: +{xp} XP", C.dim, 12) for label, xp in h.get("breakdown", [])], 320)
            draw_text(surf, h["date"], (rect.x + 24, y), 13, C.dim)
            draw_text(surf, f"{h['length'].title()} ({h['weeks_total']} wk)", (rect.x + 190, y), 13, C.text)
            result = "Season complete" if h["won"] else f"Trust collapsed in week {h['weeks'] + 1}"
            draw_text(surf, result, (rect.x + 330, y), 13, C.good if h["won"] else C.bad)
            draw_text(surf, f"{h['score']:,}" if h["won"] else "–", (rect.x + 560, y), 13, C.text)
            lvl = f"  → level {h['new_level']}" if h["new_level"] > h["old_level"] else ""
            draw_text(surf, f"+{h['xp']}{lvl}", (rect.x + 680, y), 13, C.gold)
            y += 30

    def _unlocks(self, surf, mouse):
        data = self.data
        rect = RIGHT
        panel(surf, rect, C.panel, C.border, radius=12)
        draw_text(surf, "UNLOCKS", (rect.x + 24, rect.y + 18), 12, C.faint, "bold")
        level = level_for_xp(data, self.profile.xp)
        counts = [(len(unlocked_ids(data, attr, level)), len(getattr(data, attr)), label)
                  for attr, label in (("relics", "tools"), ("consumables", "supplies"), ("training", "training"))]
        summary = " · ".join(f"{a} of {b} {label}" for a, b, label in counts)
        draw_text(surf, f"In the shop now: {summary}", (rect.x + 110, rect.y + 17), 13, C.dim)
        icons = get_icons()
        table = self.data.config["centre"]["level_xp"]
        track = unlock_track(data)
        y = rect.y + 56
        row_h = min(92, (rect.bottom - 16 - y) // max(1, len(track)))
        for lvl, items in track.items():
            got = lvl <= level
            row = pygame.Rect(rect.x + 14, y, rect.width - 28, row_h - 8)
            fill = mix(C.gold, C.panel, 0.9) if lvl == level + 1 else (C.panel2 if got else (22, 27, 36))
            pygame.draw.rect(surf, fill, row, border_radius=8)
            head_col = C.gold if got else (C.text if lvl == level + 1 else C.faint)
            draw_text(surf, f"LEVEL {lvl}", (row.x + 14, row.y + 12), 14, head_col, "bold")
            need = table[lvl - 1] if lvl - 1 < len(table) else 0
            draw_text(surf, "unlocked" if got else f"{need:,} XP", (row.x + 14, row.y + 34), 11,
                      C.good if got else C.faint)
            if not got:
                lock_icon(surf, (row.x + 104, row.y + 22), 12, C.faint)
            x = row.x + 128
            cell_w = (row.right - x - 8) // max(3, len(items))
            for cat, iid in items:
                cell = pygame.Rect(x, row.y + 6, cell_w - 8, row.height - 12)
                isz = min(44, cell.height - 4)
                if icons is not None:
                    icons.draw(surf, cat, iid, (cell.x, cell.centery), isz, dim=not got, anchor="midleft")
                col = item_colour(data, cat, iid) if got else C.faint
                draw_text(surf, item_name(data, cat, iid), (cell.x + isz + 10, cell.centery - 16), 13, col, "semibold",
                          max_width=cell.width - isz - 14)
                draw_text(surf, {"tools": "tool", "supplies": "supply"}.get(cat, cat), (cell.x + isz + 10, cell.centery + 3),
                          11, C.faint)
                if cell.collidepoint(mouse):
                    lines = item_lines(data, cat, iid)
                    if not got:
                        lines = lines + [(f"Unlocks at centre level {lvl}.", C.warn, 12)]
                    TOOLTIP.set(lines, 300)
                x += cell_w
            y += row_h
