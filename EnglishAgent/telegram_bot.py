"""Telegram Voice Bot for English Teacher.

Can run standalone: python telegram_bot.py
Or integrated into server.py for shared analytics.
"""

import datetime
import io
import json
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
from agent.gamification import BADGES, check_badges, format_new_badges_message
from agent.image_lessons import generate_lesson_image, get_image_question
from agent.level_assessor import LevelAssessor
from agent.prompts import LANGUAGE_MAP, PRONUNCIATION_PROMPT, THEORY_PROMPT, TeacherMode
from agent.quiz import VocabularyQuiz
from agent.reports import generate_weekly_report
from agent.storage import StudentStorage
from agent.teacher import EnglishTeacher
from agent.topics import TOPICS, get_topic_prompt, list_topics

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
        native_lang = "ru"
        if storage:
            student = storage.get_or_create_student(chat_id, name)
            native_lang = student.get("native_language", "ru")
        teacher = EnglishTeacher(
            api_key=API_KEY,
            student_id=chat_id,
            storage=storage,
            native_language=native_lang,
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
        "/level — Your current level & stats\n"
        "/vocab — Vocabulary stats\n"
        "/homework — Pending homework\n"
        "/mode — Switch Kids/Adult/Auto\n"
        "/topic — Choose a lesson topic\n"
        "/picture — Get a picture to discuss\n"
        "/lang — Change native language\n"
        "/parent — Link parent for reports\n"
        "/leaderboard — Top students by XP\n"
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
    """Handle /level — show current level, XP, streak, and badges."""
    chat_id = update.effective_chat.id
    if not storage:
        await update.message.reply_text("Storage not available.")
        return

    get_session(chat_id, update.effective_user.first_name or "")
    assessor = LevelAssessor(storage)
    report = assessor.format_report(chat_id)

    # Add gamification info
    student = storage.get_student(chat_id)
    if student:
        xp = student.get("xp", 0)
        streak = student.get("streak_days", 0)
        report += f"\n\n⭐ XP: {xp}"
        if streak > 0:
            report += f"\n🔥 Streak: {streak} days"

    badges = storage.get_badges(chat_id)
    if badges:
        badge_strs = []
        for b in badges:
            info = BADGES.get(b["badge_name"], {})
            badge_strs.append(f"{info.get('emoji', '🏅')} {info.get('name', b['badge_name'])}")
        report += f"\n\n🏆 Badges: {' | '.join(badge_strs)}"

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
    """Handle /mode — cycle through Kids → Adult → Auto."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    mode_cycle = {
        TeacherMode.KIDS: TeacherMode.ADULT,
        TeacherMode.ADULT: TeacherMode.AUTO,
        TeacherMode.AUTO: TeacherMode.KIDS,
    }
    new_mode = mode_cycle.get(session.teacher.mode, TeacherMode.KIDS)
    session.teacher.set_mode(new_mode)

    mode_desc = {
        TeacherMode.KIDS: "Kids mode 🧒 — simple vocabulary, playful style",
        TeacherMode.ADULT: "Adult mode 🎯 — professional, advanced vocabulary",
        TeacherMode.AUTO: "Auto mode 🤖 — level detected from your messages",
    }
    await update.message.reply_text(
        f"Switched to {mode_desc[new_mode]}\nUse /start to begin."
    )


async def topic_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /topic — choose a lesson topic."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    args = update.message.text.split(maxsplit=1)

    if len(args) < 2:
        topics = list_topics()
        completed = set()
        if storage:
            ct = storage.get_completed_topics(chat_id)
            completed = {t["topic"] for t in ct}

        lines = ["📚 Available topics:\n"]
        for t in topics:
            check = "✅" if t["key"] in completed else "  "
            lines.append(f"{check} {t['emoji']} {t['name']} — /topic {t['key']}")
        lines.append(f"\n{len(completed)}/{len(topics)} completed")
        await update.message.reply_text("\n".join(lines))
        return

    topic_key = args[1].strip().lower()
    if topic_key not in TOPICS:
        await update.message.reply_text(
            f"Topic '{topic_key}' not found. Use /topic to see available topics."
        )
        return

    level = "A2"
    if storage:
        student = storage.get_student(chat_id)
        if student:
            level = student.get("level", "A2")

    topic_prompt = get_topic_prompt(topic_key, level)
    session.state = "lesson"
    session.teacher.reset()
    session.teacher.set_topic(topic_key, topic_prompt)

    topic_info = TOPICS[topic_key]
    greeting = session.teacher.start_lesson()
    await update.message.reply_text(
        f"{topic_info['emoji']} Starting lesson: *{topic_info['name']}*",
        parse_mode="Markdown",
    )
    await _send_teacher_response(update, session.teacher, greeting)


async def picture_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /picture — send a DALL-E image and ask questions."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    args = update.message.text.split(maxsplit=1)

    topic = args[1].strip().lower() if len(args) > 1 else None
    if not topic:
        topic = session.teacher.topic or "animals"

    await update.message.reply_text("🎨 Generating a picture for you...")

    image_url = generate_lesson_image(openai_client, topic)
    if not image_url:
        await update.message.reply_text(
            "Sorry, I couldn't generate an image right now. Let's continue with words!"
        )
        return

    question = get_image_question(topic)
    await update.message.reply_photo(photo=image_url)
    await update.message.reply_text(question)

    session.teacher.image_context = (
        f"IMAGE CONTEXT: You just showed the student a picture about {topic}. "
        f"The student will describe what they see. Discuss the image, "
        f"ask follow-up questions about what they see, and teach new vocabulary "
        f"related to the image."
    )

    if session.state != "lesson":
        session.state = "lesson"
        if session.teacher._lesson_start is None:
            session.teacher.reset()
            session.teacher.start_lesson()


async def lang_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /lang — change native language for translations."""
    chat_id = update.effective_chat.id
    args = update.message.text.split(maxsplit=1)

    if len(args) < 2:
        langs = "\n".join(
            f"  /lang {code} — {name}" for code, name in LANGUAGE_MAP.items()
        )
        await update.message.reply_text(f"🌐 Available languages:\n\n{langs}")
        return

    lang_code = args[1].strip().lower()
    if lang_code not in LANGUAGE_MAP:
        await update.message.reply_text(
            f"Unknown language '{lang_code}'. Available: {', '.join(LANGUAGE_MAP.keys())}"
        )
        return

    if storage:
        storage.update_student_language(chat_id, lang_code)
    if chat_id in sessions:
        sessions[chat_id].teacher.native_language = lang_code

    lang_name = LANGUAGE_MAP[lang_code]
    await update.message.reply_text(
        f"✅ Language set to *{lang_name}*. Translations will now be in {lang_name}.",
        parse_mode="Markdown",
    )


async def parent_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /parent — link parent's chat for weekly reports."""
    chat_id = update.effective_chat.id
    args = update.message.text.split(maxsplit=1)

    if len(args) < 2:
        await update.message.reply_text(
            "👨‍👩‍👧 To link a parent, the parent should message this bot first, "
            "then send their chat ID here.\n\n"
            "Parent: send /myid to get your chat ID.\n"
            "Student: /parent <parent_chat_id>"
        )
        return

    try:
        parent_id = int(args[1].strip())
    except ValueError:
        await update.message.reply_text("Please provide a valid chat ID number.")
        return

    if storage:
        storage.set_parent(chat_id, parent_id)
        await update.message.reply_text(
            f"✅ Parent linked! Weekly reports will be sent to chat {parent_id} every Sunday."
        )
        try:
            name = update.effective_user.first_name or "Student"
            await ctx.bot.send_message(
                chat_id=parent_id,
                text=f"📊 You've been linked as a parent for {name}.\n"
                f"You'll receive weekly progress reports every Sunday at 18:00.",
            )
        except Exception:
            await update.message.reply_text(
                "⚠ Couldn't send confirmation to parent. Make sure they've started this bot."
            )


async def myid_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /myid — show user's chat ID (for parent linking)."""
    await update.message.reply_text(
        f"Your chat ID: `{update.effective_chat.id}`", parse_mode="Markdown"
    )


async def leaderboard_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /leaderboard — show top students by XP."""
    if not storage:
        await update.message.reply_text("Storage not available.")
        return

    leaders = storage.get_leaderboard(limit=10)
    if not leaders:
        await update.message.reply_text("No students yet! Be the first to start a lesson.")
        return

    lines = ["🏆 Leaderboard — Top Students by XP\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, l in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = l.get("name") or f"Student #{l['student_id']}"
        streak_icon = f" 🔥{l.get('streak_days', 0)}" if l.get("streak_days", 0) > 0 else ""
        lines.append(
            f"{medal} {name} — {l.get('xp', 0)} XP [{l.get('level', 'A1')}]{streak_icon}"
        )

    await update.message.reply_text("\n".join(lines))


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
    """Handle incoming voice messages with pronunciation scoring."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)

    voice = update.message.voice
    file = await ctx.bot.get_file(voice.file_id)
    voice_data = await file.download_as_bytearray()

    audio_file = io.BytesIO(bytes(voice_data))
    audio_file.name = "voice.ogg"

    try:
        transcription = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )
        user_text = transcription.text.strip()
        word_data = getattr(transcription, "words", None)
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        await update.message.reply_text("Sorry, I couldn't understand. Please try again.")
        return

    if not user_text:
        await update.message.reply_text("I couldn't hear anything. Please try again.")
        return

    await update.message.reply_text(f"🎙 You said: _{user_text}_", parse_mode="Markdown")

    # Pronunciation analysis
    if word_data and storage:
        try:
            await _analyze_pronunciation(update, chat_id, session, user_text, word_data)
        except Exception as e:
            logger.debug(f"Pronunciation analysis failed: {e}")

    await _process_student_message(update, session, user_text)


