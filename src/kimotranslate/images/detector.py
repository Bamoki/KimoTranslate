"""Detector de imágenes localizables: heurísticas baratas, nunca borra.

Marca likely_text=false (iconos, thumbnails, fondos por ruta, duplicados por
hash) pero conserva el asset. La decisión final la da el OCR (confidence).
"""

from __future__ import annotations

import hashlib
import os

TEXT_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
MIN_SIDE = 64
SKIP_NAME_PARTS = ("thumb", "icon", "logo", "cursor", "button_icon")
SKIP_DIR_PARTS = ("thumb", "icon")
BG_DIR_PARTS = ("bg", "background", "backdrop")


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def probe(path: str) -> dict | None:
    """Lee dimensiones/formato con PIL. None si no es imagen soportada."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            im.load()
            return {
                "width": im.width,
                "height": im.height,
                "format": (im.format or "").lower(),
                "mode": im.mode,
            }
    except Exception:  # noqa: BLE001 - archivo no-imagen o corrupto: skip
        return None


def classify(relpath: str, info: dict, seen_hashes: set[str]) -> tuple[bool, str]:
    name = os.path.basename(relpath).lower()
    dirs = relpath.lower().split(os.sep)
    if info["width"] < MIN_SIDE or info["height"] < MIN_SIDE:
        return False, "too-small"
    if any(p in name for p in SKIP_NAME_PARTS):
        return False, "icon-like-name"
    if any(p in d for d in dirs for p in SKIP_DIR_PARTS):
        return False, "icon-dir"
    if any(p in d for d in dirs for p in BG_DIR_PARTS):
        return False, "background-dir"
    if info.get("hash", "") in seen_hashes:
        return False, "duplicate"
    return True, ""


def discover(game_path: str, subdirs: tuple[str, ...] = ("",)) -> list[dict]:
    """Recorre el juego y devuelve un asset-dict por imagen. Incremental por fichero."""
    assets, seen = [], set()
    for sub in subdirs:
        root = os.path.join(game_path, sub)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, files in os.walk(root):
            dirnames.sort()  # determinista: el original gana al duplicado
            for f in sorted(files):
                if not f.lower().endswith(TEXT_EXTS):
                    continue
                path = os.path.join(dirpath, f)
                rel = os.path.relpath(path, game_path)
                info = probe(path)
                if info is None:
                    continue
                try:
                    info["hash"] = file_hash(path)
                except OSError:
                    continue
                likely, reason = classify(rel, info, seen)
                seen.add(info["hash"])
                assets.append(
                    {
                        "file_path": path,
                        "relpath": rel,
                        "original_hash": info["hash"],
                        "width": info["width"],
                        "height": info["height"],
                        "format": info["format"],
                        "likely_text": likely,
                        "skip_reason": reason,
                    }
                )
    return assets
