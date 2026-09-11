"""Operaciones pesadas de imágenes en el WORKER. Orquestadas por el Hub."""

from __future__ import annotations

import base64
import io
import os
import time
import uuid

from ..jobs.types import JobType
from . import pipeline as img_pipeline
from .inpaint import INPAINT_VERSION
from .ocr.base import ImageOcrEngine
from .renderer import RENDERER_VERSION


def get_ocr_engine(name: str = "", **kwargs) -> ImageOcrEngine:
    name = (name or os.environ.get("KIMOTRANSLATE_OCR_ENGINE", "mock")).lower()
    if name == "tradujap":
        from .ocr.tradujap_adapter import TradujapOcrEngine

        return TradujapOcrEngine(**kwargs)
    from .ocr.mock import MockOcrEngine

    return MockOcrEngine(**kwargs)


def create_ocr_job(hub, image_id: str, game_id: str, engine: str = "") -> dict:
    job_id = f"kimo-{uuid.uuid4().hex[:12]}"
    return hub.create_job(
        job_id,
        f"[{JobType.OCR_IMAGE.value}] {image_id}",
        "translation",
        {
            "kimo_job_type": JobType.OCR_IMAGE.value,
            "image_id": image_id,
            "game_id": game_id,
            "engine": engine,
        },
    )


def create_localize_job(hub, image_id: str, game_id: str) -> dict:
    job_id = f"kimo-{uuid.uuid4().hex[:12]}"
    return hub.create_job(
        job_id,
        f"[{JobType.LOCALIZE_IMAGE.value}] {image_id}",
        "translation",
        {"kimo_job_type": JobType.LOCALIZE_IMAGE.value, "image_id": image_id, "game_id": game_id},
    )


def ocr_image(hub, kimo, job: dict, engine=None) -> dict:
    """OCR_IMAGE: OCR en local (worker) + push de regiones a la API."""
    import time as _t

    m = job.get("metrics") or {}
    image_id, game_id = m["image_id"], m["game_id"]
    engine = engine or get_ocr_engine(m.get("engine", ""))
    path = m.get("file_path") or kimo.image_source(image_id)["file_path"]
    t0 = _t.time()
    result = engine.detect_text(path)
    ocr_ms = (_t.time() - t0) * 1000
    rows = img_pipeline.to_rows(image_id, result)
    res = kimo.push_ocr(game_id, image_id, rows, result.engine, result.version, ocr_ms)
    return hub.result(job["id"], True, metrics={**m, **res, "ocr_ms": round(ocr_ms, 1)})


def localize_image(hub, kimo, job: dict, style: dict | None = None) -> dict:
    """LOCALIZE_IMAGE: baja bundle, localiza en local, sube artefactos."""
    m = job.get("metrics") or {}
    game_id, image_id = m["game_id"], m["image_id"]
    bundle = kimo.localize_bundle(game_id, image_id)
    from PIL import Image

    from .editor.service import rasterize

    image = Image.open(io.BytesIO(base64.b64decode(bundle["original_b64"]))).convert("RGB")
    eligible_rows = [r for r, _ in img_pipeline.eligible(bundle["regions"])]
    mask = rasterize(image.width, image.height, eligible_rows, bundle.get("mask_strokes", []))
    t0 = time.time()
    localized, mask, report = img_pipeline.localize(image, bundle["regions"], style, mask=mask)
    total_ms = round((time.time() - t0) * 1000, 1)
    buf = io.BytesIO()
    localized.save(buf, format="PNG")
    mbuf = io.BytesIO()
    mask.save(mbuf, format="PNG")
    res = kimo.push_artifacts(
        game_id,
        image_id,
        base64.b64encode(buf.getvalue()).decode(),
        base64.b64encode(mbuf.getvalue()).decode(),
        report,
        RENDERER_VERSION,
        INPAINT_VERSION,
        bundle["original_b64"],
    )
    return hub.result(job["id"], True, metrics={**m, **res, "total_ms": total_ms})


def export_images_for_game(kimo, game_id: str, source_path: str, output_path: str) -> dict:
    """Worker: baja localized_b64, verifica contra originales locales, escribe árbol."""
    import base64
    import io
    import os
    import shutil

    from .exporter import FAIL, quality_checks_pil

    data = kimo.game_images_export_list(game_id)
    localized_dir = os.path.join(output_path, "localized")
    backup_dir = os.path.join(output_path, "backup")
    exported, failed = [], []
    for it in data["items"]:
        rel = it["relpath"]
        try:
            from PIL import Image

            loc = Image.open(io.BytesIO(base64.b64decode(it["localized_b64"]))).convert("RGB")
            orig_path = os.path.join(source_path, rel)
            with Image.open(orig_path) as o:
                o.load()
                orig = o.convert("RGB")
            checks = quality_checks_pil(orig, loc, it.get("regions", []))
        except Exception as e:  # noqa: BLE001
            failed.append({"file": rel, "reason": str(e)[:200]})
            continue
        if any(c["result"] == FAIL for c in checks):
            failed.append(
                {
                    "file": rel,
                    "reason": "checks",
                    "checks": [c["check"] for c in checks if c["result"] == FAIL],
                }
            )
            continue
        dst = os.path.join(localized_dir, rel)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        bkp = os.path.join(backup_dir, rel)
        os.makedirs(os.path.dirname(bkp) or ".", exist_ok=True)
        if not os.path.exists(bkp):
            shutil.copy2(orig_path, bkp)
        tmp = dst + ".tmp"
        loc.save(tmp, format="PNG")
        os.replace(tmp, dst)
        exported.append({"file": rel})
    return {
        "exported": exported,
        "failed": failed,
        "exported_count": len(exported),
        "failed_count": len(failed),
    }
