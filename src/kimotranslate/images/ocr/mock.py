"""OCR determinista para tests/smoke de arquitectura.

Las regiones se registran por hash de imagen (el fixture dice qué texto hay
dónde). El OCR real (Tradujap manga-ocr/paddle) vive en el worker con GPU.
"""

from __future__ import annotations

from ..models import OcrRegion, OcrResult


class MockOcrEngine:
    name = "mock"
    version = "0.1"

    def __init__(self, regions_by_hash: dict | None = None) -> None:
        self.regions_by_hash = regions_by_hash or {}
        self.calls = 0

    def detect_text(self, image_path: str) -> OcrResult:
        from ...images import detector as _det

        self.calls += 1
        key = _det.file_hash(image_path)
        regions = [OcrRegion(**r) for r in self.regions_by_hash.get(key, [])]
        return OcrResult(regions=regions, engine=self.name, version=self.version)
