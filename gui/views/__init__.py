"""Registro de vistas + editor (import lazy: sin display no se toca tkinter)."""

REGISTRY: dict = {}


def register() -> dict:
    from ..editor.editor import EditorView
    from .dashboard import DashboardView
    from .datasets import DatasetsView
    from .game_detail import GameDetailView
    from .games import GamesView
    from .images import ImagesView
    from .jobs import JobsView
    from .review import ReviewView
    from .settings import SettingsView
    from .translate import TranslateView

    return {
        "overview": DashboardView,
        "games": GamesView,
        "game_detail": GameDetailView,
        "translate": TranslateView,
        "images": ImagesView,
        "review": ReviewView,
        "datasets": DatasetsView,
        "jobs": JobsView,
        "settings": SettingsView,
        "editor": EditorView,
    }


def __getattr__(name: str):
    if name == "REGISTRY" and not REGISTRY:
        REGISTRY.update(register())
        return REGISTRY
    raise AttributeError(name)
