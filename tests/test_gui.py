"""Tests GUI Fase 8.1: lógica sin display (tema, cliente, navegación).

Widgets Tkinter no se instancian aquí (sin display en CI); se validan con
py_compile + mocks. Lo visual se prueba en Windows (checklist en docs).
"""

import io
import json
import sys
import urllib.error

sys.path.insert(0, "gui")
sys.path.insert(0, ".")


def test_theme_tokens():
    from gui.theme.colors import DARK, LIGHT, STATUS
    from gui.theme.spacing import RADIUS, SPACING
    from gui.theme.theme import Theme
    from gui.theme.typography import FONTS

    for palette in (DARK, LIGHT):
        for key in (
            "background",
            "surface",
            "border",
            "text",
            "accent",
            "success",
            "warning",
            "error",
        ):
            assert palette[key].startswith("#"), key
    assert set(SPACING) >= {"XS", "SM", "MD", "LG", "XL"}
    assert set(RADIUS) >= {"SM", "MD", "LG"}
    assert set(FONTS) >= {"display", "title", "body", "caption", "monospace"}
    dark, light = Theme("dark"), Theme("light")
    assert dark.get("background") != light.get("background")
    assert Theme("xx").mode == "dark"  # fallback
    assert dark.status_color("COMPLETED") == dark.get("success")
    assert dark.status_color("RUNNING") == dark.get("info")
    assert dark.status_color("QUE?")
    assert set(STATUS) >= {"ONLINE", "OFFLINE", "RUNNING", "FAILED"}


class _FakeResponse:
    def __init__(self, payload: bytes, code: int = 200):
        self._payload = payload
        self.code = code

    def read(self, *a):
        return self._payload

    def __enter__(self):
        if self.code >= 400:
            raise urllib.error.HTTPError("http://x/", self.code, "Bad", {}, io.BytesIO(b"{}"))
        return self

    def __exit__(self, *a):
        return False


def _client(monkeypatch, payload, code=200):
    from gui.client import KimoApiClient

    def fake_urlopen(req, timeout=None):
        return _FakeResponse(
            payload if isinstance(payload, bytes) else json.dumps(payload).encode(), code
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return KimoApiClient("http://x")


def test_client_games_and_errors(monkeypatch):
    from gui.client import ApiError

    cli = _client(monkeypatch, [{"game_id": "g1"}])
    assert cli.games() == [{"game_id": "g1"}]
    cli = _client(monkeypatch, {}, code=500)
    try:
        cli.games()
        raise AssertionError("must fail")
    except ApiError as e:
        assert "500" in str(e) and e.details is not None  # mensaje amable + detalle


def test_client_server_unavailable(monkeypatch):
    import urllib.request

    from gui.client import ApiError, KimoApiClient

    def boom(req, timeout=None):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    try:
        KimoApiClient("http://x").health()
        raise AssertionError("must fail")
    except ApiError as e:
        assert "no disponible" in str(e)  # nunca traceback crudo


def test_client_retry_uses_request(monkeypatch):
    cli = _client(monkeypatch, {"job_id": "j2"})
    import json as _json

    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["body"] = _json.loads(req.data.decode())
        return _FakeResponse(b'{"job_id": "j2"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    cli.retry_job({"metrics": {"request": {"text": "hola", "context": {"provider": "deepl"}}}})
    assert seen["body"]["text"] == "hola" and seen["body"]["provider"] == "deepl"


def test_navigation_registry():
    import ast

    tree = ast.parse(open("gui/views/__init__.py", encoding="utf-8").read())
    src = open("gui/views/__init__.py", encoding="utf-8").read()
    for key in (
        "overview",
        "games",
        "game_detail",
        "translate",
        "images",
        "review",
        "datasets",
        "jobs",
        "settings",
        "editor",
    ):
        assert f'"{key}"' in src, key
    assert tree  # parsea


def test_sidebar_sections():
    src = open("gui/components/shell.py", encoding="utf-8").read()
    for label in (
        "Overview",
        "WORKSPACE",
        "Games",
        "Translate",
        "Images",
        "Review",
        "Datasets",
        "SYSTEM",
        "Jobs",
        "Settings",
    ):
        assert label in src, label


def test_editor_uses_server_state():
    src = open("gui/editor/editor.py", encoding="utf-8").read()
    assert "sqlite3" not in src and "MemoryStore" not in src  # sin 2º sistema
    for op in (
        "editor_patch",
        "editor_create",
        "editor_delete",
        "editor_mask",
        "editor_preview",
        "editor_undo",
        "editor_redo",
        "editor_validate_region",
    ):
        assert op in src, op


def test_no_hardcoded_server_url():
    import re

    for path in ("gui/client.py", "gui/app.py", "gui/tkinter/config.py"):
        src = open(path, encoding="utf-8").read()
        assert "192.168.1.20" not in src or "DEFAULT" in src or "sugerencia" in src, path
        assert not re.search(r'base_url\s*=\s*"http://192', src), path


def test_version_bump():
    from kimotranslate import __version__

    assert __version__ == "0.8.1"
    import tomllib

    with open("pyproject.toml", "rb") as f:
        assert tomllib.load(f)["project"]["version"] == "0.8.1"
