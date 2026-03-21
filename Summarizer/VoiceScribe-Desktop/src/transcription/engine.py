"""
Abstract transcription engine interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str
    confidence: float = 1.0
    language: str = ""
    speaker: Optional[str] = None


@dataclass
class TranscriptionResult:
    text: str
    segments: list[TranscriptionSegment] = field(default_factory=list)
    language: str = ""
    duration: float = 0.0


class TranscriptionEngine(ABC):
    """Base class for transcription backends."""

    @abstractmethod
    def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        ...

    @abstractmethod
    def transcribe_file(
        self,
        filepath: str,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        ...
