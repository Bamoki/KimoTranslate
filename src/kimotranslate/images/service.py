"""Servicio de imágenes en el servidor: descubre, ingiere OCR, traduce vía
pipeline existente, sincroniza jobs, localiza en local (dev) y exporta.
Lo pesado remoto lo hace el worker con jobs del Hub (mismo código vía API).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os

from ..engines.base import TranslationRequest
from ..games import tokens as game_tokens
from ..knowledge.interfaces import TranslationContext
from . import cache as img_cache
from . import detector
from . import pipeline as img_pipeline
from .inpaint import INPAINT_VERSION
from .models import AssetStatus
from .renderer import RENDERER_VERSION

CONTENT_TYPE = "image_text"


def image_id_for(game_id: str, relpath: str, file_hash: str) -> str:
    return f"img:{game_id}:{hashlib.sha1(f'{relpath}:{file_hash}'.encode()).hexdigest()[:12]}"


class ImageService:
    def __init__(self, images, hub, translate, data_dir: str) -> None:
        self.images = images  # ImageStore
        self.hub = hub
        self.translate = translate  # TranslationService
        self.data_dir = data_dir

    # --- discovery ---
    def discover_local(self, game_id: str, game_path: str, project_id: str = "") -> dict:
        found, kept = 0, 0
        for a in detector.discover(game_path):
            found += 1
            iid = image_id_for(game_id, a["relpath"], a["original_hash"])
            self.images.upsert_asset(
                {
                    "id": iid,
                    "game_id": game_id,
                    "project_id": project_id,
                    **a,
                    "ocr_status": AssetStatus.DISCOVERED,
                    "localization_status": AssetStatus.DISCOVERED,
                }
            )
            kept += 1
        return {"images_found": found, "images_kept": kept}

    # --- OCR ingest (resultado del worker o local) ---
    def ingest_ocr(self, image_id: str, result: dict, engine: str, version: str) -> dict:
        from .models import OcrRegion, OcrResult

        asset = self._need(image_id)
        regions = []
        for r in result.get("regions", []):
            regions.append(
                OcrRegion(
                    x=r.get("x", 0),
                    y=r.get("y", 0),
                    w=r.get("w", 0),
                    h=r.get("h", 0),
                    text=r.get("text", r.get("source_text", "")),
                    confidence=r.get("confidence"),
                    orientation=r.get("orientation", "horizontal"),
                    polygon=r.get("polygon", []),
                )
            )
        rows = img_pipeline.to_rows(
            image_id,
            OcrResult(
                regions=regions,
                engine=engine,
                version=version,
            ),
        )
        self.images.replace_regions(image_id, rows)
        manifest = asset["manifest"] or {}
        manifest.update({"ocr_engine": engine, "ocr_version": version, "region_count": len(rows)})
        self.images.set_asset(image_id, ocr_status=AssetStatus.OCR_DONE, manifest=manifest)
        self._write_json(
            image_id,
            "ocr.json",
            {
                "image_id": image_id,
                "width": asset["width"],
                "height": asset["height"],
                "engine": engine,
                "regions": rows,
            },
        )
        return {"regions": len(rows)}

    # --- traducción vía pipeline existente ---
    def translate_selection(
        self, image_id: str, region_ids: list[str], provider: str = "magi", model: str = ""
    ) -> dict:
        asset = self._need(image_id)
        rows = self.images.list_regions(image_id)
        if region_ids:
            rows = [r for r in rows if r["id"] in set(region_ids)]
        else:
            rows = [r for r in rows if r["status"] in ("EXTRACTED", "FAILED") and r["translatable"]]
        queued = cached = 0
        for r in rows:
            prev, nxt = img_pipeline.neighbors(self.images.list_regions(image_id), r)
            req = TranslationRequest(
                r["source_text"],
                "ja",
                "es",
                TranslationContext(
                    source_app="kimotranslate",
                    content_type=CONTENT_TYPE,
                    domain="game_translation",
                    project_id=asset["project_id"],
                    game_id=asset["game_id"],
                    scene=asset["relpath"],
                    provider=provider,
                    model=model,
                    extra={
                        "image_id": image_id,
                        "image_region_id": r["id"],
                        "previous_text": prev,
                        "next_text": nxt,
                        "metadata_text_type": r["text_type"],
                    },
                ),
            )
            res = self.translate.submit(req, provider=provider, model=model)
            if res["job_id"]:
                self.images.set_region(r["id"], status="QUEUED", job_id=res["job_id"])
                queued += 1
            else:
                self._apply_result(r, res.get("translation") or "")
                cached += 1
        self.images.set_asset(image_id, ocr_status=AssetStatus.OCR_DONE)
        return {"queued": queued, "cached": cached, "total": len(rows)}

    def sync(self, image_id: str) -> dict:
        done = failed = 0
        for r in self.images.list_regions(image_id):
            if not r["job_id"] or r["status"] != "QUEUED":
                continue
            try:
                job = self.hub.get_job(r["job_id"])
            except Exception:  # noqa: BLE001 - reintento en próximo sync
                continue
            m = job.get("metrics") or {}
            if job.get("status") == "COMPLETED" and m.get("translation"):
                self._apply_result(r, m["translation"])
                done += 1
            elif job.get("status") == "FAILED":
                self.images.set_region(r["id"], status="FAILED")
                failed += 1
        return {"synced": done, "failed": failed}

    def _apply_result(self, r: dict, translation: str) -> None:
        if game_tokens.tokens_ok(r["source_text"], translation):
            self.images.set_region(r["id"], machine_translation=translation, status="TRANSLATED")
        else:
            self.images.set_region(
                r["id"], machine_translation=translation, status="REVIEW_REQUIRED"
            )

    # --- bundle/localize (worker o local) ---
    def localize_bundle(self, image_id: str) -> dict:
        asset = self._need(image_id)
        rows = [r for r in self.images.list_regions(image_id) if r["status"] != "DELETED"]
        finals = []
        for r in rows:
            final = r["corrected_translation"] or r["machine_translation"]
            if r["translatable"] and final and game_tokens.tokens_ok(r["source_text"], final):
                finals.append({"region_id": r["id"], "final": final})
        with open(asset["file_path"], "rb") as f:
            original_b64 = base64.b64encode(f.read()).decode()
        manifest = asset["manifest"] or {}
        return {
            "asset": asset,
            "regions": rows,
            "finals": finals,
            "original_b64": original_b64,
            "mask_strokes": manifest.get("mask_strokes", []),
        }

    def localize_local(self, image_id: str, style: dict | None = None) -> dict:
        from PIL import Image

        bundle = self.localize_bundle(image_id)
        image = Image.open(io.BytesIO(base64.b64decode(bundle["original_b64"]))).convert("RGB")
        rows = [r for r in bundle["regions"]]
        from .editor.service import rasterize

        manifest0 = bundle["asset"]["manifest"] or {}
        eligible_rows = [r for r, _ in img_pipeline.eligible(rows)]
        mask = rasterize(
            image.width, image.height, eligible_rows, manifest0.get("mask_strokes", [])
        )
        localized, mask, report = img_pipeline.localize(image, rows, style, mask=mask)
        base = img_cache.artifact_dir(self.data_dir, image_id)
        image.save(os.path.join(base, "original.png"))
        self._save_versioned_pil(base, "localized.png", localized)
        self._save_versioned_pil(base, "mask.png", mask)
        self._write_json(
            image_id,
            "translation.json",
            {
                "image_id": image_id,
                "translations": [
                    {
                        "region_id": r["id"],
                        "source": r["source_text"],
                        "translation": r["corrected_translation"] or r["machine_translation"],
                        "status": r["status"],
                    }
                    for r in rows
                ],
            },
        )
        fits = [x.get("fit") for x in report if x.get("region_id")]
        failed = [x for x in fits if x in ("OVERFLOW", "FAILED")]
        status = AssetStatus.LOCALIZED if not failed and fits else AssetStatus.FAILED
        manifest = (bundle["asset"]["manifest"] or {}) | {
            "renderer_version": RENDERER_VERSION,
            "inpaint_version": INPAINT_VERSION,
            "region_count": len(rows),
            "report": report,
            "cache_key": img_cache.image_key(
                bundle["asset"]["original_hash"],
                bundle["asset"]["ocr_engine"],
                bundle["asset"].get("manifest", {}).get("ocr_version", ""),
                "",
                img_cache.translations_blob(
                    [
                        (r["id"], r["corrected_translation"] or r["machine_translation"])
                        for r in rows
                    ]
                ),
                RENDERER_VERSION,
                INPAINT_VERSION,
            ),
        }
        self._write_json(image_id, "manifest.json", manifest)
        self.images.set_asset(image_id, localization_status=status, manifest=manifest)
        if status == "LOCALIZED":
            from .editor.service import snapshot_render_state

            snapshot_render_state(self.images, image_id)
        return {"status": status, "report": report, "artifacts": base}

    @staticmethod
    def _save_versioned_pil(base: str, name: str, image) -> None:
        import io as _io

        from . import cache as _cache

        buf = _io.BytesIO()
        image.save(buf, format="PNG")
        _cache.write_versioned(base, name, buf.getvalue())

    def _write_json(self, image_id: str, name: str, data: dict) -> str:
        path = os.path.join(img_cache.artifact_dir(self.data_dir, image_id), name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return path

    def _need(self, image_id: str) -> dict:
        asset = self.images.get_asset(image_id)
        if asset is None:
            raise KeyError(image_id)
        return asset
