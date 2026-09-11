"""Settings por categorías. Secrets: solo Configured ✓, nunca el valor."""

import customtkinter as ctk


class SettingsView(ctk.CTkScrollableFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        theme = app.theme
        ctk.CTkLabel(
            self, text="Ajustes", font=("Segoe UI", 20, "bold"), text_color=theme.get("text")
        ).pack(anchor="w", padx=8)
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._combos: dict[str, ctk.CTkComboBox] = {}
        self._switches: dict[str, ctk.CTkVariable] = {}
        cfg = app.cfg
        self._section("GENERAL")
        self._combo("appearance", "Apariencia", ["dark", "light"], cfg.get("appearance", "dark"))
        self._entry("game_roots", "Raíces de juegos (; separadas)", ";".join(cfg.get("game_roots", [])))
        self._section("CONEXIÓN")
        self._entry("server_url", "URL de Raspberry-Hub", cfg.get("server_url", ""))
        self._section("SESIÓN ADMIN DEL HUB")
        self._entry("hub_user", "Usuario admin", cfg.get("hub_user", ""))
        self._hub_pass = ctk.CTkEntry(self, width=420, show="•")
        ctk.CTkLabel(self, text="Clave (no se guarda, solo memoria)", font=("Segoe UI", 11)).pack(
            anchor="w", padx=8
        )
        self._hub_pass.pack(anchor="w", padx=8, pady=(0, 4))
        hub_row = ctk.CTkFrame(self, fg_color="transparent")
        hub_row.pack(anchor="w", padx=8, pady=(0, 4))
        ctk.CTkButton(
            hub_row, text="Iniciar sesión", width=130, command=self._hub_login
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            hub_row,
            text="Actualizar estado",
            width=130,
            fg_color="transparent",
            border_width=1,
            command=self._hub_refresh,
        ).pack(side="left")
        self._hub_state = ctk.CTkLabel(
            self, text="Estado: sin comprobar", font=("Segoe UI", 11),
            text_color=theme.get("text_secondary"),
        )
        self._hub_state.pack(anchor="w", padx=8, pady=(0, 4))
        self._hub_refresh()
        self._section("TRADUCCIÓN")
        self._combo(
            "default_provider",
            "Proveedor por defecto",
            ["magi", "ollama", "deepl", "google"],
            cfg.get("default_provider", "magi"),
        )
        self._entry("default_model", "Modelo por defecto", cfg.get("default_model", ""))
        self._section("OCR")
        self._combo("ocr_engine", "Motor", ["mock", "tradujap"], cfg.get("ocr_engine", "mock"))
        self._section("PROVEEDORES")
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
        self._section("ACTUALIZACIONES")
        self._switch(
            "auto_update",
            "Buscar actualizaciones automáticamente",
            bool(cfg.get("auto_update", True)),
        )
        ctk.CTkButton(self, text="Guardar", fg_color=theme.get("accent"), command=self._save).pack(
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

    # --- sesión admin del Hub (la clave nunca se guarda en disco) ---
    def _hub_refresh(self) -> None:
        self._hub_state.configure(text="Estado: comprobando…")
        self.app.run_async(
            self.app.api.hub_status, on_done=self._hub_show, on_error=self._hub_fail
        )

    def _hub_show(self, st: dict) -> None:
        if st.get("open_mode"):
            self._hub_state.configure(text="Estado: modo abierto (sin sesión)")
        elif st.get("logged_in"):
            self._hub_state.configure(text="Estado: sesión activa")
        else:
            self._hub_state.configure(text="Estado: requiere sesión (usuario + clave)")

    def _hub_fail(self, e: Exception) -> None:
        from ..client import friendly_message

        msg, _ = friendly_message("Estado del Hub", e)
        self._hub_state.configure(text=f"Estado: {msg}")

    def _hub_login(self) -> None:
        user = self._entries["hub_user"].get().strip()
        pwd = self._hub_pass.get()
        if not user or not pwd:
            self._hub_state.configure(text="Estado: indica usuario y clave")
            return
        self._hub_state.configure(text="Estado: conectando…")

        def _done(res: dict) -> None:
            self._hub_pass.delete(0, "end")  # la clave no permanece ni en el widget
            if res.get("open_mode"):
                self._hub_state.configure(text="Estado: modo abierto (no hacía falta)")
                return
            self._hub_state.configure(text=f"Estado: sesión activa ({res.get('username', user)})")
            self.app.cfg["hub_user"] = user
            try:
                self.app.cfg_mod.save(self.app.cfg)
            except OSError:
                pass

        def _fail(e: Exception) -> None:
            from ..client import friendly_message

            msg, _ = friendly_message("Iniciar sesión", e)
            self._hub_state.configure(text=f"Estado: {msg}")

        self.app.run_async(lambda: self.app.api.hub_login(user, pwd), on_done=_done, on_error=_fail)
