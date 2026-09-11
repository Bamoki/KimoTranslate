"""Historial persistente (tabla image_edits): undo/redo + auditoría + rollback."""

from __future__ import annotations

import json as _json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from .models import EditOp

SCHEMA = """
CREATE TABLE IF NOT EXISTS image_edits(
  id TEXT PRIMARY KEY, image_id TEXT NOT NULL, op_type TEXT NOT NULL,
  target_id TEXT NOT NULL DEFAULT '', before_json TEXT NOT NULL DEFAULT '{}',
  after_json TEXT NOT NULL DEFAULT '{}', undone INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_edits_img ON image_edits(image_id, created_at);
"""


class EditHistory:
    def __init__(self, db: sqlite3.Connection, lock: threading.Lock) -> None:
        self._db = db
        self._lock = lock
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    def record(
        self, image_id: str, op_type: str, target_id: str, before: dict, after: dict
    ) -> EditOp:
        op = EditOp(
            uuid.uuid4().hex[:12],
            image_id,
            op_type,
            target_id,
            before,
            after,
            datetime.now(UTC).isoformat(),
        )
        with self._lock, self._db:
            # Nueva operación invalida el "redo": se marcan las deshechas como historia.
            self._db.execute(
                "INSERT INTO image_edits(id, image_id, op_type, target_id, before_json,"
                " after_json, undone, created_at) VALUES(?,?,?,?,?,?,0,?)",
                (
                    op.id,
                    image_id,
                    op_type,
                    target_id,
                    _json.dumps(before),
                    _json.dumps(after),
                    op.created_at,
                ),
            )
        return op

    def _stack(self, image_id: str, undone: int) -> list[EditOp]:
        order = "DESC" if not undone else "ASC"
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM image_edits WHERE image_id=? AND undone=? ORDER BY created_at {order}, id {order}",
                (image_id, undone),
            ).fetchall()
        return [
            EditOp(
                r["id"],
                r["image_id"],
                r["op_type"],
                r["target_id"],
                _json.loads(r["before_json"]),
                _json.loads(r["after_json"]),
                r["created_at"],
                bool(r["undone"]),
            )
            for r in rows
        ]

    def pop_undo(self, image_id: str) -> EditOp | None:
        ops = self._stack(image_id, 0)
        if not ops:
            return None
        op = ops[0]
        with self._lock, self._db:
            self._db.execute("UPDATE image_edits SET undone=1 WHERE id=?", (op.id,))
        return op

    def pop_redo(self, image_id: str) -> EditOp | None:
        """Redo = la deshecha MÁS RECIENTE (la última en deshacerse)."""
        ops = self._stack(image_id, 1)
        if not ops:
            return None
        op = ops[0]
        with self._lock, self._db:
            self._db.execute("UPDATE image_edits SET undone=0 WHERE id=?", (op.id,))
        return op

    def log(self, image_id: str, limit: int = 100) -> list[EditOp]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM image_edits WHERE image_id=? ORDER BY created_at DESC LIMIT ?",
                (image_id, limit),
            ).fetchall()
        return [
            EditOp(
                r["id"],
                r["image_id"],
                r["op_type"],
                r["target_id"],
                _json.loads(r["before_json"]),
                _json.loads(r["after_json"]),
                r["created_at"],
                bool(r["undone"]),
            )
            for r in rows
        ]
