"""Tests Fase 7: editor visual (servicio testeable vía HTTP; Tkinter no)."""

from __future__ import annotations

import os

import pytest

from tests.image_factory import make_game_images


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


def _setup(client, gdir, gid="ed"):
    assert client.post("/games", json={"source_path": gdir, "game_id": gid}).status_code == 201
    client.post(f"/games/{gid}/images/discover")
    asset = next(
        a for a in client.get(f"/games/{gid}/images").json() if a["relpath"] == "cg/dialogue1.png"
    )
    iid = asset["id"]
    client.post(
        f"/games/{gid}/images/{iid}/ocr-result",
        json={
            "regions": [
                {
                    "x": 20,
                    "y": 20,
                    "w": 280,
                    "h": 30,
                    "text": "こんにちは",
                    "confidence": 0.9,
                    "orientation": "horizontal",
                },
                {
                    "x": 20,
                    "y": 60,
                    "w": 200,
                    "h": 30,
                    "text": "さようなら",
                    "confidence": 0.9,
                    "orientation": "horizontal",
                },
            ],
            "engine": "mock",
            "version": "0.1",
            "ocr_ms": 1.0,
        },
    )
    regions = client.get(f"/games/{gid}/images/{iid}").json()["regions"]
    client.post(f"/games/{gid}/images/{iid}/translate", json={}).json()
    return gid, iid, regions


def _rid(client, gid, iid, n=0):
    return client.get(f"/games/{gid}/images/{iid}").json()["regions"][n]["id"]


# --- region editing ---


