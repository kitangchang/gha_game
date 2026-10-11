"""Builds tasks: earthquake stages, SOP checklists, business-as-usual work and
staffing calls."""
from __future__ import annotations

from .models import EqEvent, Task


def eq_tier(data, mag: float) -> dict:
    tiers = data.config["eq"]["tiers"]
    chosen = tiers[0]
    for tier in tiers:
        if mag >= tier["min_mag"]:
            chosen = tier
    return chosen


def sops_for(data, mag: float, depth: float, region: str) -> list:
    found = []
    for sop in data.sops:
        for trig in sop["triggers"]:
            if trig["region"] != region:
                continue
            if mag < trig.get("min_mag", -99):
                continue
            if depth > trig.get("max_depth", 99999):
                continue
            found.append(sop)
            break
    return found


def sop_threshold(data, mag: float, depth: float, region: str):
    """Highest trigger magnitude among the SOP triggers this event meets (None if no SOP)."""
    best = None
    for sop in data.sops:
        for trig in sop["triggers"]:
            if trig["region"] == region and mag >= trig.get("min_mag", -99) and depth <= trig.get("max_depth", 99999):
                thr = trig.get("min_mag", -99)
                best = thr if best is None else max(best, thr)
    return best


def eq_params(data, mag: float, depth: float, region: str) -> dict:
    cfg = data.config["eq"]
    tier = eq_tier(data, mag)
    reg = cfg["regions"].get(region, cfg["regions"]["elsewhere"])
    importance = tier["importance"] * reg["importance"]
    if region == "local" and depth < cfg["shallow_depth_km"]:
        importance *= cfg["shallow_importance_mult"]
    sops = sops_for(data, mag, depth, region)
    return {
        "complexity": tier["complexity"],
        "work": tier["work"] * reg["work"] * data.config["balance"]["work_scale"],
        "deadline": tier["deadline"] * reg["deadline"],
        "importance": importance,
        "sops": sops,
        "two_stage": mag > cfg["two_stage_above"] or bool(sops),
    }


def _merged_sop_tasks(sops: list) -> list:
    """Union of SOP checklists for one event, de-duplicated by task type."""
    merged: dict = {}
    order: list = []
    for sop in sops:
        for st in sop["tasks"]:
            entry = merged.get(st["type"])
            if entry is None:
                merged[st["type"]] = {
                    "type": st["type"],
                    "requires": list(st.get("requires", [])),
                    "visible": st.get("visible", "locked"),
                    "sops": [sop["id"]],
                }
                order.append(st["type"])
            else:
                for req in st.get("requires", []):
                    if req not in entry["requires"]:
                        entry["requires"].append(req)
                entry["sops"].append(sop["id"])
    return [merged[t] for t in order]


def estimate_event_work(data, mag: float, depth: float, region: str) -> float:
    """Total analyst-minutes an event is expected to generate (for difficulty)."""
    p = eq_params(data, mag, depth, region)
    cfg = data.config["eq"]
    if p["two_stage"]:
        total = p["work"] * (cfg["prelim_work_frac"] + cfg["confirm_work_frac"])
    else:
        total = p["work"]
    ws = data.config["balance"]["work_scale"]
    for st in _merged_sop_tasks(p["sops"]):
        total += data.sop_task_types[st["type"]]["work"] * ws
    return total


def build_event_tasks(run, data, ev: EqEvent, now: float) -> list:
    cfg = data.config["eq"]
    p = eq_params(data, ev.mag, ev.depth, ev.region)
    ev.two_stage = p["two_stage"]
    ev.sops = [s["id"] for s in p["sops"]]
    sop_ids = list(ev.sops)
    skill = cfg["skill"]
    tasks: list = []
    by_type: dict = {}

    if ev.two_stage:
        pre_deadline = p["deadline"]
        conf_deadline = p["deadline"] * cfg["confirm_deadline_mult"]
        for sop in p["sops"]:
            pre_deadline = min(pre_deadline, sop.get("prelim_deadline", pre_deadline))
            conf_deadline = min(conf_deadline, sop.get("confirm_deadline", conf_deadline))
        prelim = Task(id=run.new_id("task"), kind="eq", type="prelim", name="Prelim solution", skill=skill,
                      work=p["work"] * cfg["prelim_work_frac"], complexity=p["complexity"],
                      importance=p["importance"], deadline=pre_deadline, created=now, available=now,
                      event_uid=ev.uid, sop_tags=list(sop_ids))
        confirm = Task(id=run.new_id("task"), kind="eq", type="confirm", name="Confirm solution", skill=skill,
                       work=p["work"] * cfg["confirm_work_frac"], complexity=p["complexity"],
                       importance=p["importance"], deadline=conf_deadline, created=now, available=None,
                       requires=[prelim.id], event_uid=ev.uid, sop_tags=list(sop_ids))
        tasks += [prelim, confirm]
        by_type["prelim"] = prelim
        by_type["confirm"] = confirm
    else:
        review = Task(id=run.new_id("task"), kind="eq", type="review", name="Review event", skill=skill,
                      work=p["work"], complexity=p["complexity"], importance=p["importance"],
                      deadline=p["deadline"], created=now, available=now, event_uid=ev.uid)
        tasks.append(review)
        by_type["review"] = review

    ws = data.config["balance"]["work_scale"]
    sop_entries = _merged_sop_tasks(p["sops"])
    for entry in sop_entries:
        tt = data.sop_task_types[entry["type"]]
        locked = bool(entry["requires"])
        task = Task(id=run.new_id("task"), kind="sop", type=entry["type"], name=tt["name"], skill=tt["skill"],
                    work=tt["work"] * ws, complexity=tt["complexity"], importance=tt["importance"],
                    deadline=tt["deadline"], created=now, available=None if locked else now,
                    hidden=locked and entry["visible"] == "on_unlock", event_uid=ev.uid,
                    sop_tags=list(entry["sops"]))
        tasks.append(task)
        by_type[entry["type"]] = task
    for entry in sop_entries:
        task = by_type[entry["type"]]
        task.requires = [by_type[r].id for r in entry["requires"] if r in by_type]
        if not task.requires:
            task.available = now
            task.hidden = False

    ev.task_ids = {k: t.id for k, t in by_type.items()}
    return tasks


