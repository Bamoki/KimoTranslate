"""Shell principal: sidebar + topbar + contenido + estado + toasts.

Operaciones largas en hilos (la GUI nunca se congela); el worker remoto
sigue en el Hub. Sin modelos en la GUI.
"""

import queue
import threading

import customtkinter as ctk

from . import update as update_mod
from .client import KimoApiClient, friendly_message
from .components.shell import Sidebar, Statusbar, Topbar
from .theme.theme import Theme
from .tkinter import config as config_mod


class App(ctk.CTk):
    def __init__(self, api: KimoApiClient, version: str = "0.8.1") -> None:
        super().__init__()
        self.api = api
        self.version = version
        self.cfg_mod = config_mod
        try:
            self.cfg = config_mod.load()
        except OSError:
            self.cfg = config_mod.defaults()
        import os as _os

        if _os.environ.get("KIMOTRANSLATE_SERVER_URL"):
            self.cfg["server_url"] = _os.environ["KIMOTRANSLATE_SERVER_URL"]
        self.api.base_url = self.cfg.get("server_url", api.base_url).rstrip("/")
        self.theme = Theme(self.cfg.get("appearance", "dark"))
        ctk.set_appearance_mode(self.theme.ctk_mode())
        self.title(f"KimoTranslate {version}")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self._tasks: queue.Queue = queue.Queue()
        self._views: dict = {}
        self._current = ""
        self._build()
        self.after(100, self._pump)
        self.after(1500, self._poll_health)
        self.after(2500, self._auto_update_check)
        self.navigate("overview")

    # --- layout ---
    def _build(self) -> None:
        self.topbar = Topbar(self, self.theme)
        self.topbar.pack(fill="x")
        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.pack(fill="both", expand=True)
        self.sidebar = Sidebar(mid, self.theme, self.navigate)
        self.sidebar.pack(side="left", fill="y")
        self.content = ctk.CTkFrame(mid, fg_color=self.theme.get("background"))
        self.content.pack(side="left", fill="both", expand=True, padx=12, pady=12)
        self.statusbar = Statusbar(self, self.theme)
        self.statusbar.pack(fill="x")

    # --- navegación ---
    def navigate(self, key: str) -> None:
        from . import views as _views

        for child in self.content.winfo_children():
            child.destroy()
        param = ""
        if ":" in key:
            key, param = key.split(":", 1)
        self._current = key
        self.sidebar.set_active(key)
        view_cls = _views.REGISTRY.get(key)
        if view_cls is None:
            return
        view = view_cls(self.content, self, param) if param else view_cls(self.content, self)
        view.pack(fill="both", expand=True)
        self._views[key] = view
        titles = {
            "overview": "Resumen",
            "games": "Juegos",
            "translate": "Traducir",
            "images": "Imágenes",
            "review": "Revisar",
            "datasets": "Datasets",
            "jobs": "Tareas",
            "settings": "Ajustes",
            "game_detail": "Juego",
            "editor": "Editor",
        }
        title = titles.get(key, key)
        if param and key in ("game_detail", "editor"):
            title = f"Juego / {param}" if key == "game_detail" else f"Editor / {param}"
        self.topbar.set_location(title)

    # --- tareas en fondo (no bloquean) ---
    def run_async(self, fn, on_done=None, on_error=None, status: str = "") -> None:
        if status:
            self.statusbar.set(status)

        def _target():
            try:
                self._tasks.put(("ok", on_done, fn()))
            except Exception as e:  # noqa: BLE001 -> on_error con mensaje amable
                self._tasks.put(("err", on_error, e))

        threading.Thread(target=_target, daemon=True).start()

    def _pump(self) -> None:
        try:
            while True:
                kind, cb, payload = self._tasks.get_nowait()
                if kind == "ok" and cb:
                    cb(payload)
                elif kind == "err":
                    if cb:
                        cb(payload)
                    else:
                        msg, details = friendly_message("La operación", payload)
                        self.toast(msg, error=True)
                        self.statusbar.set(msg)
                if kind == "ok":
                    self.statusbar.set("Listo")
        except queue.Empty:
            pass
        self.after(100, self._pump)

    # --- salud Hub/Worker ---
    def _poll_health(self) -> None:
        def _check():
            try:
                h = self.api.health()
            except Exception:
                return ("OFFLINE", "OFFLINE")
            hub = "ONLINE" if h.get("hub") == "ok" else "ERROR"
            try:
                jobs = self.api.jobs()
            except Exception:
                return (hub, "OFFLINE")
            running = any(j.get("status") == "RUNNING" for j in jobs)
            return (hub, "BUSY" if running else ("ONLINE" if hub == "ONLINE" else "OFFLINE"))

        def _apply(res):
            self.topbar.hub.set(res[0])
            self.topbar.worker.set(res[1])

        self.run_async(_check, on_done=_apply)
        self.after(15000, self._poll_health)

    # --- toasts ---
    def toast(self, message: str, error: bool = False) -> None:
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        fg = self.theme.get("error") if error else self.theme.get("success")
        ctk.CTkLabel(win, text=message, font=("Segoe UI", 11, "bold"), text_color=fg).pack(
            padx=16, pady=10
        )
        x, y = self.winfo_x() + self.winfo_width() - 320, self.winfo_y() + 60
        win.geometry(f"+{x}+{y}")
        self.after(3500, win.destroy)

    # --- updates (reutiliza gui/update.py) ---
    def _auto_update_check(self) -> None:
        try:
            cfg = config_mod.load()
        except OSError:
            return
        if not cfg.get("auto_update", True):
            return
        if not update_mod.should_auto_check(cfg.get("last_update_check", "")):
            return
        self._check_updates(silent=True)

    def _check_updates(self, silent: bool) -> None:
        from datetime import UTC, datetime

        def _got(manifest):
            try:
                cfg = config_mod.load()
                cfg["last_update_check"] = datetime.now(UTC).isoformat()
                config_mod.save(cfg)
            except OSError:
                pass
            if update_mod.is_newer(self.version, manifest["latest_version"]):
                self._update_dialog(manifest)
            elif not silent:
                self.toast(f"Ya estás en la última ({self.version})")

        def _fail(e):
            if not silent:
                msg, _ = friendly_message("Buscar actualizaciones", e)
                self.toast(msg, error=True)

        base = getattr(self.api, "base_url", "")
        self.run_async(lambda: update_mod.fetch_manifest(base), on_done=_got, on_error=_fail)

    def _update_dialog(self, manifest: dict) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Actualización disponible")
        win.geometry("420x170")
        ctk.CTkLabel(
            win,
            text=f"Nueva versión: {manifest['latest_version']} (instalada: {self.version})",
            font=("Segoe UI", 13, "bold"),
        ).pack(padx=20, pady=16)
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack()
        ctk.CTkButton(
            row,
            text="Actualizar",
            command=lambda: (win.destroy(), self._do_update(manifest)),
            fg_color=self.theme.get("accent"),
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            row, text="Ahora no", command=win.destroy, fg_color="transparent", border_width=1
        ).pack(side="left", padx=6)

    def _do_update(self, manifest: dict) -> None:
        import sys

        def _run():
            part = update_mod.download(self.api.base_url, manifest["filename"])
            update_mod.verify(part, manifest["sha256"])
            return part

        def _got(part):
            updater = self._updater_path()
            if updater is None:
                self.toast("Updater no disponible en modo desarrollo", error=True)
                return
            import subprocess

            args = [
                updater,
                "--current",
                sys.executable,
                "--new",
                part,
                "--sha256",
                manifest["sha256"],
            ]
            try:
                subprocess.Popen(args)
            except OSError as e:
                self.toast(f"No se pudo lanzar updater: {e}", error=True)
                return
            self.destroy()

        def _fail(e):
            msg, _ = friendly_message("Descargar actualización", e)
            self.toast(f"{msg} (instalación intacta)", error=True)
            self.statusbar.set(msg)

        self.run_async(_run, on_done=_got, on_error=_fail, status="Descargando actualización…")

    def _updater_path(self) -> str | None:
        import os
        import sys

        if getattr(sys, "frozen", False):
            cand = os.path.join(os.path.dirname(sys.executable), "KimoTranslate-Updater.exe")
            return cand if os.path.exists(cand) else None
        return None
