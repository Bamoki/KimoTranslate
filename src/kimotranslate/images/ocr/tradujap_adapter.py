"""Adaptador al OCR existente de Tradujap (detect + recognize). Sin copiar nada.

Uso (worker con checkout de Tradujap + modelos):
    engine = TradujapOcrEngine(detector="paddle", recognizer="manga_ocr")
Requiere TRADUJAP_SERVER_SRC en sys.path (o mismo layout /home/bamoki/projects).
Sin Tradujap o sin modelos: OcrError explicando qué falta.
"""

from __future__ import annotations

import os
import sys

from ..models import OcrRegion, OcrResult
from .base import OcrError

_TRADUJAP_SRC = os.environ.get("TRADUJAP_SERVER_SRC", "/home/bamoki/projects/tradujap/server/src")


class TradujapOcrEngine:
    name = "tradujap"
    version = "adapter-1"

    def __init__(self, detector: str = "paddle", recognizer: str = "manga_ocr") -> None:
        if _TRADUJAP_SRC not in sys.path:
            sys.path.insert(0, _TRADUJAP_SRC)
        try:
            from tradujap_server.detect import base as _det
            from tradujap_server.ocr import base as _ocr
        except ImportError as e:
            raise OcrError(f"tradujap_server no importable ({_TRADUJAP_SRC}): {e}") from e
        self._detect_mod, self._ocr_mod = _det, _ocr
        self._detector_name, self._recognizer_name = detector, recognizer
        self._recognizer = None
        self._detect_blocks = None

    def _engines(self):
        if self._recognizer is None:
            try:
                import tradujap_server.detect.detect as _dd

                self._detect_blocks = _dd.detect_blocks
                self._recognizer = self._ocr_mod.build_engine(self._recognizer_name)
            except Exception as e:  # noqa: BLE001 - ImportError/KeyError/OcrEngineError
                raise OcrError(f"motor tradujap no disponible: {e}") from e
        return self._recognizer

    def detect_text(self, image_path: str) -> OcrResult:
        import time

        from PIL import Image

        started = time.time()
        recognizer = self._engines()
        with Image.open(image_path) as im:
            w, h = im.size
            rgb = im.convert("RGB")
            blocks = self._detect_blocks(rgb, engine=self._detector_name)
        regions = []
        with Image.open(image_path) as im:
            rgb = im.convert("RGB")
            for b in blocks:
                x, y = int(b.x0 * w), int(b.y0 * h)
                bw, bh = int((b.x1 - b.x0) * w), int((b.y1 - b.y0) * h)
                if bw < 4 or bh < 4:
                    continue
                res = recognizer.recognize(rgb.crop((x, y, x + bw, y + bh)))
                if not res.text.strip():
                    continue
                regions.append(
                    OcrRegion(
                        x=x,
                        y=y,
                        w=bw,
                        h=bh,
                        text=res.text.strip(),
                        confidence=res.confidence if res.confidence is not None else b.confidence,
                        orientation="vertical" if bh > bw * 1.2 else "horizontal",
                    )
                )
        return OcrResult(
            regions=regions,
            engine=f"tradujap:{self._recognizer_name}",
            version=self.version,
            duration_ms=(time.time() - started) * 1000,
        )
