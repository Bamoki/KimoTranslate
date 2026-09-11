"""Chequeo/descarga de actualizaciones (stdlib, sin tkinter: testeable).

El .exe principal nunca se reemplaza a sí mismo: descarga a temporal,
verifica SHA-256 y delega en KimoTranslate-Updater.exe.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from datetime import UTC, datetime


class UpdateError(Exception):
    pass


def parse_version(v: str) -> tuple[int, ...]:
    """Semver MAJOR.MINOR.PATCH. Inválida -> ValueError (se ignora, no se rompe)."""
    parts = str(v).strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"bad version {v!r}")
    return tuple(int(p) for p in parts)


def is_newer(installed: str, latest: str) -> bool:
    try:
        return parse_version(latest) > parse_version(installed)
    except ValueError:
        return False


def fetch_manifest(server_url: str, timeout: float = 10.0) -> dict:
    url = server_url.rstrip("/") + "/api/downloads/kimotranslate/manifest.json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            manifest = json.loads(res.read().decode("utf-8"))
    except Exception as e:
        raise UpdateError(f"manifest unreachable: {e}") from e
    for key in ("latest_version", "filename", "sha256"):
        if not manifest.get(key):
            raise UpdateError(f"manifest inválido: falta {key}")
    try:
        parse_version(manifest["latest_version"])
    except ValueError as e:
        raise UpdateError(f"manifest inválido: {e}") from e
    if "/" in manifest["filename"] or "\\" in manifest["filename"]:
        raise UpdateError("manifest inválido: filename con path")
    return manifest


def download(server_url: str, filename: str, dest_dir: str = "", timeout: float = 60.0) -> str:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise UpdateError("filename inseguro")
    url = server_url.rstrip("/") + "/api/downloads/kimotranslate/" + filename
    dest = os.path.join(dest_dir or tempfile.gettempdir(), filename + ".part")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res, open(dest, "wb") as f:
            while True:
                chunk = res.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        raise UpdateError(f"download failed: {e}") from e
    return dest


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: str, expected_sha256: str) -> None:
    if sha256_file(path).lower() != expected_sha256.lower():
        raise UpdateError("checksum mismatch: se conserva la instalación actual")


def should_auto_check(last_check: str, now: str = "") -> bool:
    """Una vez al día como máximo."""
    if not last_check:
        return True
    try:
        last = datetime.fromisoformat(last_check)
        cur = datetime.fromisoformat(now) if now else datetime.now(UTC)
        return (cur - last).total_seconds() >= 86400
    except ValueError:
        return True
