"""
Local SQLite storage for recordings, transcripts, and analyses.
"""
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from utils.config import PROJECT_ROOT
from utils.logger import log

DB_PATH = PROJECT_ROOT / "voicescribe.db"
AUDIO_DIR = PROJECT_ROOT / "recordings"


@dataclass
class RecordingRecord:
    id: str
    title: str
    duration_sec: float
    audio_path: str
    transcript: str
    language: str
    segments_json: str  # JSON array of segments
    summary: str
    action_items_json: str  # JSON array
    key_points_json: str  # JSON array
    created_at: str


class Storage:
    """SQLite-based local storage."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or DB_PATH
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recordings (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    duration_sec REAL DEFAULT 0,
                    audio_path TEXT,
                    transcript TEXT DEFAULT '',
                    language TEXT DEFAULT '',
                    segments_json TEXT DEFAULT '[]',
                    summary TEXT DEFAULT '',
                    action_items_json TEXT DEFAULT '[]',
                    key_points_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
        log.info(f"Database initialized: {self._db_path}")

    def save_recording(
        self,
        title: str,
        duration_sec: float,
        audio_path: str = "",
        transcript: str = "",
        language: str = "",
        segments: Optional[list] = None,
        summary: str = "",
        action_items: Optional[list] = None,
        key_points: Optional[list] = None,
    ) -> str:
        """Save a new recording. Returns the ID."""
        rec_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO recordings
                   (id, title, duration_sec, audio_path, transcript, language,
                    segments_json, summary, action_items_json, key_points_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec_id,
                    title,
                    duration_sec,
                    audio_path,
                    transcript,
                    language,
                    json.dumps(segments or [], ensure_ascii=False),
                    summary,
                    json.dumps(action_items or [], ensure_ascii=False),
                    json.dumps(key_points or [], ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()

        log.info(f"Saved recording {rec_id}: '{title}'")
        return rec_id

    def update_recording(self, rec_id: str, **kwargs) -> None:
        """Update fields of an existing recording."""
        allowed = {
            "title", "transcript", "language", "summary",
            "segments_json", "action_items_json", "key_points_json",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [rec_id]

        with self._get_conn() as conn:
            conn.execute(
                f"UPDATE recordings SET {set_clause} WHERE id = ?",
                values,
            )
            conn.commit()

    def get_recording(self, rec_id: str) -> Optional[RecordingRecord]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM recordings WHERE id = ?", (rec_id,)
            ).fetchone()

        if row is None:
            return None

        return RecordingRecord(**dict(row))

    def list_recordings(self, limit: int = 50) -> list[RecordingRecord]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM recordings ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [RecordingRecord(**dict(r)) for r in rows]

    def delete_recording(self, rec_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM recordings WHERE id = ?", (rec_id,))
            conn.commit()
        log.info(f"Deleted recording {rec_id}")

    @staticmethod
    def get_audio_dir() -> Path:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        return AUDIO_DIR