async def _analyze_pronunciation(update, chat_id, session, text, word_data):
    """Analyze pronunciation and send feedback."""
    lang_name = LANGUAGE_MAP.get(session.teacher.native_language, "Russian")

    words_info = []
    for w in word_data:
        words_info.append({
            "word": w.word if hasattr(w, "word") else str(w),
            "start": getattr(w, "start", 0),
            "end": getattr(w, "end", 0),
        })

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": PRONUNCIATION_PROMPT.format(
                    native_language_name=lang_name,
                    text=text,
                    word_data=str(words_info),
                ),
            }],
            max_tokens=200,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        result = json.loads(raw)
        score = result.get("overall_score", 0)
        problems = result.get("problem_sounds", [])
        feedback = result.get("feedback", "")

        pron_lines = [f"🗣 Pronunciation: {score}%"]
        if feedback:
            pron_lines.append(feedback)
        for p in problems[:3]:
            pron_lines.append(
                f"  💡 '{p.get('sound', '')}' in "
                f"{', '.join(p.get('words', []))}: {p.get('tip', '')}"
            )
        await update.message.reply_text("\n".join(pron_lines))

        if storage:
            storage.log_pronunciation(chat_id, text[:50], score, problems)
    except Exception as e:
        logger.debug(f"Pronunciation GPT analysis failed: {e}")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    await _process_student_message(update, session, update.message.text)


