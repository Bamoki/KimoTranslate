"""FastAPI app. Kimo = traducción; Jobs/Workers = Hub; memoria = MAGI."""

from __future__ import annotations

from fastapi import FastAPI

from .. import __version__
from ..core.config import Settings, load_settings
from ..core.logging import setup_logging
from ..db.sqlite import SQLiteRepository
from ..games.service import GameService
from ..games.store import GameStore
from ..hub.client import HubClient
from ..images.service import ImageService
from ..images.store import ImageStore
from ..knowledge.corrections import CorrectionService
from ..knowledge.dataset import DatasetBuilder
from ..translate.pipeline import TranslationService
from . import router as r

log = setup_logging()


def _open_memory(data_dir: str = ""):
    try:
        from ..knowledge.memory import TranslationMemory

        return TranslationMemory(data_dir=data_dir)
    except Exception as e:  # noqa: BLE001 - sin MAGI: API de memoria en 501
        log.warning("memory unavailable: %s", e)
        return None


_AUTO = object()


def create_app(
    settings: Settings | None = None, hub: HubClient | None = None, memory=_AUTO
) -> FastAPI:
    settings = settings or load_settings()
    repo = SQLiteRepository(settings.db_path)
    r.store = repo
    r.hub = hub or HubClient()
    # memory=None explícito en tests; por defecto se abre la compartida MAGI.
    r.memory = _open_memory(settings.data_dir) if memory is _AUTO else memory
    r.games = GameStore(repo.conn, repo.lock)
    r.images = ImageStore(repo.conn, repo.lock)
    r.corrections = CorrectionService(repo.conn, repo.lock, r.memory, r.games, r.images)
    r.datasets = DatasetBuilder(repo.conn, repo.lock, settings.data_dir)
    translate_svc = TranslationService(repo, r.hub, r.memory)
    r.game_svc = GameService(r.games, r.hub, translate_svc)
    r.img_svc = ImageService(r.images, r.hub, translate_svc, settings.data_dir)
    from ..images.editor.service import EditorService

    r.editor = EditorService(r.images, r.corrections, settings.data_dir)

    app = FastAPI(title="KimoTranslate", version=__version__)
    app.include_router(r.router)
    r._register_future(app.router)
    log.info("kimotranslate ready db=%s hub=%s", settings.db_path, r.hub.base_url)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run("kimotranslate.api.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
