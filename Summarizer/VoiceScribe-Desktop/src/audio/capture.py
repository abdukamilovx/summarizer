"""
Audio capture via WASAPI on Windows.
Supports microphone and system audio (loopback) capture.

High-quality recording:
- Uses 44100 Hz for WAV export (resampled to 16000 for Whisper)
- Small buffer (100ms) for smooth, glitch-free audio
- Separate high-quality buffer for WAV file saving
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Optional
import threading
import queue
import time

from utils.logger import log


# High-quality sample rate for WAV export
WAV_SAMPLE_RATE = 44100


@dataclass
class AudioChunk:
    """A chunk of captured audio data."""
    data: np.ndarray
    sample_rate: int
    channels: int
    timestamp: float
    source: str  # 'microphone' | 'system' | 'mixed'


class AudioCapture:
    """Captures microphone and/or system audio via WASAPI loopback.

    Records at native device rate for WAV quality, resamples to
    target rate (16000) for Whisper API.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_duration: float = 0.1,   # 100ms for smooth recording
        capture_microphone: bool = True,
        capture_system: bool = True,
    ):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.capture_microphone = capture_microphone
        self.capture_system = capture_system

        self._callbacks: list[Callable[[AudioChunk], None]] = []
        self._hq_callbacks: list[Callable[[AudioChunk], None]] = []  # High-quality WAV callbacks
        self._is_capturing = False
        self._pyaudio = None
        self._mic_stream = None
        self._system_stream = None

    # -- public API --

    def on_audio(self, callback: Callable[[AudioChunk], None]) -> None:
        """Register callback for Whisper-rate (16kHz) audio."""
        self._callbacks.append(callback)

    def on_hq_audio(self, callback: Callable[[AudioChunk], None]) -> None:
        """Register callback for high-quality (44.1kHz) audio for WAV saving."""
        self._hq_callbacks.append(callback)

    def start(self) -> None:
        import pyaudiowpatch as pyaudio

        self._pyaudio = pyaudio.PyAudio()
        self._is_capturing = True

        frames_per_buffer = int(self.sample_rate * self.chunk_duration)

        if self.capture_microphone:
            try:
                self._mic_stream = self._pyaudio.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=frames_per_buffer,
                    stream_callback=self._mic_callback,
                )
                log.info("Microphone capture started")
            except Exception as e:
                log.warning(f"Could not open microphone: {e}")

        if self.capture_system:
            try:
                self._open_loopback_stream()
                log.info("System audio capture started")
            except Exception as e:
                log.warning(f"Could not open system audio loopback: {e}")

    def stop(self) -> None:
        self._is_capturing = False

        for stream in (self._mic_stream, self._system_stream):
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass

        self._mic_stream = None
        self._system_stream = None

        if self._pyaudio is not None:
            self._pyaudio.terminate()
            self._pyaudio = None

        log.info("Audio capture stopped")

    @property
    def is_capturing(self) -> bool:
        return self._is_capturing

    # -- internal --

    def _open_loopback_stream(self) -> None:
        import pyaudiowpatch as pyaudio

        wasapi_info = self._pyaudio.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = self._pyaudio.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )

        if not default_speakers.get("isLoopbackDevice"):
            for i in range(self._pyaudio.get_device_count()):
                dev = self._pyaudio.get_device_info_by_index(i)
                if (
                    dev.get("isLoopbackDevice")
                    and default_speakers["name"] in dev["name"]
                ):
                    default_speakers = dev
                    break

        self._system_sr = int(default_speakers["defaultSampleRate"])
        self._system_channels = max(1, int(default_speakers["maxInputChannels"]))

        # Use smaller buffer for smoother capture
        system_frames = int(self._system_sr * self.chunk_duration)

        self._system_stream = self._pyaudio.open(
            format=pyaudio.paFloat32,
            channels=self._system_channels,
            rate=self._system_sr,
            input=True,
            input_device_index=int(default_speakers["index"]),
            frames_per_buffer=system_frames,
            stream_callback=self._system_callback,
        )

    def _mic_callback(self, in_data, frame_count, time_info, status):
        import pyaudiowpatch as pyaudio

        if not self._is_capturing:
            return (in_data, pyaudio.paComplete)

        audio = np.frombuffer(in_data, dtype=np.float32).copy()

        # Emit for Whisper (already at target rate)
        chunk = AudioChunk(
            data=audio,
            sample_rate=self.sample_rate,
            channels=1,
            timestamp=time.time(),
            source="microphone",
        )
        self._emit(chunk)

        # Emit high-quality version (upsample to 44.1kHz for WAV)
        if self._hq_callbacks:
            hq_audio = self._resample(audio, self.sample_rate, WAV_SAMPLE_RATE)
            hq_chunk = AudioChunk(
                data=hq_audio,
                sample_rate=WAV_SAMPLE_RATE,
                channels=1,
                timestamp=time.time(),
                source="microphone",
            )
            self._emit_hq(hq_chunk)

        return (in_data, pyaudio.paContinue)

    def _system_callback(self, in_data, frame_count, time_info, status):
        import pyaudiowpatch as pyaudio

        if not self._is_capturing:
            return (in_data, pyaudio.paComplete)

        audio = np.frombuffer(in_data, dtype=np.float32).copy()

        # Convert to mono
        if self._system_channels > 1:
            audio = audio.reshape(-1, self._system_channels).mean(axis=1)

        # Emit high-quality version BEFORE resampling (native rate → 44.1kHz)
        if self._hq_callbacks:
            if self._system_sr != WAV_SAMPLE_RATE:
                hq_audio = self._resample(audio, self._system_sr, WAV_SAMPLE_RATE)
            else:
                hq_audio = audio.copy()
            hq_chunk = AudioChunk(
                data=hq_audio,
                sample_rate=WAV_SAMPLE_RATE,
                channels=1,
                timestamp=time.time(),
                source="system",
            )
            self._emit_hq(hq_chunk)

        # Resample to Whisper rate (16kHz)
        if self._system_sr != self.sample_rate:
            audio = self._resample(audio, self._system_sr, self.sample_rate)

        chunk = AudioChunk(
            data=audio,
            sample_rate=self.sample_rate,
            channels=1,
            timestamp=time.time(),
            source="system",
        )
        self._emit(chunk)
        return (in_data, pyaudio.paContinue)

    @staticmethod
    def _resample(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
        """High-quality linear interpolation resampling."""
        if from_rate == to_rate:
            return audio
        ratio = to_rate / from_rate
        new_len = int(len(audio) * ratio)
        indices = np.linspace(0, len(audio) - 1, new_len)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    def _emit(self, chunk: AudioChunk) -> None:
        for cb in self._callbacks:
            try:
                cb(chunk)
            except Exception as e:
                log.error(f"Audio callback error: {e}")

    def _emit_hq(self, chunk: AudioChunk) -> None:
        for cb in self._hq_callbacks:
            try:
                cb(chunk)
            except Exception as e:
                log.error(f"HQ audio callback error: {e}")
