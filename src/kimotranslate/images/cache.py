"""Cache visual: clave sobre todo lo que invalida el resultado.

Sin base nueva: la clave vive en el manifest del asset; los artefactos en
{data_dir}/images/{image_id}/. HIT = no re-ejecutar la etapa.
"""

from __future__ import annotations

import hashlib
import json
import os


def image_key(
    image_hash: str,
    ocr_engine: str,
    ocr_version: str,
    ocr_config: str,
    translations_blob: str,
    renderer_version: str,
    inpaint_version: str,
) -> str:
    raw = "|".join(
        [
            image_hash,
            ocr_engine,
            ocr_version,
            ocr_config,
            translations_blob,
            renderer_version,
            inpaint_version,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def translations_blob(finals: list[tuple[str, str]]) -> str:
    """Huella de (region_id, final). Cambia una traducción -> cambia la clave."""
    return hashlib.sha256(json.dumps(sorted(finals), ensure_ascii=False).encode()).hexdigest()[:16]


def artifact_dir(data_dir: str, image_id: str) -> str:
    d = os.path.join(data_dir, "images", image_id)
    os.makedirs(d, exist_ok=True)
    return d


ARTIFACTS = (
    "original.png",
    "ocr.json",
    "translation.json",
    "mask.png",
    "localized.png",
    "manifest.json",
)


def write_versioned(base: str, name: str, data: bytes) -> None:
    """Guarda conservando la versión anterior como *_prev (rollback mínimo)."""
    import os

    dst = os.path.join(base, name)
    if os.path.exists(dst):
        stem, ext = os.path.splitext(name)
        prev = os.path.join(base, f"{stem}_prev{ext}")
        if os.path.exists(prev):
            os.remove(prev)
        os.replace(dst, prev)
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dst)
