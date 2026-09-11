"""Worker Kimo: protocolo del Hub + engine según provider del job.

Claves de proveedores (DEEPL_API_KEY...) salen del entorno DEL WORKER.
Nunca viajan en jobs, nunca se registran en logs ni resultados.
TM y terminología se leen de la API Kimo (el worker no abre ficheros de la Pi).
"""

from __future__ import annotations

import os
import time

import httpx

from ..core.logging import setup_logging
from ..engines import UnknownProvider, get_engine
from ..engines.base import TranslationRequest
from ..hub.client import HubClient
from ..knowledge.interfaces import TranslationContext
from ..knowledge.memory import tm_threshold

log = setup_logging()


def request_from_job(job: dict) -> tuple[TranslationRequest, str]:
    m = job.get("metrics") or {}
    req, ctx = m.get("request", {}), m.get("request", {}).get("context", {})
    return TranslationRequest(
        source_text=req.get("text", ""),
        source_lang=req.get("source_lang", "ja"),
        target_lang=req.get("target_lang", "es"),
        context=TranslationContext(
            source_app=ctx.get("source_app", "kimotranslate"),
            content_type=ctx.get("content_type", ""),
            project_id=ctx.get("project_id", ""),
            game_id=ctx.get("game_id", ""),
            speaker=ctx.get("speaker", ""),
            scene=ctx.get("scene", ""),
            domain=ctx.get("domain", "game_translation"),
            provider=ctx.get("provider", "magi"),
            model=ctx.get("model", ""),
            prompt_version=ctx.get("prompt_version", ""),
            extra=ctx.get("extra", {}),
        ),
    ), m.get("kimo_cache_key", job["id"])


def text_to_json(t) -> dict:
    return {
        "id": t.id,
        "file_path": t.file_path,
        "source_text": t.source_text,
        "text_type": t.text_type,
        "speaker": t.speaker,
        "scene": t.scene,
        "position": t.position,
        "original_hash": t.original_hash,
        "encoding": t.encoding,
        "translatable": bool(t.translatable),
        "skip_reason": t.skip_reason,
        "tokens": t.tokens,
        "status": t.status,
        "metadata": t.metadata,
    }


