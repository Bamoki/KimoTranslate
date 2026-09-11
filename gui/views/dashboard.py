"""Dashboard: qué está pasando con mis proyectos."""

import customtkinter as ctk

from ..client import friendly_message
from ..components.badges import ProgressBar
from ..components.dialogs import EmptyState


class DashboardView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        theme = app.theme
        ctk.CTkLabel(
            self, text="KimoTranslate", font=("Segoe UI", 28, "bold"), text_color=theme.get("text")
        ).pack(anchor="w", padx=8, pady=(8, 0))
        self._sub = ctk.CTkLabel(
            self, text="Cargando…", font=("Segoe UI", 12), text_color=theme.get("text_secondary")
        )
        self._sub.pack(anchor="w", padx=8, pady=(0, 12))
        self._cards = ctk.CTkFrame(self, fg_color="transparent")
        self._cards.pack(fill="x", padx=8)
        self._active_title = ctk.CTkLabel(
            self, text="ACTIVE PROJECT", font=("Segoe UI", 10), text_color=theme.get("text_muted")
        )
        self._active_title.pack(anchor="w", padx=8, pady=(16, 4))
        self._active = ctk.CTkFrame(self, fg_color=theme.get("surface"), corner_radius=10)
        self._active.pack(fill="x", padx=8)
        self._activity_title = ctk.CTkLabel(
            self, text="RECENT ACTIVITY", font=("Segoe UI", 10), text_color=theme.get("text_muted")
        )
        self._activity_title.pack(anchor="w", padx=8, pady=(16, 4))
        self._activity = ctk.CTkTextbox(self, height=120, font=("Segoe UI", 11))
        self._activity.pack(fill="x", padx=8)
        self._activity.configure(state="disabled")
        app.run_async(
            self._load, on_done=self._render, on_error=self._fail, status="Cargando dashboard…"
        )

    def _load(self) -> dict:
        games = self.app.api.games()
        jobs = self.app.api.jobs()
        reviews = self.app.api.corrections()
        return {"games": games, "jobs": jobs, "reviews": reviews}

    def _render(self, data: dict) -> None:
        theme = self.app.theme
        games, jobs, reviews = data["games"], data["jobs"], data["reviews"]
        pending = sum(1 for j in jobs if j.get("status") in ("QUEUED", "RUNNING"))
        for child in self._cards.winfo_children():
            child.destroy()
        for label, value in (
            ("Games", len(games)),
            ("Jobs", len(jobs)),
            ("Reviews", len(reviews)),
            ("Worker", "●" if jobs else "●"),
        ):
            card = ctk.CTkFrame(
                self._cards, fg_color=theme.get("surface"), corner_radius=10, width=140, height=70
            )
            card.pack(side="left", padx=6)
            ctk.CTkLabel(
                card, text=str(value), font=("Segoe UI", 22, "bold"), text_color=theme.get("accent")
            ).pack()
            ctk.CTkLabel(
                card, text=label, font=("Segoe UI", 11), text_color=theme.get("text_secondary")
            ).pack()
        self._sub.configure(text=f"{pending} jobs activos")
        for child in self._active.winfo_children():
            child.destroy()
        if not games:
            EmptyState(
                self._active,
                theme,
                "No games found",
                "Add a game directory to begin.",
                "Games",
                lambda: self.app.navigate("games"),
            ).pack(fill="x", padx=8, pady=8)
            return
        g = games[0]
        counts = g.get("counts") or {}
        total = counts.get("total", 0) or 1
        done = total - counts.get("EXTRACTED", 0)
        ctk.CTkLabel(
            self._active, text=g.get("name", g.get("game_id", "?")), font=("Segoe UI", 14, "bold")
        ).pack(anchor="w", padx=12, pady=(8, 0))
        bar = ProgressBar(self._active, theme)
        bar.pack(fill="x", padx=12, pady=8)
        bar.set(done, total)
        lines = [
            f"● {j.get('name', j.get('job_id', '?'))} — {j.get('status')}" for j in jobs[:8]
        ] or ["Sin actividad reciente."]
        self._activity.configure(state="normal")
        self._activity.delete("1.0", "end")
        self._activity.insert("1.0", "\n".join(lines))
        self._activity.configure(state="disabled")

    def _fail(self, e: Exception) -> None:
        msg, details = friendly_message("Cargar dashboard", e)
        for child in self._cards.winfo_children():
            child.destroy()
        EmptyState(self._cards, self.app.theme, msg, details or "Revisa Settings.").pack()
