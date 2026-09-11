"""Configuración solo por entorno. Sin secretos en código ni en logs."""

from __future__ import annotations

import os
from dataclasses import dataclass


def data_dir() -> str:
    """Directorio de datos. Nunca hardcodea /mnt/hdd: se inyecta por entorno."""
    default = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
    return os.path.abspath(os.environ.get("KIMOTRANSLATE_DATA_DIR", default))


def game_roots() -> list[str]:
    """Raíces de juegos (Windows). Vacío = el usuario escribe la ruta en la GUI."""
    raw = os.environ.get("KIMOTRANSLATE_GAME_ROOTS", "")
    return [p for p in raw.split(os.pathsep) if p]


@dataclass(frozen=True)
class Settings:
    data_dir: str = ""
    host: str = "127.0.0.1"
    port: int = 8005
    api_key: str | None = None
    worker_key: str | None = None
    stale_after_s: int = 120

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "kimotranslate.db")


def load_settings() -> Settings:
    data = data_dir()
    os.makedirs(data, exist_ok=True)
    port = int(os.environ.get("KIMOTRANSLATE_PORT", "8005"))
    return Settings(
        data_dir=data,
        host=os.environ.get("KIMOTRANSLATE_HOST", "127.0.0.1"),
        port=port,
        api_key=os.environ.get("KIMOTRANSLATE_API_KEY"),
        worker_key=os.environ.get("KIMOTRANSLATE_WORKER_KEY"),
        stale_after_s=int(os.environ.get("KIMOTRANSLATE_STALE_AFTER_S", "120")),
    )
