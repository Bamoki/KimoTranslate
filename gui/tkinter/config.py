"""Config local de la GUI (stdlib). Sin secretos: solo URL y preferencias."""

from __future__ import annotations

import json
import os

DEFAULT_URL = "http://192.168.1.20:8005"  # sugerencia inicial, editable en la GUI
CONFIG_VERSION = 1


def config_path() -> str:
    override = os.environ.get("KIMOTRANSLATE_CONFIG", "").strip()
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "KimoTranslate")
    else:
        d = os.path.join(os.path.expanduser("~"), ".config", "kimotranslate")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "config.json")


def defaults() -> dict:
    return {
        "server_url": DEFAULT_URL,
        "auto_update": True,
        "last_update_check": "",
        "config_version": CONFIG_VERSION,
    }


def load(path: str = "") -> dict:
    cfg = defaults()
    try:
        with open(path or config_path(), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict, path: str = "") -> str:
    p = path or config_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    os.replace(tmp, p)
    return p
