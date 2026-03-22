"""Telegram Voice Bot for English Teacher.

Can run standalone: python telegram_bot.py
Or integrated into server.py for shared analytics.
"""

import datetime
import io
import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agent.analytics import AnalyticsHub
from agent.level_assessor import LevelAssessor
from agent.prompts import THEORY_PROMPT, TeacherMode
from agent.quiz import VocabularyQuiz
from agent.storage import StudentStorage
from agent.teacher import EnglishTeacher

load_dotenv()
logger = logging.getLogger(__name__)

API_KEY = os.getenv("OPENAI_API_KEY", "")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

analytics = AnalyticsHub()
storage: StudentStorage | None = None

openai_client = OpenAI(api_key=API_KEY)


# ─── Session Management ─────────────────────────────────────────


@dataclass
class StudentSession:
    teacher: EnglishTeacher
    quiz: VocabularyQuiz | None = None
    state: str = "idle"  # "idle", "quiz", "lesson", "ended"


sessions: dict[int, StudentSession] = {}


def get_session(chat_id: int, name: str = "") -> StudentSession:
    """Get or create a student session."""
    if chat_id not in sessions:
        if storage:
            storage.get_or_create_student(chat_id, name)
        teacher = EnglishTeacher(
            api_key=API_KEY,
            student_id=chat_id,
            storage=storage,
            on_event=lambda e: analytics.handle_event({**e, "source": "telegram"}),
        )
        sessions[chat_id] = StudentSession(teacher=teacher)
    return sessions[chat_id]


def text_to_speech(text: str) -> bytes:
    """Convert text to speech. Returns OGG/Opus bytes."""
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text,
        response_format="opus",
    )
    return response.content


def format_vocab_footer(analysis: dict) -> str:
    """Format complex words and new vocabulary as a footer."""
    lines = []
    complex_words = analysis.get("complex_words", [])
    vocab = analysis.get("vocabulary_used", [])
    if complex_words:
        lines.append("📚 *Complex words:*")
        for w in complex_words:
            lines.append(f"  • *{w.get('word', '')}* — {w.get('translation_ru', '')}")
    if vocab:
        lines.append("🆕 *New vocabulary:*")
        for v in vocab:
            lines.append(
                f"  • *{v.get('word', '')}* — {v.get('translation_ru', '')} [{v.get('level', '')}]"
            )
    return "\n".join(lines) if lines else ""


# ─── Command Handlers ────────────────────────────────────────────


async def start_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /start — quiz if homework pending, then lesson."""
    chat_id = update.effective_chat.id
    name = update.effective_user.first_name or ""
    session = get_session(chat_id, name)

    await update.message.reply_text(
        "Welcome to English Teacher Bot! 🎓\n\n"
        "Commands:\n"
        "/start — Start lesson (quiz first if homework pending)\n"
        "/quiz — Manual vocabulary quiz\n"
        "/level — Your current level\n"
        "/vocab — Vocabulary stats\n"
        "/homework — Pending homework\n"
        "/mode — Switch Kids/Adult\n"
        "/reset — Reset lesson\n\n"
        f"Mode: {session.teacher.mode.value.capitalize()}"
    )

    # Check if quiz needed
    if storage:
        quiz = VocabularyQuiz(storage, chat_id, API_KEY)
        if quiz.should_quiz():
            session.quiz = quiz
            session.state = "quiz"
            first_question = quiz.start()
            await update.message.reply_text(
                "📝 Before we start, let's review your vocabulary!\n\n" + first_question
            )
            return

    # Start lesson directly
    session.state = "lesson"
    session.teacher.reset()
    greeting = session.teacher.start_lesson()
    await _send_teacher_response(update, session.teacher, greeting)


async def quiz_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /quiz — manual vocabulary quiz."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)

    if not storage:
        await update.message.reply_text("Storage not available.")
        return

    quiz = VocabularyQuiz(storage, chat_id, API_KEY)
    if not quiz.should_quiz():
        await update.message.reply_text(
            "No words to quiz yet! Complete a lesson first to get homework."
        )
        return

    session.quiz = quiz
    session.state = "quiz"
    first_question = quiz.start()
    await update.message.reply_text(first_question)


async def level_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /level — show current level and progress."""
    chat_id = update.effective_chat.id
    if not storage:
        await update.message.reply_text("Storage not available.")
        return

    get_session(chat_id, update.effective_user.first_name or "")
    assessor = LevelAssessor(storage)
    report = assessor.format_report(chat_id)
    await update.message.reply_text(report)


