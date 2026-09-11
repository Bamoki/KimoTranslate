"""Tests Fase 4: corrección -> validación -> TM/terminología/dataset."""

from __future__ import annotations

BASE = {
    "source_text": "先生",
    "machine_translation": "profesor",
    "source_app": "kimotranslate",
    "content_type": "vn_dialogue",
    "domain": "game_translation",
    "project_id": "euphoria",
    "game_id": "euphoria",
    "speaker": "character_01",
    "provider": "magi",
    "model": "qwen2.5:7b",
}


def _create(client, **kw):
    body = {**BASE, **kw}
    r = client.post("/corrections", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _validate(client, cid):
    r = client.patch(f"/corrections/{cid}", json={"validated": True})
    assert r.status_code == 200, r.text
    return r.json()


def test_lifecycle_statuses(client):
    c = _create(client, corrected_translation="Sensei")
    assert c["status"] == "corrected" and c["human_validated"] == 0
    g = _create(client, source_text="学校")
    assert g["status"] == "generated"
    assert g["quality_score"] < c["quality_score"]  # lo revisado pesa más
    v = _validate(client, c["id"])
    assert v["status"] == "validated" and v["human_validated"] == 1
    assert v["quality_score"] == 1.0
    r = client.patch(f"/corrections/{g['id']}", json={"rejected": True}).json()
    assert r["status"] == "rejected"
    assert client.get(f"/corrections/{c['id']}").json()["status"] == "validated"
    assert client.get("/corrections", params={"status": "validated"}).json()
    assert client.get("/corrections/unknown").status_code == 404


def test_generated_cannot_validate_directly(client):
    g = _create(client, source_text="学校")
    assert client.patch(f"/corrections/{g['id']}", json={"validated": True}).status_code == 409
    u = client.patch(f"/corrections/{g['id']}", json={"corrected_translation": "escuela"}).json()
    assert u["status"] == "corrected"
    assert _validate(client, g["id"])["status"] == "validated"


def test_validated_promotes_to_tm_unvalidated_does_not(client):
    c = _create(client, corrected_translation="Sensei")
    hits = client.get(
        "/memory/search",
        params={
            "query": "先生",
            "domain": "game_translation",
            "content_type": "vn_dialogue",
            "project_id": "euphoria",
        },
    ).json()
    assert all(h["translation"] != "Sensei" for h in hits)
    _validate(client, c["id"])
    hits = client.get(
        "/memory/search",
        params={
            "query": "先生",
            "domain": "game_translation",
            "content_type": "vn_dialogue",
            "project_id": "euphoria",
        },
    ).json()
    assert hits[0]["translation"] == "Sensei" and hits[0]["score"] == 1.0


def test_tm_dedup_and_conflicts(client):
    a = _create(client, corrected_translation="Sensei")
    _validate(client, a["id"])
    b = _create(client, corrected_translation="Sensei")
    _validate(client, b["id"])
    params = {
        "query": "先生",
        "domain": "game_translation",
        "content_type": "vn_dialogue",
        "project_id": "euphoria",
    }
    exact = [
        h
        for h in client.get("/memory/search", params=params).json()
        if h["source"] == "先生" and h["translation"] == "Sensei"
    ]
    assert len(exact) == 1  # sin duplicados
    d = _create(client, corrected_translation="El profesor")
    _validate(client, d["id"])
    all_hits = client.get("/memory/search", params=params).json()
    assert {h["translation"] for h in all_hits} >= {"Sensei", "El profesor"}  # conflicto: ambas
    assert all_hits[0]["translation"] == "Sensei"  # estable: primera validada gana empate


def test_manual_term_promotion_not_automatic(client):
    c = _create(client, corrected_translation="Sensei")
    _validate(client, c["id"])
    assert client.get("/terminology", params={"term": "先生"}).json() == []  # nada auto
    t = client.post(
        "/terminology",
        json={
            "term": "先生",
            "preferred": "Sensei",
            "project_id": "euphoria",
            "game_id": "euphoria",
        },
    ).json()
    assert t["scope"] == "game"
    hit = client.get(
        "/terminology", params={"term": "先生", "project_id": "euphoria", "game_id": "euphoria"}
    ).json()[0]
    assert hit["preferred"] == "Sensei"


def test_examples_and_dataset_isolation(client):
    c = _create(client, corrected_translation="Sensei")
    _validate(client, c["id"])
    m = _create(
        client,
        source_text="忍者",
        machine_translation="ninja",
        corrected_translation="shinobi",
        source_app="tradujap",
        content_type="manga",
        domain="manga",
        project_id="book_001",
        game_id="",
        speaker="",
    )
    _validate(client, m["id"])
    kimo = client.get("/examples", params={"source_app": "kimotranslate"}).json()
    assert kimo and all(e["source_app"] == "kimotranslate" for e in kimo)
    manga = client.get("/examples", params={"source_app": "tradujap"}).json()
    assert [e["source_text"] for e in manga] == ["忍者"]  # datasets separables
    ds = client.post(
        "/datasets/build",
        json={
            "dataset_id": "euphoria-game",
            "source_app": "kimotranslate",
            "domain": "game_translation",
        },
    ).json()
    assert ds["version"] == 1 and ds["example_count"] >= 1
    assert all("忍者" not in line for line in open(ds["path"], encoding="utf-8"))
    ds2 = client.post(
        "/datasets/build",
        json={
            "dataset_id": "euphoria-game",
            "source_app": "kimotranslate",
            "domain": "game_translation",
        },
    ).json()
    assert ds2["version"] == 2 and ds2["sha256"] == ds["sha256"]  # versionado
    row = [line for line in open(ds["path"], encoding="utf-8") if "先生" in line][0]
    entry = __import__("json").loads(row)
    assert entry["target"] == "Sensei" and entry["human_validated"] is True
    assert entry["source_app"] == "kimotranslate" and entry["project_id"] == "euphoria"
    assert set(entry) == {
        "source",
        "target",
        "source_language",
        "target_language",
        "source_app",
        "content_type",
        "domain",
        "project_id",
        "game_id",
        "speaker",
        "human_validated",
        "quality_score",
        "provider",
        "model",
    }
    dl = client.get("/datasets/euphoria-game/1/download")
    assert dl.status_code == 200 and "先生" in dl.text
    assert client.get("/datasets").json()
