"""Fixtures visuales sintéticos (PIL). Rectángulos negros = "texto".
El OCR mock aporta el texto real; el pipeline (mask/inpaint/render) es real.
Sin material comercial.
"""

from __future__ import annotations

import os


def make_image(path: str, size=(320, 120), boxes=(), bg=(255, 255, 255), mode: str = "RGB") -> str:
    from PIL import Image, ImageDraw

    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.new(mode, size, bg if mode == "RGB" else bg + (255,))
    draw = ImageDraw.Draw(im)
    for x, y, w, h in boxes:
        draw.rectangle([x, y, x + w, y + h], fill=(0, 0, 0))
    im.save(path)
    return path


DLG_BOXES = [(20, 20, 280, 30), (20, 60, 200, 30)]


def make_game_images(root: str, name: str = "vngame") -> dict:
    """Juego sintético con imágenes. Devuelve {relpath: regions mock}."""
    gdir = os.path.join(root, name)
    spec = {
        "cg/dialogue1.png": {
            "size": (320, 120),
            "boxes": DLG_BOXES,
            "texts": ["こんにちは", "お元気ですか"],
        },
        "cg/dialogue_v.png": {
            "size": (120, 320),
            "boxes": [(20, 20, 30, 130)],
            "texts": ["たてがき"],
            "orientations": ["vertical"],
        },
        "ui/menu.png": {
            "size": (400, 100),
            "boxes": [(10, 10, 100, 25), (150, 10, 100, 25)],
            "texts": ["はじめから", "つづきから"],
        },
        "bg/scene01.png": {"size": (640, 480), "boxes": [], "texts": []},
        "thumb/cover_small.png": {
            "size": (320, 120),
            "boxes": DLG_BOXES,
            "texts": ["こんにちは", "お元気ですか"],
        },
        "icon.ico.png": {"size": (32, 32), "boxes": [], "texts": []},
    }
    mapping = {}
    from kimotranslate.images import detector as _det

    for rel, cfg in spec.items():
        path = os.path.join(gdir, rel)
        make_image(path, cfg["size"], cfg["boxes"])
        regions = []
        for i, (box, text) in enumerate(zip(cfg["boxes"], cfg["texts"], strict=True)):
            x, y, w, h = box
            regions.append(
                {
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "text": text,
                    "confidence": 0.97,
                    "orientation": (cfg.get("orientations") or ["horizontal"] * len(cfg["boxes"]))[
                        i
                    ],
                }
            )
        mapping[_det.file_hash(path)] = regions
    with open(os.path.join(gdir, "readme.txt"), "w") as f:
        f.write("not an image")
    return gdir, mapping
