"""Routers Kimo: traducción + proyectos + terminología + memoria + providers.

Jobs/workers = Hub (hub/client.py). Memoria = MAGI Memory (knowledge/memory.py).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query

from ..db.repository import Store
from ..engines import PROVIDERS, provider_status
from ..engines.base import TranslationRequest
from ..hub.client import HubClient, HubError
from ..knowledge.corrections import CorrectionError
from ..knowledge.interfaces import TranslationContext
from ..translate.pipeline import TranslationService
from .schemas import (
    CorrectionIn,
    CorrectionOut,
    CorrectionPatch,
    DatasetBuild,
    DatasetOut,
    DetectionOut,
    ExampleOut,
    GameDetect,
    GameExportIn,
    GameOut,
    GameRegister,
    GameTextOut,
    GameTranslateIn,
    HealthOut,
    ImageAssetOut,
    ImageDetailOut,
    ImageLocalizeIn,
    ImageOcrIn,
    ImageRegionOut,
    ImageTranslateIn,
    JobResultOut,
    MemoryHit,
    ProjectCreate,
    ProjectOut,
    ProviderOut,
    TerminologyIn,
    TerminologyOut,
    TranslationOut,
    TranslationSubmit,
)

router = APIRouter()
store: Store | None = None  # inyectado por app.create_app
hub: HubClient | None = None
memory = None  # TranslationMemory o None (sin MAGI instalado)
corrections = None  # CorrectionService
datasets = None  # DatasetBuilder
games = None  # GameStore
game_svc = None  # GameService
images = None  # ImageStore
img_svc = None  # ImageService
editor = None  # EditorService


def _service() -> TranslationService:
    assert store is not None and hub is not None
    return TranslationService(store, hub, memory)


def _to_request(body: TranslationSubmit) -> TranslationRequest:
    c = body.context
    return TranslationRequest(
        source_text=body.text,
        source_lang=body.source_language,
        target_lang=body.target_language,
        context=TranslationContext(
            source_app=c.source_app,
            content_type=c.content_type,
            project_id=c.project_id,
            game_id=c.game_id,
            speaker=c.speaker,
            scene=c.scene,
            domain=c.domain,
            extra={
                "previous_text": c.previous_text,
                "next_text": c.next_text,
                "relationship": c.relationship,
                "tone": c.tone,
            },
        ),
    )


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    assert store is not None and hub is not None
    try:
        db_ok = store.health()
    except Exception:  # noqa: BLE001 - cualquier fallo => degraded
        db_ok = False
    try:
        hub.health()
        hub_ok = True
    except Exception:  # noqa: BLE001
        hub_ok = False
    data_dir = os.environ.get("KIMOTRANSLATE_DATA_DIR", "")
    storage_ok = os.path.isdir(data_dir) if data_dir else True
    ok = db_ok and storage_ok and hub_ok
    return HealthOut(
        status="ok" if ok else "degraded",
        database="ok" if db_ok else "error",
        storage="ok" if storage_ok else "error",
        hub="ok" if hub_ok else "error",
        data_dir=data_dir or "default",
    )


@router.get("/projects", response_model=list[ProjectOut])
def list_projects() -> list:
    assert store is not None
    return store.list_projects()


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate) -> dict:
    assert store is not None
    return store.create_project(body.name, body.game_id)


@router.get("/providers", response_model=list[ProviderOut])
def list_providers() -> list:
    return provider_status()


@router.post("/translations", response_model=TranslationOut, status_code=201)
def submit_translation(body: TranslationSubmit) -> dict:
    """HIT exacto / TM reutilizable -> traducción. Si no, job TRANSLATE_TEXT."""
    if not body.text.strip():
        raise HTTPException(400, "empty text")
    if body.provider.lower() not in PROVIDERS:
        raise HTTPException(400, f"unknown provider (use {', '.join(PROVIDERS)})")
    try:
        return _service().submit(
            _to_request(body), provider=body.provider.lower(), model=body.model
        )
    except HubError as e:
        raise HTTPException(502, str(e)) from e


@router.get("/jobs/{job_id}", response_model=JobResultOut)
def get_job(job_id: str) -> dict:
    """Passthrough al Hub + lazy cache write al completarse."""
    try:
        return _service().job_result(job_id)
    except HubError as e:
        raise HTTPException(502, str(e)) from e


@router.get("/jobs", response_model=list[JobResultOut])
def list_jobs() -> list:
    """Solo jobs domain=translation del Hub, con traducción si completados."""
    assert hub is not None
    try:
        jobs = hub.list_translation_jobs()
    except HubError as e:
        raise HTTPException(502, str(e)) from e
    return [
        {
            "job_id": j["id"],
            "status": j["status"],
            "translation": (j.get("metrics") or {}).get("translation"),
            "cached": False,
            "memory_hit": bool((j.get("metrics") or {}).get("memory_hit")),
            "provider": (j.get("metrics") or {}).get("provider"),
            "model": (j.get("metrics") or {}).get("model"),
            "error": j.get("error"),
            "metrics": {"request": (j.get("metrics") or {}).get("request", {})},
        }
        for j in jobs
    ]


@router.post("/terminology", response_model=TerminologyOut, status_code=201)
def add_term(body: TerminologyIn) -> dict:
    """scope implícito: game_id -> game, project_id -> project, si no global."""
    assert store is not None
    if not body.term.strip() or not body.preferred.strip():
        raise HTTPException(400, "empty term/preferred")
    return store.terms.upsert(
        body.term.strip(),
        body.preferred.strip(),
        body.source_lang,
        body.target_lang,
        body.project_id,
        body.game_id,
        body.priority,
        body.notes,
    )


@router.get("/terminology", response_model=list[TerminologyOut])
def list_terminology(term: str = "", project_id: str = "", game_id: str = "") -> list:
    assert store is not None
    if term:
        hit = store.terms.lookup(term, project_id=project_id, game_id=game_id)
        return [hit] if hit else []
    return store.terms.list_terms(project_id=project_id, game_id=game_id)


@router.get("/memory/search", response_model=list[MemoryHit])
def memory_search(
    query: str = Query(min_length=1),
    domain: str = "",
    content_type: str = "",
    project_id: str = "",
    game_id: str = "",
    limit: int = 5,
) -> list:
    """TM filtrada. Sin domain no hay búsqueda global."""
    if memory is None:
        raise HTTPException(501, "memory unavailable (MAGI not installed)")
    return memory.search(query, domain, content_type, project_id, game_id, limit)


def _corrections():
    assert corrections is not None
    return corrections


@router.post("/corrections", response_model=CorrectionOut, status_code=201)
def create_correction(body: CorrectionIn) -> dict:
    if not body.source_text.strip():
        raise HTTPException(400, "empty source_text")
    return _corrections().create(body.model_dump())


@router.get("/corrections", response_model=list[CorrectionOut])
def list_corrections(status: str = "", project_id: str = "") -> list:
    return _corrections().list(status=status, project_id=project_id)


@router.get("/corrections/{cid}", response_model=CorrectionOut)
def get_correction(cid: str) -> dict:
    c = _corrections().get(cid)
    if c is None:
        raise HTTPException(404, cid)
    return c


@router.patch("/corrections/{cid}", response_model=CorrectionOut)
def patch_correction(cid: str, body: CorrectionPatch) -> dict:
    """Editar, validar (promociona a TM + ejemplo) o rechazar."""
    try:
        if body.rejected:
            return _corrections().reject(cid, body.reviewer)
        if body.validated:
            return _corrections().validate(cid, body.reviewer)
        if body.corrected_translation:
            return _corrections().update(cid, body.corrected_translation, body.reviewer)
        raise HTTPException(400, "nothing to do")
    except CorrectionError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/examples", response_model=list[ExampleOut])
def list_examples(
    source_app: str = "",
    domain: str = "",
    content_type: str = "",
    project_id: str = "",
    game_id: str = "",
) -> list:
    assert datasets is not None
    return datasets.query(
        source_app=source_app,
        domain=domain,
        content_type=content_type,
        project_id=project_id,
        game_id=game_id,
    )


@router.post("/datasets/build", response_model=DatasetOut, status_code=201)
def build_dataset(body: DatasetBuild) -> dict:
    """Validados -> dedup -> JSONL versionado en KIMOTRANSLATE_DATA_DIR/datasets."""
    assert datasets is not None
    return datasets.build(**body.model_dump())


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets() -> list:
    assert datasets is not None
    return datasets.list_datasets()


@router.get("/datasets/{dataset_id}/{version}/download")
def download_dataset(dataset_id: str, version: int):
    from fastapi.responses import FileResponse

    assert datasets is not None
    manifest = datasets.get(dataset_id, version)
    if manifest is None:
        raise HTTPException(404, f"{dataset_id} v{version}")
    return FileResponse(
        manifest["path"],
        media_type="application/x-ndjson",
        filename=f"{dataset_id}_v{version}.jsonl",
    )


FUTURE = ["images", "ocr"]


def _register_future(app_router: APIRouter) -> None:
    for prefix in FUTURE:

        def _handler(prefix=prefix):
            raise HTTPException(501, f"/{prefix} arrives in its phase")

        app_router.add_api_route(f"/{prefix}", _handler, methods=["GET", "POST"])


def _games():
    assert games is not None and game_svc is not None
    return games, game_svc


@router.post("/games/detect", response_model=DetectionOut)
def detect_game(body: GameDetect) -> dict:
    from ..games.engines import clockup

    det = clockup.detect(body.path)
    return {
        "engine": det.engine,
        "confidence": det.confidence,
        "version": det.version,
        "evidence": list(det.evidence),
    }


@router.post("/games", response_model=GameOut, status_code=201)
def register_game(body: GameRegister) -> dict:
    _, svc = _games()
    try:
        game = svc.register(body.source_path, body.name, body.game_id)
    except (OSError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return {**game, "counts": {}}


@router.get("/games", response_model=list[GameOut])
def list_games() -> list:
    store_games, _ = _games()
    return [{**g, "counts": store_games.counts(g["game_id"])} for g in store_games.list_games()]


@router.get("/games/{game_id}", response_model=GameOut)
def get_game(game_id: str) -> dict:
    store_games, _ = _games()
    game = store_games.get_game(game_id)
    if game is None:
        raise HTTPException(404, game_id)
    return {**game, "counts": store_games.counts(game_id)}


@router.delete("/games/{game_id}")
def delete_game(game_id: str) -> dict:
    store_games, _ = _games()
    if not store_games.delete_game(game_id):
        raise HTTPException(404, game_id)
    return {"deleted": game_id}


@router.post("/games/{game_id}/extract")
def extract_game(game_id: str, local: bool = False) -> dict:
    """local=true: extrae en el servidor (Pi/dev). Si no, job EXTRACT_GAME al Hub."""
    from ..games import worker_ops

    store_games, svc = _games()
    game = store_games.get_game(game_id)
    if game is None:
        raise HTTPException(404, game_id)
    if local:
        try:
            return svc.extract_local(game_id)
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e)) from e
    assert hub is not None
    try:
        return worker_ops.create_extract_job(hub, game_id, game["source_path"])
    except HubError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/games/{game_id}/texts/bulk")
def bulk_texts(game_id: str, body: dict) -> dict:
    """Push del worker: upsert por ID estable (re-extracción sin duplicar)."""
    _, svc = _games()
    from ..games.models import ExtractedText

    texts = []
    try:
        for t in body.get("texts", []):
            texts.append(
                ExtractedText(
                    id=t["id"],
                    game_id=game_id,
                    file_path=t.get("file_path", ""),
                    source_text=t.get("source_text", ""),
                    text_type=t.get("text_type", "unknown"),
                    speaker=t.get("speaker", ""),
                    scene=t.get("scene", ""),
                    position=int(t.get("position", 0)),
                    original_hash=t.get("original_hash", ""),
                    encoding=t.get("encoding", "cp932"),
                    translatable=bool(t.get("translatable", True)),
                    skip_reason=t.get("skip_reason", ""),
                    tokens=t.get("tokens", []),
                    status=t.get("status", "EXTRACTED"),
                    metadata=t.get("metadata", {}),
                )
            )
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, f"bad texts: {e}") from e
    return svc.merge_result(game_id, texts, body.get("fileinfo", {}))


@router.get("/games/{game_id}/texts", response_model=list[GameTextOut])
def list_texts(
    game_id: str,
    status: str = "",
    speaker: str = "",
    scene: str = "",
    translatable: str = "",
    search: str = "",
) -> list:
    store_games, _ = _games()
    if store_games.get_game(game_id) is None:
        raise HTTPException(404, game_id)
    rows = store_games.list_texts(game_id, status, speaker, scene, translatable, search)
    return [
        {k: r.get(k, "") for k in GameTextOut.model_fields} | {"game_id": game_id} for r in rows
    ]


@router.post("/games/{game_id}/translate")
def translate_game(game_id: str, body: GameTranslateIn) -> dict:
    """Fan-out a TRANSLATE_TEXT vía pipeline (sin queue local)."""
    from ..engines import PROVIDERS

    _, svc = _games()
    if body.provider.lower() not in PROVIDERS:
        raise HTTPException(400, f"unknown provider (use {', '.join(PROVIDERS)})")
    try:
        return svc.translate_selection(game_id, body.ids, body.provider.lower(), body.model)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except HubError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/games/{game_id}/sync")
def sync_game(game_id: str) -> dict:
    _, svc = _games()
    try:
        return svc.sync(game_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/games/{game_id}/export-bundle")
def export_bundle(game_id: str) -> dict:
    _, svc = _games()
    try:
        return svc.export_bundle(game_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/games/{game_id}/export")
def export_game(game_id: str, body: GameExportIn) -> dict:
    """local=true: exporta en el servidor. Si no, job EXPORT_GAME al Hub."""
    from ..games import exporter, worker_ops

    store_games, svc = _games()
    game = store_games.get_game(game_id)
    if game is None:
        raise HTTPException(404, game_id)
    output = body.output_path or game["output_path"]
    if not output:
        raise HTTPException(400, "output_path required")
    if body.local:
        try:
            manifest = exporter.export_game(game["source_path"], output, svc.export_bundle(game_id))
        except exporter.ExportError as e:
            raise HTTPException(400, str(e)) from e
        store_games.upsert_game(
            {
                "game_id": game_id,
                "name": game["name"],
                "source_path": game["source_path"],
                "manifest": {**(game["manifest"] or {}), "last_export": manifest},
            }
        )
        return manifest
    assert hub is not None
    try:
        return worker_ops.create_export_job(hub, game_id, game["source_path"], output)
    except HubError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/games/{game_id}/export-report")
def export_report(game_id: str, manifest: dict) -> dict:
    store_games, _ = _games()
    game = store_games.get_game(game_id)
    if game is None:
        raise HTTPException(404, game_id)
    store_games.upsert_game(
        {
            "game_id": game_id,
            "name": game["name"],
            "source_path": game["source_path"],
            "manifest": {**(game["manifest"] or {}), "last_export": manifest},
        }
    )
    return {"ok": True}


def _imgs():
    assert images is not None and img_svc is not None and hub is not None
    return images, img_svc


def _img_asset(game_id: str, image_id: str) -> dict:
    store_images, _ = _imgs()
    asset = store_images.get_asset(image_id)
    if asset is None or asset["game_id"] != game_id:
        raise HTTPException(404, image_id)
    return asset


@router.post("/games/{game_id}/images/discover")
def discover_images(game_id: str) -> dict:
    """Server-local (Pi/dev). En Windows lo hace el worker dentro de EXTRACT_GAME."""
    store_games, _ = _games()
    game = store_games.get_game(game_id)
    if game is None:
        raise HTTPException(404, game_id)
    _, svc = _imgs()
    return svc.discover_local(game_id, game["source_path"], game.get("project_id", ""))


@router.post("/games/{game_id}/images/bulk")
def bulk_images(game_id: str, body: dict) -> dict:
    """Push del worker: assets descubiertos en el PC."""
    from ..images.service import image_id_for

    store_games, _ = _games()
    if store_games.get_game(game_id) is None:
        raise HTTPException(404, game_id)
    _, svc = _imgs()
    n = 0
    for a in body.get("assets", []):
        iid = image_id_for(game_id, a["relpath"], a["original_hash"])
        svc.images.upsert_asset({"id": iid, "game_id": game_id, **a})
        n += 1
    return {"images_kept": n}


@router.get("/games/{game_id}/images", response_model=list[ImageAssetOut])
def list_images(game_id: str, ocr_status: str = "", localization_status: str = "") -> list:
    store_images, _ = _imgs()
    rows = store_images.list_assets(game_id, ocr_status, localization_status)
    return [
        {k: r.get(k, "") for k in ImageAssetOut.model_fields}
        | {"likely_text": bool(r["likely_text"])}
        for r in rows
    ]


@router.get("/games/{game_id}/images/export-list")
def images_export_list(game_id: str) -> dict:
    """Para EXPORT_GAME (worker): localized_b64 + regiones con finales.
    DEFINIDA ANTES que /{image_id}: si no, FastAPI la captura como image_id."""
    import base64
    import os

    from ..images import cache as img_cache

    store_images, svc = _imgs()
    items = []
    for a in store_images.list_assets(game_id, limit=100000):
        if a["localization_status"] != "LOCALIZED":
            continue
        path = os.path.join(img_cache.artifact_dir(svc.data_dir, a["id"]), "localized.png")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        regions = []
        for r in store_images.list_regions(a["id"]):
            if r["status"] == "DELETED":
                continue
            final = r["corrected_translation"] or r["machine_translation"]
            regions.append(
                {
                    "id": r["id"],
                    "source": r["source_text"],
                    "final": final,
                    "translatable": bool(r["translatable"]),
                }
            )
        items.append({"relpath": a["relpath"], "localized_b64": b64, "regions": regions})
    return {"items": items}


@router.get("/games/{game_id}/images/{image_id}", response_model=ImageDetailOut)
def get_image(game_id: str, image_id: str) -> dict:
    asset = _img_asset(game_id, image_id)
    store_images, _ = _imgs()
    regions = store_images.list_regions(image_id)
    base = {k: asset.get(k, "") for k in ImageAssetOut.model_fields}
    base["likely_text"] = bool(asset["likely_text"])
    base["regions"] = [{k: r.get(k) for k in ImageRegionOut.model_fields} for r in regions]
    return base


@router.post("/games/{game_id}/images/{image_id}/ocr")
def ocr_image(game_id: str, image_id: str, body: ImageOcrIn) -> dict:
    """Siempre vía Hub (el OCR pesado es del worker)."""
    from ..images import worker_ops as img_ops

    _img_asset(game_id, image_id)
    try:
        return img_ops.create_ocr_job(hub, image_id, game_id, body.engine)
    except HubError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/games/{game_id}/images/ocr")
def ocr_images_batch(game_id: str, body: ImageOcrIn) -> dict:
    from ..images import worker_ops as img_ops

    store_images, _ = _imgs()
    jobs = []
    try:
        for a in store_images.list_assets(game_id, limit=100000):
            if a["likely_text"] and a["ocr_status"] == "DISCOVERED":
                jobs.append(img_ops.create_ocr_job(hub, a["id"], game_id, body.engine)["id"])
    except HubError as e:
        raise HTTPException(502, str(e)) from e
    return {"jobs": jobs}


@router.post("/games/{game_id}/images/{image_id}/ocr-result")
def ocr_result(game_id: str, image_id: str, body: dict) -> dict:
    _img_asset(game_id, image_id)
    _, svc = _imgs()
    return svc.ingest_ocr(
        image_id,
        {"regions": body.get("regions", [])},
        body.get("engine", ""),
        body.get("version", ""),
    )


@router.post("/games/{game_id}/images/{image_id}/translate")
def translate_image(game_id: str, image_id: str, body: ImageTranslateIn) -> dict:
    from ..engines import PROVIDERS

    _img_asset(game_id, image_id)
    if body.provider.lower() not in PROVIDERS:
        raise HTTPException(400, f"unknown provider (use {', '.join(PROVIDERS)})")
    _, svc = _imgs()
    try:
        return svc.translate_selection(image_id, body.region_ids, body.provider.lower(), body.model)
    except HubError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/games/{game_id}/images/translate")
def translate_images_batch(game_id: str, body: ImageTranslateIn) -> dict:
    from ..engines import PROVIDERS

    if body.provider.lower() not in PROVIDERS:
        raise HTTPException(400, f"unknown provider (use {', '.join(PROVIDERS)})")
    store_images, svc = _imgs()
    out = {"images": 0, "queued": 0, "cached": 0}
    try:
        for a in store_images.list_assets(game_id, limit=100000):
            if a["ocr_status"] != "OCR_DONE":
                continue
            r = svc.translate_selection(a["id"], [], body.provider.lower(), body.model)
            out["images"] += 1
            out["queued"] += r["queued"]
            out["cached"] += r["cached"]
    except HubError as e:
        raise HTTPException(502, str(e)) from e
    return out


@router.post("/games/{game_id}/images/{image_id}/sync")
def sync_image(game_id: str, image_id: str) -> dict:
    _img_asset(game_id, image_id)
    _, svc = _imgs()
    return svc.sync(image_id)


@router.post("/games/{game_id}/images/{image_id}/localize")
def localize_image(game_id: str, image_id: str, body: ImageLocalizeIn) -> dict:
    from ..images import worker_ops as img_ops

    _img_asset(game_id, image_id)
    if body.local:
        _, svc = _imgs()
        return svc.localize_local(image_id)
    try:
        return img_ops.create_localize_job(hub, image_id, game_id)
    except HubError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/games/{game_id}/images/localize")
def localize_images_batch(game_id: str, body: ImageLocalizeIn) -> dict:
    from ..images import worker_ops as img_ops

    store_images, svc = _imgs()
    if body.local:
        done = []
        for a in store_images.list_assets(game_id, limit=100000):
            if store_images.list_regions(a["id"]):
                done.append(svc.localize_local(a["id"])["status"])
        return {"localized": done}
    jobs = []
    try:
        for a in store_images.list_assets(game_id, limit=100000):
            if a["ocr_status"] == "OCR_DONE":
                jobs.append(img_ops.create_localize_job(hub, a["id"], game_id)["id"])
    except HubError as e:
        raise HTTPException(502, str(e)) from e
    return {"jobs": jobs}


@router.get("/games/{game_id}/images/{image_id}/bundle")
def image_bundle(game_id: str, image_id: str) -> dict:
    _img_asset(game_id, image_id)
    _, svc = _imgs()
    return svc.localize_bundle(image_id)


@router.post("/games/{game_id}/images/{image_id}/artifacts")
def push_artifacts(game_id: str, image_id: str, body: dict) -> dict:
    import base64

    from ..images import cache as img_cache

    asset = _img_asset(game_id, image_id)
    _, svc = _imgs()
    base = img_cache.artifact_dir(svc.data_dir, image_id)
    for name, b64 in (
        ("localized.png", body.get("localized_b64", "")),
        ("mask.png", body.get("mask_b64", "")),
        ("original.png", body.get("original_b64", "")),
    ):
        if b64:
            img_cache.write_versioned(base, name, base64.b64decode(b64))
    report = body.get("report", [])
    fits = [x.get("fit") for x in report if x.get("region_id")]
    failed = [x for x in fits if x in ("OVERFLOW", "FAILED")]
    status = "LOCALIZED" if not failed and fits else "FAILED"
    manifest = (asset["manifest"] or {}) | {
        "renderer_version": body.get("renderer_version", ""),
        "inpaint_version": body.get("inpaint_version", ""),
        "report": report,
    }
    svc.images.set_asset(image_id, localization_status=status, manifest=manifest)
    if status == "LOCALIZED":
        from ..images.editor.service import snapshot_render_state

        snapshot_render_state(svc.images, image_id)
        manifest = (svc.images.get_asset(image_id) or {}).get("manifest", manifest)
    svc._write_json(image_id, "manifest.json", manifest)
    svc._write_json(
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
                for r in svc.images.list_regions(image_id)
            ],
        },
    )
    return {"status": status, "artifacts": img_cache.artifact_dir(svc.data_dir, image_id)}


def _editor():
    assert editor is not None
    return editor


@router.get("/games/{game_id}/images/{image_id}/artifact/{name}")
def get_artifact(game_id: str, image_id: str, name: str):
    """Bytes de artefactos para el editor (original/preview/localized/mask)."""
    from fastapi.responses import FileResponse

    from ..images import cache as img_cache

    _img_asset(game_id, image_id)
    if name not in (*img_cache.ARTIFACTS, "preview.png", "localized_prev.png"):
        raise HTTPException(400, f"bad artifact {name}")
    assert img_svc is not None
    path = __import__("os").path.join(img_cache.artifact_dir(img_svc.data_dir, image_id), name)
    if not __import__("os").path.exists(path):
        raise HTTPException(404, name)
    return FileResponse(path, media_type="image/png")


@router.get("/games/{game_id}/images/{image_id}/editor")
def editor_state(game_id: str, image_id: str) -> dict:
    _img_asset(game_id, image_id)
    try:
        return _editor().state(image_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.patch("/games/{game_id}/images/{image_id}/regions/{region_id}")
def patch_region(game_id: str, image_id: str, region_id: str, body: dict) -> dict:
    from ..images.editor import operations as _ops

    _img_asset(game_id, image_id)
    ed = _editor()
    try:
        out = {}
        if {"x", "y", "w", "h"} <= set(body):
            out = ed.resize_region(
                image_id, region_id, int(body["x"]), int(body["y"]), int(body["w"]), int(body["h"])
            )
        elif {"x", "y"} <= set(body):
            out = ed.move_region(image_id, region_id, int(body["x"]), int(body["y"]))
        if "source_text" in body:
            out = ed.edit_ocr(image_id, region_id, body["source_text"])
        if "translation" in body:
            out = ed.edit_translation(
                image_id, region_id, body["translation"], body.get("reviewer", "")
            )
        if "style" in body:
            out = ed.set_style(image_id, region_id, body["style"])
        if not out:
            raise HTTPException(400, "nothing to patch")
        return out
    except _ops.EditorError as e:
        raise HTTPException(400, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/games/{game_id}/images/{image_id}/regions", status_code=201)
def create_region(game_id: str, image_id: str, body: dict) -> dict:
    from ..images.editor import operations as _ops

    _img_asset(game_id, image_id)
    try:
        return _editor().create_region(
            image_id, int(body["x"]), int(body["y"]), int(body["w"]), int(body["h"])
        )
    except _ops.EditorError as e:
        raise HTTPException(400, str(e)) from e
    except (KeyError, ValueError) as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/games/{game_id}/images/{image_id}/regions/{region_id}")
def delete_region(game_id: str, image_id: str, region_id: str) -> dict:
    _img_asset(game_id, image_id)
    try:
        return _editor().delete_region(image_id, region_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/games/{game_id}/images/{image_id}/mask")
def mask_stroke(game_id: str, image_id: str, body: dict) -> dict:
    from ..images.editor import operations as _ops

    _img_asset(game_id, image_id)
    try:
        return _editor().mask_stroke(
            image_id,
            body.get("tool", ""),
            int(body.get("x", 0)),
            int(body.get("y", 0)),
            int(body.get("radius", 8)),
        )
    except _ops.EditorError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/games/{game_id}/images/{image_id}/preview")
def editor_preview(game_id: str, image_id: str, body: dict) -> dict:
    """Render server-side (dev/Pi con ficheros). En Windows usa LOCALIZE_IMAGE."""
    import base64
    import io
    import os

    from PIL import Image

    from ..images import cache as img_cache
    from ..images import pipeline as img_pipeline

    asset = _img_asset(game_id, image_id)
    try:
        with open(asset["file_path"], "rb") as f:
            image = Image.open(io.BytesIO(f.read())).convert("RGB")
    except OSError as e:
        raise HTTPException(409, f"preview needs local file (use worker localize): {e}") from e
    ed = _editor()
    rows = [r for r in ed.images.list_regions(image_id) if r["status"] != "DELETED"]
    wanted = set(body.get("region_ids", []))
    if wanted:
        rows = [r for r in rows if r["id"] in wanted]
    from ..images.editor.service import rasterize

    asset0 = ed.images.get_asset(image_id)
    manifest0 = (asset0["manifest"] if asset0 else {}) or {}
    eligible_rows = [r for r, _ in img_pipeline.eligible(rows)]
    mask = rasterize(image.width, image.height, eligible_rows, manifest0.get("mask_strokes", []))
    localized, _, report = img_pipeline.localize(image, rows, body.get("style"), mask=mask)
    buf = io.BytesIO()
    localized.save(buf, format="PNG")
    with open(
        os.path.join(img_cache.artifact_dir(ed.data_dir, image_id), "preview.png"), "wb"
    ) as f:
        f.write(buf.getvalue())
    return {"preview_b64": base64.b64encode(buf.getvalue()).decode(), "report": report}


@router.post("/games/{game_id}/images/{image_id}/history/undo")
def editor_undo(game_id: str, image_id: str) -> dict:
    _img_asset(game_id, image_id)
    return _editor().undo(image_id) or {"undone": None}


@router.post("/games/{game_id}/images/{image_id}/history/redo")
def editor_redo(game_id: str, image_id: str) -> dict:
    _img_asset(game_id, image_id)
    return _editor().redo(image_id) or {"redone": None}


@router.post("/games/{game_id}/images/{image_id}/regions/{region_id}/validate")
def validate_region(game_id: str, image_id: str, region_id: str, body: dict) -> dict:
    from ..images.editor import operations as _ops

    _img_asset(game_id, image_id)
    try:
        return _editor().validate_region(image_id, region_id, body.get("reviewer", ""))
    except _ops.EditorError as e:
        raise HTTPException(400, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/games/{game_id}/images/{image_id}/validate")
def validate_image(game_id: str, image_id: str, body: dict) -> dict:
    from ..images.editor import operations as _ops

    _img_asset(game_id, image_id)
    try:
        return _editor().validate_image(image_id, body.get("reviewer", ""))
    except _ops.EditorError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/games/{game_id}/images/{image_id}/reset")
def reset_editor(game_id: str, image_id: str, body: dict) -> dict:
    """Reset Region (region_id) o Reset Image (localized_prev -> localized)."""
    import os
    import shutil

    from ..images import cache as img_cache

    _img_asset(game_id, image_id)
    if body.get("region_id"):
        try:
            return _editor().reset_region(image_id, body["region_id"])
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
    assert img_svc is not None
    base = img_cache.artifact_dir(img_svc.data_dir, image_id)
    prev = os.path.join(base, "localized_prev.png")
    if not os.path.exists(prev):
        raise HTTPException(409, "no previous version")
    shutil.copy2(prev, os.path.join(base, "localized.png"))
    return {"reset": "image", "restored": "localized_prev.png"}


@router.post("/games/{game_id}/integrity")
def verify_integrity(game_id: str, body: dict) -> dict:
    from ..games import integrity as _integrity

    store_games, _ = _games()
    game = store_games.get_game(game_id)
    if game is None:
        raise HTTPException(404, game_id)
    output = body.get("output_path") or game.get("output_path")
    if not output:
        raise HTTPException(400, "output_path required")
    manifest = (game.get("manifest") or {}).get("last_export", {})
    return _integrity.verify_export(game["source_path"], output, manifest)


@router.get("/release")
def release_manifest() -> dict:
    from ..release import build_manifest

    assert datasets is not None
    return build_manifest(
        {"datasets": [d["dataset_id"] + "@v" + str(d["version"]) for d in datasets.list_datasets()]}
    )


@router.get("/hub/status")
def hub_status() -> dict:
    assert hub is not None
    try:
        mode = hub.hub_mode()
    except HubError as e:
        raise HTTPException(502, str(e)) from e
    return {"hub_url": hub.base_url, **mode}


@router.post("/hub/login")
def hub_login(body: dict) -> dict:
    """Guarda sesión admin del Hub en memoria (para modo seguro).
    La clave no se persiste ni se registra; solo vive en el proceso."""
    assert hub is not None
    try:
        result = hub.login((body.get("username") or "").strip(), body.get("password") or "")
    except HubError as e:
        raise HTTPException(401, "hub rejected credentials") from e
    return {"hub_url": hub.base_url, **result}
