"""Run lifecycle: new run, analysts, roster defaults, week start/finish."""
from __future__ import annotations

import random

from .avatars import random_avatar
from .engine import WeekEngine
from .models import GHA, Roster, RunState
from .modifiers import Ctx, ModifierSet, collect_specials
from .tags import count_tags
from .run_builder import build_plan
from .util import DAY_NAMES, clamp, fmt_money, weighted_choice

ARCHETYPES = {
    "graduate":    {"label": "Graduate",    "base": (1, 2), "focus": 1, "focus_lvl": (2, 3), "traits": (0, 1), "good": 0.75, "ltf": (0, 8)},
    "experienced": {"label": "Experienced", "base": (2, 3), "focus": 1, "focus_lvl": (3, 4), "traits": (1, 2), "good": 0.6,  "ltf": (8, 30)},
    "specialist":  {"label": "Specialist",  "base": (1, 2), "focus": 1, "focus_lvl": (5, 5), "traits": (1, 1), "good": 0.6,  "ltf": (5, 25)},
    "generalist":  {"label": "Generalist",  "base": (2, 3), "focus": 2, "focus_lvl": (3, 3), "traits": (1, 1), "good": 0.6,  "ltf": (5, 25)},
    "veteran":     {"label": "Veteran",     "base": (3, 4), "focus": 2, "focus_lvl": (4, 5), "traits": (1, 2), "good": 0.45, "ltf": (30, 55)},
}
HIRE_WEIGHTS = {"graduate": 0.28, "experienced": 0.34, "specialist": 0.22, "generalist": 0.08, "veteran": 0.08}
START_TEAM = [("specialist", "seismic"), ("specialist", "tsunami"), ("experienced", "seismic"),
              ("experienced", "seismic"), ("experienced", "comms"), ("experienced", "volcano"),
              ("generalist", None), ("generalist", None), ("graduate", "seismic"), ("graduate", None),
              ("experienced", "systems"), ("graduate", "landslide")]


def salary_for(data, skills: dict, traits: list) -> float:
    econ = data.config["economy"]
    s = econ["salary_base"] + econ["salary_per_skill_point"] * sum(skills.values())
    per_kind = {"good": econ["salary_good_trait"], "bad": econ["salary_bad_trait"],
                "balanced": econ.get("salary_balanced_trait", 0.0)}
    for tid in traits:
        s += per_kind.get(data.traits[tid]["kind"], 0.0)
    return round(max(1.0, s), 1)


def _unique_name(data, rng, taken: set, gender: str = "") -> str:
    firsts = data.first_names_for(gender)
    for _ in range(200):
        name = f"{rng.choice(firsts)} {rng.choice(data.last_names)}"
        first = name.split(" ")[0]
        if name not in taken and first not in {t.split(' ')[0] for t in taken}:
            return name
    return f"{rng.choice(firsts)} {rng.choice(data.last_names)}"


def _pick_traits(data, rng, n: int, good_bias: float) -> list:
    """good_bias = chance of a good trait; the rest is split evenly between balanced and bad."""
    chosen: list = []
    for _ in range(n):
        roll = rng.random()
        kind = "good" if roll < good_bias else ("balanced" if roll < good_bias + (1 - good_bias) / 2 else "bad")
        pool = [t for t in data.traits.values() if t["kind"] == kind and t["id"] not in chosen]
        if not pool:
            continue
        weights = [t.get("weight", 1) for t in pool]
        pick = rng.random() * sum(weights)
        acc = 0.0
        for t, w in zip(pool, weights):
            acc += w
            if pick <= acc:
                chosen.append(t["id"])
                break
    return chosen


