"""Editor visual: canvas + regiones + propiedades. Estado en servidor (Fase 7).

Sin PIL/OpenCV/OCR en la GUI: imágenes vía PhotoImage, todo por HTTP.
"""

import tkinter as tk

import customtkinter as ctk

from ..client import friendly_message
from ..components.badges import StatusBadge

MODES = ("Original", "OCR", "Translated", "Localized", "Split")
MIN_SIDE = 8


class EditorView(ctk.CTkFrame):
    """Vista embebida (navigate editor:game/image) o Toplevel vía open_editor()."""

    def __init__(self, master, app, param: str = "") -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.theme = app.theme
        self.game_id, _, self.image_id = param.partition("/") if "/" in param else ("", "", param)
        self.zoom = 1.0
        self.mode = "OCR"
        self.show_boxes = True
        self.mask_tool = "off"
        self.brush = 8
        self.selected: str | None = None
        self.regions: list[dict] = []
        self.photos: dict = {}
        self._drag: dict = {}
        self._build()

    def on_show(self) -> None:
        self.refresh()

    # --- layout §4 ---
    def _build(self) -> None:
        theme = self.theme
        bar = ctk.CTkFrame(self, fg_color=theme.get("surface"), corner_radius=0, height=40)
        bar.pack(fill="x")
        ctk.CTkButton(
            bar,
            text="←",
            width=36,
            fg_color="transparent",
            command=lambda: self.app.navigate("images"),
        ).pack(side="left", padx=4)
        ctk.CTkLabel(
            bar, text=f"Game / Images / {self.image_id}", font=("Segoe UI", 12, "bold")
        ).pack(side="left", padx=8)
        for m in ("Original", "OCR", "Final"):
            ctk.CTkButton(
                bar,
                text=m,
                width=70,
                fg_color="transparent",
                border_width=1,
                command=lambda mm=m: self._set_mode(mm),
            ).pack(side="left", padx=2)
        for label, fn in (
            ("Undo", self._undo),
            ("Redo", self._redo),
            ("Preview", self._preview),
            ("Save", self.refresh),
            ("Reset", self._reset),
        ):
            ctk.CTkButton(bar, text=label, width=64, command=fn).pack(side="left", padx=2)
        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.pack(fill="both", expand=True)
        # izquierda: regiones
        left = ctk.CTkFrame(mid, fg_color=theme.get("surface"), corner_radius=10, width=220)
        left.pack(side="left", fill="y", padx=(0, 8), pady=8)
        ctk.CTkLabel(
            left, text="REGIONES", font=("Segoe UI", 10), text_color=theme.get("text_muted")
        ).pack(anchor="w", padx=8, pady=(8, 0))
        self.tree = tk.Listbox(
            left,
            height=18,
            bg=theme.get("surface_elevated"),
            fg=theme.get("text"),
            selectbackground=theme.get("accent"),
            font=("Segoe UI", 10),
        )
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.tree.bind("<<ListboxSelect>>", self._tree_select)
        ctk.CTkButton(left, text="+ Add (dibuja)", command=self._mode_new).pack(padx=8, pady=4)
        # centro: canvas
        center = ctk.CTkFrame(mid, fg_color=theme.get("surface"), corner_radius=10)
        center.pack(side="left", fill="both", expand=True, pady=8)
        self.canvas = tk.Canvas(center, bg="#101020", highlightthickness=0)
        sx = ctk.CTkScrollbar(center, orientation="horizontal", command=self.canvas.xview)
        sy = ctk.CTkScrollbar(center, orientation="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sx.pack(fill="x", padx=4)
        sy.pack(side="right", fill="y")
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<B1-Motion>", self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drop)
        self.canvas.bind("<Button-4>", lambda e: self._zoom_step(1.25))
        self.canvas.bind("<Button-5>", lambda e: self._zoom_step(0.8))
        self.canvas.bind("<Delete>", lambda e: self._delete_selected())
        # derecha: propiedades
        right = ctk.CTkFrame(mid, fg_color=theme.get("surface"), corner_radius=10, width=280)
        right.pack(side="right", fill="y", padx=(8, 0), pady=8)
        ctk.CTkLabel(
            right, text="PROPIEDADES", font=("Segoe UI", 10), text_color=theme.get("text_muted")
        ).pack(anchor="w", padx=8, pady=(8, 0))
        self._badge = StatusBadge(right, theme, "REVIEW_REQUIRED")
        self._badge.pack(anchor="w", padx=8, pady=4)
        self.props: dict = {}
        for key, label in (
            ("ocr", "OCR"),
            ("translation", "Translation"),
            ("x", "X"),
            ("y", "Y"),
            ("w", "W"),
            ("h", "H"),
            ("font_size", "Font size"),
            ("color", "Color (r,g,b)"),
            ("stroke", "Stroke"),
            ("align", "Align l/c/r"),
            ("valign", "Valign t/c/b"),
        ):
            ctk.CTkLabel(right, text=label, font=("Segoe UI", 10)).pack(anchor="w", padx=8)
            ent = ctk.CTkEntry(right, width=240)
            ent.pack(anchor="w", padx=8, pady=(0, 2))
            self.props[key] = ent
        btns = ctk.CTkFrame(right, fg_color="transparent")
        btns.pack(padx=8, pady=6)
        ctk.CTkButton(
            btns, text="Aplicar", width=80, fg_color=theme.get("accent"), command=self._apply_props
        ).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="Validar", width=80, command=self._validate_region).pack(
            side="left", padx=2
        )
        ctk.CTkLabel(right, text="Máscara: off/add/erase + pincel", font=("Segoe UI", 10)).pack(
            anchor="w", padx=8
        )
        mrow = ctk.CTkFrame(right, fg_color="transparent")
        mrow.pack(anchor="w", padx=8)
        self._maskvar = tk.StringVar(value="off")
        for t in ("off", "add", "erase"):
            ctk.CTkRadioButton(
                mrow, text=t, value=t, variable=self._maskvar, command=self._mask_changed
            ).pack(side="left")
        self._brushvar = tk.IntVar(value=8)
        ctk.CTkSlider(mrow, from_=2, to=40, variable=self._brushvar, width=100).pack(side="left")
        self.warn = ctk.CTkLabel(
            right, text="", font=("Segoe UI", 10), text_color=theme.get("error"), wraplength=250
        )
        self.warn.pack(anchor="w", padx=8)
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x")
        self.status = ctk.CTkLabel(
            bottom, text="", font=("Segoe UI", 10), text_color=theme.get("text_secondary")
        )
        self.status.pack(side="left", padx=8)
        for seq, fn in (
            ("<Control-z>", self._undo),
            ("<Control-y>", self._redo),
            ("<Control-s>", lambda e: self.refresh()),
            ("<Delete>", lambda e: self._delete_selected()),
        ):
            self.bind_all(seq, lambda e, f=fn: f(), add="+")

    # --- datos ---
    def refresh(self) -> None:
        def _load():
            det = self.app.api.image(self.game_id, self.image_id)
            return det

        def _got(det):
            self.regions = [r for r in det.get("regions", []) if r["status"] != "DELETED"]
            self._fill_tree()
            self._redraw()
            self.status.configure(text=f"{len(self.regions)} regiones · guardado ✓")

        def _fail(e):
            msg, _ = friendly_message("Abrir editor", e)
            self.status.configure(text=msg)

        self.app.run_async(_load, on_done=_got, on_error=_fail, status="Abriendo editor…")

    def _fill_tree(self) -> None:
        self.tree.delete(0, "end")
        for i, r in enumerate(self.regions):
            self.tree.insert("end", f"#{i + 1} {r.get('text_type', '')} | {r['source_text'][:20]}")

    # --- dibujo/zoom/pan/selección ---
    def _artifact(self, name: str):
        try:
            raw = self.app.api.image_artifact(self.game_id, self.image_id, name)
            return tk.PhotoImage(data=raw)
        except Exception:
            return None

    def _redraw(self) -> None:
        self.canvas.delete("all")
        name = "localized.png" if self.mode == "Final" else "original.png"
        photo = self._artifact(name) or self._artifact("original.png")
        if photo is None:
            self.canvas.create_text(100, 100, text="(localiza primero)", fill="white")
            return
        z = self.zoom
        img = photo
        if z != 1.0:
            img = photo.zoom(int(z), int(z)) if z >= 1 else photo.subsample(int(1 / z), int(1 / z))
            self.photos["_z"] = img
        else:
            self.photos["_base"] = img
        self.canvas.create_image(0, 0, anchor="nw", image=img)
        self.canvas.configure(scrollregion=(0, 0, int(img.width()), int(img.height())))
        if self.show_boxes():
            for r in self.regions:
                x0, y0 = r["x"] * z, r["y"] * z
                x1, y1 = (r["x"] + r["w"]) * z, (r["y"] + r["h"]) * z
                color = "red" if r["id"] == self.selected else "yellow"
                self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2)
                self.canvas.create_text(
                    x0, y0 - 8, text=r["id"].split(":")[-1], fill=color, anchor="sw"
                )
                if r["id"] == self.selected:
                    for hx, hy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                        self.canvas.create_rectangle(hx - 4, hy - 4, hx + 4, hy + 4, fill="red")

    def show_boxes(self) -> bool:
        return self.mode in ("OCR", "Final")

    def _zoom_step(self, factor: float) -> None:
        self.zoom = min(4.0, max(0.25, self.zoom * factor))
        self._redraw()

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self._redraw()

    def _region_at(self, x: int, y: int) -> dict | None:
        cx, cy = self.canvas.canvasx(x) / self.zoom, self.canvas.canvasy(y) / self.zoom
        for r in self.regions:
            if r["x"] <= cx <= r["x"] + r["w"] and r["y"] <= cy <= r["y"] + r["h"]:
                return r
        return None

    def _corner_at(self, r: dict, cx: float, cy: float) -> str | None:
        tol = 8 / self.zoom
        corners = {
            "nw": (r["x"], r["y"]),
            "ne": (r["x"] + r["w"], r["y"]),
            "sw": (r["x"], r["y"] + r["h"]),
            "se": (r["x"] + r["w"], r["y"] + r["h"]),
        }
        for name, (px, py) in corners.items():
            if abs(cx - px) <= tol and abs(cy - py) <= tol:
                return name
        return None

    # --- interacción: click/drag/resize/new/máscara ---
    def _click(self, event) -> None:
        if self._maskvar.get() != "off":
            self._paint(event)
            return
        r = self._region_at(event.x, event.y)
        if r is None:
            self._drag = {
                "new": True,
                "x0": self.canvas.canvasx(event.x) / self.zoom,
                "y0": self.canvas.canvasy(event.y) / self.zoom,
            }
            return
        self.selected = r["id"]
        cx = self.canvas.canvasx(event.x) / self.zoom
        cy = self.canvas.canvasy(event.y) / self.zoom
        corner = self._corner_at(r, cx, cy)
        self._drag = {
            "id": r["id"],
            "cx0": cx,
            "cy0": cy,
            "corner": corner,
            "x0": r["x"],
            "y0": r["y"],
            "w0": r["w"],
            "h0": r["h"],
        }
        self._fill_props(r)
        self._redraw()

    def _drag_motion(self, event) -> None:
        if self._maskvar.get() != "off":
            self._paint(event)

    def _drop(self, event) -> None:
        d = self._drag
        self._drag = {}
        if not d or self._maskvar.get() != "off":
            return
        cx = self.canvas.canvasx(event.x) / self.zoom
        cy = self.canvas.canvasy(event.y) / self.zoom
        if d.get("new"):
            x, y = int(min(d["x0"], cx)), int(min(d["y0"], cy))
            w, h = int(max(abs(cx - d["x0"]), MIN_SIDE)), int(max(abs(cy - d["y0"]), MIN_SIDE))
            self.app.run_async(
                lambda: self.app.api.editor_create(self.game_id, self.image_id, x, y, w, h),
                on_done=lambda r: (setattr(self, "selected", r["id"]), self.refresh()),
                on_error=lambda e: self.status.configure(text=str(e)),
            )
        elif d.get("id"):
            r = next(rr for rr in self.regions if rr["id"] == d["id"])
            dx = int(cx - d["cx0"])
            dy = int(cy - d["cy0"])
            if d.get("corner"):
                x, y, w, h = d["x0"], d["y0"], d["w0"], d["h0"]
                if "e" in d["corner"]:
                    w = max(MIN_SIDE, w + dx)
                if "s" in d["corner"]:
                    h = max(MIN_SIDE, h + dy)
                if "w" in d["corner"]:
                    x, w = x + dx, max(MIN_SIDE, w - dx)
                if "n" in d["corner"]:
                    y, h = y + dy, max(MIN_SIDE, h - dy)
                body = {"x": max(0, x), "y": max(0, y), "w": w, "h": h}
            else:
                body = {"x": max(0, r["x"] + dx), "y": max(0, r["y"] + dy)}
            self.app.run_async(
                lambda: self.app.api.editor_patch(self.game_id, self.image_id, d["id"], body),
                on_done=lambda r2: self.refresh(),
                on_error=lambda e: self.status.configure(text=str(e)),
            )

    def _paint(self, event) -> None:
        cx = int(self.canvas.canvasx(event.x) / self.zoom)
        cy = int(self.canvas.canvasy(event.y) / self.zoom)
        self.app.run_async(
            lambda: self.app.api.editor_mask(
                self.game_id, self.image_id, self._maskvar.get(), cx, cy, self._brushvar.get()
            ),
            on_error=lambda e: self.status.configure(text=str(e)),
        )

    def _tree_select(self, event) -> None:
        sel = self.tree.curselection()
        if not sel:
            return
        r = self.regions[sel[0]]
        self.selected = r["id"]
        self._fill_props(r)
        self._redraw()

    def _fill_props(self, r: dict) -> None:
        style = r.get("style") or {}
        vals = {
            "ocr": r["source_text"],
            "translation": r["corrected_translation"] or r["machine_translation"],
            "x": r["x"],
            "y": r["y"],
            "w": r["w"],
            "h": r["h"],
            "font_size": style.get("font_size", ""),
            "color": style.get("color", ""),
            "stroke": style.get("stroke_width", ""),
            "align": style.get("align", ""),
            "valign": style.get("valign", ""),
        }
        for k, v in vals.items():
            if k in self.props:
                self.props[k].delete(0, "end")
                self.props[k].insert(0, str(v))
        self._badge.set(r["status"])

    def _apply_props(self) -> None:
        if not self.selected:
            return
        g = {k: self.props[k].get().strip() for k in self.props}
        body: dict = {}
        if g["ocr"]:
            body["source_text"] = g["ocr"]
        if g["translation"]:
            body["translation"] = g["translation"]
        for k in ("x", "y", "w", "h"):
            if g[k]:
                body[k] = int(g[k])
        style = {}
        if g["font_size"]:
            style["font_size"] = int(g["font_size"])
        if g["color"]:
            style["color"] = g["color"]
        if g["stroke"]:
            style["stroke_width"] = int(g["stroke"])
        if g["align"]:
            style["align"] = g["align"]
        if g["valign"]:
            style["valign"] = g["valign"]
        if style:
            body["style"] = style
        self.app.run_async(
            lambda: self.app.api.editor_patch(self.game_id, self.image_id, self.selected, body),
            on_done=lambda r: (self.warn(r), self.refresh()),
            on_error=lambda e: self.status.configure(text=str(e)),
        )

    def warn(self, res: dict) -> None:
        self.status.configure(text="; ".join(res.get("warnings", [])) or "guardado ✓")

    def _delete_selected(self) -> None:
        if not self.selected:
            return
        self.app.run_async(
            lambda: self.app.api.editor_delete(self.game_id, self.image_id, self.selected),
            on_done=lambda r: (setattr(self, "selected", None), self.refresh()),
            on_error=lambda e: self.status.configure(text=str(e)),
        )

    def _mask_changed(self) -> None:
        self.status.configure(text=f"máscara: {self._maskvar.get()} (pinta sobre el canvas)")

    def _mode_new(self) -> None:
        self.selected = None
        self.status.configure(text="dibuja un rectángulo en el canvas")

    # --- toolbar ---
    def _undo(self, event=None) -> None:
        self.app.run_async(
            lambda: self.app.api.editor_undo(self.game_id, self.image_id),
            on_done=lambda r: self.refresh(),
        )

    def _redo(self, event=None) -> None:
        self.app.run_async(
            lambda: self.app.api.editor_redo(self.game_id, self.image_id),
            on_done=lambda r: self.refresh(),
        )

    def _preview(self) -> None:
        sel = [self.selected] if self.selected else []
        self.app.run_async(
            lambda: self.app.api.editor_preview(self.game_id, self.image_id, sel),
            on_done=lambda r: (self._set_mode("Final"), self.refresh()),
            on_error=lambda e: self.status.configure(text=str(e)),
            status="Render preview…",
        )

    def _reset(self) -> None:
        body = {"region_id": self.selected} if self.selected else {}
        self.app.run_async(
            lambda: self.app.api.editor_reset(self.game_id, self.image_id, body),
            on_done=lambda r: self.refresh(),
            on_error=lambda e: self.status.configure(text=str(e)),
        )

    def _validate_region(self) -> None:
        if not self.selected:
            return
        self.app.run_async(
            lambda: self.app.api.editor_validate_region(self.game_id, self.image_id, self.selected),
            on_done=lambda r: (self.app.toast("VALIDATED"), self.refresh()),
            on_error=lambda e: self.status.configure(text=str(e)),
        )
