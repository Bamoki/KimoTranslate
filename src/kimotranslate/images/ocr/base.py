"""Interfaz OCR de imágenes. El pipeline no conoce el motor concreto."""

from __future__ import annotations

from typing import Protocol

from ..models import OcrResult


class ImageOcrEngine(Protocol):
    name: str
    version: str

    def detect_text(self, image_path: str) -> OcrResult:
        """Detecta regiones + reconoce texto. Pesado: corre en el worker."""
        ...


class OcrError(Exception):
    pass
