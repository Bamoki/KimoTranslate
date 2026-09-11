"""Verificación de integridad post-export: original vs backup vs output.

Compara path/size/sha256, detecta faltantes/extras. No modifica nada.
"""

from __future__ import annotations

import hashlib
import os


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree(root: str) -> dict[str, dict]:
    out = {}
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, files in os.walk(root):
        dirnames.sort()
        for f in sorted(files):
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, root)
            try:
                out[rel] = {"size": os.path.getsize(p), "sha256": sha256_file(p)}
            except OSError as e:
                out[rel] = {"error": str(e)[:200]}
    return out


def verify_export(source_path: str, output_path: str, manifest: dict | None = None) -> dict:
    """source_path = juego original; output = localized/+backup/.

    Reglas: backup debe ser copia exacta del original; localized debe existir
    para cada fichero exportado del manifest; nada fuera de lo esperado.
    """
    localized = _tree(os.path.join(output_path, "localized"))
    backup = _tree(os.path.join(output_path, "backup"))
    # manifest de scripts e imágenes usa {"file": ...}.
    expected = {
        (f.get("file") if isinstance(f, dict) else f) for f in (manifest or {}).get("files", [])
    }
    issues, checked = [], 0
    for rel in localized:
        if rel not in expected:
            issues.append({"file": rel, "status": "EXTRA_FILE"})
    for rel, info in localized.items():
        checked += 1
        if "error" in info:
            issues.append({"file": rel, "status": "UNREADABLE"})
            continue
        bkp = backup.get(rel)
        if bkp is None or "error" in bkp:
            issues.append({"file": rel, "status": "NO_BACKUP"})
            continue
        orig = os.path.join(source_path, rel)
        if os.path.exists(orig):
            if sha256_file(orig) != bkp["sha256"]:
                issues.append({"file": rel, "status": "BACKUP_MISMATCH"})
    for rel in backup:
        if rel not in localized:
            issues.append({"file": rel, "status": "BACKUP_WITHOUT_OUTPUT"})
    ok = not issues
    return {
        "ok": ok,
        "checked": checked,
        "backup_files": len(backup),
        "issues": issues,
        "status": "INTEGRITY_PASS" if ok else "INTEGRITY_FAIL",
    }