def make_gha(data, rng: random.Random, run: RunState | None, archetype: str, focus: str | None = None,
             taken: set | None = None, week: int = 0) -> GHA:
    a = ARCHETYPES[archetype]
    sm = data.config["skill_model"]
    skills = {k: rng.randint(*a["base"]) for k in data.skill_keys}
    focus_keys = [focus] if focus else []
    others = [k for k in data.skill_keys if k not in focus_keys]
    rng.shuffle(others)
    while len(focus_keys) < a["focus"]:
        focus_keys.append(others.pop())
    for k in focus_keys:
        skills[k] = rng.randint(*a["focus_lvl"])
    if archetype != "graduate":
        skills["seismic"] = max(2, skills["seismic"])
    skills = {k: int(clamp(v, sm["min_level"], sm["max_level"])) for k, v in skills.items()}
    traits = _pick_traits(data, rng, rng.randint(*a["traits"]), a["good"])
    if archetype == "graduate" and "quick_learner" not in traits and rng.random() < 0.5:
        traits.append("quick_learner")
    if archetype == "veteran" and rng.random() < 0.4 and "burnout_risk" not in traits:
        traits.append("burnout_risk")
    taken = taken if taken is not None else set()
    gender = rng.choice("fm")
    name = _unique_name(data, rng, taken, gender)
    taken.add(name)
    fat = data.config["fatigue"]
    g = GHA(id=run.new_id("gha") if run else -1, name=name, color=rng.choice(data.avatar_colors),
            skills=skills, traits=traits, salary=salary_for(data, skills, traits),
            fatigue=rng.uniform(fat["start_min"], fat["start_max"]), ltf=float(rng.randint(*a["ltf"])),
            xp={k: 0.0 for k in data.skill_keys}, hired_week=week, gender=gender)
    g.stats["archetype"] = a["label"]
    g.avatar = random_avatar(rng, gender)
    return g


def rotation_grid(data, week: int) -> dict:
    """Team x slot grid for a week, following the rotation in config.json/roster.
    The cycle continues across weeks (it's based on the absolute day of the run)."""
    n_shifts = data.slots_per_day
    grid = {t: [False] * data.slots_per_week for t in data.team_keys}
    for k, team in enumerate(data.team_keys):
        for d in range(7):
            shift = data.rotation_shift(k, week * 7 + d)
            if shift != "off":
                grid[team][d * n_shifts + data.shift_index(shift)] = True
    return grid


def team_shifts(data, grid: dict, team: str) -> list:
    """Per day of the week, the shift initials a team works (e.g. ['M', 'M', 'L', '', ...])."""
    n_shifts = data.slots_per_day
    cells = grid.get(team, [])
    out = []
    for d in range(7):
        codes = [data.shifts[s]["name"][0] for s in range(n_shifts)
                 if d * n_shifts + s < len(cells) and cells[d * n_shifts + s]]
        out.append("".join(codes))
    return out


def strength(g) -> float:
    return g.skills.get("seismic", 1) * 2 + g.skills.get("tsunami", 1) + g.skills.get("comms", 1) * 0.5


def snake_draft(teams: list, ghas: list) -> dict:
    out = {t: [] for t in teams}
    ordered = sorted(ghas, key=lambda g: -strength(g))
    for i, g in enumerate(ordered):
        lap, pos = divmod(i, len(teams))
        out[teams[pos if lap % 2 == 0 else len(teams) - 1 - pos]].append(g.id)
    return out


