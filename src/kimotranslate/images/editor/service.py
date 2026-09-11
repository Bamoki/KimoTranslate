"""EditorService: estado, operaciones con historial, dirty flags, preview,
validación y rollback. Metadata por API; píxeles solo donde ya existen
(pipeline Fase 6)."""

from __future__ import annotations

import hashlib
import json

from . import operations as ops
from .history import EditHistory
from .models import (
    CREATE,
    DELETE,
    EDIT_OCR,
    EDIT_TRANSLATION,
    MASK_STROKE,
    MOVE,
    RESIZE,
    SET_STYLE,
    VALIDATE_REGION,
)

RENDER_FIELDS = ("machine_translation", "corrected_translation", "x", "y", "w", "h", "style")


def _region_hash(r: dict) -> str:
    final = r.get("corrected_translation") or r.get("machine_translation") or ""
    blob = "|".join(
        [
            final,
            str(r.get("x")),
            str(r.get("y")),
            str(r.get("w")),
            str(r.get("h")),
            json.dumps(r.get("style", {}), sort_keys=True),
        ]
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def snapshot_render_state(images, image_id: str, editor_version: str = "img-editor@1") -> None:
    asset = images.get_asset(image_id)
    manifest = (asset["manifest"] if asset else {}) or {}
    manifest["render_state"] = {r["id"]: _region_hash(r) for r in images.list_regions(image_id)}
    manifest["inpainted_mask"] = manifest.get("mask_version", 0)
    manifest["editor_version"] = editor_version
    images.set_asset(image_id, manifest=manifest)


class EditorService:
    EDITOR_VERSION = "img-editor@1"

    def __init__(
        self, images, corrections, data_dir: str, history: EditHistory | None = None
    ) -> None:
        self.images = images  # ImageStore
        self.corrections = corrections  # CorrectionService
        self.data_dir = data_dir
        self.history = history or EditHistory(images._db, images._lock)

    # --- estado ---
    def state(self, image_id: str) -> dict:
        asset = self._need(image_id)
        regions = self.images.list_regions(image_id)
        manifest = asset["manifest"] or {}
        rendered = manifest.get("render_state") or {}
        dirty = {
            "translation_dirty": False,
            "mask_dirty": bool(manifest.get("mask_modified")),
            "render_dirty": False,
            "ocr_dirty": False,
        }
        for r in regions:
            if rendered.get(r["id"]) != _region_hash(r):
                dirty["translation_dirty"] = dirty["render_dirty"] = True
            if r["status"] in ("QUEUED", "EXTRACTED"):
                dirty["ocr_dirty"] = True
        inpaint_dirty = dirty["mask_dirty"] or manifest.get("mask_version") != manifest.get(
            "inpainted_mask"
        )
        return {
            "asset": asset,
            "regions": regions,
            "dirty": {**dirty, "inpaint_dirty": inpaint_dirty},
            "editor_version": self.EDITOR_VERSION,
            "history": [
                {"id": o.id, "op_type": o.op_type, "target_id": o.target_id, "undone": o.undone}
                for o in self.history.log(image_id, 20)
            ],
        }

    # --- operaciones geométricas ---
    def move_region(self, image_id: str, region_id: str, x: int, y: int) -> dict:
        r = self._region(image_id, region_id)
        before, after = ops.move(r, x, y)
        self.images.set_region(region_id, **after)
        self.history.record(image_id, MOVE, region_id, before, after)
        return self._region(image_id, region_id)

    def resize_region(self, image_id: str, region_id: str, x: int, y: int, w: int, h: int) -> dict:
        r = self._region(image_id, region_id)
        before, after = ops.resize(r, x, y, w, h)
        self.images.set_region(region_id, **after)
        self.history.record(image_id, RESIZE, region_id, before, after)
        return self._region(image_id, region_id)

    def create_region(self, image_id: str, x: int, y: int, w: int, h: int) -> dict:
        self._need(image_id)
        ops._check_box(x, y, w, h)
        existing = self.images.list_regions(image_id)
        rid = ops.node_id(image_id, [r["id"] for r in existing])
        idx = max([r["region_index"] for r in existing] + [-1]) + 1
        row = self.images.add_region(
            image_id,
            {
                "id": rid,
                "region_index": idx,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "status": "REVIEW_REQUIRED",
            },
        )
        self.history.record(image_id, CREATE, rid, {}, {"id": rid})
        return row

    def delete_region(self, image_id: str, region_id: str) -> dict:
        r = self._region(image_id, region_id)
        snapshot = {
            k: r.get(k)
            for k in (
                "x",
                "y",
                "w",
                "h",
                "source_text",
                "machine_translation",
                "corrected_translation",
                "status",
                "style",
                "polygon",
            )
        }
        self.images.set_region(region_id, status="DELETED")
        self.history.record(image_id, DELETE, region_id, snapshot, {"status": "DELETED"})
        return {"id": region_id, "status": "DELETED"}

    # --- texto ---
    def edit_ocr(self, image_id: str, region_id: str, text: str) -> dict:
        r = self._region(image_id, region_id)
        before = {"source_text": r["source_text"], "status": r["status"]}
        after = {
            "source_text": text,
            "status": "TRANSLATION_PENDING",
            "machine_translation": "",
            "job_id": "",
        }
        self.images.set_region(region_id, **after)
        self.history.record(image_id, EDIT_OCR, region_id, before, after)
        return self._region(image_id, region_id)

    def edit_translation(
        self, image_id: str, region_id: str, translation: str, reviewer: str = ""
    ) -> dict:
        """Guarda working copy + Correction (Fase 4). Avisos de tokens, no bloqueo."""
        r = self._region(image_id, region_id)
        warnings = ops.check_translation(r["source_text"], translation)
        before = {"corrected_translation": r["corrected_translation"], "status": r["status"]}
        self.images.set_region(
            region_id, corrected_translation=translation, status="REVIEW_REQUIRED"
        )
        self.corrections.create(
            {
                "source_text": r["source_text"],
                "machine_translation": r["machine_translation"],
                "corrected_translation": translation,
                "source_app": "kimotranslate",
                "content_type": "image_text",
                "domain": "game_translation",
                "project_id": self._need(image_id)["project_id"],
                "game_id": self._need(image_id)["game_id"],
                "reviewer": reviewer,
                "image_region_id": region_id,
            }
        )
        self.history.record(
            image_id,
            EDIT_TRANSLATION,
            region_id,
            before,
            {"corrected_translation": translation, "status": "REVIEW_REQUIRED"},
        )
        out = self._region(image_id, region_id)
        out["warnings"] = warnings
        return out

    def set_style(self, image_id: str, region_id: str, style: dict) -> dict:
        r = self._region(image_id, region_id)
        merged = {**(r.get("style") or {}), **style}
        self.images.set_region(region_id, style=merged)
        self.history.record(
            image_id, SET_STYLE, region_id, {"style": r.get("style") or {}}, {"style": merged}
        )
        return self._region(image_id, region_id)

    # --- máscara manual (strokes vectoriales; rasteriza el pipeline) ---
    def mask_stroke(self, image_id: str, tool: str, x: int, y: int, radius: int) -> dict:
        if tool not in ("add", "erase"):
            raise ops.EditorError("MASK_ERROR: tool add|erase")
        asset = self._need(image_id)
        manifest = asset["manifest"] or {}
        strokes = manifest.get("mask_strokes", [])
        strokes.append({"tool": tool, "x": x, "y": y, "r": max(1, radius)})
        manifest.update(
            {
                "mask_strokes": strokes,
                "mask_source": "manual",
                "mask_modified": True,
                "mask_version": manifest.get("mask_version", 0) + 1,
            }
        )
        self.images.set_asset(image_id, manifest=manifest)
        self.history.record(image_id, MASK_STROKE, "", {}, {"stroke": strokes[-1]})
        return {"mask_strokes": len(strokes), "mask_modified": True}

    def rasterize_mask(self, image_id: str):
        """Automática + strokes manuales. La usa el localize (servidor y worker)."""
        asset = self._need(image_id)
        manifest = asset["manifest"] or {}
        regions = [r for r in self.images.list_regions(image_id) if r["status"] != "DELETED"]
        return rasterize(asset["width"], asset["height"], regions, manifest.get("mask_strokes", []))

    # --- undo/redo/reset ---
    def undo(self, image_id: str) -> dict | None:
        op = self.history.pop_undo(image_id)
        if op is None:
            return None
        self._restore(op, op.before)
        return {"undone": op.op_type, "target_id": op.target_id}

    def redo(self, image_id: str) -> dict | None:
        op = self.history.pop_redo(image_id)
        if op is None:
            return None
        self._restore(op, op.after)
        return {"redone": op.op_type, "target_id": op.target_id}

    def _restore(self, op, snapshot: dict) -> None:
        if op.op_type in (MOVE, RESIZE, SET_STYLE):
            self.images.set_region(
                op.target_id,
                **{k: v for k, v in snapshot.items() if k in ("x", "y", "w", "h", "style")},
            )
        elif op.op_type == EDIT_OCR:
            self.images.set_region(
                op.target_id,
                source_text=snapshot.get("source_text", ""),
                status=snapshot.get("status", "EXTRACTED"),
            )
        elif op.op_type == EDIT_TRANSLATION:
            self.images.set_region(
                op.target_id,
                corrected_translation=snapshot.get("corrected_translation", ""),
                status=snapshot.get("status", "TRANSLATED"),
            )
        elif op.op_type == CREATE:
            if not snapshot:  # undo create -> marcar DELETED
                self.images.set_region(op.target_id, status="DELETED")
            else:
                self.images.set_region(op.target_id, status="EXTRACTED")
        elif op.op_type == DELETE:
            self.images.set_region(
                op.target_id,
                status="TRANSLATED",
                **{
                    k: v
                    for k, v in snapshot.items()
                    if k
                    in (
                        "x",
                        "y",
                        "w",
                        "h",
                        "source_text",
                        "machine_translation",
                        "corrected_translation",
                    )
                },
            )
        elif op.op_type == MASK_STROKE:
            asset = self._need(op.image_id)
            manifest = asset["manifest"] or {}
            strokes = manifest.get("mask_strokes", [])
            if snapshot == {} and strokes:  # undo: quitar último
                strokes = strokes[:-1]
            manifest.update(
                {
                    "mask_strokes": strokes,
                    "mask_modified": bool(strokes),
                    "mask_source": "manual" if strokes else "automatic",
                }
            )
            self.images.set_asset(op.image_id, manifest=manifest)

    def reset_region(self, image_id: str, region_id: str) -> dict:
        """Vuelve al primer estado registrado de la región (o la marca intacta)."""
        ops_log = [
            o
            for o in self.history.log(image_id, 1000)
            if o.target_id == region_id
            and o.op_type in (MOVE, RESIZE, EDIT_OCR, EDIT_TRANSLATION, SET_STYLE)
            and not o.undone
        ]
        if not ops_log:
            return self._region(image_id, region_id)
        first = ops_log[-1]
        self._restore(first, first.before)
        return self._region(image_id, region_id)

    # --- validación ---
    def validate_region(self, image_id: str, region_id: str, reviewer: str = "") -> dict:
        from ...games import tokens as game_tokens
        from ..renderer import default_font_path, missing_glyphs

        r = self._region(image_id, region_id)
        final = r["corrected_translation"] or r["machine_translation"]
        if not final:
            raise ops.EditorError("VALIDATE: región sin traducción")
        if not game_tokens.tokens_ok(r["source_text"], final):
            raise ops.EditorError(f"TOKEN_MISMATCH en {region_id}")
        style = r.get("style") or {}
        missing = missing_glyphs(final, style.get("font_path") or default_font_path())
        if missing:
            raise ops.EditorError(f"GLYPH_MISSING {missing[:5]} en {region_id}")
        # correction vinculada (la última del editor) o creada al vuelo
        corr = self._latest_correction(region_id, r, reviewer)
        done = self.corrections.validate(corr["id"], reviewer)
        self.history.record(
            image_id, VALIDATE_REGION, region_id, {"status": r["status"]}, {"status": "VALIDATED"}
        )
        return {"id": region_id, "status": "VALIDATED", "correction_id": done["id"]}

    def _latest_correction(self, region_id: str, r: dict, reviewer: str) -> dict:
        cands = [
            c
            for c in self.corrections.list(limit=1000)
            if c.get("image_region_id") == region_id and c["status"] != "validated"
        ]
        if cands:
            return cands[0]
        c = self.corrections.create(
            {
                "source_text": r["source_text"],
                "machine_translation": r["machine_translation"],
                "corrected_translation": r["corrected_translation"] or r["machine_translation"],
                "source_app": "kimotranslate",
                "content_type": "image_text",
                "domain": "game_translation",
                "reviewer": reviewer,
                "image_region_id": region_id,
            }
        )
        if c["status"] == "generated":
            c = self.corrections.update(
                c["id"], c["corrected_translation"] or c["machine_translation"]
            )
        return c

    def validate_image(self, image_id: str, reviewer: str = "") -> dict:
        self._need(image_id)
        regions = [
            r
            for r in self.images.list_regions(image_id)
            if r["translatable"] and r["status"] != "DELETED"
        ]
        if not regions:
            raise ops.EditorError("VALIDATE: sin regiones relevantes")
        pending = [r["id"] for r in regions if r["status"] != "VALIDATED"]
        if pending:
            raise ops.EditorError(f"VALIDATE: regiones pendientes {pending[:5]}")
        self.images.set_asset(image_id, localization_status="VALIDATED")
        return {"id": image_id, "status": "VALIDATED", "regions": len(regions)}

    # --- preview + versiones ---
    def snapshot_render_state(self, image_id: str) -> None:
        snapshot_render_state(self.images, image_id, self.EDITOR_VERSION)

    # --- helpers ---
    def _need(self, image_id: str) -> dict:
        asset = self.images.get_asset(image_id)
        if asset is None:
            raise KeyError(image_id)
        return asset

    def _region(self, image_id: str, region_id: str) -> dict:
        for r in self.images.list_regions(image_id):
            if r["id"] == region_id:
                return r
        raise KeyError(region_id)


def rasterize(width: int, height: int, regions: list, strokes: list):
    from PIL import ImageDraw

    from .. import mask as mask_mod

    base = mask_mod.make_mask(width, height, regions)
    if strokes:
        d = ImageDraw.Draw(base)
        for s in strokes:
            box = [s["x"] - s["r"], s["y"] - s["r"], s["x"] + s["r"], s["y"] + s["r"]]
            d.ellipse(box, fill=255 if s["tool"] == "add" else 0)
    return base
