"""Headless UI smoke test: drives the real screens with SDL's dummy video
driver and saves screenshots.

    python tools/ui_smoke.py [output_dir]
"""
from __future__ import annotations

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from game import save  # noqa: E402

# Never touch the player's real save slots.
save.SAVE_DIR = Path(tempfile.mkdtemp(prefix="seismic_shift_test_"))
from ui.app import App  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "screens"


def frame(app, events=(), dt=1 / 60):
    app.frame(dt, list(events))


def shot(app, name):
    os.makedirs(OUT, exist_ok=True)
    frame(app)
    pygame.image.save(app.screen, os.path.join(OUT, f"{name}.png"))
    print("saved", name)


def main():
    app = App(headless=True)
    app.wait_for_catalog()
    shot(app, "01_title")
    app.scene._play()
    shot(app, "01b_slots")
    app.scene.open_slot(1)
    shot(app, "01c_centre")
    app.scene.start_run("short")
    planning = app.scene
    shot(app, "01d_starting_tool")
    if planning.start_pick.pending:
        planning.start_pick.choose(planning.start_pick.options[0])
    shot(app, "02_planning_roster")
    planning.set_tab("shop")
    shot(app, "03_planning_shop")
    planning.set_tab("team")
    shot(app, "04_planning_team")
    planning.set_tab("roster")
    planning.try_start()
    shift = app.scene
    shot(app, "05_shift_start")
    # Unpause and run ~6 game hours at 4x
    shift.toggle_pause()
    shift.speed_i = len(shift.speeds) - 1
    for _ in range(140):
        frame(app, dt=1 / 30)
        if shift.eng.modal or shift.paused:
            break
    shot(app, "06_shift_running")
    # Drag the first inbox card onto desk 1 via the scene's own handlers.
    eng = shift.eng
    frame(app)
    cards = [(r, tid, o) for r, tid, o in shift.card_rects if o is None]
    if cards and shift.desk_rects:
        rect, tid, _ = cards[0]
        desk_rect, gid = next(iter(shift.desk_rects.values()))
        shift._left_down(rect.center)
        shift._motion((rect.centerx + 40, rect.centery + 10))
        shift._motion(desk_rect.center)
        shot(app, "07_dragging")
        shift._left_up(desk_rect.center)
        assert eng.tasks[tid].assignee == gid, "drag and drop failed"
        print("drag-drop ok")
    # Keep playing with a simple auto-assign so the screens fill up.
    from game.bot import Bot
    bot = Bot(app.data, attention=10)
    shots = {"08_shift_busy": False, "09_sop": False, "10_event_modal": False, "11_staffing_modal": False}
    for step in range(30000):
        if shift.eng.modal:
            kind = shift.eng.modal["type"]
            key = "10_event_modal" if kind == "event" else "11_staffing_modal"
            if not shots[key]:
                shot(app, key)
                shots[key] = True
            bot.decide(shift.eng)
        if shift.paused:
            if shift.banner and shift.banner[0].startswith("SOP") and not shots["09_sop"]:
                shot(app, "09_sop")
                shots["09_sop"] = True
            shift.toggle_pause()
        bot.act(shift.eng)
        frame(app, dt=1 / 30)
        if step == 400 and not shots["08_shift_busy"]:
            shot(app, "08_shift_busy")
            shots["08_shift_busy"] = True
        if app.scene is not shift:
            break
    shot(app, "12_after_week")
    print("scene:", type(app.scene).__name__)
    if type(app.scene).__name__ == "SummaryScene":
        app.scene.next()
        shot(app, "13_next_planning")
    # The week-2 planning state was saved to slot 1.
    profile = save.load_profile(1)
    assert profile is not None and profile.run is not None and profile.run.week == 1, "slot 1 should hold week 2"
    print("save slot ok")


if __name__ == "__main__":
    main()
