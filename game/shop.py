"""The weekly shop: hires, tools (relics), supplies (consumables), training."""
from __future__ import annotations

from .modifiers import Ctx, collect_specials
from .profile import unlock_level
from .run import HIRE_WEIGHTS, consumable_slots, make_gha, run_mods
from .util import weighted_choice


def price_mult(data, run) -> float:
    return run_mods(data, run).mult("shop_price", Ctx())


def _hire_cost(data, gha, mult) -> float:
    return round(gha.salary * data.config["economy"]["hire_fee_weeks"] * mult, 1)


def generate_shop(data, run, reroll_count: int = 0) -> dict:
    rng = run.rng
    econ = data.config["economy"]
    slots = econ["shop_slots"]
    spec = collect_specials(data, run.relics)
    mult = price_mult(data, run)
    taken = {g.name for g in run.ghas}

    hires = []
    archetypes = list(HIRE_WEIGHTS)
    for _ in range(slots["hires"]):
        arche = weighted_choice(rng, archetypes, [HIRE_WEIGHTS[a] for a in archetypes])
        g = make_gha(data, rng, None, arche, None, taken, week=run.week)
        hires.append({"gha": g, "cost": _hire_cost(data, g, mult), "sold": False, "tag": g.stats["archetype"]})
    if run.flags.pop("graduate_in_shop", False):
        g = make_gha(data, rng, None, "graduate", "seismic", taken, week=run.week)
        if "quick_learner" not in g.traits:
            g.traits.append("quick_learner")
        hires.append({"gha": g, "cost": round(_hire_cost(data, g, mult) * 0.5, 1), "sold": False,
                      "tag": "Keen graduate"})

    rarities = econ["rarity_weights"]
    level = getattr(run, "unlock_level", 99)
    pool = [r for r in data.relics.values() if r["id"] not in run.relics and unlock_level(r) <= level]
    relics = []
    for _ in range(slots["relics"] + int(spec.get("shop_extra_relic", 0))):
        if not pool:
            break
        r = weighted_choice(rng, pool, [rarities.get(p["rarity"], 1) for p in pool])
        pool.remove(r)
        relics.append({"id": r["id"], "cost": round(econ["relic_costs"][r["rarity"]] * mult, 1), "sold": False})

    cons_ids = [cid for cid, c in data.consumables.items() if unlock_level(c) <= level]
    rng.shuffle(cons_ids)
    consumables = [{"id": cid, "cost": round(data.consumables[cid]["cost"] * mult, 1), "sold": False}
                   for cid in cons_ids[: slots["consumables"]]]

    train_ids = [tid for tid, t in data.training.items() if unlock_level(t) <= level]
    rng.shuffle(train_ids)
    training = [{"id": tid, "cost": round(data.training[tid]["cost"] * mult, 1), "sold": False}
                for tid in train_ids[: slots["training"]]]

    return {"week": run.week, "hires": hires, "relics": relics, "consumables": consumables,
            "training": training, "rerolls": reroll_count,
            "reroll_cost": round(econ["reroll_cost"] + econ["reroll_cost_step"] * reroll_count, 1)}


def _pay(run, cost) -> bool:
    if run.budget + 1e-9 < cost:
        return False
    run.budget -= cost
    return True


def buy_hire(data, run, index: int) -> tuple:
    item = run.shop["hires"][index]
    if item["sold"]:
        return False, "Already hired."
    if not _pay(run, item["cost"]):
        return False, "Not enough budget."
    g = item["gha"]
    g.id = run.new_id("gha")
    g.hired_week = run.week
    run.ghas.append(g)
    item["sold"] = True
    return True, f"{g.name} joins the team (on the bench until you place them)."


def buy_relic(data, run, index: int) -> tuple:
    item = run.shop["relics"][index]
    if item["sold"] or item["id"] in run.relics:
        return False, "Already owned."
    if not _pay(run, item["cost"]):
        return False, "Not enough budget."
    run.relics.append(item["id"])
    item["sold"] = True
    return True, f"Bought {data.relics[item['id']]['name']}."


def buy_consumable(data, run, index: int) -> tuple:
    item = run.shop["consumables"][index]
    if item["sold"]:
        return False, "Sold out."
    if len(run.consumables) >= consumable_slots(data, run):
        return False, "Supply cupboard is full."
    if not _pay(run, item["cost"]):
        return False, "Not enough budget."
    run.consumables.append(item["id"])
    item["sold"] = True
    return True, f"Bought {data.consumables[item['id']]['name']}."


def training_targets(data, run, index: int) -> list:
    """Analysts a training item can be used on."""
    t = data.training[run.shop["training"][index]["id"]]
    out = []
    for g in run.active_ghas():
        if t["effect"] == "skill" and g.skills.get(t["skill"], 1) >= data.config["skill_model"]["max_level"]:
            continue
        if t["effect"] == "remove_bad_trait" and not any(not data.traits[x].get("good", True) for x in g.traits):
            continue
        if t["effect"] == "add_trait" and t["trait"] in g.traits:
            continue
        if t["effect"] == "ltf" and g.ltf <= 0:
            continue
        out.append(g)
    return out


def buy_training(data, run, index: int, gid: int) -> tuple:
    item = run.shop["training"][index]
    if item["sold"]:
        return False, "Already used."
    g = run.gha(gid)
    if g is None or g not in training_targets(data, run, index):
        return False, "Can't train them with that."
    if not _pay(run, item["cost"]):
        return False, "Not enough budget."
    t = data.training[item["id"]]
    if t["effect"] == "skill":
        g.skills[t["skill"]] = min(data.config["skill_model"]["max_level"], g.skills.get(t["skill"], 1) + t.get("amount", 1))
        msg = f"{g.first_name}: {data.skill_name(t['skill'])} {g.skills[t['skill']]}"
    elif t["effect"] == "ltf":
        g.ltf = max(0.0, g.ltf + t["amount"])
        msg = f"{g.first_name}: long-term fatigue {g.ltf:.0f}"
    elif t["effect"] == "remove_bad_trait":
        bad = [x for x in g.traits if not data.traits[x].get("good", True)]
        removed = run.rng.choice(bad)
        g.traits.remove(removed)
        msg = f"{g.first_name} lost '{data.traits[removed]['name']}'"
    else:
        g.traits.append(t["trait"])
        msg = f"{g.first_name} gained '{data.traits[t['trait']]['name']}'"
    from .run import salary_for
    g.salary = salary_for(data, g.skills, g.traits)
    item["sold"] = True
    return True, msg


def reroll(data, run) -> tuple:
    cost = run.shop["reroll_cost"]
    if not _pay(run, cost):
        return False, "Not enough budget."
    run.shop = generate_shop(data, run, run.shop["rerolls"] + 1)
    return True, "New stock arrived."


def let_go(data, run, gid: int) -> tuple:
    g = run.gha(gid)
    if g is None or not g.active:
        return False, "Not on the team."
    if len(run.active_ghas()) <= 2:
        return False, "You need at least two analysts."
    g.active = False
    g.left_reason = "Let go"
    run.roster.remove(gid)
    run.ghas.remove(g)
    return True, f"{g.name} has left the team."
