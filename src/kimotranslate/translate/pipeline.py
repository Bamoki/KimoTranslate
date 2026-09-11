"""Pipeline: exact cache -> TM -> Hub job -> resultado -> cache write.

El job vive en el Hub; aquí solo lógica de traducción.
"""

from __future__ import annotations

import uuid

from ..db.repository import CacheStore
from ..engines.base import TranslationRequest
from ..hub.client import HubClient
from ..jobs.types import JobType
from .cache import cache_key, normalize


class TranslationService:
    def __init__(self, cache: CacheStore, hub: HubClient, memory=None) -> None:
        self.cache = cache
        self.hub = hub
        self.memory = memory  # TranslationMemory o None

    def submit(
        self,
        request: TranslationRequest,
        provider: str = "magi",
        model: str = "",
        prompt_version: str = "",
    ) -> dict:
        """HIT exacto o TM reutilizable -> traducción inmediata.
        Si no, job en el Hub (el worker traduce)."""
        ctx = request.context
        domain = ctx.domain or "game_translation"
        key = cache_key(
            request.source_text,
            request.source_lang,
            request.target_lang,
            provider,
            model,
            prompt_version,
            domain,
            ctx.content_type,
            ctx.game_id or ctx.project_id,
        )
        hit = self.cache.cache_get(key)
        if hit:
            return {
                "translation": hit["translation"],
                "cached": True,
                "memory_hit": False,
                "job_id": None,
                "status": "COMPLETED",
                "provider": provider,
                "model": model,
                "key": key,
            }
        reusable = self._tm_reusable(request, domain)
        if reusable:
            return {
                "translation": reusable["translation"],
                "cached": False,
                "memory_hit": True,
                "job_id": None,
                "status": "COMPLETED",
                "provider": provider,
                "model": model,
                "key": key,
            }
        job_id = f"kimo-{uuid.uuid4().hex[:12]}"
        job = self.hub.create_translation_job(
            job_id,
            f"[{JobType.TRANSLATE_TEXT.value}] "
            f"{request.source_lang}->{request.target_lang} {normalize(request.source_text)[:60]}",
            base_model=model or "qwen2.5:7b",
            metrics={
                "kimo_job_type": JobType.TRANSLATE_TEXT.value,
                "kimo_cache_key": key,
                "request": {
                    "text": request.source_text,
                    "source_lang": request.source_lang,
                    "target_lang": request.target_lang,
                    "context": {
                        "source_app": ctx.source_app,
                        "content_type": ctx.content_type,
                        "domain": domain,
                        "project_id": ctx.project_id,
                        "game_id": ctx.game_id,
                        "speaker": ctx.speaker,
                        "scene": ctx.scene,
                        "provider": provider,
                        "model": model,
                        "prompt_version": prompt_version,
                        "extra": ctx.extra,
                    },
                },
            },
        )
        return {
            "translation": None,
            "cached": False,
            "memory_hit": False,
            "job_id": job["id"],
            "status": job["status"],
            "provider": provider,
            "model": model,
            "key": key,
        }

    def _tm_reusable(self, request: TranslationRequest, domain: str) -> dict | None:
        if self.memory is None:
            return None
        return self.memory.find_reusable(
            query=request.source_text,
            domain=domain,
            content_type=request.context.content_type,
            project_id=request.context.project_id,
            game_id=request.context.game_id,
        )

    def job_result(self, job_id: str) -> dict:
        """Lee el job del Hub; si COMPLETED con traducción, escribe cache (lazy write)."""
        job = self.hub.get_job(job_id)
        metrics = job.get("metrics") or {}
        out = {
            "job_id": job_id,
            "status": job.get("status"),
            "translation": metrics.get("translation"),
            "cached": False,
            "memory_hit": bool(metrics.get("memory_hit")),
            "provider": metrics.get("provider"),
            "model": metrics.get("model"),
            "error": job.get("error"),
        }
        if job.get("status") == "COMPLETED" and metrics.get("translation"):
            req = metrics.get("request", {})
            rctx = req.get("context", {})
            self.cache.cache_put(
                {
                    "key": metrics.get("kimo_cache_key", job_id),
                    "source_text": req.get("text", ""),
                    "translation": metrics["translation"],
                    "source_lang": req.get("source_lang", "ja"),
                    "target_lang": req.get("target_lang", "es"),
                    "provider": metrics.get("provider", "magi"),
                    "model": metrics.get("model", ""),
                    "prompt_version": metrics.get("prompt_version", ""),
                    "content_type": rctx.get("content_type", ""),
                    "domain": rctx.get("domain", ""),
                    "quality": metrics.get("confidence"),
                    "human_verified": 0,
                }
            )
            out["cached"] = True  # a partir de ahora es HIT
        return out
