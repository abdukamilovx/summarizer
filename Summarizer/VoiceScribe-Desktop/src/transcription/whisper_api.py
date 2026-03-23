"""
OpenAI Whisper API transcription backend.
"""
import io
import tempfile
import numpy as np
import soundfile as sf
from typing import Optional
from openai import OpenAI

from transcription.engine import (
    TranscriptionEngine,
    TranscriptionResult,
    TranscriptionSegment,
)
from utils.config import settings
from utils.logger import log


class WhisperAPITranscriber(TranscriptionEngine):
    """Transcribes audio using the OpenAI Whisper API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-1"):
        self.client = OpenAI(api_key=api_key or settings.OPENAI_API_KEY)
        self.model = model

    def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe raw WAV bytes."""
        buf = io.BytesIO(audio_data)
        buf.name = "audio.wav"

        kwargs: dict = {
            "model": self.model,
            "file": buf,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment"],
        }
        if language:
            kwargs["language"] = language
        if prompt:
            kwargs["prompt"] = prompt

        response = self.client.audio.transcriptions.create(**kwargs)

        segments = []
        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                segments.append(
                    TranscriptionSegment(
                        start=seg.get("start", 0) if isinstance(seg, dict) else getattr(seg, "start", 0),
                        end=seg.get("end", 0) if isinstance(seg, dict) else getattr(seg, "end", 0),
                        text=(seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip(),
                        confidence=seg.get("avg_logprob", 0) if isinstance(seg, dict) else getattr(seg, "avg_logprob", 0),
                        language=getattr(response, "language", ""),
                    )
                )

        return TranscriptionResult(
            text=response.text.strip(),
            segments=segments,
            language=getattr(response, "language", ""),
            duration=getattr(response, "duration", 0.0),
        )

    def transcribe_file(
        self,
        filepath: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file from disk."""
        with open(filepath, "rb") as f:
            return self.transcribe(f.read(), language=language, prompt=prompt)

    def transcribe_numpy(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe a numpy array of audio samples."""
        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV", subtype="FLOAT")
        buf.seek(0)
        return self.transcribe(buf.read(), language=language, prompt=prompt)
