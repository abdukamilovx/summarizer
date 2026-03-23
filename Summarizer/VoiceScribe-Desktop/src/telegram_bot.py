"""
VoiceScribe Telegram Bot.

Receives voice messages → transcribes → translates via GPT → sends back.
Accumulates session transcript. "📊 Анализ" button triggers full analysis.

Usage:
    python telegram_bot.py
    # or from main.py: bot runs in a background thread alongside the desktop UI
"""
import asyncio
import io
import tempfile
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from utils.config import settings
from utils.logger import log

# ── Lazy singletons ──────────────────────────────────────────────────────────

_whisper = None
_summarizer = None
_uzbek = None


def _get_whisper():
    global _whisper
    if _whisper is None:
        from transcription.whisper_api import WhisperAPITranscriber
        _whisper = WhisperAPITranscriber()
    return _whisper


def _get_summarizer():
    global _summarizer
    if _summarizer is None:
        from analysis.summarizer import Summarizer
        _summarizer = Summarizer()
    return _summarizer


def _get_uzbek():
    global _uzbek
    if _uzbek is None:
        from transcription.uzbek_stt import UzbekTranscriber
        _uzbek = UzbekTranscriber(device="auto")
        _uzbek.load_model()
    return _uzbek


# ── Per-user session store ───────────────────────────────────────────────────

_sessions: dict[int, dict] = {}


def _get_session(user_id: int) -> dict:
    if user_id not in _sessions:
        _sessions[user_id] = {
            "language": "auto",  # auto / en / ru / uz / ...
            "transcript_parts": [],  # list of transcribed chunks
            "translation_parts": [],  # list of translated chunks
        }
    return _sessions[user_id]


# ── Languages ────────────────────────────────────────────────────────────────

_LANG_MAP = {
    "auto": None, "en": "en", "ru": "ru", "uz": "uz",
    "zh": "zh", "ja": "ja", "ko": "ko", "de": "de",
    "fr": "fr", "es": "es", "tr": "tr", "ar": "ar",
}

_LOCAL_ONLY_LANGS = {"uz"}  # Whisper API doesn't support these


# ── GPT translation ─────────────────────────────────────────────────────────

def _translate_gpt(text: str, src_lang: str = "auto") -> str:
    """Translate text to Russian using GPT-4o-mini."""
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    lang_hint = ""
    if src_lang == "uz":
        lang_hint = " Исходный текст на узбекском языке (латиница)."
    elif src_lang == "en":
        lang_hint = " Исходный текст на английском."

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты профессиональный переводчик. Переводи на русский язык."
                    f"{lang_hint}"
                    " Верни ТОЛЬКО перевод, без пояснений."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.2,
        max_tokens=2000,
    )
    return (resp.choices[0].message.content or "").strip()


# ── Transcription ────────────────────────────────────────────────────────────

