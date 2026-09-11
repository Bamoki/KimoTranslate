"""Google Translate v2 (API key). Key en GOOGLE_TRANSLATE_API_KEY.

v2 no tiene glosarios (son de v3 con config GCP externa): sin reemplazos
ciegos; la terminología viaja solo como metadata de auditoría.
"""

from __future__ import annotations

import os
import time

from .base import TranslationRequest, TranslationResponse
from .http_base import ProviderClient, ProviderError, RetryPolicy


class GoogleTranslationEngine:
    name = "google"

    def __init__(self, api_key: str = "", client: ProviderClient | None = None) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")
        self._client = client or ProviderClient(
            "https://translation.googleapis.com",
            RetryPolicy(max_retries=int(os.environ.get("KIMOTRANSLATE_MAX_RETRIES", "3"))),
        )

    def translate(
        self, request: TranslationRequest, glossary=None, examples=None
    ) -> TranslationResponse:
        if not self.api_key:
            raise ProviderError("GOOGLE_TRANSLATE_API_KEY not configured")
        started = time.time()
        # Key en body (query en URL quedaría en logs del server). Nunca se registra.
        try:
            data = self._client.post(
                "/language/translate/v2",
                payload={
                    "q": request.source_text,
                    "source": request.source_lang,
                    "target": request.target_lang,
                    "format": "text",
                    "key": self.api_key,
                },
            )
            text = data["data"]["translations"][0]["translatedText"]
        except (KeyError, IndexError) as e:
            raise ProviderError(f"unexpected Google response: {e}") from e
        return TranslationResponse(
            translation=text,
            provider="google",
            model="google-v2",
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            duration_s=round(time.time() - started, 2),
            metadata={"terms_seen": [g for g in (glossary or [])] or None},
        )
