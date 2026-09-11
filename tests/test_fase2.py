"""Tests Fase 2: GUI -> Kimo -> Hub -> Worker -> MAGI -> cache. Sin Ollama."""

from __future__ import annotations

import httpx
import pytest

from kimotranslate.engines.base import TranslationRequest
from kimotranslate.engines.magi_engine import (
    FakeBackend,
    KimoTranslateAdapter,
    MagiTranslationEngine,
)
from kimotranslate.hub.client import HubClient
from kimotranslate.knowledge.interfaces import TranslationContext
from kimotranslate.worker.agent import KimoWorker, request_from_job

TEXT = "おはようございます"


@pytest.fixture(autouse=True)
def _drain(hub_client):
    """Cada test parte de cola vacía: los jobs son del Hub, no hay aislamiento por test."""
    while True:
        job = hub_client.claim("kimo-drain", types="translation")
        if job is None:
            break
        hub_client.result(job["id"], False, error="drained by test setup")


def submit(client, text=TEXT, **ctx):
    body = {
        "text": text,
        "context": {
            "content_type": "vn_dialogue",
            "domain": "game_translation",
            "speaker": "character_01",
            **ctx,
        },
    }
    return client.post("/translations", json=body)


def test_miss_creates_hub_job(client, hub_client):
    r = submit(client)
    assert r.status_code == 201
    body = r.json()
    assert body["cached"] is False and body["job_id"]
    job = hub_client.get_job(body["job_id"])
    assert job["domain"] == "translation" and job["method"] == "custom"
    assert job["status"] == "QUEUED"
    req = job["metrics"]["request"]
    assert req["text"] == TEXT and req["context"]["speaker"] == "character_01"
    assert req["context"]["content_type"] == "vn_dialogue"
    assert req["context"]["domain"] == "game_translation"


def test_training_worker_never_sees_custom_jobs(client, hub_client):
    submit(client)
    assert hub_client.claim("pc-worker", types="") is None  # sin filtro: invisible
    job = hub_client.claim("kimo-worker", types="translation")
    assert job is not None
    hub_client.result(job["id"], False, error="released by test")


def test_full_pipeline_worker_magi(client, hub_client):
    calls = []

    class Counting(FakeBackend):
        def generate(self, model, prompt, **kw):
            calls.append(prompt)
            self.text = '{"translation": "Buenos días", "confidence": 0.9}'
            return super().generate(model, prompt, **kw)

    job_id = submit(client).json()["job_id"]
    worker = KimoWorker(hub_client, "kimo-worker", MagiTranslationEngine(backend=Counting()))
    done = worker.run_once()
    assert done["status"] == "COMPLETED"
    assert done["metrics"]["translation"] == "Buenos días"
    assert done["metrics"]["provider"] == "magi"
    assert len(calls) == 1 and TEXT in calls[0]  # MAGI ejecutado una vez
    res = client.get(f"/jobs/{job_id}").json()
    assert res["translation"] == "Buenos días" and res["status"] == "COMPLETED"


def test_cache_hit_skips_magi(client, hub_client):
    backend = FakeBackend(text='{"translation": "Buenos días", "confidence": 0.9}')
    worker = KimoWorker(hub_client, "kimo-worker", MagiTranslationEngine(backend=backend))
    job_id = submit(client).json()["job_id"]
    worker.run_once()
    client.get(f"/jobs/{job_id}")  # lazy cache write
    calls = []

    class Counting(FakeBackend):
        def generate(self, model, prompt, **kw):
            calls.append(1)
            return super().generate(model, prompt, **kw)

    worker.engine = MagiTranslationEngine(backend=Counting())
    second = submit(client).json()
    assert second["cached"] is True and second["translation"] == "Buenos días"
    assert calls == [] and second["job_id"] is None  # MAGI no ejecutado, sin job


def test_context_preserved_end_to_end(client, hub_client):
    r = submit(client, game_id="game_007", project_id="p1").json()
    job = hub_client.get_job(r["job_id"])
    worker = KimoWorker(
        hub_client,
        "kimo-worker",
        MagiTranslationEngine(backend=FakeBackend(text='{"translation": "X", "confidence": 0.5}')),
    )
    worker.run_once()
    req_ctx = job["metrics"]["request"]["context"]
    assert req_ctx["game_id"] == "game_007" and req_ctx["project_id"] == "p1"


def test_hub_failure_then_resubmit(client, hub_client):
    job_id = submit(client).json()["job_id"]
    hub_client.result(job_id, False, error="worker died")
    assert client.get(f"/jobs/{job_id}").json()["status"] == "FAILED"
    # Sin lógica stale en Kimo: re-POST crea job nuevo y el pipeline funciona.
    second = submit(client).json()
    assert second["cached"] is False and second["job_id"] != job_id
    worker = KimoWorker(
        hub_client,
        "kimo-worker",
        MagiTranslationEngine(
            backend=FakeBackend(text='{"translation": "Buenos días", "confidence": 1.0}')
        ),
    )
    worker.run_once()
    assert client.get(f"/jobs/{second['job_id']}").json()["translation"] == "Buenos días"


def test_adapter_contract():
    adapter = KimoTranslateAdapter()
    ctx = adapter.build_context(
        "hola", context=TranslationContext(speaker="A"), glossary=["senpai"]
    )
    assert ctx["speaker"] == "A" and adapter.allowed_symbols(ctx) == {"senpai"}
    out = adapter.interpret_result({"translation": "t", "confidence": 0.7})
    assert out == {"translation": "t", "confidence": 0.7}


def test_request_from_hub_job():
    req, key = request_from_job(
        {
            "id": "j",
            "metrics": {
                "kimo_cache_key": "k",
                "request": {
                    "text": "あ",
                    "source_lang": "ja",
                    "target_lang": "es",
                    "context": {"speaker": "B"},
                },
            },
        }
    )
    assert isinstance(req, TranslationRequest) and req.context.speaker == "B"
    assert key == "k"


def test_hub_client_points_at_hub(hub_client):
    assert isinstance(hub_client, HubClient)
    jobs = hub_client.list_translation_jobs()
    assert isinstance(jobs, list)
    r = httpx.get("http://127.0.0.1:18081/api/training/jobs", timeout=5.0)
    assert r.status_code == 200
