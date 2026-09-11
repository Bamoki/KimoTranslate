"""SQLite (WAL + FK + transacciones). Solo projects + translation_cache.

Sin tablas jobs/workers: esa autoridad es del Hub (hub/client.py).
Sin memoria semántica propia: es MAGI Memory (engines/magi_engine.py).
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from ..knowledge.terminology import SQLiteTerminology


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, game_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS translation_cache(
  key TEXT PRIMARY KEY, source_text TEXT NOT NULL, translation TEXT NOT NULL,
  source_lang TEXT NOT NULL, target_lang TEXT NOT NULL, provider TEXT NOT NULL,
  model TEXT NOT NULL, prompt_version TEXT NOT NULL DEFAULT '',
  content_type TEXT NOT NULL DEFAULT '', domain TEXT NOT NULL DEFAULT '',
  quality REAL, human_verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
"""


class SQLiteRepository:
    """Un solo fichero .db para lógica propia de Kimo.

    # ponytail: global lock + una conexión; pool/Postgres si el throughput lo exige.
    """

    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.executescript(SCHEMA)
        self.terms = SQLiteTerminology(self._db, self._lock)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._db

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def health(self) -> bool:
        with self._lock:
            self._db.execute("SELECT 1").fetchone()
        return True

    def create_project(self, name: str, game_id: str | None) -> dict:
        pid, now = uuid.uuid4().hex[:12], utcnow()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO projects(id,name,game_id,created_at) VALUES(?,?,?,?)",
                (pid, name, game_id, now),
            )
        return {"id": pid, "name": name, "game_id": game_id, "created_at": now}

    def get_project(self, project_id: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(r) if r else None

    def list_projects(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def cache_get(self, key: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM translation_cache WHERE key=?", (key,)).fetchone()
        return dict(r) if r else None

    def cache_put(self, entry: dict) -> None:
        entry = {"created_at": utcnow(), **entry}
        cols = ",".join(entry)
        with self._lock, self._db:
            self._db.execute(
                f"INSERT INTO translation_cache({cols}) VALUES({','.join('?' * len(entry))})"
                " ON CONFLICT(key) DO UPDATE SET translation=excluded.translation,"
                " quality=excluded.quality, human_verified=excluded.human_verified",
                tuple(entry.values()),
            )
