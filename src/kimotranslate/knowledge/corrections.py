"""Correcciones humanas + promoción a conocimiento. Lo auto nunca promociona.

Estados: generated -> reviewed -> corrected -> validated | rejected.
Solo VALIDATED alimenta TM (dedup, sin sobrescribir) y training examples.
Terminología: solo manual (la GUI llama a POST /terminology).
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS corrections(
  id TEXT PRIMARY KEY, source_text TEXT NOT NULL, machine_translation TEXT NOT NULL,
  corrected_translation TEXT NOT NULL DEFAULT '',
  source_lang TEXT NOT NULL DEFAULT 'ja', target_lang TEXT NOT NULL DEFAULT 'es',
  source_app TEXT NOT NULL DEFAULT 'kimotranslate', content_type TEXT NOT NULL DEFAULT '',
  domain TEXT NOT NULL DEFAULT '', project_id TEXT NOT NULL DEFAULT '',
  game_id TEXT NOT NULL DEFAULT '', speaker TEXT NOT NULL DEFAULT '',
  scene TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '', prompt_version TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'generated', reviewer TEXT NOT NULL DEFAULT '',
  human_validated INTEGER NOT NULL DEFAULT 0, quality_score REAL NOT NULL DEFAULT 0,
  game_text_id TEXT NOT NULL DEFAULT '',
  image_region_id TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS training_examples(
  id TEXT PRIMARY KEY, correction_id TEXT NOT NULL, source_text TEXT NOT NULL,
  machine_translation TEXT NOT NULL, corrected_translation TEXT NOT NULL,
  source_lang TEXT NOT NULL, target_lang TEXT NOT NULL, source_app TEXT NOT NULL,
  content_type TEXT NOT NULL, domain TEXT NOT NULL, project_id TEXT NOT NULL DEFAULT '',
  game_id TEXT NOT NULL DEFAULT '', speaker TEXT NOT NULL DEFAULT '',
  scene TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '', prompt_version TEXT NOT NULL DEFAULT '',
  human_validated INTEGER NOT NULL DEFAULT 1, quality_score REAL NOT NULL DEFAULT 1.0,
  created_at TEXT NOT NULL);
"""

# Transiciones permitidas. validated es terminal: lo validado no se reabre.
TRANSITIONS = {
    "generated": ("reviewed", "corrected", "rejected"),
    "reviewed": ("corrected", "validated", "rejected"),
    "corrected": ("corrected", "validated", "rejected"),
    "validated": (),
    "rejected": (),
}

# Calidad: lo humano manda; la confianza auto solo vale sin revisión.
QUALITY = {"generated": 0.0, "reviewed": 0.5, "corrected": 0.7, "validated": 1.0, "rejected": 0.0}


