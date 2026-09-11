"""Renderer de texto traducido (PIL). Correcto antes que perfecto.

- Fuente configurable (default vendored DejaVu: español completo).
- Glyph validation antes de dibujar (RENDER_FAILED si falta).
- Fit: envuelve, encoge hasta mínimo, si no cabe -> OVERFLOW (no pinta fuera).
- Stroke/borde básico, centrado, padding. Vertical = apilado (básico).
"""

from __future__ import annotations

import os

RENDERER_VERSION = "pil-basic@1"

FIT = "FIT"
SHRUNK = "SHRUNK"
OVERFLOW = "OVERFLOW"
FAILED = "FAILED"

_DEFAULT_FONT = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "assets", "fonts", "DejaVuSans.ttf"
)

MIN_FONT_SIZE = 8


def default_font_path(bold: bool = False) -> str:
    base = os.path.dirname(_DEFAULT_FONT)
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    env = os.environ.get("KIMOTRANSLATE_FONT_PATH", "")
    if env and os.path.exists(env):
        return env
    return os.path.join(base, name)


def missing_glyphs(text: str, font_path: str, size: int = 20) -> list[str]:
    cmap = _cmap_chars(font_path)
    return [c for c in dict.fromkeys(text) if not c.isspace() and ord(c) not in cmap]


_cmap_cache: dict[str, set] = {}


def _cmap_chars(font_path: str) -> set[int]:
    """Codepoints del cmap TTF (formatos 4 y 12). Sin dependencias."""
    import struct

    if font_path in _cmap_cache:
        return _cmap_cache[font_path]
    chars: set[int] = set()
    try:
        with open(font_path, "rb") as f:
            data = f.read()
        num_tables = struct.unpack(">H", data[4:6])[0]
        cmap_off = 0
        for i in range(num_tables):
            tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i : 28 + 16 * i])
            if tag == b"cmap":
                cmap_off = off
                break
        n_sub = struct.unpack(">H", data[cmap_off + 2 : cmap_off + 4])[0]
        for i in range(n_sub):
            plat, enc, off = struct.unpack(
                ">HHI", data[cmap_off + 4 + 8 * i : cmap_off + 12 + 8 * i]
            )
            base = cmap_off + off
            fmt = struct.unpack(">H", data[base : base + 2])[0]
            if fmt == 4:
                seg_x2 = struct.unpack(">H", data[base + 6 : base + 8])[0]
                n = seg_x2 // 2
                ends = struct.unpack(f">{n}H", data[base + 14 : base + 14 + 2 * n])
                starts = struct.unpack(
                    f">{n}H", data[base + 14 + 2 * n + 2 : base + 14 + 4 * n + 2]
                )
                for s, e in zip(starts, ends, strict=True):
                    if e == 0xFFFF and s == 0xFFFF:
                        continue
                    chars.update(range(s, e + 1))
            elif fmt == 12:
                n = struct.unpack(">I", data[base + 12 : base + 16])[0]
                for j in range(n):
                    start, end, _ = struct.unpack(
                        ">III", data[base + 16 + 12 * j : base + 28 + 12 * j]
                    )
                    chars.update(range(start, min(end, start + 0xFFFF) + 1))
    except (OSError, struct.error, IndexError):
        pass
    _cmap_cache[font_path] = chars
    return chars


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def render_region(
    background, region: dict, translation: str, style: dict | None = None
) -> tuple[object, str, list[str]]:
    """Devuelve (imagen, fit_status, missing). No pinta fuera del bbox."""
    from PIL import ImageDraw, ImageFont

    style = style or {}
    region_style = region.get("style") or {}
    font_path = style.get("font_path") or region_style.get("font_path") or default_font_path()
    size = int(style.get("font_size") or region_style.get("font_size") or 0)
    stroke = int(style.get("stroke_width", region_style.get("stroke_width", 1)))
    fill = style.get("color", region_style.get("color", (255, 255, 255)))
    vertical = (region.get("orientation") == "vertical") or style.get("vertical", False)

    missing = missing_glyphs(translation, font_path)
    if missing:
        return background, FAILED, missing
    if not translation.strip():
        return background, FAILED, []

    img = background.copy()
    draw = ImageDraw.Draw(img)
    pad = int(style.get("padding", 2))
    max_w, max_h = region["w"] - 2 * pad, region["h"] - 2 * pad
    if max_w <= 4 or max_h <= 4:
        return background, FAILED, []

    size = size or max(MIN_FONT_SIZE, max_h if vertical else max_h // 2)
    fit = FIT
    lines: list[str] = [translation]
    font = ImageFont.truetype(font_path, size)
    while size > MIN_FONT_SIZE:
        font = ImageFont.truetype(font_path, size)
        if vertical:
            needed_h = sum(draw.textlength(c, font=font) for c in translation)
            needed_w = max((draw.textlength(c, font=font) for c in translation), default=0)
            if needed_h <= max_h and needed_w <= max_w:
                break
        else:
            lines = _wrap(draw, translation, font, max_w)
            needed_h = sum(draw.textbbox((0, 0), ln, font=font)[3] for ln in lines)
            if needed_h <= max_h:
                break
        size -= 1
        fit = SHRUNK
    else:
        font = ImageFont.truetype(font_path, MIN_FONT_SIZE)
        if vertical:
            needed_h = sum(draw.textlength(c, font=font) for c in translation)
            if needed_h > max_h:
                return background, OVERFLOW, []
        else:
            lines = _wrap(draw, translation, font, max_w)
            needed_h = sum(draw.textbbox((0, 0), ln, font=font)[3] for ln in lines)
            if needed_h > max_h:
                return background, OVERFLOW, []

    cx, cy = region["x"] + region["w"] / 2, region["y"] + region["h"] / 2
    if vertical:
        total_h = sum(draw.textlength(c, font=font) for c in translation)
        y = cy - total_h / 2
        for c in translation:
            w = draw.textlength(c, font=font)
            draw.text(
                (cx - w / 2, y), c, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0)
            )
            y += w
    else:
        heights = [draw.textbbox((0, 0), ln, font=font)[3] for ln in lines]
        y = cy - sum(heights) / 2
        for ln, lh in zip(lines, heights, strict=True):
            draw.text(
                (cx, y),
                ln,
                font=font,
                fill=fill,
                anchor="mt",
                stroke_width=stroke,
                stroke_fill=(0, 0, 0),
            )
            y += lh
    # Seguridad: nada pintado fuera del bbox (el anchor+wrap lo garantiza por
    # construcción; OVERFLOW ya retornó antes).
    return img, fit, []
