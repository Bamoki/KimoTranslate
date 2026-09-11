"""Dataset Builder: validated examples -> JSONL versionado. Local y rápido
(SQLite + fichero); si crece se mueve a un job BUILD_DATASET del Hub
(JobType ya existe) sin cambiar la interfaz.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets(
  dataset_id TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL,
  filters TEXT NOT NULL, example_count INTEGER NOT NULL, sha256 TEXT NOT NULL,
  path TEXT NOT NULL, PRIMARY KEY (dataset_id, version));
"""

FILTER_KEYS = (
    "source_app",
    "domain",
    "content_type",
    "project_id",
    "game_id",
    "source_lang",
    "target_lang",
    "provider",
)


class DatasetBuilder:
    def __init__(self, db: sqlite3.Connection, lock: threading.Lock, data_dir: str) -> None:
        self._db = db
        self._lock = lock
        self._dir = os.path.join(data_dir, "datasets")
        os.makedirs(self._dir, exist_ok=True)
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    def query(self, validated_only: bool = True, limit: int = 10000, **filters) -> list[dict]:
        clauses, args = [], []
        if validated_only:
            clauses.append("human_validated=1")
        for k in FILTER_KEYS:
            if filters.get(k):
                clauses.append(f"{k}=?")
                args.append(filters[k])
        q = "SELECT * FROM training_examples"
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        with self._lock:
            rows = self._db.execute(q + " ORDER BY created_at LIMIT ?", (*args, limit)).fetchall()
        seen, out = set(), []
        for r in [dict(x) for x in rows]:
            # Dedup: misma fuente + destino + contexto. Sin cientos de copias.
            key = (
                r["source_text"],
                r["corrected_translation"],
                r["source_lang"],
                r["target_lang"],
                r["domain"],
                r["content_type"],
                r["project_id"],
            )
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out

    def build(self, dataset_id: str = "", **filters) -> dict:
        dataset_id = dataset_id or filters.get("source_app", "kimotranslate") + "-dataset"
        examples = self.query(**filters)
        lines = [json.dumps(self._export_row(e), ensure_ascii=False) for e in examples]
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT COALESCE(MAX(version),0) FROM datasets WHERE dataset_id=?", (dataset_id,)
            ).fetchone()
            version = (row[0] or 0) + 1
        path = os.path.join(self._dir, f"{dataset_id}_v{version}.jsonl")
        body = "\n".join(lines) + ("\n" if lines else "")
        digest = hashlib.sha256(body.encode()).hexdigest()[:16]
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        manifest = {
            "dataset_id": dataset_id,
            "version": version,
            "created_at": datetime.now(UTC).isoformat(),
            "filters": {k: v for k, v in filters.items() if v},
            "example_count": len(examples),
            "sha256": digest,
            "path": path,
        }
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO datasets(dataset_id, version, created_at, filters, example_count, sha256, path)"
                " VALUES(?,?,?,?,?,?,?)",
                (
                    dataset_id,
                    version,
                    manifest["created_at"],
                    json.dumps(manifest["filters"]),
                    len(examples),
                    digest,
                    path,
                ),
            )
        return manifest

    @staticmethod
    def _export_row(e: dict) -> dict:
        """Solo lo necesario para entrenar/localizar. Cero secretos."""
        return {
            "source": e["source_text"],
            "target": e["corrected_translation"],
            "source_language": e["source_lang"],
            "target_language": e["target_lang"],
            "source_app": e["source_app"],
            "content_type": e["content_type"],
            "domain": e["domain"],
            "project_id": e["project_id"],
            "game_id": e["game_id"],
            "speaker": e["speaker"],
            "human_validated": bool(e["human_validated"]),
            "quality_score": e["quality_score"],
            "provider": e["provider"],
            "model": e["model"],
        }

    def list_datasets(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM datasets ORDER BY dataset_id, version"
            ).fetchall()
        return [{**dict(r), "filters": json.loads(dict(r)["filters"])} for r in rows]

    def get(self, dataset_id: str, version: int) -> dict | None:
        with self._lock:
            r = self._db.execute(
                "SELECT * FROM datasets WHERE dataset_id=? AND version=?", (dataset_id, version)
            ).fetchone()
        return dict(r) if r else None
