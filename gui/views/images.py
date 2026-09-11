"""Images: biblioteca visual con filtros, búsqueda y lazy loading."""

import customtkinter as ctk

from ..client import friendly_message
from ..components.badges import StatusBadge
from ..components.dialogs import EmptyState

FILTERS = [
    ("All", ""),
    ("OCR", "OCR_DONE"),
    ("Translated", "TRANSLATED"),
    ("Localized", "LOCALIZED"),
    ("Review", "REVIEW_REQUIRED"),
]
PAGE = 60


class ImagesView(ctk.CTkFrame):
    def __init__(self, master, app, game_id: str = "") -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.game_id = game_id
        theme = app.theme
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkLabel(
            head, text="Images", font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        ).pack(side="left")
        self.search = ctk.CTkEntry(head, placeholder_text="Buscar… (Ctrl+F)", width=220)
        self.search.pack(side="right", padx=4)
        self.search.bind("<Return>", lambda e: self._load())
        self.filter = ctk.CTkComboBox(head, values=[f[0] for f in FILTERS], width=130)
        self.filter.set("All")
        self.filter.pack(side="right", padx=4)
        ctk.CTkButton(head, text="Discover", width=90, command=self._discover).pack(
            side="right", padx=4
        )
        self._grid = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._grid.pack(fill="both", expand=True, padx=8)
        self._shown = 0
        self._items: list = []
        self.bind_all("<Control-f>", lambda e: self.search.focus_set())
        self._load()

    def _game(self) -> str:
        if self.game_id:
            return self.game_id
        try:
            games = self.app.api.games()
        except Exception:
            return ""
        return games[0]["game_id"] if games else ""

    def _load(self) -> None:
        gid = self._game()
        if not gid:
            EmptyState(self._grid, self.app.theme, "No games found", "Add a game first.").pack()
            return
        self.app.run_async(
            lambda: self.app.api.game_images(gid),
            on_done=self._render,
            on_error=self._fail,
            status="Cargando imágenes…",
        )

    def _render(self, items: list) -> None:
        want = dict(FILTERS)[self.filter.get()]
        q = self.search.get().strip().lower()
        self._items = [
            a
            for a in items
            if (not want or a.get("ocr_status") == want or want == "All")
            and (not q or q in a.get("relpath", "").lower())
        ]
        self._shown = 0
        for child in self._grid.winfo_children():
            child.destroy()
        if not self._items:
            EmptyState(
                self._grid,
                self.app.theme,
                "Sin imágenes",
                "Discover para buscar recursos con texto.",
            ).pack()
            return
        self._more()

    def _more(self) -> None:
        theme = self.app.theme
        batch = self._items[self._shown : self._shown + PAGE]
        for a in batch:
            card = ctk.CTkFrame(
                self._grid, fg_color=theme.get("surface"), corner_radius=10, width=200, height=120
            )
            card.pack(side="left", padx=6, pady=6)
            ctk.CTkLabel(card, text=a.get("relpath", "?")[-28:], font=("Segoe UI", 10)).pack(
                padx=6, pady=(6, 0)
            )
            StatusBadge(
                card, theme, a.get("localization_status") or a.get("ocr_status", "DISCOVERED")
            ).pack(pady=4)
            ctk.CTkButton(
                card, text="Open", width=80, command=lambda i=a["id"]: self._open(i)
            ).pack(pady=(0, 6))
        self._shown += len(batch)
        if self._shown < len(self._items):
            ctk.CTkButton(
                self._grid, text=f"More ({len(self._items) - self._shown})", command=self._more
            ).pack(side="left", padx=6)

    def _fail(self, e: Exception) -> None:
        msg, details = friendly_message("Cargar imágenes", e)
        EmptyState(self._grid, self.app.theme, msg, details).pack()

    def _discover(self) -> None:
        gid = self._game()
        if gid:
            self.app.run_async(
                lambda: self.app.api.discover_images(gid),
                on_done=lambda r: (self.app.toast("Discover OK"), self._load()),
                on_error=self._fail,
                status="Discover…",
            )

    def _open(self, image_id: str) -> None:
        gid = self._game()
        self.app.navigate(f"editor:{gid}/{image_id}")
