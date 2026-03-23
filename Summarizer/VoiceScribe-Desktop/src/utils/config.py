import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings


def _get_project_root() -> Path:
    """Return project root — works both for dev and frozen (PyInstaller) exe."""
    if getattr(sys, "frozen", False):
        # Running as bundled exe: .env sits next to the .exe
        return Path(sys.executable).resolve().parent
    # Development: VoiceScribe-Desktop/src/utils/config.py → ../../
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _get_project_root()

# Load .env from project root (next to exe or repo root)
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
