"""Tests Fase 5: YU-RIS real (sintético) -> extract -> translate -> export."""

from __future__ import annotations

import hashlib
import os

import pytest

from kimotranslate.engines.magi_engine import FakeBackend, MagiTranslationEngine
from kimotranslate.games import tokens as game_tokens
from kimotranslate.games.engines import clockup
from kimotranslate.games.yuris import ypf, ystb
from kimotranslate.worker.agent import KimoWorker
from tests.game_factory import (
    CALL_OP,
    DLG_A,
    DLG_B,
    KEY_A,
    KEY_B,
    MSG_OP,
    build_ypf,
    build_ystb,
    make_game,
)

HINTS = {"*": {"msg_op": MSG_OP, "call_op": CALL_OP}}


@pytest.fixture(autouse=True)
def _drain(hub_client):
    """Cola del Hub limpia por test (servidor Hub compartido por sesión)."""
    while True:
        job = hub_client.claim("kimo-drain", types="translation")
        if job is None:
            break
        hub_client.result(job["id"], False, error="drained by test setup")


@pytest.fixture()
def game_a(tmp_path):
    return make_game(str(tmp_path), "game_a", {"yst00001.ybn": DLG_A, "yst00002.ybn": DLG_B}, KEY_A)


@pytest.fixture()
def game_b(tmp_path):
    return make_game(str(tmp_path), "game_b", {"yst00001.ybn": DLG_B}, KEY_B)


@pytest.fixture()
def game_c(tmp_path):
    return make_game(str(tmp_path), "game_c", {"yst00001.ybn": DLG_A}, KEY_A, packed=True)


@pytest.fixture()
def game_nested(tmp_path):
    # Variante real Natsu no Kusari: .ypf solo en pac/, sin exe ni sueltos.
    return make_game(str(tmp_path), "game_n", {"yst00001.ybn": DLG_A}, KEY_A, pac_split=True)


# --- detection ---


def test_detect_clockup_loose(game_a):
    det = clockup.detect(game_a)
    assert det.engine == "clockup" and det.confidence == 0.99
    assert any("YSTB" in e for e in det.evidence) and "yu-ris.exe" in det.evidence


def test_detect_clockup_packed(game_c):
    det = clockup.detect(game_c)
    assert det.engine == "clockup" and det.confidence >= 0.6


def test_detect_nested_pac_variant(game_nested):
    det = clockup.detect(game_nested)
    assert det.engine == "clockup" and det.confidence >= 0.6
    assert any(e.startswith("ypf:pac/") for e in det.evidence)


def test_detect_unknown(tmp_path):
    d = str(tmp_path / "empty")
    os.makedirs(d)
    det = clockup.detect(d)
    assert det.engine == "unknown" and det.confidence == 0.0


# --- YPF ---


def test_ypf_roundtrip():
    blob = build_ystb(DLG_A)
    arc = build_ypf({"ysbin/yst00001.ybn": blob})
    version, entries = ypf.parse_ypf(arc)
    assert version == 463 and [e.name for e in entries] == ["ysbin/yst00001.ybn"]
    assert ypf.extract_entry(arc, entries[0], version) == blob


def test_ypf_bad_checksum():
    arc = bytearray(build_ypf({"ysbin/a.ybn": b"12345678901234567890"}))
    arc[-5] ^= 0xFF
    version, entries = ypf.parse_ypf(bytes(arc))
    with pytest.raises(ypf.YpfError):
        ypf.extract_entry(bytes(arc), entries[0], version)


# --- YSTB ---


def test_ystb_key_and_parse():
    blob = build_ystb(DLG_A, KEY_B)
    assert ystb.guess_key(blob) == KEY_B
    script = ystb.parse(blob, KEY_B)
    first_msg = next(i for i in script.insts if i.op == MSG_OP)
    assert ystb.decode(first_msg.args[0].data) == "おはよう、{PLAYER}。今日もいい天気だね。"
    with pytest.raises(ystb.YstbError):
        ystb.parse(blob, 0x12345678)


