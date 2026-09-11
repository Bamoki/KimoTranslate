"""Schemas de API (request/response). Sin secretos en respuestas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str
    service: str = "kimotranslate"
    database: str
    storage: str
    hub: str
    data_dir: str


class ProjectCreate(BaseModel):
    name: str
    game_id: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    game_id: str | None = None
    created_at: str


class TranslationContextIn(BaseModel):
    source_app: str = "kimotranslate"
    content_type: str = "vn_dialogue"
    project_id: str = ""
    game_id: str = ""
    speaker: str = ""
    scene: str = ""
    domain: str = "game_translation"
    previous_text: str = ""
    next_text: str = ""
    relationship: str = ""
    tone: str = ""


class TranslationSubmit(BaseModel):
    text: str
    source_language: str = "ja"
    target_language: str = "es"
    provider: str = "magi"
    model: str = ""
    context: TranslationContextIn = Field(default_factory=TranslationContextIn)


class TranslationOut(BaseModel):
    translation: str | None = None
    cached: bool = False
    memory_hit: bool = False
    job_id: str | None = None
    status: str = "COMPLETED"
    provider: str = "magi"
    model: str = ""


class JobResultOut(BaseModel):
    job_id: str
    status: str
    translation: str | None = None
    cached: bool = False
    memory_hit: bool = False
    provider: str | None = None
    model: str | None = None
    error: str | None = None
    metrics: dict = Field(default_factory=dict)


class ProviderOut(BaseModel):
    provider: str
    configured: bool
    needs: str


class TerminologyIn(BaseModel):
    term: str
    preferred: str
    source_lang: str = "ja"
    target_lang: str = "es"
    project_id: str = ""
    game_id: str = ""
    priority: int = 0
    notes: str = ""


class TerminologyOut(BaseModel):
    id: str
    term: str
    preferred: str
    source_lang: str
    target_lang: str
    project_id: str
    game_id: str
    scope: str
    priority: int
    notes: str


class MemoryHit(BaseModel):
    source: str
    translation: str
    score: float
    content_type: str
    project_id: str
    confidence: float | None = None


class CorrectionIn(BaseModel):
    source_text: str
    machine_translation: str = ""
    corrected_translation: str = ""
    source_lang: str = "ja"
    target_lang: str = "es"
    source_app: str = "kimotranslate"
    content_type: str = "vn_dialogue"
    domain: str = "game_translation"
    project_id: str = ""
    game_id: str = ""
    speaker: str = ""
    scene: str = ""
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    reviewer: str = ""
    game_text_id: str = ""
    image_region_id: str = ""


class CorrectionOut(BaseModel):
    id: str
    source_text: str
    machine_translation: str
    corrected_translation: str
    source_lang: str
    target_lang: str
    source_app: str
    content_type: str
    domain: str
    project_id: str
    game_id: str
    speaker: str
    scene: str
    provider: str
    model: str
    prompt_version: str
    status: str
    reviewer: str
    human_validated: int
    quality_score: float
    game_text_id: str = ""
    image_region_id: str = ""
    created_at: str
    updated_at: str


class CorrectionPatch(BaseModel):
    corrected_translation: str = ""
    reviewer: str = ""
    validated: bool = False
    rejected: bool = False


class ExampleOut(BaseModel):
    id: str
    source_text: str
    machine_translation: str
    corrected_translation: str
    source_lang: str
    target_lang: str
    source_app: str
    content_type: str
    domain: str
    project_id: str
    game_id: str
    speaker: str
    provider: str
    model: str
    human_validated: int
    quality_score: float


class DatasetBuild(BaseModel):
    dataset_id: str = ""
    source_app: str = ""
    domain: str = ""
    content_type: str = ""
    project_id: str = ""
    game_id: str = ""
    source_lang: str = ""
    target_lang: str = ""
    provider: str = ""


class DatasetOut(BaseModel):
    dataset_id: str
    version: int
    created_at: str
    filters: dict
    example_count: int
    sha256: str
    path: str


class GameRegister(BaseModel):
    source_path: str
    name: str = ""
    game_id: str = ""


class GameOut(BaseModel):
    game_id: str
    name: str
    source_path: str
    output_path: str = ""
    detected_engine: str
    engine_version: str = ""
    source_lang: str = "ja"
    target_lang: str = "es"
    source_hash: str = ""
    extractor_version: str = ""
    exporter_version: str = ""
    manifest: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    counts: dict = Field(default_factory=dict)


class GameDetect(BaseModel):
    path: str


class DetectionOut(BaseModel):
    engine: str
    confidence: float
    version: str = ""
    evidence: list = Field(default_factory=list)


class GameTextOut(BaseModel):
    id: str
    game_id: str
    file_path: str
    source_text: str
    text_type: str
    speaker: str
    scene: str
    position: int
    original_hash: str
    translatable: bool
    skip_reason: str = ""
    tokens: list = Field(default_factory=list)
    status: str
    machine_translation: str = ""
    corrected_translation: str = ""
    job_id: str = ""


class GameTranslateIn(BaseModel):
    ids: list[str] = Field(default_factory=list)
    provider: str = "magi"
    model: str = ""


class GameExportIn(BaseModel):
    output_path: str = ""
    local: bool = False


class ImageAssetOut(BaseModel):
    id: str
    game_id: str
    file_path: str
    relpath: str
    original_hash: str = ""
    width: int = 0
    height: int = 0
    format: str = ""
    likely_text: bool = True
    skip_reason: str = ""
    ocr_status: str = "DISCOVERED"
    localization_status: str = "DISCOVERED"
    ocr_engine: str = ""
    provider: str = ""
    model: str = ""


class ImageRegionOut(BaseModel):
    id: str
    image_id: str
    region_index: int = 0
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    polygon: list = Field(default_factory=list)
    source_text: str = ""
    confidence: float | None = None
    orientation: str = "horizontal"
    reading_order: int = 0
    group_id: str = ""
    text_type: str = "dialogue"
    speaker: str = ""
    translatable: bool = True
    status: str = "EXTRACTED"
    machine_translation: str = ""
    corrected_translation: str = ""
    job_id: str = ""
    style: dict = Field(default_factory=dict)


class ImageDetailOut(ImageAssetOut):
    regions: list[ImageRegionOut] = Field(default_factory=list)


class ImageOcrIn(BaseModel):
    engine: str = ""


class ImageTranslateIn(BaseModel):
    region_ids: list[str] = Field(default_factory=list)
    provider: str = "magi"
    model: str = ""


class ImageLocalizeIn(BaseModel):
    local: bool = False
