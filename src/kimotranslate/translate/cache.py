"""Normalización + cache key. Módulo hoja: sin imports locales (evita ciclos)."""

from __future__ import annotations

import hashlib
import unicodedata


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def cache_key(
    source: str,
    source_lang: str,
    target_lang: str,
    provider: str,
    model: str,
    prompt_version: str,
    domain: str,
    content_type: str,
    scope: str = "",
) -> str:
    """scope = game_id o project_id: evita que el juego A contamine al B."""
    raw = "|".join(
        [
            normalize(source),
            source_lang,
            target_lang,
            provider,
            model,
            prompt_version,
            domain,
            content_type,
            scope,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