def build_sop_task(run, data, ev: EqEvent, task_type: str, now: float, sop_ids: list, name: str | None = None,
                   available: bool = True) -> Task:
    """One SOP step for an event, e.g. 'Assess DART signals' added to an SOP that's already running."""
    tt = data.sop_task_types[task_type]
    return Task(id=run.new_id("task"), kind="sop", type=task_type, name=name or tt["name"], skill=tt["skill"],
                work=tt["work"] * data.config["balance"]["work_scale"], complexity=tt["complexity"],
                importance=tt["importance"], deadline=tt["deadline"], created=now,
                available=now if available else None, event_uid=ev.uid, sop_tags=list(sop_ids))


def build_sop_checklist(run, data, ev: EqEvent, sop: dict, now: float) -> list:
    """Tasks for an SOP that starts after the quake itself (the DART Trigger SOP). A step with
    'repeat' and 'every_minutes' is added several times; copy k appears k * every_minutes later
    (meta['available_at']) and stays hidden until then if visible is 'on_unlock'."""
    tasks: list = []
    by_key: dict = {}
    for st in sop["tasks"]:
        repeat = max(1, int(st.get("repeat", 1)))
        every = float(st.get("every_minutes", 0.0))
        for k in range(repeat):
            delay = every * (k + 1) if every > 0 else 0.0
            key = st["type"] if repeat == 1 else f"{st['type']}_{k + 1}"
            if key in ev.task_ids:          # e.g. the event's own SOP already pages the duty officers
                continue
            name = data.sop_task_types[st["type"]]["name"] + (f" ({k + 1}/{repeat})" if repeat > 1 else "")
            t = build_sop_task(run, data, ev, st["type"], now, [sop["id"]], name, available=delay <= 0)
            if delay > 0:
                t.meta["available_at"] = now + delay
                t.hidden = st.get("visible", "locked") == "on_unlock"
            t.meta["step"] = st["type"]
            tasks.append(t)
            by_key[key] = (t, st)
    for t, st in by_key.values():
        reqs = []
        for r in st.get("requires", []):
            rid = ev.task_ids.get(r) or (by_key[r][0].id if r in by_key else None)
            if rid is not None:
                reqs.append(rid)
        t.requires = reqs
        if reqs:
            t.available = None
    ev.task_ids.update({k: t.id for k, (t, _) in by_key.items()})
    return tasks


def build_bau_task(run, data, bau_id: str, now: float) -> Task:
    b = data.bau[bau_id]
    return Task(id=run.new_id("task"), kind="bau", type=bau_id, name=b["name"], skill=b["skill"],
                work=b["work"] * data.config["balance"]["work_scale"], complexity=b["complexity"],
                importance=b["importance"], deadline=b["deadline"], created=now, available=now,
                desc=b.get("desc", ""))


def build_staffing_task(run, data, now: float, deadline: float, sick, slot: int, slot_label: str) -> Task:
    st = data.config["sick"]["staffing_task"]
    return Task(id=run.new_id("task"), kind="staffing", type="find_cover", name=st["name"], skill=st["skill"],
                work=st["work"], complexity=st["complexity"], importance=st["importance"],
                deadline=max(15.0, deadline), created=now, available=now,
                subtitle=f"{sick.name} is sick for {slot_label}",
                desc="Ring around for someone to cover the next shift. When it's done you choose who covers.",
                meta={"sick": sick.id, "slot": slot})
