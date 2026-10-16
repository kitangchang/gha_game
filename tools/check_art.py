"""Lists which tools, supplies and training items have an icon yet.

    python tools/check_art.py

Icons live in assets/items/<tools|supplies|training>/<item id>.png. The data
files are checked too (duplicate ids, bad stats), so this is also a quick way
to test a JSON edit without starting the game.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.art_check import full_lines  # noqa: E402
from game.data import DataError, GameData  # noqa: E402


def main():
    try:
        data = GameData()
    except DataError as exc:
        print(exc)
        sys.exit(1)
    print("Data files OK.")
    print("\n".join(full_lines(data)))


if __name__ == "__main__":
    main()
