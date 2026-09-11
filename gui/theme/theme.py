"""Tema centralizado: paleta + modo. Nada de colores hardcodeados en vistas."""

from .colors import DARK, LIGHT, STATUS

MODES = ("dark", "light")


class Theme:
    def __init__(self, mode: str = "dark") -> None:
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "dark"
        self.colors = dict(DARK if self.mode == "dark" else LIGHT)

    def get(self, name: str) -> str:
        return self.colors.get(name, "#FF00FF")

    def status_color(self, status: str) -> str:
        return self.get(STATUS.get(str(status).upper(), "text_secondary"))

    def ctk_mode(self) -> str:
        return "Dark" if self.mode == "dark" else "Light"
