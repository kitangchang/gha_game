"""Forces specific situations on every screen and saves screenshots.

    python tools/ui_scenarios.py [output_dir]
"""
from __future__ import annotations

import os
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from game import save  # noqa: E402

# Never touch the player's real save slots.
save.SAVE_DIR = Path(tempfile.mkdtemp(prefix="seismic_shift_test_"))
from game.bot import Bot  # noqa: E402
from game.profile import new_profile  # noqa: E402
from game.run import new_run  # noqa: E402
from ui.app import App  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "screens"


def frame(app, dt=1 / 60):
    app.frame(dt, [])


def shot(app, name):
    os.makedirs(OUT, exist_ok=True)
    frame(app, 0.0)
    pygame.image.save(app.screen, os.path.join(OUT, f"{name}.png"))
    print("saved", name)


def main():
    app = App(headless=True)
    app.wait_for_catalog()
    profile = new_profile(1)
    profile.xp = 820          # level 4, to show some unlocks
    app.profile = profile
    run = new_run(app.data, app.catalog, seed=4242, length_key="short", unlock_level=4)
    profile.run = run
    save.save_profile(profile)
    from ui.scenes.planning import PlanningScene
    app.change(PlanningScene(app, run))
    frame(app)
    app.scene.try_start()
    scene = app.scene
    eng = scene.eng
    scene.toggle_pause()
    bot = Bot(app.data, attention=30, horizon=400)
    # Play ~10 game hours with long queues.
    while eng.now < 600 and not eng.blocked:
        if scene.paused:
            scene.toggle_pause()
        bot.act(eng)
        frame(app, 1 / 30)
    if eng.modal:
        bot.decide(eng)
    scene.paused = True
    scene.banner = None
    shot(app, "s1_queues")

    # Frame timing at a busy moment.
    t0 = time.perf_counter()
    for _ in range(120):
        frame(app, 1 / 60)
    print(f"avg frame {1000 * (time.perf_counter() - t0) / 120:.1f} ms")

    # Sick call -> staffing modal with the roster.
    nxt = eng.slot + 1
    lineup = eng.lineup(nxt)
    eng._sick_call(nxt, lineup[0])
    task = next(t for t in eng.tasks.values() if t.kind == "staffing" and not t.done)
    g = eng.ghas[eng.on_shift[0]]
    eng.assign(task.id, g.id, 0)
    task.progress = task.work - 0.001
    g.arrive_at = 0
    g.away_until = 0
    scene.paused = False
    for _ in range(30):
        frame(app, 1 / 60)
        if eng.modal:
            break
    cands = [p for p in eng.staffing_options() if not p.on_shift]
    if scene.modal_buttons:
        pygame.mouse.set_pos(scene.modal_buttons[0].rect.center)
    shot(app, "s2_staffing_roster")
    pygame.mouse.set_pos((5, 5))
    scene.choose_cover(cands[0].id if cands else None)
    scene.paused = True

    scene.open_callin()
    shot(app, "s3_callin")
    scene.close_callin()
    scene.menu = True
    shot(app, "s4_menu")
    scene.menu = False
    scene.help.visible = True
    shot(app, "s5_help")
    scene.help.visible = False

    # Auto-assign: open the mode menu, then switch it on.
    scene.toggle_auto_menu()
    shot(app, "s5b_auto_menu")
    scene.set_auto_mode("fastest")
    scene.toggle_auto()
    frame(app)

    run.consumables.append("energy_drink")
    run.relics += ["coffee_machine", "rubber_duck", "tsunami_db", "picker_upgrade", "espresso"]
    eng.refresh_mods()
    frame(app)
    scene.use_item(len(run.consumables) - 1)
    shot(app, "s6_targeting")
    rect, gid = next(iter(scene.desk_rects.values()))
    scene._apply_target((rect.x + 20, rect.y + 20))
    frame(app)

    # Big local event -> SOP, then its DART trigger adds 'Assess DART signals'.
    eng._spawn_event((0, 6.6, -38.9, 178.9, 12.0, "60 km east of Gisborne", "test2026p000001",
                      "2026-10-10T08:12:33.123Z"))
    for _ in range(3):
        frame(app)
    shot(app, "s7_sop_local")
    for _ in range(400):
        if scene.paused:
            scene.toggle_pause()
        if eng.modal:
            bot.decide(eng)
        frame(app, 1 / 60)
    scene.paused = True
    scene.banner = None
    shot(app, "s8_sop_dart_auto")

    # A quake near Tonga (below the distant-tsunami threshold) with no SOP running -> DART Trigger SOP.
    for t in list(eng.tasks.values()):
        if not t.done and t.kind in ("sop", "eq"):
            eng.complete_external(t)
    eng._spawn_event((0, 7.0, -21.0, -174.0, 30.0, "Tonga Islands", "test2026p000002", ""))
    scene.paused = False
    for _ in range(200):
        frame(app, 1 / 60)
        if eng.modal:
            bot.decide(eng)
        if scene.paused:
            break
    scene.banner = None
    for b in app.data.dart_buoys:
        if eng.dart_active(b["code"]):
            from ui.scenes.shift_draw import DART_RECT
            pygame.mouse.set_pos((DART_RECT.centerx, DART_RECT.centery))
            break
    shot(app, "s8b_dart_sop")
    pygame.mouse.set_pos((5, 5))

    # Game over (awards centre XP).
    scene.paused = False
    run.rating = 0.5
    eng.change_rating(-1.0)
    for _ in range(200):
        frame(app, 1 / 30)
        if type(app.scene).__name__ != "ShiftScene":
            break
    shot(app, "s9_game_over")

    # Victory screen with a level-up.
    from ui.scenes.summary import VictoryScene
    run2 = new_run(app.data, app.catalog, seed=7, length_key="short", unlock_level=4)
    run2.week = run2.weeks_total
    run2.phase = "won"
    run2.rating = 81.0
    run2.totals.update({"tasks": 2310, "eq": 1650, "errors": 41, "ontime": 2201, "sops": 6})
    app.profile.run = run2
    app.change(VictoryScene(app, run2))
    shot(app, "s10_victory")
    app.scene.back()
    shot(app, "s10b_centre_after_runs")

    # Planning with people on leave, a custom grid and a hover tooltip on a team strip.
    run3 = new_run(app.data, app.catalog, seed=99, length_key="short")
    tired = sorted(run3.active_ghas(), key=lambda g: -g.ltf)[:2]
    for g in tired:
        g.ltf = 88.0
    run3.roster.move(tired[0].id, "leave")
    run3.roster.grid["blue"][3] = True
    run3.roster.custom = True
    run3.relics += ["office_dog", "dart_dashboard", "second_monitors"]
    planning = PlanningScene(app, run3)
    app.change(planning)
    box = planning.tabs["roster"].group_rects["red"]
    pygame.mouse.set_pos((box.x + 60, box.y + 60))
    shot(app, "s11_roster_leave")
    pygame.mouse.set_pos((box.x + 220, box.y + 20))
    shot(app, "s11a_roster_team_tooltip")
    planning.set_tab("shop")
    pygame.mouse.set_pos((5, 5))
    shot(app, "s11b_shop_with_tools")

    # Week summary with level-ups, leave and a burnout in the notes.
    from game.run import finish_week, start_week
    from ui.scenes.summary import SummaryScene
    run4 = new_run(app.data, app.catalog, seed=11, length_key="short")
    eng4 = start_week(app.data, run4)
    bot4 = Bot(app.data, attention=10)
    while not eng4.week_done and not eng4.game_over:
        if eng4.modal:
            bot4.decide(eng4)
        bot4.act(eng4)
        eng4.update(30.0)
    s = finish_week(app.data, run4, eng4)
    s["level_ups"] = s["level_ups"][:2] or ["Aroha Ngata: Seismic 4", "Ben Carter: Tsunami 3"]
    s["leave"] = ["Mere Walker: long-term fatigue 74 → 14"]
    s["burnouts"] = ["Sam Patel"]
    app.change(SummaryScene(app, run4, s))
    shot(app, "s12_summary_notes")

    # Slots with a used centre.
    from ui.scenes.slots import SlotScene
    app.change(SlotScene(app))
    shot(app, "s13_slots")

    # Avatar gallery (art preview), with the tired overlay on.
    from ui.scenes.gallery import GalleryScene
    gallery = GalleryScene(app)
    app.change(gallery)
    gallery.focus = 3
    shot(app, "s14_gallery")
    gallery.toggle_tired()
    app.reload_art()
    shot(app, "s15_gallery_tired_reloaded")


if __name__ == "__main__":
    main()
