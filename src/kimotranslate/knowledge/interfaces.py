"""Knowledge Core: SOLO interfaces en Fase 1.

Nada de implementaciones propias de memoria semántica: la TM vive en
MAGI Memory (MemoryStore + HybridRetriever) y se conectará en Fase 4
detrás de estos Protocols. El cache exacto sí persiste en SQLite
(CacheStore, patrón de Tradujap PersistentAiCache).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ContentType:
    MANGA = "manga"
    NOVEL = "novel"
    VN_DIALOGUE = "vn_dialogue"
    GAME_UI = "game_ui"
    IMAGE_TEXT = "image_text"


@dataclass(frozen=True)
class TranslationContext:
    """Contexto obligatorio: evita mezclar manga <-> diálogo de juego."""

    source_app: str = "kimotranslate"  # kimotranslate | tradujap
    content_type: str = ContentType.VN_DIALOGUE
    project_id: str = ""
    game_id: str = ""
    speaker: str = ""
    scene: str = ""
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    domain: str = ""  # concepto MAGI: filtra memoria por dominio
    extra: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class CacheEntry:
    key: str  # hash(normalización + langs + provider + model + prompt_version)
    source_text: str
    translation: str
    source_lang: str
    target_lang: str
    context: TranslationContext = field(default_factory=TranslationContext)
    quality: float | None = None
    human_verified: bool = False


class TranslationCache(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...
    def put(self, entry: CacheEntry) -> None: ...


class TranslationMemory(Protocol):
    """Fase 4: MAGI HybridRetriever detrás de esta interfaz. Sin impl propia."""

    def search(self, text: str, context: TranslationContext, limit: int = 5) -> list[dict]: ...
    def add(self, source: str, translation: str, context: TranslationContext) -> None: ...


class TerminologyStore(Protocol):
    def lookup(self, term: str, domain: str, project_id: str = "") -> str | None: ...
    def upsert(self, term: str, preferred: str, domain: str, project_id: str = "") -> None: ...


class CorrectionStore(Protocol):
    def add(
        self, source: str, machine: str, corrected: str, context: TranslationContext
    ) -> None: ...
    def pending(self, limit: int = 100) -> list[dict]: ...


class TrainingExampleStore(Protocol):
    def add_candidate(self, example: dict) -> None: ...
    def mark(self, example_id: str, state: str) -> None: ...
