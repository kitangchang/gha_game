"""Save slots (pickle). Each slot holds one centre profile, including the run in
progress, which is saved at the start of every week. Saves are tied to the game
version: if the code changes a lot, an old save is ignored."""
from __future__ import annotations

import pickle

from .data import ROOT

SAVE_VERSION = 3
SAVE_DIR = ROOT / "saves"


def slot_path(slot: int):
    return SAVE_DIR / f"slot{slot}.pkl"


def _last_path():
    return SAVE_DIR / "last_slot.txt"


def save_profile(profile) -> bool:
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        path = slot_path(profile.slot)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump({"version": SAVE_VERSION, "profile": profile}, fh)
        tmp.replace(path)
        _last_path().write_text(str(profile.slot), encoding="utf-8")
        return True
    except OSError:
        return False


def load_profile(slot: int):
    path = slot_path(slot)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as fh:
            blob = pickle.load(fh)
        if blob.get("version") != SAVE_VERSION:
            return None
        return blob["profile"]
    except Exception:
        return None


def slot_exists(slot: int) -> bool:
    return slot_path(slot).exists()


def slot_unreadable(slot: int) -> bool:
    """A file is there but can't be loaded (old version or damaged)."""
    return slot_exists(slot) and load_profile(slot) is None


def delete_slot(slot: int):
    try:
        slot_path(slot).unlink()
    except OSError:
        pass


def last_slot():
    try:
        return int(_last_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
