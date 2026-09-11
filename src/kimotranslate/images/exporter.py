"""Export de imágenes localizadas al árbol del juego (loose override).

Valida: original/localized existen, dimensiones iguales, formato válido,
regiones con traducción, tokens preservados. Backup + rollback por fichero.
"""

from __future__ import annotations

import os
import shutil

PASS, WARNING, FAIL = "PASS", "WARNING", "FAIL"


def quality_checks(original_path: str, localized_path: str, regions: list[dict]) -> list[dict]:
    from PIL import Image

    try:
        with Image.open(original_path) as a, Image.open(localized_path) as b:
            a.load()
            b.load()
            return quality_checks_pil(a, b, regions)
    except Exception as e:  # noqa: BLE001
        return [{"check": "open", "result": FAIL, "detail": str(e)[:200]}]


def quality_checks_pil(orig, localized, regions: list[dict]) -> list[dict]:
    from ..games import tokens as game_tokens

    checks = [{"check": "dimensions", "result": PASS if orig.size == localized.size else FAIL}]
    checks.append(
        {
            "check": "alpha",
            "result": PASS if (orig.mode == localized.mode or "A" in orig.mode) else WARNING,
        }
    )
    missing = [r["id"] for r in regions if r.get("translatable", True) and not r.get("final")]
    checks.append(
        {"check": "translations", "result": PASS if not missing else FAIL, "missing": missing}
    )
    bad_tokens = [
        r["id"]
        for r in regions
        if r.get("final") and not game_tokens.tokens_ok(r.get("source", ""), r["final"])
    ]
    checks.append(
        {"check": "tokens", "result": PASS if not bad_tokens else FAIL, "mismatch": bad_tokens}
    )
    return checks


def export_images(game_source: str, output_path: str, items: list[dict]) -> dict:
    """items: [{relpath, localized_path, original_path, regions[{id,source,final,
    translatable}]}]. Copia localized sobre output/... + backup del original."""
    localized_dir = os.path.join(output_path, "localized")
    backup_dir = os.path.join(output_path, "backup")
    exported, failed = [], []
    for it in items:
        rel = it["relpath"]
        dst = os.path.join(localized_dir, rel)
        try:
            checks = quality_checks(
                it["original_path"], it["localized_path"], it.get("regions", [])
            )
        except Exception as e:  # noqa: BLE001
            failed.append({"file": rel, "reason": str(e)[:200]})
            continue
        if any(c["result"] == FAIL for c in checks):
            failed.append(
                {
                    "file": rel,
                    "reason": ";".join(c["check"] for c in checks if c["result"] == FAIL),
                    "checks": checks,
                }
            )
            continue
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        bkp = os.path.join(backup_dir, rel)
        os.makedirs(os.path.dirname(bkp) or ".", exist_ok=True)
        if not os.path.exists(bkp):
            shutil.copy2(it["original_path"], bkp)
        tmp = dst + ".tmp"
        shutil.copy2(it["localized_path"], tmp)
        os.replace(tmp, dst)
        exported.append({"file": rel, "checks": checks})
    return {
        "exported": exported,
        "failed": failed,
        "exported_count": len(exported),
        "failed_count": len(failed),
    }
