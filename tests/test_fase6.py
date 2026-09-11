"""Tests Fase 6: imágenes discover -> OCR -> translate -> localize -> export."""

from __future__ import annotations

import os

import pytest

from kimotranslate.engines.magi_engine import FakeBackend, MagiTranslationEngine
from kimotranslate.images import detector as img_detector
from kimotranslate.images import regions as regions_mod
from kimotranslate.images.cache import image_key, translations_blob
from kimotranslate.images.inpaint import SimpleInpainter
from kimotranslate.images.mask import make_mask
from kimotranslate.images.ocr.mock import MockOcrEngine
from kimotranslate.images.renderer import (
    default_font_path,
    missing_glyphs,
    render_region,
)
from kimotranslate.worker.agent import KimoWorker
from tests.image_factory import make_game_images, make_image

FONT = default_font_path()


@pytest.fixture()
def vngame(tmp_path):
    return make_game_images(str(tmp_path))


@pytest.fixture(autouse=True)
def _drain(hub_client):
    while True:
        job = hub_client.claim("kimo-drain", types="translation")
        if job is None:
            break
        hub_client.result(job["id"], False, error="drained by test setup")


def _register_game(client, path, gid):
    r = client.post("/games", json={"source_path": path, "game_id": gid, "name": gid})
    assert r.status_code == 201, r.text
    return gid


# --- discovery ---


def test_discover_heuristics(vngame):
    gdir, _ = vngame
    assets = img_detector.discover(gdir)
    by_rel = {a["relpath"]: a for a in assets}
    assert "cg/dialogue1.png" in by_rel and by_rel["cg/dialogue1.png"]["likely_text"]
    assert "readme.txt" not in by_rel
    assert by_rel["icon.ico.png"]["likely_text"] is False
    assert by_rel["icon.ico.png"]["skip_reason"] == "too-small"
    assert by_rel["bg/scene01.png"]["skip_reason"] == "background-dir"
    assert by_rel["thumb/cover_small.png"]["skip_reason"] == "icon-dir"
    assert by_rel["cg/dialogue1.png"]["width"] == 320
    assert by_rel["cg/dialogue1.png"]["original_hash"]


def test_discover_ids_deterministic(client, vngame):
    gdir, _ = vngame
    gid = _register_game(client, gdir, "vg1")
    r1 = client.post(f"/games/{gid}/images/discover").json()
    r2 = client.post(f"/games/{gid}/images/discover").json()
    assert r1["images_kept"] == r2["images_kept"] == 6
    ids1 = [a["id"] for a in client.get(f"/games/{gid}/images").json()]
    assert len(set(ids1)) == 6 and all(i.startswith("img:vg1:") for i in ids1)


# --- OCR ---


def test_ocr_mock_ingest(client, vngame):
    gdir, mapping = vngame
    gid = _register_game(client, gdir, "vg1")
    client.post(f"/games/{gid}/images/discover")
    asset = [
        a for a in client.get(f"/games/{gid}/images").json() if a["relpath"] == "cg/dialogue1.png"
    ][0]
    engine = MockOcrEngine(mapping)
    result = engine.detect_text(os.path.join(gdir, "cg/dialogue1.png"))
    assert [r.text for r in result.regions] == ["こんにちは", "お元気ですか"]
    body = {
        "regions": [
            {
                "x": r.x,
                "y": r.y,
                "w": r.w,
                "h": r.h,
                "text": r.text,
                "confidence": r.confidence,
                "orientation": r.orientation,
            }
            for r in result.regions
        ],
        "engine": "mock",
        "version": "0.1",
        "ocr_ms": 1.0,
    }
    out = client.post(f"/games/{gid}/images/{asset['id']}/ocr-result", json=body).json()
    assert out["regions"] == 2
    det = client.get(f"/games/{gid}/images/{asset['id']}").json()
    assert det["ocr_status"] == "OCR_DONE"
    assert [r["reading_order"] for r in det["regions"]] == [0, 1]
    assert det["regions"][0]["source_text"] == "こんにちは"


