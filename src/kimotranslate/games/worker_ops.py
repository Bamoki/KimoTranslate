"""Operaciones pesadas con ficheros: corren en el WORKER (Windows),
orquestadas por jobs del Hub. Mismo código que el servidor usa en local.
"""

from __future__ import annotations

import uuid

from ..jobs.types import JobType
from . import exporter
from .engines import clockup


def extract_game(hub, kimo, job: dict) -> dict:
    """EXTRACT_GAME: detecta+extrae en local y sube textos a la API Kimo.
    También descubre imágenes (barato) para el pipeline visual."""
    from ..images import detector as img_detector

    m = job.get("metrics") or {}
    game_id, source_path = m["game_id"], m["source_path"]
    det = clockup.detect(source_path)
    if det.engine != clockup.ENGINE:
        return hub.result(job["id"], False, error=f"engine {det.engine} unsupported")
    game = kimo.get_game(game_id)
    hints = {f["relpath"]: f for f in (game.get("manifest") or {}).get("files", [])}
    texts, fileinfo = clockup.extract(game_id, source_path, hints)
    res = kimo.bulk_texts(game_id, texts, fileinfo)
    imgs = kimo.push_game_images(game_id, img_detector.discover(source_path))
    return hub.result(
        job["id"],
        True,
        metrics={**m, "engine": det.engine, "confidence": det.confidence, **res, **imgs},
    )


def export_game(hub, kimo, job: dict) -> dict:
    """EXPORT_GAME: baja bundles y escribe el árbol localizado en local
    (scripts + imágenes)."""
    m = job.get("metrics") or {}
    game_id = m["game_id"]
    bundle = kimo.export_bundle(game_id)
    manifest = exporter.export_game(
        m.get("source_path") or bundle["game"]["source_path"], m["output_path"], bundle
    )
    kimo.export_report(game_id, manifest)
    from ..images.worker_ops import export_images_for_game

    img_manifest = export_images_for_game(
        kimo, game_id, m.get("source_path") or bundle["game"]["source_path"], m["output_path"]
    )
    failed = manifest["failed"] + img_manifest["failed"]
    return hub.result(
        job["id"],
        not failed,
        metrics={**m, **manifest, "images": img_manifest},
        error="" if not failed else f"{len(failed)} files failed",
    )


def create_extract_job(hub, game_id: str, source_path: str) -> dict:
    job_id = f"kimo-{uuid.uuid4().hex[:12]}"
    return hub.create_job(
        job_id,
        f"[{JobType.EXTRACT_GAME.value}] {game_id}",
        "translation",
        {
            "kimo_job_type": JobType.EXTRACT_GAME.value,
            "game_id": game_id,
            "source_path": source_path,
        },
    )


def create_export_job(hub, game_id: str, source_path: str, output_path: str) -> dict:
    job_id = f"kimo-{uuid.uuid4().hex[:12]}"
    return hub.create_job(
        job_id,
        f"[{JobType.EXPORT_GAME.value}] {game_id}",
        "translation",
        {
            "kimo_job_type": JobType.EXPORT_GAME.value,
            "game_id": game_id,
            "source_path": source_path,
            "output_path": output_path,
        },
    )
