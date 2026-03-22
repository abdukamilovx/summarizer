"""FastAPI server with Twilio, Telegram bot, and Analytics dashboard.

Run: python server.py
- Twilio: expose with ngrok, set webhook to /incoming-call
- Telegram: set TELEGRAM_BOT_TOKEN in .env
- Dashboard: open http://localhost:8000/dashboard/
"""

import asyncio
import base64
import io
import json
import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from agent.analytics import AnalyticsHub
from agent.storage import StudentStorage
from agent.teacher import EnglishTeacher
from audio_utils import (
    detect_silence,
    mulaw_to_pcm_bytes,
    pcm_bytes_to_wav,
    wav_to_mulaw_base64,
)
from dashboard.routes import router as dashboard_router
import dashboard.routes as dashboard_routes

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="English Teacher Phone Agent")

API_KEY = os.getenv("OPENAI_API_KEY", "")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

SILENCE_THRESHOLD = 500
SILENCE_DURATION = 1.5
MIN_AUDIO_BYTES = 8000

# ─── Analytics & Storage ─────────────────────────────────────────────

analytics = AnalyticsHub()
storage = StudentStorage(db_path="data/english_agent.db")

# ─── Dashboard ───────────────────────────────────────────────────────

app.include_router(dashboard_router)


# ─── Lifecycle ───────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize storage, analytics, and optionally start Telegram bot."""
    storage.initialize()
    logger.info("Database initialized")

    loop = asyncio.get_running_loop()
    analytics.set_loop(loop)
    dashboard_routes.analytics_hub = analytics
    dashboard_routes.storage = storage

    # Start Telegram bot if token is set
    if BOT_TOKEN:
        asyncio.create_task(_start_telegram_bot())
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")


async def _start_telegram_bot():
    """Start the Telegram bot in the background (shares analytics hub)."""
    try:
        from telegram_bot import create_bot_app
        bot_app = create_bot_app(token=BOT_TOKEN, hub=analytics, db_storage=storage)

        # Initialize and start polling without blocking
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling()

        logger.info("Telegram bot started (polling)")
    except ImportError:
        logger.warning("python-telegram-bot not installed — Telegram bot disabled")
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")


@app.on_event("shutdown")
async def shutdown():
    """Clean up Telegram bot on shutdown."""
    # Telegram bot cleanup is handled automatically


# ─── Twilio: Voice Webhook ───────────────────────────────────────────

@app.post("/incoming-call")
async def incoming_call(request: Request):
    """Twilio Voice webhook — returns TwiML to start a Media Stream."""
    host = request.headers.get("host", "localhost:8000")
    protocol = "wss" if request.url.scheme == "https" else "ws"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Hello! Connecting you to your English teacher. One moment please.</Say>
    <Connect>
        <Stream url="{protocol}://{host}/media-stream" />
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


# ─── Twilio: Media Stream WebSocket ─────────────────────────────────

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """Handle Twilio Media Stream WebSocket connection."""
    await websocket.accept()

    teacher = EnglishTeacher(
        api_key=API_KEY,
        storage=storage,
        on_event=lambda e: analytics.handle_event({**e, "source": "twilio"}),
    )
    stream_sid = None
    audio_buffer = bytearray()
    processing = False

    greeting = teacher.start_lesson()

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                stream_sid = data["start"]["streamSid"]
                logger.info(f"[Twilio] Stream started: {stream_sid}")
                await _send_speech(websocket, stream_sid, greeting)

            elif event == "media":
                if processing:
                    continue

                payload = base64.b64decode(data["media"]["payload"])
                pcm = mulaw_to_pcm_bytes(payload)
                audio_buffer.extend(pcm)

                if len(audio_buffer) > MIN_AUDIO_BYTES and detect_silence(
                    bytes(audio_buffer),
                    threshold=SILENCE_THRESHOLD,
                    silence_duration=SILENCE_DURATION,
                ):
                    processing = True
                    buffer_copy = bytes(audio_buffer)
                    audio_buffer.clear()

                    asyncio.create_task(
                        _process_utterance(
                            websocket, stream_sid, teacher, buffer_copy
                        )
                    )
                    processing = False

            elif event == "stop":
                logger.info("[Twilio] Stream stopped")
                break

    except WebSocketDisconnect:
        logger.info("[Twilio] Client disconnected")
    except Exception as e:
        logger.error(f"[Twilio] WebSocket error: {e}")


async def _process_utterance(
    websocket: WebSocket,
    stream_sid: str,
    teacher: EnglishTeacher,
    pcm_data: bytes,
):
    """Transcribe audio, get teacher response, and send back speech."""
    from openai import OpenAI

    client = OpenAI(api_key=API_KEY)

    wav_data = pcm_bytes_to_wav(pcm_data, sample_rate=8000)
    audio_file = io.BytesIO(wav_data)
    audio_file.name = "audio.wav"

    try:
        transcription = client.audio.transcriptions.create(
            model="whisper-1", file=audio_file, language="en",
        )
        user_text = transcription.text.strip()
    except Exception as e:
        logger.error(f"[Whisper error] {e}")
        return

    if not user_text:
        return

    logger.info(f"[Student said] {user_text}")

    try:
        response_text = teacher.chat(user_text)
    except Exception as e:
        logger.error(f"[GPT error] {e}")
        response_text = "I'm sorry, can you say that again?"

    logger.info(f"[Teacher says] {response_text}")
    await _send_speech(websocket, stream_sid, response_text)


async def _send_speech(websocket: WebSocket, stream_sid: str, text: str):
    """Convert text to speech and send via Twilio Media Stream."""
    from openai import OpenAI

    client = OpenAI(api_key=API_KEY)

    try:
        tts_response = client.audio.speech.create(
            model="tts-1", voice="nova", input=text, response_format="wav",
        )

        mulaw_b64 = wav_to_mulaw_base64(tts_response.content, target_rate=8000)

        chunk_size = 32000
        for i in range(0, len(mulaw_b64), chunk_size):
            chunk = mulaw_b64[i : i + chunk_size]
            media_message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": chunk},
            }
            await websocket.send_text(json.dumps(media_message))

    except Exception as e:
        logger.error(f"[TTS/Send error] {e}")


# ─── Health Check ────────────────────────────────────────────────────

@app.get("/")
async def health():
    return {
        "status": "running",
        "telegram": "enabled" if BOT_TOKEN else "disabled",
        "dashboard": "/dashboard/",
        "twilio_webhook": "/incoming-call",
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    uvicorn.run(app, host="0.0.0.0", port=8000)
