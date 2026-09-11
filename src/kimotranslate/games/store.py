"""Persistencia de juegos: tablas games + game_texts en el SQLite de Kimo.

Sin segunda base de datos. Upsert por ID estable: re-extraer no duplica;
detecta NEW/CHANGED/UNCHANGED/REMOVED sin borrar traducciones.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS games(
  game_id TEXT PRIMARY KEY, name TEXT NOT NULL, source_path TEXT NOT NULL,
  output_path TEXT NOT NULL DEFAULT '', detected_engine TEXT NOT NULL DEFAULT 'unknown',
  engine_version TEXT NOT NULL DEFAULT '', source_lang TEXT NOT NULL DEFAULT 'ja',
  target_lang TEXT NOT NULL DEFAULT 'es', source_hash TEXT NOT NULL DEFAULT '',
  extractor_version TEXT NOT NULL DEFAULT '', exporter_version TEXT NOT NULL DEFAULT '',
  manifest TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS game_texts(
  id TEXT PRIMARY KEY, game_id TEXT NOT NULL, file_path TEXT NOT NULL,
  source_text TEXT NOT NULL, text_type TEXT NOT NULL DEFAULT 'unknown',
  speaker TEXT NOT NULL DEFAULT '', scene TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL DEFAULT 0,
  original_hash TEXT NOT NULL DEFAULT '', encoding TEXT NOT NULL DEFAULT 'cp932',
  translatable INTEGER NOT NULL DEFAULT 1, skip_reason TEXT NOT NULL DEFAULT '',
  tokens TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'EXTRACTED',
  machine_translation TEXT NOT NULL DEFAULT '', corrected_translation TEXT NOT NULL DEFAULT '',
  job_id TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_gametexts_game ON game_texts(game_id, status);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class GameStore:
    def __init__(self, db: sqlite3.Connection, lock: threading.Lock) -> None:
        self._db = db
        self._lock = lock
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    # --- games ---
    def upsert_game(self, manifest: dict) -> dict:
        manifest = {"updated_at": _now(), **manifest}
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT * FROM games WHERE game_id=?", (manifest["game_id"],)
            ).fetchone()
            if row:
                keep = dict(row)
                keep.update(
                    {k: v for k, v in manifest.items() if v not in ("", [], {}) or k == "manifest"}
                )
                keep["updated_at"] = _now()
                manifest = keep
            else:
                manifest.setdefault("created_at", _now())
            cols = [
                "game_id",
                "name",
                "source_path",
                "output_path",
                "detected_engine",
                "engine_version",
                "source_lang",
                "target_lang",
                "source_hash",
                "extractor_version",
                "exporter_version",
                "manifest",
                "created_at",
                "updated_at",
            ]
            vals = [
                manifest.get(c, "") if c != "manifest" else json.dumps(manifest.get("manifest", {}))
                for c in cols
            ]
            self._db.execute(
                f"INSERT INTO games({','.join(cols)}) VALUES({','.join('?' * len(cols))})"
                " ON CONFLICT(game_id) DO UPDATE SET "
                + ",".join(f"{c}=excluded.{c}" for c in cols[1:]),
                vals,
            )
            r = self._db.execute(
                "SELECT * FROM games WHERE game_id=?", (manifest["game_id"],)
            ).fetchone()
        out = dict(r)
        out["manifest"] = json.loads(out["manifest"])
        return out

    def get_game(self, game_id: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM games WHERE game_id=?", (game_id,)).fetchone()
        if not r:
            return None
        out = dict(r)
        out["manifest"] = json.loads(out["manifest"])
        return out

    def list_games(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM games ORDER BY created_at").fetchall()
        return [{**dict(r), "manifest": json.loads(dict(r)["manifest"])} for r in rows]

    def delete_game(self, game_id: str) -> bool:
        with self._lock, self._db:
            self._db.execute("DELETE FROM game_texts WHERE game_id=?", (game_id,))
            cur = self._db.execute("DELETE FROM games WHERE game_id=?", (game_id,))
            return cur.rowcount > 0

    # --- texts ---
    def merge_texts(self, game_id: str, texts: list[dict]) -> dict:
        """Upsert por ID: NEW / CHANGED / UNCHANGED. Lo ausente -> REMOVED (sin borrar)."""
        stats = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0}
        seen = set()
        with self._lock, self._db:
            for t in texts:
                seen.add(t["id"])
                row = self._db.execute(
                    "SELECT original_hash, status FROM game_texts WHERE id=?", (t["id"],)
                ).fetchone()
                if row is None:
                    self._db.execute(
                        """INSERT INTO game_texts(id, game_id, file_path, source_text, text_type, speaker,
                           scene, position, original_hash, encoding, translatable, skip_reason, tokens,
                           status, metadata, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            t["id"],
                            game_id,
                            t["file_path"],
                            t["source_text"],
                            t["text_type"],
                            t["speaker"],
                            t["scene"],
                            t["position"],
                            t["original_hash"],
                            t["encoding"],
                            int(t["translatable"]),
                            t["skip_reason"],
                            json.dumps(t["tokens"]),
                            t["status"],
                            json.dumps(t.get("metadata", {})),
                            _now(),
                        ),
                    )
                    stats["new"] += 1
                elif row["original_hash"] != t["original_hash"]:
                    self._db.execute(
                        "UPDATE game_texts SET source_text=?, original_hash=?, status='EXTRACTED',"
                        " machine_translation='', job_id='', updated_at=? WHERE id=?",
                        (t["source_text"], t["original_hash"], _now(), t["id"]),
                    )
                    stats["changed"] += 1
                else:
                    stats["unchanged"] += 1
            if seen:
                cur = self._db.execute(
                    f"SELECT id FROM game_texts WHERE game_id=? AND status!='REMOVED' AND id NOT IN"
                    f" ({','.join('?' * len(seen))})",
                    (game_id, *seen),
                )
                for (rid,) in cur.fetchall():
                    self._db.execute(
                        "UPDATE game_texts SET status='REMOVED', updated_at=? WHERE id=?",
                        (_now(), rid),
                    )
                    stats["removed"] += 1
        return stats

    def list_texts(
        self,
        game_id: str,
        status: str = "",
        speaker: str = "",
        scene: str = "",
        translatable: str = "",
        search: str = "",
        limit: int = 500,
    ) -> list[dict]:
        clauses, args = ["game_id=?"], [game_id]
        if status:
            clauses.append("status=?")
            args.append(status)
        if speaker:
            clauses.append("speaker=?")
            args.append(speaker)
        if scene:
            clauses.append("scene=?")
            args.append(scene)
        if translatable in ("0", "1"):
            clauses.append("translatable=?")
            args.append(int(translatable))
        if search:
            clauses.append("(source_text LIKE ? OR machine_translation LIKE ? OR file_path LIKE ?)")
            args += [f"%{search}%"] * 3
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM game_texts WHERE {' AND '.join(clauses)}"
                " ORDER BY file_path, position LIMIT ?",
                (*args, limit),
            ).fetchall()
        return [
            {
                **dict(r),
                "tokens": json.loads(dict(r)["tokens"]),
                "metadata": json.loads(dict(r)["metadata"]),
            }
            for r in rows
        ]

    def counts(self, game_id: str) -> dict:
        with self._lock:
            rows = self._db.execute(
                "SELECT status, COUNT(*) FROM game_texts WHERE game_id=? GROUP BY status",
                (game_id,),
            ).fetchall()
            total = self._db.execute(
                "SELECT COUNT(*) FROM game_texts WHERE game_id=?", (game_id,)
            ).fetchone()[0]
        out = {"total": total}
        out.update({r[0]: r[1] for r in rows})
        return out

    def get_text(self, tid: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM game_texts WHERE id=?", (tid,)).fetchone()
        return dict(r) if r else None

    def set_text(self, tid: str, **fields) -> dict | None:
        fields["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._db:
            cur = self._db.execute(
                f"UPDATE game_texts SET {sets} WHERE id=?", (*fields.values(), tid)
            )
            if cur.rowcount == 0:
                return None
        return self.get_text(tid)