def test_reading_order_and_grouping():
    rows = [
        {"image_id": "i", "x": 200, "y": 10, "w": 50, "h": 20, "orientation": "horizontal"},
        {"image_id": "i", "x": 10, "y": 12, "w": 50, "h": 20, "orientation": "horizontal"},
        {"image_id": "i", "x": 300, "y": 10, "w": 20, "h": 100, "orientation": "vertical"},
        {"image_id": "i", "x": 250, "y": 15, "w": 20, "h": 100, "orientation": "vertical"},
    ]
    regions_mod.reading_order(rows)
    by_x = {r["x"]: r["reading_order"] for r in rows}
    assert by_x[10] < by_x[200]  # horizontal: izq -> der
    assert by_x[300] < by_x[250]  # vertical: der -> izq
    close = [
        {
            "image_id": "i",
            "x": 10,
            "y": 10,
            "w": 100,
            "h": 20,
            "orientation": "horizontal",
            "reading_order": 0,
        },
        {
            "image_id": "i",
            "x": 12,
            "y": 34,
            "w": 100,
            "h": 20,
            "orientation": "horizontal",
            "reading_order": 1,
        },
        {
            "image_id": "i",
            "x": 12,
            "y": 200,
            "w": 100,
            "h": 20,
            "orientation": "horizontal",
            "reading_order": 2,
        },
    ]
    regions_mod.group_regions(close)
    assert close[0]["group_id"] and close[0]["group_id"] == close[1]["group_id"]
    assert close[2]["group_id"] == ""


# --- mask / inpaint / renderer ---


def test_mask_rect_and_polygon(tmp_path):
    from PIL import Image

    p = make_image(str(tmp_path / "m.png"), (100, 60), [(10, 10, 30, 20)])
    im = Image.open(p)
    mask = make_mask(
        im.width, im.height, [{"x": 10, "y": 10, "w": 30, "h": 20, "translatable": True}], padding=2
    )
    px = mask.load()
    assert px[15, 15] == 255 and px[0, 0] == 0 and px[9, 9] == 255 and px[43, 33] == 0
    poly = make_mask(
        100,
        60,
        [
            {
                "x": 0,
                "y": 0,
                "w": 0,
                "h": 0,
                "polygon": [[50, 50], [70, 50], [60, 30]],
                "translatable": True,
            }
        ],
    )
    assert poly.load()[60, 45] == 255 and poly.load()[10, 10] == 0


def test_inpaint_fills_and_keeps_size(tmp_path):
    import numpy as np
    from PIL import Image

    p = make_image(str(tmp_path / "m.png"), (100, 60), [(10, 10, 30, 20)])
    im = Image.open(p).convert("RGB")
    mask = make_mask(100, 60, [{"x": 10, "y": 10, "w": 30, "h": 20, "translatable": True}])
    out = SimpleInpainter().inpaint(im, mask)
    assert out.size == (100, 60)
    arr = np.asarray(out)
    assert (arr[15:25, 15:35] > 200).all()  # negro eliminado
    assert (arr[0:5, 0:5] > 200).all()  # fondo intacto


def test_renderer_spanish_and_fit(tmp_path):
    from PIL import Image

    bg = Image.new("RGB", (300, 60), (0, 0, 0))
    region = {"x": 10, "y": 10, "w": 280, "h": 40}
    assert missing_glyphs("áéíóú ü ñ ¿¡", FONT) == []  # español obligatorio
    assert missing_glyphs("￿", FONT)  # U+FFFF sin glyph -> detectado
    img, fit, missing = render_region(bg, region, "Buenos días, ¿cómo estás?")
    assert fit == "FIT" and not missing
    import numpy as np

    assert (np.asarray(img)[15:45, 15:275].sum(axis=2) > 0).any()  # hay píxeles
    _, fit2, _ = render_region(
        bg, region, "Una frase extremadamente larga que no cabe ni encogiendo " * 10
    )
    assert fit2 == "OVERFLOW"
    tiny = {"x": 0, "y": 0, "w": 60, "h": 40}
    _, fit3, _ = render_region(bg, tiny, "Frase moderadamente larga aquí")
    assert fit3 == "SHRUNK"
    img4, fit4, miss4 = render_region(bg, region, "Hola ￿")
    assert fit4 == "FAILED" and miss4


def test_renderer_vertical(tmp_path):
    from PIL import Image

    bg = Image.new("RGB", (60, 300), (0, 0, 0))
    img, fit, _ = render_region(
        bg, {"x": 10, "y": 10, "w": 40, "h": 280, "orientation": "vertical"}, "ABC"
    )
    assert fit in ("FIT", "SHRUNK")
    # japonés vertical con fuente latina -> FAILED honesto (worker: fuente CJK vía env)
    _, fit_jp, miss_jp = render_region(
        bg, {"x": 10, "y": 10, "w": 40, "h": 280, "orientation": "vertical"}, "たて"
    )
    assert fit_jp == "FAILED" and miss_jp


# --- cache ---


def test_image_cache_key():
    k1 = image_key("h", "mock", "0.1", "", translations_blob([("r0", "Hola")]), "rv", "iv")
    assert k1 == image_key("h", "mock", "0.1", "", translations_blob([("r0", "Hola")]), "rv", "iv")
    assert k1 != image_key("h", "mock", "0.1", "", translations_blob([("r0", "Adios")]), "rv", "iv")
    assert k1 != image_key("h", "mock", "0.2", "", translations_blob([("r0", "Hola")]), "rv", "iv")


