"""Operaciones puras sobre regiones: validan y calculan before/after.

Sin IO, sin DB: testeables directas. La persistencia vive en service.py.
"""

from __future__ import annotations

from ...games import tokens as game_tokens

MIN_SIDE = 4


class EditorError(Exception):
    pass


def _check_box(x: int, y: int, w: int, h: int) -> None:
    if w < MIN_SIDE or h < MIN_SIDE:
        raise EditorError(f"INVALID_REGION: bbox {w}x{h} bajo mínimo {MIN_SIDE}")
    if x < 0 or y < 0:
        raise EditorError("INVALID_REGION: coordenadas negativas")


def move(region: dict, x: int, y: int) -> tuple[dict, dict]:
    _check_box(x, y, region["w"], region["h"])
    return {"x": region["x"], "y": region["y"]}, {"x": x, "y": y}


def resize(region: dict, x: int, y: int, w: int, h: int) -> tuple[dict, dict]:
    _check_box(x, y, w, h)
    before = {"x": region["x"], "y": region["y"], "w": region["w"], "h": region["h"]}
    return before, {"x": x, "y": y, "w": w, "h": h}


def check_translation(source: str, translation: str) -> list[str]:
    """Avisos (no excepciones): tokens que el usuario eliminó."""
    missing = [t for t in game_tokens.find_tokens(source) if t not in translation]
    return [f"TOKEN_MISMATCH: falta {t}" for t in missing]


def node_id(image_id: str, existing: list[str], prefix: str = "manual") -> str:
    n = sum(1 for i in existing if f":{prefix}" in i)
    rid = f"{image_id}:{prefix}{n}"
    while rid in existing:
        n += 1
        rid = f"{image_id}:{prefix}{n}"
    return rid
