"""Exportador: juego original + traducciones -> árbol localizado.

Seguridad (§15): valida tokens/encoding/estructura, backup del original,
escritura a temporal + verificación (re-parse) + rename atómico. Ante
cualquier fallo el original queda intacto. Estrategia loose-file (el runtime
YU-RIS prefiere sueltos sobre .ypf): sin repack de archives.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime

from . import tokens as game_tokens
from .engines import clockup
from .yuris import ypf, ystb


class ExportError(Exception):
    pass


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _read_source(source_path: str, relpath: str) -> bytes:
    """Bytes originales: suelto si existe; si no, dentro del .ypf que lo contenga."""
    loose = os.path.join(source_path, relpath)
    if os.path.exists(loose):
        with open(loose, "rb") as f:
            return f.read()
    for root, _, files in os.walk(source_path):
        for f in sorted(files):
            if not f.lower().endswith(".ypf"):
                continue
            p = os.path.join(root, f)
            with open(p, "rb") as fh:
                data = fh.read()
            try:
                version, entries = ypf.parse_ypf(data)
            except ypf.YpfError:
                continue
            for e in entries:
                if e.name == relpath:
                    return ypf.extract_entry(data, e, version)
    raise ExportError(f"source not found: {relpath}")


def export_game(source_path: str, output_path: str, bundle: dict) -> dict:
    """bundle = export_bundle() del GameService. Devuelve export manifest."""
    game, texts = bundle["game"], bundle["texts"]
    manifest = game.get("manifest") or {}
    files = {f["relpath"]: f for f in manifest.get("files", [])}
    by_file: dict[str, list] = {}
    for t in texts:
        by_file.setdefault(t["file_path"], []).append(t)

    localized = os.path.join(output_path, "localized")
    backup = os.path.join(output_path, "backup")
    os.makedirs(localized, exist_ok=True)
    os.makedirs(backup, exist_ok=True)

    exported, failed, validations = 0, [], []
    for relpath, items in sorted(by_file.items()):
        info = files.get(relpath)
        if info is None:
            failed.append({"file": relpath, "reason": "no-fileinfo"})
            continue
        try:
            raw = _read_source(source_path, relpath)
        except ExportError as e:
            failed.append({"file": relpath, "reason": f"unreadable: {e}"})
            continue
        # 1-4: validar estructura + cada texto pertenece + tokens + encoding
        try:
            script = ystb.parse(raw, info["key"])
            msg_op, call_op = ystb.guess_ops(script, info["msg_op"], info["call_op"])
        except ystb.YstbError as e:
            failed.append({"file": relpath, "reason": f"parse: {e}"})
            continue
        ordered = sorted(items, key=lambda t: t["position"])
        if _slot_count(script, msg_op, call_op) != len(ordered):
            failed.append({"file": relpath, "reason": "incomplete (slots != finals)"})
            continue
        repack_blobs, ok = [], True
        for t in ordered:
            meta = t.get("metadata", {})
            try:
                blob = ystb.rebuild(t["final"], meta.get("ctls", []), meta.get("junks", []))
            except UnicodeEncodeError:
                failed.append({"file": relpath, "id": t["id"], "reason": "unencodable-cp932"})
                ok = False
                break
            except (ystb.YstbError, ValueError) as e:
                failed.append({"file": relpath, "id": t["id"], "reason": f"rebuild: {e}"})
                ok = False
                break
            if not game_tokens.tokens_ok(t["source"], t["final"]):
                failed.append({"file": relpath, "id": t["id"], "reason": "tokens-mismatch"})
                ok = False
                break
            repack_blobs.append(blob)
        if not ok:
            continue
        # espejo del orden de extracción: slots msg/call en orden de parse
        try:
            new_raw = ystb.repack_bytes(script, repack_blobs, msg_op, call_op, info["key"])
            ystb.parse(new_raw, info["key"])  # 7: verificar re-parse
        except (ystb.YstbError, UnicodeEncodeError, KeyError) as e:
            failed.append({"file": relpath, "reason": f"repack: {e}"})
            continue
        # 5-6: backup (bytes originales) + temporal + rename
        dst = os.path.join(localized, relpath)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        bkp = os.path.join(backup, relpath)
        os.makedirs(os.path.dirname(bkp) or ".", exist_ok=True)
        if not os.path.exists(bkp):
            with open(bkp, "wb") as f:
                f.write(raw)
        tmp = dst + ".tmp"
        with open(tmp, "wb") as f:
            f.write(new_raw)
        os.replace(tmp, dst)
        exported += 1
        validations.append(
            {
                "file": relpath,
                "source_hash": _sha_bytes(raw),
                "output_hash": hashlib.sha256(new_raw).hexdigest()[:16],
            }
        )
    return {
        "game_id": game["game_id"],
        "engine": clockup.ENGINE,
        "source_path": source_path,
        "output_path": output_path,
        "extractor_version": clockup.EXTRACTOR_VERSION,
        "exporter_version": clockup.EXPORTER_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "translation_count": len(texts),
        "exported_files": exported,
        "skipped_count": bundle.get("skipped", 0),
        "failed": failed,
        "files": validations,
    }


def _slot_count(script: ystb.Script, msg_op: int, call_op: int) -> int:
    """Slots que el repack consume: debe igualar los finales del bundle."""
    from .yuris.ystb import TEXT_FUNCS

    n = 0
    for inst in script.insts:
        if inst.op == msg_op and len(inst.args) == 1:
            n += 1
        elif inst.op == call_op and inst.args and inst.args[0].type == 3:
            fname = ystb.decode(inst.args[0].data) or ""
            if fname in TEXT_FUNCS:
                n += sum(1 for a in inst.args[1:] if a.type == 3 and a.data not in (b'""', b"''"))
    return n
