"""Orquestación por imagen. Reutiliza TODO el pipeline de texto.

El OCR solo aporta (texto, bbox, confianza); la traducción es el
TranslationService existente (cache scope=game, TM, terminología).
"""

from __future__ import annotations

import time

from ..games import tokens as game_tokens
from . import mask as mask_mod
from . import regions as regions_mod
from .inpaint import SimpleInpainter
from .models import OcrResult
from .renderer import render_region


def to_rows(image_id: str, result: OcrResult) -> list[dict]:
    """OcrResult -> filas de región con IDs deterministas + orden + grupos."""
    rows = []
    for i, r in enumerate(result.regions):
        text = (r.text or "").strip()
        rows.append(
            {
                "id": f"{image_id}:r{i}",
                "image_id": image_id,
                "region_index": i,
                "x": r.x,
                "y": r.y,
                "w": r.w,
                "h": r.h,
                "polygon": r.polygon,
                "source_text": text,
                "confidence": r.confidence,
                "language": "ja",
                "orientation": r.orientation,
                "reading_order": i,
                "group_id": "",
                "text_type": "dialogue",
                "translatable": bool(text),
                "status": "EXTRACTED" if text else "SKIPPED",
                "skip_reason": "" if text else "empty-ocr",
                "tokens": game_tokens.find_tokens(text),
            }
        )
    regions_mod.reading_order(rows)
    regions_mod.group_regions(rows)
    return rows


def neighbors(rows: list[dict], row: dict) -> tuple[str, str]:
    ordered = sorted(rows, key=lambda r: r["reading_order"])
    idx = ordered.index(row)
    prev = ordered[idx - 1]["source_text"] if idx > 0 else ""
    nxt = ordered[idx + 1]["source_text"] if idx + 1 < len(ordered) else ""
    return prev, nxt


def eligible(rows: list[dict]) -> list[tuple[dict, str]]:
    """(región, final) con traducción válida y tokens ok. Sin DELETED."""
    out = []
    for r in [r for r in rows if r.get("status") != "DELETED"]:
        final = r.get("corrected_translation") or r.get("machine_translation") or ""
        if r.get("translatable") and final and game_tokens.tokens_ok(r["source_text"], final):
            out.append((r, final))
    return out


def localize(
    image, rows: list[dict], style: dict | None = None, padding: int = 2, mask=None
) -> tuple[object, object, list[dict]]:
    """Devuelve (localized, mask, report[{region_id, fit, missing}]).
    mask explícita (editor manual) o automática sobre elegibles."""
    style = style or {}
    finals = eligible(rows)
    paintable = [r for r, _ in finals]
    if mask is None:
        mask = mask_mod.make_mask(image.width, image.height, paintable, padding)
    inpaint_ms, render_ms = 0.0, 0.0
    t0 = time.time()
    background = SimpleInpainter().inpaint(image, mask)
    inpaint_ms = (time.time() - t0) * 1000
    report, localized = [], background
    t2 = time.time()
    for r, final in finals:
        localized, fit, missing = render_region(localized, r, final, style)
        report.append({"region_id": r["id"], "fit": fit, "missing": missing, "used": final})
    render_ms = (time.time() - t2) * 1000
    total_ms = (time.time() - t0) * 1000
    return (
        localized,
        mask,
        [{"region_id": x["region_id"], "fit": x["fit"], "missing": x["missing"]} for x in report]
        + [
            {
                "timings_ms": {
                    "inpaint": round(inpaint_ms, 1),
                    "render": round(render_ms, 1),
                    "total": round(total_ms, 1),
                }
            }
        ],
    )
