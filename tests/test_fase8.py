"""Tests Fase 8: RC — idempotencia, fallos controlados, integridad, release."""

from __future__ import annotations

import os

import pytest

from kimotranslate.engines.magi_engine import FakeBackend, MagiTranslationEngine
from kimotranslate.images.ocr.mock import MockOcrEngine
from kimotranslate.release import KIMO_VERSION, build_manifest
from kimotranslate.worker.agent import KimoWorker
from tests.game_factory import build_ypf, build_ystb, make_game
from tests.image_factory import make_game_images


@pytest.fixture(autouse=True)
def _drain(hub_client):
    while True:
        job = hub_client.claim("kimo-drain", types="translation")
        if job is None:
            break
        hub_client.result(job["id"], False, error="drained by test setup")


def _register(client, path, gid):
    r = client.post("/games", json={"source_path": path, "game_id": gid, "name": gid})
    assert r.status_code == 201, r.text


# --- retry/resume sin duplicar ---


def _own_jobs(hub_client, before: set) -> list:
    return [j for j in hub_client.list_translation_jobs() if j["id"] not in before]


def test_sync_idempotent_no_duplicates(client, hub_client, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory
    from tests.test_fase5 import _StubKimo

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    g = make_game(str(tmp_path), "rc1", {"s.ybn": [("msg", "テスト")]})
    _register(client, g, "rc1")
    client.post("/games/rc1/extract", params={"local": True})
    before = {j["id"] for j in hub_client.list_translation_jobs()}
    client.post("/games/rc1/translate", json={})
    worker = KimoWorker(
        hub_client,
        "gw",
        MagiTranslationEngine(backend=FakeBackend(text='{"translation": "T", "confidence": 1.0}')),
        kimo_api=_StubKimo(client, mem),
    )
    while worker.run_once() is not None:
        pass
    first = client.post("/games/rc1/sync").json()
    assert first["synced"] == 1
    second = client.post("/games/rc1/sync").json()
    assert second == {"synced": 0, "failed": 0}  # idempotente
    assert len(client.get("/games/rc1/texts").json()) == 1  # sin duplicados
    assert len(_own_jobs(hub_client, before)) == 1  # un solo Hub job propio


def test_failed_job_resubmit_works(client, hub_client, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory
    from tests.test_fase5 import _StubKimo

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    g = make_game(str(tmp_path), "rc2", {"s.ybn": [("msg", "テスト")]})
    _register(client, g, "rc2")
    client.post("/games/rc2/extract", params={"local": True})
    before = {j["id"] for j in hub_client.list_translation_jobs()}
    client.post("/games/rc2/translate", json={})
    mine = _own_jobs(hub_client, before)
    assert len(mine) == 1
    hub_client.result(mine[0]["id"], False, error="worker died")
    assert client.post("/games/rc2/sync").json() == {"synced": 0, "failed": 1}
    out = client.post("/games/rc2/translate", json={}).json()  # retry = job nuevo
    assert out["queued"] == 1
    worker = KimoWorker(
        hub_client,
        "gw",
        MagiTranslationEngine(backend=FakeBackend(text='{"translation": "T", "confidence": 1.0}')),
        kimo_api=_StubKimo(client, mem),
    )
    while worker.run_once() is not None:
        pass
    assert client.post("/games/rc2/sync").json()["synced"] == 1


def test_ocr_failure_controlled(client, hub_client, tmp_path):
    gdir, _ = make_game_images(str(tmp_path))
    _register(client, gdir, "rc3")
    client.post("/games/rc3/images/discover")
    iid = client.get("/games/rc3/images").json()[0]["id"]

    class Boom(MockOcrEngine):
        def detect_text(self, image_path: str):
            raise RuntimeError("CUDA OOM simulado")

    job = client.post(f"/games/rc3/images/{iid}/ocr", json={"engine": "mock"}).json()
    assert job["method"] == "custom"
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory
    from kimotranslate.worker.agent import KimoWorker
    from tests.test_fase6 import _StubKimo

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    worker = KimoWorker(hub_client, "gw", kimo_api=_StubKimo(client, mem), ocr_engine=Boom())
    done = worker.run_once()
    assert done["status"] == "FAILED"
    assert "OOM" in (done.get("error") or "")
    asset = client.get(f"/games/rc3/images/{iid}").json()
    assert asset["ocr_status"] == "DISCOVERED"  # sin escritura parcial
    assert asset.get("regions", []) == []


def test_no_secrets_in_jobs_or_results(client, hub_client, tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "sk-FAKE-SECRET-123")
    r = client.post("/translations", json={"text": "テスト", "provider": "magi"}).json()
    assert "sk-FAKE" not in str(r)
    for j in hub_client.list_translation_jobs():
        assert "sk-FAKE" not in str(j)
    provs = client.get("/providers").json()
    assert "sk-FAKE" not in str(provs)


# --- integridad / release ---


def test_integrity_pass_and_fail(client, hub_client, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.engines.magi_engine import FakeBackend, MagiTranslationEngine
    from kimotranslate.knowledge.memory import TranslationMemory
    from kimotranslate.worker.agent import KimoWorker
    from tests.test_fase5 import _StubKimo

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    g = make_game(str(tmp_path), "rc4", {"s.ybn": [("msg", "テスト")]})
    _register(client, g, "rc4")
    client.post("/games/rc4/extract", params={"local": True})
    client.post("/games/rc4/translate", json={})
    worker = KimoWorker(
        hub_client,
        "gw",
        MagiTranslationEngine(backend=FakeBackend(text='{"translation": "T", "confidence": 1.0}')),
        kimo_api=_StubKimo(client, mem),
    )
    while worker.run_once() is not None:
        pass
    client.post("/games/rc4/sync")
    out = str(tmp_path / "out")
    client.post("/games/rc4/export", json={"output_path": out, "local": True})
    ok = client.post("/games/rc4/integrity", json={"output_path": out}).json()
    assert ok["status"] == "INTEGRITY_PASS" and ok["checked"] == 1
    os.remove(os.path.join(out, "backup", "ysbin", "s.ybn"))  # simula fallo
    bad = client.post("/games/rc4/integrity", json={"output_path": out}).json()
    assert bad["status"] == "INTEGRITY_FAIL"
    assert bad["issues"][0]["status"] == "NO_BACKUP"


def test_release_manifest(client):
    m = client.get("/release").json()
    assert m["version"] == KIMO_VERSION and m["created_at"]
    assert m["prompt_version"] and m["extractor_version"] and m["renderer_version"]
    assert build_manifest()["version"] == KIMO_VERSION


# --- fixtures formato real (edge) ---


def test_ystb_empty_and_garbage():
    from kimotranslate.games.yuris import ystb

    with pytest.raises(ystb.YstbError):
        ystb.parse(b"NOPE" * 20, 0x1234)
    # header cero válido estructuralmente: 0 instrucciones, sin error
    assert ystb.parse(b"YSTB" + b"\x00" * 28, 0x1234).insts == []


def test_ypf_multifile_and_garbage():
    from kimotranslate.games.yuris import ypf

    arc = build_ypf(
        {
            "ysbin/a.ybn": build_ystb([("msg", "あ")]),
            "ysbin/b.ybn": build_ystb([("msg", "い")]),
            "pac/data.bin": b"\x00" * 64,
        }
    )
    version, entries = ypf.parse_ypf(arc)
    assert sorted(e.name for e in entries) == ["pac/data.bin", "ysbin/a.ybn", "ysbin/b.ybn"]
    assert (
        ypf.extract_entry(arc, [e for e in entries if e.name.endswith("a.ybn")][0], version)[:4]
        == b"YSTB"
    )
    with pytest.raises(ypf.YpfError):
        ypf.parse_ypf(b"RAR!" + b"\x00" * 100)


def test_detector_ignores_non_ybn(tmp_path):
    from kimotranslate.games.engines import clockup

    d = str(tmp_path / "fake")
    os.makedirs(d)
    open(os.path.join(d, "game.exe"), "wb").write(b"MZ")
    open(os.path.join(d, "data.ypf"), "wb").write(b"not a ypfxxxxxxxxxxxx")
    det = clockup.detect(d)
    assert det.engine == "unknown"
