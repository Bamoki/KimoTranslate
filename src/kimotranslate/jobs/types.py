"""Vocabulario de jobs Kimo. Los jobs VIVEN en el Hub (method=custom,
domain=translation); aquí solo el tipo viaja en name/metrics."""

from enum import StrEnum


class JobType(StrEnum):
    TRANSLATE_TEXT = "TRANSLATE_TEXT"
    EXTRACT_GAME = "EXTRACT_GAME"
    EXPORT_GAME = "EXPORT_GAME"
    OCR_IMAGE = "OCR_IMAGE"
    LOCALIZE_IMAGE = "LOCALIZE_IMAGE"
    OCR = "OCR"
    TRANSLATE_IMAGE = "TRANSLATE_IMAGE"
    INPAINT_IMAGE = "INPAINT_IMAGE"
    RENDER_IMAGE = "RENDER_IMAGE"
    BUILD_DATASET = "BUILD_DATASET"
