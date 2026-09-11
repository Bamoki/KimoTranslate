"""RC validation para juegos reales (corre en Windows, sin servidor).

Uso:
    python scripts/rc_validate_game.py "D:\\Juegos\\Euphoria" --game-id euphoria

Hace: detect -> extract (suelto o .ypf) -> stats -> IDs deterministas ->
re-extract (diff) -> sample de textos -> report JSON por stdout.
NO traduce, NO modifica nada. Solo lee.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kimotranslate.games.engines import clockup


def main() -> int:
    ap = argparse.ArgumentParser(description="RC: valida un juego real (solo lectura)")
    ap.add_argument("path", help="carpeta del juego instalado")
    ap.add_argument("--game-id", default="", help="id (default: nombre de carpeta)")
    ap.add_argument("--sample", type=int, default=5, help="textos de muestra")
    ap.add_argument("--msg-op", type=int, default=-1, help="override opcode msg")
    ap.add_argument("--call-op", type=int, default=-1, help="override opcode call")
    args = ap.parse_args()

    game_id = args.game_id or os.path.basename(os.path.normpath(args.path)).lower()
    report: dict = {"game_id": game_id, "path": args.path}
    det = clockup.detect(args.path)
    report["detection"] = {
        "engine": det.engine,
        "confidence": det.confidence,
        "version": det.version,
        "evidence": list(det.evidence),
    }
    if det.engine != clockup.ENGINE:
        report["status"] = "UNSUPPORTED_ENGINE"
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 2
    hints = {"*": {"msg_op": args.msg_op, "call_op": args.call_op}}
    texts, fileinfo = clockup.extract(game_id, args.path, hints)
    report["extraction"] = {
        "files": len(fileinfo),
        "texts": len(texts),
        "translatable": sum(1 for t in texts if t.translatable),
        "skipped": sum(1 for t in texts if not t.translatable),
        "fileinfo": {
            k: {kk: (hex(v) if kk == "key" else v) for kk, v in fi.items()}
            for k, fi in fileinfo.items()
        },
    }
    # re-extract: IDs estables
    texts2, _ = clockup.extract(game_id, args.path, hints)
    report["reextract"] = {"stable_ids": [t.id for t in texts] == [t.id for t in texts2]}
    report["sample"] = [
        {"id": t.id, "type": t.text_type, "speaker": t.speaker, "text": t.source_text[:120]}
        for t in texts[: args.sample]
    ]
    report["status"] = "PIPELINE_PASS_ANALYSIS"
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
