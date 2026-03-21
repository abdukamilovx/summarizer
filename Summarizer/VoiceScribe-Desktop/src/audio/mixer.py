"""
Mixes microphone and system audio into a single mono stream.
"""
import numpy as np
import threading
from typing import Optional

from audio.capture import AudioChunk


class AudioMixer:
    """Collects chunks from mic and system, mixes when both are available."""

    def __init__(self, mic_gain: float = 0.7, system_gain: float = 0.5):
        self.mic_gain = mic_gain
        self.system_gain = system_gain

        self._mic_buffer: list[np.ndarray] = []
        self._system_buffer: list[np.ndarray] = []
        self._lock = threading.Lock()

    def add_chunk(self, chunk: AudioChunk) -> Optional[AudioChunk]:
        """Add a chunk; returns a mixed chunk when enough data is buffered."""
        with self._lock:
            if chunk.source == "microphone":
                self._mic_buffer.append(chunk.data)
            elif chunk.source == "system":
                self._system_buffer.append(chunk.data)
            else:
                # Already mixed or unknown — pass through
                return chunk

            return self._try_mix(chunk.sample_rate)

    def _try_mix(self, sample_rate: int) -> Optional[AudioChunk]:
        if not self._mic_buffer and not self._system_buffer:
            return None

        # If only one source is active, return that directly
        if not self._system_buffer and self._mic_buffer:
            mic = np.concatenate(self._mic_buffer)
            self._mic_buffer.clear()
            return AudioChunk(
                data=mic,
                sample_rate=sample_rate,
                channels=1,
                timestamp=0,
                source="mixed",
            )

        if not self._mic_buffer and self._system_buffer:
            sys = np.concatenate(self._system_buffer)
            self._system_buffer.clear()
            return AudioChunk(
                data=sys,
                sample_rate=sample_rate,
                channels=1,
                timestamp=0,
                source="mixed",
            )

        # Both sources available — mix
        mic = np.concatenate(self._mic_buffer)
        sys = np.concatenate(self._system_buffer)

        min_len = min(len(mic), len(sys))
        if min_len < sample_rate * 0.1:  # need at least 100ms
            return None

        mixed = mic[:min_len] * self.mic_gain + sys[:min_len] * self.system_gain
        peak = np.max(np.abs(mixed)) + 1e-8
        if peak > 1.0:
            mixed = mixed / peak

        self._mic_buffer.clear()
        self._system_buffer.clear()

        return AudioChunk(
            data=mixed.astype(np.float32),
            sample_rate=sample_rate,
            channels=1,
            timestamp=0,
            source="mixed",
        )

    def flush(self, sample_rate: int = 16000) -> Optional[AudioChunk]:
        """Flush remaining buffered audio."""
        with self._lock:
            return self._try_mix(sample_rate)
