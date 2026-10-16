"""Effects used by random events and supplies (see data/events.json)."""
from __future__ import annotations

from .models import GHA, Task
from .util import clamp, fmt_money


def _pick(eng, who: str, target=None, skill: str | None = None) -> list:
    rng = eng.rng
    present = eng.present_ghas()
    if who == "on_shift":
        return [eng.ghas[gid] for gid in eng.on_shift]
    if who == "all":
        return [g for g in eng.ghas.values() if g.active and not g.temp]
    if who == "target":
        return [target] if isinstance(target, GHA) else []
    if who == "random":
        return [rng.choice(present)] if present else []
    if who == "best_skill":
        return [max(present, key=lambda g: (g.base_skill(skill or "comms"), -g.fatigue))] if present else []
    if who == "least_fatigued":
        return [min(present, key=lambda g: g.fatigue)] if present else []
    if who == "most_fatigued":
        return [max(present, key=lambda g: g.fatigue)] if present else []
    if who == "random_off_shift":
        off = [g for g in eng.ghas.values() if g.active and not g.temp and not g.on_shift]
        return [rng.choice(off)] if off else []
    return []


def apply_effects(eng, effects: list, target=None) -> list:
    msgs: list = []
    for e in effects:
        msgs.extend(apply_effect(eng, e, target))
    return msgs


def apply_effect(eng, e: dict, target=None) -> list:
    run, data, rng = eng.run, eng.data, eng.rng
    kind = e["type"]
    floor_frac = eng.cfg["fatigue"]["floor_from_ltf"]

    if kind == "rating":
        eng.change_rating(e["amount"], "event")
        return [f"Trust {e['amount']:+g}"]
    if kind == "budget":
        run.budget += e["amount"]
        return [f"Budget {'+' if e['amount'] >= 0 else ''}{fmt_money(e['amount'])}"]
    if kind == "fatigue":
        out = []
        for g in _pick(eng, e.get("who", "on_shift"), target):
            g.fatigue = clamp(g.fatigue + e["amount"], g.ltf * floor_frac if e["amount"] < 0 else 0.0, 100.0)
            out.append(g.first_name)
        return [f"Fatigue {e['amount']:+g} ({', '.join(out)})"] if out else []
    if kind == "fatigue_floor":
        for g in _pick(eng, e.get("who", "target"), target):
            g.fatigue = g.ltf * floor_frac
        return []
    if kind == "ltf":
        out = []
        for g in _pick(eng, e.get("who", "target"), target):
            g.ltf = clamp(g.ltf + e["amount"], 0.0, 100.0)
            out.append(g.first_name)
        return [f"Long-term fatigue {e['amount']:+g} ({', '.join(out)})"] if out else []
    if kind == "away":
        out = []
        for g in _pick(eng, e.get("pick", "random"), target, e.get("skill")):
            eng.send_away(g, e.get("hours", 1), e.get("reason", "Away"))
            out.append(f"{g.first_name} away {e.get('hours', 1):g} h")
        return out
    if kind == "spawn_task":
        n = int(e.get("count", 1))
        for _ in range(n):
            eng.spawn_bau(e["task"])
        name = data.bau[e["task"]]["name"]
        return [f"New task: {name}" + (f" x{n}" if n > 1 else "")]
    if kind == "modifier":
        eng.mods.add_temp(e["modifier"], eng.now + e.get("hours", 1) * 60.0)
        return []
    if kind == "relic":
        if e.get("id"):
            choices = [e["id"]] if e["id"] not in run.relics else []
        else:
            rar = e.get("rarities")
            level = getattr(run, "unlock_level", 99)
            choices = [r["id"] for r in data.relics.values()
                       if r["id"] not in run.relics and (r["rarity"] in rar if rar else r["rarity"] != "boss")
                       and int(r.get("unlock_level", 1)) <= level]
            tag = e.get("tag")
            if tag:
                # Prefer tools with this tag; if there are none left, any tool of those rarities will do.
                tagged = [rid for rid in choices if tag in data.relics[rid].get("tags", [])]
                choices = tagged or choices
        if not choices:
            return ["No new tool available"]
        rid = rng.choice(choices)
        run.relics.append(rid)
        eng.refresh_mods()
        return [f"New tool: {data.relics[rid]['name']}"]
    if kind == "consumable":
        level = getattr(run, "unlock_level", 99)
        cid = e.get("id") or rng.choice([c for c, item in data.consumables.items()
                                         if int(item.get("unlock_level", 1)) <= level] or list(data.consumables))
        slots = eng.cfg["run"]["max_consumables"] + int(eng.specials.get("consumable_slots", 0))
        if len(run.consumables) >= slots:
            return ["Supply cupboard full"]
        run.consumables.append(cid)
        return [f"New supply: {data.consumables[cid]['name']}"]
    if kind == "chance":
        if rng.random() < e.get("p", 0.5):
            return apply_effects(eng, e.get("success", []), target) + [e.get("success_text", "")]
        return apply_effects(eng, e.get("failure", []), target) + [e.get("failure_text", "")]
    if kind == "flag":
        run.flags[e["key"]] = e.get("value", True)
        return []
    if kind == "complete_task":
        if isinstance(target, Task):
            eng.complete_external(target)
            return [f"Done: {eng.task_title(target)}"]
        return []
    if kind == "extend_deadline":
        if isinstance(target, Task):
            target.deadline += e.get("minutes", 60)
            if target.overdue and target.available is not None and eng.now <= target.available + target.deadline:
                target.overdue = False
            return [f"Deadline extended: {eng.task_title(target)}"]
        return []
    if kind == "temp_gha":
        g = eng.add_temp_gha(e.get("name", "Contractor"), e.get("skills", {}))
        return [f"{g.name} has arrived"] if g else ["No free desk"]
    return []


def reward_summary(data, effects: list) -> str:
    """Short text for what a contract pays: '+$3.0k', 'a new uncommon or rare tool', '+2 trust'."""
    parts = []
    for e in effects:
        kind = e.get("type")
        if kind == "budget":
            parts.append(f"+{fmt_money(e['amount'])}")
        elif kind == "rating":
            parts.append(f"{e['amount']:+g} trust")
        elif kind == "relic":
            if e.get("id") and e["id"] in data.relics:
                parts.append(data.relics[e["id"]]["name"])
            else:
                rar = e.get("rarities")
                tag = data.tags[e["tag"]]["name"] + " " if e.get("tag") in data.tags else ""
                parts.append("a new " + (" or ".join(rar) + " " if rar else "") + tag + "tool")
        elif kind == "consumable":
            parts.append(data.consumables[e["id"]]["name"] if e.get("id") in data.consumables else "a random supply")
        elif kind == "modifier":
            parts.append(f"a {e.get('hours', 1):g} h boost")
        elif kind == "chance":
            parts.append("a chance of a bonus")
    return ", ".join(parts) or "a reward"
