"""Sidebar + Topbar + barra de estado."""

import customtkinter as ctk

NAV = [
    ("overview", "Overview", None),
    ("games", "Games", "WORKSPACE"),
    ("translate", "Translate", None),
    ("images", "Images", None),
    ("review", "Review", None),
    ("datasets", "Datasets", None),
    ("jobs", "Jobs", "SYSTEM"),
    ("settings", "Settings", None),
]

_MARKERS = {
    "overview": "◈",
    "games": "◇",
    "translate": "◇",
    "images": "◇",
    "review": "◇",
    "datasets": "◇",
    "jobs": "◇",
    "settings": "⚙",
}


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, theme, on_navigate) -> None:
        super().__init__(master, fg_color=theme.get("surface"), corner_radius=0, width=200)
        self._theme = theme
        self._on_navigate = on_navigate
        self._buttons: dict[str, ctk.CTkButton] = {}
        ctk.CTkLabel(
            self, text="KIMO TRANSLATE", font=("Segoe UI", 13, "bold"), text_color=theme.get("text")
        ).pack(padx=12, pady=(16, 4), anchor="w")
        for key, label, section in NAV:
            if section:
                ctk.CTkLabel(
                    self, text=section, font=("Segoe UI", 9), text_color=theme.get("text_muted")
                ).pack(padx=12, pady=(10, 2), anchor="w")
            marker = _MARKERS.get(key, "◇")
            btn = ctk.CTkButton(
                self,
                text=f"{marker}  {label}",
                anchor="w",
                fg_color="transparent",
                text_color=theme.get("text_secondary"),
                hover_color=theme.get("surface_hover"),
                corner_radius=8,
                command=lambda k=key: self._on_navigate(k),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._buttons[key] = btn
        self._current = ""

    def set_active(self, key: str) -> None:
        self._current = key
        for k, btn in self._buttons.items():
            if k == key:
                btn.configure(
                    fg_color=self._theme.get("surface_elevated"),
                    text_color=self._theme.get("accent"),
                    border_width=1,
                    border_color=self._theme.get("accent"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=self._theme.get("text_secondary"),
                    border_width=0,
                )


class Topbar(ctk.CTkFrame):
    def __init__(self, master, theme) -> None:
        from .badges import HealthDot

        super().__init__(master, fg_color=theme.get("surface"), corner_radius=0, height=44)
        self._location = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 12, "bold"), text_color=theme.get("text")
        )
        self._location.pack(side="left", padx=16)
        self.hub = HealthDot(self, theme, "Hub")
        self.hub.pack(side="right", padx=8)
        self.worker = HealthDot(self, theme, "Worker")
        self.worker.pack(side="right", padx=8)

    def set_location(self, text: str) -> None:
        self._location.configure(text=text)


class Statusbar(ctk.CTkFrame):
    def __init__(self, master, theme) -> None:
        super().__init__(master, fg_color=theme.get("surface"), corner_radius=0, height=26)
        self._label = ctk.CTkLabel(
            self, text="Listo", font=("Segoe UI", 10), text_color=theme.get("text_secondary")
        )
        self._label.pack(side="left", padx=12)

    def set(self, text: str) -> None:
        self._label.configure(text=text)
