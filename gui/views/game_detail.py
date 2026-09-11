"""Game Detail: tabs Overview/Text/Images/Review/Export/Integrity + stepper."""

import customtkinter as ctk

from ..client import friendly_message
from ..components.badges import ProgressBar
from ..components.dialogs import ErrorDialog

STEPS = ["DETECT", "EXTRACT", "TRANSLATE", "OCR", "REVIEW", "LOCALIZE", "EXPORT", "VERIFY"]


class GameDetailView(ctk.CTkFrame):
    def __init__(self, master, app, game_id: str) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.game_id = game_id
        theme = app.theme
        self._head = ctk.CTkLabel(
            self, text=game_id, font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        )
        self._head.pack(anchor="w", padx=8)
        self._steps = ctk.CTkFrame(self, fg_color="transparent")
        self._steps.pack(fill="x", padx=8, pady=6)
        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=8, pady=8)
        for name in ("Overview", "Text", "Images", "Review", "Export", "Integrity"):
            self._tabs.add(name)
        app.run_async(
            lambda: app.api.game(game_id),
            on_done=self._render,
            on_error=self._fail,
            status=f"Cargando {game_id}…",
        )

    def _render(self, game: dict) -> None:
        theme = self.app.theme
        self._head.configure(text=game.get("name", self.game_id))
        counts = game.get("counts") or {}
        total = counts.get("total", 0)
        # Stepper por estado real.
        step_state = self._step_states(game, counts)
        for child in self._steps.winfo_children():
            child.destroy()
        for i, step in enumerate(STEPS):
            st = step_state.get(step, "NOT STARTED")
            color = {
                "COMPLETED": theme.get("success"),
                "RUNNING": theme.get("info"),
                "FAILED": theme.get("error"),
            }.get(st, theme.get("text_muted"))
            arrow = "  ↓  " if i < len(STEPS) - 1 else ""
            ctk.CTkLabel(
                self._steps, text=f"{step}{arrow}", font=("Segoe UI", 10, "bold"), text_color=color
            ).pack(side="left")
        ov = self._tabs.tab("Overview")
        for child in ov.winfo_children():
            child.destroy()
        info = (
            f"ENGINE  {game.get('detected_engine', '?')}\n"
            f"ENCODING  CP932\n"
            f"SOURCE  {game.get('source_path', '')}"
        )
        ctk.CTkLabel(
            ov,
            text=info,
            font=("Consolas", 11),
            justify="left",
            text_color=theme.get("text_secondary"),
        ).pack(anchor="w", padx=12, pady=8)
        bar = ProgressBar(ov, theme)
        bar.pack(fill="x", padx=12)
        bar.set(total - counts.get("EXTRACTED", 0), total)
        # Acciones con jerarquía: primaria + secundarias.
        row = ctk.CTkFrame(ov, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)
        primary = ctk.CTkButton(
            row, text="Translate", width=110, fg_color=theme.get("accent"), command=self._translate
        )
        primary.pack(side="left", padx=4)
        for label, fn in (
            ("Extract", self._extract),
            ("Images", self._images),
            ("Review", lambda: self.app.navigate("review")),
            ("Export", self._export),
            ("Integrity", self._integrity),
        ):
            ctk.CTkButton(
                row,
                text=label,
                width=90,
                fg_color="transparent",
                border_width=1,
                text_color=theme.get("text"),
                command=fn,
            ).pack(side="left", padx=4)
        # Tab Text: resumen + ir a review.
        tx = self._tabs.tab("Text")
        for child in tx.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            tx,
            text=f"{total} textos · {counts.get('VALIDATED', 0)} validados",
            font=("Segoe UI", 12),
        ).pack(padx=12, pady=8, anchor="w")
        ctk.CTkButton(tx, text="Open Review", command=lambda: self.app.navigate("review")).pack(
            padx=12, anchor="w"
        )
        # Tab Images: conteo + ir a la biblioteca.
        im = self._tabs.tab("Images")
        for child in im.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            im, text="Imágenes del juego (OCR + localización).", font=("Segoe UI", 12)
        ).pack(padx=12, pady=8, anchor="w")
        ctk.CTkButton(im, text="Open Images", command=lambda: self.app.navigate("images")).pack(
            padx=12, anchor="w"
        )

    def _step_states(self, game: dict, counts: dict) -> dict:
        total = counts.get("total", 0)
        images = self._image_counts()
        return {
            "DETECT": "COMPLETED" if game.get("detected_engine") != "unknown" else "FAILED",
            "EXTRACT": "COMPLETED" if total else "NOT STARTED",
            "TRANSLATE": "COMPLETED"
            if counts.get("TRANSLATED", 0) == total and total
            else ("RUNNING" if counts.get("QUEUED", 0) else "NOT STARTED"),
            "OCR": images,
            "REVIEW": "COMPLETED"
            if counts.get("VALIDATED", 0) == total and total
            else "NOT STARTED",
            "LOCALIZE": "NOT STARTED",
            "EXPORT": "COMPLETED"
            if ((game.get("manifest") or {}).get("last_export"))
            else "NOT STARTED",
            "VERIFY": "NOT STARTED",
        }

    def _image_counts(self) -> str:
        return "NOT STARTED"

    def _fail(self, e: Exception) -> None:
        msg, details = friendly_message("Cargar juego", e)
        ErrorDialog(self, self.app.theme, "Game failed", msg, details)

    def _extract(self) -> None:
        self.app.run_async(
            lambda: self.app.api.extract_game(self.game_id),
            on_done=lambda r: self.app.toast("Extract encolado"),
            on_error=lambda e: self._fail(e),
            status="Extract…",
        )

    def _translate(self) -> None:
        self.app.run_async(
            lambda: self.app.api.translate_game(self.game_id),
            on_done=lambda r: self.app.toast(f"Translate: {r}"),
            on_error=lambda e: self._fail(e),
            status="Translate…",
        )

    def _images(self) -> None:
        self.app.navigate("images")

    def _export(self) -> None:
        import os

        out = os.path.join(os.path.expanduser("~"), "KimoTranslate", self.game_id + "_es")
        self.app.run_async(
            lambda: self.app.api.export_game(self.game_id, out),
            on_done=lambda r: self.app.toast("Export encolado"),
            on_error=lambda e: self._fail(e),
            status="Export…",
        )

    def _integrity(self) -> None:
        self.app.run_async(
            lambda: self.app.api.game_integrity(self.game_id),
            on_done=lambda r: self.app.toast(
                "Integrity PASS" if r.get("ok") else "Integrity FAIL", error=not r.get("ok")
            ),
            on_error=lambda e: self._fail(e),
            status="Integrity…",
        )
