"""TranslationEngine: interfaz común. La API depende de esto, nunca de un proveedor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..knowledge.interfaces import TranslationContext


@dataclass(frozen=True)
class TranslationRequest:
    source_text: str
    source_lang: str = "ja"
    target_lang: str = "es"
    context: TranslationContext = field(default_factory=TranslationContext)


@dataclass(frozen=True)
class TranslationResponse:
    """Resultado normalizado de cualquier proveedor (confidence opcional)."""

    translation: str
    provider: str
    model: str = ""
    source_lang: str = "ja"
    target_lang: str = "es"
    cached: bool = False
    memory_hit: bool = False
    duration_s: float = 0.0
    confidence: float | None = None
    prompt_version: str = ""
    metadata: dict = field(default_factory=dict)


class TranslationEngine(Protocol):
    name: str

    def translate(
        self,
        request: TranslationRequest,
        glossary: list | None = None,
        examples: list | None = None,
    ) -> TranslationResponse: ...


class MockEngine:
    """Solo para probar la arquitectura sin modelos."""

    name = "mock"

    def translate(
        self, request: TranslationRequest, glossary=None, examples=None
    ) -> TranslationResponse:
        return TranslationResponse(
            translation=f"[mock:{request.target_lang}] {request.source_text}",
            provider="mock",
            model="mock-0.1",
            source_lang=request.source_lang,
            target_lang=request.target_lang,
        )
