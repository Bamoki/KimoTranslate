"""Cliente del Job system del Hub. Kimo NO tiene queue/workers/stale propios.

Protocolo reutilizado de scripts/pc_worker.py:
heartbeat -> claim(?types=translation) -> progress -> result.
Auth: reutiliza la del Hub (X-Worker-Key; sesión admin para crear jobs en
modo seguro). En LAN abierta todo pasa sin claves.
"""

from __future__ import annotations

import os

import httpx

HUB_PREFIX = "/api/training"
DOMAIN = "translation"
DATASET_ID = "kimo-translations"


class HubError(Exception):
    pass


class HubClient:
    def __init__(
        self,
        base_url: str = "",
        worker_key: str = "",
        admin_user: str = "",
        admin_pass: str = "",
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("KIMOTRANSLATE_HUB_URL", "http://127.0.0.1:8080")
        ).rstrip("/")
        self.worker_key = worker_key or os.environ.get("HUB_WORKER_KEY", "")
        self.admin_user = admin_user or os.environ.get("HUB_ADMIN_USER", "")
        self.admin_pass = admin_pass or os.environ.get("HUB_ADMIN_PASS", "")
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)
        self._logged_in = False

    def _headers(self) -> dict:
        return {"X-Worker-Key": self.worker_key} if self.worker_key else {}

    def _check(self, res: httpx.Response, op: str) -> dict:
        if res.status_code >= 400:
            raise HubError(f"{op}: HTTP {res.status_code} {res.text[:200]}")
        return res.json() if res.text else {}

    def _ensure_admin(self) -> None:
        """Solo si hay credenciales (modo seguro del Hub). En LAN abierta no hace nada."""
        if self._logged_in or not (self.admin_user and self.admin_pass):
            return
        self.login(self.admin_user, self.admin_pass)

    def hub_mode(self) -> dict:
        """¿El Hub exige sesión? (open_mode = sin credenciales, no hace falta login)."""
        try:
            me = self._check(self._client.get("/api/auth/me"), "hub me")
        except HubError as e:
            raise HubError(f"hub unreachable: {e}") from e
        return {"open_mode": bool(me.get("setup_required")), "logged_in": self._logged_in}

    def login(self, username: str, password: str) -> dict:
        """Sesión admin del Hub. La clave queda SOLO en memoria del proceso
        (para re-login si la cookie expira); nunca en disco ni en logs."""
        if not username or not password:
            raise HubError("username and password required")
        res = self._client.post(
            f"{HUB_PREFIX}/../auth/login",
            json={"username": username, "password": password},
        )
        if res.status_code == 403:
            return {"open_mode": True, "logged_in": False}
        self._check(res, "hub login")
        self.admin_user, self.admin_pass = username, password
        self._logged_in = True
        return {"open_mode": False, "logged_in": True, "username": username}

    # --- lectura (abierta) ---
    def health(self) -> dict:
        return self._check(self._client.get("/api/health", timeout=3.0), "hub health")

    def get_job(self, job_id: str) -> dict:
        return self._check(self._client.get(f"{HUB_PREFIX}/jobs/{job_id}"), "get job")

    def list_translation_jobs(self) -> list[dict]:
        data = self._check(self._client.get(f"{HUB_PREFIX}/jobs"), "list jobs")
        return [j for j in data.get("jobs", []) if j.get("domain") == DOMAIN]

    def _admin_write(self, op: str, method: str, path: str, payload: dict) -> dict:
        """POST con re-login único si la cookie expiró (401)."""
        self._ensure_admin()
        res = self._client.post(path, json=payload) if method == "POST" else None
        assert res is not None
        if res.status_code == 401 and (self.admin_user and self.admin_pass):
            self._logged_in = False
            self.login(self.admin_user, self.admin_pass)
            res = self._client.post(path, json=payload)
        return self._check(res, op)

    # --- escritura admin (sesión del Hub si modo seguro) ---
    def ensure_dataset(self) -> dict:
        data = self._check(self._client.get(f"{HUB_PREFIX}/datasets"), "list datasets")
        if any(d.get("id") == DATASET_ID for d in data.get("datasets", [])):
            return {"id": DATASET_ID, "exists": True}
        return self._admin_write(
            "create dataset",
            "POST",
            f"{HUB_PREFIX}/datasets",
            {
                "id": DATASET_ID,
                "name": "KimoTranslate translations",
                "domain": DOMAIN,
                "path": "kimo-translations.jsonl",
            },
        )

    def create_job(
        self, job_id: str, name: str, domain: str, metrics: dict, base_model: str = "kimo"
    ) -> dict:
        self.ensure_dataset()
        return self._admin_write(
            "create job",
            "POST",
            f"{HUB_PREFIX}/jobs",
            {
                "id": job_id,
                "name": name,
                "domain": domain,
                "dataset_id": DATASET_ID,
                "base_model": base_model,
                "method": "custom",
                "device": "remote",
                "mode": "real_training",
                "metrics": metrics,
            },
        )

    def create_translation_job(
        self, job_id: str, name: str, base_model: str, metrics: dict
    ) -> dict:
        """El request de traducción viaja en metrics (dict libre del Hub)."""
        return self.create_job(job_id, name, DOMAIN, metrics, base_model)

    # --- protocolo worker (X-Worker-Key si modo seguro) ---
    def heartbeat(self, worker_id: str, ollama_models: list[str] | None = None) -> dict:
        h = self._headers()
        return self._check(
            self._client.post(
                f"{HUB_PREFIX}/worker/heartbeat",
                json={"worker_id": worker_id, "ollama_models": ollama_models or []},
                headers=h,
            ),
            "heartbeat",
        )

    def claim(self, worker_id: str, types: str = DOMAIN, lease_seconds: int = 300) -> dict | None:
        data = self._check(
            self._client.get(
                f"{HUB_PREFIX}/worker/jobs/claim",
                params={"worker_id": worker_id, "lease_seconds": lease_seconds, "types": types},
                headers=self._headers(),
            ),
            "claim",
        )
        return data.get("job")

    def progress(
        self, job_id: str, progress: float | None = None, metrics: dict | None = None
    ) -> dict:
        return self._check(
            self._client.post(
                f"{HUB_PREFIX}/worker/jobs/{job_id}/progress",
                json={"progress": progress, "metrics": metrics or {}},
                headers=self._headers(),
            ),
            "progress",
        )

    def result(self, job_id: str, ok: bool, metrics: dict | None = None, error: str = "") -> dict:
        return self._check(
            self._client.post(
                f"{HUB_PREFIX}/worker/jobs/{job_id}/result",
                json={
                    "status": "COMPLETED" if ok else "FAILED",
                    "metrics": metrics or {},
                    "error": error,
                },
                headers=self._headers(),
            ),
            "result",
        )
