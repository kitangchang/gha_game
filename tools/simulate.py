"""Headless balancing: plays whole runs with the bot and prints a weekly table.

    python tools/simulate.py                 # 3 standard runs
    python tools/simulate.py --runs 10 --length long --attention 10
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.bot import Bot  # noqa: E402
from game.catalog import load_catalog  # noqa: E402
from game.data import get_data  # noqa: E402
from game.run import finish_week, new_run, start_week  # noqa: E402


def play_run(data, catalog, seed, length, bot_kwargs, verbose=True, auto=None):
    run = new_run(data, catalog, seed=seed, length_key=length)
    bot = Bot(data, **bot_kwargs)
    rows = []
    if auto:
        run.flags["auto_assign"] = {"on": True, "mode": auto}
    while run.phase not in ("won", "over"):
        bot.shop(run)
        bot.plan_week(run)
        eng = start_week(data, run)
        bot.busy_samples = bot.present_samples = 0
        while not eng.week_done and not eng.game_over:
            if auto:
                if eng.modal:
                    bot.decide(eng)
            else:
                bot.act(eng)
            eng.update(1.0 if not eng.modal else 0.0)
            bot.notify(eng, eng.drain_notes())
        fat = [g.fatigue for g in run.active_ghas()]
        ltf = [g.ltf for g in run.active_ghas()]
        util = bot.busy_samples / max(1, bot.present_samples)
        if eng.game_over:
            run.phase = "over"
            rows.append((run.week + 1, run.rating, run.budget, eng.stats, util, fat, ltf, None))
            break
        summary = finish_week(data, run, eng)
        rows.append((summary["week"], run.rating, run.budget, eng.stats, util, fat, ltf, summary))
    if verbose:
        print(f"\nseed {seed} · {length} · {catalog.label}")
        print(" wk  trust  budget  events  sop  done  ontime%  err  overdue  unmanned  sick  burn  util  fat  ltfmax  team  payout   +gain  -err  -late  -oth")
        for wk, rating, budget, st, util, fat, ltf, summ in rows:
            ontime = 100.0 * st["ontime"] / max(1, st["tasks_done"])
            payout = f"{summ['payout']:.1f}" if summ else "-"
            print(f" {wk:>2}  {rating:5.1f}  {budget:6.1f}  {st['events']:>6}  {st['sop_events']:>3}  {st['tasks_done']:>4}"
                  f"  {ontime:6.1f}  {st['errors']:>3}  {st['overdue']:>7}  {st['unmanned_shifts']:>8}  {st['sick_calls']:>4}"
                  f"  {len(st['burnouts']):>4}  {util:4.2f}  {statistics.mean(fat) if fat else 0:4.0f}  {max(ltf) if ltf else 0:6.0f}"
                  f"  {len(fat):>4}  {payout:>6}  {st['gained']:6.1f} {st['lost_errors']:5.1f} {st['lost_overdue']:5.1f} {st['lost_other']:5.1f}")
        print(" result:", run.phase.upper(), f"trust {run.rating:.1f}")
    return run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--length", default="standard")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--attention", type=float, default=3.0)
    ap.add_argument("--horizon", type=float, default=150.0)
    ap.add_argument("--no-leave", action="store_true")
    ap.add_argument("--no-shop", action="store_true")
    ap.add_argument("--no-triage", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--per-look", type=int, default=999)
    ap.add_argument("--auto", default=None, help="let the game's auto-assign play (balanced, fastest, safest, "
                                                  "freshest, shortest) instead of the bot")
    args = ap.parse_args()
    data = get_data()
    catalog = load_catalog(data)
    kwargs = dict(attention=args.attention, horizon=args.horizon, use_leave=not args.no_leave,
                  use_shop=not args.no_shop, triage=not args.no_triage, max_per_look=args.per_look)
    results = []
    t0 = time.time()
    for i in range(args.runs):
        run = play_run(data, catalog, args.seed + i, args.length, kwargs, verbose=not args.quiet, auto=args.auto)
        results.append((run.phase, run.rating, run.week))
    wins = sum(1 for r in results if r[0] == "won")
    print(f"\n{wins}/{len(results)} runs survived · mean final trust {statistics.mean(r[1] for r in results):.1f}"
          f" · {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