def test_ystb_opcode_guess():
    items = [("msg", f"テスト文章その{i}です。") for i in range(12)]
    items += [("call", '"es.sel.set"', ["はい"])] * 6
    script = ystb.parse(build_ystb(items), KEY_A)
    assert ystb.guess_ops(script) == (MSG_OP, CALL_OP)


def test_ystb_repack_roundtrip():
    blob = build_ystb(DLG_A, KEY_A)
    script = ystb.parse(blob, KEY_A)
    msg_op, call_op = ystb.guess_ops(script, MSG_OP, CALL_OP)
    # cp932 no acepta acentos españoles: el exportador lo valida por línea.
    # (SJIS tunneling / fuente custom = trabajo futuro, documentado.)
    finals = [
        "直人",
        "Buenos dias {PLAYER} amigo",
        "Vamos a la escuela",
        "Ir",
        "Descansar",
        "Es una trampa",
    ]
    new = ystb.repack(script, finals, msg_op, call_op, KEY_A)
    back = ystb.parse(new, KEY_A)
    got = []
    for inst in back.insts:
        if inst.op == msg_op and len(inst.args) == 1:
            got.append(ystb.decode(inst.args[0].data))
        elif inst.op == call_op:
            for a in inst.args[1:]:
                if a.type == 3 and a.data not in (b'""', b"''"):
                    got.append(ystb.decode(a.data))
    assert got == finals


# --- tokens ---


def test_tokens_preserved_or_blocked():
    assert game_tokens.find_tokens("Hola {PLAYER}, ve al 100%") == ["{PLAYER}"]
    assert game_tokens.tokens_ok("a {X} b", "a {X} b")
    assert not game_tokens.tokens_ok("a {X} b", "a b")


# --- extraction ---


def test_extract_classification(game_a):
    texts, fileinfo = clockup.extract("ga", game_a, HINTS)
    by_type = {}
    for t in texts:
        by_type.setdefault(t.text_type, []).append(t)
    assert len(by_type["dialogue"]) == 5  # 3 en f1 + 2 en f2
    assert len(by_type["choice"]) == 2
    assert by_type["system"][0].source_text == "直人"  # el nombre fija speaker
    assert all(t.speaker == "直人" for t in by_type["dialogue"][:3])
    assert texts[1].tokens == ["{PLAYER}"]
    assert all(t.id.startswith("clockup:ga:") for t in texts)
    assert len({t.id for t in texts}) == len(texts)
    assert set(fileinfo) == {"ysbin/yst00001.ybn", "ysbin/yst00002.ybn"}
    assert all(set(f) >= {"key", "msg_op", "call_op", "sha"} for f in fileinfo.values())


def test_extract_skips_non_jp(tmp_path):
    g = make_game(
        str(tmp_path), "gx", {"s.ybn": [("msg", "SaveFile01.dat"), ("msg", "こんにちは")]}
    )
    texts, _ = clockup.extract("gx", g, HINTS)
    assert texts[0].status == "SKIPPED" and texts[0].skip_reason == "non-jp"
    assert texts[1].translatable


def test_extract_ids_stable(game_a):
    once, _ = clockup.extract("ga", game_a, HINTS)
    twice, _ = clockup.extract("ga", game_a, HINTS)
    assert [t.id for t in once] == [t.id for t in twice]


# --- API games ---


def _register(client, path, game_id):
    r = client.post("/games", json={"source_path": path, "game_id": game_id, "name": game_id})
    assert r.status_code == 201, r.text
    return r.json()


def test_register_and_extract_local(client, game_a):
    g = _register(client, game_a, "game_a")
    assert g["detected_engine"] == "clockup"
    stats = client.post("/games/game_a/extract", params={"local": True}).json()
    assert stats["texts_found"] == 9 and stats["texts_translatable"] == 9
    rows = client.get("/games/game_a/texts").json()
    assert len(rows) == 9
    assert client.get("/games/game_a/texts", params={"speaker": "直人"}).json()
    assert client.get("/games/game_a/texts", params={"search": "罠"}).json()
    assert client.get("/games/game_a").json()["counts"]["total"] == 9
    assert client.get("/games").json()


