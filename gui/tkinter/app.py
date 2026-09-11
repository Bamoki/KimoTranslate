"""Entrada GUI (dev): `python gui/tkinter/app.py`. Lanza el shell CustomTkinter.

La GUI anterior vive en gui/legacy/ (referencia). Toda la lógica HTTP está
en gui/client.py (testeable sin display).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from gui.app import App  # noqa: E402
from gui.client import KimoApiClient  # noqa: E402


def _version() -> str:
    try:
        from kimotranslate import __version__

        return __version__
    except ImportError:
        return "0.8.1"


def main() -> None:
    from gui.tkinter import config as _config

    try:
        cfg = _config.load()
    except OSError:
        cfg = _config.defaults()
    base = os.environ.get("KIMOTRANSLATE_SERVER_URL") or cfg.get("server_url", "")
    App(KimoApiClient(base or "http://127.0.0.1:8005"), version=_version()).mainloop()


if __name__ == "__main__":
    main()
