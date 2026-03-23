"""
Local Uzbek speech-to-text using fine-tuned Whisper model.

Model: islomov/rubaistt_v2_medium (whisper-medium fine-tuned on 475h Uzbek audio)
  - WER ~17%, CER ~5.5%
  - 769M params, Tashkent dialect focus
  - Trained on: Common Voice 17, USC, FLEURS, YouTube podcasts/news/IT
  - 4k+ downloads/month — most popular Uzbek ASR model

Runs locally on GPU (CUDA) or CPU.
Downloads from HuggingFace ONCE, saves locally via save_pretrained(),
then loads from disk forever — no internet required.
"""
import threading
import numpy as np
from pathlib import Path

from transcription.engine import TranscriptionResult, TranscriptionSegment
from utils.logger import log

# Model ID on HuggingFace
_MODEL_ID = "islomov/rubaistt_v2_medium"

# Store models next to the project on D: drive (download once, reuse forever)
_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent  # VoiceScribe-Desktop/
_LOCAL_MODEL_DIR = _PROJECT_DIR / "models" / "rubaistt-v2-medium"


class UzbekTranscriber:
    """Local Uzbek ASR using rubaiSTT-v2 (Whisper-medium fine-tuned).

    islomov/rubaistt_v2_medium: 769M params, WER ~17%, CER ~5.5%
    Trained on 475 hours of diverse Uzbek audio.
    """

    def __init__(self, device: str = "auto"):
        self._device = device
        self._model = None
        self._processor = None
        self._ready = False
        self._loading = False
        self._lock = threading.Lock()
        self._torch_device = None
        self._dtype = None

    @property
    def is_ready(self) -> bool:
        return self._ready

    def load_model(self):
        """Load the Whisper-Uzbek model. Call from background thread."""
        if self._ready or self._loading:
            return
        self._loading = True

        try:
            import torch
            from transformers import (
                WhisperForConditionalGeneration,
                WhisperProcessor,
            )

            device_str = self._device
            if device_str == "auto":
                device_str = "cuda" if torch.cuda.is_available() else "cpu"

            self._torch_device = device_str
            self._dtype = torch.float16 if device_str == "cuda" else torch.float32

            log.info(f"Loading rubaiSTT-v2 Uzbek model on {device_str}...")

            marker = _LOCAL_MODEL_DIR / "config.json"

            if marker.exists():
                # ---- Load from local disk (fast, no internet) ----
                log.info(f"Loading from local: {_LOCAL_MODEL_DIR}")
                self._processor = WhisperProcessor.from_pretrained(str(_LOCAL_MODEL_DIR))
                self._model = WhisperForConditionalGeneration.from_pretrained(
                    str(_LOCAL_MODEL_DIR),
                    torch_dtype=self._dtype,
                ).to(device_str)
            else:
                # ---- First run: download from HuggingFace & save locally ----
                log.info(f"Downloading {_MODEL_ID} from HuggingFace (one-time)...")
                self._processor = WhisperProcessor.from_pretrained(_MODEL_ID)
                self._model = WhisperForConditionalGeneration.from_pretrained(
                    _MODEL_ID,
                    torch_dtype=self._dtype,
                ).to(device_str)

                _LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
                self._model.save_pretrained(str(_LOCAL_MODEL_DIR))
                self._processor.save_pretrained(str(_LOCAL_MODEL_DIR))
                log.info(f"Model saved to {_LOCAL_MODEL_DIR}")

            self._model.eval()

            # Smoke test
            dummy = np.zeros(16000, dtype=np.float32)
            self._transcribe_internal(dummy)

            self._ready = True
            log.info("rubaiSTT-v2 Uzbek model loaded successfully")

        except ImportError as e:
            log.warning(f"Whisper-Uzbek: missing dependency: {e}")
        except Exception as e:
            log.error(f"Whisper-Uzbek: failed to load: {e}")
        finally:
            self._loading = False

    def _transcribe_internal(self, audio: np.ndarray) -> str:
        """Low-level transcription using processor + model.generate()."""
        import torch

        input_features = self._processor(
            audio, sampling_rate=16000, return_tensors="pt",
        ).input_features.to(self._torch_device, dtype=self._dtype)

        with torch.no_grad():
            predicted_ids = self._model.generate(
                input_features,
                language="uz",
                task="transcribe",
                max_new_tokens=440,
            )

        text = self._processor.batch_decode(
            predicted_ids, skip_special_tokens=True,
        )[0].strip()
        return text

    def transcribe_numpy(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        """Transcribe numpy audio array using local rubaiSTT-v2."""
        if not self._ready or self._model is None:
            return TranscriptionResult(text="", segments=[], language="uz", duration=0.0)

        try:
            # Resample if needed
            if sample_rate != 16000:
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(16000, sample_rate)
                audio = resample_poly(audio, 16000 // g, sample_rate // g).astype(np.float32)

            text = self._transcribe_internal(audio)
            duration = len(audio) / 16000

            segments = [TranscriptionSegment(
                start=0.0,
                end=duration,
                text=text,
                language="uz",
            )]

            return TranscriptionResult(
                text=text,
                segments=segments,
                language="uz",
                duration=duration,
            )

        except Exception as e:
            log.error(f"Uzbek transcription error: {e}")
            return TranscriptionResult(text="", segments=[], language="uz", duration=0.0)
