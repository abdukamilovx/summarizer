"""
Main application window for VoiceScribe Desktop.

Timekettle-style multi-panel layout:
  Panel 1: Live raw transcription (<1s latency)
  Panel 2: Live translation of raw text
  Panel 3: AI-corrected transcription with speakers
  Panel 4: Translation of corrected text
  Panel 5: Analysis (popup window on button click)
"""
import customtkinter as ctk
import numpy as np
import threading
from tkinter import filedialog
from typing import Optional

from audio.capture import AudioCapture, AudioChunk, WAV_SAMPLE_RATE
# AudioMixer removed — raw audio passed directly
from audio.preprocessor import enhance_speech
from transcription.whisper_api import WhisperAPITranscriber
from transcription.streaming import StreamingTranscriber
from transcription.corrector import TranscriptCorrector
from transcription.engine import TranscriptionResult
from analysis.summarizer import Summarizer
from ui.recording_panel import RecordingPanel
from ui.transcript_view import TranscriptMultiView, AnalysisWindow
from ui.components.waveform import WaveformCanvas
from utils.config import settings
from utils.storage import Storage
from utils.logger import log

import soundfile as sf


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VoiceScribe — Sync Transcription")
        self.geometry("1400x850")
        self.minsize(1000, 650)

        # State
        self._audio_capture: Optional[AudioCapture] = None
        # No mixer — direct audio
        self._audio_buffer: list[np.ndarray] = []
        self._hq_audio_buffer: list[np.ndarray] = []
        self._transcription_result: Optional[TranscriptionResult] = None
        self._streaming_transcriber: Optional[StreamingTranscriber] = None
        self._current_rec_id: Optional[str] = None
        self._is_stopping = False
        self._corrector: Optional[TranscriptCorrector] = None
        self._analysis_window: Optional[AnalysisWindow] = None

        # Local translator (loaded in background)
        self._local_translator = None

        # Services (lazy init)
        self._transcriber: Optional[WhisperAPITranscriber] = None
        self._summarizer: Optional[Summarizer] = None
        self._storage = Storage()

        self._build_ui()
        self._init_local_translator()

    # -- Services --

    @property
    def transcriber(self) -> WhisperAPITranscriber:
        if self._transcriber is None:
            self._transcriber = WhisperAPITranscriber()
        return self._transcriber

    @property
    def summarizer(self) -> Summarizer:
        if self._summarizer is None:
            self._summarizer = Summarizer()
        return self._summarizer

    def _init_local_translator(self):
        def load():
            try:
                from translation.local_translator import LocalTranslator
                self._local_translator = LocalTranslator()
                self._local_translator.load_model()
                if self._local_translator.is_ready:
                    log.info("Local NLLB-200 translator ready")
                else:
                    log.info("Local translator not available, will use GPT fallback")
            except Exception as e:
                log.warning(f"Local translator init failed: {e}")

        threading.Thread(target=load, daemon=True).start()

    # -- UI --

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Row 0: Recording controls
        self.recording_panel = RecordingPanel(
            self,
            on_start=self._on_start_recording,
            on_stop=self._on_stop_recording,
        )
        self.recording_panel.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        # Row 1: Waveform
        self.waveform = WaveformCanvas(self, height=60)
        self.waveform.grid(row=1, column=0, sticky="ew", padx=10, pady=2)

        # Row 2: 4-panel transcript view (fills all available space)
        self.transcript_view = TranscriptMultiView(self, fg_color="transparent")
        self.transcript_view.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

        # Row 3: Bottom controls
        bottom = ctk.CTkFrame(self)
        bottom.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))

        ctk.CTkButton(
            bottom, text="\U0001f4c4 TXT",
            command=lambda: self._export("txt"), width=80,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            bottom, text="\U0001f3ac SRT",
            command=lambda: self._export("srt"), width=80,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            bottom, text="\U0001f4c2 Load",
            command=self._load_file, width=90,
        ).pack(side="left", padx=4)

        # Multi-language selector (up to 4 languages)
        ctk.CTkLabel(bottom, text="Lang:", font=("Segoe UI", 12)).pack(side="left", padx=(4, 2))
        lang_values = [
            "—", "Auto", "English", "Russian", "Uzbek",
            "Chinese", "Japanese", "Korean",
            "German", "French", "Spanish",
            "Turkish", "Arabic", "Hindi",
            "Italian", "Portuguese", "Ukrainian",
        ]
        self._lang_vars: list[ctk.StringVar] = []
        self._lang_menus: list[ctk.CTkOptionMenu] = []
        for i in range(4):
            var = ctk.StringVar(value="Auto" if i == 0 else "—")
            menu = ctk.CTkOptionMenu(
                bottom, variable=var, width=85, values=lang_values,
                font=("Segoe UI", 11),
            )
            menu.pack(side="left", padx=1)
            self._lang_vars.append(var)
            self._lang_menus.append(menu)

        ctk.CTkLabel(bottom, text="|", text_color="gray").pack(side="left", padx=4)

        # Audio source toggles
        self._mic_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            bottom, text="\U0001f3a4 Mic",
            variable=self._mic_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=6)

        self._system_audio_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            bottom, text="\U0001f50a System",
            variable=self._system_audio_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=6)

        ctk.CTkLabel(bottom, text="|", text_color="gray").pack(side="left", padx=4)

        # Feature toggles
        self._realtime_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            bottom, text="Real-time",
            variable=self._realtime_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=6)

        self._translate_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            bottom, text="\U0001f310 Translate",
            variable=self._translate_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=6)

        self._denoise_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            bottom, text="Denoise",
            variable=self._denoise_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=6)

        self._correction_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            bottom, text="Correct",
            variable=self._correction_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=6)

        self._diarize_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            bottom, text="Speakers",
            variable=self._diarize_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=6)

        # Right side buttons
        self.analyze_btn = ctk.CTkButton(
            bottom, text="\U0001f916 Analyze",
            command=self._run_analysis, width=130,
            fg_color="#7C3AED", hover_color="#5B21B6",
        )
        self.analyze_btn.pack(side="right", padx=4)

        self.transcribe_btn = ctk.CTkButton(
            bottom, text="\U0001f4ac Transcribe",
            command=self._transcribe_buffer, width=140,
            fg_color="#0D9488", hover_color="#065F53",
        )
        self.transcribe_btn.pack(side="right", padx=4)

    # -- Recording --

    def _on_start_recording(self):
        log.info("Starting recording...")
        self._audio_buffer.clear()
        self._hq_audio_buffer.clear()
        self.transcript_view.clear()
        self.waveform.reset()

        do_translate = self._translate_var.get()
        do_correct = self._correction_var.get()
        do_denoise = self._denoise_var.get()
        whisper_lang = self._get_whisper_language()
        whisper_prompt = self._get_whisper_prompt()

        # Corrector for periodic self-healing
        self._corrector = None
        if do_correct:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_path = str(Storage.get_audio_dir() / f"{ts}_raw.txt")
            self._corrector = TranscriptCorrector(
                raw_file_path=raw_path,
                correction_interval=3,
                on_corrected=self._on_periodic_correction,
            )

        # Start streaming transcriber with 4-panel callbacks
        if self._realtime_var.get() and settings.OPENAI_API_KEY:
            self._streaming_transcriber = StreamingTranscriber(
                transcriber=self.transcriber,
                sample_rate=settings.SAMPLE_RATE,
                fast_interval=5.0,
                group_size=2,
                language=whisper_lang,
                prompt=whisper_prompt,
                # 4-panel callbacks
                on_raw_text=self._on_raw_text,
                on_raw_translation=self._on_raw_translation if do_translate else None,
                on_corrected=self._on_corrected if do_correct else None,
                on_corrected_translation=(
                    self._on_corrected_translation
                    if (do_translate and do_correct) else None
                ),
                # Settings
                translate_to_russian=do_translate,
                noise_reduction=do_denoise,
                corrector=self._corrector,
                local_translator=self._local_translator,
                live_correction=do_correct,
            )
            self._streaming_transcriber.start()
            selected_langs = self._get_selected_languages()
            log.info(
                "Real-time ON (langs=%s, prompt=%s, translate=%s, correct=%s, denoise=%s)",
                selected_langs or ["auto"], bool(whisper_prompt),
                do_translate, do_correct, do_denoise,
            )

        # Start audio capture (respect toggles)
        do_mic = self._mic_var.get()
        do_system = self._system_audio_var.get()
        if not do_mic and not do_system:
            do_mic = True
        self._audio_capture = AudioCapture(
            sample_rate=settings.SAMPLE_RATE,
            chunk_duration=0.1,
            capture_microphone=do_mic,
            capture_system=do_system,
        )
        self._audio_capture.on_audio(self._on_audio_chunk)
        self._audio_capture.on_hq_audio(self._on_hq_audio_chunk)

        try:
            self._audio_capture.start()
        except Exception as e:
            log.error(f"Failed to start capture: {e}")
            self.recording_panel.status_label.configure(
                text=f"Error: {e}", text_color="#E53935",
            )

    def _on_stop_recording(self):
        if self._is_stopping:
            return
        self._is_stopping = True
        log.info("Stopping recording...")

        if self._audio_capture:
            self._audio_capture.stop()
            self._audio_capture = None

        self.recording_panel.status_label.configure(
            text="\u23f3 Finishing...", text_color="#FF9800",
        )

        def finalize():
            try:
                if self._streaming_transcriber:
                    result = self._streaming_transcriber.stop()
                    self._transcription_result = result
                    self._streaming_transcriber = None

                    # Speaker diarization
                    if self._diarize_var.get() and result.segments and self._audio_buffer:
                        self.after(0, lambda: self.recording_panel.status_label.configure(
                            text="\U0001f3a4 Detecting speakers...",
                            text_color="#FF9800",
                        ))
                        from transcription.diarizer import SpeakerDiarizer
                        diarizer = SpeakerDiarizer(sample_rate=settings.SAMPLE_RATE)
                        full_audio = np.concatenate(self._audio_buffer)
                        result.segments = diarizer.diarize(full_audio, result.segments)
                        self._transcription_result = result

                    # Force final correction
                    if self._corrector and result.segments:
                        labeled_chunks = []
                        for seg in result.segments:
                            prefix = f"[{seg.speaker}]: " if seg.speaker else ""
                            labeled_chunks.append(f"{prefix}{seg.text.strip()}")
                        self._corrector.replace_chunks(labeled_chunks)
                        self._corrector.force_correction()

                total_samples = sum(len(b) for b in self._audio_buffer)
                duration = total_samples / settings.SAMPLE_RATE
                log.info(f"Recording stopped. Duration: {duration:.1f}s")

                if self._audio_buffer and duration > 0.5:
                    self._save_recording(duration)

                self.after(0, lambda: self.recording_panel.status_label.configure(
                    text="Recording complete", text_color="#4CAF50",
                ))
            except Exception as e:
                log.error(f"Finalization error: {e}")
                self.after(0, self._show_error, f"Error: {e}")
            finally:
                self._is_stopping = False

        threading.Thread(target=finalize, daemon=True).start()

    # -- Audio callbacks --

    def _on_audio_chunk(self, chunk: AudioChunk):
        self._audio_buffer.append(chunk.data)

        if self._streaming_transcriber:
            self._streaming_transcriber.add_audio(chunk.data)

        rms = float(np.sqrt(np.mean(chunk.data ** 2)))
        level = min(1.0, rms * 10)
        self.after(0, self.waveform.push_level, level)

    def _on_hq_audio_chunk(self, chunk: AudioChunk):
        self._hq_audio_buffer.append(chunk.data)

    # -- Panel callbacks --

    def _on_raw_text(self, text: str, speaker: Optional[str] = None):
        """Panel 1: instant raw transcription."""
        self.after(0, self.transcript_view.append_raw, text, speaker)

    def _on_raw_translation(self, translated_text: str):
        """Panel 2: instant translation of raw text."""
        self.after(0, self.transcript_view.append_raw_translation, translated_text)

    def _on_corrected(self, corrected_text: str, speaker: Optional[str] = None):
        """Panel 3: AI-corrected text with speakers."""
        self.after(0, self.transcript_view.append_corrected, corrected_text, speaker)

    def _on_corrected_translation(self, translated_text: str):
        """Panel 4: translation of corrected text."""
        self.after(0, self.transcript_view.append_corrected_translation, translated_text)

    def _on_periodic_correction(self, corrected_text: str):
        """Periodic correction from TranscriptCorrector — update Panel 3."""
        def update():
            self.transcript_view.set_corrected(corrected_text)
            self.recording_panel.status_label.configure(
                text="\u2705 Text corrected", text_color="#4CAF50",
            )
        self.after(0, update)

    # -- Transcription (manual / file) --

    def _transcribe_buffer(self):
        if not self._audio_buffer:
            log.warning("No audio to transcribe")
            return

        self.transcribe_btn.configure(
            state="disabled", text="\u23f3 Transcribing...",
        )

        def do_transcribe():
            try:
                audio = np.concatenate(self._audio_buffer)
                log.info(f"Transcribing {len(audio)/settings.SAMPLE_RATE:.1f}s...")

                if self._denoise_var.get():
                    audio = enhance_speech(audio, settings.SAMPLE_RATE)

                result = self.transcriber.transcribe_numpy(
                    audio, sample_rate=settings.SAMPLE_RATE,
                )
                self._transcription_result = result
                self.after(0, self._show_transcription, result)
            except Exception as e:
                log.error(f"Transcription failed: {e}")
                self.after(0, self._show_error, f"Error: {e}")
            finally:
                self.after(0, lambda: self.transcribe_btn.configure(
                    state="normal", text="\U0001f4ac Transcribe",
                ))

        threading.Thread(target=do_transcribe, daemon=True).start()

    def _show_transcription(self, result: TranscriptionResult):
        self.transcript_view.clear()
        if result.segments:
            for seg in result.segments:
                self.transcript_view.append_raw(seg.text, speaker=seg.speaker)
        else:
            self.transcript_view.panel_raw.set_text(result.text)
        log.info(f"Transcription complete. Language: {result.language}")

    # -- Analysis (Panel 5 — popup window) --

    def _run_analysis(self):
        text = self.transcript_view.get_text()
        if not text.strip():
            log.warning("No transcript to analyze")
            return

        # Create or bring to front analysis window
        if self._analysis_window is None or not self._analysis_window.winfo_exists():
            self._analysis_window = AnalysisWindow(self)
        else:
            self._analysis_window.focus()

        self._analysis_window.clear()
        self.analyze_btn.configure(state="disabled", text="\u23f3 Analyzing...")

        def do_analysis():
            try:
                result = self.summarizer.full_analysis(text)

                def update_ui():
                    if self._analysis_window and self._analysis_window.winfo_exists():
                        self._analysis_window.set_summary(result.get("summary", ""))
                        self._analysis_window.set_actions(result.get("action_items", []))
                        self._analysis_window.set_key_points(result.get("key_points", []))

                        translation = result.get("translation", "")
                        if translation:
                            self._analysis_window.set_translation(text, translation)

                        dialogue = result.get("dialogue", "")
                        if dialogue:
                            self._analysis_window.set_dialogue(dialogue)

                self.after(0, update_ui)

                if self._current_rec_id:
                    import json
                    self._storage.update_recording(
                        self._current_rec_id,
                        summary=result.get("summary", ""),
                        action_items_json=json.dumps(
                            result.get("action_items", []), ensure_ascii=False,
                        ),
                        key_points_json=json.dumps(
                            result.get("key_points", []), ensure_ascii=False,
                        ),
                    )

                log.info("Analysis complete")
            except Exception as e:
                log.error(f"Analysis failed: {e}")
                self.after(0, self._show_error, f"Analysis error: {e}")
            finally:
                self.after(0, lambda: self.analyze_btn.configure(
                    state="normal", text="\U0001f916 Analyze",
                ))

        threading.Thread(target=do_analysis, daemon=True).start()

    # -- Storage --

    def _save_recording(self, duration: float):
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = f"Recording {timestamp}"
        audio_dir = Storage.get_audio_dir()
        audio_path = str(audio_dir / f"{timestamp}.wav")

        if self._hq_audio_buffer:
            hq_audio = np.concatenate(self._hq_audio_buffer)
            sf.write(audio_path, hq_audio, WAV_SAMPLE_RATE)
            log.info(f"Saved HQ WAV at {WAV_SAMPLE_RATE}Hz")
        else:
            audio = np.concatenate(self._audio_buffer)
            sf.write(audio_path, audio, settings.SAMPLE_RATE)

        transcript = ""
        segments = []
        language = ""
        if self._transcription_result:
            transcript = self._transcription_result.text
            segments = [
                {"start": s.start, "end": s.end, "text": s.text, "speaker": s.speaker}
                for s in self._transcription_result.segments
            ]
            language = self._transcription_result.language

        self._current_rec_id = self._storage.save_recording(
            title=title,
            duration_sec=duration,
            audio_path=audio_path,
            transcript=transcript,
            language=language,
            segments=segments,
        )
        log.info(f"Recording saved: {self._current_rec_id}")

    # -- File Loading --

    def _load_file(self):
        filepath = filedialog.askopenfilename(
            filetypes=[
                ("Audio", "*.wav *.mp3 *.m4a *.ogg *.flac *.webm"),
                ("All", "*.*"),
            ],
        )
        if not filepath:
            return

        self.transcribe_btn.configure(state="disabled", text="\u23f3 Transcribing...")
        self.transcript_view.clear()

        def do_transcribe():
            try:
                result = self.transcriber.transcribe_file(filepath)
                self._transcription_result = result

                if result.text.strip():
                    try:
                        batch_result = self.summarizer.batch_diarize(result.text)
                        if batch_result.strip():
                            result = TranscriptionResult(
                                text=batch_result,
                                segments=result.segments,
                                language=result.language,
                                duration=result.duration,
                            )
                            self._transcription_result = result
                    except Exception as e:
                        log.warning(f"Batch diarization failed: {e}")

                self.after(0, self._show_transcription, result)
            except Exception as e:
                log.error(f"File transcription failed: {e}")
                self.after(0, self._show_error, f"Error: {e}")
            finally:
                self.after(0, lambda: self.transcribe_btn.configure(
                    state="normal", text="\U0001f4ac Transcribe",
                ))

        threading.Thread(target=do_transcribe, daemon=True).start()

    # -- Export --

    def _export(self, fmt: str):
        text = self.transcript_view.get_text()
        if not text.strip():
            return

        ext_map = {"txt": ".txt", "srt": ".srt"}
        filepath = filedialog.asksaveasfilename(
            defaultextension=ext_map.get(fmt, ".txt"),
            filetypes=[(f"{fmt.upper()}", f"*{ext_map.get(fmt, '.txt')}")],
        )
        if not filepath:
            return

        from utils.export import export_transcript
        segments = self._transcription_result.segments if self._transcription_result else []
        export_transcript(text, segments, filepath, fmt)
        log.info(f"Exported to {filepath}")

    # -- Helpers --

    _LANG_MAP = {
        "Auto": None, "—": None,
        "English": "en", "Russian": "ru", "Uzbek": "uz",
        "Chinese": "zh", "Japanese": "ja", "Korean": "ko",
        "German": "de", "French": "fr", "Spanish": "es",
        "Turkish": "tr", "Arabic": "ar", "Hindi": "hi",
        "Italian": "it", "Portuguese": "pt", "Ukrainian": "uk",
    }

    # Prompt hints for languages that Whisper struggles with
    _LANG_PROMPTS = {
        "uz": "Assalomu alaykum. Bugun biz muhim masalalarni muhokama qilamiz.",
        "ru": "Здравствуйте. Сегодня мы обсудим важные вопросы.",
        "en": "Hello. Today we will discuss important matters.",
        "zh": "你好。今天我们将讨论重要的事情。",
        "ja": "こんにちは。今日は重要なことについて話し合います。",
        "ko": "안녕하세요. 오늘 중요한 사항을 논의하겠습니다.",
        "ar": "مرحبا. اليوم سنناقش أمور مهمة.",
        "hi": "नमस्ते। आज हम महत्वपूर्ण मुद्दों पर चर्चा करेंगे।",
        "tr": "Merhaba. Bugün önemli konuları tartışacağız.",
    }

    def _get_selected_languages(self) -> list[str]:
        """Return list of selected ISO language codes (no duplicates, no None)."""
        langs = []
        seen = set()
        for var in self._lang_vars:
            code = self._LANG_MAP.get(var.get())
            if code and code not in seen:
                langs.append(code)
                seen.add(code)
        return langs

    def _get_whisper_language(self) -> Optional[str]:
        """Return single language for Whisper API, or None for auto-detect."""
        langs = self._get_selected_languages()
        if len(langs) == 1:
            return langs[0]
        # Multiple languages or Auto → let Whisper auto-detect
        return None

    def _get_whisper_prompt(self) -> Optional[str]:
        """Build prompt hint for Whisper to improve recognition of selected languages."""
        langs = self._get_selected_languages()
        if not langs:
            return None
        # Build combined prompt from all selected languages
        hints = []
        for lang in langs:
            if lang in self._LANG_PROMPTS:
                hints.append(self._LANG_PROMPTS[lang])
        return " ".join(hints) if hints else None

    def _show_error(self, message: str):
        self.recording_panel.status_label.configure(text=message, text_color="#E53935")
