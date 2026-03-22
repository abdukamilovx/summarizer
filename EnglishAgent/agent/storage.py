"""SQLite persistent storage for student data, vocabulary, grammar, and sessions."""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path


class StudentStorage:
    def __init__(self, db_path: str = "data/english_agent.db"):
        self.db_path = db_path
        self._lock = threading.Lock()

    def initialize(self):
        """Create tables if they don't exist. Call once at startup."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._lock:
            conn = self._connect()
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS students (
                    student_id INTEGER PRIMARY KEY,
                    name TEXT DEFAULT '',
                    level TEXT DEFAULT 'A1',
                    level_score REAL DEFAULT 0.0,
                    mode TEXT DEFAULT 'kids',
                    created_at TEXT DEFAULT (datetime('now')),
                    last_session_at TEXT
                );

                CREATE TABLE IF NOT EXISTS vocabulary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    translation_ru TEXT DEFAULT '',
                    level TEXT DEFAULT 'A1',
                    learned_date TEXT DEFAULT (datetime('now')),
                    last_tested TEXT,
                    score REAL DEFAULT 0.0,
                    times_tested INTEGER DEFAULT 0,
                    times_correct INTEGER DEFAULT 0,
                    FOREIGN KEY (student_id) REFERENCES students(student_id),
                    UNIQUE(student_id, word COLLATE NOCASE)
                );

                CREATE TABLE IF NOT EXISTS grammar_areas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    area TEXT NOT NULL,
                    score REAL DEFAULT 50.0,
                    error_count INTEGER DEFAULT 0,
                    last_error_at TEXT,
                    FOREIGN KEY (student_id) REFERENCES students(student_id),
                    UNIQUE(student_id, area)
                );

                CREATE TABLE IF NOT EXISTS session_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    started_at TEXT DEFAULT (datetime('now')),
                    ended_at TEXT,
                    duration_seconds REAL DEFAULT 0,
                    message_count INTEGER DEFAULT 0,
                    words_learned TEXT DEFAULT '[]',
                    errors_summary TEXT DEFAULT '[]',
                    homework TEXT DEFAULT '[]',
                    level_before TEXT,
                    level_after TEXT,
                    FOREIGN KEY (student_id) REFERENCES students(student_id)
                );

                CREATE TABLE IF NOT EXISTS homework (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    translation_ru TEXT DEFAULT '',
                    assigned_date TEXT DEFAULT (datetime('now')),
                    tested INTEGER DEFAULT 0,
                    test_result REAL,
                    FOREIGN KEY (student_id) REFERENCES students(student_id)
                );

                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    badge_name TEXT NOT NULL,
                    earned_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (student_id) REFERENCES students(student_id),
                    UNIQUE(student_id, badge_name)
                );

                CREATE TABLE IF NOT EXISTS pronunciation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    score REAL DEFAULT 0.0,
                    problem_sounds TEXT DEFAULT '[]',
                    recorded_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (student_id) REFERENCES students(student_id)
                );
            """)
            # Migrations for existing databases
            self._run_migrations(conn)
            conn.commit()
            conn.close()

    def _run_migrations(self, conn: sqlite3.Connection):
        """Add columns that may be missing in older databases."""
        cursor = conn.execute("PRAGMA table_info(students)")
        existing = {row[1] for row in cursor.fetchall()}

        migrations = {
            "native_language": "ALTER TABLE students ADD COLUMN native_language TEXT DEFAULT 'ru'",
            "interests": "ALTER TABLE students ADD COLUMN interests TEXT DEFAULT '[]'",
            "last_topic": "ALTER TABLE students ADD COLUMN last_topic TEXT DEFAULT ''",
            "completed_topics": "ALTER TABLE students ADD COLUMN completed_topics TEXT DEFAULT '[]'",
            "xp": "ALTER TABLE students ADD COLUMN xp INTEGER DEFAULT 0",
            "streak_days": "ALTER TABLE students ADD COLUMN streak_days INTEGER DEFAULT 0",
            "last_active_date": "ALTER TABLE students ADD COLUMN last_active_date TEXT DEFAULT ''",
            "parent_chat_id": "ALTER TABLE students ADD COLUMN parent_chat_id INTEGER",
        }
        for col, sql in migrations.items():
            if col not in existing:
                conn.execute(sql)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ─── Students ────────────────────────────────────────────────

    def get_or_create_student(self, student_id: int, name: str = "") -> dict:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
            if row:
                if name and not row["name"]:
                    conn.execute(
                        "UPDATE students SET name = ? WHERE student_id = ?",
                        (name, student_id),
                    )
                    conn.commit()
                result = dict(row)
            else:
                conn.execute(
                    "INSERT INTO students (student_id, name) VALUES (?, ?)",
                    (student_id, name),
                )
                conn.commit()
                result = {
                    "student_id": student_id,
                    "name": name,
                    "level": "A1",
                    "level_score": 0.0,
                    "mode": "kids",
                    "native_language": "ru",
                }
            conn.close()
            return result

    def get_student(self, student_id: int) -> dict | None:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
            conn.close()
            return dict(row) if row else None

    def get_all_students(self) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute("SELECT * FROM students").fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def update_student_level(
        self, student_id: int, level: str, level_score: float
    ) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE students SET level = ?, level_score = ? WHERE student_id = ?",
                (level, level_score, student_id),
            )
            conn.commit()
            conn.close()

    def update_student_language(self, student_id: int, lang_code: str) -> None:
        """Set native language: ru, uz, kz, tr."""
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE students SET native_language = ? WHERE student_id = ?",
                (lang_code, student_id),
            )
            conn.commit()
            conn.close()

    # ─── Memory / Personalization ─────────────────────────────────

    def update_student_memory(
        self,
        student_id: int,
        interests: list[str] | None = None,
        last_topic: str | None = None,
    ) -> None:
        """Update personalization data for a student."""
        with self._lock:
            conn = self._connect()
            if interests is not None:
                conn.execute(
                    "UPDATE students SET interests = ? WHERE student_id = ?",
                    (json.dumps(interests, ensure_ascii=False), student_id),
                )
            if last_topic is not None:
                conn.execute(
                    "UPDATE students SET last_topic = ? WHERE student_id = ?",
                    (last_topic, student_id),
                )
            conn.commit()
            conn.close()

    def get_student_memory(self, student_id: int) -> dict:
        """Get personalization context for building system prompt."""
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT name, interests, last_topic, last_session_at FROM students WHERE student_id = ?",
                (student_id,),
            ).fetchone()
            vocab_count = conn.execute(
                "SELECT COUNT(*) as c FROM vocabulary WHERE student_id = ?",
                (student_id,),
            ).fetchone()["c"]
            conn.close()
            if not row:
                return {"name": "", "interests": [], "last_topic": "", "vocab_count": 0, "last_session_at": ""}
            try:
                interests = json.loads(row["interests"] or "[]")
            except (json.JSONDecodeError, TypeError):
                interests = []
            return {
                "name": row["name"] or "",
                "interests": interests,
                "last_topic": row["last_topic"] or "",
                "vocab_count": vocab_count,
                "last_session_at": row["last_session_at"] or "",
            }

    # ─── Topics ───────────────────────────────────────────────────

    def record_completed_topic(self, student_id: int, topic: str, words_count: int = 0) -> None:
        """Add a topic to the student's completed list."""
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT completed_topics FROM students WHERE student_id = ?",
                (student_id,),
            ).fetchone()
            try:
                topics = json.loads(row["completed_topics"] or "[]") if row else []
            except (json.JSONDecodeError, TypeError):
                topics = []
            topics.append({
                "topic": topic,
                "completed_at": datetime.now().isoformat(),
                "words_learned": words_count,
            })
            conn.execute(
                "UPDATE students SET completed_topics = ?, last_topic = ? WHERE student_id = ?",
                (json.dumps(topics, ensure_ascii=False), topic, student_id),
            )
            conn.commit()
            conn.close()

    def get_completed_topics(self, student_id: int) -> list[dict]:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT completed_topics FROM students WHERE student_id = ?",
                (student_id,),
            ).fetchone()
            conn.close()
            if not row:
                return []
            try:
                return json.loads(row["completed_topics"] or "[]")
            except (json.JSONDecodeError, TypeError):
                return []

    # ─── Gamification ─────────────────────────────────────────────

    def add_xp(self, student_id: int, amount: int) -> dict:
        """Add XP and update streak. Returns {xp, streak_days, streak_changed}."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT xp, streak_days, last_active_date FROM students WHERE student_id = ?",
                (student_id,),
            ).fetchone()
            if not row:
                conn.close()
                return {"xp": 0, "streak_days": 0, "streak_changed": False}

            old_xp = row["xp"] or 0
            old_streak = row["streak_days"] or 0
            last_date = row["last_active_date"] or ""
            streak_changed = False

            if last_date != today:
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                if last_date == yesterday:
                    new_streak = old_streak + 1
                    streak_changed = True
                elif last_date == "":
                    new_streak = 1
                    streak_changed = True
                else:
                    new_streak = 1
                    streak_changed = old_streak > 1
            else:
                new_streak = old_streak

            new_xp = old_xp + amount
            conn.execute(
                "UPDATE students SET xp = ?, streak_days = ?, last_active_date = ? WHERE student_id = ?",
                (new_xp, new_streak, today, student_id),
            )
            conn.commit()
            conn.close()
            return {"xp": new_xp, "streak_days": new_streak, "streak_changed": streak_changed}

    def award_badge(self, student_id: int, badge_name: str) -> bool:
        """Award a badge. Returns True if newly awarded, False if already had."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO achievements (student_id, badge_name) VALUES (?, ?)",
                    (student_id, badge_name),
                )
                conn.commit()
                conn.close()
                return True
            except sqlite3.IntegrityError:
                conn.close()
                return False

    def get_badges(self, student_id: int) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT badge_name, earned_at FROM achievements WHERE student_id = ? ORDER BY earned_at DESC",
                (student_id,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_leaderboard(self, limit: int = 10) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT student_id, name, xp, level, streak_days FROM students ORDER BY xp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # ─── Parent ───────────────────────────────────────────────────

    def set_parent(self, student_id: int, parent_chat_id: int) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE students SET parent_chat_id = ? WHERE student_id = ?",
                (parent_chat_id, student_id),
            )
            conn.commit()
            conn.close()

    def get_weekly_stats(self, student_id: int) -> dict:
        """Get stats for the last 7 days."""
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        with self._lock:
            conn = self._connect()
            sessions = conn.execute(
                "SELECT * FROM session_history WHERE student_id = ? AND started_at >= ?",
                (student_id, week_ago),
            ).fetchall()
            new_words = conn.execute(
                "SELECT COUNT(*) as c FROM vocabulary WHERE student_id = ? AND learned_date >= ?",
                (student_id, week_ago),
            ).fetchone()["c"]
            student = conn.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
            grammar = conn.execute(
                "SELECT area, score, error_count FROM grammar_areas WHERE student_id = ? ORDER BY score ASC LIMIT 5",
                (student_id,),
            ).fetchall()
            conn.close()

            total_duration = sum(s["duration_seconds"] or 0 for s in sessions)
            total_messages = sum(s["message_count"] or 0 for s in sessions)

            return {
                "session_count": len(sessions),
                "total_duration": total_duration,
                "total_messages": total_messages,
                "new_words": new_words,
                "level": student["level"] if student else "A1",
                "level_score": student["level_score"] if student else 0,
                "xp": student["xp"] if student else 0,
                "streak": student["streak_days"] if student else 0,
                "weak_grammar": [dict(g) for g in grammar],
                "student_name": student["name"] if student else "",
            }

    # ─── Pronunciation ────────────────────────────────────────────

    def log_pronunciation(
        self, student_id: int, word: str, score: float, problems: list[dict]
    ) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO pronunciation_log (student_id, word, score, problem_sounds) VALUES (?, ?, ?, ?)",
                (student_id, word, score, json.dumps(problems, ensure_ascii=False)),
            )
            conn.commit()
            conn.close()

    def get_pronunciation_stats(self, student_id: int) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                """SELECT word, AVG(score) as avg_score, COUNT(*) as attempts,
                          MAX(recorded_at) as last_attempt
                   FROM pronunciation_log WHERE student_id = ?
                   GROUP BY word ORDER BY avg_score ASC""",
                (student_id,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # ─── Vocabulary ──────────────────────────────────────────────

    def add_vocabulary(self, student_id: int, words: list[dict]) -> None:
        """Add words from analysis. Each dict: {word, translation_ru, level}. Upsert."""
        with self._lock:
            conn = self._connect()
            for w in words:
                conn.execute(
                    """INSERT INTO vocabulary (student_id, word, translation_ru, level)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(student_id, word) DO UPDATE SET
                           translation_ru = COALESCE(NULLIF(excluded.translation_ru, ''), translation_ru),
                           level = COALESCE(NULLIF(excluded.level, ''), level)
                    """,
                    (
                        student_id,
                        w.get("word", "").lower().strip(),
                        w.get("translation_ru", ""),
                        w.get("level", "A1"),
                    ),
                )
            conn.commit()
            conn.close()

    def get_vocabulary(self, student_id: int) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM vocabulary WHERE student_id = ? ORDER BY learned_date DESC",
                (student_id,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def update_word_score(self, student_id: int, word: str, correct: bool) -> None:
        """Update spaced repetition score. Correct: +30%, Incorrect: *0.5."""
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT score, times_tested, times_correct FROM vocabulary WHERE student_id = ? AND word = ? COLLATE NOCASE",
                (student_id, word),
            ).fetchone()
            if row:
                old_score = row["score"]
                if correct:
                    new_score = min(100, old_score + (100 - old_score) * 0.3)
                    conn.execute(
                        """UPDATE vocabulary SET score = ?, times_tested = times_tested + 1,
                           times_correct = times_correct + 1, last_tested = datetime('now')
                           WHERE student_id = ? AND word = ? COLLATE NOCASE""",
                        (new_score, student_id, word),
                    )
                else:
                    new_score = max(0, old_score * 0.5)
                    conn.execute(
                        """UPDATE vocabulary SET score = ?, times_tested = times_tested + 1,
                           last_tested = datetime('now')
                           WHERE student_id = ? AND word = ? COLLATE NOCASE""",
                        (new_score, student_id, word),
                    )
                conn.commit()
            conn.close()

    # ─── Grammar ─────────────────────────────────────────────────

    def record_grammar_error(self, student_id: int, area: str) -> None:
        """Record a grammar error — decrease score for this area."""
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT score, error_count FROM grammar_areas WHERE student_id = ? AND area = ?",
                (student_id, area),
            ).fetchone()
            if row:
                new_score = max(0, row["score"] - 5)
                conn.execute(
                    """UPDATE grammar_areas SET score = ?, error_count = error_count + 1,
                       last_error_at = datetime('now')
                       WHERE student_id = ? AND area = ?""",
                    (new_score, student_id, area),
                )
            else:
                conn.execute(
                    "INSERT INTO grammar_areas (student_id, area, score, error_count, last_error_at) VALUES (?, ?, 45, 1, datetime('now'))",
                    (student_id, area),
                )
            conn.commit()
            conn.close()

    def get_grammar_areas(self, student_id: int) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM grammar_areas WHERE student_id = ? ORDER BY score ASC",
                (student_id,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_weakest_grammar(self, student_id: int, limit: int = 3) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM grammar_areas WHERE student_id = ? ORDER BY score ASC LIMIT ?",
                (student_id, limit),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # ─── Sessions ────────────────────────────────────────────────

    def start_session(self, student_id: int, session_id: str) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO session_history (student_id, session_id) VALUES (?, ?)",
                (student_id, session_id),
            )
            conn.execute(
                "UPDATE students SET last_session_at = datetime('now') WHERE student_id = ?",
                (student_id,),
            )
            conn.commit()
            conn.close()

    def end_session(
        self,
        student_id: int,
        session_id: str,
        duration: float,
        message_count: int,
        words_learned: list,
        errors_summary: list,
        homework_words: list,
        level_before: str = "",
        level_after: str = "",
    ) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                """UPDATE session_history SET
                       ended_at = datetime('now'),
                       duration_seconds = ?,
                       message_count = ?,
                       words_learned = ?,
                       errors_summary = ?,
                       homework = ?,
                       level_before = ?,
                       level_after = ?
                   WHERE student_id = ? AND session_id = ?""",
                (
                    duration,
                    message_count,
                    json.dumps(words_learned, ensure_ascii=False),
                    json.dumps(errors_summary, ensure_ascii=False),
                    json.dumps(homework_words, ensure_ascii=False),
                    level_before,
                    level_after,
                    student_id,
                    session_id,
                ),
            )
            conn.commit()
            conn.close()

    def get_session_history(self, student_id: int, limit: int = 20) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM session_history WHERE student_id = ? ORDER BY started_at DESC LIMIT ?",
                (student_id, limit),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # ─── Homework ────────────────────────────────────────────────

    def assign_homework(self, student_id: int, words: list[dict]) -> None:
        """Assign words as homework. Each dict: {word, translation_ru}."""
        with self._lock:
            conn = self._connect()
            for w in words:
                conn.execute(
                    "INSERT INTO homework (student_id, word, translation_ru) VALUES (?, ?, ?)",
                    (student_id, w.get("word", ""), w.get("translation_ru", "")),
                )
            conn.commit()
            conn.close()

    def get_pending_homework(self, student_id: int) -> list[dict]:
        """Get all vocabulary words that need testing — spaced repetition order."""
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                """SELECT DISTINCT v.word, v.translation_ru, v.score, v.times_tested,
                          v.times_correct, v.level
                   FROM homework h
                   JOIN vocabulary v ON v.student_id = h.student_id
                       AND LOWER(v.word) = LOWER(h.word)
                   WHERE h.student_id = ?
                   ORDER BY v.score ASC, v.times_tested ASC""",
                (student_id,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def mark_homework_tested(
        self, student_id: int, word: str, score: float
    ) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                """UPDATE homework SET tested = 1, test_result = ?
                   WHERE student_id = ? AND LOWER(word) = LOWER(?) AND tested = 0""",
                (score, student_id, word),
            )
            conn.commit()
            conn.close()

    # ─── Stats ───────────────────────────────────────────────────

    def get_student_stats(self, student_id: int) -> dict:
        """Get aggregated stats for a student."""
        with self._lock:
            conn = self._connect()
            vocab_count = conn.execute(
                "SELECT COUNT(*) as c FROM vocabulary WHERE student_id = ?",
                (student_id,),
            ).fetchone()["c"]
            mastered = conn.execute(
                "SELECT COUNT(*) as c FROM vocabulary WHERE student_id = ? AND score >= 80",
                (student_id,),
            ).fetchone()["c"]
            session_count = conn.execute(
                "SELECT COUNT(*) as c FROM session_history WHERE student_id = ?",
                (student_id,),
            ).fetchone()["c"]
            pending_hw = conn.execute(
                "SELECT COUNT(DISTINCT word) as c FROM homework WHERE student_id = ? AND tested = 0",
                (student_id,),
            ).fetchone()["c"]
            conn.close()
            return {
                "vocabulary_total": vocab_count,
                "vocabulary_mastered": mastered,
                "session_count": session_count,
                "pending_homework": pending_hw,
            }
