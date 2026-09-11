"""KimoApiClient: única capa HTTP de la GUI. Sin tkinter (testeable).

Errores técnicos (KeyError, struct.error...) se envuelven en mensajes
comprensibles; el detalle viaja en `details` para [View details].
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class ApiError(Exception):
    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.details = details


def friendly_message(action: str, err: Exception) -> tuple[str, str]:
    if isinstance(err, ApiError):
        return str(err), err.details
    return f"{action} falló", f"{type(err).__name__}: {err}"


class KimoApiClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None, params: dict | None = None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v != ""})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                raw = res.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode()) if e.fp else {}
            except (ValueError, OSError):
                detail = {}
            msg = (
                detail.get("detail", f"error {e.code}") if isinstance(detail, dict) else str(detail)
            )
            raise ApiError(f"El servidor respondió {e.code}: {msg}", str(detail)) from e
        except urllib.error.URLError as e:
            raise ApiError(
                f"Servidor no disponible ({self.base_url})",
                f"revisa la URL en Settings: {e.reason}",
            ) from e
        except (ValueError, OSError) as e:
            raise ApiError("Respuesta inválida del servidor", str(e)) from e

    def _get(self, path: str, params: dict | None = None):
        return self._call("GET", path, params=params)

    def _post(self, path: str, body: dict | None = None):
        return self._call("POST", path, body if body is not None else {})

    # --- sistema ---
    def health(self) -> dict:
        return self._get("/health")

    def hub_status(self) -> dict:
        return self._get("/hub/status")

    def hub_login(self, username: str, password: str) -> dict:
        return self._call("POST", "/hub/login", {"username": username, "password": password})

    def providers(self) -> list:
        return self._get("/providers")

    def release(self) -> dict:
        return self._get("/release")

    # --- juegos ---
    def games(self) -> list:
        return self._get("/games")

    def game(self, game_id: str) -> dict:
        return self._get(f"/games/{game_id}")

    def detect_game(self, path: str) -> dict:
        return self._post("/games/detect", {"path": path})

    def add_game(self, source_path: str, game_id: str = "", name: str = "") -> dict:
        return self._call(
            "POST",
            "/games",
            {"source_path": source_path, "game_id": game_id, "name": name},
        )

    def delete_game(self, game_id: str):
        return self._call("DELETE", f"/games/{game_id}")

    def extract_game(self, game_id: str, local: bool = False) -> dict:
        path = f"/games/{game_id}/extract"
        if local:
            path += "?local=true"
        return self._post(path)

    def sync_game(self, game_id: str) -> dict:
        return self._post(f"/games/{game_id}/sync")

    def export_game(self, game_id: str, output_path: str, local: bool = False) -> dict:
        return self._post(f"/games/{game_id}/export", {"output_path": output_path, "local": local})

    def game_integrity(self, game_id: str, output_path: str = "") -> dict:
        return self._post(f"/games/{game_id}/integrity", {"output_path": output_path})

    def game_texts(self, game_id: str, **filters) -> list:
        return self._get(f"/games/{game_id}/texts", filters)

    def translate_game(
        self, game_id: str, ids: list | None = None, provider: str = "magi", model: str = ""
    ) -> dict:
        return self._post(
            f"/games/{game_id}/translate", {"ids": ids or [], "provider": provider, "model": model}
        )

    # --- traducción simple ---
    def translate(
        self,
        text: str,
        provider: str = "magi",
        model: str = "",
        content_type: str = "vn_dialogue",
        speaker: str = "",
        project_id: str = "",
        game_id: str = "",
    ) -> dict:
        return self._post(
            "/translations",
            {
                "text": text,
                "provider": provider,
                "model": model,
                "context": {
                    "content_type": content_type,
                    "speaker": speaker,
                    "project_id": project_id,
                    "game_id": game_id,
                },
            },
        )

    def job(self, job_id: str) -> dict:
        return self._get(f"/jobs/{job_id}")

    def jobs(self, status: str = "") -> list:
        jobs = self._get("/jobs")
        return [j for j in jobs if not status or j.get("status") == status]

    def retry_job(self, failed_job: dict) -> dict:
        """Reintento = nueva traducción con el request original del job."""
        req = (failed_job.get("metrics") or {}).get("request") or {}
        ctx = req.get("context", {})
        return self.translate(
            req.get("text", ""),
            provider=ctx.get("provider", "magi"),
            model=ctx.get("model", ""),
            content_type=ctx.get("content_type", "vn_dialogue"),
            speaker=ctx.get("speaker", ""),
            project_id=ctx.get("project_id", ""),
            game_id=ctx.get("game_id", ""),
        )

    # --- imágenes ---

    def game_images(self, game_id: str, **filters) -> list:
        return self._get(f"/games/{game_id}/images", filters)

    def image(self, game_id: str, image_id: str) -> dict:
        return self._get(f"/games/{game_id}/images/{image_id}")

    def image_artifact(self, game_id: str, image_id: str, name: str) -> bytes:
        url = f"{self.base_url}/games/{game_id}/images/{image_id}/artifact/{name}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as res:
                return res.read()
        except urllib.error.URLError as e:
            raise ApiError("No se pudo cargar la imagen", str(e)) from e

    def discover_images(self, game_id: str) -> dict:
        return self._post(f"/games/{game_id}/images/discover")

    def ocr_images(self, game_id: str, engine: str = "") -> dict:
        return self._post(f"/games/{game_id}/images/ocr", {"engine": engine})

    def translate_images(self, game_id: str, provider: str = "magi") -> dict:
        return self._post(f"/games/{game_id}/images/translate", {"provider": provider})

    def localize_images(self, game_id: str, local: bool = False) -> dict:
        return self._post(f"/games/{game_id}/images/localize", {"local": local})

    def ocr_image(self, game_id: str, image_id: str, engine: str = "") -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/ocr", {"engine": engine})

    def translate_image(self, game_id: str, image_id: str, provider: str = "magi") -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/translate", {"provider": provider})

    def sync_image(self, game_id: str, image_id: str) -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/sync")

    def localize_image(self, game_id: str, image_id: str, local: bool = False) -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/localize", {"local": local})

    # --- editor ---
    def editor_state(self, game_id: str, image_id: str) -> dict:
        return self._get(f"/games/{game_id}/images/{image_id}/editor")

    def editor_patch(self, game_id: str, image_id: str, region_id: str, body: dict) -> dict:
        return self._call("PATCH", f"/games/{game_id}/images/{image_id}/regions/{region_id}", body)

    def editor_create(self, game_id: str, image_id: str, x: int, y: int, w: int, h: int) -> dict:
        return self._post(
            f"/games/{game_id}/images/{image_id}/regions", {"x": x, "y": y, "w": w, "h": h}
        )

    def editor_delete(self, game_id: str, image_id: str, region_id: str) -> dict:
        return self._call("DELETE", f"/games/{game_id}/images/{image_id}/regions/{region_id}")

    def editor_mask(
        self, game_id: str, image_id: str, tool: str, x: int, y: int, radius: int
    ) -> dict:
        return self._post(
            f"/games/{game_id}/images/{image_id}/mask",
            {"tool": tool, "x": x, "y": y, "radius": radius},
        )

    def editor_preview(self, game_id: str, image_id: str, region_ids: list | None = None) -> dict:
        return self._post(
            f"/games/{game_id}/images/{image_id}/preview", {"region_ids": region_ids or []}
        )

    def editor_undo(self, game_id: str, image_id: str) -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/history/undo")

    def editor_redo(self, game_id: str, image_id: str) -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/history/redo")

    def editor_validate_region(self, game_id: str, image_id: str, region_id: str) -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/regions/{region_id}/validate")

    def editor_validate_image(self, game_id: str, image_id: str) -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/validate")

    def editor_reset(self, game_id: str, image_id: str, body: dict) -> dict:
        return self._post(f"/games/{game_id}/images/{image_id}/reset", body)

    # --- review / knowledge ---
    def corrections(self, status: str = "", project_id: str = "") -> list:
        params = {}
        if status:
            params["status"] = status
        if project_id:
            params["project_id"] = project_id
        return self._get("/corrections", params)

    def save_correction(self, body: dict) -> dict:
        return self._post("/corrections", body)

    def patch_correction(self, cid: str, body: dict) -> dict:
        return self._call("PATCH", f"/corrections/{cid}", body)

    def terminology(self, term: str = "", project_id: str = "", game_id: str = "") -> list:
        params = {}
        if term:
            params["term"] = term
        if project_id:
            params["project_id"] = project_id
        if game_id:
            params["game_id"] = game_id
        return self._get("/terminology", params)

    def add_term(self, body: dict) -> dict:
        return self._post("/terminology", body)

    def memory_search(self, **params) -> list:
        return self._get("/memory/search", params)

    def datasets(self) -> list:
        return self._get("/datasets")

    def build_dataset(self, body: dict) -> dict:
        return self._post("/datasets/build", body)

    def projects(self) -> list:
        return self._get("/projects")