class CorrectionError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CorrectionService:
    def __init__(
        self,
        db: sqlite3.Connection,
        lock: threading.Lock,
        memory=None,
        games=None,
        images=None,
    ) -> None:
        self._db = db
        self._lock = lock
        self.memory = memory  # TranslationMemory o None
        self.games = games  # GameStore o None
        self.images = images  # ImageStore o None
        with self._lock, self._db:
            self._db.executescript(SCHEMA)
            cols = {r[1] for r in self._db.execute("PRAGMA table_info(corrections)")}
            for col in ("game_text_id", "image_region_id"):
                if col not in cols:
                    self._db.execute(
                        f"ALTER TABLE corrections ADD COLUMN {col} TEXT NOT NULL DEFAULT ''"
                    )

    # --- CRUD ---
    def create(self, data: dict) -> dict:
        cid = uuid.uuid4().hex[:12]
        now = _now()
        corrected = data.get("corrected_translation", "")
        status = (
            "corrected"
            if corrected and corrected != data.get("machine_translation")
            else "generated"
        )
        row = {
            "id": cid,
            "source_text": data["source_text"],
            "machine_translation": data.get("machine_translation", ""),
            "corrected_translation": corrected,
            "source_lang": data.get("source_lang", "ja"),
            "target_lang": data.get("target_lang", "es"),
            "source_app": data.get("source_app", "kimotranslate"),
            "content_type": data.get("content_type", ""),
            "domain": data.get("domain", ""),
            "project_id": data.get("project_id", ""),
            "game_id": data.get("game_id", ""),
            "speaker": data.get("speaker", ""),
            "scene": data.get("scene", ""),
            "provider": data.get("provider", ""),
            "model": data.get("model", ""),
            "prompt_version": data.get("prompt_version", ""),
            "status": status,
            "reviewer": data.get("reviewer", ""),
            "human_validated": 0,
            "quality_score": QUALITY[status],
            "game_text_id": data.get("game_text_id", ""),
            "image_region_id": data.get("image_region_id", ""),
            "created_at": now,
            "updated_at": now,
        }
        cols = ",".join(row)
        with self._lock, self._db:
            self._db.execute(
                f"INSERT INTO corrections({cols}) VALUES({','.join('?' * len(row))})",
                tuple(row.values()),
            )
        return row

    def get(self, cid: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM corrections WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None

    def list(self, status: str = "", project_id: str = "", limit: int = 100) -> list[dict]:
        q = "SELECT * FROM corrections"
        args: list = []
        clauses = []
        if status:
            clauses.append("status=?")
            args.append(status)
        if project_id:
            clauses.append("project_id=?")
            args.append(project_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        with self._lock:
            rows = self._db.execute(
                q + " ORDER BY updated_at DESC LIMIT ?", (*args, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def update(self, cid: str, corrected: str = "", reviewer: str = "") -> dict:
        cur = self.get(cid)
        if cur is None:
            raise CorrectionError(f"unknown correction {cid}")
        target = "corrected" if corrected != cur["machine_translation"] else "reviewed"
        return self._transition(
            cur,
            target,
            corrected_translation=corrected or cur["corrected_translation"],
            reviewer=reviewer or cur["reviewer"],
        )

    def validate(self, cid: str, reviewer: str = "") -> dict:
        cur = self.get(cid)
        if cur is None:
            raise CorrectionError(f"unknown correction {cid}")
        if not (cur["corrected_translation"] or cur["machine_translation"]):
            raise CorrectionError("nothing to validate")
        done = self._transition(
            cur, "validated", human_validated=1, reviewer=reviewer or cur["reviewer"]
        )
        self._promote(done)
        if done["game_text_id"] and self.games is not None:
            final = done["corrected_translation"] or done["machine_translation"]
            self.games.set_text(
                done["game_text_id"], corrected_translation=final, status="VALIDATED"
            )
        if done["image_region_id"] and self.images is not None:
            final = done["corrected_translation"] or done["machine_translation"]
            self.images.set_region(
                done["image_region_id"], corrected_translation=final, status="VALIDATED"
            )
        return done

    def reject(self, cid: str, reviewer: str = "") -> dict:
        cur = self.get(cid)
        if cur is None:
            raise CorrectionError(f"unknown correction {cid}")
        return self._transition(cur, "rejected", reviewer=reviewer or cur["reviewer"])

    def _transition(self, cur: dict, target: str, **fields) -> dict:
        if target not in TRANSITIONS[cur["status"]]:
            raise CorrectionError(f"{cur['status']} -> {target} not allowed")
        fields["status"] = target
        fields["quality_score"] = QUALITY[target]
        fields["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._db:
            self._db.execute(
                f"UPDATE corrections SET {sets} WHERE id=?", (*fields.values(), cur["id"])
            )
        updated = self.get(cur["id"])
        assert updated is not None
        return updated

    # --- promoción (solo VALIDATED) ---
    def _promote(self, c: dict) -> None:
        final = c["corrected_translation"] or c["machine_translation"]
        if self.memory is not None and not self._tm_has(c, final):
            self.memory.add(
                c["source_text"],
                final,
                c["domain"] or "game_translation",
                c["content_type"],
                c["project_id"],
                c["game_id"],
                validated=True,
                confidence=c["quality_score"],
            )
        with self._lock, self._db:
            self._db.execute(
                """INSERT INTO training_examples(id, correction_id, source_text, machine_translation,
                   corrected_translation, source_lang, target_lang, source_app, content_type, domain,
                   project_id, game_id, speaker, scene, provider, model, prompt_version,
                   human_validated, quality_score, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uuid.uuid4().hex[:12],
                    c["id"],
                    c["source_text"],
                    c["machine_translation"],
                    final,
                    c["source_lang"],
                    c["target_lang"],
                    c["source_app"],
                    c["content_type"],
                    c["domain"],
                    c["project_id"],
                    c["game_id"],
                    c["speaker"],
                    c["scene"],
                    c["provider"],
                    c["model"],
                    c["prompt_version"],
                    1,
                    c["quality_score"],
                    _now(),
                ),
            )

    def _tm_has(self, c: dict, final: str) -> bool:
        """Dedup: misma fuente + misma traducción + mismo contexto validado -> no duplicar."""
        if self.memory is None:
            return True
        from ..translate.cache import normalize

        for cand in self.memory.search(
            c["source_text"],
            c["domain"] or "game_translation",
            c["content_type"],
            c["project_id"],
            c["game_id"],
            limit=10,
        ):
            if (
                normalize(cand["source"]) == normalize(c["source_text"])
                and cand["translation"] == final
            ):
                return True
        return False