# --- pipeline completo ---


class _StubKimo:
    def __init__(self, client, mem):
        self._c = client
        self._mem = mem

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
        params = {}
        if project_id:
            params["project_id"] = project_id
        if game_id:
            params["game_id"] = game_id
        return self._c.get("/terminology", params=params).json()

    def get_game(self, game_id):
        return self._c.get(f"/games/{game_id}").json()

    def image_source(self, image_id):
        for g in self._c.get("/games").json():
            for a in self._c.get(f"/games/{g['game_id']}/images").json():
                if a["id"] == image_id:
                    return a
        raise KeyError(image_id)

    def bulk_texts(self, game_id, texts, fileinfo):
        from kimotranslate.worker.agent import text_to_json

        return self._c.post(
            f"/games/{game_id}/texts/bulk",
            json={"texts": [text_to_json(t) for t in texts], "fileinfo": fileinfo},
        ).json()

    def export_report(self, game_id, manifest):
        return self._c.post(f"/games/{game_id}/export-report", json=manifest).json()

    def push_game_images(self, game_id, assets):
        return self._c.post(f"/games/{game_id}/images/bulk", json={"assets": assets}).json()

    def push_ocr(self, game_id, image_id, rows, engine, version, ocr_ms):
        return self._c.post(
            f"/games/{game_id}/images/{image_id}/ocr-result",
            json={
                "regions": [
                    {
                        "x": r["x"],
                        "y": r["y"],
                        "w": r["w"],
                        "h": r["h"],
                        "text": r["source_text"],
                        "confidence": r.get("confidence"),
                        "orientation": r.get("orientation", "horizontal"),
                    }
                    for r in rows
                ],
                "engine": engine,
                "version": version,
                "ocr_ms": ocr_ms,
            },
        ).json()

    def localize_bundle(self, game_id, image_id):
        bundle = self._c.get(f"/games/{game_id}/images/{image_id}/bundle").json()
        import base64

        bundle["original_b64"] = base64.b64encode(
            open(os.path.join(self._root, bundle["asset"]["relpath"]), "rb").read()
        ).decode()
        return bundle

    def push_artifacts(
        self,
        game_id,
        image_id,
        localized_b64,
        mask_b64,
        report,
        renderer_version,
        inpaint_version,
        original_b64="",
    ):
        return self._c.post(
            f"/games/{game_id}/images/{image_id}/artifacts",
            json={
                "localized_b64": localized_b64,
                "mask_b64": mask_b64,
                "report": report,
                "renderer_version": renderer_version,
                "inpaint_version": inpaint_version,
                "original_b64": original_b64,
            },
        ).json()


def _drain(hub_client, kimo_api, engine=None):
    worker = KimoWorker(
        hub_client,
        "gw",
        engine
        or MagiTranslationEngine(
            backend=FakeBackend(text='{"translation": "T", "confidence": 0.9}')
        ),
        kimo_api=kimo_api,
    )
    for _ in range(100):
        if worker.run_once() is None:
            break
    return worker


