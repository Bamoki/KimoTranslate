"""Orquestación de juegos en el servidor: registro, extracción local,
traducción vía pipeline existente, sync de resultados, bundle de export.

El trabajo pesado con ficheros remotos (Windows) lo hace el worker vía jobs
del Hub; este servicio corre lo mismo en local (Pi/dev) y guarda resultados.
"""

from __future__ import annotations

import hashlib
import os

from ..translate.pipeline import TranslationService
from . import tokens as game_tokens
from .engines import clockup
from .models import GameStats, TextStatus, TextType

CONTENT_BY_TYPE = {
    TextType.DIALOGUE: "vn_dialogue",
    TextType.NARRATION: "vn_dialogue",
    TextType.CHOICE: "game_ui",
    TextType.SYSTEM: "game_ui",
    TextType.UI: "game_ui",
    TextType.TITLE: "game_ui",
    TextType.UNKNOWN: "game_ui",
}


def game_hash(fileinfo: dict) -> str:
    h = hashlib.sha256()
    for rel in sorted(fileinfo):
        h.update(f"{rel}:{fileinfo[rel].get('sha', '')}".encode())
    return h.hexdigest()[:16]


class GameService:
    def __init__(self, games, hub, translate: TranslationService) -> None:
        self.games = games  # GameStore
        self.hub = hub  # HubClient
        self.translate = translate

    # --- registro + detección ---
    def register(self, source_path: str, name: str = "", game_id: str = "") -> dict:
        from ..db.sqlite import utcnow

        game_id = game_id or os.path.basename(os.path.normpath(source_path)).lower()
        det = clockup.detect(source_path)
        manifest = {
            "game_id": game_id,
            "name": name or game_id,
            "source_path": source_path,
            "detected_engine": det.engine,
            "engine_version": det.version,
            "extractor_version": clockup.EXTRACTOR_VERSION,
            "exporter_version": clockup.EXPORTER_VERSION,
            "created_at": utcnow(),
            "manifest": {"evidence": list(det.evidence)},
        }
        return self.games.upsert_game(manifest)

    # --- extracción (local o resultado del worker vía merge_result) ---
    def extract_local(self, game_id: str) -> dict:
        game = self._need(game_id)
        if game["detected_engine"] != clockup.ENGINE:
            raise ValueError(f"engine {game['detected_engine']} not supported")
        manifest = game["manifest"] or {}
        hints = {f["relpath"]: f for f in manifest.get("files", [])}
        texts, fileinfo = clockup.extract(game_id, game["source_path"], hints)
        return self.merge_result(game_id, texts, fileinfo)

    def merge_result(self, game_id: str, texts: list, fileinfo: dict) -> dict:
        """Upsert de textos (worker o local): NEW/CHANGED/UNCHANGED/REMOVED."""
        from ..db.sqlite import utcnow

        game = self._need(game_id)
        rows = [self._row(t) for t in texts]
        stats = self.games.merge_texts(game_id, rows)
        manifest = game["manifest"] or {}
        manifest["files"] = [{"relpath": rel, **info} for rel, info in fileinfo.items()]
        self.games.upsert_game(
            {
                "game_id": game_id,
                "name": game["name"],
                "source_path": game["source_path"],
                "source_hash": game_hash(fileinfo),
                "extractor_version": clockup.EXTRACTOR_VERSION,
                "manifest": manifest,
                "updated_at": utcnow(),
            }
        )
        stats.update(
            GameStats(
                texts_found=len(rows),
                texts_translatable=sum(1 for t in rows if t["translatable"]),
                texts_skipped=sum(1 for t in rows if not t["translatable"]),
            ).__dict__
        )
        return {"game_id": game_id, "source_hash": game_hash(fileinfo), **stats}

    @staticmethod
    def _row(t) -> dict:
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
            "translatable": t.translatable,
            "skip_reason": t.skip_reason,
            "tokens": t.tokens,
            "status": t.status,
            "metadata": t.metadata,
        }

    # --- traducción vía pipeline existente (fan-out a TRANSLATE_TEXT) ---
    def translate_selection(
        self, game_id: str, ids: list[str], provider: str = "magi", model: str = ""
    ) -> dict:
        from ..engines.base import TranslationRequest
        from ..knowledge.interfaces import TranslationContext

        game = self._need(game_id)
        texts = self.games.list_texts(game_id, limit=100000)
        if ids:
            texts = [t for t in texts if t["id"] in set(ids)]
        else:
            # EXTRACTED + FAILED (retry de jobs muertos): QUEUED vivos no se reenvían.
            texts = [
                t
                for t in texts
                if t["status"] in (TextStatus.EXTRACTED, TextStatus.FAILED) and t["translatable"]
            ]
        queued, cached = 0, 0
        for t in texts:
            req = TranslationRequest(
                t["source_text"],
                "ja",
                game["target_lang"] or "es",
                TranslationContext(
                    source_app="kimotranslate",
                    content_type=CONTENT_BY_TYPE.get(t["text_type"], "game_ui"),
                    domain="game_translation",
                    project_id=game_id,
                    game_id=game_id,
                    speaker=t["speaker"],
                    scene=t["scene"],
                    provider=provider,
                    model=model,
                    extra={"game_text_id": t["id"]},
                ),
            )
            res = self.translate.submit(req, provider=provider, model=model)
            if res["job_id"]:
                self.games.set_text(t["id"], status=TextStatus.QUEUED, job_id=res["job_id"])
                queued += 1
            else:
                self._apply_result(t, res.get("translation") or "", provider, cached_hit=True)
                cached += 1
        return {"queued": queued, "cached": cached, "total": len(texts)}

    # --- sync: Hub -> game_texts ---
    def sync(self, game_id: str) -> dict:
        done, failed = 0, 0
        for t in self.games.list_texts(game_id, limit=100000):
            if not t["job_id"] or t["status"] not in (TextStatus.QUEUED,):
                continue
            try:
                job = self.hub.get_job(t["job_id"])
            except Exception:  # noqa: BLE001 - reintento en próximo sync
                continue
            m = job.get("metrics") or {}
            if job.get("status") == "COMPLETED" and m.get("translation"):
                self._apply_result(t, m["translation"], m.get("provider", ""), cached_hit=False)
                done += 1
            elif job.get("status") == "FAILED":
                self.games.set_text(t["id"], status=TextStatus.FAILED)
                failed += 1
        return {"synced": done, "failed": failed}

    def _apply_result(self, t: dict, translation: str, provider: str, cached_hit: bool) -> None:
        if game_tokens.tokens_ok(t["source_text"], translation):
            self.games.set_text(
                t["id"], machine_translation=translation, status=TextStatus.TRANSLATED
            )
        else:
            self.games.set_text(
                t["id"], machine_translation=translation, status=TextStatus.REVIEW_REQUIRED
            )

    # --- bundle para el worker (export) ---
    def export_bundle(self, game_id: str) -> dict:
        """Un final por slot del fichero (skipped = original). Sin huecos:
        el repack consume en orden y un hueco corrompería el alineado."""
        game = self._need(game_id)
        texts, skipped = [], 0
        for t in self.games.list_texts(game_id, limit=100000):
            if t["status"] == TextStatus.REMOVED:
                skipped += 1
                continue
            final = t["corrected_translation"] or t["machine_translation"]
            if not t["translatable"]:
                final = t["source_text"]  # passthrough
            if not final:
                skipped += 1
                continue
            if t["translatable"] and not game_tokens.tokens_ok(t["source_text"], final):
                skipped += 1
                continue
            texts.append(
                {
                    "id": t["id"],
                    "file_path": t["file_path"],
                    "source": t["source_text"],
                    "final": final,
                    "position": t["position"],
                    "validated": bool(t["corrected_translation"]),
                    "translatable": bool(t["translatable"]),
                    "metadata": t.get("metadata", {}),
                }
            )
        return {"game": game, "texts": texts, "skipped": skipped}

    def _need(self, game_id: str) -> dict:
        game = self.games.get_game(game_id)
        if game is None:
            raise KeyError(game_id)
        return game
