"""Games: tarjetas por juego con progreso y acciones con jerarquía."""

import customtkinter as ctk

from ..client import friendly_message
from ..components.badges import ProgressBar, StatusBadge, progress_counts
from ..components.dialogs import EmptyState, ErrorDialog


class GameCard(ctk.CTkFrame):
    def __init__(self, master, app, game: dict) -> None:
        super().__init__(
            master,
            fg_color=app.theme.get("surface"),
            corner_radius=10,
            border_width=1,
            border_color=app.theme.get("border"),
        )
        self.app = app
        theme = app.theme
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            top,
            text=game.get("name", game.get("game_id", "?")),
            font=("Segoe UI", 14, "bold"),
            text_color=theme.get("text"),
        ).pack(side="left")
        StatusBadge(
            top, theme, "READY" if game.get("detected_engine") != "unknown" else "WARNING"
        ).pack(side="right")
        counts = game.get("counts") or {}
        done, total = progress_counts(counts)
        info = (
            f"{game.get('detected_engine', '?')} · {game.get('source_lang', 'ja')}→"
            f"{game.get('target_lang', 'es')}"
        )
        ctk.CTkLabel(
            self, text=info, font=("Segoe UI", 11), text_color=theme.get("text_secondary")
        ).pack(anchor="w", padx=12)
        bar = ProgressBar(self, theme)
        bar.pack(fill="x", padx=12, pady=6)
        bar.set(done, total)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))
        gid = game["game_id"]
        # Acción primaria con peso; secundarias sutiles.
        ctk.CTkButton(
            row,
            text="Abrir",
            width=90,
            fg_color=theme.get("accent"),
            hover_color=theme.get("accent_hover"),
            command=lambda: app.navigate("game_detail:" + gid),
        ).pack(side="left", padx=4)
        self._extract_btn = ctk.CTkButton(
            row,
            text="Extraer",
            width=90,
            fg_color="transparent",
            border_width=1,
            text_color=theme.get("text"),
            command=lambda: self._extract(gid),
        )
        self._extract_btn.pack(side="left", padx=4)
        self._translate_btn = ctk.CTkButton(
            row,
            text="Traducir",
            width=90,
            fg_color="transparent",
            border_width=1,
            text_color=theme.get("text"),
            command=lambda: self._translate(gid),
        )
        self._translate_btn.pack(side="left", padx=4)

    def _set_busy(self, busy: bool) -> None:
        import tkinter as _tk

        try:
            if not self.winfo_exists():
                return
            state = "disabled" if busy else "normal"
            self._extract_btn.configure(state=state)
            self._translate_btn.configure(state=state)
        except _tk.TclError:
            pass  # tarjeta destruida al navegar antes de terminar

    def _extract(self, gid: str) -> None:
        self._set_busy(True)
        self.app.run_async(
            lambda: self.app.api.extract_game(gid),
            on_done=lambda r: (self._set_busy(False), self.app.toast(f"Extracción: {r}")),
            on_error=lambda e: (self._set_busy(False), self._err("Extraer", e)),
            status=f"Extrayendo {gid}…",
        )

    def _translate(self, gid: str) -> None:
        self._set_busy(True)
        self.app.run_async(
            lambda: self.app.api.translate_game(gid),
            on_done=lambda r: (self._set_busy(False), self.app.toast(f"Traducción: {r}")),
            on_error=lambda e: (self._set_busy(False), self._err("Traducir", e)),
            status=f"Traduciendo {gid}…",
        )

    def _translate(self, gid: str) -> None:
        self.app.run_async(
            lambda: self.app.api.translate_game(gid),
            on_done=lambda r: self.app.toast(f"Translate: {r}"),
            on_error=lambda e: self._err("Translate", e),
            status=f"Translate {gid}…",
        )

    def _err(self, action: str, e: Exception) -> None:
        msg, details = friendly_message(action, e)
        ErrorDialog(self, self.app.theme, action + " failed", msg, details)


class GamesView(ctk.CTkScrollableFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        theme = app.theme
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            head, text="Juegos", font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        ).pack(side="left")
        ctk.CTkButton(
            head,
            text="+ Añadir juego",
            width=110,
            fg_color=theme.get("accent"),
            command=self._add_dialog,
        ).pack(side="right")
        self._list = ctk.CTkFrame(self, fg_color="transparent")
        self._list.pack(fill="both", expand=True)
        app.run_async(
            app.api.games, on_done=self._render, on_error=self._fail, status="Cargando juegos…"
        )

    def _render(self, games: list) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        if not games:
            EmptyState(
                self._list,
                self.app.theme,
                "Sin juegos",
                "Añade un directorio de juego para empezar.",
                "Añadir juego",
                self._add_dialog,
            ).pack(fill="x")
            return
        for g in games:
            GameCard(self._list, self.app, g).pack(fill="x", pady=6)

    def _fail(self, e: Exception) -> None:
        msg, details = friendly_message("Cargar juegos", e)
        EmptyState(self._list, self.app.theme, msg, details).pack(fill="x")

    def _add_dialog(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Añadir juego")
        win.geometry("460x180")
        win.transient(self.winfo_toplevel())
        ctk.CTkLabel(win, text="Carpeta del juego (en el Worker):").pack(
            padx=16, pady=(12, 2), anchor="w"
        )
        entry = ctk.CTkEntry(win, width=400)
        entry.pack(padx=16)
        entry.focus_set()
        try:
            import os

            roots = [
                p for p in os.environ.get("KIMOTRANSLATE_GAME_ROOTS", "").split(os.pathsep) if p
            ]
            if roots:
                entry.insert(0, roots[0])
        except OSError:
            pass

        def _go(event=None):
            path = entry.get().strip()
            if not path:
                return
            win.destroy()
            self.app.run_async(
                lambda: self.app.api.add_game(path),
                on_done=lambda g: self.app.navigate("game_detail:" + g["game_id"]),
                on_error=lambda e: self._fail(e),
                status="Detectando juego…",
            )

        entry.bind("<Return>", _go)
        ctk.CTkButton(win, text="Detectar", command=_go).pack(pady=12)
        win.grab_set()
