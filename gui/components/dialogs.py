"""Cards, empty states, diálogos de error con detalles + tooltips."""

import customtkinter as ctk
import tkinter as tk


class Card(ctk.CTkFrame):
    def __init__(self, master, theme, **kwargs) -> None:
        super().__init__(
            master,
            fg_color=theme.get("surface"),
            corner_radius=10,
            border_width=1,
            border_color=theme.get("border"),
            **kwargs,
        )


class EmptyState(ctk.CTkFrame):
    def __init__(
        self, master, theme, title: str, hint: str, action_label: str = "", action=None, **kwargs
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(
            self, text=title, font=("Segoe UI", 14, "bold"), text_color=theme.get("text")
        ).pack(pady=(20, 4))
        ctk.CTkLabel(
            self, text=hint, font=("Segoe UI", 11), text_color=theme.get("text_secondary")
        ).pack(pady=(0, 12))
        if action_label and action:
            ctk.CTkButton(
                self,
                text=action_label,
                command=action,
                fg_color=theme.get("accent"),
                hover_color=theme.get("accent_hover"),
            ).pack()


class ErrorDialog(ctk.CTkToplevel):
    """Error comprensible + [View details] técnico aparte."""

    def __init__(self, master, theme, title: str, message: str, details: str = "") -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("480x220")
        ctk.CTkLabel(
            self, text=title, font=("Segoe UI", 14, "bold"), text_color=theme.get("error")
        ).pack(padx=20, pady=(16, 4), anchor="w")
        ctk.CTkLabel(
            self,
            text=message,
            font=("Segoe UI", 12),
            text_color=theme.get("text"),
            wraplength=440,
            justify="left",
        ).pack(padx=20, anchor="w")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=12)
        if details:
            ctk.CTkButton(
                row, text="Ver detalles", command=lambda: self._show_details(details)
            ).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Cerrar", command=self.destroy).pack(side="left", padx=6)
        self.grab_set()

    def _show_details(self, details: str) -> None:
        box = ctk.CTkToplevel(self)
        box.title("Detalles técnicos")
        box.geometry("520x300")
        txt = ctk.CTkTextbox(box, font=("Consolas", 10))
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        txt.insert("1.0", details)
        txt.configure(state="disabled")


def ask_confirm(master, theme, title: str, message: str) -> bool:
    box = ctk.CTkToplevel(master)
    box.title(title)
    box.geometry("380x160")
    ctk.CTkLabel(box, text=message, wraplength=340).pack(padx=20, pady=16)
    result = {"ok": False}
    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack()

    def _ok():
        result["ok"] = True
        box.destroy()

    ctk.CTkButton(row, text="Confirmar", command=_ok, fg_color=theme.get("error")).pack(
        side="left", padx=6
    )
    ctk.CTkButton(row, text="Cancelar", command=box.destroy).pack(side="left", padx=6)
    box.grab_set()
    master.wait_window(box)
    return result["ok"]


class ToolTip:
    """Tooltip simple que aparece tras 400ms al hacer hover."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip: ctk.CTkToplevel | None = None
        self._after_id = ""
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, event=None) -> None:
        if self._after_id:
            return
        self._after_id = self.widget.after(400, self._create)

    def _create(self) -> None:
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.tip = ctk.CTkToplevel(self.widget)
            self.tip.overrideredirect(True)
            self.tip.attributes("-topmost", True)
            lbl = ctk.CTkLabel(
                self.tip, text=self.text, font=("Segoe UI", 10), text_color="#C0CAF5",
                fg_color="#24283B", corner_radius=6, padx=8, pady=4
            )
            lbl.pack()
            self.tip.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _hide(self, event=None) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = ""
        if self.tip:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None
