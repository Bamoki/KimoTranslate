"""Release manifest: qué versiones produjeron una traducción/export."""

from __future__ import annotations

from datetime import UTC, datetime

from . import __version__ as KIMO_VERSION
from .engines.magi_engine import PROMPT_NAME, PROMPT_VERSION
from .games.engines.clockup import EXPORTER_VERSION, EXTRACTOR_VERSION
from .images.inpaint import INPAINT_VERSION
from .images.renderer import RENDERER_VERSION


def build_manifest(extra: dict | None = None) -> dict:
    import sys

    try:
        import PIL

        pil_v = PIL.__version__
    except ImportError:
        pil_v = "missing"
    try:
        import numpy

        numpy_v = numpy.__version__
    except ImportError:
        numpy_v = "missing"
    manifest = {
        "version": KIMO_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "pipeline_version": "translate@4",
        "prompt_version": f"{PROMPT_NAME}@v{PROMPT_VERSION}",
        "extractor_version": EXTRACTOR_VERSION,
        "exporter_version": EXPORTER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "inpaint_version": INPAINT_VERSION,
        "pillow": pil_v,
        "numpy": numpy_v,
        "games": [],
        "providers": [],
        "datasets": [],
        "artifacts": [],
    }
    if extra:
        manifest.update(extra)
    return manifest
