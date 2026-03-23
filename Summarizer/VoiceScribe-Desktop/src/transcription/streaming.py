"""
Streaming transcriber — multi-panel architecture.

Design (Timekettle-style):
1. Panel 1: 1-sec audio -> Whisper -> INSTANT raw text (<1s latency)
2. Panel 2: Each raw chunk -> translate immediately (sync with Panel 1)
3. Panel 3: Every 5 chunks -> re-transcribe + GPT compare + speaker labels
4. Panel 4: Corrected text -> translate (sync with Panel 3)
"""
import numpy as np
import threading
import queue
from typing import Callable, Optional

from openai import OpenAI

from transcription.whisper_api import WhisperAPITranscriber
from transcription.engine import TranscriptionResult, TranscriptionSegment
from audio.preprocessor import enhance_speech
from utils.config import settings
from utils.logger import log

# Lazy import for Uzbek local model
_uzbek_transcriber = None


class StreamingTranscriber:
    """Multi-panel streaming transcriber.

    Callbacks:
    - on_raw_text(text, speaker): Panel 1 — instant raw transcription
    - on_raw_translation(text): Panel 2 — instant translation of raw text
    - on_corrected(text, speaker): Panel 3 — AI-corrected text with speakers
    - on_corrected_translation(text): Panel 4 — translation of corrected text
    """

    def __init__(
        self,
        transcriber: WhisperAPITranscriber,
        sample_rate: int = 16000,
        fast_interval: float = 1.0,
        group_size: int = 5,
        # Panel callbacks
        on_raw_text: Optional[Callable] = None,
        on_raw_translation: Optional[Callable] = None,
        on_corrected: Optional[Callable] = None,
        on_corrected_translation: Optional[Callable] = None,
        # Settings
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        translate_to_russian: bool = False,
        noise_reduction: bool = True,
        corrector=None,
        live_correction: bool = True,
        local_translator=None,
    ):
        self._transcriber = transcriber
        self._sample_rate = sample_rate
        self._fast_interval = fast_interval
        self._group_size = group_size

        # Panel callbacks
        self._on_raw_text = on_raw_text
        self._on_raw_translation = on_raw_translation
        self._on_corrected = on_corrected
        self._on_corrected_translation = on_corrected_translation

        self._language = language
        self._prompt = prompt
        self._translate = translate_to_russian
        self._noise_reduction = noise_reduction
        self._corrector = corrector
        self._live_correction = live_correction
        self._local_translator = local_translator

        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._is_running = False
        self._thread: Optional[threading.Thread] = None

        # Block tracking
        self._block_counter = 0
        self._group_audio: list[np.ndarray] = []
        self._group_texts: list[str] = []
        self._group_speakers: list[Optional[str]] = []
        self._group_block_start = 0

        # Accumulated results
        self._all_segments: list[TranscriptionSegment] = []
        self._time_offset: float = 0.0

        # OpenAI client (lazy)
        self._openai: Optional[OpenAI] = None

        # Uzbek local model (lazy, shared across instances)
        self._uzbek_transcriber = None
        if self._language == "uz" or (self._prompt and "uz" in str(self._prompt).lower()):
            self._init_uzbek_model()

    def _init_uzbek_model(self):
        """Initialize local Uzbek Whisper model in background."""
        def load():
            global _uzbek_transcriber
            if _uzbek_transcriber is not None:
                self._uzbek_transcriber = _uzbek_transcriber
                return
            try:
                from transcription.uzbek_stt import UzbekTranscriber
                uz = UzbekTranscriber(device="auto")
                uz.load_model()
                if uz.is_ready:
                    _uzbek_transcriber = uz
                    self._uzbek_transcriber = uz
                    log.info("Uzbek local model ready for streaming")
                else:
                    log.warning("Uzbek local model failed to load, using Whisper API")
            except Exception as e:
                log.warning(f"Uzbek model init error: {e}")
        threading.Thread(target=load, daemon=True).start()

    # Languages NOT supported by OpenAI Whisper API — must use local models
    _LOCAL_ONLY_LANGS = {"uz"}

    def _transcribe_audio(self, audio: np.ndarray) -> TranscriptionResult:
        """Transcribe audio using appropriate engine (Uzbek local or Whisper API)."""
        is_local_only = self._language in self._LOCAL_ONLY_LANGS

        # Use local Uzbek model if available and language matches
        if self._uzbek_transcriber and self._uzbek_transcriber.is_ready:
            if self._language == "uz" or self._language is None:
                result = self._uzbek_transcriber.transcribe_numpy(
                    audio, sample_rate=self._sample_rate,
                )
                if result.text.strip():
                    return result
                # If empty and not local-only, fall through to Whisper API
                if is_local_only:
                    return result

        # If language is local-only but model not ready yet — skip chunk
        if is_local_only and (not self._uzbek_transcriber or not self._uzbek_transcriber.is_ready):
            log.debug("Waiting for local model to load, skipping chunk...")
            return TranscriptionResult(text="", segments=[], language=self._language or "", duration=0.0)

        # Default: Whisper API (don't pass unsupported languages)
        api_language = self._language if self._language not in self._LOCAL_ONLY_LANGS else None
        return self._transcriber.transcribe_numpy(
            audio, sample_rate=self._sample_rate,
            language=api_language, prompt=self._prompt,
        )

    def start(self):
        self._is_running = True
        self._all_segments.clear()
        self._time_offset = 0.0
        self._block_counter = 0
        self._group_audio.clear()
        self._group_texts.clear()
        self._group_speakers.clear()
        self._group_block_start = 0
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        log.info(
            f"Streaming started (fast={self._fast_interval}s, group={self._group_size}, "
            f"translate={self._translate}, correction={self._live_correction})"
        )

    def stop(self) -> TranscriptionResult:
        """Stop and return final combined result."""
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=30.0)
            self._thread = None

        # Process remaining audio in queue
        remaining = self._drain_queue()
        if len(remaining) > self._sample_rate * 0.3:
            self._process_fast_chunk(remaining)

        # Process remaining group (sync)
        if self._group_texts:
            self._process_group_sync()

        full_text = " ".join(seg.text for seg in self._all_segments)
        log.info(f"Streaming stopped. Segments: {len(self._all_segments)}")

        return TranscriptionResult(
            text=full_text,
            segments=self._all_segments,
            language=self._all_segments[0].language if self._all_segments else "",
            duration=self._time_offset,
        )

    def add_audio(self, audio: np.ndarray):
        if self._is_running:
            self._audio_queue.put(audio)

    # -- Main loop --

    def _process_loop(self):
        buffer = np.array([], dtype=np.float32)
        chunk_samples = int(self._fast_interval * self._sample_rate)

        while self._is_running:
            try:
                audio = self._audio_queue.get(timeout=0.2)
                buffer = np.concatenate([buffer, audio])

                while len(buffer) >= chunk_samples:
                    chunk = buffer[:chunk_samples]
                    buffer = buffer[chunk_samples:]
                    self._process_fast_chunk(chunk)

            except queue.Empty:
                continue

        # Put remaining buffer back for stop() to process
        if len(buffer) > 0:
            self._audio_queue.put(buffer)

    def _drain_queue(self) -> np.ndarray:
        parts = []
        while not self._audio_queue.empty():
            try:
                parts.append(self._audio_queue.get_nowait())
            except queue.Empty:
                break
        return np.concatenate(parts) if parts else np.array([], dtype=np.float32)

    # Known Whisper hallucinations on silence/quiet audio
    _HALLUCINATIONS = {
        "you", "you.", "bye", "bye.", "bye!", "bye-bye", "bye-bye.",
        "thank you", "thank you.", "thanks", "thanks.",
        "oh", "oh.", "ah", "ah.", "uh", "uh.", "i", "and", "the",
        "thanks for watching", "thanks for watching!",
        "thanks for watching.", "thank you for watching",
        "thank you for watching!", "see you next time",
        "subscribe", "like and subscribe",
        "bye bye", "bye bye!", "goodbye", "goodbye.",
    }

    # Minimum RMS energy to consider audio as speech (not silence)
    # Low threshold to allow system audio (typically quieter than mic)
    _MIN_SPEECH_RMS = 0.001

    # -- Fast path: Panel 1 + Panel 2 --

    def _process_fast_chunk(self, audio: np.ndarray):
        """Transcribe chunk -> Panel 1 (instant) + Panel 2 (translation)."""
        try:
            # Skip silent audio — prevents Whisper hallucinations
            rms = float(np.sqrt(np.mean(audio ** 2)))
            if rms < self._MIN_SPEECH_RMS:
                self._group_audio.append(audio)
                self._time_offset += len(audio) / self._sample_rate
                log.debug(f"Skipped silent chunk (rms={rms:.5f})")
                return

            processed = audio
            if self._noise_reduction:
                processed = enhance_speech(
                    audio, self._sample_rate,
                    enable_bandpass=True, enable_noise_reduction=True,
                )

            result = self._transcribe_audio(processed)

            if not result.text.strip():
                self._group_audio.append(audio)
                self._time_offset += len(audio) / self._sample_rate
                return

            text = result.text.strip()

            # Filter Whisper hallucinations
            text_clean = text.lower().strip(".,!? ")
            if text_clean in self._HALLUCINATIONS:
                log.debug(f"Filtered hallucination: '{text}'")
                self._group_audio.append(audio)
                self._time_offset += len(audio) / self._sample_rate
                return

            # Filter repetition loops ("word word word word...")
            if self._is_repetition_loop(text):
                log.debug(f"Filtered repetition loop: '{text[:50]}'")
                self._group_audio.append(audio)
                self._time_offset += len(audio) / self._sample_rate
                return

            speaker = (
                result.segments[0].speaker
                if result.segments and result.segments[0].speaker
                else None
            )

            # === PANEL 1: INSTANT RAW TEXT ===
            block_index = self._block_counter
            self._block_counter += 1
            if self._on_raw_text:
                self._on_raw_text(text, speaker)

            # === PANEL 2: INSTANT TRANSLATION (async, non-blocking) ===
            if self._translate and self._on_raw_translation:
                threading.Thread(
                    target=self._do_raw_translate,
                    args=(text,),
                    daemon=True,
                ).start()

            # Accumulate segments
            for seg in result.segments:
                seg.start += self._time_offset
                seg.end += self._time_offset
                self._all_segments.append(seg)

            # Accumulate for group (Panel 3 + 4)
            self._group_audio.append(audio)
            self._group_texts.append(text)
            self._group_speakers.append(speaker)

            # Feed corrector
            if self._corrector and text:
                prefix = f"[{speaker}]: " if speaker else ""
                self._corrector.add_chunk(f"{prefix}{text}")

            self._time_offset += len(audio) / self._sample_rate
            log.info(f"Fast [{block_index}]: '{text[:50]}' t={self._time_offset:.1f}s")

            # === CHECK GROUP READY (Panel 3 + 4) ===
            if len(self._group_texts) >= self._group_size:
                self._launch_group_processing(block_index, speaker)

        except Exception as e:
            log.error(f"Fast chunk error: {e}")
            self._time_offset += len(audio) / self._sample_rate

    def _do_raw_translate(self, text: str):
        """Translate raw chunk for Panel 2."""
        try:
            translated = self._translate_text(text)
            if translated and self._on_raw_translation:
                self._on_raw_translation(translated)
        except Exception as e:
            log.error(f"Raw translation error: {e}")

    # -- Slow path: Panel 3 + Panel 4 --

    def _launch_group_processing(self, last_block_index: int, fallback_speaker):
        group_audio = np.concatenate(self._group_audio)
        group_texts = list(self._group_texts)
        group_speakers = list(self._group_speakers)

        # Reset group for next batch
        self._group_audio.clear()
        self._group_texts.clear()
        self._group_speakers.clear()
        self._group_block_start = self._block_counter

        if self._live_correction:
            threading.Thread(
                target=self._process_group,
                args=(group_audio, group_texts, group_speakers),
                daemon=True,
            ).start()
        elif self._translate:
            # No correction, just translate the combined text
            combined = " ".join(group_texts)
            speaker = next((s for s in group_speakers if s), None)
            threading.Thread(
                target=self._translate_group,
                args=(combined, speaker),
                daemon=True,
            ).start()

    def _process_group(self, audio, instant_texts, speakers):
        """Re-transcribe + GPT compare -> Panel 3, translate -> Panel 4."""
        try:
            # 1. Re-transcribe combined audio
            processed = audio
            if self._noise_reduction:
                processed = enhance_speech(
                    audio, self._sample_rate,
                    enable_bandpass=True, enable_noise_reduction=True,
                )

            result = self._transcribe_audio(processed)
            retranscription = result.text.strip()

            if not retranscription:
                return

            instant_combined = " ".join(instant_texts)
            speaker = next((s for s in speakers if s), None)

            log.info(
                f"Group re-transcription: '{retranscription[:60]}' "
                f"(instant: '{instant_combined[:60]}')"
            )

            # 2. Compare
            if instant_combined.strip() == retranscription.strip():
                corrected = instant_combined
                log.debug("Group: identical, no correction needed")
            else:
                corrected = self._gpt_compare(instant_combined, retranscription)
                if not corrected:
                    corrected = instant_combined
                if corrected != instant_combined:
                    log.info(f"Group corrected: '{corrected[:60]}'")

            # === PANEL 3: CORRECTED TEXT ===
            if self._on_corrected:
                log.info(f"-> Panel 3: '{corrected[:60]}'")
                self._on_corrected(corrected, speaker)

            # === PANEL 4: CORRECTED TRANSLATION ===
            if self._translate and self._on_corrected_translation:
                translated = self._translate_text(corrected)
                if translated:
                    log.info(f"-> Panel 4: '{translated[:60]}'")
                    self._on_corrected_translation(translated)

        except Exception as e:
            log.error(f"Group processing error: {e}")

    def _translate_group(self, text: str, speaker: Optional[str]):
        """Translate without correction -> Panel 3 + 4."""
        try:
            if self._on_corrected:
                self._on_corrected(text, speaker)
            if self._on_corrected_translation:
                translated = self._translate_text(text)
                if translated:
                    self._on_corrected_translation(translated)
        except Exception as e:
            log.error(f"Translate group error: {e}")

    def _process_group_sync(self):
        if not self._group_texts:
            return
        try:
            audio = np.concatenate(self._group_audio)
            texts = list(self._group_texts)
            speakers = list(self._group_speakers)
            self._process_group(audio, texts, speakers)
        except Exception as e:
            log.error(f"Final group error: {e}")

    # -- Filters --

    @staticmethod
    def _is_repetition_loop(text: str) -> bool:
        """Detect Whisper repetition loops like 'word word word word'."""
        words = text.lower().split()
        if len(words) < 4:
            return False
        # Check if any 1-3 word phrase repeats 3+ times
        for phrase_len in range(1, 4):
            if len(words) < phrase_len * 3:
                continue
            phrase = " ".join(words[:phrase_len])
            count = 0
            for i in range(0, len(words) - phrase_len + 1, phrase_len):
                chunk = " ".join(words[i:i + phrase_len])
                if chunk == phrase:
                    count += 1
                else:
                    break
            if count >= 3:
                return True
        return False

    # -- GPT comparison --

    def _gpt_compare(self, instant: str, retranscribed: str) -> str:
        try:
            if self._openai is None:
                self._openai = OpenAI(api_key=settings.OPENAI_API_KEY)

            # Language-aware system prompt for correction
            lang_note = ""
            if self._language == "uz":
                lang_note = " Текст на узбекском языке (латиница). Сохраняй узбекские слова как есть."
            elif self._language:
                lang_note = f" Язык: {self._language}."

            response = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты модуль сравнения двух транскрипций одного и того же аудио.\n"
                            "Первая — мгновенная (собрана из коротких 5-секундных фрагментов, "
                            "может содержать ошибки на стыках слов).\n"
                            "Вторая — повторная (из объединённого аудио ~10 секунд, "
                            "более точная за счёт контекста).\n\n"
                            "Правила:\n"
                            "1. Сравни обе транскрипции пословно.\n"
                            "2. Где слова совпадают — оставь как есть.\n"
                            "3. Где отличаются — выбери наиболее подходящее по смыслу "
                            "и звучанию слово.\n"
                            "4. Делай МИНИМАЛЬНЫЕ изменения. Не переписывай текст.\n"
                            "5. Не добавляй слова, которых нет ни в одной из версий.\n"
                            f"6. Верни ТОЛЬКО итоговый текст, без пояснений.{lang_note}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"МГНОВЕННАЯ ТРАНСКРИПЦИЯ (из 5-сек фрагментов):\n{instant}\n\n"
                            f"ПОВТОРНАЯ ТРАНСКРИПЦИЯ (из 10-сек аудио):\n{retranscribed}\n\n"
                            f"ЛУЧШИЙ ВАРИАНТ:"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=500,
            )

            corrected = (response.choices[0].message.content or instant).strip()

            if self._is_minor_change(instant, corrected):
                return corrected
            else:
                log.warning("GPT changed too much, keeping instant version")
                return instant

        except Exception as e:
            log.error(f"GPT compare error: {e}")
            return instant

    @staticmethod
    def _is_minor_change(original: str, corrected: str) -> bool:
        orig_words = set(original.lower().split())
        corr_words = set(corrected.lower().split())
        if not orig_words:
            return True
        common = orig_words & corr_words
        kept_ratio = len(common) / len(orig_words)
        return kept_ratio >= 0.5

    # Languages where NLLB-200 gives poor quality → always use GPT
    _GPT_TRANSLATE_LANGS = {"uz", "kk", "tg"}

    # -- Translation --

    def _translate_text(self, text: str) -> str:
        if not text.strip():
            return ""
        try:
            # For Uzbek and other poorly-supported NLLB languages → GPT directly
            use_gpt = self._language in self._GPT_TRANSLATE_LANGS

            # Local translator (fast, no API call) — only for well-supported languages
            if (
                not use_gpt
                and self._local_translator
                and self._local_translator.is_ready
            ):
                return self._local_translator.translate(text, target_lang="ru")

            # GPT translation (better quality for Uzbek, Kazakh, etc.)
            return self._translate_gpt(text)

        except Exception as e:
            log.error(f"Translation error: {e}")
            return ""

    def _translate_gpt(self, text: str) -> str:
        """Translate using GPT-4o-mini — high quality for all languages."""
        if self._openai is None:
            self._openai = OpenAI(api_key=settings.OPENAI_API_KEY)

        # Detect source language hint for better translation
        lang_hint = ""
        if self._language == "uz":
            lang_hint = " Исходный текст на узбекском языке (латиница)."
        elif self._language == "kk":
            lang_hint = " Исходный текст на казахском языке."

        response = self._openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты профессиональный переводчик. Переводи на русский язык."
                        f"{lang_hint}"
                        " Верни ТОЛЬКО перевод, без пояснений и комментариев."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            max_tokens=1000,
        )
        return (response.choices[0].message.content or "").strip()
