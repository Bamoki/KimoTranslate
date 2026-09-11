"""Tests Fase 1 (adaptados a Fase 2: jobs/workers viven en el Hub)."""

from __future__ import annotations

import pytest

from kimotranslate.engines.base import MockEngine, TranslationRequest
from kimotranslate.knowledge.interfaces import ContentType, TranslationContext


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["hub"] == "ok"


def test_projects(client):
    p = client.post("/projects", json={"name": "game_001"}).json()
    assert p["id"]
    assert client.get("/projects").json()


def test_empty_text_rejected(client):
    r = client.post("/translations", json={"text": "  "})
    assert r.status_code == 400


def test_engine_interface():
    res = MockEngine().translate(TranslationRequest("こんにちは"))
    assert res.translation and res.provider == "mock"


def test_context_tags_mandatory():
    ctx = TranslationContext(source_app="tradujap", content_type=ContentType.MANGA, domain="manga")
    assert ctx.content_type != ContentType.VN_DIALOGUE  # no se mezclan


def test_cache_roundtrip(repo):
    assert repo.cache_get("abc") is None
    repo.cache_put(
        {
            "key": "abc",
            "source_text": "a",
            "translation": "b",
            "source_lang": "ja",
            "target_lang": "es",
            "provider": "mock",
            "model": "mock-0.1",
        }
    )
    assert repo.cache_get("abc")["translation"] == "b"


def test_future_endpoints_501(client):
    for prefix in ("images", "ocr"):
        assert client.get(f"/{prefix}").status_code == 501


def test_no_local_job_tables(repo):
    """Confirmación explícita: Kimo no tiene queue/workers/stale propios."""
    tables = {r[0] for r in repo._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "jobs" not in tables and "workers" not in tables
    assert not hasattr(repo, "claim_job") and not hasattr(repo, "heartbeat")
    with pytest.raises(ImportError):
        import kimotranslate.jobs.manager  # noqa: F401
