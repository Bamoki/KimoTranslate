"""Persistencia de imágenes: image_assets + image_regions (SQLite de Kimo)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS image_assets(
  id TEXT PRIMARY KEY, game_id TEXT NOT NULL, project_id TEXT NOT NULL DEFAULT '',
  file_path TEXT NOT NULL, relpath TEXT NOT NULL, original_hash TEXT NOT NULL DEFAULT '',
  width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0,
  format TEXT NOT NULL DEFAULT '', likely_text INTEGER NOT NULL DEFAULT 1,
  skip_reason TEXT NOT NULL DEFAULT '', ocr_status TEXT NOT NULL DEFAULT 'DISCOVERED',
  localization_status TEXT NOT NULL DEFAULT 'DISCOVERED',
  ocr_engine TEXT NOT NULL DEFAULT '', ocr_version TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
  manifest TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS image_regions(
  id TEXT PRIMARY KEY, image_id TEXT NOT NULL, region_index INTEGER NOT NULL DEFAULT 0,
  x INTEGER NOT NULL DEFAULT 0, y INTEGER NOT NULL DEFAULT 0,
  w INTEGER NOT NULL DEFAULT 0, h INTEGER NOT NULL DEFAULT 0,
  polygon TEXT NOT NULL DEFAULT '[]', source_text TEXT NOT NULL DEFAULT '',
  confidence REAL, language TEXT NOT NULL DEFAULT 'ja',
  orientation TEXT NOT NULL DEFAULT 'horizontal', reading_order INTEGER NOT NULL DEFAULT 0,
  group_id TEXT NOT NULL DEFAULT '', text_type TEXT NOT NULL DEFAULT 'dialogue',
  speaker TEXT NOT NULL DEFAULT '', scene TEXT NOT NULL DEFAULT '',
  translatable INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'EXTRACTED',
  machine_translation TEXT NOT NULL DEFAULT '', corrected_translation TEXT NOT NULL DEFAULT '',
  job_id TEXT NOT NULL DEFAULT '', style TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_imgregions_img ON image_regions(image_id, status);
CREATE INDEX IF NOT EXISTS idx_imgassets_game ON image_assets(game_id, ocr_status);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ImageStore:
    def __init__(self, db: sqlite3.Connection, lock: threading.Lock) -> None:
        self._db = db
        self._lock = lock
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    def upsert_asset(self, asset: dict) -> dict:
        asset = {"updated_at": _now(), **asset}
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT * FROM image_assets WHERE id=?", (asset["id"],)
            ).fetchone()
            if row is None:
                asset.setdefault("created_at", _now())
                cols = [
                    "id",
                    "game_id",
                    "project_id",
                    "file_path",
                    "relpath",
                    "original_hash",
                    "width",
                    "height",
                    "format",
                    "likely_text",
                    "skip_reason",
                    "ocr_status",
                    "localization_status",
                    "ocr_engine",
                    "ocr_version",
                    "provider",
                    "model",
                    "manifest",
                    "created_at",
                    "updated_at",
                ]
                vals = [
                    asset.get(c, "") if c != "manifest" else json.dumps(asset.get("manifest", {}))
                    for c in cols
                ]
                vals[9] = int(bool(asset.get("likely_text", True)))
                self._db.execute(
                    f"INSERT INTO image_assets({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                    vals,
                )
            else:
                keep = dict(row)
                keep.update(
                    {
                        k: v
                        for k, v in asset.items()
                        if v not in ("", [], {}) or k in ("manifest", "likely_text")
                    }
                )
                keep["manifest"] = asset.get("manifest", keep["manifest"])
                if isinstance(keep["manifest"], dict):
                    keep["manifest"] = json.dumps(keep["manifest"])
                keep["updated_at"] = _now()
                sets = ", ".join(f"{k}=?" for k in keep if k != "id")
                self._db.execute(
                    f"UPDATE image_assets SET {sets} WHERE id=?",
                    (*[keep[k] for k in keep if k != "id"], keep["id"]),
                )
        return self.get_asset(asset["id"])  # type: ignore[return-value]

    def get_asset(self, image_id: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM image_assets WHERE id=?", (image_id,)).fetchone()
        if not r:
            return None
        out = dict(r)
        out["manifest"] = json.loads(out["manifest"])
        return out

    def list_assets(
        self, game_id: str, ocr_status: str = "", localization_status: str = "", limit: int = 500
    ) -> list[dict]:
        clauses, args = ["game_id=?"], [game_id]
        if ocr_status:
            clauses.append("ocr_status=?")
            args.append(ocr_status)
        if localization_status:
            clauses.append("localization_status=?")
            args.append(localization_status)
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM image_assets WHERE {' AND '.join(clauses)}"
                " ORDER BY relpath LIMIT ?",
                (*args, limit),
            ).fetchall()
        return [{**dict(r), "manifest": json.loads(dict(r)["manifest"])} for r in rows]

    def set_asset(self, image_id: str, **fields) -> dict | None:
        fields["updated_at"] = _now()
        if isinstance(fields.get("manifest"), dict):
            fields["manifest"] = json.dumps(fields["manifest"])
        with self._lock, self._db:
            cur = self._db.execute(
                f"UPDATE image_assets SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                (*fields.values(), image_id),
            )
            if cur.rowcount == 0:
                return None
        return self.get_asset(image_id)

    def replace_regions(self, image_id: str, regions: list[dict]) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM image_regions WHERE image_id=?", (image_id,))
            for r in regions:
                self._db.execute(
                    """INSERT INTO image_regions(id, image_id, region_index, x, y, w, h, polygon,
                       source_text, confidence, language, orientation, reading_order, group_id,
                       text_type, speaker, scene, translatable, status, machine_translation,
                       corrected_translation, job_id, style, updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        r["id"],
                        image_id,
                        r.get("region_index", 0),
                        r.get("x", 0),
                        r.get("y", 0),
                        r.get("w", 0),
                        r.get("h", 0),
                        json.dumps(r.get("polygon", [])),
                        r.get("source_text", ""),
                        r.get("confidence"),
                        r.get("language", "ja"),
                        r.get("orientation", "horizontal"),
                        r.get("reading_order", 0),
                        r.get("group_id", ""),
                        r.get("text_type", "dialogue"),
                        r.get("speaker", ""),
                        r.get("scene", ""),
                        int(r.get("translatable", True)),
                        r.get("status", "EXTRACTED"),
                        r.get("machine_translation", ""),
                        r.get("corrected_translation", ""),
                        r.get("job_id", ""),
                        json.dumps(r.get("style", {})),
                        _now(),
                    ),
                )

    def add_region(self, image_id: str, region: dict) -> dict:
        with self._lock, self._db:
            self._db.execute(
                """INSERT INTO image_regions(id, image_id, region_index, x, y, w, h, polygon,
                   source_text, confidence, language, orientation, reading_order, group_id,
                   text_type, speaker, scene, translatable, status, machine_translation,
                   corrected_translation, job_id, style, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    region["id"],
                    image_id,
                    region.get("region_index", 0),
                    region.get("x", 0),
                    region.get("y", 0),
                    region.get("w", 0),
                    region.get("h", 0),
                    json.dumps(region.get("polygon", [])),
                    region.get("source_text", ""),
                    region.get("confidence"),
                    region.get("language", "ja"),
                    region.get("orientation", "horizontal"),
                    region.get("reading_order", 0),
                    region.get("group_id", ""),
                    region.get("text_type", "dialogue"),
                    region.get("speaker", ""),
                    region.get("scene", ""),
                    int(region.get("translatable", True)),
                    region.get("status", "EXTRACTED"),
                    region.get("machine_translation", ""),
                    region.get("corrected_translation", ""),
                    region.get("job_id", ""),
                    json.dumps(region.get("style", {})),
                    _now(),
                ),
            )
        rows = self.list_regions(image_id)
        return next(r for r in rows if r["id"] == region["id"])

    def list_regions(self, image_id: str, status: str = "") -> list[dict]:
        q = "SELECT * FROM image_regions WHERE image_id=?"
        args: list = [image_id]
        if status:
            q += " AND status=?"
            args.append(status)
        with self._lock:
            rows = self._db.execute(q + " ORDER BY reading_order, region_index", args).fetchall()
        return [
            {
                **dict(r),
                "polygon": json.loads(dict(r)["polygon"]),
                "style": json.loads(dict(r)["style"]),
            }
            for r in rows
        ]

    def set_region(self, rid: str, **fields) -> dict | None:
        fields["updated_at"] = _now()
        for k in ("polygon", "style"):
            if isinstance(fields.get(k), (list, dict)):
                fields[k] = json.dumps(fields[k])
        with self._lock, self._db:
            cur = self._db.execute(
                f"UPDATE image_regions SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                (*fields.values(), rid),
            )
            if cur.rowcount == 0:
                return None
            r = self._db.execute("SELECT * FROM image_regions WHERE id=?", (rid,)).fetchone()
        out = dict(r)
        out["polygon"], out["style"] = json.loads(out["polygon"]), json.loads(out["style"])
        return out

    def counts(self, game_id: str) -> dict:
        with self._lock:
            total = self._db.execute(
                "SELECT COUNT(*) FROM image_assets WHERE game_id=?", (game_id,)
            ).fetchone()[0]
            ocr = self._db.execute(
                "SELECT COUNT(*) FROM image_assets WHERE game_id=? AND ocr_status='OCR_DONE'",
                (game_id,),
            ).fetchone()[0]
            loc = self._db.execute(
                "SELECT COUNT(*) FROM image_assets WHERE game_id=? AND localization_status='LOCALIZED'",
                (game_id,),
            ).fetchone()[0]
        return {"images": total, "ocr_done": ocr, "localized": loc}
