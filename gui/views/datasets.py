"""Datasets: lista + construir desde ejemplos validados."""

import customtkinter as ctk

from ..client import friendly_message
from ..components.dialogs import EmptyState


class DatasetsView(ctk.CTkScrollableFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        theme = app.theme
        ctk.CTkLabel(
            self, text="Datasets", font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        ).pack(anchor="w", padx=8)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=6)
        self.source_app = ctk.CTkComboBox(row, values=["kimotranslate", "tradujap"], width=150)
        self.source_app.set("kimotranslate")
        self.source_app.pack(side="left", padx=4)
        self.domain = ctk.CTkEntry(row, placeholder_text="domain", width=160)
        self.domain.pack(side="left", padx=4)
        ctk.CTkButton(
            row, text="Build dataset", width=130, fg_color=theme.get("accent"), command=self._build
        ).pack(side="left", padx=4)
        self._list = ctk.CTkFrame(self, fg_color="transparent")
        self._list.pack(fill="both", expand=True, padx=8)
        self._load()

    def _load(self) -> None:
        self.app.run_async(
            self.app.api.datasets,
            on_done=self._render,
            on_error=self._fail,
            status="Cargando datasets…",
        )

    def _render(self, items: list) -> None:
        theme = self.app.theme
        for child in self._list.winfo_children():
            child.destroy()
        if not items:
            EmptyState(
                self._list, theme, "No datasets", "Valida correcciones y construye el primero."
            ).pack(fill="x")
            return
        for d in items:
            card = ctk.CTkFrame(self._list, fg_color=theme.get("surface"), corner_radius=8)
            card.pack(fill="x", pady=3)
            ctk.CTkLabel(
                card,
                text=f"{d.get('dataset_id')} v{d.get('version')}",
                font=("Segoe UI", 12, "bold"),
            ).pack(side="left", padx=10)
            ctk.CTkLabel(
                card,
                text=f"{d.get('example_count')} ejemplos · {d.get('sha256', '')[:12]}",
                font=("Segoe UI", 11),
                text_color=theme.get("text_secondary"),
            ).pack(side="left")

    def _fail(self, e: Exception) -> None:
        msg, details = friendly_message("Datasets", e)
        EmptyState(self._list, self.app.theme, msg, details).pack(fill="x")

    def _build(self) -> None:
        body = {"source_app": self.source_app.get(), "domain": self.domain.get().strip()}
        self.app.run_async(
            lambda: self.app.api.build_dataset(body),
            on_done=lambda r: (
                self.app.toast(f"Dataset v{r.get('version')} ({r.get('example_count')})"),
                self._load(),
            ),
            on_error=lambda e: self.app.toast(str(e), error=True),
            status="Construyendo dataset…",
        )
