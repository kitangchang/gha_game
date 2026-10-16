"""Tags: families that traits, tools and supplies belong to (data/tags.json).

A modifier with "per_tag" is applied once for every matching tag the run has:
on owned tools, on the supplies in the cupboard and on the traits of every
active analyst. "per_tag": "any" counts all tags."""
from __future__ import annotations

from collections import Counter

ANY = "any"


def tags_of(item: dict | None) -> list:
    return list((item or {}).get("tags", []))


def tag_sources(data, run) -> dict:
    """{tag: [(kind, label), ...]} for everything the run currently has."""
    out: dict = {}

    def add(tags, kind, label):
        for tag in tags:
            out.setdefault(tag, []).append((kind, label))

    for rid in run.relics:
        if rid in data.relics:
            add(tags_of(data.relics[rid]), "tool", data.relics[rid]["name"])
    for cid in run.consumables:
        if cid in data.consumables:
            add(tags_of(data.consumables[cid]), "supply", data.consumables[cid]["name"])
    for g in run.active_ghas():
        for tid in g.traits:
            t = data.traits.get(tid)
            if t:
                add(tags_of(t), "trait", f"{g.first_name} ({t['name']})")
    return out


def count_tags(data, run) -> Counter:
    return Counter({tag: len(srcs) for tag, srcs in tag_sources(data, run).items()})


def tag_total(counts, tag: str) -> int:
    if tag == ANY:
        return sum(counts.values())
    return counts.get(tag, 0)


def scaled_value(m: dict, counts) -> float:
    """A modifier's value after per_tag scaling (linear: +1% per tag stays +1% per tag)."""
    value = m["value"]
    tag = m.get("per_tag")
    if not tag:
        return value
    n = tag_total(counts or {}, tag)
    if "max_tags" in m:
        n = min(n, int(m["max_tags"]))
    if m.get("op", "mult") == "add":
        return value * n
    return max(0.05, 1.0 + (value - 1.0) * n)


def scaling_tags(item: dict | None) -> list:
    """Tags an item's modifiers scale with, in order, without repeats."""
    seen = []
    for m in (item or {}).get("modifiers", []):
        tag = m.get("per_tag")
        if tag and tag not in seen:
            seen.append(tag)
    return seen
