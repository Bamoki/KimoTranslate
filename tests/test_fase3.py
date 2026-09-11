"""Tests Fase 3: providers, terminología, TM. Sin Internet (MockTransport)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from kimotranslate.api.app import create_app
from kimotranslate.core.config import Settings
from kimotranslate.engines import PROVIDERS, UnknownProvider, get_engine, provider_status
from kimotranslate.engines.base import TranslationRequest
from kimotranslate.engines.deepl import DeepLTranslationEngine
from kimotranslate.engines.google import GoogleTranslationEngine
from kimotranslate.engines.http_base import (
    ProviderAuthError,
    ProviderClient,
    ProviderError,
    RetryPolicy,
)
from kimotranslate.engines.magi_engine import FakeBackend, MagiTranslationEngine
from kimotranslate.knowledge.interfaces import TranslationContext
from kimotranslate.knowledge.memory import TranslationMemory
from kimotranslate.worker.agent import KimoWorker

TEXT = "おはようございます"


@pytest.fixture()
def mem(tmp_path):
    from magi.memory.store import MemoryStore

    return TranslationMemory(store=MemoryStore(str(tmp_path / "mem.db")))


@pytest.fixture()
def app3(tmp_path, hub_client, mem):
    return TestClient(create_app(Settings(data_dir=str(tmp_path)), hub_client, mem))


def req(text=TEXT, provider="magi", **ctxkw):
    ctx = {
        "content_type": "vn_dialogue",
        "domain": "game_translation",
        "speaker": "character_01",
        **ctxkw,
    }
    return TranslationRequest(text, context=TranslationContext(**ctx)), provider


# --- providers ---


def test_registry_selection():
    assert get_engine("magi").name == "magi"
    assert get_engine("ollama").name == "ollama"
    assert get_engine("deepl").name == "deepl"
    assert get_engine("google").name == "google"
    assert set(PROVIDERS) == {"magi", "deepl", "google", "ollama"}
    with pytest.raises(UnknownProvider):
        get_engine("nope")


def test_submit_rejects_unknown_provider(client):
    r = client.post("/translations", json={"text": TEXT, "provider": "nope"})
    assert r.status_code == 400


def test_providers_endpoint_no_secrets(client, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "super-secret")
    for p in client.get("/providers").json():
        assert "super-secret" not in str(p)
    assert {p["provider"] for p in client.get("/providers").json()} == set(PROVIDERS)
    assert provider_status()


def _mock_client(payloads):
    calls = []

    def handler(request):
        calls.append(request)
        status, body = payloads[min(len(calls) - 1, len(payloads) - 1)]
        return httpx.Response(status, json=body)

    return ProviderClient(
        "http://x",
        RetryPolicy(max_retries=2, backoff_base_s=0),
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x"),
    ), calls


def test_deepl_translate():
    client, _ = _mock_client([(200, {"translations": [{"text": "Buenos días"}]})])
    res = DeepLTranslationEngine(api_key="k", client=client).translate(req()[0])
    assert (res.translation, res.provider) == ("Buenos días", "deepl")
    assert res.confidence is None  # DeepL no da confidence: opcional


def test_google_translate():
    client, _ = _mock_client([(200, {"data": {"translations": [{"translatedText": "Hi"}]}})])
    res = GoogleTranslationEngine(api_key="k", client=client).translate(req()[0])
    assert (res.translation, res.provider) == ("Hi", "google")


def test_retry_429_then_ok():
    client, calls = _mock_client([(429, {}), (200, {"translations": [{"text": "ok"}]})])
    res = DeepLTranslationEngine(api_key="k", client=client).translate(req()[0])
    assert res.translation == "ok" and len(calls) == 2


def test_4xx_fails_fast_no_retry():
    client, calls = _mock_client([(400, {"message": "bad"})])
    with pytest.raises(ProviderAuthError):
        DeepLTranslationEngine(api_key="k", client=client).translate(req()[0])
    assert len(calls) == 1


def test_missing_key_never_leaks():
    with pytest.raises(ProviderError, match="not configured"):
        DeepLTranslationEngine(api_key="").translate(req()[0])
    client, _ = _mock_client([(403, {"message": "forbidden"})])
    try:
        GoogleTranslationEngine(api_key="SECRETKEY", client=client).translate(req()[0])
        raise AssertionError("must fail")
    except ProviderAuthError as e:
        assert "SECRETKEY" not in str(e)
    from kimotranslate.engines.http_base import _clean

    assert _clean("https://x/?key=SECRETKEY&q=a") == "https://x/?key=<redacted>&q=a"


# --- terminología ---


def test_terminology_precedence(client):
    c = client
    c.post("/terminology", json={"term": "先生", "preferred": "profesor"})
    c.post("/terminology", json={"term": "先生", "preferred": "maestro", "project_id": "euphoria"})
    c.post(
        "/terminology",
        json={
            "term": "先生",
            "preferred": "Sensei",
            "project_id": "euphoria",
            "game_id": "euphoria",
        },
    )
    g = c.get("/terminology", params={"term": "先生"}).json()[0]
    assert g["preferred"] == "profesor" and g["scope"] == "global"
    p = c.get("/terminology", params={"term": "先生", "project_id": "euphoria"}).json()[0]
    assert p["preferred"] == "maestro" and p["scope"] == "project"
    gm = c.get(
        "/terminology", params={"term": "先生", "project_id": "euphoria", "game_id": "euphoria"}
    ).json()[0]
    assert gm["preferred"] == "Sensei" and gm["scope"] == "game"
    other = c.get("/terminology", params={"term": "先生", "project_id": "otro"}).json()[0]
    assert other["preferred"] == "profesor"  # lo específico no contamina


def test_terminology_priority_tiebreak(repo):
    repo.terms.upsert("先輩", "senpai", priority=1)
    repo.terms.upsert("先輩", "sempai", priority=5)
    assert repo.terms.lookup("先輩")["preferred"] == "sempai"


# --- TM ---


def test_tm_filters_domain_content_project(mem):
    mem.add(
        "おはようございます",
        "Buenos días",
        domain="game_translation",
        content_type="vn_dialogue",
        project_id="euphoria",
    )
    mem.add(
        "おはようございます",
        "Good morning manga",
        domain="manga",
        content_type="manga",
        project_id="berserk",
    )
    mem.add(
        "さようなら",
        "Adiós",
        domain="game_translation",
        content_type="vn_dialogue",
        validated=False,
    )  # auto: invisible
    hits = mem.search(
        "おはよう", domain="game_translation", content_type="vn_dialogue", project_id="euphoria"
    )
    assert hits and hits[0]["translation"] == "Buenos días"
    assert all(h["content_type"] == "vn_dialogue" for h in hits)
    assert mem.search("おはよう", domain="") == []  # sin domain no hay global
    assert mem.search("さようなら", domain="game_translation", content_type="vn_dialogue") == []
    assert (
        mem.find_reusable(
            query="おはよう",
            domain="game_translation",
            content_type="vn_dialogue",
            project_id="euphoria",
        )
        is None
    )  # bajo umbral
    assert (
        mem.find_reusable(
            query="おはようございます",
            domain="game_translation",
            content_type="vn_dialogue",
            project_id="euphoria",
        )["translation"]
        == "Buenos días"
    )


def test_tm_project_isolation(mem):
    mem.add("学園", "academia", domain="game_translation", content_type="game_ui")
    mem.add(
        "学園",
        "la Academia Euphoria",
        domain="game_translation",
        content_type="game_ui",
        project_id="euphoria",
    )
    assert (
        mem.search("学園", domain="game_translation", content_type="game_ui")[0]["translation"]
        == "academia"
    )
    assert (
        mem.search(
            "学園", domain="game_translation", content_type="game_ui", project_id="euphoria"
        )[0]["translation"]
        == "la Academia Euphoria"
    )


def test_memory_search_endpoint(app3, mem):
    mem.add("おはよう", "Buenas", domain="game_translation", content_type="vn_dialogue")
    r = app3.get(
        "/memory/search",
        params={"query": "おはよう", "domain": "game_translation", "content_type": "vn_dialogue"},
    )
    assert r.status_code == 200 and r.json()[0]["translation"] == "Buenas"
    assert app3.get("/memory/search", params={"query": "x"}).json() == []


def test_submit_uses_tm_without_job(app3, mem, hub_client):
    mem.add(
        "おはようございます",
        "Buenos días TM",
        domain="game_translation",
        content_type="vn_dialogue",
        project_id="euphoria",
    )
    r = app3.post(
        "/translations",
        json={"text": TEXT, "provider": "magi", "context": {"project_id": "euphoria"}},
    ).json()
    assert r["memory_hit"] is True and r["translation"] == "Buenos días TM"
    assert r["job_id"] is None  # sin proveedor, sin job


# --- pipeline por provider ---


class LocalKimo:
    def __init__(self, mem, terms):
        self._mem = mem
        self._terms = terms

    def memory_search(self, **p):
        return self._mem.search(
            p["query"],
            p["domain"],
            p.get("content_type", ""),
            p.get("project_id", ""),
            p.get("game_id", ""),
            p.get("limit", 3),
        )

    def terminology(self, project_id="", game_id=""):
        return self._terms


def _run(app3, hub_client, mem, terms, provider, engine, text=TEXT, **ctx):
    r = app3.post(
        "/translations",
        json={"text": text, "provider": provider, "context": {"project_id": "euphoria", **ctx}},
    ).json()
    assert r["job_id"], r
    worker = KimoWorker(hub_client, "w3", engine, kimo_api=LocalKimo(mem, terms))
    done = worker.run_once()
    assert done["status"] == "COMPLETED", done
    return app3.get(f"/jobs/{r['job_id']}").json()


def test_worker_selects_engine_by_provider(app3, hub_client, mem):
    seen = {}

    def factory(provider):
        seen["provider"] = provider
        return MagiTranslationEngine(
            backend=FakeBackend(text='{"translation": "T", "confidence": 0.9}'), provider=provider
        )

    r = app3.post("/translations", json={"text": TEXT, "provider": "deepl"}).json()
    worker = KimoWorker(hub_client, "w3", engine_factory=factory, kimo_api=LocalKimo(mem, []))
    worker.run_once()
    assert seen["provider"] == "deepl"
    got = app3.get(f"/jobs/{r['job_id']}").json()
    assert got["translation"] == "T" and got["provider"] == "deepl"


def test_terms_reach_magi_prompt(app3, hub_client, mem, repo):
    prompts = []

    class Spy(FakeBackend):
        def generate(self, model, prompt, **kw):
            prompts.append(prompt)
            self.text = '{"translation": "X", "confidence": 1.0}'
            return super().generate(model, prompt, **kw)

    terms = [{"term": "生徒会", "preferred": "consejo escolar"}]
    out = _run(
        app3,
        hub_client,
        mem,
        terms,
        "magi",
        MagiTranslationEngine(backend=Spy()),
        game_id="euphoria",
    )
    assert out["translation"] == "X"
    assert "生徒会 = consejo escolar" in prompts[0]  # contexto, no sustitución


def test_context_preserved_with_provider(app3, hub_client, mem):
    out = _run(
        app3,
        hub_client,
        mem,
        [],
        "google",
        MagiTranslationEngine(backend=FakeBackend(text='{"translation": "G", "confidence": 0.4}')),
        game_id="euphoria",
    )
    job = hub_client.get_job(out["job_id"])
    ctx = job["metrics"]["request"]["context"]
    assert (ctx["game_id"], ctx["provider"], ctx["domain"]) == (
        "euphoria",
        "google",
        "game_translation",
    )
