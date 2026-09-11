"""Translate: controles + progreso por proveedor, sin detalles internos."""

import customtkinter as ctk

from ..client import friendly_message
from ..components.badges import ProgressBar
from ..components.dialogs import EmptyState


class TranslateView(ctk.CTkScrollableFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        theme = app.theme
        ctk.CTkLabel(
            self, text="Translate", font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        ).pack(anchor="w", padx=8)
        form = ctk.CTkFrame(self, fg_color=theme.get("surface"), corner_radius=10)
        form.pack(fill="x", padx=8, pady=8)
        self.provider = ctk.CTkComboBox(
            form, values=["magi", "ollama", "deepl", "google"], width=130
        )
        self.provider.set("magi")
        self.provider.pack(side="left", padx=8, pady=8)
        self.model = ctk.CTkEntry(form, placeholder_text="Modelo (vacío = default)", width=200)
        self.model.pack(side="left", padx=8)
        self.game = ctk.CTkEntry(form, placeholder_text="Game (vacío = todos)", width=160)
        self.game.pack(side="left", padx=8)
        ctk.CTkButton(
            form, text="Traducir pendientes", fg_color=theme.get("accent"), command=self._go
        ).pack(side="left", padx=8)
        self._bar = ProgressBar(self, theme)
        self._bar.pack(fill="x", padx=8, pady=4)
        self._status = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 11), text_color=theme.get("text_secondary")
        )
        self._status.pack(anchor="w", padx=8)
        self._jobs_box = ctk.CTkFrame(self, fg_color="transparent")
        self._jobs_box.pack(fill="x", padx=8, pady=8)
        self._refresh_jobs()

    def _go(self) -> None:
        gid = self.game.get().strip()
        if not gid:
            self._status.configure(text="Indica un game para traducir sus pendientes")
            return
        self.app.run_async(
            lambda: self.app.api.translate_game(
                gid, provider=self.provider.get(), model=self.model.get().strip()
            ),
            on_done=lambda r: (
                self._status.configure(text=f"queued={r.get('queued')} cached={r.get('cached')}"),
                self._refresh_jobs(),
            ),
            on_error=lambda e: self._fail(e),
            status="Traduciendo…",
        )

    def _refresh_jobs(self) -> None:
        self.app.run_async(self.app.api.jobs, on_done=self._render_jobs, on_error=lambda e: None)

    def _render_jobs(self, jobs: list) -> None:
        theme = self.app.theme
        for child in self._jobs_box.winfo_children():
            child.destroy()
        recent = jobs[:10]
        if not recent:
            EmptyState(self._jobs_box, theme, "No active jobs", "").pack(fill="x")
            return
        for j in recent:
            row = ctk.CTkFrame(self._jobs_box, fg_color=theme.get("surface"), corner_radius=8)
            row.pack(fill="x", pady=3)
            name = (j.get("metrics") or {}).get("request", {}).get("text", "?")[:40]
            ctk.CTkLabel(
                row,
                text=f"{j.get('provider', '?')} · {j.get('status')}",
                font=("Segoe UI", 11, "bold"),
            ).pack(side="left", padx=10)
            ctk.CTkLabel(
                row, text=name, font=("Segoe UI", 11), text_color=theme.get("text_secondary")
            ).pack(side="left")

    def _fail(self, e: Exception) -> None:
        msg, _ = friendly_message("Traducir", e)
        self._status.configure(text=msg)
