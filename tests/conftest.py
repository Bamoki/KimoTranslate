"""Fixtures Fase 2: Hub real por HTTP (router training del Hub en uvicorn
efímero) + Kimo TestClient. Sin mocks de red: la integración es la que se prueba.
"""

from __future__ import annotations

import sys
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, "/mnt/hdd/raspberry-hub/data/projects/raspberry-Hub")
sys.path.insert(0, "/mnt/hdd/raspberry-hub/data/projects/magi/src")

from kimotranslate.api.app import create_app  # noqa: E402
from kimotranslate.core.config import Settings  # noqa: E402
from kimotranslate.db.sqlite import SQLiteRepository  # noqa: E402
from kimotranslate.hub.client import HubClient  # noqa: E402

HUB_PORT = 18081
HUB_URL = f"http://127.0.0.1:{HUB_PORT}"


@pytest.fixture(scope="session")
def hub_server(tmp_path_factory):
    import os

    d = tmp_path_factory.mktemp("hub")
    os.environ["HUB_TRAINING_JOBS_DIR"] = str(d / "jobs")
    os.environ["HUB_TRAINING_DATASETS_DIR"] = str(d / "datasets")
    os.environ["HUB_TRAINING_EXPERIMENTS_DIR"] = str(d / "experiments")
    os.environ["HUB_TRAINING_MODELS_DIR"] = str(d / "models")
    os.environ["HUB_TRAINING_EVALUATIONS_DIR"] = str(d / "evals")
    # Modo abierto: sin esto, ~/.config/raspberry-hub/auth.json activaría modo seguro.
    os.environ["HUB_AUTH_FILE"] = str(d / "auth.json")
    os.environ["HUB_AUDIT_FILE"] = str(d / "audit.jsonl")
    for v in (
        "MAGI_HUB_USERNAME",
        "MAGI_HUB_PASSWORD",
        "HUB_ADMIN_USERNAME",
        "HUB_ADMIN_PASSWORD",
        "MAGI_HUB_WORKER_KEY",
        "HUB_WORKER_KEY",
    ):
        os.environ.pop(v, None)
    from backend.app.auth import store as _auth_store

    _auth_store.reset_state()
    from backend.app.api.health import router as hub_health_router
    from backend.app.api.training import router as hub_router
    from backend.app.auth.router import router as hub_auth_router
    from backend.app.core.config import get_settings

    get_settings.cache_clear()
    app = FastAPI()
    app.include_router(hub_auth_router)
    app.include_router(hub_health_router)
    app.include_router(hub_router)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=HUB_PORT, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            httpx.get(f"{HUB_URL}/api/training/jobs", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)
    yield server
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture()
def repo(tmp_path):
    return SQLiteRepository(str(tmp_path / "kimo.db"))


@pytest.fixture()
def hub_client(hub_server):
    return HubClient(base_url=HUB_URL)


@pytest.fixture()
def client(tmp_path, hub_client):
    return TestClient(create_app(Settings(data_dir=str(tmp_path)), hub=hub_client))