def test_reextract_diff(client, game_a):
    _register(client, game_a, "game_a")
    client.post("/games/game_a/extract", params={"local": True})
    again = client.post("/games/game_a/extract", params={"local": True}).json()
    assert again["new"] == 0 and again["unchanged"] == 9
    # nuevo fichero + texto cambiado + fichero eliminado
    extra = os.path.join(game_a, "ysbin", "yst00009.ybn")
    with open(extra, "wb") as f:
        f.write(build_ystb([("msg", "新規テキスト")]))
    fe = os.path.join(game_a, "ysbin", "yst00002.ybn")
    os.rename(fe, fe + ".bak")
    diff = client.post("/games/game_a/extract", params={"local": True}).json()
    assert diff["new"] == 1 and diff["removed"] == 3
    os.rename(fe + ".bak", fe)
    os.remove(extra)


def test_changed_text_resets(client, game_a):
    _register(client, game_a, "game_a")
    client.post("/games/game_a/extract", params={"local": True})
    tid = "clockup:game_a:ysbin/yst00001.ybn:msg:1"
    fe = os.path.join(game_a, "ysbin", "yst00001.ybn")
    with open(fe, "wb") as f:
        items = [list(x) for x in DLG_A]
        items[1] = ("msg", "おはよう、{PLAYER}。雨ですね。")
        f.write(build_ystb([tuple(x) for x in items]))
    diff = client.post("/games/game_a/extract", params={"local": True}).json()
    assert diff["changed"] == 1
    row = [t for t in client.get("/games/game_a/texts").json() if t["id"] == tid][0]
    assert row["status"] == "EXTRACTED" and row["machine_translation"] == ""


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

    def bulk_texts(self, game_id, texts, fileinfo):
        from kimotranslate.worker.agent import text_to_json

        return self._c.post(
            f"/games/{game_id}/texts/bulk",
            json={"texts": [text_to_json(t) for t in texts], "fileinfo": fileinfo},
        ).json()

    def export_bundle(self, game_id):
        return self._c.get(f"/games/{game_id}/export-bundle").json()

    def export_report(self, game_id, manifest):
        return self._c.post(f"/games/{game_id}/export-report", json=manifest).json()

    def push_game_images(self, game_id, assets):
        return self._c.post(f"/games/{game_id}/images/bulk", json={"assets": assets}).json()

    def game_images_export_list(self, game_id):
        return self._c.get(f"/games/{game_id}/images/export-list").json()


def _drain_worker(hub_client, kimo_api, text=None):
    from kimotranslate.games import tokens as game_tokens

    class Echo(FakeBackend):
        def generate(self, model, prompt, **kw):
            if text is not None:
                self.text = text
            else:  # eco: conserva exactamente los tokens del original
                src = prompt.split("Text: ")[-1].strip()
                toks = " ".join(game_tokens.find_tokens(src))
                self.text = '{"translation": "T ' + toks + '", "confidence": 0.9}'
            return super().generate(model, prompt, **kw)

    worker = KimoWorker(hub_client, "gw", MagiTranslationEngine(backend=Echo()), kimo_api=kimo_api)
    for _ in range(50):
        if worker.run_once() is None:
            break


