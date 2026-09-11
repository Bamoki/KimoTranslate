"""Badges de estado, barras de progreso, indicadores. Sin solo-color:
siempre texto + símbolo.
"""

import customtkinter as ctk

_SYMBOLS = {
    "ONLINE": "●",
    "COMPLETED": "●",
    "VALIDATED": "●",
    "LOCALIZED": "●",
    "PASS": "●",
    "RUNNING": "◐",
    "QUEUED": "○",
    "CONNECTING": "◌",
    "WARNING": "▲",
    "REVIEW_REQUIRED": "▲",
    "SHRUNK": "▲",
    "OFFLINE": "■",
    "FAILED": "■",
    "ERROR": "■",
    "OVERFLOW": "■",
    "REJECTED": "■",
}


class StatusBadge(ctk.CTkFrame):
    def __init__(self, master, theme, status: str = "OFFLINE", **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._theme = theme
        self._label = ctk.CTkLabel(self, text="", font=("Segoe UI", 11, "bold"))
        self._label.pack(side="left")
        self.set(status)

    def set(self, status: str) -> None:
        symbol = _SYMBOLS.get(str(status).upper(), "○")
        self._label.configure(
            text=f"{symbol} {status}", text_color=self._theme.status_color(status)
        )


class HealthDot(ctk.CTkLabel):
    """Hub ● / Worker ● compacto para la topbar."""

    def __init__(self, master, theme, name: str) -> None:
        super().__init__(master, text="", font=("Segoe UI", 11, "bold"))
        self._theme = theme
        self._name = name
        self.set("OFFLINE")

    def set(self, status: str) -> None:
        symbol = _SYMBOLS.get(str(status).upper(), "○")
        self.configure(text=f"{self._name} {symbol}", text_color=self._theme.status_color(status))


class ProgressBar(ctk.CTkFrame):
    def __init__(self, master, theme, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._bar = ctk.CTkProgressBar(self)
        self._bar.pack(fill="x", expand=True)
        self._label = ctk.CTkLabel(self, text="", font=("Segoe UI", 10))
        self._label.pack(anchor="w")
        self.set(0, 0)

    def set(self, done: int, total: int) -> None:
        frac = (done / total) if total else 0.0
        self._bar.set(max(0.0, min(1.0, frac)))
        self._label.configure(text=f"{done} / {total}" if total else "—")


def progress_counts(counts: dict) -> tuple[int, int]:
    """Progreso único para todas las vistas: hecho = total − pendientes.

    Pendiente = EXTRACTED (extraído, sin traducir) + QUEUED.
    """
    total = counts.get("total", 0) or 0
    pending = counts.get("EXTRACTED", 0) + counts.get("QUEUED", 0)
    return max(0, total - pending), total
