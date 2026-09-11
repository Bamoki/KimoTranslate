"""Editor visual: Toplevel Tkinter, 100% HTTP. Sin PIL, sin OCR, sin SQLite.

Imágenes vía PhotoImage(data=bytes PNG, nativo en Tk 8.6+). Zoom por
subsample/magnify enteros + fit. Cajas = rectángulos del canvas.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

MODES = ("Original", "OCR", "Translated", "Localized", "Split")


class ImageEditor(tk.Toplevel):
    def __init__(self, master, api, game_id: str, image_id: str) -> None:
        super().__init__(master)
        self.api = api
        self.game_id = game_id
        self.image_id = image_id
        self.title(f"Editor - {image_id}")
        self.geometry("1100x700")
        self.zoom = 1.0
        self.mode = tk.StringVar(value="OCR")
        self.show_boxes = tk.BooleanVar(value=True)
        self.mask_tool = tk.StringVar(value="off")
        self.brush = tk.IntVar(value=8)
        self.selected: str | None = None
        self.regions: list[dict] = []
        self.photos: dict = {}
        self._drag: dict = {}
        self._build()
        self.refresh()
        self._bind_shortcuts()

    # --- layout ---
    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        for m in MODES:
            ttk.Radiobutton(bar, text=m, value=m, variable=self.mode, command=self._redraw).pack(
                side="left"
            )
        for label, fn in (
            ("Undo", self._undo),
            ("Redo", self._redo),
            ("Preview", self._preview),
            ("Reset", self._reset),
            ("Validate", self._validate_img),
        ):
            ttk.Button(bar, text=label, command=fn).pack(side="left")
        ttk.Label(bar, text="Mask:").pack(side="left")
        for t in ("off", "add", "erase"):
            ttk.Radiobutton(bar, text=t, value=t, variable=self.mask_tool).pack(side="left")
        ttk.Scale(bar, from_=2, to=40, variable=self.brush, orient="horizontal", length=80).pack(
            side="left"
        )
        ttk.Button(bar, text="New Region", command=self._mode_new).pack(side="left")

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True)
        cframe = ttk.Frame(mid)
        cframe.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(cframe, bg="gray", scrollregion=(0, 0, 2000, 2000))
        sx = ttk.Scrollbar(cframe, orient="horizontal", command=self.canvas.xview)
        sy = ttk.Scrollbar(cframe, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.canvas.pack(side="top", fill="both", expand=True)
        sx.pack(side="bottom", fill="x")
        sy.pack(side="right", fill="y")
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<B1-Motion>", self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drop)
        self.canvas.bind("<Button-4>", lambda e: self._zoom_step(1.25))
        self.canvas.bind("<Button-5>", lambda e: self._zoom_step(0.8))
        self.canvas.bind("<Delete>", lambda e: self._delete_selected())

        right = ttk.Frame(mid, width=300)
        right.pack(side="right", fill="y")
        ttk.Label(right, text="Regions").pack(anchor="w")
        self.tree = ttk.Treeview(right, columns=("text", "status"), show="headings", height=10)
        self.tree.heading("text", text="OCR -> trad")
        self.tree.heading("status", text="status")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._tree_select)
        self.props = {}
        for key in ("ocr", "translation", "x", "y", "w", "h", "font_size", "color", "stroke"):
            ttk.Label(right, text=key).pack(anchor="w")
            ent = ttk.Entry(right, width=32)
            ent.pack(anchor="w")
            self.props[key] = ent
        ttk.Button(right, text="Apply", command=self._apply_props).pack()
        ttk.Button(right, text="Validate region", command=self._validate_region).pack()
        self.warn = ttk.Label(right, text="", foreground="red")
        self.warn.pack(anchor="w")
        self.status = ttk.Label(self, text="")
        self.status.pack(fill="x")

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-s>", lambda e: self.refresh())
        self.bind("<Control-z>", lambda e: self._undo())
        self.bind("<Control-y>", lambda e: self._redo())
        self.bind("<Control-plus>", lambda e: self._zoom_step(1.25))
        self.bind("<Control-minus>", lambda e: self._zoom_step(0.8))

    # --- datos (HTTP) ---
    def refresh(self) -> None:
        try:
            det = self.api.game_image(self.game_id, self.image_id)
            self.regions = [r for r in det.get("regions", []) if r["status"] != "DELETED"]
            state = self.api.editor_state(self.game_id, self.image_id)
            dirty = state.get("dirty", {})
            self.status.config(text=f"{len(self.regions)} regions | dirty={dirty}")
            self._fill_tree()
            self._redraw()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _fill_tree(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in self.regions:
            self.tree.insert(
                "",
                "end",
                iid=r["id"],
                values=(
                    f"{r['source_text'][:24]} -> "
                    f"{(r['corrected_translation'] or r['machine_translation'])[:24]}",
                    r["status"],
                ),
            )

    def _photo(self, name: str):
        if name not in self.photos:
            try:
                raw = self.api.image_artifact(self.game_id, self.image_id, name)
                self.photos[name] = tk.PhotoImage(data=raw)
            except Exception:
                return None
        return self.photos[name]

    def _base_name(self) -> str:
        mode = self.mode.get()
        if mode in ("Localized", "Translated"):
            return "localized.png"
        return "original.png"

    # --- dibujo ---
    def _redraw(self) -> None:
        self.canvas.delete("all")
        photo = self._photo(self._base_name()) or self._photo("original.png")
        if photo is None:
            self.canvas.create_text(100, 100, text="(sin imagen: localiza primero)")
            return
        z = self.zoom
        img = photo
        if z != 1.0:
            img = photo.zoom(int(z), int(z)) if z >= 1 else photo.subsample(int(1 / z), int(1 / z))
            self.photos["_z"] = img  # ref viva
        self.canvas.create_image(0, 0, anchor="nw", image=img, tags=("base",))
        self.canvas.configure(scrollregion=(0, 0, int(img.width()), int(img.height())))
        if self.show_boxes.get() or self.mode.get() in ("OCR", "Translated"):
            for r in self.regions:
                x0, y0, x1, y1 = (
                    r["x"] * z,
                    r["y"] * z,
                    (r["x"] + r["w"]) * z,
                    (r["y"] + r["h"]) * z,
                )
                color = "red" if r["id"] == self.selected else "yellow"
                self.canvas.create_rectangle(
                    x0, y0, x1, y1, outline=color, width=2, tags=(f"reg:{r['id']}",)
                )
                self.canvas.create_text(
                    x0, y0 - 8, text=r["id"].split(":")[-1], fill=color, anchor="sw"
                )
                if r["id"] == self.selected:
                    for hx, hy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                        self.canvas.create_rectangle(
                            hx - 4, hy - 4, hx + 4, hy + 4, fill="red", tags=("handle",)
                        )

    def _zoom_step(self, factor: float) -> None:
        self.zoom = min(4.0, max(0.25, self.zoom * factor))
        self._redraw()

    def _region_at(self, x: int, y: int) -> dict | None:
        cx, cy = self.canvas.canvasx(x) / self.zoom, self.canvas.canvasy(y) / self.zoom
        for r in self.regions:
            if r["x"] <= cx <= r["x"] + r["w"] and r["y"] <= cy <= r["y"] + r["h"]:
                return r
        return None

    # --- interacción ---
    def _click(self, event) -> None:
        if self.mask_tool.get() != "off":
            self._paint(event)
            return
        r = self._region_at(event.x, event.y)
        if r is None:
            self._new_start(event)
            return
        self.selected = r["id"]
        # ¿handle de resize?
        self._drag = {"id": r["id"], "x0": r["x"], "y": r["y"], "mode": "move"}
        self._fill_props(r)
        self._redraw()

    def _new_start(self, event) -> None:
        cx, cy = self.canvas.canvasx(event.x) / self.zoom, self.canvas.canvasy(event.y) / self.zoom
        self._drag = {"new": True, "x0": cx, "y0": cy}

    def _drag_motion(self, event) -> None:
        if self.mask_tool.get() != "off":
            self._paint(event)
            return
        if not self._drag:
            return
        cx, cy = self.canvas.canvasx(event.x) / self.zoom, self.canvas.canvasy(event.y) / self.zoom
        self._drag["x1"], self._drag["y1"] = cx, cy
        # feedback barato: solo re-dibuja al soltar (HTTP en drop, no por pixel)

    def _drop(self, event) -> None:
        d = self._drag
        self._drag = {}
        if not d or self.mask_tool.get() != "off":
            return
        try:
            if d.get("new"):
                cx, cy = (
                    self.canvas.canvasx(event.x) / self.zoom,
                    self.canvas.canvasy(event.y) / self.zoom,
                )
                x, y = int(min(d["x0"], cx)), int(min(d["y0"], cy))
                w, h = int(abs(cx - d["x0"])), int(abs(cy - d["y0"]))
                res = self.api.editor_create(
                    self.game_id, self.image_id, x, y, max(w, 8), max(h, 8)
                )
                self.selected = res["id"]
            elif d.get("id"):
                cx, cy = (
                    self.canvas.canvasx(event.x) / self.zoom,
                    self.canvas.canvasy(event.y) / self.zoom,
                )
                r = next(r for r in self.regions if r["id"] == d["id"])
                dx, dy = int(cx - d["x0"] - r["w"] / 2), int(cy - d["y"] - r["h"] / 2)
                self.api.editor_patch(
                    self.game_id,
                    self.image_id,
                    d["id"],
                    {"x": max(0, r["x"] + dx), "y": max(0, r["y"] + dy)},
                )
            self.photos.pop("_z", None)
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _paint(self, event) -> None:
        cx, cy = (
            int(self.canvas.canvasx(event.x) / self.zoom),
            int(self.canvas.canvasy(event.y) / self.zoom),
        )
        try:
            self.api.editor_mask(
                self.game_id, self.image_id, self.mask_tool.get(), cx, cy, self.brush.get()
            )
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _tree_select(self, event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        self.selected = sel[0]
        r = next(r for r in self.regions if r["id"] == self.selected)
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
        }
        for k, v in vals.items():
            self.props[k].delete(0, "end")
            self.props[k].insert(0, str(v))

    def _apply_props(self) -> None:
        if not self.selected:
            return

        def g(k: str) -> str:
            return self.props[k].get().strip()

        body: dict = {}
        if g("ocr"):
            body["source_text"] = g("ocr")
        if g("translation"):
            body["translation"] = g("translation")
        for k in ("x", "y", "w", "h"):
            if g(k):
                body[k] = int(g(k))
        style = {}
        if g("font_size"):
            style["font_size"] = int(g("font_size"))
        if g("color"):
            style["color"] = g("color")
        if g("stroke"):
            style["stroke_width"] = int(g("stroke"))
        if style:
            body["style"] = style
        try:
            res = self.api.editor_patch(self.game_id, self.image_id, self.selected, body)
            self.warn.config(text="; ".join(res.get("warnings", [])))
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _delete_selected(self) -> None:
        if not self.selected:
            return
        try:
            self.api.editor_delete(self.game_id, self.image_id, self.selected)
            self.selected = None
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _mode_new(self) -> None:
        self.selected = None
        self.status.config(text="dibuja un rectángulo en el canvas")

    # --- toolbar ---
    def _undo(self) -> None:
        try:
            self.api.editor_undo(self.game_id, self.image_id)
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _redo(self) -> None:
        try:
            self.api.editor_redo(self.game_id, self.image_id)
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _preview(self) -> None:
        try:
            self.api.editor_preview(self.game_id, self.image_id)
            self.photos.pop("localized.png", None)
            self.photos.pop("_z", None)
            self.mode.set("Localized")
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _reset(self) -> None:
        try:
            self.api.editor_reset(self.game_id, self.image_id, {})
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _validate_region(self) -> None:
        if not self.selected:
            return
        try:
            self.api.editor_validate_region(self.game_id, self.image_id, self.selected)
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")

    def _validate_img(self) -> None:
        try:
            res = self.api.editor_validate_image(self.game_id, self.image_id)
            self.status.config(text=f"VALIDATED {res.get('regions', 0)} regiones")
            self.refresh()
        except Exception as e:
            self.status.config(text=f"error: {e}")


def open_editor(master, api, game_id: str, image_id: str) -> ImageEditor:
    return ImageEditor(master, api, game_id, image_id)
