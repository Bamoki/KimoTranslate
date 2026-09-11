"""Translation Memory sobre MAGI Memory. Cero implementaciones propias.

- Store: magi.memory.MemoryStore (mismo fichero compartido en la Pi).
- Retriever: keyword (default, offline) | semantic | hybrid (ver env).
- Filtros obligatorios: domain, content_type, project — por tags, nunca global.
- Solo entradas `validated`: lo auto nunca alimenta la TM (§19).
- Score: SequenceMatcher stdlib sobre candidatas; umbral configurable.
"""

from __future__ import annotations

import os
from difflib import SequenceMatcher

from ..translate.cache import normalize

CONTENT_TYPES = ("manga", "novel", "vn_dialogue", "game_ui", "image_text")


def _get_magi_memory():
    try:
        from magi.memory.store import MemoryStore
    except ImportError as e:
        raise RuntimeError(f"MAGI not installed (pip install -e ../magi): {e}") from e
    return MemoryStore


def open_store(db_path: str = "", data_dir: str = ""):
    MemoryStore = _get_magi_memory()
    path = db_path or os.environ.get("KIMOTRANSLATE_MEMORY_DB", "")
    if not path:
        if not data_dir:
            from ..core.config import data_dir as default_data_dir

            data_dir = default_data_dir()
        path = os.path.join(data_dir, "memory.db")
    return MemoryStore(path)


def build_retriever(store, kind: str = ""):
    from magi.memory.retriever import (
        HybridMemoryRetriever,
        KeywordMemoryRetriever,
        SemanticMemoryRetriever,
    )

    kind = (kind or os.environ.get("KIMOTRANSLATE_RETRIEVER", "keyword")).lower()
    if kind == "semantic":
        return SemanticMemoryRetriever(store, provider=_embedding_provider())
    if kind == "hybrid":
        return HybridMemoryRetriever(store, provider=_embedding_provider())
    return KeywordMemoryRetriever(store)


def _embedding_provider():
    from magi.memory.embedding_provider import (
        FakeEmbeddingProvider,
        LocalEmbeddingProvider,
        OllamaEmbeddingProvider,
    )

    kind = os.environ.get("KIMOTRANSLATE_EMBEDDINGS", "fake").lower()
    if kind == "local":
        return LocalEmbeddingProvider()
    if kind == "ollama":
        return OllamaEmbeddingProvider(
            base_url=os.environ.get("KIMOTRANSLATE_OLLAMA_URL", "http://localhost:11434")
        )
    return FakeEmbeddingProvider()


def _tags(entry) -> list[str]:
    return list(entry.tags or [])


def _compatible(tags: list[str], content_type: str, project_id: str) -> bool:
    if "validated" not in tags:
        return False
    cts = [t for t in tags if t in CONTENT_TYPES]
    if cts and content_type not in cts:
        return False
    projs = [t.split(":", 1)[1] for t in tags if t.startswith("project:")]
    return not projs or project_id in projs


def score(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def tm_threshold() -> float:
    return float(os.environ.get("KIMOTRANSLATE_TM_THRESHOLD", "0.85"))


class TranslationMemory:
    def __init__(
        self, store=None, retriever=None, threshold: float | None = None, data_dir: str = ""
    ) -> None:
        self.store = store or open_store(data_dir=data_dir)
        self.retriever = retriever or build_retriever(self.store)
        self.threshold = threshold if threshold is not None else tm_threshold()

    def search(
        self,
        query: str,
        domain: str,
        content_type: str = "",
        project_id: str = "",
        game_id: str = "",
        limit: int = 5,
    ) -> list[dict]:
        """Candidatas compatibles con score. Nunca búsqueda global: domain exigido."""
        if not domain:
            return []
        out = []
        for entry in self.retriever.search(query, limit=limit * 4, domain=domain):
            tags = _tags(entry)
            if not _compatible(tags, content_type, project_id):
                continue
            content = entry.content or {}
            source = content.get("source", "")
            if not source:
                continue
            out.append(
                {
                    "source": source,
                    "translation": content.get("translation", ""),
                    "score": round(score(query, source), 3),
                    "content_type": content.get("content_type", ""),
                    "project_id": next(
                        (t.split(":", 1)[1] for t in tags if t.startswith("project:")), ""
                    ),
                    "confidence": entry.confidence,
                    "created": str(entry.created_at or ""),
                }
            )
        # Conflictos (misma fuente, distinta traducción) se conservan;
        # gana: score, específico-de-proyecto, confianza, y primera validada.
        out.sort(key=lambda c: (c["score"], bool(c["project_id"]), c["confidence"] or 0))
        oldest = {}
        for c in out:
            oldest.setdefault((c["source"], c["translation"]), c["created"])
        out.sort(
            key=lambda c: (
                -c["score"],
                not c["project_id"],
                -(c["confidence"] or 0),
                oldest[(c["source"], c["translation"])],
            )
        )
        for c in out:
            del c["created"]
        return out[:limit]

    def find_reusable(self, **kwargs) -> dict | None:
        cands = self.search(**kwargs)
        return cands[0] if cands and cands[0]["score"] >= self.threshold else None

    def add(
        self,
        source: str,
        translation: str,
        domain: str,
        content_type: str = "",
        project_id: str = "",
        game_id: str = "",
        validated: bool = True,
        confidence: float | None = None,
    ) -> None:
        """Solo entradas validadas (correcciones humanas). Lo auto no entra."""
        tags = [content_type] if content_type in CONTENT_TYPES else []
        if project_id:
            tags.append(f"project:{project_id}")
        if game_id:
            tags.append(f"game:{game_id}")
        tags.append("validated" if validated else "auto")
        self.store.add(
            "semantic",
            f"kimo:{normalize(source)[:80]}",
            {
                "source": source,
                "translation": translation,
                "content_type": content_type,
                "domain": domain,
            },
            tags=tags,
            confidence=confidence,
        )
