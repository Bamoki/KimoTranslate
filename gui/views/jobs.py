"""Jobs: tarjetas con progreso, filtros y retry solo en FAILED."""

import customtkinter as ctk

from ..client import friendly_message
from ..components.badges import StatusBadge
from ..components.dialogs import EmptyState

FILTERS = ["All", "RUNNING", "QUEUED", "COMPLETED", "FAILED"]


class JobsView(ctk.CTkScrollableFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        theme = app.theme
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            head, text="Jobs", font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        ).pack(side="left")
        self.filter = ctk.CTkComboBox(head, values=FILTERS, width=130)
        self.filter.set("All")
        self.filter.pack(side="right", padx=4)
        ctk.CTkButton(head, text="Refresh", width=80, command=self._load).pack(side="right")
        self._list = ctk.CTkFrame(self, fg_color="transparent")
        self._list.pack(fill="both", expand=True)
        self._load()

    def _load(self) -> None:
        want = "" if self.filter.get() == "All" else self.filter.get()
        self.app.run_async(
            lambda: self.app.api.jobs(want),
            on_done=self._render,
            on_error=self._fail,
            status="Cargando jobs…",
        )

    def _render(self, jobs: list) -> None:
        theme = self.app.theme
        for child in self._list.winfo_children():
            child.destroy()
        if not jobs:
            EmptyState(self._list, theme, "No active jobs", "").pack(fill="x")
            return
        for j in jobs[:50]:
            card = ctk.CTkFrame(self._list, fg_color=theme.get("surface"), corner_radius=8)
            card.pack(fill="x", pady=3)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(6, 0))
            kind = (j.get("metrics") or {}).get("kimo_job_type") or j.get("provider") or "?"
            ctk.CTkLabel(top, text=f"{kind}", font=("Segoe UI", 12, "bold")).pack(side="left")
            StatusBadge(top, theme, j.get("status", "?")).pack(side="right")
            detail = j.get("translation") or j.get("error") or j.get("job_id", "")
            ctk.CTkLabel(
                card,
                text=str(detail)[:100],
                font=("Segoe UI", 11),
                text_color=theme.get("text_secondary"),
            ).pack(anchor="w", padx=10)
            if j.get("status") == "FAILED" and ((j.get("metrics") or {}).get("request") or {}).get(
                "text"
            ):
                ctk.CTkButton(
                    card, text="Retry", width=80, command=lambda jj=j: self._retry(jj)
                ).pack(anchor="e", padx=10, pady=(0, 6))

    def _fail(self, e: Exception) -> None:
        msg, details = friendly_message("Cargar jobs", e)
        EmptyState(self._list, self.app.theme, msg, details).pack(fill="x")

    def _retry(self, job: dict) -> None:
        self.app.run_async(
            lambda: self.app.api.retry_job(job),
            on_done=lambda r: (self.app.toast("Reintentado"), self._load()),
            on_error=lambda e: self.app.toast(str(e), error=True),
        )
