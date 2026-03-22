"""Analytics hub for tracking teaching sessions in real-time.

Collects events from EnglishTeacher instances and broadcasts
to WebSocket subscribers (dashboard clients).
"""

import asyncio
import threading
import time
from dataclasses import dataclass, field


@dataclass
class SessionMetrics:
    session_id: str
    source: str = "unknown"  # "desktop", "twilio", "telegram"
    mode: str = "kids"
    start_time: float = field(default_factory=time.time)
    messages: list[dict] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if not self.messages:
            return 0
        return self.messages[-1]["timestamp"] - self.start_time

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def user_word_count(self) -> int:
        return sum(len(m.get("user", "").split()) for m in self.messages)

    @property
    def assistant_word_count(self) -> int:
        return sum(len(m.get("assistant", "").split()) for m in self.messages)

    @property
    def total_errors(self) -> int:
        return sum(
            len(m.get("analysis", {}).get("errors", []))
            for m in self.messages
        )

    @property
    def all_vocabulary(self) -> list[dict]:
        """All vocabulary words introduced across the session."""
        vocab = []
        for m in self.messages:
            vocab.extend(m.get("analysis", {}).get("vocabulary_used", []))
        return vocab

    @property
    def all_complex_words(self) -> list[dict]:
        """All complex words used by teacher across the session."""
        words = []
        for m in self.messages:
            words.extend(m.get("analysis", {}).get("complex_words", []))
        return words

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "source": self.source,
            "mode": self.mode,
            "duration": round(self.duration_seconds, 1),
            "message_count": self.message_count,
            "user_word_count": self.user_word_count,
            "assistant_word_count": self.assistant_word_count,
            "total_errors": self.total_errors,
            "messages": self.messages,
            "start_time": self.start_time,
            "all_vocabulary": self.all_vocabulary,
            "all_complex_words": self.all_complex_words,
        }


class AnalyticsHub:
    """Central analytics collector.

    Thread-safe for sync callers (EnglishTeacher.chat runs in threads),
    broadcasts to async WebSocket subscribers via asyncio.Queue.
    """

    def __init__(self):
        self.sessions: dict[str, SessionMetrics] = {}
        self._subscribers: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the asyncio event loop for broadcasting."""
        self._loop = loop

    def handle_event(self, event: dict):
        """Called from any thread — the on_event callback for EnglishTeacher."""
        with self._lock:
            sid = event.get("session_id", "unknown")
            if sid not in self.sessions:
                self.sessions[sid] = SessionMetrics(
                    session_id=sid,
                    source=event.get("source", "unknown"),
                    mode=event.get("mode", "kids"),
                )
            session = self.sessions[sid]
            session.messages.append(event)

        # Broadcast to WebSocket subscribers
        payload = {
            "type": "live_update",
            "session": session.to_dict(),
            "latest_event": {
                "user": event.get("user", ""),
                "assistant": event.get("assistant", ""),
                "analysis": event.get("analysis", {}),
                "timestamp": event.get("timestamp", time.time()),
            },
        }
        self._broadcast(payload)

    def _broadcast(self, payload: dict):
        if self._loop is None:
            return
        for q in list(self._subscribers):
            try:
                self._loop.call_soon_threadsafe(q.put_nowait, payload)
            except Exception:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def get_all_sessions(self) -> list[dict]:
        with self._lock:
            return [s.to_dict() for s in self.sessions.values()]