async def vocab_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /vocab — show vocabulary stats."""
    chat_id = update.effective_chat.id
    if not storage:
        await update.message.reply_text("Storage not available.")
        return

    get_session(chat_id)
    stats = storage.get_student_stats(chat_id)
    vocab = storage.get_vocabulary(chat_id)

    lines = [
        f"📖 Vocabulary Stats",
        f"Total words: {stats['vocabulary_total']}",
        f"Mastered (80%+): {stats['vocabulary_mastered']}",
        f"Sessions: {stats['session_count']}",
        f"Pending homework: {stats['pending_homework']} words",
    ]

    if vocab:
        lines.append("\n📋 Recent words:")
        for w in vocab[:15]:
            score_bar = "█" * int(w["score"] / 10) + "░" * (10 - int(w["score"] / 10))
            lines.append(
                f"  {w['word']} — {w['translation_ru']} [{score_bar}] {w['score']:.0f}%"
            )

    await update.message.reply_text("\n".join(lines))


async def homework_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /homework — show pending homework."""
    chat_id = update.effective_chat.id
    if not storage:
        await update.message.reply_text("Storage not available.")
        return

    get_session(chat_id)
    words = storage.get_pending_homework(chat_id)

    if not words:
        await update.message.reply_text("No pending homework! Start a lesson with /start.")
        return

    lines = ["📝 Homework — words to study:"]
    for w in words:
        lines.append(f"  • {w['word']} — {w.get('translation_ru', '')} (score: {w['score']:.0f}%)")
    lines.append(f"\nTotal: {len(words)} words. Use /quiz to test yourself!")
    await update.message.reply_text("\n".join(lines))


async def mode_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /mode — toggle between kids and adult."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    if session.teacher.mode == TeacherMode.KIDS:
        session.teacher.set_mode(TeacherMode.ADULT)
        await update.message.reply_text("Switched to Adult mode. 🎯\nUse /start to begin.")
    else:
        session.teacher.set_mode(TeacherMode.KIDS)
        await update.message.reply_text("Switched to Kids mode. 🧒\nUse /start to begin.")


async def reset_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /reset — start a fresh lesson."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    session.state = "lesson"
    session.quiz = None
    session.teacher.reset()
    greeting = session.teacher.start_lesson()
    await _send_teacher_response(update, session.teacher, greeting)


# ─── Message Handlers ────────────────────────────────────────────


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle incoming voice messages."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)

    voice = update.message.voice
    file = await ctx.bot.get_file(voice.file_id)
    voice_data = await file.download_as_bytearray()

    audio_file = io.BytesIO(bytes(voice_data))
    audio_file.name = "voice.ogg"

    try:
        transcription = openai_client.audio.transcriptions.create(
            model="whisper-1", file=audio_file, language="en",
        )
        user_text = transcription.text.strip()
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        await update.message.reply_text("Sorry, I couldn't understand. Please try again.")
        return

    if not user_text:
        await update.message.reply_text("I couldn't hear anything. Please try again.")
        return

    await update.message.reply_text(f"🎙 You said: _{user_text}_", parse_mode="Markdown")
    await _process_student_message(update, session, user_text)


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    await _process_student_message(update, session, update.message.text)


