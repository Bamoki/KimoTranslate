"""Cards, empty states, diálogos de error con detalles."""

import customtkinter as ctk


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
                row, text="View details", command=lambda: self._show_details(details)
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
