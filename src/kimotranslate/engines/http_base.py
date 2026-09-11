"""Cliente HTTP común para proveedores externos.

Política única: timeout/429/5xx -> retry con backoff; 4xx -> fail directo.
Sin retries infinitos (max_retries configurable). Las claves nunca aparecen
en errores: se redactan de URLs y cuerpos antes de lanzar.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

_REDACT = re.compile(r"(?i)(auth_key|key|token)=[^&\s]+")


class ProviderError(Exception):
    pass


class ProviderAuthError(ProviderError):
    """4xx permanente (incluye 401/403/456 cuota): no reintentar."""


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base_s: float = 1.0
    timeout_s: float = 15.0


def _clean(text: str) -> str:
    return _REDACT.sub(r"\1=<redacted>", text)


class ProviderClient:
    def __init__(
        self, base_url: str, policy: RetryPolicy | None = None, client: httpx.Client | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.policy = policy or RetryPolicy()
        self._client = client or httpx.Client(base_url=self.base_url, timeout=self.policy.timeout_s)

    def post(
        self,
        path: str,
        *,
        headers: dict | None = None,
        data: dict | None = None,
        payload: dict | None = None,
    ) -> dict:
        last: Exception | None = None
        for attempt in range(self.policy.max_retries + 1):
            try:
                if payload is not None:
                    res = self._client.post(path, json=payload, headers=headers)
                else:
                    res = self._client.post(path, data=data, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last = e
            else:
                if res.status_code == 429 or res.status_code >= 500:
                    last = ProviderError(f"HTTP {res.status_code}: {_clean(res.text[:200])}")
                elif 400 <= res.status_code < 500:
                    raise ProviderAuthError(f"HTTP {res.status_code}: {_clean(res.text[:200])}")
                else:
                    try:
                        return res.json()
                    except ValueError as e:
                        raise ProviderError(f"bad JSON: {_clean(res.text[:200])}") from e
            if attempt < self.policy.max_retries:
                time.sleep(self.policy.backoff_base_s * 2**attempt)
        raise ProviderError(f"failed after {self.policy.max_retries + 1} tries: {last}")
