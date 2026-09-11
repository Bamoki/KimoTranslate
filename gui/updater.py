"""KimoTranslate-Updater: reemplaza el .exe SIN Python instalado (bundled).

Uso (lo invoca la GUI al cerrar):
    KimoTranslate-Updater.exe --current "C:\\...\\KimoTranslate.exe"
        --new "C:\\...\\KimoTranslate-0.8.1.exe.part" --sha256 <hex>

Flujo: espera salida -> verifica sha -> backup .bak -> reemplaza ->
verifica -> lanza nueva versión -> limpia. Si algo falla, restaura y sale
con mensaje (nunca deja la instalación inutilizable).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str) -> int:
    try:
        import tkinter as _tk
        import tkinter.messagebox as _mb

        root = _tk.Tk()
        root.withdraw()
        _mb.showerror("KimoTranslate Updater", msg)
        root.destroy()
    except Exception:
        print(f"updater error: {msg}", file=sys.stderr)
    return 1


def wait_exit(path: str, timeout_s: float = 30.0) -> bool:
    """Espera a que no exista un proceso con ese ejecutable (Windows)."""
    deadline = time.time() + timeout_s
    current_base = os.path.basename(path).lower()
    while time.time() < deadline:
        if os.name != "nt":
            return True
        try:
            out = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10
            ).stdout.lower()
            if current_base not in out:
                return True
        except Exception:
            return True
        time.sleep(1.0)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args(argv)

    current, new = args.current, args.new
    if not os.path.exists(new):
        return fail(f"descarga no encontrada: {new}")
    if sha256_file(new).lower() != args.sha256.lower():
        return fail("checksum inválido: se conserva la versión actual")
    if not wait_exit(current, args.timeout):
        return fail("KimoTranslate sigue en ejecución; actualiza más tarde")
    backup = current + ".bak"
    try:
        if os.path.exists(backup):
            os.remove(backup)
        if os.path.exists(current):
            os.replace(current, backup)  # backup temporal
        shutil.copy2(new, current)  # reemplazo (no move: conserva .part para auditar)
    except OSError as e:
        try:
            if os.path.exists(backup) and not os.path.exists(current):
                os.replace(backup, current)
        except OSError:
            pass
        return fail(f"reemplazo fallido (rollback intentado): {e}")
    if not os.path.exists(current) or sha256_file(current).lower() != args.sha256.lower():
        try:
            if os.path.exists(backup):
                os.replace(backup, current)
        except OSError:
            pass
        return fail("verificación post-reemplazo fallida: versión anterior restaurada")
    try:
        if os.path.exists(new):
            os.remove(new)
    except OSError:
        pass
    try:
        if os.name == "nt":
            os.startfile(current)  # noqa: S606 (path interno verificado)
        else:
            subprocess.Popen([current])
    except OSError as e:
        return fail(f"actualizado pero no se pudo lanzar: {e} (ejecuta {current})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
