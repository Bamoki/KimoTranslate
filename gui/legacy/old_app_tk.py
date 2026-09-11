"""GUI mínima Tkinter. Solo HTTP contra el server: sin SQLite, sin modelos,
sin MAGI, sin workers. Los jobs/workers los administra el Hub."""

from __future__ import annotations

import json
import os
import tkinter as tk
import urllib.error
import urllib.request
from tkinter import ttk


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def _call(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, headers={"Content-Type": "application/json"}, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read() or b"[]")
        except urllib.error.URLError as e:
            raise ConnectionError(f"servidor no disponible ({self.base}): {e.reason}") from e

    def projects(self):
        return self._call("GET", "/projects")

    def jobs(self):
        return self._call("GET", "/jobs")

    def translate(self, text: str, content_type: str, speaker: str, provider: str):
        return self._call(
            "POST",
            "/translations",
            {
                "text": text,
                "provider": provider,
                "context": {"content_type": content_type, "speaker": speaker},
            },
        )

    def job(self, job_id: str):
        return self._call("GET", f"/jobs/{job_id}")

    def corrections(self):
        return self._call("GET", "/corrections")

    def detect_game(self, path: str):
        return self._call("POST", "/games/detect", {"path": path})

    def add_game(self, path: str):
        return self._call("POST", "/games", {"source_path": path})

    def game_extract(self, game_id: str):
        return self._call("POST", f"/games/{game_id}/extract")

    def game_texts(self, game_id: str, status: str = ""):
        params = f"?status={status}" if status else ""
        return self._call("GET", f"/games/{game_id}/texts{params}")

    def game_translate(self, game_id: str):
        return self._call("POST", f"/games/{game_id}/translate", {})

    def game_sync(self, game_id: str):
        return self._call("POST", f"/games/{game_id}/sync")

    def game_export(self, game_id: str, output: str):
        return self._call("POST", f"/games/{game_id}/export", {"output_path": output})

    def game_images(self, game_id: str):
        return self._call("GET", f"/games/{game_id}/images")

    def game_image(self, game_id: str, image_id: str):
        return self._call("GET", f"/games/{game_id}/images/{image_id}")

    def discover_images(self, game_id: str):
        return self._call("POST", f"/games/{game_id}/images/discover")

    def ocr_images(self, game_id: str):
        return self._call("POST", f"/games/{game_id}/images/ocr", {})

    def translate_images(self, game_id: str):
        return self._call("POST", f"/games/{game_id}/images/translate", {})

    def localize_images(self, game_id: str):
        return self._call("POST", f"/games/{game_id}/images/localize", {"local": False})

    def image_artifact(self, game_id: str, image_id: str, name: str):
        req = urllib.request.Request(
            f"{self.base}/games/{game_id}/images/{image_id}/artifact/{name}"
        )
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.read()

    def editor_state(self, game_id: str, image_id: str):
        return self._call("GET", f"/games/{game_id}/images/{image_id}/editor")

    def editor_patch(self, game_id: str, image_id: str, region_id: str, body: dict):
        return self._call("PATCH", f"/games/{game_id}/images/{image_id}/regions/{region_id}", body)

    def editor_create(self, game_id: str, image_id: str, x: int, y: int, w: int, h: int):
        return self._call(
            "POST", f"/games/{game_id}/images/{image_id}/regions", {"x": x, "y": y, "w": w, "h": h}
        )

    def editor_delete(self, game_id: str, image_id: str, region_id: str):
        return self._call("DELETE", f"/games/{game_id}/images/{image_id}/regions/{region_id}")

    def editor_mask(self, game_id: str, image_id: str, tool: str, x: int, y: int, radius: int):
        return self._call(
            "POST",
            f"/games/{game_id}/images/{image_id}/mask",
            {"tool": tool, "x": x, "y": y, "radius": radius},
        )

    def editor_preview(self, game_id: str, image_id: str, region_ids: list | None = None):
        return self._call(
            "POST", f"/games/{game_id}/images/{image_id}/preview", {"region_ids": region_ids or []}
        )

    def editor_undo(self, game_id: str, image_id: str):
        return self._call("POST", f"/games/{game_id}/images/{image_id}/history/undo", {})

    def editor_redo(self, game_id: str, image_id: str):
        return self._call("POST", f"/games/{game_id}/images/{image_id}/history/redo", {})

    def editor_validate_region(self, game_id: str, image_id: str, region_id: str):
        return self._call(
            "POST", f"/games/{game_id}/images/{image_id}/regions/{region_id}/validate", {}
        )

    def editor_validate_image(self, game_id: str, image_id: str):
        return self._call("POST", f"/games/{game_id}/images/{image_id}/validate", {})

    def editor_reset(self, game_id: str, image_id: str, body: dict):
        return self._call("POST", f"/games/{game_id}/images/{image_id}/reset", body)

    def hub_status(self):
        return self._call("GET", "/hub/status")

    def hub_login(self, username: str, password: str):
        return self._call("POST", "/hub/login", {"username": username, "password": password})

    def save_correction(self, body: dict):
        return self._call("POST", "/corrections", body)

    def patch_correction(self, cid: str, body: dict):
        return self._call("PATCH", f"/corrections/{cid}", body)

    def add_term(self, body: dict):
        return self._call("POST", "/terminology", body)


