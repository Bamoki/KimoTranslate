"""Abstracción de persistencia LOCAL de Kimo: proyectos de juego + cache exacto.

Jobs y workers viven en Raspberry-Hub (única autoridad). Este Store nunca
tendrá JobStore ni WorkerStore: ver hub/client.py.
"""

from __future__ import annotations

from typing import Protocol


class ProjectStore(Protocol):
    def create_project(self, name: str, game_id: str | None) -> dict: ...
    def get_project(self, project_id: str) -> dict | None: ...
    def list_projects(self) -> list[dict]: ...


class CacheStore(Protocol):
    """Cache exacto (normalizar -> hash -> lookup). Patrón de Tradujap PersistentAiCache."""

    def cache_get(self, key: str) -> dict | None: ...
    def cache_put(self, entry: dict) -> None: ...


class Store(ProjectStore, CacheStore, Protocol):
    def health(self) -> bool: ...
