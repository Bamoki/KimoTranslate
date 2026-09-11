"""MagiTranslationEngine: traduce con MAGI sin copiar MAGI.

Reutiliza de MAGI: OllamaClient (transporte+retry), PromptSpec (prompts
versionados), MemoryStore/HybridRetriever (memoria, con domain filter).
NO usa el Committee: su normalización es financiera (stance/symbols/echo
gates) y pelearía contra JSON de traducción; además votar 3 modelos por
string es VRAM-thrash en el worker. Una llamada generate + parse
determinista es lo correcto aquí.

Sin Ollama (tests/smoke sin GPU): inyectar backend falso con .generate().
Con Ollama en el worker: backend=None lo crea solo. Cero cambios de código.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from ..knowledge.interfaces import TranslationContext
from .base import TranslationRequest, TranslationResponse

DOMAIN_DEFAULT = "game_translation"
PROMPT_NAME = "kimotranslate.translate"
PROMPT_VERSION = 1

SYSTEM_TRANSLATE = (
    "You are a Japanese-to-target game localizer. Respond with JSON only: "
    '{"translation": "...", "confidence": 0.0-1.0}. '
    "Respect speaker tone, glossary terms and visual-novel/UI context. "
    "Never explain, never add notes."
)

TEMPLATE = (
    "Translate [$source_lang -> $target_lang] ($content_type, domain $domain).\n"
    "Speaker: $speaker | Scene: $scene | Tone: $tone\n"
    "Previous: $previous\nNext: $next\n"
    "Glossary (preferred terms): $glossary\n"
    "Similar approved examples: $examples\n"
    "Text: $text"
)


class EngineError(Exception):
    pass


def _get_magi():
    try:
        import magi  # noqa: F401
        from magi.common.prompts import PromptSpec, get_prompt, register_prompt
        from magi.ollama.client import create_ollama_client
    except ImportError as e:
        raise EngineError(f"MAGI not installed (pip install -e ../magi): {e}") from e
    return PromptSpec, get_prompt, register_prompt, create_ollama_client


def _ensure_prompt() -> None:
    PromptSpec, get_prompt, register_prompt, _ = _get_magi()
    try:
        get_prompt(PROMPT_NAME, PROMPT_VERSION)
    except KeyError:
        register_prompt(PromptSpec(name=PROMPT_NAME, version=PROMPT_VERSION, template=TEMPLATE))


class KimoTranslateAdapter:
    """Adapter MAGI (DomainAdapter): contexto <-> resultado. Sin lógica de red."""

    def build_context(self, query: str, **kwargs) -> dict:
        ctx: TranslationContext = kwargs.get("context") or TranslationContext()
        extra = ctx.extra
        return {
            "query": query,
            "text": query,
            "source_lang": kwargs.get("source_lang", "ja"),
            "target_lang": kwargs.get("target_lang", "es"),
            "content_type": ctx.content_type,
            "domain": ctx.domain or DOMAIN_DEFAULT,
            "speaker": ctx.speaker,
            "scene": ctx.scene,
            "project_id": ctx.project_id,
            "game_id": ctx.game_id,
            "previous_text": extra.get("previous_text", ""),
            "next_text": extra.get("next_text", ""),
            "relationship": extra.get("relationship", ""),
            "tone": extra.get("tone", ""),
            "glossary": kwargs.get("glossary", []),
            "examples": kwargs.get("examples", []),
        }

    def allowed_symbols(self, context: dict) -> set[str]:
        """Reuso del concepto MAGI: términos preferidos que el modelo debe respetar."""
        return {str(t) for t in context.get("glossary", [])}

    def interpret_result(self, result: dict) -> dict:
        if not result.get("translation"):
            raise EngineError(f"empty translation in {result}")
        return {
            "translation": result["translation"],
            "confidence": float(result.get("confidence", 0.0)),
        }


class MagiTranslationEngine:
    """provider=magi u ollama (mismo camino MAGI->Ollama; solo cambia el nombre).

    La memoria de lectura la aporta el caller (examples ya filtrados por el
    wrapper de TM). Este engine NO escribe memoria: solo entradas validadas
    alimentan conocimiento (§19).
    """

    def __init__(
        self,
        backend=None,
        model: str = "",
        adapter: KimoTranslateAdapter | None = None,
        provider: str = "magi",
    ) -> None:
        self.provider = provider
        self.name = provider
        self.model = model or os.environ.get("KIMOTRANSLATE_MODEL", "qwen2.5:7b")
        self.backend = backend  # None -> Ollama real (lazy); tests inyectan falso
        self.adapter = adapter or KimoTranslateAdapter()

    def _backend(self):
        if self.backend is None:
            _, _, _, create_ollama_client = _get_magi()
            self.backend = create_ollama_client()
        return self.backend

    def translate(
        self,
        request: TranslationRequest,
        glossary: list | None = None,
        examples: list | None = None,
    ) -> TranslationResponse:
        import time

        _ensure_prompt()
        _, get_prompt, _, _ = _get_magi()
        started = time.time()
        terms = [f"{g['term']} = {g['preferred']}" for g in (glossary or [])]
        ctx = self.adapter.build_context(
            request.source_text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            context=request.context,
            glossary=terms,
            examples=examples or [],
        )
        prompt = get_prompt(PROMPT_NAME, PROMPT_VERSION).render(
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            content_type=request.context.content_type,
            domain=request.context.domain or DOMAIN_DEFAULT,
            speaker=request.context.speaker or "-",
            scene=request.context.scene or "-",
            tone=request.context.extra.get("tone", "-"),
            previous=request.context.extra.get("previous_text", "-"),
            next=request.context.extra.get("next_text", "-"),
            glossary="\n".join(terms) or "-",
            examples=json.dumps(ctx["examples"], ensure_ascii=False)[:2000],
            text=request.source_text,
        )
        out = self._backend().generate(
            model=self.model,
            prompt=prompt,
            system=SYSTEM_TRANSLATE,
            json_mode=True,
            temperature=0.0,
        )
        parsed = _parse_json(out.text)
        final = self.adapter.interpret_result(parsed)
        return TranslationResponse(
            translation=final["translation"],
            provider=self.provider,
            model=self.model,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            duration_s=round(time.time() - started, 2),
            confidence=final["confidence"],
            prompt_version=f"{PROMPT_NAME}@v{PROMPT_VERSION}",
            metadata={"terms_applied": len(terms), "examples_seen": len(ctx["examples"])},
        )


def _parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"translation": text}
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
    raise EngineError(f"non-JSON model output: {text[:200]}")


@dataclass
class FakeBackend:
    """Backend MAGI falso para tests/smoke: misma interfaz .generate()."""

    text: str = '{"translation": "MOCK", "confidence": 1.0}'

    def generate(self, model: str, prompt: str, **kwargs):
        from collections import namedtuple

        return namedtuple("Gen", ["text"])(self.text)
