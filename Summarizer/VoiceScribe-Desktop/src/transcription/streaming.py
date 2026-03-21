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

    # -- Fast path: Panel 1 + Panel 2 --

    def _process_fast_chunk(self, audio: np.ndarray):
        """Transcribe 1-sec chunk -> Panel 1 (instant) + Panel 2 (translation)."""
        try:
            processed = audio
            if self._noise_reduction:
                processed = enhance_speech(
                    audio, self._sample_rate,
                    enable_bandpass=True, enable_noise_reduction=True,
                )

            result = self._transcriber.transcribe_numpy(
                processed, sample_rate=self._sample_rate
            )

            if not result.text.strip():
                self._group_audio.append(audio)
                self._time_offset += len(audio) / self._sample_rate
                return

            text = result.text.strip()
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

            result = self._transcriber.transcribe_numpy(
                processed, sample_rate=self._sample_rate
            )
            retranscription = result.text.strip()

            if not retranscription:
                return

            instant_combined = " ".join(instant_texts)
            speaker = next((s for s in speakers if s), None)

            # 2. Compare
            if instant_combined.strip() == retranscription.strip():
                corrected = instant_combined
            else:
                corrected = self._gpt_compare(instant_combined, retranscription)
                if not corrected:
                    corrected = instant_combined

            # === PANEL 3: CORRECTED TEXT ===
            if self._on_corrected:
                self._on_corrected(corrected, speaker)

            # === PANEL 4: CORRECTED TRANSLATION ===
            if self._translate and self._on_corrected_translation:
                translated = self._translate_text(corrected)
                if translated:
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

    # -- GPT comparison --

    def _gpt_compare(self, instant: str, retranscribed: str) -> str:
        try:
            if self._openai is None:
                self._openai = OpenAI(api_key=settings.OPENAI_API_KEY)

            response = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты модуль сравнения двух транскрипций одного и того же аудио.\n"
                            "Первая — мгновенная (собрана из коротких 1-секундных фрагментов, "
                            "может содержать ошибки на стыках слов).\n"
                            "Вторая — повторная (из объединённого аудио ~5 секунд, "
                            "более точная за счёт контекста).\n\n"
                            "Правила:\n"
                            "1. Сравни обе транскрипции пословно.\n"
                            "2. Где слова совпадают — оставь как есть.\n"
                            "3. Где отличаются — выбери наиболее подходящее по смыслу "
                            "и звучанию слово.\n"
                            "4. Делай МИНИМАЛЬНЫЕ изменения. Не переписывай текст.\n"
                            "5. Не добавляй слова, которых нет ни в одной из версий.\n"
                            "6. Верни ТОЛЬКО итоговый текст, без пояснений."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"МГНОВЕННАЯ ТРАНСКРИПЦИЯ (из 1-сек фрагментов):\n{instant}\n\n"
                            f"ПОВТОРНАЯ ТРАНСКРИПЦИЯ (из 5-сек аудио):\n{retranscribed}\n\n"
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

    # -- Translation --

    def _translate_text(self, text: str) -> str:
        if not text.strip():
            return ""
        try:
            # Local translator (fast, no API call)
            if self._local_translator and self._local_translator.is_ready:
                return self._local_translator.translate(text, target_lang="ru")

            # GPT fallback
            if self._openai is None:
                self._openai = OpenAI(api_key=settings.OPENAI_API_KEY)

            response = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Ты переводчик. Переводи на русский. Верни ТОЛЬКО перевод.",
                    },
                    {"role": "user", "content": text},
                ],
                temperature=0.2,
                max_tokens=1000,
            )
            return (response.choices[0].message.content or "").strip()

        except Exception as e:
            log.error(f"Translation error: {e}")
            return ""
