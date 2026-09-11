"""Settings por categorías. Secrets: solo Configured ✓, nunca el valor."""

import customtkinter as ctk


class SettingsView(ctk.CTkScrollableFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        theme = app.theme
        ctk.CTkLabel(
            self, text="Settings", font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        ).pack(anchor="w", padx=8)
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._combos: dict[str, ctk.CTkComboBox] = {}
        self._switches: dict[str, ctk.CTkVariable] = {}
        cfg = app.cfg
        self._section("GENERAL")
        self._combo("appearance", "Appearance", ["dark", "light"], cfg.get("appearance", "dark"))
        self._entry("game_roots", "Game roots (; separados)", ";".join(cfg.get("game_roots", [])))
        self._section("CONNECTION")
        self._entry("server_url", "Raspberry-Hub URL", cfg.get("server_url", ""))
        self._entry("hub_user", "Hub admin user", cfg.get("hub_user", ""))
        self._section("TRANSLATION")
        self._combo(
            "default_provider",
            "Default provider",
            ["magi", "ollama", "deepl", "google"],
            cfg.get("default_provider", "magi"),
        )
        self._entry("default_model", "Default model", cfg.get("default_model", ""))
        self._section("OCR")
        self._combo("ocr_engine", "Engine", ["mock", "tradujap"], cfg.get("ocr_engine", "mock"))
        self._section("PROVIDERS")
        import os

        for key, label in (("DEEPL_API_KEY", "DeepL"), ("GOOGLE_TRANSLATE_API_KEY", "Google")):
            state = "Configured ✓" if os.environ.get(key) else "No configurada"
            ctk.CTkLabel(
                self,
                text=f"{label}: {state}",
                font=("Segoe UI", 12),
                text_color=theme.get("text_secondary"),
            ).pack(anchor="w", padx=8)
        ctk.CTkLabel(
            self,
            text="Las keys viven en el Worker (env), nunca aquí.",
            font=("Segoe UI", 10),
            text_color=theme.get("text_muted"),
        ).pack(anchor="w", padx=8, pady=(0, 8))
        self._section("UPDATES")
        self._switch(
            "auto_update",
            "Buscar actualizaciones automáticamente",
            bool(cfg.get("auto_update", True)),
        )
        ctk.CTkButton(self, text="Save", fg_color=theme.get("accent"), command=self._save).pack(
            anchor="w", padx=8, pady=8
        )
        ctk.CTkButton(
            self, text="Buscar actualizaciones", command=lambda: app._check_updates(silent=False)
        ).pack(anchor="w", padx=8)
        self._status = ctk.CTkLabel(self, text="", font=("Segoe UI", 11))
        self._status.pack(anchor="w", padx=8)

    def _section(self, title: str) -> None:
        ctk.CTkLabel(
            self, text=title, font=("Segoe UI", 10), text_color=self.app.theme.get("text_muted")
        ).pack(anchor="w", padx=8, pady=(12, 2))

    def _entry(self, key: str, label: str, value: str) -> None:
        ctk.CTkLabel(self, text=label, font=("Segoe UI", 11)).pack(anchor="w", padx=8)
        ent = ctk.CTkEntry(self, width=420)
        ent.insert(0, value)
        ent.pack(anchor="w", padx=8, pady=(0, 4))
        self._entries[key] = ent

    def _combo(self, key: str, label: str, values: list, current: str) -> None:
        ctk.CTkLabel(self, text=label, font=("Segoe UI", 11)).pack(anchor="w", padx=8)
        combo = ctk.CTkComboBox(self, values=values, width=220)
        combo.set(current if current in values else values[0])
        combo.pack(anchor="w", padx=8, pady=(0, 4))
        self._combos[key] = combo

    def _switch(self, key: str, label: str, value: bool) -> None:
        var = ctk.BooleanVar(value=value)
        ctk.CTkSwitch(self, text=label, variable=var).pack(anchor="w", padx=8, pady=4)
        self._switches[key] = var

    def _save(self) -> None:
        import os

        cfg = self.app.cfg
        for k, ent in self._entries.items():
            v = ent.get().strip()
            if k == "game_roots":
                cfg[k] = [p.strip() for p in v.split(";") if p.strip()]
            elif k == "server_url" and v and not v.startswith(("http://", "https://")):
                self._status.configure(text="URL debe empezar por http(s)://")
                return
            else:
                cfg[k] = v
        for k, combo in self._combos.items():
            cfg[k] = combo.get()
        for k, var in self._switches.items():
            cfg[k] = bool(var.get())
        if not os.environ.get("KIMOTRANSLATE_SERVER_URL"):
            self.app.api.base_url = cfg.get("server_url", self.app.api.base_url).rstrip("/")
        try:
            self.app.cfg_mod.save(cfg)
            self.app.theme.set_mode(cfg.get("appearance", "dark"))
            import customtkinter as ctk

            ctk.set_appearance_mode(self.app.theme.ctk_mode())
            self._status.configure(text="Guardado. Reinicia para tema completo.")
        except OSError as e:
            self._status.configure(text=f"error: {e}")