async def _process_student_message(update, session, text):
    """Route message based on session state."""
    chat_id = update.effective_chat.id

    # Quiz mode
    if session.state == "quiz" and session.quiz and session.quiz.active:
        feedback, done = session.quiz.check_answer(text)
        await update.message.reply_text(feedback)

        if done:
            session.state = "idle"
            session.quiz = None

            if storage:
                assessor = LevelAssessor(storage)
                result = assessor.assess(chat_id)
                await update.message.reply_text(
                    f"📊 Your level: {result['level']} ({result['score']:.0f}/100)\n\n"
                    f"Ready for today's lesson? Starting now!"
                )
                new_badges = check_badges(storage, chat_id)
                if new_badges:
                    msg = format_new_badges_message(new_badges)
                    await update.message.reply_text(msg, parse_mode="Markdown")

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

    if session.teacher._lesson_ended:
        await update.message.reply_text("The lesson has ended! Use /start to begin a new one.")
        return

    try:
        response_text = session.teacher.chat(text)
    except Exception as e:
        logger.error(f"GPT error: {e}")
        response_text = "I'm sorry, something went wrong. Please try again."

    await _send_teacher_response(update, session.teacher, response_text)

    # Auto-level notification
    if (
        session.teacher.mode == TeacherMode.AUTO
        and session.teacher._detected_level
        and session.teacher._message_count == session.teacher._auto_detect_threshold
    ):
        await update.message.reply_text(
            f"🎯 I've detected your level as *{session.teacher._detected_level}*! "
            f"Adjusting difficulty accordingly.",
            parse_mode="Markdown",
        )

    # Level assessment + badges after lesson ends
    if session.teacher._lesson_ended and storage:
        session.state = "ended"
        assessor = LevelAssessor(storage)
        result = assessor.assess(chat_id)
        await update.message.reply_text(
            f"\n📊 Level: {result['level']} ({result['score']:.0f}/100)"
            f"\nProgress to {result.get('next_level', 'max')}: {result['progress_to_next']}%"
        )
        new_badges = check_badges(storage, chat_id)
        if new_badges:
            msg = format_new_badges_message(new_badges)
            await update.message.reply_text(msg, parse_mode="Markdown")


