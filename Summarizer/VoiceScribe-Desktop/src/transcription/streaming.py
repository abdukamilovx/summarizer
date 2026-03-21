"""
Streaming transcriber that accumulates audio and transcribes in chunks.
Sends chunks to OpenAI Whisper API periodically during recording.
"""
import numpy as np
import threading
import queue
import time
from typing import Callable, Optional

from transcription.whisper_api import WhisperAPITranscriber
from transcription.engine import TranscriptionResult, TranscriptionSegment
from utils.logger import log


class StreamingTranscriber:
    """Accumulates audio chunks and transcribes every `interval` seconds."""

    def __init__(
        self,
        transcriber: WhisperAPITranscriber,
        sample_rate: int = 16000,
        interval_sec: float = 10.0,
        on_result: Optional[Callable[[TranscriptionResult], None]] = None,
    ):
        self._transcriber = transcriber
        self._sample_rate = sample_rate
        self._interval = interval_sec
        self._on_result = on_result

        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._is_running = False
        self._thread: Optional[threading.Thread] = None

        # Accumulated results
        self._all_segments: list[TranscriptionSegment] = []
        self._time_offset: float = 0.0

    def start(self):
        self._is_running = True
        self._all_segments.clear()
        self._time_offset = 0.0
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        log.info("Streaming transcriber started")

    def stop(self) -> TranscriptionResult:
        """Stop and return final combined result."""
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        # Process any remaining audio
        remaining = self._drain_queue()
        if len(remaining) > self._sample_rate:  # at least 1 sec
            self._transcribe_chunk(remaining)

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
            # Put back into queue so stop() can drain it
            self._audio_queue.put(buffer)

    def _drain_queue(self) -> np.ndarray:
        parts = []
        while not self._audio_queue.empty():
            try:
                parts.append(self._audio_queue.get_nowait())
            except queue.Empty:
                break
        return np.concatenate(parts) if parts else np.array([], dtype=np.float32)

    def _transcribe_chunk(self, audio: np.ndarray):
        try:
            result = self._transcriber.transcribe_numpy(
                audio, sample_rate=self._sample_rate
            )

            # Adjust timestamps with offset
            for seg in result.segments:
                seg.start += self._time_offset
                seg.end += self._time_offset
                self._all_segments.append(seg)

            self._time_offset += len(audio) / self._sample_rate

            if self._on_result:
                self._on_result(result)

            log.info(f"Chunk transcribed: '{result.text[:60]}...' at offset {self._time_offset:.1f}s")

        except Exception as e:
            log.error(f"Streaming transcription error: {e}")
            self._time_offset += len(audio) / self._sample_rate
