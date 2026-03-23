"""
AI-powered transcript analysis using OpenAI GPT models.
"""
import json
from typing import Optional
from openai import OpenAI

from analysis.prompts import (
    SUMMARY_PROMPT,
    ACTION_ITEMS_PROMPT,
    KEY_POINTS_PROMPT,
    TOPICS_PROMPT,
    TRANSLATE_FULL_PROMPT,
    DIALOGUE_PROMPT,
    BATCH_DIARIZATION_PROMPT,
    POST_EDIT_PROMPT,
    MEETING_PROTOCOL_PROMPT,
)
from utils.config import settings
from utils.logger import log


class Summarizer:
    """Analyzes transcripts: summaries, action items, key points, topics, dialogue."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.client = OpenAI(api_key=api_key or settings.OPENAI_API_KEY)
        self.model = model or settings.ANALYSIS_MODEL

    def _call_llm(self, prompt: str, json_mode: bool = False, temperature: float = 0.3) -> str:
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Ты помощник для анализа записей встреч и разговоров."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 2000,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def summarize(self, transcript: str) -> str:
        """Generate a structured summary of the transcript."""
        log.info("Generating summary...")
        return self._call_llm(SUMMARY_PROMPT.format(transcript=transcript))

    def extract_actions(self, transcript: str) -> list[dict]:
        """Extract action items from transcript."""
        log.info("Extracting action items...")
        raw = self._call_llm(
            ACTION_ITEMS_PROMPT.format(transcript=transcript),
            json_mode=True,
            temperature=0.2,
        )
        try:
            data = json.loads(raw)
            return data.get("action_items", [])
        except json.JSONDecodeError:
            log.error("Failed to parse action items JSON")
            return []

    def get_key_points(self, transcript: str) -> list[str]:
        """Extract key points from transcript."""
        log.info("Extracting key points...")
        raw = self._call_llm(KEY_POINTS_PROMPT.format(transcript=transcript))
        points = [line.strip() for line in raw.split("\n") if line.strip()]
        return points

    def analyze_topics(self, transcript: str) -> list[dict]:
        """Analyze conversation topics."""
        log.info("Analyzing topics...")
        raw = self._call_llm(
            TOPICS_PROMPT.format(transcript=transcript),
            json_mode=True,
        )
        try:
            data = json.loads(raw)
            return data.get("topics", [])
        except json.JSONDecodeError:
            log.error("Failed to parse topics JSON")
            return []

    def translate(self, transcript: str) -> str:
        """Translate transcript to Russian, preserving sentence count."""
        log.info("Translating to Russian...")
        return self._call_llm(
            TRANSLATE_FULL_PROMPT.format(transcript=transcript),
            temperature=0.2,
        )

    def reconstruct_dialogue(self, transcript: str) -> str:
        """Reconstruct structured dialogue with speaker identification.

        Identifies speakers by name from context, assigns roles,
        and includes translation if the text is in a foreign language.
        """
        log.info("Reconstructing dialogue...")
        return self._call_llm(
            DIALOGUE_PROMPT.format(transcript=transcript),
            temperature=0.3,
        )

    def batch_diarize(self, transcript: str) -> str:
        """Process uploaded file: diarization + structuring + correction."""
        log.info("Batch diarization and structuring...")
        return self._call_llm(
            BATCH_DIARIZATION_PROMPT.format(transcript=transcript),
            temperature=0.3,
        )

    def post_edit(self, transcript: str) -> str:
        """Final cleanup of a completed transcript."""
        log.info("Post-editing transcript...")
        return self._call_llm(
            POST_EDIT_PROMPT.format(transcript=transcript),
            temperature=0.2,
        )

    def meeting_protocol(self, transcript: str) -> str:
        """Generate a detailed meeting protocol (minutes)."""
        log.info("Generating meeting protocol...")
        return self._call_llm(
            MEETING_PROTOCOL_PROMPT.format(transcript=transcript),
            temperature=0.3,
        )

    def full_analysis(self, transcript: str) -> dict:
        """Run all analyses and return combined results."""
        return {
            "summary": self.summarize(transcript),
            "action_items": self.extract_actions(transcript),
            "key_points": self.get_key_points(transcript),
            "topics": self.analyze_topics(transcript),
            "translation": self.translate(transcript),
            "dialogue": self.reconstruct_dialogue(transcript),
            "protocol": self.meeting_protocol(transcript),
        }
