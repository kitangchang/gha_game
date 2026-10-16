"""Avatar pieces: which layers exist and which piece each analyst gets.

Art lives in assets/avatars/<layer>/*.png and is described by
assets/avatars/avatar_config.json (layer order, tints, chances). This module
only deals with file names, so it works without pygame. The UI composes the
actual images (ui/avatars.py).
"""
from __future__ import annotations

import fnmatch
import json
import random

from .data import ROOT

AVATAR_DIR = ROOT / "assets" / "avatars"
MANIFEST_FILE = AVATAR_DIR / "avatar_config.json"

DEFAULT_MANIFEST = {
    "canvas": [128, 128],
    "pixel_art": False,
    "portrait_crop": [14, 4, 100, 100],
    "layers": [
        {"name": "skin", "tint": "skin_tones", "required": True},
        {"name": "clothes", "tint": "team"},
        {"name": "eyes"},
        {"name": "nose"},
        {"name": "mouth"},
        {"name": "hair", "tint": "hair_colours", "chance_none": 0.06},
        {"name": "accessories", "chance_none": 0.55},
    ],
    "palettes": {
        "skin_tones": [[255, 226, 200], [244, 204, 170], [230, 180, 140], [205, 150, 110],
                       [170, 115, 80], [130, 88, 60], [96, 64, 44]],
        "hair_colours": [[40, 32, 30], [70, 50, 38], [110, 74, 48], [150, 98, 60], [196, 150, 90],
                         [222, 196, 140], [176, 176, 180], [236, 236, 236]],
    },
    "overlays": {"tired": "overlays/tired.png"},
    "tired_fatigue": 70,
}

_SCAN: dict | None = None
_MANIFEST: dict | None = None


def load_manifest() -> dict:
    global _MANIFEST
    if _MANIFEST is None:
        manifest = json.loads(json.dumps(DEFAULT_MANIFEST))
        if MANIFEST_FILE.exists():
            try:
                with open(MANIFEST_FILE, encoding="utf-8") as fh:
                    user = json.load(fh)
                for key, value in user.items():
                    if not key.startswith("_"):
                        manifest[key] = value
            except (OSError, json.JSONDecodeError) as exc:
                print(f"avatar_config.json ignored: {exc}")
        _MANIFEST = manifest
    return _MANIFEST


def layer_names(manifest: dict | None = None) -> list:
    manifest = manifest or load_manifest()
    return [layer["name"] for layer in manifest["layers"]]


def scan(force: bool = False) -> dict:
    """{layer: [front piece file names]} from the asset folders. *_back.png files
    are the behind-the-head half of a piece and are not listed separately."""
    global _SCAN
    if _SCAN is None or force:
        out = {}
        for name in layer_names():
            folder = AVATAR_DIR / name
            if folder.is_dir():
                out[name] = sorted(p.name for p in folder.glob("*.png") if not p.stem.endswith("_back"))
            else:
                out[name] = []
        _SCAN = out
    return _SCAN


def clear_cache():
    global _SCAN, _MANIFEST
    _SCAN = None
    _MANIFEST = None


def piece_fits(file: str, gender: str = "") -> bool:
    """Pieces named f_*.png are only for female analysts and m_*.png only for male
    ones; anything else suits everyone."""
    low = file.lower()
    if low.startswith("f_"):
        return gender != "m"
    if low.startswith("m_"):
        return gender != "f"
    return True


def _matches(rule_value, chosen) -> bool:
    """Does one part of an "exclude" rule match what was picked? Layers are matched
    by file name patterns ("afro*.png", "m_*"); palettes by colour index (0 = first)."""
    if chosen is None:
        return False
    patterns = rule_value if isinstance(rule_value, list) else [rule_value]
    for pat in patterns:
        if isinstance(pat, int):
            if chosen == pat:
                return True
        elif isinstance(chosen, str) and fnmatch.fnmatch(chosen.lower(), str(pat).lower()):
            return True
    return False


def allowed(rules: list, picked: dict, key: str, value) -> bool:
    """False if picking `value` for `key` (a layer or palette name) would complete an
    exclude rule together with what's already been picked."""
    for rule in rules:
        if key not in rule or not _matches(rule[key], value):
            continue
        others = [k for k in rule if k != key]
        if others and all(k in picked and _matches(rule[k], picked[k]) for k in others):
            return False
    return True


def random_avatar(rng: random.Random, gender: str = "") -> dict:
    """Pick a piece (and tint) for every layer that has art. Uses a private RNG
    seeded from rng, so adding art never changes the rest of a run."""
    local = random.Random(rng.random())
    manifest = load_manifest()
    pieces = scan()
    avatar = {}
    chosen: dict = {}            # one colour per palette, so skin, nose and ears all match
    rules = [r for r in manifest.get("exclude", []) if isinstance(r, dict)]
    picked: dict = {}            # layer -> file, palette -> colour index, for the exclude rules
    for layer in manifest["layers"]:
        name = layer["name"]
        files = [f for f in pieces.get(name, []) if piece_fits(f, gender)]
        files = [f for f in files if allowed(rules, picked, name, f)] or files
        roll_none = local.random()
        pick = local.random()
        tint_pick = local.random()
        if not files:
            continue
        chance = layer.get("chance_none", 0.0)
        if isinstance(chance, dict):            # per gender, e.g. {"f": 0.0, "m": 0.12}
            chance = chance.get(gender, chance.get("any", max(chance.values(), default=0.0)))
        if not layer.get("required") and roll_none < chance:
            avatar[name] = None
            continue
        file = files[int(pick * len(files)) % len(files)]
        picked[name] = file
        tint = None
        palette = layer.get("tint")
        if palette and palette != "team":
            colours = manifest.get("palettes", {}).get(palette) or [[255, 255, 255]]
            if palette not in chosen:
                ok = [i for i in range(len(colours)) if allowed(rules, picked, palette, i)] or list(range(len(colours)))
                idx = ok[int(tint_pick * len(ok)) % len(ok)]
                chosen[palette] = list(colours[idx])
                picked[palette] = idx
                # A small chance of a two-colour gradient (top colour -> bottom colour)
                grad = float((manifest.get("gradients") or {}).get(palette, 0.0))
                if grad > 0 and len(colours) > 1 and local.random() < grad:
                    others = [i for i in range(len(colours)) if list(colours[i]) != list(colours[idx])]
                    if others:
                        chosen[palette] = [list(colours[idx]), list(colours[local.choice(others)])]
            tint = chosen[palette]
        avatar[name] = {"file": file, "tint": tint}
    return avatar
