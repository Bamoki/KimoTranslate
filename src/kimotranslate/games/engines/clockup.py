"""Extractor/exportador ClockUp (engine YU-RIS): .ybn sueltos o dentro de .ypf.

YU-RIS verificado: Euphoria (VNDB). Otros ClockUp de la era comparten engine,
pero cada juego trae su XOR key y opcodes propios -> se guardan por fichero
en el manifest (repack imposible sin ellos). Si un juego no es YU-RIS, el
detector devuelve UNKNOWN y este extractor no lo toca.
"""

from __future__ import annotations

import hashlib
import os

from ..models import DetectionResult, ExtractedText, TextStatus, TextType
from ..tokens import find_tokens
from ..yuris import ypf, ystb

ENGINE = "clockup"
EXTRACTOR_VERSION = "yuris-ystb@1"
EXPORTER_VERSION = "yuris-ystb@1"


def detect(game_path: str) -> DetectionResult:
    """Evidencia real: exe, ypf, ybn con magia YSTB. Nada por nombre."""
    evidence, hits = [], 0
    try:
        names = os.listdir(game_path)
    except OSError:
        return DetectionResult("unknown", 0.0, evidence=("unreadable",))
    lower = [n.lower() for n in names]
    if "yu-ris.exe" in lower:
        evidence.append("yu-ris.exe")
        hits += 2
    ypfs = [n for n in lower if n.endswith(".ypf")]
    if "ysbin.ypf" in ypfs or any("ysbin" in n for n in lower):
        evidence.append("ysbin.ypf|ysbin/")
        hits += 2
    elif ypfs:
        evidence.append(f"ypf:{ypfs[0]}")
        hits += 1
    else:
        # Variante real (Natsu no Kusari et al.): .ypf solo dentro de pac/.
        # Escaneo acotado (1 nivel) con magia YPF verificada, no por nombre.
        nested = _find_nested_ypf(game_path)
        if nested:
            evidence.append(f"ypf:{nested[0]}")
            hits += 2
    if "pac" in lower:
        evidence.append("pac/")
        hits += 1
    magic_hit = ""
    for root, _, files in os.walk(game_path):
        for f in files:
            if not f.lower().endswith(".ybn"):
                continue
            p = os.path.join(root, f)
            try:
                with open(p, "rb") as fh:
                    head = fh.read(4)
            except OSError:
                continue
            if head == ystb.MAGIC:
                magic_hit = os.path.relpath(p, game_path)
                break
        if magic_hit:
            break
    if magic_hit:
        evidence.append(f"YSTB:{magic_hit}")
        hits += 2
    if hits >= 4:
        return DetectionResult(ENGINE, 0.99, version="yuris", evidence=tuple(evidence))
    if hits >= 2:
        return DetectionResult(ENGINE, 0.6, version="yuris?", evidence=tuple(evidence))
    return DetectionResult("unknown", 0.0, evidence=tuple(evidence or ("no-evidence",)))


def _find_nested_ypf(game_path: str) -> list[str]:
    """Archivos .ypf un nivel bajo raíz con magia YPF\x00 real. Acotado a
    subdirectorios directos para no recorrer ISOs/BGs gigantes."""
    try:
        subs = [d for d in os.listdir(game_path) if os.path.isdir(os.path.join(game_path, d))]
    except OSError:
        return []
    found = []
    for sub in sorted(subs):
        try:
            files = os.listdir(os.path.join(game_path, sub))
        except OSError:
            continue
        for f in sorted(files):
            if not f.lower().endswith(".ypf"):
                continue
            p = os.path.join(game_path, sub, f)
            try:
                with open(p, "rb") as fh:
                    if fh.read(4) == ypf.MAGIC:
                        found.append(os.path.join(sub, f))
            except OSError:
                continue
    return found


def _iter_ybn(game_path: str) -> list[tuple[str, bytes]]:
    """(relpath, bytes crudos): sueltos primero; si no hay, desde .ypf."""
    found = []
    for root, _, files in os.walk(game_path):
        for f in sorted(files):
            if f.lower().endswith(".ybn"):
                p = os.path.join(root, f)
                with open(p, "rb") as fh:
                    found.append((os.path.relpath(p, game_path), fh.read()))
    if found:
        return found
    for root, _, files in os.walk(game_path):
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
                if e.name.lower().endswith(".ybn"):
                    found.append((e.name, ypf.extract_entry(data, e, version)))
    return found


def _resolve_key(data: bytes, hint: int = 0) -> int:
    if hint:
        ystb.decrypt(data, hint)  # valida
        return hint
    try:
        return ystb.guess_key(data)
    except ystb.YstbError:
        pass
    for k in ystb.DEFAULT_KEYS:
        try:
            ystb.decrypt(data, k)
            return k
        except ystb.YstbError:
            continue
    raise ystb.YstbError("unknown xor key")


