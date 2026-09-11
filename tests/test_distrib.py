"""Tests distribución: versión única, config GUI, update check, updater."""

from __future__ import annotations

import http.server
import json
import os
import threading

import pytest

from kimotranslate import __version__ as KIMO_VERSION


def test_version_single_source():
    from kimotranslate.release import KIMO_VERSION as REL

    assert REL == KIMO_VERSION
    import re
    import tomllib

    with open("pyproject.toml", "rb") as f:
        assert tomllib.load(f)["project"]["version"] == KIMO_VERSION
    assert re.match(r"^\d+\.\d+\.\d+$", KIMO_VERSION)


@pytest.fixture()
def gui_modules():
    import importlib.util

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    root = os.path.abspath("gui")
    return (
        load("kimo_cfg", os.path.join(root, "tkinter", "config.py")),
        load("kimo_upd", os.path.join(root, "update.py")),
    )


def test_config_roundtrip(tmp_path, monkeypatch, gui_modules):
    cfg_mod, _ = gui_modules
    monkeypatch.setenv("KIMOTRANSLATE_CONFIG", str(tmp_path / "c.json"))
    cfg = cfg_mod.load()
    assert cfg["server_url"].startswith("http")  # default sugerido, editable
    cfg["server_url"] = "http://pi:8005"
    cfg["auto_update"] = False
    cfg_mod.save(cfg)
    assert cfg_mod.load() == cfg


def test_config_corrupt_falls_back(tmp_path, monkeypatch, gui_modules):
    cfg_mod, _ = gui_modules
    p = tmp_path / "c.json"
    p.write_text("{not json")
    monkeypatch.setenv("KIMOTRANSLATE_CONFIG", str(p))
    assert cfg_mod.load()["server_url"].startswith("http")


class _Handler(http.server.BaseHTTPRequestHandler):
    manifest = {}
    payload = b""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith("manifest.json"):
            body = json.dumps(self.manifest).encode()
        elif self.path.endswith(".exe"):
            body = self.payload
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def fake_hub(tmp_path):
    payload = b"MZ" + os.urandom(1000)
    import hashlib

    _Handler.payload = payload
    _Handler.manifest = {
        "product": "KimoTranslate",
        "latest_version": "9.9.9",
        "filename": "KimoTranslate-9.9.9.exe",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", payload
    srv.shutdown()


def test_update_flow_newer(gui_modules, fake_hub, tmp_path):
    _, upd = gui_modules
    url, payload = fake_hub
    manifest = upd.fetch_manifest(url)
    assert upd.is_newer("0.8.0", manifest["latest_version"])
    assert not upd.is_newer("9.9.9", manifest["latest_version"])
    assert not upd.is_newer("0.8.0", "xx") and not upd.is_newer("xx", "9.9.9")
    dest = upd.download(url, manifest["filename"], dest_dir=str(tmp_path))
    upd.verify(dest, manifest["sha256"])  # checksum correcto
    with pytest.raises(upd.UpdateError):
        upd.verify(dest, "0" * 64)  # incorrecto -> aborta, conserva instalación
    with pytest.raises(upd.UpdateError):
        upd.download(url, "../evil.exe", dest_dir=str(tmp_path))
    assert upd.should_auto_check("") and not upd.should_auto_check("2099-01-01T00:00:00+00:00")


def test_update_server_unavailable(gui_modules):
    _, upd = gui_modules
    with pytest.raises(upd.UpdateError):
        upd.fetch_manifest("http://127.0.0.1:1", timeout=1.0)  # no cierra nada, solo error


def test_updater_success_and_rollback(tmp_path):
    import importlib.util
    import stat

    spec = importlib.util.spec_from_file_location("kimo_updater", os.path.abspath("gui/updater.py"))
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    import hashlib

    current = tmp_path / "KimoTranslate.exe"
    current.write_bytes(b"OLD-VERSION")
    # nuevo lanzable que deja marca al arrancar
    launched = tmp_path / "launched.txt"
    new = tmp_path / "KimoTranslate-9.9.9.exe.part"
    new.write_bytes(b"#!/bin/sh\necho hi > " + str(launched).encode() + b"\n")
    new.chmod(new.stat().st_mode | stat.S_IEXEC)
    sha = hashlib.sha256(new.read_bytes()).hexdigest()
    rc = updater.main(["--current", str(current), "--new", str(new), "--sha256", sha])
    import time

    time.sleep(1.0)
    assert rc == 0
    assert current.read_bytes().startswith(b"#!/bin/sh")  # reemplazado
    assert (tmp_path / "KimoTranslate.exe.bak").read_bytes() == b"OLD-VERSION"
    assert launched.exists()  # nueva versión lanzada
    assert not new.exists()  # temporal limpio


def test_updater_aborts_on_bad_checksum(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "kimo_updater2", os.path.abspath("gui/updater.py")
    )
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    current = tmp_path / "KimoTranslate.exe"
    current.write_bytes(b"OLD-VERSION")
    new = tmp_path / "new.part"
    new.write_bytes(b"BAD")
    rc = updater.main(["--current", str(current), "--new", str(new), "--sha256", "0" * 64])
    assert rc != 0
    assert current.read_bytes() == b"OLD-VERSION"  # intacta
    assert not (tmp_path / "KimoTranslate.exe.bak").exists()  # ni backup hizo falta