def _transcribe_audio(audio_bytes: bytes, lang: str) -> str:
    """Transcribe audio bytes. Uses local model for Uzbek, Whisper API otherwise."""
    # Convert OGG/OGA to WAV numpy
    audio_np, sr = sf.read(io.BytesIO(audio_bytes))
    if audio_np.ndim > 1:
        audio_np = audio_np.mean(axis=1)
    audio_np = audio_np.astype(np.float32)

    # Resample to 16kHz if needed
    if sr != 16000:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(16000, sr)
        audio_np = resample_poly(audio_np, 16000 // g, sr // g).astype(np.float32)

    # Uzbek → local model
    if lang == "uz":
        uz = _get_uzbek()
        if uz.is_ready:
            result = uz.transcribe_numpy(audio_np, sample_rate=16000)
            return result.text.strip()

    # All other languages → Whisper API
    whisper = _get_whisper()
    api_lang = lang if lang not in _LOCAL_ONLY_LANGS and lang != "auto" else None
    result = whisper.transcribe_numpy(audio_np, sample_rate=16000, language=api_lang)
    return result.text.strip()


# ── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context):
    user = update.effective_user
    session = _get_session(user.id)
    session["transcript_parts"].clear()
    session["translation_parts"].clear()

    keyboard = [
        [
            InlineKeyboardButton("🇺🇿 UZ", callback_data="lang_uz"),
            InlineKeyboardButton("🇷🇺 RU", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 EN", callback_data="lang_en"),
            InlineKeyboardButton("🔄 Auto", callback_data="lang_auto"),
        ],
        [
            InlineKeyboardButton("📊 Анализ", callback_data="analysis"),
            InlineKeyboardButton("🗑 Очистить", callback_data="clear"),
        ],
    ]
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Отправь мне **голосовое сообщение** — я расшифрую и переведу.\n\n"
        "🔤 Язык: **Auto** (определю автоматически)\n"
        "📊 После всех сообщений нажми **Анализ** для полного разбора.\n\n"
        "Выбери язык записи:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def cmd_lang(update: Update, context):
    """Set language via /lang uz|ru|en|auto"""
    user = update.effective_user
    session = _get_session(user.id)
    args = context.args
    if args and args[0].lower() in _LANG_MAP:
        session["language"] = args[0].lower()
        await update.message.reply_text(f"✅ Язык установлен: **{args[0].upper()}**", parse_mode="Markdown")
    else:
        await update.message.reply_text("Использование: /lang uz | ru | en | auto")


async def handle_voice(update: Update, context):
    """Process incoming voice message."""
    user = update.effective_user
    session = _get_session(user.id)
    lang = session["language"]

    # Show "typing" indicator
    await update.message.chat.send_action("typing")

    # Download voice file
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    file = await context.bot.get_file(voice.file_id)
    audio_bytes = await file.download_as_bytearray()

    # Transcribe in thread pool (blocking operation)
    loop = asyncio.get_event_loop()
    transcript = await loop.run_in_executor(
        None, _transcribe_audio, bytes(audio_bytes), lang,
    )

    if not transcript:
        await update.message.reply_text("🔇 Не удалось распознать речь.")
        return

    # Translate via GPT
    await update.message.chat.send_action("typing")
    translation = await loop.run_in_executor(
        None, _translate_gpt, transcript, lang,
    )

    # Save to session
    session["transcript_parts"].append(transcript)
    session["translation_parts"].append(translation)

    # Build response
    msg_num = len(session["transcript_parts"])
    response = (
        f"🎤 **#{msg_num}**\n\n"
        f"📝 {transcript}\n\n"
        f"🇷🇺 {translation}"
    )

    # Add analysis button
    keyboard = [[
        InlineKeyboardButton("📊 Анализ", callback_data="analysis"),
        InlineKeyboardButton("🗑 Очистить", callback_data="clear"),
    ]]

    await update.message.reply_text(
        response,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def handle_callback(update: Update, context):
    """Handle inline button presses."""
    query = update.callback_query
    user = query.from_user
    session = _get_session(user.id)
    data = query.data

    await query.answer()

    # ── Language selection ──
    if data.startswith("lang_"):
        lang = data.replace("lang_", "")
        session["language"] = lang
        lang_names = {"uz": "🇺🇿 Узбекский", "ru": "🇷🇺 Русский", "en": "🇬🇧 Английский", "auto": "🔄 Авто"}
        await query.edit_message_text(
            f"✅ Язык: **{lang_names.get(lang, lang)}**\n\n"
            "Отправь голосовое сообщение 🎙",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🇺🇿 UZ", callback_data="lang_uz"),
                InlineKeyboardButton("🇷🇺 RU", callback_data="lang_ru"),
                InlineKeyboardButton("🇬🇧 EN", callback_data="lang_en"),
                InlineKeyboardButton("🔄 Auto", callback_data="lang_auto"),
            ], [
                InlineKeyboardButton("📊 Анализ", callback_data="analysis"),
                InlineKeyboardButton("🗑 Очистить", callback_data="clear"),
            ]]),
        )
        return

    # ── Analysis ──
    if data == "analysis":
        if not session["transcript_parts"]:
            await query.edit_message_text("⚠️ Нет записей для анализа. Отправь голосовые сообщения.")
            return

        # Notify user
        await query.edit_message_text("⏳ Выполняю анализ... (это займёт ~30 сек)")

        full_transcript = "\n".join(session["transcript_parts"])
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, _get_summarizer().full_analysis, full_transcript,
        )

        # Format analysis
        parts = []

        # Protocol (Meeting Minutes) — first, most important
        protocol = result.get("protocol", "")
        if protocol:
            parts.append(f"📝 **ПРОТОКОЛ СОВЕЩАНИЯ:**\n\n{protocol}")

        # Summary
        summary = result.get("summary", "")
        if summary:
            parts.append(f"📋 **Резюме:**\n{summary}")

        # Key points
        key_points = result.get("key_points", [])
        if key_points:
            pts = "\n".join(f"• {p}" for p in key_points[:10])
            parts.append(f"📌 **Ключевые моменты:**\n{pts}")

        # Action items
        actions = result.get("action_items", [])
        if actions:
            acts = "\n".join(
                f"{'🔴' if a.get('priority')=='high' else '🟡' if a.get('priority')=='medium' else '🟢'} "
                f"{a.get('task', '')}"
                + (f" → {a.get('assignee')}" if a.get('assignee') else "")
                for a in actions[:10]
            )
            parts.append(f"✅ **Задачи:**\n{acts}")

        # Translation
        translation = result.get("translation", "")
        if translation:
            parts.append(f"🌐 **Перевод:**\n{translation}")

        # Dialogue
        dialogue = result.get("dialogue", "")
        if dialogue:
            parts.append(f"💬 **Диалог:**\n{dialogue}")

        analysis_text = "\n\n".join(parts)

        # Telegram has 4096 char limit — split if needed
        keyboard = [[
            InlineKeyboardButton("🗑 Очистить сессию", callback_data="clear"),
        ]]

        if len(analysis_text) <= 4000:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=analysis_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            # Split into chunks
            chunks = _split_message(analysis_text, 4000)
            for i, chunk in enumerate(chunks):
                rm = InlineKeyboardMarkup(keyboard) if i == len(chunks) - 1 else None
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=chunk,
                    parse_mode="Markdown",
                    reply_markup=rm,
                )
        return

    # ── Clear session ──
    if data == "clear":
        count = len(session["transcript_parts"])
        session["transcript_parts"].clear()
        session["translation_parts"].clear()
        await query.edit_message_text(
            f"🗑 Сессия очищена ({count} записей удалено).\n"
            "Отправь новое голосовое сообщение 🎙",
        )
        return


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split text into chunks respecting paragraph boundaries."""
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)
    return chunks


# ── Bot runner ───────────────────────────────────────────────────────────────

def run_bot():
    """Start the Telegram bot (blocking). Call from main thread or background thread."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return

    log.info("Starting Telegram bot...")

    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("lang", cmd_lang))

    # Voice messages
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    # Inline buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    log.info("Telegram bot running. Send /start to your bot.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


def run_bot_background():
    """Start bot in a background thread (non-blocking). For use alongside desktop UI."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        log.info("TELEGRAM_BOT_TOKEN not set — Telegram bot not started")
        return None

    thread = threading.Thread(target=run_bot, daemon=True, name="TelegramBot")
    thread.start()
    log.info("Telegram bot started in background thread")
    return thread


# ── Standalone entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    run_bot()