def default_roster(data, ghas: list) -> Roster:
    teams = data.team_keys
    per_team = max(1, len(ghas) // len(teams))
    core = sorted(ghas, key=lambda g: -strength(g))[: per_team * len(teams)]
    return Roster(teams=snake_draft(teams, core), leave=[], grid=rotation_grid(data, 0))


def new_run(data, catalog, seed: int | None = None, length_key: str = "standard", unlock_level: int = 99) -> RunState:
    if seed is None:
        seed = random.randrange(1, 10**9)
    rng = random.Random(seed)
    lengths = {l["key"]: l["weeks"] for l in data.config["run"]["lengths"]}
    weeks = lengths.get(length_key, 8)
    plan = build_plan(data, catalog, random.Random(seed * 7919 + 17), weeks)
    run = RunState(seed=seed, length_key=length_key, weeks_total=weeks, plan=plan, ghas=[], roster=None,
                   rng=rng, catalog_label=catalog.label, rating=float(data.config["run"]["start_rating"]),
                   budget=float(data.config["run"]["start_budget"]), unlock_level=unlock_level)
    taken: set = set()
    for arche, focus in START_TEAM[: data.config["run"]["start_team_size"]]:
        run.ghas.append(make_gha(data, rng, run, arche, focus, taken))
    run.roster = default_roster(data, run.ghas)
    prepare_week(data, run)
    options = start_reward_options(data, run)
    if options:
        run.flags["start_reward"] = options
    return run


def run_mods(data, run: RunState) -> ModifierSet:
    mods = ModifierSet(data)
    special = run.plan[run.week].special if run.week < len(run.plan) else None
    mods.rebuild(run.relics, special, count_tags(data, run))
    return mods


def desk_count(data, run: RunState) -> int:
    spec = collect_specials(data, run.relics)
    return min(data.config["run"]["max_desks"], data.config["run"]["desks"] + int(spec.get("extra_desks", 0)))


def consumable_slots(data, run: RunState) -> int:
    spec = collect_specials(data, run.relics)
    return data.config["run"]["max_consumables"] + int(spec.get("consumable_slots", 0))


def prepare_week(data, run: RunState):
    """Called when the planning phase for run.week begins."""
    from .shop import generate_shop
    if run.week >= len(run.plan):
        return
    run.phase = "planning"
    week = run.plan[run.week]
    run.away_week = []
    special = data.special_weeks.get(week.special) if week.special else None
    if special and special.get("away_count"):
        pool = [g for g in run.active_ghas()]
        run.rng.shuffle(pool)
        run.away_week = [g.id for g in pool[: special["away_count"]]]
    run.roster.grid = rotation_grid(data, run.week)
    run.roster.custom = False
    for key in data.team_keys:
        run.roster.teams.setdefault(key, [])
    if not run.shop or run.shop.get("week") != run.week:
        run.shop = generate_shop(data, run)


def start_week(data, run: RunState) -> WeekEngine:
    run.phase = "shift"
    return WeekEngine(data, run)


def weekly_salaries(run: RunState) -> float:
    return round(sum(g.salary for g in run.active_ghas()), 1)


def finish_week(data, run: RunState, eng: WeekEngine) -> dict:
    econ = data.config["economy"]
    st = eng.stats
    perf = st["imp_ontime"] / st["imp_due"] if st["imp_due"] > 0 else 1.0
    err_frac = st["errors"] / max(1, st["tasks_done"])
    perf_adj = clamp(perf - 1.5 * err_frac, 0.0, 1.0)
    special = eng.special
    payout_mult = eng.mods.mult("payout", Ctx()) * (special.get("payout_mult", 1.0) if special else 1.0)
    base = econ["base_grant"]
    bonus = econ["performance_bonus_max"] * perf_adj
    trust_bonus = econ["trust_bonus_max"] * max(0.0, run.rating) / 100.0
    weekly_bonus = max(0.0, eng.mods.add("weekly_bonus", Ctx()))
    payout = (base + bonus + trust_bonus) * payout_mult + weekly_bonus
    salaries = weekly_salaries(run)
    if special and special.get("end_rating"):
        run.rating = min(float(data.config["run"]["max_rating"]), run.rating + special["end_rating"])

    leave_notes = []
    lt = data.config["long_term"]
    floor = data.config["fatigue"]["floor_from_ltf"]
    returning = run.roster.return_team
    for gid in list(run.roster.leave):
        g = run.gha(gid)
        if g is None or not g.active:
            continue
        if gid in eng.leave_cancelled:
            leave_notes.append(f"{g.name}: leave cancelled (called in)")
            continue
        before = g.ltf
        g.ltf = max(0.0, g.ltf - lt["leave_recovery"])
        g.fatigue = g.ltf * floor
        g.ltf_warned = g.ltf >= lt["warn_level"]
        leave_notes.append(f"{g.name}: long-term fatigue {before:.0f} → {g.ltf:.0f}")
        back = returning.pop(gid, None)
        run.roster.move(gid, back if back in run.roster.teams else "bench")

    run.budget += payout - salaries
    summary = {
        "week": run.week + 1,
        "rating_start": st["rating_start"], "rating_end": run.rating,
        "tasks_done": st["tasks_done"], "ontime": st["ontime"], "late": st["late"], "errors": st["errors"],
        "caught": st["caught"], "events": st["events"], "sop_events": st["sop_events"], "overdue": st["overdue"],
        "perf": perf, "perf_adj": perf_adj, "base": base, "bonus": bonus, "trust_bonus": trust_bonus,
        "payout_mult": payout_mult, "weekly_bonus": weekly_bonus, "payout": payout, "salaries": salaries, "overtime": eng.overtime_cost,
        "net": payout - salaries, "budget_end": run.budget, "leave": leave_notes,
        "burnouts": list(st["burnouts"]), "level_ups": list(st["level_ups"]), "sick_calls": st["sick_calls"],
        "covers": st["covers"], "call_ins": st["call_ins"], "unmanned": st["unmanned_shifts"],
        "biggest": st["biggest"], "lost_errors": st["lost_errors"], "lost_overdue": st["lost_overdue"],
        "lost_other": st["lost_other"], "gained": st["gained"], "auto_reviewed": st["auto_reviewed"],
        "carried": len(run.carry_tasks), "special": eng.plan.special,
        "dart_triggers": st.get("dart_triggers", 0),
    }
    run.history.append(summary)
    run.totals["tasks"] += st["tasks_done"]
    run.totals["eq"] += st["eq_done"]
    run.totals["errors"] += st["errors"]
    run.totals["ontime"] += st["ontime"]
    run.totals["sops"] += st["sop_events"]
    run.ghas = [g for g in run.ghas if not g.temp]
    for g in run.ghas:
        if not g.active:
            run.roster.remove(g.id)
    boss_day = any(d.boss for d in eng.plan.days)
    run.week += 1
    if run.week >= run.weeks_total:
        run.phase = "won"
    else:
        prepare_week(data, run)
        if boss_day:
            options = boss_reward_options(data, run)
            if options:
                run.flags["boss_reward"] = options
                summary["boss_reward"] = options
    return summary


def reward_options(data, run: RunState, weights: dict, count: int) -> list:
    """Tools to choose from (unlocked, not owned, not in this week's shop), drawn
    by rarity weights. Used for boss-day rewards and the starting tool."""
    level = getattr(run, "unlock_level", 99)
    in_shop = {o["id"] for o in (run.shop or {}).get("relics", [])}
    # "repeatable" tools can be owned more than once; "reward_weight" makes a tool rarer (<1) or commoner (>1)
    pool = [r for r in data.relics.values() if (r.get("repeatable") or r["id"] not in run.relics)
            and r["id"] not in in_shop and r["rarity"] in weights and weights[r["rarity"]] > 0
            and int(r.get("unlock_level", 1)) <= level]
    picks = []
    for _ in range(int(count)):
        if not pool:
            break
        r = weighted_choice(run.rng, pool, [weights[p["rarity"]] * float(p.get("reward_weight", 1.0)) for p in pool])
        pool.remove(r)
        picks.append(r["id"])
    return picks


def boss_reward_options(data, run: RunState) -> list:
    """Tools offered for surviving a week's boss day: boss-only tools plus rare and
    legendary ones."""
    diff = data.config["difficulty"]
    return reward_options(data, run, diff.get("boss_reward_weights", {"boss": 55, "rare": 35, "legendary": 10}),
                          diff.get("boss_reward_choices", 3))


def start_reward_options(data, run: RunState) -> list:
    """The starting tool to choose from at the beginning of a run."""
    st = data.config["run"].get("starting_tool", {})
    if not st.get("enabled", True):
        return []
    return reward_options(data, run, st.get("weights", {"boss": 60, "rare": 25, "uncommon": 15}),
                          st.get("choices", 3))


def claim_boss_reward(data, run: RunState, rid: str | None, flag: str = "boss_reward") -> str:
    """Take one of the offered tools (or None to skip). Returns a message.
    flag: which offer this is (boss_reward or start_reward)."""
    options = run.flags.pop(flag, None) or []
    if rid is None or rid not in options or (rid in run.relics and not data.relics[rid].get("repeatable")):
        return "Reward skipped."
    run.relics.append(rid)
    extra = gain_effects(data, run, rid)
    from .shop import refresh_after_new_tool
    refresh_after_new_tool(data, run)
    return f"New tool: {data.relics[rid]['name']}" + (f" ({extra})" if extra else "")


def gain_effects(data, run: RunState, rid: str) -> str:
    """A tool's one-off "on_gain" effects (budget, rating) when you get it."""
    msgs = []
    for e in data.relics[rid].get("on_gain", []):
        if e.get("type") == "budget":
            run.budget += e["amount"]
            msgs.append(f"+{fmt_money(e['amount'])}")
        elif e.get("type") == "rating":
            run.rating = clamp(run.rating + e["amount"], 0.0, float(data.config["run"]["max_rating"]))
            msgs.append(f"{e['amount']:+g} trust")
    return ", ".join(msgs)


def roster_issues(data, run: RunState) -> list:
    """(level, text, code) triples for the planning screen. level: error | warn | info."""
    issues = []
    roster = run.roster
    n_shifts = data.slots_per_day
    desks = desk_count(data, run)
    shift_names = [s["name"] for s in data.shifts]

    def label(slot):
        day, s = divmod(slot, n_shifts)
        return f"{DAY_NAMES[day]} {shift_names[s][0]}"

    lineups = []
    unmanned, single = [], []
    for slot in range(data.slots_per_week):
        ids = [gid for gid in roster.lineup(slot)
               if run.gha(gid) and run.gha(gid).active and gid not in run.away_week and gid not in roster.leave]
        lineups.append(ids)
        if not ids:
            unmanned.append(label(slot))
        elif len(ids) > desks:
            issues.append(("error", f"{label(slot)}: {len(ids)} rostered but only {desks} desks", "desks"))
        elif len(ids) == 1:
            single.append(label(slot))
    if unmanned:
        issues.append(("error", f"Unmanned ({len(unmanned)}): " + ", ".join(unmanned), "unmanned"))
    if single:
        issues.append(("warn", f"Only one analyst ({len(single)}): " + ", ".join(single), "single"))
    doubles = {}
    for slot in range(1, len(lineups)):
        for gid in set(lineups[slot]) & set(lineups[slot - 1]):
            doubles.setdefault(gid, []).append(label(slot - 1) + "+" + label(slot)[-1])
    for gid, where in doubles.items():
        issues.append(("warn", f"{run.gha(gid).first_name} works back-to-back shifts ({', '.join(where)})", "double"))
    if lineups:
        for gid in set(lineups[0]) & set(run.last_slot_lineup):
            issues.append(("warn", f"{run.gha(gid).first_name} worked last night and is on Monday's first shift", "double"))
    for g in run.active_ghas():
        if g.id in run.away_week:
            team = roster.group_of(g.id)
            if team not in ("bench", "leave"):
                issues.append(("info", f"{g.first_name} is away this week, so {data.team_name(team)} team is short",
                               "away"))
        if g.ltf >= data.config["long_term"]["warn_level"] and g.id not in roster.leave:
            issues.append(("warn", f"{g.first_name} is near burnout (long-term fatigue {g.ltf:.0f}). Consider leave.",
                           "burnout"))
    return issues
