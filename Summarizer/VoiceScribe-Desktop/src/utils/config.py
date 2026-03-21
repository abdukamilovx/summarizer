import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Project root is VoiceScribe-Desktop/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env from project root
_env_file = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str = ""
    WHISPER_MODEL: str = "whisper-1"
    ANALYSIS_MODEL: str = "gpt-4o"

    # Audio
    SAMPLE_RATE: int = 16000
    CHUNK_DURATION_SEC: int = 30

    # UI
    APPEARANCE_MODE: str = "dark"
    COLOR_THEME: str = "blue"

    model_config = {"env_file": str(_env_file), "env_file_encoding": "utf-8"}


settings = Settings()