class KimoApi:
    """Lecturas que el worker necesita del server Kimo (TM + terminología)."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0)

    def memory_search(self, **params) -> list:
        return self._client.get("/memory/search", params=params).json()

    def terminology(self, project_id: str = "", game_id: str = "") -> list:
        params = {}
        if project_id:
            params["project_id"] = project_id
        if game_id:
            params["game_id"] = game_id
        return self._client.get("/terminology", params=params).json()

    def get_game(self, game_id: str) -> dict:
        return self._client.get(f"/games/{game_id}").json()

    def bulk_texts(self, game_id: str, texts: list, fileinfo: dict) -> dict:
        return self._client.post(
            f"/games/{game_id}/texts/bulk",
            json={"texts": [text_to_json(t) for t in texts], "fileinfo": fileinfo},
        ).json()

    def export_bundle(self, game_id: str) -> dict:
        return self._client.get(f"/games/{game_id}/export-bundle").json()

    def export_report(self, game_id: str, manifest: dict) -> dict:
        return self._client.post(f"/games/{game_id}/export-report", json=manifest).json()

    def push_game_images(self, game_id: str, assets: list) -> dict:
        return self._client.post(f"/games/{game_id}/images/bulk", json={"assets": assets}).json()

    def image_source(self, image_id: str) -> dict:
        for g in self._client.get("/games").json():
            for a in self._client.get(f"/games/{g['game_id']}/images").json():
                if a["id"] == image_id:
                    return a
        raise KeyError(image_id)

    def push_ocr(
        self, game_id: str, image_id: str, rows: list, engine: str, version: str, ocr_ms: float
    ) -> dict:
        return self._client.post(
            f"/games/{game_id}/images/{image_id}/ocr-result",
            json={
                "regions": [
                    {
                        k: r.get(k)
                        for k in (
                            "x",
                            "y",
                            "w",
                            "h",
                            "polygon",
                            "source_text",
                            "confidence",
                            "orientation",
                        )
                    }
                    | {"region_index": i}
                    for i, r in enumerate(rows)
                ],
                "engine": engine,
                "version": version,
                "ocr_ms": ocr_ms,
            },
        ).json()

    def localize_bundle(self, game_id: str, image_id: str) -> dict:
        return self._client.get(f"/games/{game_id}/images/{image_id}/bundle").json()

    def push_artifacts(
        self,
        game_id: str,
        image_id: str,
        localized_b64: str,
        mask_b64: str,
        report: list,
        renderer_version: str,
        inpaint_version: str,
        original_b64: str = "",
    ) -> dict:
        return self._client.post(
            f"/games/{game_id}/images/{image_id}/artifacts",
            json={
                "localized_b64": localized_b64,
                "mask_b64": mask_b64,
                "report": report,
                "renderer_version": renderer_version,
                "inpaint_version": inpaint_version,
                "original_b64": original_b64,
            },
        ).json()

    def game_images_export_list(self, game_id: str) -> dict:
        return self._client.get(f"/games/{game_id}/images/export-list").json()


class KimoWorker:
    def __init__(
        self,
        hub: HubClient,
        worker_id: str,
        engine=None,
        kimo_url: str = "",
        engine_factory=get_engine,
        kimo_api=None,
        ocr_engine=None,
    ) -> None:
        self.hub = hub
        self.worker_id = worker_id
        self.kimo = kimo_api or KimoApi(
            kimo_url or os.environ.get("KIMOTRANSLATE_SERVER_URL", "http://127.0.0.1:8005")
        )
        self.engine = engine  # instancia fija (tests) o None -> factory por provider
        self.engine_factory = engine_factory
        self.ocr_engine = ocr_engine  # instancia fija (tests) o None -> get_ocr_engine

    def run_once(self, types: str = "translation") -> dict | None:
        self.hub.heartbeat(self.worker_id)
        job = self.hub.claim(self.worker_id, types=types)
        if job is None:
            return None
        log.info("claimed %s", job["id"])
        try:
            kind = (job.get("metrics") or {}).get("kimo_job_type", "TRANSLATE_TEXT")
            if kind == "EXTRACT_GAME":
                from ..games import worker_ops as game_ops

                return game_ops.extract_game(self.hub, self.kimo, job)
            if kind == "EXPORT_GAME":
                from ..games import worker_ops as game_ops

                return game_ops.export_game(self.hub, self.kimo, job)
            if kind == "OCR_IMAGE":
                from ..images import worker_ops as img_ops

                return img_ops.ocr_image(
                    self.hub, self.kimo, job, engine=getattr(self, "ocr_engine", None)
                )
            if kind == "LOCALIZE_IMAGE":
                from ..images import worker_ops as img_ops

                return img_ops.localize_image(self.hub, self.kimo, job)
            return self._do(job)
        except UnknownProvider as e:
            return self.hub.result(job["id"], False, error=str(e)[:500])
        except Exception as e:  # noqa: BLE001 - el fallo va al Hub, no al log
            return self.hub.result(job["id"], False, error=str(e)[:500])

    def _do(self, job: dict) -> dict:
        request, cache_key = request_from_job(job)
        ctx = request.context
        terms = self._terms(ctx.project_id, ctx.game_id)
        cands = self._candidates(request, ctx)
        if cands and cands[0]["score"] >= tm_threshold():
            best = cands[0]
            return self._finish(
                job,
                cache_key,
                best["translation"],
                ctx.provider or "magi",
                model="",
                memory_hit=True,
                confidence=best.get("confidence"),
            )
        engine = self.engine or self.engine_factory(ctx.provider or "magi")
        res = engine.translate(request, glossary=terms, examples=cands)
        return self._finish(
            job,
            cache_key,
            res.translation,
            res.provider,
            res.model,
            memory_hit=False,
            confidence=res.confidence,
            prompt_version=res.prompt_version,
            duration_s=res.duration_s,
            terms=len(terms),
        )

    def _terms(self, project_id: str, game_id: str) -> list:
        try:
            rows = self.kimo.terminology(project_id, game_id)
            return [{"term": r["term"], "preferred": r["preferred"]} for r in rows]
        except Exception:  # noqa: BLE001 - sin terminología se traduce igual
            return []

    def _candidates(self, request: TranslationRequest, ctx) -> list:
        try:
            return self.kimo.memory_search(
                query=request.source_text,
                domain=ctx.domain or "game_translation",
                content_type=ctx.content_type,
                project_id=ctx.project_id,
                game_id=ctx.game_id,
                limit=3,
            )
        except Exception:  # noqa: BLE001
            return []

    def _finish(
        self,
        job: dict,
        cache_key: str,
        translation: str,
        provider: str,
        model: str = "",
        memory_hit: bool = False,
        confidence=None,
        prompt_version: str = "",
        duration_s: float = 0.0,
        terms: int = 0,
    ) -> dict:
        return self.hub.result(
            job["id"],
            True,
            metrics={
                **(job.get("metrics") or {}),
                "translation": translation,
                "provider": provider,
                "model": model,
                "confidence": confidence,
                "memory_hit": memory_hit,
                "prompt_version": prompt_version,
                "duration_s": duration_s,
                "terms_applied": terms,
                "kimo_cache_key": cache_key,
            },
        )

    def run_forever(self, interval_s: int = 10) -> None:
        while True:
            try:
                self.run_once()
            except Exception as e:  # noqa: BLE001 - reintento en interval_s
                log.warning("worker loop: %s", e)
            time.sleep(interval_s)


def main() -> None:
    worker = KimoWorker(
        HubClient(base_url=os.environ.get("KIMOTRANSLATE_HUB_URL", "http://127.0.0.1:8080")),
        worker_id=os.environ.get("KIMOTRANSLATE_WORKER_ID", "kimo-worker"),
    )
    worker.run_forever()


if __name__ == "__main__":
    main()