async def _process_student_message(
    update: Update, session: StudentSession, text: str
):
    """Route message based on session state."""

    # Quiz mode
    if session.state == "quiz" and session.quiz and session.quiz.active:
        feedback, done = session.quiz.check_answer(text)
        await update.message.reply_text(feedback)

        if done:
            session.state = "idle"
            session.quiz = None

            # Assess level after quiz
            if storage:
                assessor = LevelAssessor(storage)
                result = assessor.assess(update.effective_chat.id)
                await update.message.reply_text(
                    f"📊 Your level: {result['level']} ({result['score']:.0f}/100)\n\n"
                    f"Ready for today's lesson? Starting now!"
                )

            # Auto-start lesson
            session.state = "lesson"
            session.teacher.reset()
            greeting = session.teacher.start_lesson()
            await _send_teacher_response(update, session.teacher, greeting)
        return

    # Auto-start lesson if idle
    if session.state not in ("lesson",):
        session.state = "lesson"
        if session.teacher._lesson_start is None:
            session.teacher.reset()
            session.teacher.start_lesson()

    # Lesson ended
    if session.teacher._lesson_ended:
        await update.message.reply_text(
            "The lesson has ended! Use /start to begin a new one."
        )
        return

    try:
        response_text = session.teacher.chat(text)
    except Exception as e:
        logger.error(f"GPT error: {e}")
        response_text = "I'm sorry, something went wrong. Please try again."

    await _send_teacher_response(update, session.teacher, response_text)

    # Level assessment after lesson ends
    if session.teacher._lesson_ended and storage:
        session.state = "ended"
        assessor = LevelAssessor(storage)
        result = assessor.assess(update.effective_chat.id)
        await update.message.reply_text(
            f"\n📊 Level: {result['level']} ({result['score']:.0f}/100)"
            f"\nProgress to {result.get('next_level', 'max')}: {result['progress_to_next']}%"
        )


async def _send_teacher_response(
    update: Update, teacher: EnglishTeacher, response_text: str
):
    """Send teacher's text + voice + vocabulary translations."""
    remaining = teacher.time_remaining
    timer_text = ""
    if remaining is not None and remaining < 180:
        timer_text = f"\n⏱ {remaining // 60}:{remaining % 60:02d} remaining"

    await update.message.reply_text(response_text + timer_text)

    try:
        voice_response = text_to_speech(response_text)
        await update.message.reply_voice(voice=io.BytesIO(voice_response))
    except Exception as e:
        logger.error(f"TTS error: {e}")

    analysis = teacher._last_analysis
    if analysis:
        footer = format_vocab_footer(analysis)
        if footer:
            try:
                await update.message.reply_text(
                    f"───────────────\n{footer}", parse_mode="Markdown"
                )
            except Exception:
                await update.message.reply_text(footer.replace("*", ""))


# ─── Daily Theory Push ───────────────────────────────────────────


async def setup_daily_theory(app):
    """Schedule daily grammar theory push at 14:00."""
    app.job_queue.run_daily(
        send_daily_theory,
        time=datetime.time(hour=14, minute=0),
        name="daily_theory",
    )
    logger.info("Daily theory push scheduled at 14:00")


async def send_daily_theory(context: ContextTypes.DEFAULT_TYPE):
    """Send grammar mini-lessons to all students based on weaknesses."""
    if not storage:
        return

    all_students = storage.get_all_students()
    for student in all_students:
        student_id = student["student_id"]
        weak_areas = storage.get_weakest_grammar(student_id, limit=1)
        if not weak_areas:
            continue

        area = weak_areas[0]["area"]
        level = student.get("level", "A1")

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": THEORY_PROMPT.format(area=area, level=level),
                    },
                    {"role": "user", "content": f"Create a mini-lesson about {area}"},
                ],
                max_tokens=300,
                temperature=0.7,
            )
            theory_text = response.choices[0].message.content.strip()

            await context.bot.send_message(
                chat_id=student_id,
                text=f"📘 Daily Grammar Tip\n\n"
                f"Topic: {area.replace('_', ' ').title()}\n\n"
                f"{theory_text}",
            )
            logger.info(f"Sent daily theory to {student_id}: {area}")
        except Exception as e:
            logger.error(f"Failed to send theory to {student_id}: {e}")


# ─── Bot Setup ───────────────────────────────────────────────────


def create_bot_app(
    token: str | None = None,
    hub: AnalyticsHub | None = None,
    db_storage: StudentStorage | None = None,
):
    """Create the Telegram bot Application."""
    global analytics, storage
    if hub is not None:
        analytics = hub
    if db_storage is not None:
        storage = db_storage

    bot_token = token or BOT_TOKEN
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    app = (
        ApplicationBuilder()
        .token(bot_token)
        .post_init(setup_daily_theory)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("level", level_command))
    app.add_handler(CommandHandler("vocab", vocab_command))
    app.add_handler(CommandHandler("homework", homework_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


def main():
    """Run the bot standalone."""
    global storage
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN is not set in .env")
        return

    storage = StudentStorage()
    storage.initialize()

    print("Starting Telegram bot...")
    app = create_bot_app(db_storage=storage)
    app.run_polling()


if __name__ == "__main__":
    main()
