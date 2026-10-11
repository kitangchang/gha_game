"""Seismic Shift — run with:  python main.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    try:
        import pygame  # noqa: F401
    except ImportError:
        print("Seismic Shift needs pygame. Install it with:\n    pip install pygame-ce\n(or: pip install pygame)")
        sys.exit(1)
    from game.data import DataError
    try:
        from ui.app import App
        app = App()
    except DataError as exc:
        print(exc)
        sys.exit(1)
    app.run()


if __name__ == "__main__":
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    main()
