"""DeepL: https://api-free.deepl.com (default) o https://api.deepl.com.

Key en DEEPL_API_KEY (header Authorization, nunca en logs/jobs).
Glosario oficial: DEEPL_GLOSSARY_ID si existe (config externa, ver README).
Sin glosario configurado no se toca el texto: la terminología solo viaja
como metadata para auditoría, nunca como reemplazo ciego.
"""

from __future__ import annotations

import os
import time

from .base import TranslationRequest, TranslationResponse
from .http_base import ProviderAuthError, ProviderClient, ProviderError, RetryPolicy

LANG = {"ja": "JA", "es": "ES", "en": "EN"}


class DeepLTranslationEngine:
    name = "deepl"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        glossary_id: str = "",
        client: ProviderClient | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPL_API_KEY", "")
        self.glossary_id = glossary_id or os.environ.get("DEEPL_GLOSSARY_ID", "")
        self._client = client or ProviderClient(
            base_url or os.environ.get("DEEPL_API_URL", "https://api-free.deepl.com"),
            RetryPolicy(max_retries=int(os.environ.get("KIMOTRANSLATE_MAX_RETRIES", "3"))),
        )

    def translate(
        self, request: TranslationRequest, glossary=None, examples=None
    ) -> TranslationResponse:
        if not self.api_key:
            raise ProviderError("DEEPL_API_KEY not configured")
        started = time.time()
        try:
            body = {
                "text": [request.source_text],
                "source_lang": LANG.get(request.source_lang, request.source_lang.upper()),
                "target_lang": LANG.get(request.target_lang, request.target_lang.upper()),
            }
            if self.glossary_id:
                body["glossary_id"] = self.glossary_id
            data = self._client.post(
                "/v2/translate",
                payload=body,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
            )
            text = data["translations"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ProviderError(f"unexpected DeepL response: {e}") from e
        except ProviderAuthError:
            raise
        return TranslationResponse(
            translation=text,
            provider="deepl",
            model="deepl-api",
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            duration_s=round(time.time() - started, 2),
            metadata={
                "glossary_id": self.glossary_id or None,
                "terms_seen": [g for g in (glossary or [])] or None,
            },
        )
