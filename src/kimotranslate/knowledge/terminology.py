"""Terminología: global < proyecto < juego. Lo específico gana siempre.

Implementa knowledge.interfaces.TerminologyStore sobre SQLite (tabla del
.db propio de Kimo: es lógica de proyecto, no infraestructura del Hub).
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS terminology(
  id TEXT PRIMARY KEY, term TEXT NOT NULL, preferred TEXT NOT NULL,
  source_lang TEXT NOT NULL DEFAULT 'ja', target_lang TEXT NOT NULL DEFAULT 'es',
  project_id TEXT NOT NULL DEFAULT '', game_id TEXT NOT NULL DEFAULT '',
  priority INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_term_langs ON terminology(term, source_lang, target_lang);
"""


def _scope(row: dict) -> str:
    if row["game_id"]:
        return "game"
    if row["project_id"]:
        return "project"
    return "global"


class SQLiteTerminology:
    def __init__(self, db: sqlite3.Connection, lock: threading.Lock) -> None:
        self._db = db
        self._lock = lock
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    def upsert(
        self,
        term: str,
        preferred: str,
        source_lang: str = "ja",
        target_lang: str = "es",
        project_id: str = "",
        game_id: str = "",
        priority: int = 0,
        notes: str = "",
    ) -> dict:
        with self._lock, self._db:
            row = self._db.execute(
                """SELECT * FROM terminology WHERE term=? AND source_lang=?
                   AND target_lang=? AND project_id=? AND game_id=?""",
                (term, source_lang, target_lang, project_id, game_id),
            ).fetchone()
            if row:
                self._db.execute(
                    "UPDATE terminology SET preferred=?, priority=?, notes=? WHERE id=?",
                    (preferred, priority, notes, row["id"]),
                )
                tid = row["id"]
            else:
                tid = uuid.uuid4().hex[:12]
                self._db.execute(
                    """INSERT INTO terminology(id, term, preferred, source_lang, target_lang,
                       project_id, game_id, priority, notes, created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tid,
                        term,
                        preferred,
                        source_lang,
                        target_lang,
                        project_id,
                        game_id,
                        priority,
                        notes,
                        datetime.now(UTC).isoformat(),
                    ),
                )
            r = self._db.execute("SELECT * FROM terminology WHERE id=?", (tid,)).fetchone()
        return {**dict(r), "scope": _scope(dict(r))}

    def lookup(
        self,
        term: str,
        source_lang: str = "ja",
        target_lang: str = "es",
        project_id: str = "",
        game_id: str = "",
    ) -> dict | None:
        """Precedencia: juego > proyecto > global; a igual nivel, mayor priority."""
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM terminology WHERE term=? AND source_lang=?
                   AND target_lang=? AND (project_id IN ('', ?)) AND (game_id IN ('', ?))""",
                (term, source_lang, target_lang, project_id, game_id),
            ).fetchall()
        cands = [dict(r) for r in rows]
        if not cands:
            return None
        # especificidad (game=2, project=1, global=0), luego priority
        best = max(
            cands,
            key=lambda c: ((2 if c["game_id"] else 1 if c["project_id"] else 0), c["priority"]),
        )
        return {**best, "scope": _scope(best)}

    def list_terms(self, project_id: str = "", game_id: str = "", limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM terminology
                   WHERE (project_id IN ('', ?)) AND (game_id IN ('', ?))
                   ORDER BY term LIMIT ?""",
                (project_id, game_id, limit),
            ).fetchall()
        return [{**dict(r), "scope": _scope(dict(r))} for r in rows]
