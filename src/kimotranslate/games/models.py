"""Modelos del dominio juegos. IDs deterministas: nunca índices temporales."""

from __future__ import annotations

from dataclasses import dataclass, field


class TextStatus:
    EXTRACTED = "EXTRACTED"
    SKIPPED = "SKIPPED"
    QUEUED = "QUEUED"
    TRANSLATED = "TRANSLATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VALIDATED = "VALIDATED"
    EXPORTED = "EXPORTED"
    FAILED = "FAILED"
    REMOVED = "REMOVED"  # re-extracción: ya no está en el juego (conserva traducción)


class TextType:
    DIALOGUE = "dialogue"
    NARRATION = "narration"
    CHOICE = "choice"
    SYSTEM = "system"
    UI = "ui"
    TITLE = "title"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DetectionResult:
    engine: str  # clockup | unknown
    confidence: float
    version: str = ""
    evidence: tuple = ()


@dataclass
class ExtractedText:
    id: str  # {engine}:{game_id}:{relpath}:msg:{index} — estable entre extracciones
    game_id: str
    file_path: str
    source_text: str
    text_type: str = TextType.UNKNOWN
    speaker: str = ""
    scene: str = ""
    position: int = 0
    original_hash: str = ""
    encoding: str = "cp932"
    translatable: bool = True
    skip_reason: str = ""
    tokens: list = field(default_factory=list)  # protected tokens del original
    status: str = TextStatus.EXTRACTED
    machine_translation: str = ""
    job_id: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class GameManifest:
    game_id: str
    name: str
    source_path: str
    output_path: str = ""
    detected_engine: str = "unknown"
    engine_version: str = ""
    source_language: str = "ja"
    target_language: str = "es"
    source_hash: str = ""
    extractor_version: str = ""
    exporter_version: str = ""
    files: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class GameStats:
    texts_found: int = 0
    texts_translatable: int = 0
    texts_skipped: int = 0
    texts_translated: int = 0
    texts_validated: int = 0
    texts_exported: int = 0
    texts_failed: int = 0
    files_scanned: int = 0
