"""Máscaras: bbox/polygon + padding configurable. Solo PIL."""

from __future__ import annotations

MASK_VERSION = "mask-rect@1"


def make_mask(width: int, height: int, regions: list[dict], padding: int = 2) -> object:
    """Devuelve PIL.Image L (255 = inpaint). Solo regiones traducibles."""
    from PIL import Image, ImageDraw

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for r in regions:
        if not r.get("translatable", True):
            continue
        if r.get("polygon"):
            draw.polygon([tuple(p) for p in r["polygon"]], fill=255)
        else:
            x0 = max(0, r["x"] - padding)
            y0 = max(0, r["y"] - padding)
            x1 = min(width, r["x"] + r["w"] + padding)
            y1 = min(height, r["y"] + r["h"] + padding)
            draw.rectangle([x0, y0, x1, y1], fill=255)
    return mask