def test_full_image_flow(client, hub_client, vngame, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory

    gdir, mapping = vngame
    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    stub = _StubKimo(client, mem)
    stub._root = gdir
    gid = _register_game(client, gdir, "vgame")
    client.post(f"/games/{gid}/images/discover")
    assets = client.get(f"/games/{gid}/images").json()
    assert len(assets) == 6
    target = next(a for a in assets if a["relpath"] == "cg/dialogue1.png")
    # OCR vía worker Hub con mock
    job = client.post(f"/games/{gid}/images/{target['id']}/ocr", json={"engine": "mock"}).json()
    assert job["method"] == "custom"
    worker = KimoWorker(
        hub_client,
        "gw",
        MagiTranslationEngine(backend=FakeBackend()),
        kimo_api=stub,
        ocr_engine=MockOcrEngine(mapping),
    )
    done = worker.run_once()
    assert done["status"] == "COMPLETED"
    det = client.get(f"/games/{gid}/images/{target['id']}").json()
    assert len(det["regions"]) == 2
    # translate vía pipeline existente (jobs TRANSLATE_TEXT del Hub)
    out = client.post(f"/games/{gid}/images/{target['id']}/translate", json={}).json()
    assert out["queued"] == 2
    _drain(hub_client, stub)
    assert client.post(f"/games/{gid}/images/{target['id']}/sync").json()["synced"] == 2
    det = client.get(f"/games/{gid}/images/{target['id']}").json()
    assert all(r["status"] == "TRANSLATED" for r in det["regions"])
    # corrección -> VALIDATED -> TM + ejemplo (content_type image_text)
    rid = det["regions"][0]["id"]
    c = client.post(
        "/corrections",
        json={
            "source_text": "こんにちは",
            "machine_translation": "T",
            "corrected_translation": "Hola",
            "source_app": "kimotranslate",
            "content_type": "image_text",
            "domain": "game_translation",
            "project_id": "vgame",
            "game_id": "vgame",
            "image_region_id": rid,
        },
    ).json()
    client.patch(f"/corrections/{c['id']}", json={"validated": True})
    assert (
        client.get(f"/games/{gid}/images/{target['id']}").json()["regions"][0]["status"]
        == "VALIDATED"
    )
    hits = client.get(
        "/memory/search",
        params={
            "query": "こんにちは",
            "domain": "game_translation",
            "content_type": "image_text",
            "project_id": "vgame",
        },
    ).json()
    assert hits[0]["translation"] == "Hola"
    ex = client.get("/examples", params={"content_type": "image_text"}).json()
    assert any(e["source_text"] == "こんにちは" for e in ex)
    # localize vía worker -> artefactos en servidor
    client.post(f"/games/{gid}/images/{target['id']}/localize", json={}).json()
    done2 = worker.run_once()
    assert done2["status"] == "COMPLETED"
    det = client.get(f"/games/{gid}/images/{target['id']}").json()
    assert det["localization_status"] == "LOCALIZED"
    # localize local (mismo código, misma máquina): devuelve la ruta de artefactos
    local = client.post(f"/games/{gid}/images/{target['id']}/localize", json={"local": True}).json()
    assert local["status"] == "LOCALIZED"
    base = local["artifacts"]
    for name in (
        "original.png",
        "ocr.json",
        "translation.json",
        "mask.png",
        "localized.png",
        "manifest.json",
    ):
        assert os.path.exists(os.path.join(base, name)), name
    from PIL import Image

    with Image.open(os.path.join(base, "localized.png")) as loc:
        assert loc.size == (320, 120)


def test_batch_endpoints(client, hub_client, vngame):
    gdir, _ = vngame
    gid = _register_game(client, gdir, "vgame")
    client.post(f"/games/{gid}/images/discover")
    jobs = client.post(f"/games/{gid}/images/ocr", json={}).json()["jobs"]
    assert len(jobs) == 3  # likely_text: dialogue1, dialogue_v, menu
    out = client.post(f"/games/{gid}/images/translate", json={}).json()
    assert out["images"] == 0  # sin OCR aún
    loc = client.post(f"/games/{gid}/images/localize", json={"local": True}).json()
    assert loc["localized"] == []


def test_game_isolation_images(client, vngame):
    gdir, _ = vngame
    _register_game(client, gdir, "vgA")
    _register_game(client, gdir, "vgB")
    client.post("/games/vgA/images/discover")
    client.post("/games/vgB/images/discover")
    a = client.get("/games/vgA/images").json()
    b = client.get("/games/vgB/images").json()
    assert a and b and a[0]["id"] != b[0]["id"]
    assert a[0]["game_id"] == "vgA" and b[0]["game_id"] == "vgB"


def test_export_integration(client, vngame, tmp_path):
    gdir, _ = vngame
    gid = _register_game(client, gdir, "vgame")
    client.post(f"/games/{gid}/images/discover")
    asset = next(
        a for a in client.get(f"/games/{gid}/images").json() if a["relpath"] == "ui/menu.png"
    )
    from kimotranslate.images import exporter as img_exporter

    with open(os.path.join(gdir, "ui/menu.png"), "rb") as f:
        import hashlib

        h = hashlib.sha256(f.read()).hexdigest()[:16]
    assert asset["original_hash"] == h
    out = str(tmp_path / "imgout")
    res = img_exporter.export_images(
        gdir,
        out,
        [
            {
                "relpath": "ui/menu.png",
                "localized_path": os.path.join(gdir, "ui/menu.png"),
                "original_path": os.path.join(gdir, "ui/menu.png"),
                "regions": [{"id": "x", "source": "a", "final": "b", "translatable": True}],
            }
        ],
    )
    assert res["exported_count"] == 1 and res["failed_count"] == 0
    assert os.path.exists(os.path.join(out, "localized", "ui/menu.png"))
    assert os.path.exists(os.path.join(out, "backup", "ui/menu.png"))


def test_tradujap_adapter_missing(tmp_path):
    from kimotranslate.images.ocr.tradujap_adapter import TradujapOcrEngine
    from tests.image_factory import make_image

    p = make_image(str(tmp_path / "t.png"), (100, 40), [(5, 5, 40, 20)])
    try:
        eng = TradujapOcrEngine(detector="nope", recognizer="nope")
        eng.detect_text(p)
        raise AssertionError("debería fallar sin modelos")
    except Exception as e:
        assert "tradujap" in str(e).lower() or "disponible" in str(e) or "desconocido" in str(e)
