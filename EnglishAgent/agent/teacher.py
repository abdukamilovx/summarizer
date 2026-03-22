import json
import logging
import time
import uuid
from typing import Callable

from openai import OpenAI

from agent.prompts import (
    ANALYSIS_PROMPT,
    ANALYSIS_PROMPT_TEMPLATE,
    AUTO_LEVEL_PROMPT,
    LANGUAGE_MAP,
    LEVEL_DIFFICULTY,
    MEMORY_EXTRACT_PROMPT,
    MEMORY_SUFFIX,
    PROMPTS,
    TIMER_WARNING,
    TIMER_WRAPUP,
    WEAK_AREAS_SUFFIX,
    TeacherMode,
)

logger = logging.getLogger(__name__)


class EnglishTeacher:
    LESSON_DURATION = 15 * 60   # 15 minutes
    WARNING_TIME = 12 * 60     # warn at 12 min
    WRAPUP_TIME = 14 * 60      # wrap up at 14 min

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        mode: TeacherMode = TeacherMode.KIDS,
        on_event: Callable | None = None,
        student_id: int | None = None,
        storage=None,
        native_language: str = "ru",
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.mode = mode
        self._on_event = on_event
        self.student_id = student_id
        self.storage = storage
        self.native_language = native_language
        self.session_id: str = str(uuid.uuid4())
        self._lesson_start: float | None = None
        self._warned = False
        self._wrapping_up = False
        self._lesson_ended = False
        self._session_words: list[dict] = []
        self._session_errors: list[dict] = []
        self._last_analysis: dict | None = None
        self._message_count = 0

        # Auto-level detection
        self._auto_level_messages: list[str] = []
        self._detected_level: str | None = None
        self._auto_detect_threshold = 5

        # Topic-based lessons
        self.topic: str | None = None
        self._topic_prompt: str | None = None

        # Image context
        self.image_context: str | None = None

        self.history: list[dict] = [
            {"role": "system", "content": self._build_system_prompt()}
        ]

    @property
    def _lang_name(self) -> str:
        return LANGUAGE_MAP.get(self.native_language, "Russian")

    def _build_system_prompt(self) -> str:
        """Build system prompt with memory, weak areas, topic, and level."""
        # Select base prompt
        if self.mode == TeacherMode.AUTO and self._detected_level:
            # Use Kids for A1-A2, Adult for B1+
            if self._detected_level in ("A1", "A2"):
                base = PROMPTS[TeacherMode.KIDS]
            else:
                base = PROMPTS[TeacherMode.ADULT]
            base += "\n\n" + LEVEL_DIFFICULTY.get(self._detected_level, "")
        else:
            base = PROMPTS[self.mode]

        # Append memory context
        if self.storage and self.student_id:
            try:
                memory = self.storage.get_student_memory(self.student_id)
                if memory.get("name") or memory.get("last_topic"):
                    interests_str = ", ".join(memory.get("interests", [])) or "not yet known"
                    base += MEMORY_SUFFIX.format(
                        name=memory.get("name", ""),
                        vocab_count=memory.get("vocab_count", 0),
                        last_topic=memory.get("last_topic", "") or "none yet",
                        interests=interests_str,
                        last_session_at=memory.get("last_session_at", "") or "first session",
                    )
            except Exception:
                pass

        # Append weak grammar areas
        if self.storage and self.student_id:
            try:
                weak = self.storage.get_weakest_grammar(self.student_id, limit=3)
                if weak:
                    areas_text = "\n".join(
                        f"- {w['area']} (score: {w['score']}/100, errors: {w['error_count']})"
                        for w in weak
                    )
                    base += WEAK_AREAS_SUFFIX.format(areas=areas_text)
            except Exception:
                pass

        # Append topic instructions
        if self._topic_prompt:
            base += "\n\n" + self._topic_prompt

        # Append image context
        if self.image_context:
            base += "\n\n" + self.image_context

        return base

    def set_mode(self, mode: TeacherMode):
        """Switch mode and reset conversation."""
        self.mode = mode
        self._detected_level = None
        self.reset()

    def set_topic(self, topic: str, topic_prompt: str):
        """Set topic for this lesson."""
        self.topic = topic
        self._topic_prompt = topic_prompt

    def chat(self, user_message: str) -> str:
        # Check timer first
        timer_action = self._check_timer()
        if self._lesson_ended:
            return self._end_lesson_summary()

        # Inject timer warnings into system context
        if timer_action == "warn" and not self._warned:
            self._warned = True
            self.history.append({"role": "system", "content": TIMER_WARNING})
        elif timer_action == "wrapup" and not self._wrapping_up:
            self._wrapping_up = True
            self.history.append({"role": "system", "content": TIMER_WRAPUP})

        self.history.append({"role": "user", "content": user_message})
        self._message_count += 1

        # Auto-level detection: collect first N user messages
        if (
            self.mode == TeacherMode.AUTO
            and self._detected_level is None
            and self._message_count <= self._auto_detect_threshold
        ):
            self._auto_level_messages.append(user_message)
            if self._message_count == self._auto_detect_threshold:
                self._auto_detect_level()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.history,
            max_tokens=300,
            temperature=0.8,
        )

        assistant_message = response.choices[0].message.content
        self.history.append({"role": "assistant", "content": assistant_message})

        # Analyze the exchange
        analysis = self._analyze_exchange(user_message, assistant_message)
        self._last_analysis = analysis

        # Persist to storage
        self._persist_analysis(analysis)

        # Emit event for analytics
        if self._on_event:
            try:
                self._on_event({
                    "type": "message",
                    "session_id": self.session_id,
                    "mode": self.mode.value,
                    "user": user_message,
                    "assistant": assistant_message,
                    "analysis": analysis,
                    "timestamp": time.time(),
                })
            except Exception:
                pass

        # Check if timer hit 15 min after this exchange
        if self._check_timer() == "end":
            self._lesson_ended = True
            summary = self._end_lesson_summary()
            assistant_message += "\n\n" + summary

        return assistant_message

    def _auto_detect_level(self):
        """Detect student's CEFR level from their first messages."""
        messages_text = "\n".join(
            f"- \"{m}\"" for m in self._auto_level_messages
        )
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": AUTO_LEVEL_PROMPT.format(messages=messages_text),
                    }
                ],
                max_tokens=200,
                temperature=0.2,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
            result = json.loads(raw)
            level = result.get("estimated_level", "A1")
            if level in LEVEL_DIFFICULTY:
                self._detected_level = level
                # Rebuild system prompt with detected level
                self.history[0] = {
                    "role": "system",
                    "content": self._build_system_prompt(),
                }
                # Update storage
                if self.storage and self.student_id:
                    self.storage.update_student_level(
                        self.student_id, level, 0.0
                    )
                logger.info(f"Auto-detected level for {self.student_id}: {level}")
        except Exception as e:
            logger.error(f"Auto-level detection failed: {e}")
            self._detected_level = "A2"  # fallback

    def _check_timer(self) -> str | None:
        """Check lesson timer. Returns 'warn', 'wrapup', 'end', or None."""
        if self._lesson_start is None:
            return None
        elapsed = time.time() - self._lesson_start
        if elapsed >= self.LESSON_DURATION:
            return "end"
        if elapsed >= self.WRAPUP_TIME:
            return "wrapup"
        if elapsed >= self.WARNING_TIME:
            return "warn"
        return None

    def _persist_analysis(self, analysis: dict):
        """Save vocabulary and grammar errors to storage."""
        if not self.storage or not self.student_id:
            return
        try:
            vocab = analysis.get("vocabulary_used", [])
            if vocab:
                self.storage.add_vocabulary(self.student_id, vocab)
                self._session_words.extend(vocab)

            errors = analysis.get("errors", [])
            if errors:
                self._session_errors.extend(errors)
                for err in errors:
                    category = err.get("grammar_category", "other")
                    if category:
                        self.storage.record_grammar_error(self.student_id, category)
        except Exception:
            pass

    def _end_lesson_summary(self) -> str:
        """Generate end-of-lesson summary, assign homework, extract memory."""
        # Build word list for homework
        word_list = []
        seen = set()
        for w in self._session_words:
            word = w.get("word", "").lower().strip()
            if word and word not in seen:
                seen.add(word)
                word_list.append(w)

        # Assign homework
        if self.storage and self.student_id and word_list:
            try:
                self.storage.assign_homework(self.student_id, word_list)
            except Exception:
                pass

        # Save session
        duration = 0
        if self._lesson_start:
            duration = time.time() - self._lesson_start
        if self.storage and self.student_id:
            try:
                error_categories = list({
                    e.get("grammar_category", "other")
                    for e in self._session_errors
                })
                self.storage.end_session(
                    student_id=self.student_id,
                    session_id=self.session_id,
                    duration=duration,
                    message_count=self._message_count,
                    words_learned=[w.get("word", "") for w in word_list],
                    errors_summary=error_categories,
                    homework_words=[w.get("word", "") for w in word_list],
                )
            except Exception:
                pass

            # Add XP for lesson completion
            try:
                self.storage.add_xp(self.student_id, 50)
                for _ in word_list:
                    self.storage.add_xp(self.student_id, 5)
            except Exception:
                pass

            # Record completed topic
            if self.topic:
                try:
                    self.storage.record_completed_topic(
                        self.student_id, self.topic, len(word_list)
                    )
                except Exception:
                    pass

            # Extract memory (topic, interests) from conversation
            self._extract_and_save_memory()

        # Format summary
        lines = ["📋 Lesson Complete!"]
        lines.append(f"⏱ Duration: {int(duration // 60)} minutes")
        lines.append(f"💬 Messages: {self._message_count}")

        if word_list:
            lines.append("\n📝 Homework — learn these words:")
            for w in word_list:
                tr = w.get("translation_ru", "")
                lines.append(f"  • {w['word']} — {tr}")
            lines.append("\nI'll quiz you on these next time!")

        if self._session_errors:
            categories = list({e.get("grammar_category", "other") for e in self._session_errors})
            lines.append(f"\n⚠ Areas to practice: {', '.join(categories)}")

        return "\n".join(lines)

    def _extract_and_save_memory(self):
        """Extract topic and interests from conversation history and save."""
        if not self.storage or not self.student_id:
            return
        try:
            # Build conversation text from history (skip system messages)
            conv_parts = []
            for msg in self.history:
                if msg["role"] == "user":
                    conv_parts.append(f"Student: {msg['content']}")
                elif msg["role"] == "assistant":
                    conv_parts.append(f"Teacher: {msg['content']}")
            conversation = "\n".join(conv_parts[-10:])  # last 10 messages

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": MEMORY_EXTRACT_PROMPT.format(conversation=conversation),
                    }
                ],
                max_tokens=150,
                temperature=0.2,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
            result = json.loads(raw)

            topic = result.get("topic", "")
            interests = result.get("interests", [])

            if topic or interests:
                self.storage.update_student_memory(
                    self.student_id,
                    interests=interests if interests else None,
                    last_topic=topic if topic else None,
                )
        except Exception as e:
            logger.debug(f"Memory extraction failed: {e}")

    def _analyze_exchange(self, user_message: str, assistant_message: str) -> dict:
        """Analyze student's message for errors, complex words, alternatives."""
        try:
            # Use language-specific analysis prompt
            analysis_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
                native_language_name=self._lang_name
            )

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": analysis_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Student ({self.mode.value} mode) said: \"{user_message}\"\n"
                            f"Teacher responded: \"{assistant_message}\""
                        ),
                    },
                ],
                max_tokens=500,
                temperature=0.2,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
            return json.loads(raw)
        except Exception:
            return {
                "errors": [],
                "complex_words": [],
                "alternative_phrases": [],
                "vocabulary_used": [],
            }

    def start_lesson(self) -> str:
        """Start a new lesson — agent sends the first greeting."""
        self._lesson_start = time.time()
        if self.storage and self.student_id:
            try:
                self.storage.start_session(self.student_id, self.session_id)
            except Exception:
                pass
        return self.chat("Hello! Let's start our English lesson!")

    def reset(self):
        """Reset conversation history for a new lesson."""
        self.session_id = str(uuid.uuid4())
        self._lesson_start = None
        self._warned = False
        self._wrapping_up = False
        self._lesson_ended = False
        self._session_words = []
        self._session_errors = []
        self._last_analysis = None
        self._message_count = 0
        self._auto_level_messages = []
        self._detected_level = None
        self.topic = None
        self._topic_prompt = None
        self.image_context = None
        self.history = [
            {"role": "system", "content": self._build_system_prompt()}
        ]

    @property
    def time_remaining(self) -> int | None:
        """Seconds remaining in lesson, or None if timer not started."""
        if self._lesson_start is None:
            return None
        remaining = self.LESSON_DURATION - (time.time() - self._lesson_start)
        return max(0, int(remaining))