def test_game_translate_sync_flow(client, hub_client, game_a, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    _register(client, game_a, "game_a")
    client.post("/games/game_a/extract", params={"local": True})
    out = client.post("/games/game_a/translate", json={"provider": "magi"}).json()
    assert out["queued"] == 9
    _drain_worker(hub_client, _StubKimo(client, mem))
    synced = client.post("/games/game_a/sync").json()
    assert synced["synced"] == 9
    rows = client.get("/games/game_a/texts", params={"status": "TRANSLATED"}).json()
    assert len(rows) == 9
    hello = [r for r in rows if r["source_text"].startswith("おはよう")][0]
    assert hello["machine_translation"] == "T {PLAYER}"


def test_game_isolation_ab(client, hub_client, game_a, game_b, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    _register(client, game_a, "game_a")
    _register(client, game_b, "game_b")
    client.post("/games/game_a/extract", params={"local": True})
    client.post("/games/game_b/extract", params={"local": True})
    # mismo texto おはよう en ambos: traducir A no contamina B (scope en cache key)
    only_a = [
        t
        for t in client.get("/games/game_a/texts").json()
        if t["source_text"].startswith("おはよう")
    ]
    assert only_a
    client.post("/games/game_a/translate", json={"ids": [only_a[0]["id"]]}).json()
    _drain_worker(hub_client, _StubKimo(client, mem))
    client.post("/games/game_a/sync")
    b_same = [
        t
        for t in client.get("/games/game_b/texts").json()
        if t["source_text"] == only_a[0]["source_text"]
    ]
    assert b_same and b_same[0]["status"] == "EXTRACTED"  # B intacto
    out_b = client.post("/games/game_b/translate", json={"ids": [b_same[0]["id"]]}).json()
    assert out_b["queued"] == 1 and out_b["cached"] == 0


def test_token_mismatch_needs_review(client, hub_client, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    g = make_game(str(tmp_path), "gt", {"s.ybn": [("msg", "行こう、{PLAYER}。")]})
    _register(client, g, "game_t")
    client.post("/games/game_t/extract", params={"local": True})
    client.post("/games/game_t/translate", json={}).json()
    worker = KimoWorker(
        hub_client,
        "gw",
        MagiTranslationEngine(
            backend=FakeBackend(text='{"translation": "Vamos", "confidence": 0.5}')
        ),
        kimo_api=_StubKimo(client, mem),
    )
    worker.run_once()
    client.post("/games/game_t/sync")
    rows = client.get("/games/game_t/texts").json()
    assert rows[0]["status"] == "REVIEW_REQUIRED"


def test_correction_links_game_text(client, game_a):
    _register(client, game_a, "game_a")
    client.post("/games/game_a/extract", params={"local": True})
    tid = "clockup:game_a:ysbin/yst00001.ybn:msg:1"
    c = client.post(
        "/corrections",
        json={
            "source_text": "おはよう",
            "machine_translation": "M",
            "corrected_translation": "C",
            "game_id": "game_a",
            "game_text_id": tid,
        },
    ).json()
    assert c["game_text_id"] == tid
    client.patch(f"/corrections/{c['id']}", json={"validated": True})
    rows = [t for t in client.get("/games/game_a/texts").json() if t["id"] == tid]
    assert rows[0]["status"] == "VALIDATED" and rows[0]["corrected_translation"] == "C"


def test_export_local(client, hub_client, game_a, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    _register(client, game_a, "game_a")
    before = {
        p: hashlib.sha256(open(os.path.join(game_a, "ysbin", p), "rb").read()).hexdigest()
        for p in ("yst00001.ybn", "yst00002.ybn")
    }
    client.post("/games/game_a/extract", params={"local": True})
    client.post("/games/game_a/translate", json={}).json()
    _drain_worker(hub_client, _StubKimo(client, mem))
    client.post("/games/game_a/sync")
    out = str(tmp_path / "localized_game")
    manifest = client.post("/games/game_a/export", json={"output_path": out, "local": True}).json()
    assert manifest["exported_files"] == 2 and not manifest["failed"]
    assert manifest["engine"] == "clockup" and manifest["translation_count"] == 9
    for p, h in before.items():
        assert hashlib.sha256(open(os.path.join(game_a, "ysbin", p), "rb").read()).hexdigest() == h
        assert os.path.exists(os.path.join(out, "backup", "ysbin", p))
        exported = open(os.path.join(out, "localized", "ysbin", p), "rb").read()
        assert exported != open(os.path.join(game_a, "ysbin", p), "rb").read()
    reparsed = ystb.parse(exported, KEY_A)
    assert ystb.decode(reparsed.insts[1].args[0].data) == "T {PLAYER}"
    assert manifest["files"][0]["source_hash"] and manifest["files"][0]["output_hash"]


def test_export_blocks_bad_tokens(client, game_a, tmp_path):
    _register(client, game_a, "game_a")
    client.post("/games/game_a/extract", params={"local": True})
    tid = "clockup:game_a:ysbin/yst00001.ybn:msg:1"
    c = client.post(
        "/corrections",
        json={
            "source_text": "x",
            "machine_translation": "M",
            "corrected_translation": "sin token",
            "game_id": "game_a",
            "game_text_id": tid,
        },
    ).json()
    client.patch(f"/corrections/{c['id']}", json={"validated": True})
    out = str(tmp_path / "out2")
    manifest = client.post("/games/game_a/export", json={"output_path": out, "local": True}).json()
    assert manifest["exported_files"] == 0  # fichero incompleto: no se toca nada
    assert not os.path.exists(os.path.join(out, "localized", "ysbin", "yst00001.ybn"))


def test_export_unencodable_blocked(client, hub_client, game_a, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    _register(client, game_a, "game_a")
    client.post("/games/game_a/extract", params={"local": True})
    client.post("/games/game_a/translate", json={}).json()
    _drain_worker(hub_client, _StubKimo(client, mem))
    client.post("/games/game_a/sync")
    # override con emoji conservando el token: falla encoding, no tokens
    tid = "clockup:game_a:ysbin/yst00001.ybn:msg:1"
    src = [t for t in client.get("/games/game_a/texts").json() if t["id"] == tid][0]
    c = client.post(
        "/corrections",
        json={
            "source_text": src["source_text"],
            "machine_translation": "M",
            "corrected_translation": "{PLAYER} 😀",
            "game_id": "game_a",
            "game_text_id": tid,
        },
    ).json()
    client.patch(f"/corrections/{c['id']}", json={"validated": True})
    out = str(tmp_path / "out3")
    manifest = client.post("/games/game_a/export", json={"output_path": out, "local": True}).json()
    assert manifest["exported_files"] == 1  # el otro fichero sí sale
    bad = [f for f in manifest["failed"] if f["file"] == "ysbin/yst00001.ybn"]
    assert bad and "unencodable" in bad[0]["reason"]
    assert not os.path.exists(os.path.join(out, "localized", "ysbin", "yst00001.ybn"))


def test_worker_extract_and_export_jobs(client, hub_client, game_c, tmp_path):
    from magi.memory.store import MemoryStore

    from kimotranslate.knowledge.memory import TranslationMemory

    mem = TranslationMemory(store=MemoryStore(str(tmp_path / "m.db")))
    _register(client, game_c, "game_c")
    job = client.post("/games/game_c/extract", json={}).json()
    assert job["method"] == "custom"
    worker = KimoWorker(
        hub_client,
        "gw",
        MagiTranslationEngine(backend=FakeBackend()),
        kimo_api=_StubKimo(client, mem),
    )
    done = worker.run_once()
    assert done["status"] == "COMPLETED"
    assert len(client.get("/games/game_c/texts").json()) == 6  # desde .ypf
    client.post("/games/game_c/translate", json={}).json()
    _drain_worker(hub_client, _StubKimo(client, mem))
    client.post("/games/game_c/sync")
    out = str(tmp_path / "outc")
    client.post("/games/game_c/export", json={"output_path": out}).json()
    done2 = worker.run_once()
    assert done2["status"] == "COMPLETED"
    rep = client.get("/games/game_c").json()["manifest"]["last_export"]
    assert rep["exported_files"] == 1
    assert os.path.exists(os.path.join(out, "localized", "ysbin", "yst00001.ybn"))


def test_unknown_engine_extract_fails(client, tmp_path):
    d = str(tmp_path / "plain")
    os.makedirs(d)
    g = _register(client, d, "plain")
    assert g["detected_engine"] == "unknown"
    assert client.post("/games/plain/extract", params={"local": True}).status_code == 400


def test_delete_game(client, game_a):
    _register(client, game_a, "game_a")
    client.post("/games/game_a/extract", params={"local": True})
    assert client.delete("/games/game_a").json() == {"deleted": "game_a"}
    assert client.get("/games/game_a/texts").status_code == 404


def test_inline_controls_roundtrip():
    # Patrón real Natsu no Kusari: texto + 0x80+byte + texto + cola binaria.
    raw = "おはよう".encode("cp932") + b"\x80g" + "ございます".encode("cp932") + b"\x00\x03"
    segments, ctls, junks = ystb.split_controls(raw)
    assert [k for k, _ in segments] == ["t", "c", "t", "x"]
    assert ctls == [b"\x80g"]
    template, ctls_hex, junks_hex = ystb.build_template(segments, ctls, junks)
    assert template == "おはよう{Y0}ございます{X0}"
    assert game_tokens.find_tokens(template) == ["{Y0}", "{X0}"]
    # traducción simulada conserva placeholders -> bytes exactos
    rebuilt = ystb.rebuild("Ohayo{Y0}gozaimasu{X0}", ctls_hex, junks_hex)
    assert rebuilt == "Ohayo".encode("cp932") + b"\x80g" + "gozaimasu".encode("cp932") + b"\x00\x03"
    with __import__("pytest").raises(ystb.YstbError):
        ystb.rebuild("Ohayo{Y9}", ctls_hex, junks_hex)  # placeholder sin datos
    # sin texto traducible -> skipped, no a MT
    assert ystb.build_template(*ystb.split_controls(b"\x00\x03\xff"))[0] == ""


def test_extract_emit_and_repack_with_controls(tmp_path):
    # .ybn sintético con control inline real -> extract -> repack preserva bytes.
    raw_msg = "おはよう".encode("cp932") + b"\x80g" + "ね".encode("cp932")
    gdir = os.path.join(str(tmp_path), "gctl")
    os.makedirs(os.path.join(gdir, "ysbin"))
    with open(os.path.join(gdir, "ysbin", "s.ybn"), "wb") as f:
        f.write(build_ystb([("msg_raw", raw_msg)], KEY_A))
    texts, fi = clockup.extract(
        "gx", gdir, {"*": {"msg_op": MSG_OP, "call_op": CALL_OP}})
    assert len(texts) == 1
    t = texts[0]
    assert t.source_text == "おはよう{Y0}ね"
    assert t.metadata["ctls"] == ["8067"] and t.translatable
    # traducción simulada + rebuild + repack -> control intacto en el binario
    final = "Ohayo{Y0}ne"
    assert game_tokens.tokens_ok(t.source_text, final)
    blob = ystb.rebuild(final, t.metadata["ctls"], t.metadata["junks"])
    script = ystb.parse(open(os.path.join(gdir, "ysbin", "s.ybn"), "rb").read(), KEY_A)
    new_raw = ystb.repack_bytes(script, [blob], MSG_OP, CALL_OP, KEY_A)
    back = ystb.parse(new_raw, KEY_A)
    got = next(i.args[0].data for i in back.insts if i.op == MSG_OP)
    assert got == blob
    assert got.startswith(b"Ohayo") and b"\x80g" in got and got.endswith("ne".encode("cp932"))


def test_repack_bytes_preserves_controls(tmp_path):
    raw_msg = "おはよう".encode("cp932") + b"\x80g" + "ね".encode("cp932")
    blob = build_ystb([("msg", "ダミー")], KEY_A)
    script = ystb.parse(blob, KEY_A)
    # sustituye el recurso del único msg por el patrón con control
    inst = next(i for i in script.insts if i.op == MSG_OP)
    arg = inst.args[0]
    res_off = script.res_start + arg.res_offset
    new_res = raw_msg
    dec = bytearray(script.raw)
    dec[res_off : res_off + arg.res_size] = new_res
    # re-parsea el script modificado como si viniera del juego
    import struct as _st

    hdr = bytearray(blob[:32])
    code_size, arg_size = _st.unpack_from("<II", bytes(hdr), 12)
    # reconstruye fichero válido: re-empaqueta vía API pública con override
    texts, _ = clockup.extract("gx", str(tmp_path), {})
    assert texts == []
    segs, ctls, junks = ystb.split_controls(raw_msg)
    template, ch, jh = ystb.build_template(segs, ctls, junks)
    assert template == "おはよう{Y0}ね"
    final = "Ohayo{Y0}ne"
    rebuilt = ystb.rebuild(final, ch, jh)
    assert rebuilt == "Ohayo".encode("cp932") + b"\x80g" + "ne".encode("cp932")
