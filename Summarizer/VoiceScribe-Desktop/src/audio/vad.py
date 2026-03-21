"""
Simple energy-based Voice Activity Detection.
Splits audio into speech/silence segments.
"""
import numpy as np
from dataclasses import dataclass


@dataclass
class VADSegment:
    start_sample: int
    end_sample: int
    is_speech: bool


class EnergyVAD:
    """Simple energy-based VAD for chunking audio before transcription."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        energy_threshold: float = 0.01,
        min_speech_duration_ms: int = 300,
        min_silence_duration_ms: int = 500,
    ):
        self.sample_rate = sample_rate
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.energy_threshold = energy_threshold
        self.min_speech_frames = int(min_speech_duration_ms / frame_duration_ms)
        self.min_silence_frames = int(min_silence_duration_ms / frame_duration_ms)

    def detect(self, audio: np.ndarray) -> list[VADSegment]:
        """Return speech/silence segments for the given audio."""
        segments: list[VADSegment] = []
        n_frames = len(audio) // self.frame_size

        if n_frames == 0:
            return segments

        is_speech = False
        speech_start = 0
        silence_count = 0
        speech_count = 0

        for i in range(n_frames):
            frame = audio[i * self.frame_size : (i + 1) * self.frame_size]
            energy = np.sqrt(np.mean(frame ** 2))

            if energy >= self.energy_threshold:
                speech_count += 1
                silence_count = 0

                if not is_speech and speech_count >= self.min_speech_frames:
                    is_speech = True
                    speech_start = max(0, (i - self.min_speech_frames)) * self.frame_size
            else:
                silence_count += 1
                speech_count = 0

                if is_speech and silence_count >= self.min_silence_frames:
                    is_speech = False
                    segments.append(VADSegment(
                        start_sample=speech_start,
                        end_sample=i * self.frame_size,
                        is_speech=True,
                    ))

        # Close any open speech segment
        if is_speech:
            segments.append(VADSegment(
                start_sample=speech_start,
                end_sample=len(audio),
                is_speech=True,
            ))

        return segments

    def get_speech_audio(self, audio: np.ndarray, padding_ms: int = 200) -> np.ndarray:
        """Return only the speech portions of audio, concatenated."""
        segments = self.detect(audio)
        if not segments:
            return audio  # no segmentation, return as-is

        pad = int(self.sample_rate * padding_ms / 1000)
        parts = []
        for seg in segments:
            start = max(0, seg.start_sample - pad)
            end = min(len(audio), seg.end_sample + pad)
            parts.append(audio[start:end])

        return np.concatenate(parts) if parts else audio