def test_move_resize_create_delete(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    rid = regions[0]["id"]
    base = f"/games/{gid}/images/{iid}/regions/{rid}"
    moved = client.patch(base, json={"x": 30, "y": 25}).json()
    assert (moved["x"], moved["y"]) == (30, 25)
    resized = client.patch(base, json={"x": 30, "y": 25, "w": 100, "h": 40}).json()
    assert (resized["w"], resized["h"]) == (100, 40)
    assert client.patch(base, json={"x": 0, "y": 0, "w": 0, "h": 5}).status_code == 400
    created = client.post(
        f"/games/{gid}/images/{iid}/regions", json={"x": 5, "y": 5, "w": 50, "h": 20}
    ).json()
    assert created["id"].endswith(":manual0") and created["status"] == "REVIEW_REQUIRED"
    assert (
        client.post(
            f"/games/{gid}/images/{iid}/regions", json={"x": 0, "y": 0, "w": 1, "h": 1}
        ).status_code
        == 400
    )
    assert client.delete(base).json()["status"] == "DELETED"
    # eliminada no sale en localize: preview la ignora
    pv = client.post(f"/games/{gid}/images/{iid}/preview", json={}).json()
    assert all(r["region_id"] != rid for r in pv["report"] if r.get("region_id"))


def test_undo_redo_move(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    rid = regions[0]["id"]
    x0 = regions[0]["x"]
    client.patch(f"/games/{gid}/images/{iid}/regions/{rid}", json={"x": 99, "y": 99})
    assert (
        client.post(f"/games/{gid}/images/{iid}/history/undo", json={}).json()["undone"] == "move"
    )
    assert _rid_row(client, gid, iid, rid)["x"] == x0
    assert (
        client.post(f"/games/{gid}/images/{iid}/history/redo", json={}).json()["redone"] == "move"
    )
    assert _rid_row(client, gid, iid, rid)["x"] == 99
    assert (
        client.post(f"/games/{gid}/images/{iid}/history/undo", json={}).json()["undone"] == "move"
    )
    log = client.get(f"/games/{gid}/images/{iid}/editor").json()["history"]
    assert any(o["op_type"] == "move" for o in log)


def _rid_row(client, gid, iid, rid):
    return next(
        r for r in client.get(f"/games/{gid}/images/{iid}").json()["regions"] if r["id"] == rid
    )


# --- OCR / traducción ---


def test_edit_ocr_resets_translation(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    rid = regions[0]["id"]
    out = client.patch(
        f"/games/{gid}/images/{iid}/regions/{rid}", json={"source_text": "おはよう"}
    ).json()
    assert out["status"] == "TRANSLATION_PENDING" and out["machine_translation"] == ""


def test_edit_translation_creates_correction(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    rid = regions[0]["id"]
    out = client.patch(
        f"/games/{gid}/images/{iid}/regions/{rid}", json={"translation": "Hola {PLAYER}"}
    ).json()
    assert out["corrected_translation"] == "Hola {PLAYER}"
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["warnings"] == []  # sin tokens en origen: sin avisos
    out2 = client.patch(
        f"/games/{gid}/images/{iid}/regions/{rid}", json={"translation": "Hola"}
    ).json()
    assert out2["warnings"] == []
    corr = [c for c in client.get("/corrections").json() if c.get("image_region_id") == rid]
    assert any(c["corrected_translation"] == "Hola {PLAYER}" for c in corr)


def test_token_warning_on_edit(client, vngame, tmp_path):
    from tests.image_factory import make_image as _mk

    p = _mk(str(tmp_path / "t.png"), (200, 60), [(10, 10, 150, 30)])
    gdir = str(tmp_path / "g2")
    os.makedirs(os.path.join(gdir, "cg"), exist_ok=True)
    import shutil

    shutil.copy(p, os.path.join(gdir, "cg", "a.png"))
    gid = "tok"
    assert client.post("/games", json={"source_path": gdir, "game_id": gid}).status_code == 201
    client.post(f"/games/{gid}/images/discover")
    iid = client.get(f"/games/{gid}/images").json()[0]["id"]
    client.post(
        f"/games/{gid}/images/{iid}/ocr-result",
        json={
            "regions": [
                {
                    "x": 10,
                    "y": 10,
                    "w": 150,
                    "h": 30,
                    "text": "行こう{PLAYER}",
                    "confidence": 0.9,
                    "orientation": "horizontal",
                }
            ],
            "engine": "mock",
            "version": "0.1",
            "ocr_ms": 1.0,
        },
    )
    rid = client.get(f"/games/{gid}/images/{iid}").json()["regions"][0]["id"]
    out = client.patch(
        f"/games/{gid}/images/{iid}/regions/{rid}", json={"translation": "Vamos"}
    ).json()
    assert any("TOKEN_MISMATCH" in w and "{PLAYER}" in w for w in out["warnings"])
    assert (
        client.post(f"/games/{gid}/images/{iid}/regions/{rid}/validate", json={}).status_code == 400
    )  # tokens incompatibles: no valida


# --- validación ---


def test_validate_region_and_image(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    for r in regions:
        client.patch(
            f"/games/{gid}/images/{iid}/regions/{r['id']}",
            json={"translation": "Texto {}".format(r["region_index"])},
        )
    assert client.post(f"/games/{gid}/images/{iid}/validate", json={}).status_code == 400
    for r in regions:
        out = client.post(
            f"/games/{gid}/images/{iid}/regions/{r['id']}/validate", json={"reviewer": "tester"}
        ).json()
        assert out["status"] == "VALIDATED" and out["correction_id"]
    done = client.post(f"/games/{gid}/images/{iid}/validate", json={}).json()
    assert done["status"] == "VALIDATED" and done["regions"] == 2
    hits = client.get(
        "/memory/search",
        params={"query": "こんにちは", "domain": "game_translation", "content_type": "image_text"},
    ).json()
    assert hits  # promovida a TM al validar


def test_validate_empty_region_fails(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    rid = regions[0]["id"]
    assert (
        client.post(f"/games/{gid}/images/{iid}/regions/{rid}/validate", json={}).status_code == 400
    )


# --- máscara ---


def test_mask_strokes_and_rasterize(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    out = client.post(
        f"/games/{gid}/images/{iid}/mask", json={"tool": "add", "x": 5, "y": 5, "radius": 6}
    ).json()
    assert out["mask_modified"] is True
    out = client.post(
        f"/games/{gid}/images/{iid}/mask", json={"tool": "erase", "x": 5, "y": 5, "radius": 2}
    ).json()
    state = client.get(f"/games/{gid}/images/{iid}/editor").json()
    assert state["asset"]["manifest"]["mask_source"] == "manual"
    assert len(state["asset"]["manifest"]["mask_strokes"]) == 2
    assert state["dirty"]["mask_dirty"] is True and state["dirty"]["inpaint_dirty"] is True
    assert (
        client.post(
            f"/games/{gid}/images/{iid}/mask", json={"tool": "laser", "x": 0, "y": 0, "radius": 1}
        ).status_code
        == 400
    )
    client.post(f"/games/{gid}/images/{iid}/history/undo", json={})
    state = client.get(f"/games/{gid}/images/{iid}/editor").json()
    assert len(state["asset"]["manifest"]["mask_strokes"]) == 1


# --- preview / dirty / versiones ---


def test_preview_and_dirty_flags(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    for r in regions:
        client.patch(f"/games/{gid}/images/{iid}/regions/{r['id']}", json={"translation": "Hola"})
    pv = client.post(f"/games/{gid}/images/{iid}/preview", json={}).json()
    assert pv["preview_b64"] and all(
        x.get("fit") in ("FIT", "SHRUNK") for x in pv["report"] if x.get("region_id")
    )
    pv_one = client.post(
        f"/games/{gid}/images/{iid}/preview", json={"region_ids": [regions[0]["id"]]}
    ).json()
    assert len([x for x in pv_one["report"] if x.get("region_id")]) == 1
    import base64

    from PIL import Image

    im = Image.open(__import__("io").BytesIO(base64.b64decode(pv["preview_b64"])))
    assert im.size == (320, 120)


def test_versioned_rollback(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    for r in regions:
        client.patch(f"/games/{gid}/images/{iid}/regions/{r['id']}", json={"translation": "Uno"})
    client.post(f"/games/{gid}/images/{iid}/localize", json={"local": True})
    for r in regions:
        client.patch(f"/games/{gid}/images/{iid}/regions/{r['id']}", json={"translation": "Dos"})
    client.post(f"/games/{gid}/images/{iid}/localize", json={"local": True})

    base = client.post(f"/games/{gid}/images/{iid}/localize", json={"local": True}).json()[
        "artifacts"
    ]
    assert os.path.exists(os.path.join(base, "localized_prev.png"))
    assert client.post(f"/games/{gid}/images/{iid}/reset", json={}).json()["restored"]
    # reset de región: vuelve al texto anterior registrado
    rid = regions[0]["id"]
    assert (
        client.post(f"/games/{gid}/images/{iid}/reset", json={"region_id": rid}).json()["id"] == rid
    )


def test_editor_state_versions(client, vngame):
    gdir, _ = vngame
    gid, iid, regions = _setup(client, gdir)
    state = client.get(f"/games/{gid}/images/{iid}/editor").json()
    assert state["editor_version"].startswith("img-editor@")
    assert set(state["dirty"]) >= {
        "translation_dirty",
        "mask_dirty",
        "inpaint_dirty",
        "render_dirty",
        "ocr_dirty",
    }
    assert state["asset"]["id"] == iid and len(state["regions"]) == 2
