"""
Local offline translation using CTranslate2 + NLLB-200.

Uses Meta's NLLB-200-distilled-600M model (~600MB CT2) for fast
translation between 200+ languages including Russian.
Falls back to OpenAI GPT if the local model isn't available.
"""
import os
import re
import threading
from pathlib import Path
from typing import Optional

from utils.logger import log

# Store models next to the project on D: drive (download once, reuse forever)
_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent  # VoiceScribe-Desktop/
_MODEL_DIR = _PROJECT_DIR / "models" / "nllb-200-distilled-600M"

# NLLB language codes
NLLB_LANG_CODES = {
    "ru": "rus_Cyrl",
    "en": "eng_Latn",
    "de": "deu_Latn",
    "fr": "fra_Latn",
    "es": "spa_Latn",
    "it": "ita_Latn",
    "pt": "por_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "ar": "arb_Arab",
    "tr": "tur_Latn",
    "pl": "pol_Latn",
    "uk": "ukr_Cyrl",
    "cs": "ces_Latn",
    "nl": "nld_Latn",
    "sv": "swe_Latn",
    "hi": "hin_Deva",
    "uz": "uzn_Latn",
    "kk": "kaz_Cyrl",
    "tg": "tgk_Cyrl",
}


class LocalTranslator:
    """Offline translator using CTranslate2 + NLLB-200.

    Downloads the model on first use. Provides near-instant translation
    on GPU or modern CPU.

    Falls back to OpenAI GPT if ctranslate2 is unavailable.
    """

    def __init__(self, model_dir: Optional[str] = None, device: str = "auto"):
        self._model_dir = Path(model_dir) if model_dir else _MODEL_DIR
        self._device = device
        self._translator = None
        self._tokenizer = None  # transformers AutoTokenizer
        self._ready = False
        self._loading = False
        self._lock = threading.Lock()

        # GPT fallback
        self._openai = None

    @property
    def is_ready(self) -> bool:
        return self._ready

    def load_model(self):
        """Load or download the NLLB-200 model. Can be called from a background thread."""
        if self._ready or self._loading:
            return
        self._loading = True

        try:
            import ctranslate2

            ct2_model_dir = self._model_dir / "ct2_model"

            if not ct2_model_dir.exists():
                log.info("NLLB-200 CT2 model not found. Converting...")
                self._download_and_convert()

            # Load CTranslate2 translator
            # Try CUDA with full test translation, fallback to CPU
            device = self._device
            if device == "auto":
                device = "cpu"
                if ctranslate2.get_cuda_device_count() > 0:
                    device = "cuda"

            log.info(f"Loading NLLB-200 translator on {device}...")
            try:
                self._translator = ctranslate2.Translator(
                    str(ct2_model_dir),
                    device=device,
                    compute_type="int8" if device == "cpu" else "float16",
                )
                # Quick smoke test — if CUDA libs are missing this will fail
                if device == "cuda":
                    self._translator.translate_batch([["eng_Latn", "▁test"]])
            except Exception as e:
                if device == "cuda":
                    log.info(f"CUDA failed ({e}), falling back to CPU")
                    device = "cpu"
                    self._translator = ctranslate2.Translator(
                        str(ct2_model_dir),
                        device="cpu",
                        compute_type="int8",
                    )
                else:
                    raise

            # Load tokenizer via transformers (handles NLLB's fast tokenizer)
            self._load_tokenizer()

            if self._tokenizer is not None:
                self._ready = True
                log.info("NLLB-200 translator loaded successfully")
            else:
                log.warning("Tokenizer failed to load. Using GPT fallback.")

        except ImportError as e:
            log.warning(f"CTranslate2 not available: {e}. Using GPT fallback.")
        except Exception as e:
            log.error(f"Failed to load NLLB-200: {e}. Using GPT fallback.")
        finally:
            self._loading = False

    def _load_tokenizer(self):
        """Load the NLLB tokenizer using transformers library."""
        try:
            from transformers import AutoTokenizer

            # Try loading from local saved tokenizer first
            tokenizer_dir = self._model_dir / "tokenizer"
            if tokenizer_dir.exists() and (tokenizer_dir / "tokenizer.json").exists():
                self._tokenizer = AutoTokenizer.from_pretrained(
                    str(tokenizer_dir), local_files_only=True
                )
                log.info("Loaded tokenizer from local cache")
                return

            # Download tokenizer from HuggingFace
            log.info("Downloading NLLB-200 tokenizer...")
            self._tokenizer = AutoTokenizer.from_pretrained(
                "facebook/nllb-200-distilled-600M"
            )
            # Save locally for future use
            tokenizer_dir.mkdir(parents=True, exist_ok=True)
            self._tokenizer.save_pretrained(str(tokenizer_dir))
            log.info("Tokenizer saved locally")

        except Exception as e:
            log.error(f"Tokenizer loading failed: {e}")
            self._tokenizer = None

    def _download_and_convert(self):
        """Download NLLB-200-distilled-600M and convert to CTranslate2 format."""
        self._model_dir.mkdir(parents=True, exist_ok=True)

        try:
            import ctranslate2

            hf_model_name = "facebook/nllb-200-distilled-600M"
            ct2_dir = str(self._model_dir / "ct2_model")

            log.info(f"Converting {hf_model_name} to CTranslate2 format...")

            # Use ct2-transformers-converter directly
            converter = ctranslate2.converters.TransformersConverter(hf_model_name)
            converter.convert(ct2_dir, quantization="int8")

            log.info("NLLB-200 model converted successfully")

        except Exception as e:
            log.error(f"Model conversion failed: {e}")
            raise

    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "ru",
    ) -> str:
        """Translate text. Uses local NLLB-200 if loaded, else GPT fallback."""
        if not text.strip():
            return text

        # Try local model first
        if self._ready and self._translator and self._tokenizer:
            return self._translate_local(text, source_lang, target_lang)

        # Fall back to GPT
        return self._translate_gpt(text, target_lang)

    def _translate_local(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """Translate using local CTranslate2 + NLLB-200."""
        try:
            src_code = NLLB_LANG_CODES.get(src_lang, f"{src_lang}_Latn")
            tgt_code = NLLB_LANG_CODES.get(tgt_lang, f"{tgt_lang}_Latn")

            # Set source language on tokenizer
            self._tokenizer.src_lang = src_code

            # Split into sentences for better translation
            sentences = re.split(r'(?<=[.!?])\s+', text.strip())
            translated_parts = []

            for sentence in sentences:
                if not sentence.strip():
                    continue

                # Tokenize using transformers tokenizer
                inputs = self._tokenizer(sentence, return_tensors=None)
                input_ids = inputs["input_ids"]

                # Convert IDs to tokens for CTranslate2
                tokens = self._tokenizer.convert_ids_to_tokens(input_ids)

                # Translate with CTranslate2
                results = self._translator.translate_batch(
                    [tokens],
                    target_prefix=[[tgt_code]],
                    beam_size=4,
                    max_decoding_length=512,
                )

                # Decode — skip the target language token
                translated_tokens = results[0].hypotheses[0]
                if translated_tokens and translated_tokens[0] == tgt_code:
                    translated_tokens = translated_tokens[1:]

                # Remove EOS token
                if translated_tokens and translated_tokens[-1] == "</s>":
                    translated_tokens = translated_tokens[:-1]

                # Convert tokens back to text
                token_ids = self._tokenizer.convert_tokens_to_ids(translated_tokens)
                translated_text = self._tokenizer.decode(token_ids, skip_special_tokens=True)
                translated_parts.append(translated_text)

            return " ".join(translated_parts)

        except Exception as e:
            log.error(f"Local translation error: {e}")
            return self._translate_gpt(text, tgt_lang)

    def _translate_gpt(self, text: str, target_lang: str = "ru") -> str:
        """Fallback: translate using OpenAI GPT."""
        try:
            if self._openai is None:
                from openai import OpenAI
                from utils.config import settings
                self._openai = OpenAI(api_key=settings.OPENAI_API_KEY)

            lang_name = {
                "ru": "русский", "en": "английский", "de": "немецкий",
                "fr": "французский", "es": "испанский",
            }.get(target_lang, target_lang)

            response = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Ты точный переводчик. Переводи на {lang_name} язык."},
                    {"role": "user", "content": f"Переведи на {lang_name}. Верни ТОЛЬКО перевод.\n\n{text}"},
                ],
                temperature=0.2,
                max_tokens=2000,
            )
            return (response.choices[0].message.content or text).strip()
        except Exception as e:
            log.error(f"GPT translation fallback error: {e}")
            return text

    def translate_sentences(
        self,
        sentences: list[str],
        source_lang: str = "en",
        target_lang: str = "ru",
    ) -> list[str]:
        """Translate a list of sentences, returning parallel list."""
        return [self.translate(s, source_lang, target_lang) for s in sentences]
