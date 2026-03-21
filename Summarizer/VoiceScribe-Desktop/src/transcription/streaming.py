"""
Streaming transcriber that accumulates audio and transcribes in chunks.
Sends chunks to OpenAI Whisper API periodically during recording.
Uses overlap between chunks to prevent losing words at boundaries.
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

# Overlap duration in seconds — keeps tail of previous chunk
# so Whisper has context and doesn't cut words mid-sentence.
OVERLAP_SEC = 3.0

TRANSLATE_PROMPT = (
    "Переведи следующий текст на русский язык. "
    "Сохрани смысл и стиль. Верни ТОЛЬКО перевод, без пояснений.\n\n{text}"
)


class StreamingTranscriber:
    """Accumulates audio chunks and transcribes every `interval` seconds.

    Features:
    - Overlap between chunks to avoid losing words at boundaries
    - Processes all remaining audio when stopped
    - Optional real-time translation to Russian
    """

    def __init__(
        self,
        transcriber: WhisperAPITranscriber,
        sample_rate: int = 16000,
        interval_sec: float = 10.0,
        on_result: Optional[Callable[[TranscriptionResult], None]] = None,
        translate_to_russian: bool = False,
        noise_reduction: bool = True,
        corrector=None,
    ):
        self._transcriber = transcriber
        self._sample_rate = sample_rate
        self._interval = interval_sec
        self._on_result = on_result
        self._translate = translate_to_russian
        self._noise_reduction = noise_reduction
        self._corrector = corrector  # Optional[TranscriptCorrector]

        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._is_running = False
        self._thread: Optional[threading.Thread] = None

        # Accumulated results
        self._all_segments: list[TranscriptionSegment] = []
        self._time_offset: float = 0.0

        # Overlap samples kept from previous chunk
        self._overlap_samples = int(OVERLAP_SEC * sample_rate)
        self._prev_tail: Optional[np.ndarray] = None

        # OpenAI client for translation (lazy init)
        self._openai: Optional[OpenAI] = None

    def start(self):
        self._is_running = True
        self._all_segments.clear()
        self._time_offset = 0.0
        self._prev_tail = None
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        log.info(f"Streaming transcriber started (overlap={int(OVERLAP_SEC)}s, translate={self._translate}, denoise={self._noise_reduction})")

    def stop(self) -> TranscriptionResult:
        """Stop and return final combined result.

        Processes ALL remaining audio before returning so nothing is lost.
        """
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=30.0)
            self._thread = None

        # Process any remaining audio in the queue
        remaining = self._drain_queue()
        if len(remaining) > self._sample_rate * 0.5:  # at least 0.5 sec
            self._transcribe_chunk(remaining, is_final=True)

        full_text = " ".join(seg.text for seg in self._all_segments)
        log.info(f"Streaming transcriber stopped. Total segments: {len(self._all_segments)}")

        return TranscriptionResult(
            text=full_text,
            segments=self._all_segments,
            language=self._all_segments[0].language if self._all_segments else "",
            duration=self._time_offset,
        )

    def add_audio(self, audio: np.ndarray):
        """Add audio data to the processing queue."""
        if self._is_running:
            self._audio_queue.put(audio)

    def _process_loop(self):
        buffer = np.array([], dtype=np.float32)
        chunk_samples = int(self._interval * self._sample_rate)

        while self._is_running:
            try:
                audio = self._audio_queue.get(timeout=0.2)
                buffer = np.concatenate([buffer, audio])

                if len(buffer) >= chunk_samples:
                    chunk = buffer[:chunk_samples]
                    buffer = buffer[chunk_samples:]
                    self._transcribe_chunk(chunk)

            except queue.Empty:
                continue

        # Don't lose remaining buffer — it'll be handled in stop()
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

    def _transcribe_chunk(self, audio: np.ndarray, is_final: bool = False):
        try:
            # Prepend overlap from previous chunk for context
            if self._prev_tail is not None and len(self._prev_tail) > 0:
                audio_with_overlap = np.concatenate([self._prev_tail, audio])
                overlap_duration = len(self._prev_tail) / self._sample_rate
            else:
                audio_with_overlap = audio
                overlap_duration = 0.0

            # Save tail for next chunk (unless this is the last chunk)
            if not is_final:
                tail_len = min(self._overlap_samples, len(audio))
                self._prev_tail = audio[-tail_len:].copy()
            else:
                self._prev_tail = None

            # Clean audio: bandpass filter + noise reduction
            if self._noise_reduction:
                audio_with_overlap = enhance_speech(
                    audio_with_overlap,
                    self._sample_rate,
                    enable_bandpass=True,
                    enable_noise_reduction=True,
                )

            result = self._transcriber.transcribe_numpy(
                audio_with_overlap, sample_rate=self._sample_rate
            )

            # Translate if enabled
            if self._translate and result.text.strip():
                translated_text = self._translate_text(result.text.strip())
                if translated_text:
                    # Build translated segments
                    if result.segments:
                        translated_segments = []
                        for s in result.segments:
                            t_text = self._translate_text(s.text) if s.text.strip() else s.text
                            translated_segments.append(TranscriptionSegment(
                                start=s.start, end=s.end,
                                text=t_text, confidence=s.confidence,
                                language="ru", speaker=s.speaker,
                            ))
                    else:
                        translated_segments = [TranscriptionSegment(
                            start=0, end=len(audio) / self._sample_rate,
                            text=translated_text, language="ru",
                        )]

                    result = TranscriptionResult(
                        text=translated_text,
                        segments=translated_segments,
                        language="ru",
                        duration=result.duration,
                    )

            # Adjust segment timestamps: skip overlap region,
            # then offset to global timeline
            for seg in result.segments:
                seg.start = max(0, seg.start - overlap_duration) + self._time_offset
                seg.end = max(0, seg.end - overlap_duration) + self._time_offset
                self._all_segments.append(seg)

            # Advance offset by the NEW audio length (not overlap)
            self._time_offset += len(audio) / self._sample_rate

            if self._on_result:
                self._on_result(result)

            # Feed text to corrector for self-healing
            if self._corrector and result.text.strip():
                self._corrector.add_chunk(result.text.strip())

            log.info(f"Chunk transcribed: '{result.text[:60]}...' at offset {self._time_offset:.1f}s")

        except Exception as e:
            log.error(f"Streaming transcription error: {e}")
            self._time_offset += len(audio) / self._sample_rate

    def _translate_text(self, text: str) -> str:
        """Translate text to Russian using OpenAI GPT."""
        if not text.strip():
            return text
        try:
            if self._openai is None:
                self._openai = OpenAI(api_key=settings.OPENAI_API_KEY)

            response = self._openai.chat.completions.create(
                model=settings.ANALYSIS_MODEL,
                messages=[
                    {"role": "system", "content": "Ты точный переводчик. Переводи на русский язык."},
                    {"role": "user", "content": TRANSLATE_PROMPT.format(text=text)},
                ],
                temperature=0.2,
                max_tokens=2000,
            )
            translated = response.choices[0].message.content or text
            return translated.strip()
        except Exception as e:
            log.error(f"Translation error: {e}")
            return text
