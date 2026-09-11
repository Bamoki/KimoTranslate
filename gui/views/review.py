"""Review: corregir rápido con Previous/Next y filtros."""

import customtkinter as ctk

from ..client import friendly_message
from ..components.badges import StatusBadge

FILTERS = ["All", "generated", "REVIEW_REQUIRED", "corrected", "validated", "rejected"]


class ReviewView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        theme = app.theme
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkLabel(
            head, text="Review", font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        ).pack(side="left")
        self.filter = ctk.CTkComboBox(head, values=FILTERS, width=150)
        self.filter.set("REVIEW_REQUIRED")
        self.filter.pack(side="right", padx=4)
        ctk.CTkButton(head, text="Reload", width=80, command=self._load).pack(side="right", padx=4)
        self._pos = ctk.CTkLabel(
            head, text="", font=("Segoe UI", 11), text_color=theme.get("text_secondary")
        )
        self._pos.pack(side="right", padx=8)
        nav = ctk.CTkFrame(head, fg_color="transparent")
        nav.pack(side="right", padx=4)
        ctk.CTkButton(nav, text="← Previous", width=90, command=lambda: self._step(-1)).pack(
            side="left", padx=2
        )
        ctk.CTkButton(nav, text="Next →", width=90, command=lambda: self._step(1)).pack(
            side="left", padx=2
        )
        self._items: list = []
        self._idx = 0
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8)
        self._badge = StatusBadge(body, theme, "REVIEW_REQUIRED")
        self._badge.pack(anchor="w", pady=4)
        self._boxes = {}
        for key, label in (
            ("source", "Original"),
            ("machine", "Machine translation"),
            ("corrected", "Human correction"),
        ):
            ctk.CTkLabel(
                body,
                text=label,
                font=("Segoe UI", 11, "bold"),
                text_color=theme.get("text_secondary"),
            ).pack(anchor="w")
            box = ctk.CTkTextbox(body, height=70, font=("Segoe UI", 12))
            box.pack(fill="x", pady=(0, 6))
            self._boxes[key] = box
        self._boxes["machine"].configure(state="disabled")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=6)
        for label, fn, primary in (
            ("Save", self._save, False),
            ("Validate", self._validate, True),
            ("Reject", self._reject, False),
            ("To terminology", self._to_term, False),
        ):
            fg = theme.get("accent") if primary else "transparent"
            ctk.CTkButton(
                row, text=label, fg_color=fg, border_width=0 if primary else 1, command=fn
            ).pack(side="left", padx=4)
        self._load()

    def _load(self) -> None:
        status = "" if self.filter.get() == "All" else self.filter.get()
        self.app.run_async(
            lambda: self.app.api.corrections(status=status),
            on_done=self._render,
            on_error=self._fail,
            status="Cargando review…",
        )

    def _render(self, items: list) -> None:
        self._items = items
        self._idx = 0
        self._show()

    def _fail(self, e: Exception) -> None:
        msg, details = friendly_message("Cargar review", e)
        self._pos.configure(text=msg)

    def _show(self) -> None:
        if not self._items:
            for box in self._boxes.values():
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.configure(state="disabled" if box != self._boxes["corrected"] else "normal")
            self._pos.configure(text="Nothing to review — All translations are validated.")
            self._badge.set("VALIDATED")
            return
        self._idx = max(0, min(self._idx, len(self._items) - 1))
        item = self._items[self._idx]
        self._pos.configure(text=f"{self._idx + 1} / {len(self._items)}")
        self._badge.set(item.get("status", ""))
        for key, field in (
            ("source", "source_text"),
            ("machine", "machine_translation"),
            ("corrected", "corrected_translation"),
        ):
            box = self._boxes[key]
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", item.get(field) or "")
            if key == "machine":
                box.configure(state="disabled")

    def _step(self, delta: int) -> None:
        if self._items:
            self._idx = (self._idx + delta) % len(self._items)
            self._show()

    def _current(self) -> dict | None:
        return self._items[self._idx] if self._items else None

    def _save(self) -> None:
        item = self._current()
        if not item:
            return
        text = self._boxes["corrected"].get("1.0", "end").strip()
        self.app.run_async(
            lambda: self.app.api.patch_correction(item["id"], {"corrected_translation": text}),
            on_done=lambda r: (self.app.toast("Saved"), self._load()),
            on_error=lambda e: self.app.toast(str(e), error=True),
        )

    def _validate(self) -> None:
        item = self._current()
        if not item:
            return
        self._save()
        self.app.run_async(
            lambda: self.app.api.patch_correction(item["id"], {"validated": True}),
            on_done=lambda r: (
                self.app.toast("VALIDATED — promovido a TM"),
                self._items.pop(self._idx),
                self._show(),
            ),
            on_error=lambda e: self.app.toast(str(e), error=True),
        )

    def _reject(self) -> None:
        item = self._current()
        if not item:
            return
        self.app.run_async(
            lambda: self.app.api.patch_correction(item["id"], {"rejected": True}),
            on_done=lambda r: (self._items.pop(self._idx), self._show()),
            on_error=lambda e: self.app.toast(str(e), error=True),
        )

    def _to_term(self) -> None:
        item = self._current()
        if not item:
            return
        body = {
            "term": item.get("source_text", ""),
            "preferred": self._boxes["corrected"].get("1.0", "end").strip(),
            "project_id": item.get("project_id", ""),
            "game_id": item.get("game_id", ""),
        }
        self.app.run_async(
            lambda: self.app.api.add_term(body),
            on_done=lambda r: self.app.toast(f"Terminology ✓ ({r.get('scope')})"),
            on_error=lambda e: self.app.toast(str(e), error=True),
        )
