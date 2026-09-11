"""Registro de proveedores. La API y el worker seleccionan por nombre."""

from __future__ import annotations

import os

from .base import TranslationEngine

PROVIDERS = ("magi", "ollama", "deepl", "google")

DEFAULT_PROVIDER = os.environ.get("KIMOTRANSLATE_DEFAULT_PROVIDER", "magi")


class UnknownProvider(Exception):
    pass


def get_engine(provider: str = "", **kwargs) -> TranslationEngine:
    name = (provider or DEFAULT_PROVIDER).lower()
    if name in ("magi", "ollama"):
        from .magi_engine import MagiTranslationEngine

        return MagiTranslationEngine(provider=name, **kwargs)
    if name == "deepl":
        from .deepl import DeepLTranslationEngine

        return DeepLTranslationEngine(**kwargs)
    if name == "google":
        from .google import GoogleTranslationEngine

        return GoogleTranslationEngine(**kwargs)
    raise UnknownProvider(f"unknown provider: {provider} (use {', '.join(PROVIDERS)})")


def provider_status() -> list[dict]:
    """Sin secretos: solo si cada proveedor está configurado."""
    try:
        import magi  # noqa: F401

        magi_ok = True
    except ImportError:
        magi_ok = False
    return [
        {"provider": "magi", "configured": magi_ok, "needs": "magi instalado + Ollama en worker"},
        {"provider": "ollama", "configured": magi_ok, "needs": "magi instalado + Ollama en worker"},
        {
            "provider": "deepl",
            "configured": bool(os.environ.get("DEEPL_API_KEY")),
            "needs": "DEEPL_API_KEY",
        },
        {
            "provider": "google",
            "configured": bool(os.environ.get("GOOGLE_TRANSLATE_API_KEY")),
            "needs": "GOOGLE_TRANSLATE_API_KEY",
        },
    ]
