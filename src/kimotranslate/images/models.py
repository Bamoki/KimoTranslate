"""Modelos de imágenes. IDs deterministas: img:{game}:{sha} y {img}:r{idx}."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..games.models import TextStatus  # noqa: F401 (reutiliza estados Fase 5)


class AssetStatus:
    DISCOVERED = "DISCOVERED"
    SKIPPED = "SKIPPED"
    OCR_PENDING = "OCR_PENDING"
    OCR_DONE = "OCR_DONE"
    TRANSLATION_PENDING = "TRANSLATION_PENDING"
    TRANSLATED = "TRANSLATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VALIDATED = "VALIDATED"
    LOCALIZED = "LOCALIZED"
    FAILED = "FAILED"


@dataclass
class ImageAsset:
    id: str
    game_id: str
    project_id: str = ""
    file_path: str = ""
    relpath: str = ""
    original_hash: str = ""
    width: int = 0
    height: int = 0
    format: str = ""
    likely_text: bool = True
    skip_reason: str = ""
    ocr_status: str = AssetStatus.DISCOVERED
    localization_status: str = AssetStatus.DISCOVERED
    ocr_engine: str = ""
    ocr_version: str = ""
    provider: str = ""
    model: str = ""


@dataclass
class ImageTextRegion:
    id: str
    image_id: str
    region_index: int
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    polygon: list = field(default_factory=list)
    source_text: str = ""
    confidence: float | None = None
    language: str = "ja"
    orientation: str = "horizontal"  # horizontal | vertical
    reading_order: int = 0
    group_id: str = ""
    text_type: str = "dialogue"
    speaker: str = ""
    scene: str = ""
    translatable: bool = True
    status: str = "EXTRACTED"
    machine_translation: str = ""
    corrected_translation: str = ""
    job_id: str = ""
    style: dict = field(default_factory=dict)


@dataclass
class OcrRegion:
    x: int
    y: int
    w: int
    h: int
    text: str
    confidence: float | None = None
    orientation: str = "horizontal"
    polygon: list = field(default_factory=list)


@dataclass
class OcrResult:
    regions: list = field(default_factory=list)  # OcrRegion
    engine: str = ""
    version: str = ""
    duration_ms: float = 0.0
