"""NZ map screen on the ops room wall: recent events, a Kermadec inset and any
DART buoys that are in event mode."""
from __future__ import annotations

import math

import pygame

from game.geo import short_place

from ..theme import C, depth_color, render
from ..widgets import alpha_circle, draw_text
from .wall import DART_ALERT, screen_frame, screen_glare

MAIN = {"lat": (-47.6, -34.1), "lon": (165.5, 184.3)}
INSET = {"lat": (-33.4, -28.6), "lon": (180.6, 184.4)}
KX = math.cos(math.radians(41.0))
OCEAN = (12, 22, 34)
LAND = (44, 58, 52)
LAND_EDGE = (86, 108, 94)


class MapPanel:
    def __init__(self, data, rect):
        self.data = data
        self.rect = pygame.Rect(rect)
        self.map_rect = pygame.Rect(self.rect.x + 3, self.rect.y + 3, self.rect.width - 6, self.rect.height - 21)
        self.strip = pygame.Rect(self.rect.x + 6, self.map_rect.bottom + 2, self.rect.width - 12, 14)
        w_deg = (MAIN["lon"][1] - MAIN["lon"][0]) * KX
        h_deg = MAIN["lat"][1] - MAIN["lat"][0]
        self.scale = min(self.map_rect.width / w_deg, self.map_rect.height / h_deg)
        self.ox = self.map_rect.x + (self.map_rect.width - w_deg * self.scale) / 2
        self.oy = self.map_rect.y + (self.map_rect.height - h_deg * self.scale) / 2
        iw_px = max(64, int(self.map_rect.width * 0.26))
        self.inset = pygame.Rect(self.map_rect.right - iw_px - 3, self.map_rect.y + 3, iw_px, int(iw_px * 1.15))
        iw = (INSET["lon"][1] - INSET["lon"][0]) * KX
        ih = INSET["lat"][1] - INSET["lat"][0]
        self.iscale = min((self.inset.width - 8) / iw, (self.inset.height - 18) / ih)
        self.background = self._render_background()

    def project(self, lat: float, lon: float):
        lon = lon % 360.0
        if INSET["lat"][0] <= lat <= INSET["lat"][1] + 0.4 and INSET["lon"][0] - 0.5 <= lon <= INSET["lon"][1] + 0.5:
            x = self.inset.x + 4 + (lon - INSET["lon"][0]) * KX * self.iscale
            y = self.inset.y + 14 + (INSET["lat"][1] - lat) * self.iscale
            return x, y, True
        if not (MAIN["lat"][0] - 0.5 <= lat <= MAIN["lat"][1] + 0.6 and MAIN["lon"][0] - 0.5 <= lon <= MAIN["lon"][1] + 0.5):
            return None
        x = self.ox + (lon - MAIN["lon"][0]) * KX * self.scale
        y = self.oy + (MAIN["lat"][1] - lat) * self.scale
        return x, y, False

    def _render_background(self) -> pygame.Surface:
        pad = 6
        surf = pygame.Surface((self.rect.width + 2 * pad, self.rect.height + 2 * pad), pygame.SRCALPHA)
        origin = (self.rect.x - pad, self.rect.y - pad)
        local = self.rect.move(-origin[0], -origin[1])
        screen_frame(surf, local)
        mr = self.map_rect.move(-origin[0], -origin[1])
        pygame.draw.rect(surf, OCEAN, mr, border_radius=3)
        for lat in range(-46, -33, 2):
            p1 = self._proj_local(lat, MAIN["lon"][0], origin)
            p2 = self._proj_local(lat, MAIN["lon"][1], origin)
            pygame.draw.line(surf, (20, 32, 46), p1, p2)
        for poly in self.data.coast["polygons"]:
            pts = [self._proj_local(p[0], p[1], origin) for p in poly["points"]]
            if len(pts) >= 3:
                pygame.draw.polygon(surf, LAND, pts)
                pygame.draw.aalines(surf, LAND_EDGE, True, pts)
        ir = self.inset.move(-origin[0], -origin[1])
        pygame.draw.rect(surf, (10, 18, 28), ir, border_radius=3)
        pygame.draw.rect(surf, (52, 64, 80), ir, 1, border_radius=3)
        surf.blit(render("KERMADEC", 8, C.faint, "bold"), (ir.x + 4, ir.y + 3))
        for pt in self.data.coast["points"]:
            res = self.project(pt["lat"], pt["lon"])
            if res:
                pygame.draw.circle(surf, LAND_EDGE, (int(res[0] - origin[0]), int(res[1] - origin[1])), 2)
        self._bg_origin = origin
        return surf

    def _proj_local(self, lat, lon, origin):
        x = self.ox + (lon - MAIN["lon"][0]) * KX * self.scale - origin[0]
        y = self.oy + (MAIN["lat"][1] - lat) * self.scale - origin[1]
        return (x, y)

    def draw(self, surf, eng, ripples: list, t: float, highlight=None):
        surf.blit(self.background, self._bg_origin)
        window = 1440.0
        recent = [ev for ev in eng.events.values() if eng.now - ev.t <= window or ev.sops and eng.now - ev.t <= 3 * window]
        recent.sort(key=lambda e: e.mag)
        distant = []
        clip = surf.get_clip()
        surf.set_clip(self.map_rect)
        for b in self.data.dart_buoys:          # only buoys in event mode are marked
            if not eng.dart_active(b["code"]):
                continue
            res = self.project(b["lat"], b["lon"])
            if res is None:
                continue
            x, y = res[:2]
            pygame.draw.polygon(surf, DART_ALERT, [(x, y - 4), (x + 3.5, y + 3), (x - 3.5, y + 3)])
            if int(t * 2) % 2 == 0:
                pygame.draw.circle(surf, DART_ALERT, (int(x), int(y)), 8, 1)
        for ev in recent:
            res = self.project(ev.lat, ev.lon)
            if res is None:
                if ev.region == "elsewhere" or ev.region == "kermadec":
                    distant.append(ev)
                continue
            x, y, _ = res
            age = (eng.now - ev.t) / window
            alpha = int(255 * max(0.18, 1.0 - age * 0.85))
            m = ev.display_mag()
            r = int(2 + max(0.0, m - 1.0) ** 1.5)
            alpha_circle(surf, depth_color(ev.depth) + (alpha,), (x, y), r)
            alpha_circle(surf, (0, 0, 0, min(140, alpha)), (x, y), r, 1)
            if ev.sops:
                alpha_circle(surf, C.sop + (220,), (x, y), r + 4, 2)
        for uid, start in ripples:
            ev = eng.events.get(uid)
            if ev is None:
                continue
            res = self.project(ev.lat, ev.lon)
            if res is None:
                continue
            k = (t - start) / 1.4
            if 0 <= k <= 1:
                rad = int(4 + k * (10 + ev.mag * 5))
                alpha_circle(surf, (255, 255, 255, int(200 * (1 - k))), res[:2], rad, 2)
        if highlight is not None:
            res = self.project(highlight.lat, highlight.lon)
            if res:
                x, y = res[:2]
                pygame.draw.circle(surf, C.white, (int(x), int(y)), 11, 2)
                pygame.draw.line(surf, C.white, (x - 17, y), (x - 7, y), 2)
                pygame.draw.line(surf, C.white, (x + 7, y), (x + 17, y), 2)
        surf.set_clip(clip)
        draw_text(surf, "OFF MAP", (self.strip.x, self.strip.y + 3), 8, C.faint, "bold")
        if distant:
            distant.sort(key=lambda e: -e.t)
            text = "  ·  ".join(f"{ev.mag_label()} {short_place(ev.description, 20)}" for ev in distant[:3])
            draw_text(surf, text, (self.strip.x + 44, self.strip.y + 1), 10, C.dim, max_width=self.strip.width - 44)
        else:
            draw_text(surf, "nothing in the last day", (self.strip.x + 44, self.strip.y + 1), 10, C.faint)
        screen_glare(surf, self.rect)