def _app_version() -> str:
    """Versión única: src/kimotranslate/__init__.py (repo/dev) o
    build_version.txt estampado por PyInstaller (bundle)."""
    try:
        from kimotranslate import __version__

        return __version__
    except ImportError:
        pass
    import os
    import re
    import sys

    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "build_version.txt"))
    candidates.append(os.path.join(os.path.dirname(__file__), "..", "..", "build_version.txt"))
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                v = f.read().strip()
            if v:
                return v
        except OSError:
            continue
    try:
        init = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "kimotranslate", "__init__.py"
        )
        m = re.search(r'__version__\s*=\s*"([^"]+)"', open(init, encoding="utf-8").read())
        if m:
            return m.group(1)
    except OSError:
        pass
    return "0.0.0-dev"


def _gui_module(name: str):
    """Importa gui/tkinter/<name>.py o gui/<name>.py por ruta (script o bundle)."""
    import importlib.util
    import os
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    paths = [os.path.join(here, name + ".py"), os.path.join(here, "..", name + ".py")]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        paths += [
            os.path.join(sys._MEIPASS, "gui", "tkinter", name + ".py"),
            os.path.join(sys._MEIPASS, "gui", name + ".py"),
        ]
    for path in paths:
        path = os.path.normpath(path)
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location(f"kimo_gui_{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise ImportError(name)


class App(tk.Tk):
    def __init__(self, api: Api) -> None:
        super().__init__()
        self.api = api
        self.version = _app_version()
        self.title(f"KimoTranslate {self.version}")
        self.geometry("700x520")
        self._cfg_mod = _gui_module("config")
        self._update_mod = _gui_module("update")
        self.cfg = self._cfg_mod.load()
        import os as _os

        if _os.environ.get("KIMOTRANSLATE_SERVER_URL"):
            # Env explícito gana a la config guardada (primer arranque/dev).
            self.cfg["server_url"] = _os.environ["KIMOTRANSLATE_SERVER_URL"]
        self.api.base = self.cfg.get("server_url", api.base).rstrip("/")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self._translate_tab(nb)
        self._review_tab(nb)
        self._games_tab(nb)
        self._images_tab(nb)
        self.tabs: dict[str, tk.Text] = {}
        for name in ("Projects", "Jobs", "Logs"):
            frame = ttk.Frame(nb)
            nb.add(frame, text=name)
            txt = tk.Text(frame, height=18, width=80)
            txt.pack(fill="both", expand=True)
            ttk.Button(frame, text="Refresh", command=lambda n=name: self.refresh(n)).pack()
            self.tabs[name] = txt
        self._settings_tab(nb)
        self.log("GUI ready. Server: " + api.base)
        self.after(2000, self._auto_update_check)

    def _translate_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Translate")
        ttk.Label(f, text="Japanese text:").pack(anchor="w")
        self.src = tk.Text(f, height=5, width=80)
        self.src.pack()
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Content type:").pack(side="left")
        self.ctype = ttk.Combobox(row, values=["vn_dialogue", "game_ui", "image_text"], width=15)
        self.ctype.set("vn_dialogue")
        self.ctype.pack(side="left")
        ttk.Label(row, text="Speaker:").pack(side="left")
        self.speaker = ttk.Entry(row, width=20)
        self.speaker.pack(side="left")
        ttk.Label(row, text="Provider:").pack(side="left")
        self.provider = ttk.Combobox(row, values=["magi", "deepl", "google", "ollama"], width=10)
        self.provider.set("magi")
        self.provider.pack(side="left")
        ttk.Button(f, text="Translate", command=self.do_translate).pack()
        ttk.Label(f, text="Result:").pack(anchor="w")
        self.result = tk.Text(f, height=8, width=80)
        self.result.pack()
        self.status = ttk.Label(f, text="")
        self.status.pack()

    def do_translate(self) -> None:
        try:
            res = self.api.translate(
                self.src.get("1.0", "end").strip(),
                self.ctype.get(),
                self.speaker.get(),
                self.provider.get(),
            )
        except Exception as e:
            self.status.config(text=f"error: {e}")
            return
        if res.get("cached") or res.get("memory_hit"):
            self._show(res["translation"], self._flags(res))
        elif res.get("job_id"):
            self.status.config(text=f"translating... {res['job_id']}")
            self.after(1000, lambda: self._poll(res["job_id"]))

    def _flags(self, res: dict) -> str:
        return (
            f"provider={res.get('provider')} cache="
            f"{'HIT' if res.get('cached') else 'MISS'} TM="
            f"{'HIT' if res.get('memory_hit') else 'MISS'}"
        )

    def _poll(self, job_id: str) -> None:
        try:
            res = self.api.job(job_id)
        except Exception as e:
            self.status.config(text=f"error: {e}")
            return
        if res.get("translation"):
            self._show(res["translation"], self._flags(res))
        elif res.get("status") in ("QUEUED", "RUNNING"):
            self.after(1000, lambda: self._poll(job_id))
        else:
            self.status.config(text=f"{res['status']}: {res.get('error')}")

    def _show(self, text: str, note: str) -> None:
        self.result.delete("1.0", "end")
        self.result.insert("end", text or "")
        self.status.config(text=note)

    def _review_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Review")
        self.rev: dict[str, tk.Text | ttk.Entry] = {}
        for label, key, height in (
            ("Original", "source", 3),
            ("Machine", "machine", 3),
            ("Correction", "corrected", 3),
        ):
            ttk.Label(f, text=label + ":").pack(anchor="w")
            txt = tk.Text(f, height=height, width=80)
            txt.pack()
            self.rev[key] = txt
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.rev_id = ttk.Entry(row, width=14)
        self.rev_id.pack(side="left")
        ttk.Button(row, text="Load job", command=self._rev_load_job).pack(side="left")
        ttk.Button(row, text="Save", command=lambda: self._rev_act("save")).pack(side="left")
        ttk.Button(row, text="Validate", command=lambda: self._rev_act("validate")).pack(
            side="left"
        )
        ttk.Button(row, text="Reject", command=lambda: self._rev_act("reject")).pack(side="left")
        ttk.Button(row, text="To terminology", command=lambda: self._rev_act("term")).pack(
            side="left"
        )
        self.rev_status = ttk.Label(f, text="")
        self.rev_status.pack()

    def _rev_text(self, key: str) -> str:
        return self.rev[key].get("1.0", "end").strip()

    def _rev_load_job(self) -> None:
        try:
            res = self.api.job(self.rev_id.get().strip())
            self.rev["source"].delete("1.0", "end")
            self.rev["machine"].delete("1.0", "end")
            self.rev["machine"].insert("end", res.get("translation") or "")
            self.rev_status.config(text=f"{res['status']} provider={res.get('provider')}")
        except Exception as e:
            self.rev_status.config(text=f"error: {e}")

    def _rev_act(self, act: str) -> None:
        try:
            if act == "save":
                res = self.api.save_correction(
                    {
                        "source_text": self._rev_text("source"),
                        "machine_translation": self._rev_text("machine"),
                        "corrected_translation": self._rev_text("corrected"),
                    }
                )
                self.rev_id.delete(0, "end")
                self.rev_id.insert(0, res["id"])
                self.rev_status.config(text=f"saved {res['status']}")
            elif act == "term":
                self.api.add_term(
                    {"term": self._rev_text("source"), "preferred": self._rev_text("corrected")}
                )
                self.rev_status.config(text="term added (global)")
            else:
                cid = self.rev_id.get().strip()
                if act == "validate":
                    res = self.api.patch_correction(cid, {"validated": True})
                    self.rev_status.config(text=f"VALIDATED -> TM + example ({res['id']})")
                else:
                    self.api.patch_correction(cid, {"rejected": True})
                    self.rev_status.config(text="REJECTED")
        except Exception as e:
            self.rev_status.config(text=f"error: {e}")

    def log(self, msg: str) -> None:
        self.tabs["Logs"].insert("end", msg + "\n")

    def _games_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Games")
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Game:").pack(side="left")
        self.game_path = ttk.Entry(row, width=50)
        self.game_path.pack(side="left")
        self.game_id = ttk.Entry(row, width=16)
        self.game_id.pack(side="left")
        for label, fn in (
            ("Detect", self._g_detect),
            ("Add", self._g_add),
            ("Extract", self._g_extract),
            ("Translate", self._g_translate),
            ("Sync", self._g_sync),
            ("Export", self._g_export),
        ):
            ttk.Button(row, text=label, command=fn).pack(side="left")
        self.game_stats = ttk.Label(f, text="")
        self.game_stats.pack(anchor="w")
        cols = ("speaker", "scene", "source", "translation", "status")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=12)
        for c, w in (
            ("speaker", 90),
            ("scene", 90),
            ("source", 260),
            ("translation", 260),
            ("status", 90),
        ):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)
        brow = ttk.Frame(f)
        brow.pack(fill="x")
        self.game_filter = ttk.Combobox(
            brow, values=["", "EXTRACTED", "TRANSLATED", "REVIEW_REQUIRED", "VALIDATED"], width=14
        )
        self.game_filter.pack(side="left")
        ttk.Button(brow, text="List", command=self._g_list).pack(side="left")
        ttk.Button(brow, text="To Review", command=self._g_to_review).pack(side="left")

    def _g(self, fn, ok):
        try:
            res = fn()
            self.game_stats.config(text=json.dumps(res, ensure_ascii=False)[:300])
        except Exception as e:
            self.game_stats.config(text=f"error: {e}")

    def _g_detect(self):
        self._g(lambda: self.api.detect_game(self.game_path.get()), None)

    def _g_add(self):
        def go():
            res = self.api.add_game(self.game_path.get())
            self.game_id.delete(0, "end")
            self.game_id.insert(0, res["game_id"])
            return res

        self._g(go, None)

    def _g_extract(self):
        self._g(lambda: self.api.game_extract(self.game_id.get()), None)

    def _g_translate(self):
        self._g(lambda: self.api.game_translate(self.game_id.get()), None)

    def _g_sync(self):
        self._g(lambda: self.api.game_sync(self.game_id.get()), None)

    def _g_export(self):
        self._g(
            lambda: self.api.game_export(self.game_id.get(), self.game_path.get() + "_es"), None
        )

    def _g_list(self):
        try:
            rows = self.api.game_texts(self.game_id.get(), self.game_filter.get())
            for i in self.tree.get_children():
                self.tree.delete(i)
            for r in rows[:500]:
                self.tree.insert(
                    "",
                    "end",
                    iid=r["id"],
                    values=(
                        r["speaker"],
                        r["scene"],
                        r["source_text"][:80],
                        (r["corrected_translation"] or r["machine_translation"])[:80],
                        r["status"],
                    ),
                )
            self.game_stats.config(text=f"{len(rows)} texts")
        except Exception as e:
            self.game_stats.config(text=f"error: {e}")

    def _g_to_review(self):
        sel = self.tree.selection()
        if not sel:
            return
        try:
            rows = self.api.game_texts(self.game_id.get())
            row = next(r for r in rows if r["id"] == sel[0])
            # Reutiliza la pestaña Review (sin segundo sistema de revisión).
            for key, val in (
                ("source", row["source_text"]),
                ("machine", row["machine_translation"]),
                ("corrected", row["corrected_translation"]),
            ):
                self.rev[key].delete("1.0", "end")
                self.rev[key].insert("end", val)
        except Exception as e:
            self.game_stats.config(text=f"error: {e}")

    def _images_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Images")
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Game:").pack(side="left")
        self.img_game = ttk.Entry(row, width=16)
        self.img_game.pack(side="left")
        for label, fn in (
            ("Discover", self._i_discover),
            ("OCR", self._i_ocr),
            ("Translate", self._i_translate),
            ("Localize", self._i_localize),
            ("List", self._i_list),
        ):
            ttk.Button(row, text=label, command=fn).pack(side="left")
        self.img_stats = ttk.Label(f, text="")
        self.img_stats.pack(anchor="w")
        cols = ("relpath", "likely", "ocr", "loc")
        self.img_tree = ttk.Treeview(f, columns=cols, show="headings", height=8)
        for c, w in (("relpath", 300), ("likely", 60), ("ocr", 90), ("loc", 90)):
            self.img_tree.heading(c, text=c)
            self.img_tree.column(c, width=w)
        self.img_tree.pack(fill="both", expand=True)
        self.img_detail = tk.Text(f, height=8, width=80)
        self.img_detail.pack(fill="both", expand=True)
        ttk.Button(f, text="Show regions", command=self._i_detail).pack()
        ttk.Button(f, text="To Review", command=self._i_to_review).pack()
        ttk.Button(f, text="Open Editor", command=self._i_open_editor).pack()

    def _i(self, fn):
        try:
            res = fn()
            self.img_stats.config(text=json.dumps(res, ensure_ascii=False)[:300])
        except Exception as e:
            self.img_stats.config(text=f"error: {e}")

    def _i_discover(self):
        self._i(lambda: self.api.discover_images(self.img_game.get()))

    def _i_ocr(self):
        self._i(lambda: self.api.ocr_images(self.img_game.get()))

    def _i_translate(self):
        self._i(lambda: self.api.translate_images(self.img_game.get()))

    def _i_localize(self):
        self._i(lambda: self.api.localize_images(self.img_game.get()))

    def _i_list(self):
        try:
            rows = self.api.game_images(self.img_game.get())
            for i in self.img_tree.get_children():
                self.img_tree.delete(i)
            for r in rows:
                self.img_tree.insert(
                    "",
                    "end",
                    iid=r["id"],
                    values=(
                        r["relpath"],
                        r["likely_text"],
                        r["ocr_status"],
                        r["localization_status"],
                    ),
                )
            self.img_stats.config(text=f"{len(rows)} images")
        except Exception as e:
            self.img_stats.config(text=f"error: {e}")

    def _i_detail(self):
        sel = self.img_tree.selection()
        if not sel:
            return
        try:
            det = self.api.game_image(self.img_game.get(), sel[0])
            lines = [
                f"{i}: {r['source_text']} -> "
                f"{r['corrected_translation'] or r['machine_translation']} "
                f"[{r['status']}]"
                for i, r in enumerate(det.get("regions", []))
            ]
            self.img_detail.delete("1.0", "end")
            self.img_detail.insert(
                "end", f"{det['relpath']} {det['width']}x{det['height']}\n" + "\n".join(lines)
            )
        except Exception as e:
            self.img_stats.config(text=f"error: {e}")

    def _i_to_review(self):
        sel = self.img_tree.selection()
        if not sel:
            return
        try:
            det = self.api.game_image(self.img_game.get(), sel[0])
            regs = det.get("regions", [])
            if not regs:
                return
            r = regs[0]
            for key, val in (
                ("source", r["source_text"]),
                ("machine", r["machine_translation"]),
                ("corrected", r["corrected_translation"]),
            ):
                self.rev[key].delete("1.0", "end")
                self.rev[key].insert("end", val)
            self.img_stats.config(text=f"region {r['id']} conf={r['confidence']} -> Review")
        except Exception as e:
            self.img_stats.config(text=f"error: {e}")

    def _i_open_editor(self):
        sel = self.img_tree.selection()
        if not sel:
            self.img_stats.config(text="selecciona una imagen")
            return
        try:
            try:
                from gui.images.editor import open_editor
            except ImportError:
                import os
                import sys

                sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
                from gui.images.editor import open_editor

            open_editor(self, self.api, self.img_game.get(), sel[0])
        except Exception as e:
            self.img_stats.config(text=f"error: {e}")

    def refresh(self, tab: str) -> None:
        try:
            data = {
                "Projects": self.api.projects,
                "Jobs": self.api.jobs,
            }[tab]()
            txt = self.tabs[tab]
            txt.delete("1.0", "end")
            txt.insert("end", json.dumps(data, indent=1, ensure_ascii=False))
            self.log(f"{tab} refreshed")
        except Exception as e:
            self.log(f"{tab} error: {e}")

    def _settings_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Settings")
        ttk.Label(f, text=f"KimoTranslate {self.version}").pack(anchor="w")
        ttk.Label(f, text="Raspberry-Hub URL:").pack(anchor="w")
        self.server_entry = ttk.Entry(f, width=50)
        self.server_entry.pack(anchor="w")
        self.server_entry.insert(0, self.api.base)
        ttk.Label(f, text="Hub admin (solo si el Hub pide sesión):").pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w")
        ttk.Label(row, text="Usuario:").pack(side="left")
        self.hub_user = ttk.Entry(row, width=16)
        self.hub_user.pack(side="left")
        self.hub_user.insert(0, self.cfg.get("hub_user", ""))
        ttk.Label(row, text="Clave:").pack(side="left")
        self.hub_pass = ttk.Entry(row, width=16, show="•")
        self.hub_pass.pack(side="left")
        ttk.Button(row, text="Conectar", command=self._hub_connect).pack(side="left")
        self.hub_status = ttk.Label(f, text="")
        self.hub_status.pack(anchor="w")
        self.auto_update = tk.BooleanVar(value=bool(self.cfg.get("auto_update", True)))
        ttk.Checkbutton(
            f, text="Buscar actualizaciones automáticamente", variable=self.auto_update
        ).pack(anchor="w")
        ttk.Button(f, text="Save", command=self._save_settings).pack(anchor="w")
        ttk.Button(f, text="Buscar actualizaciones", command=self._manual_update_check).pack(
            anchor="w"
        )
        self.settings_status = ttk.Label(f, text="")
        self.settings_status.pack(anchor="w")
        self._hub_refresh_status()

    def _hub_refresh_status(self) -> None:
        try:
            st = self.api.hub_status()
            if st.get("open_mode"):
                self.hub_status.config(text="Hub: modo abierto (sin sesión)")
            elif st.get("logged_in"):
                self.hub_status.config(text="Hub: sesión activa")
            else:
                self.hub_status.config(text="Hub: requiere sesión (pon usuario/clave)")
        except Exception as e:
            self.hub_status.config(text=f"Hub: {e}")

    def _hub_connect(self) -> None:
        try:
            res = self.api.hub_login(self.hub_user.get().strip(), self.hub_pass.get())
            self.hub_pass.delete(0, "end")  # la clave no se queda en la GUI
            if res.get("open_mode"):
                self.hub_status.config(text="Hub: modo abierto (no hacía falta)")
            else:
                self.hub_status.config(text=f"Hub: sesión activa ({res.get('username')})")
            self.cfg["hub_user"] = self.hub_user.get().strip()
            try:
                self._cfg_mod.save(self.cfg)
            except OSError:
                pass
        except Exception as e:
            self.hub_status.config(text=f"Hub: {e}")

    def _save_settings(self) -> None:
        url = self.server_entry.get().strip().rstrip("/")
        if not (url.startswith("http://") or url.startswith("https://")):
            self.settings_status.config(text="URL debe empezar por http(s)://")
            return
        self.api.base = url
        self.cfg["server_url"] = url
        self.cfg["auto_update"] = bool(self.auto_update.get())
        try:
            self._cfg_mod.save(self.cfg)
            self.settings_status.config(text=f"guardado. Servidor: {url}")
        except OSError as e:
            self.settings_status.config(text=f"error guardando: {e}")
        self.log("settings saved")

    def _auto_update_check(self) -> None:
        if self.cfg.get("auto_update", True) and self._update_mod.should_auto_check(
            self.cfg.get("last_update_check", "")
        ):
            self._check_updates(silent=True)

    def _manual_update_check(self) -> None:
        self._check_updates(silent=False)

    def _check_updates(self, silent: bool) -> None:
        from datetime import UTC, datetime

        try:
            manifest = self._update_mod.fetch_manifest(self.api.base)
        except Exception as e:
            if not silent:
                self.settings_status.config(text=f"actualización: {e}")
            return
        self.cfg["last_update_check"] = datetime.now(UTC).isoformat()
        try:
            self._cfg_mod.save(self.cfg)
        except OSError:
            pass
        if not self._update_mod.is_newer(self.version, manifest["latest_version"]):
            if not silent:
                self.settings_status.config(text=f"ya estás en la última ({self.version})")
            return
        self._update_dialog(manifest)

    def _update_dialog(self, manifest: dict) -> None:
        win = tk.Toplevel(self)
        win.title("Actualización disponible")
        ttk.Label(
            win,
            text=f"Nueva versión disponible: {manifest['latest_version']} "
            f"(instalada: {self.version})",
        ).pack(padx=20, pady=10)
        row = ttk.Frame(win)
        row.pack(pady=10)
        ttk.Button(
            row, text="Actualizar", command=lambda: (win.destroy(), self._do_update(manifest))
        ).pack(side="left")
        ttk.Button(row, text="Ahora no", command=win.destroy).pack(side="left")

    def _do_update(self, manifest: dict) -> None:
        import sys

        try:
            part = self._update_mod.download(self.api.base, manifest["filename"])
            self._update_mod.verify(part, manifest["sha256"])
        except Exception as e:
            self.settings_status.config(text=f"actualización fallida: {e} (instalación intacta)")
            return
        updater = self._updater_path()
        if updater is None:
            self.settings_status.config(
                text=f"updater no disponible en modo desarrollo (descarga verificada en {part})"
            )
            return
        import subprocess

        args = [updater, "--current", sys.executable, "--new", part, "--sha256", manifest["sha256"]]
        try:
            subprocess.Popen(args)
        except OSError as e:
            self.settings_status.config(text=f"no se pudo lanzar updater: {e}")
            return
        self.destroy()

    def _updater_path(self) -> str | None:
        import os
        import sys

        if getattr(sys, "frozen", False):
            cand = os.path.join(os.path.dirname(sys.executable), "KimoTranslate-Updater.exe")
            return cand if os.path.exists(cand) else None
        return None


def main() -> None:
    import os as _os

    roots = [p for p in _os.environ.get("KIMOTRANSLATE_GAME_ROOTS", "").split(_os.pathsep) if p]
    app = App(Api(os.environ.get("KIMOTRANSLATE_SERVER_URL", "http://127.0.0.1:8005")))
    if roots:
        app.game_path.insert(0, roots[0])
    app.mainloop()


if __name__ == "__main__":
    main()
