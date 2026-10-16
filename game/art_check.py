"""Which items have a picture in assets/items/ and which don't. Works without
pygame, so tools/check_art.py can run on its own; the game also prints a short
version of this at start-up."""
from __future__ import annotations

from pathlib import Path

from .data import ROOT

ITEM_DIR = ROOT / "assets" / "items"
# folder name -> GameData attribute
CATEGORIES = (("tools", "relics"), ("supplies", "consumables"), ("training", "training"))


def png_files(folder: Path) -> list:
    """PNGs in a folder, whatever the case of the extension (.png or .PNG)."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".png")


def icon_report(data) -> list:
    """One dict per category: have / missing (item ids) and unused PNG file names."""
    out = []
    for folder, attr in CATEGORIES:
        items = getattr(data, attr)
        files = {p.stem: p.name for p in png_files(ITEM_DIR / folder)}
        lower = {stem.lower(): stem for stem in files}
        have, missing, wrong_case = [], [], []
        for iid in items:
            if iid in files:
                have.append(iid)
            elif iid.lower() in lower:
                wrong_case.append((iid, files[lower[iid.lower()]]))
                have.append(iid)
            else:
                missing.append(iid)
        matched = {iid.lower() for iid in have}
        unused = [name for stem, name in files.items() if stem.lower() not in matched]
        upper_ext = [name for name in files.values() if not name.endswith(".png")]
        out.append({"folder": folder, "items": items, "have": have, "missing": missing,
                    "unused": unused, "wrong_case": wrong_case, "upper_ext": upper_ext})
    return out


def summary_lines(data) -> list:
    """Short start-up version: counts, missing ids and stray files."""
    lines = ["Item icons (assets/items/):"]
    for r in icon_report(data):
        total = len(r["items"])
        line = f"  {r['folder']:<9}{len(r['have']):>3}/{total:<3}"
        if r["missing"]:
            line += "  missing: " + ", ".join(r["missing"])
        lines.append(line)
        if r["unused"]:
            lines.append(f"  {'':<9}       not used by any item: " + ", ".join(r["unused"]))
    return lines


def full_lines(data) -> list:
    """Detailed version for tools/check_art.py, with item names."""
    lines = []
    for r in icon_report(data):
        items = r["items"]
        lines.append(f"\n{r['folder'].upper()}  ({len(r['have'])} of {len(items)} drawn)  "
                     f"- assets/items/{r['folder']}/")
        lines.append("  Drawn:")
        for iid in r["have"]:
            lines.append(f"    [x] {items[iid].get('name', iid)}  ({iid})")
        lines.append("  Still to draw:" if r["missing"] else "  Still to draw: none")
        for iid in r["missing"]:
            extra = "  boss" if items[iid].get("rarity") == "boss" else ""
            lines.append(f"    [ ] {items[iid].get('name', iid)}  -> {iid}.png{extra}")
        if r["unused"]:
            lines.append("  PNGs that don't match any item id (typo, or a spare file):")
            lines += [f"    ? {name}" for name in r["unused"]]
        if r["wrong_case"]:
            lines.append("  Name differs from the id only in capitals (works, but matching exactly is tidier):")
            lines += [f"    ! {name}  could be {iid}.png" for iid, name in r["wrong_case"]]
    return lines
