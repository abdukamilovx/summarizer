"""
Self-healing transcript corrector.
Accumulates raw transcript chunks, saves to file, and periodically
sends the full text to GPT for error correction and gap filling.
"""
import threading
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI

from analysis.prompts import CORRECTION_PROMPT
from utils.config import settings
from utils.logger import log


class TranscriptCorrector:
    """Writes raw transcript to file and periodically corrects it via GPT.

    Every `correction_interval` chunks, the accumulated raw text is sent
    to GPT to fix:
    - Words cut off at chunk boundaries
    - Duplicate phrases from overlap
    - Speech recognition errors
    - Incoherent transitions
    """

    def __init__(
        self,
        raw_file_path: str,
        correction_interval: int = 3,
        on_corrected: Optional[Callable[[str], None]] = None,
    ):
        self._raw_path = Path(raw_file_path)
        self._interval = correction_interval
        self._on_corrected = on_corrected

        self._raw_chunks: list[str] = []
        self._chunk_count = 0
        self._corrected_text = ""
        self._lock = threading.Lock()
        self._correcting = False

        self._openai: Optional[OpenAI] = None

        # Ensure directory exists and create/clear the raw file
        self._raw_path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_path.write_text("", encoding="utf-8")
        log.info(f"TranscriptCorrector: raw file at {self._raw_path}")

    def add_chunk(self, text: str):
        """Add a new transcript chunk. Writes to file and triggers correction if due."""
        if not text.strip():
            return

        with self._lock:
            self._raw_chunks.append(text.strip())
            self._chunk_count += 1

        # Append to raw file
        with open(self._raw_path, "a", encoding="utf-8") as f:
            f.write(text.strip() + "\n\n")

        # Trigger correction every N chunks
        if self._chunk_count % self._interval == 0 and not self._correcting:
            threading.Thread(target=self._run_correction, daemon=True).start()

    def _run_correction(self):
        """Send accumulated text to GPT for correction."""
        self._correcting = True
        try:
            with self._lock:
                raw_text = "\n".join(self._raw_chunks)

            if not raw_text.strip():
                return

            if self._openai is None:
                self._openai = OpenAI(api_key=settings.OPENAI_API_KEY)

            log.info(f"Running transcript correction ({len(raw_text)} chars)...")

            response = self._openai.chat.completions.create(
                model=settings.ANALYSIS_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты редактор транскрипций. Исправляй ошибки, не добавляя нового содержания.",
                    },
                    {
                        "role": "user",
                        "content": CORRECTION_PROMPT.format(transcript=raw_text),
                    },
                ],
                temperature=0.2,
                max_tokens=4000,
            )

            corrected = response.choices[0].message.content or raw_text
            self._corrected_text = corrected.strip()

            log.info("Transcript correction complete")

            if self._on_corrected:
                self._on_corrected(self._corrected_text)

        except Exception as e:
            log.error(f"Transcript correction failed: {e}")
        finally:
            self._correcting = False

    def get_raw_text(self) -> str:
        """Return all raw chunks concatenated."""
        with self._lock:
            return "\n".join(self._raw_chunks)

    def get_corrected_text(self) -> str:
        """Return the latest corrected text, or raw if no correction has run."""
        if self._corrected_text:
            return self._corrected_text
        return self.get_raw_text()

    def force_correction(self):
        """Force a correction run regardless of chunk count."""
        if not self._correcting:
            threading.Thread(target=self._run_correction, daemon=True).start()