async def _send_teacher_response(update, teacher, response_text):
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


# ─── Daily Theory Push & Weekly Reports ──────────────────────────


async def setup_daily_theory(app):
    """Schedule daily grammar theory at 14:00 and weekly reports Sunday 18:00."""
    app.job_queue.run_daily(
        send_daily_theory,
        time=datetime.time(hour=14, minute=0),
        name="daily_theory",
    )
    app.job_queue.run_daily(
        send_weekly_reports,
        time=datetime.time(hour=18, minute=0),
        days=(6,),  # Sunday
        name="weekly_reports",
    )
    logger.info("Scheduled: daily theory at 14:00, weekly reports Sunday 18:00")


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
                    {"role": "system", "content": THEORY_PROMPT.format(area=area, level=level)},
                    {"role": "user", "content": f"Create a mini-lesson about {area}"},
                ],
                max_tokens=300, temperature=0.7,
            )
            theory_text = response.choices[0].message.content.strip()
            await context.bot.send_message(
                chat_id=student_id,
                text=f"📘 Daily Grammar Tip\n\nTopic: {area.replace('_', ' ').title()}\n\n{theory_text}",
            )
            logger.info(f"Sent daily theory to {student_id}: {area}")
        except Exception as e:
            logger.error(f"Failed to send theory to {student_id}: {e}")


async def send_weekly_reports(context: ContextTypes.DEFAULT_TYPE):
    """Send weekly progress reports to parents."""
    if not storage:
        return
    all_students = storage.get_all_students()
    for student in all_students:
        parent_id = student.get("parent_chat_id")
        if not parent_id:
            continue
        try:
            report = generate_weekly_report(storage, student["student_id"])
            await context.bot.send_message(chat_id=parent_id, text=report)
            logger.info(f"Sent weekly report for {student['student_id']} to parent {parent_id}")
        except Exception as e:
            logger.error(f"Failed to send report to parent {parent_id}: {e}")


# ─── Bot Setup ───────────────────────────────────────────────────


def create_bot_app(token=None, hub=None, db_storage=None):
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
    app.add_handler(CommandHandler("topic", topic_command))
    app.add_handler(CommandHandler("picture", picture_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("parent", parent_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
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