def extract(
    game_id: str, game_path: str, hints: dict | None = None
) -> tuple[list[ExtractedText], dict]:
    """Devuelve (textos, fileinfo {relpath: {key, msg_op, call_op, sha}})."""
    hints = hints or {}
    defaults = hints.get("*", {})
    texts, fileinfo = [], {}
    for relpath, raw in _iter_ybn(game_path):
        if raw[:4] != ystb.MAGIC:
            continue  # YSCM/YSER/etc: metadatos, no escenario (§30: fuera)
        hint = {**defaults, **(hints.get(relpath) or {})}
        try:
            key = _resolve_key(raw, hint.get("key", 0))
            script = ystb.parse(raw, key)
        except ystb.YstbError:
            continue
        msg_op = hint.get("msg_op", -1)
        call_op = hint.get("call_op", -1)
        if msg_op < 0 or call_op < 0:
            msg_op, call_op = ystb.guess_ops(script, msg_op, call_op)
        fileinfo[relpath] = {
            "key": key,
            "msg_op": msg_op,
            "call_op": call_op,
            "sha": hashlib.sha256(raw).hexdigest()[:16],
        }
        texts.extend(_classify(game_id, relpath, script, msg_op, call_op))
    return texts, fileinfo


def _classify(
    game_id: str,
    relpath: str,
    script: ystb.Script,
    msg_op: int,
    call_op: int,
) -> list[ExtractedText]:
    out, speaker, slot = [], "", 0
    scene = os.path.splitext(os.path.basename(relpath))[0]

    def emit_raw(raw: bytes, ttype: str, reason: str = "", spk: str = "") -> None:
        """Vía split_controls: controles inline -> {Y#}, binario -> {X#}."""
        nonlocal slot
        tid = f"{ENGINE}:{game_id}:{relpath}:msg:{slot}"
        segments, ctls, junks = ystb.split_controls(raw)
        template, ctls_hex, junks_hex = ystb.build_template(segments, ctls, junks)
        if not template:
            out.append(
                ExtractedText(
                    tid,
                    game_id,
                    relpath,
                    "",
                    ttype,
                    spk or speaker,
                    scene,
                    slot,
                    hashlib.sha1(raw).hexdigest()[:12],
                    "cp932",
                    False,
                    (reason + " " if reason else "") + "binary",
                    [],
                    TextStatus.SKIPPED,
                )
            )
            slot += 1
            return
        text_bytes = b"".join(b for k, b in segments if k == "t")
        ok = ystb.is_jp(text_bytes)
        try:
            digest = hashlib.sha1(template.encode("cp932")).hexdigest()[:12]
        except UnicodeEncodeError:  # nunca silencioso: hash utf-8 + marca
            digest = "u8-" + hashlib.sha1(template.encode("utf-8")).hexdigest()[:9]
            reason = (reason + " " if reason else "") + "non-cp932-source"
        out.append(
            ExtractedText(
                tid,
                game_id,
                relpath,
                template,
                ttype,
                spk or speaker,
                scene,
                slot,
                digest,
                "cp932",
                ok,
                "" if ok else "non-jp",
                find_tokens(template),
                TextStatus.EXTRACTED if ok else TextStatus.SKIPPED,
                metadata={"ctls": ctls_hex, "junks": junks_hex} if ctls or junks else {},
            )
        )
        slot += 1

    def emit(source: str, ttype: str, translatable: bool, reason: str = "", spk: str = "") -> None:
        emit_raw(source.encode("cp932", "replace"), ttype, reason, spk)

    for inst in script.insts:
        if inst.op == call_op and inst.args and inst.args[0].type == 3:
            fname = ystb.decode(inst.args[0].data) or ""
            if fname in ystb.NAME_FUNCS and len(inst.args) > 1:
                speaker = (ystb.decode(inst.args[1].data) or "").strip('"')
                emit(speaker, TextType.SYSTEM, bool(speaker), "" if speaker else "empty-name", "")
            elif fname in ystb.CHOICE_FUNCS:
                for arg in inst.args[1:]:
                    if arg.type == 3 and arg.data not in (b'""', b"''"):
                        emit_raw(arg.data, TextType.CHOICE)
            elif fname in ystb.TEXT_FUNCS:
                for arg in inst.args[1:]:
                    if arg.type == 3 and arg.data not in (b'""', b"''"):
                        emit_raw(arg.data, TextType.SYSTEM)
            continue
        if inst.op == msg_op and len(inst.args) == 1:
            emit_raw(inst.args[0].data, TextType.DIALOGUE)
    return out
