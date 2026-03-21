"""
Main application window for VoiceScribe Desktop.

Instant transcription with incremental corrections and translation.
"""
import customtkinter as ctk
import numpy as np
import threading
from tkinter import filedialog
from typing import Optional

from audio.capture import AudioCapture, AudioChunk, WAV_SAMPLE_RATE
from audio.mixer import AudioMixer
from audio.preprocessor import enhance_speech
from transcription.whisper_api import WhisperAPITranscriber
from transcription.streaming import StreamingTranscriber
from transcription.corrector import TranscriptCorrector
from transcription.engine import TranscriptionResult
from analysis.summarizer import Summarizer
from ui.recording_panel import RecordingPanel
from ui.transcript_view import TranscriptView, AnalysisPanel
from ui.components.waveform import WaveformCanvas
from utils.config import settings
from utils.storage import Storage
from utils.logger import log

import soundfile as sf


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VoiceScribe")
        self.geometry("1280x800")
        self.minsize(900, 600)

        # State
        self._audio_capture: Optional[AudioCapture] = None
        self._mixer = AudioMixer()
        self._audio_buffer: list[np.ndarray] = []
        self._hq_audio_buffer: list[np.ndarray] = []
        self._transcription_result: Optional[TranscriptionResult] = None
        self._streaming_transcriber: Optional[StreamingTranscriber] = None
        self._current_rec_id: Optional[str] = None
        self._is_stopping = False
        self._corrector: Optional[TranscriptCorrector] = None

        # Local translator (loaded in background)
        self._local_translator = None

        # Services (lazy init)
        self._transcriber: Optional[WhisperAPITranscriber] = None
        self._summarizer: Optional[Summarizer] = None
        self._storage = Storage()

        self._build_ui()
        self._init_local_translator()

    # ── Services ──

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
        """Load NLLB-200 translator in background."""
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

    # ── UI ──

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Top: recording controls
        self.recording_panel = RecordingPanel(
            self,
            on_start=self._on_start_recording,
            on_stop=self._on_stop_recording,
        )
        self.recording_panel.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        # Waveform
        self.waveform = WaveformCanvas(self, height=80)
        self.waveform.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        # Main content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        self.transcript_view = TranscriptView(content)
        self.transcript_view.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.analysis_panel = AnalysisPanel(content)
        self.analysis_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        # Bottom: action buttons
        bottom = ctk.CTkFrame(self)
        bottom.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))

        ctk.CTkButton(
            bottom, text="\U0001f4c4 TXT",
            command=lambda: self._export("txt"), width=100,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            bottom, text="\U0001f3ac SRT",
            command=lambda: self._export("srt"), width=100,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            bottom,
            text="\U0001f4c2 \u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c",
            command=self._load_file, width=130,
        ).pack(side="left", padx=5)

        # Toggles
        self._realtime_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            bottom, text="Real-time",
            variable=self._realtime_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=10)

        self._translate_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            bottom,
            text="\U0001f310 \u041f\u0435\u0440\u0435\u0432\u043e\u0434 \u043d\u0430 RU",
            variable=self._translate_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=10)

        self._denoise_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            bottom,
            text="\U0001f50a \u0428\u0443\u043c\u043e\u043f\u043e\u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435",
            variable=self._denoise_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=10)

        self._correction_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            bottom,
            text="\u270f\ufe0f \u0410\u0432\u0442\u043e\u043a\u043e\u0440\u0440\u0435\u043a\u0446\u0438\u044f",
            variable=self._correction_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=10)

        self._diarize_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            bottom,
            text="\U0001f3a4 \u0421\u043f\u0438\u043a\u0435\u0440\u044b",
            variable=self._diarize_var, onvalue=True, offvalue=False,
        ).pack(side="left", padx=10)

        self.analyze_btn = ctk.CTkButton(
            bottom,
            text="\U0001f916 \u0410\u043d\u0430\u043b\u0438\u0437",
            command=self._run_analysis, width=150,
            fg_color="#7C3AED", hover_color="#5B21B6",
        )
        self.analyze_btn.pack(side="right", padx=5)

        self.transcribe_btn = ctk.CTkButton(
            bottom,
            text="\U0001f4ac \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
            command=self._transcribe_buffer, width=180,
            fg_color="#0D9488", hover_color="#065F53",
        )
        self.transcribe_btn.pack(side="right", padx=5)

    # ── Recording ──

    def _on_start_recording(self):
        log.info("Starting recording...")
        self._audio_buffer.clear()
        self._hq_audio_buffer.clear()
        self.transcript_view.clear()
        self.analysis_panel.clear()
        self.waveform.reset()

        # Read toggle states ONCE at start
        do_translate = self._translate_var.get()
        do_correct = self._correction_var.get()
        do_denoise = self._denoise_var.get()

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

        # Start streaming transcriber (dual-path: 1-sec fast + 5-sec re-transcription)
        if self._realtime_var.get() and settings.OPENAI_API_KEY:
            self._streaming_transcriber = StreamingTranscriber(
                transcriber=self.transcriber,
                sample_rate=settings.SAMPLE_RATE,
                fast_interval=1.0,
                group_size=5,
                # Callbacks
                on_text=self._on_instant_text,
                on_group_done=self._on_group_done if (do_correct or do_translate) else None,
                on_instant_translation=self._on_instant_translation if (do_translate and not do_correct) else None,
                # Settings
                translate_to_russian=do_translate,
                noise_reduction=do_denoise,
                corrector=self._corrector,
                local_translator=self._local_translator,
                live_correction=do_correct,
            )
            self._streaming_transcriber.start()
            log.info(
                "Real-time ON (translate=%s, correct=%s, denoise=%s)",
                do_translate, do_correct, do_denoise,
            )

        # Start audio capture
        self._audio_capture = AudioCapture(
            sample_rate=settings.SAMPLE_RATE,
            chunk_duration=0.1,
            capture_microphone=True,
            capture_system=True,
        )
        self._audio_capture.on_audio(self._on_audio_chunk)
        self._audio_capture.on_hq_audio(self._on_hq_audio_chunk)

        try:
            self._audio_capture.start()
        except Exception as e:
            log.error(f"Failed to start capture: {e}")
            self.recording_panel.status_label.configure(
                text=f"\u041e\u0448\u0438\u0431\u043a\u0430: {e}", text_color="#E53935"
            )

    def _on_stop_recording(self):
        if self._is_stopping:
            return
        self._is_stopping = True
        log.info("Stopping recording...")

        if self._audio_capture:
            self._audio_capture.stop()
            self._audio_capture = None

        flushed = self._mixer.flush(settings.SAMPLE_RATE)
        if flushed:
            self._audio_buffer.append(flushed.data)

        self.recording_panel.status_label.configure(
            text="\u23f3 \u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u0435...",
            text_color="#FF9800",
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
                            text="\U0001f3a4 \u041e\u043f\u0440\u0435\u0434\u0435\u043b\u0435\u043d\u0438\u0435 \u0441\u043f\u0438\u043a\u0435\u0440\u043e\u0432...",
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
                    text="\u0417\u0430\u043f\u0438\u0441\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430",
                    text_color="#4CAF50",
                ))
            except Exception as e:
                log.error(f"Finalization error: {e}")
                self.after(0, self._show_error, f"\u041e\u0448\u0438\u0431\u043a\u0430: {e}")
            finally:
                self._is_stopping = False

        threading.Thread(target=finalize, daemon=True).start()

    # ── Audio callbacks ──

    def _on_audio_chunk(self, chunk: AudioChunk):
        mixed = self._mixer.add_chunk(chunk)
        if mixed is not None:
            self._audio_buffer.append(mixed.data)

            if self._streaming_transcriber:
                self._streaming_transcriber.add_audio(mixed.data)

            rms = float(np.sqrt(np.mean(mixed.data ** 2)))
            level = min(1.0, rms * 10)
            self.after(0, self.waveform.push_level, level)

    def _on_hq_audio_chunk(self, chunk: AudioChunk):
        self._hq_audio_buffer.append(chunk.data)

    # ── Streaming callbacks ──

    def _on_instant_text(self, text: str, speaker: Optional[str] = None):
        """Text appears INSTANTLY from 1-sec Whisper chunk."""
        self.after(0, self.transcript_view.append_text, text, speaker)

    def _on_group_done(
        self,
        block_start: int,
        block_end: int,
        corrected_text: str,
        translated_text: Optional[str],
        speaker: Optional[str],
    ):
        """Group of blocks replaced with corrected text + translation."""
        self.after(
            0,
            self.transcript_view.update_block_group,
            block_start, block_end, corrected_text, translated_text, speaker,
        )

    def _on_instant_translation(self, translated_text: str):
        """Per-chunk translation (when correction is off)."""
        self.after(0, self.transcript_view.append_translation, translated_text)

    def _on_periodic_correction(self, corrected_text: str):
        """Periodic correction from TranscriptCorrector — update display."""
        def update():
            self.transcript_view.set_text(corrected_text)
            self.recording_panel.status_label.configure(
                text="\u2705 \u0422\u0435\u043a\u0441\u0442 \u0441\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d",
                text_color="#4CAF50",
            )
        self.after(0, update)

    # ── Transcription ──

    def _transcribe_buffer(self):
        if not self._audio_buffer:
            log.warning("No audio to transcribe")
            return

        self.transcribe_btn.configure(
            state="disabled", text="\u23f3 \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f..."
        )

        def do_transcribe():
            try:
                audio = np.concatenate(self._audio_buffer)
                log.info(f"Transcribing {len(audio)/settings.SAMPLE_RATE:.1f}s...")

                if self._denoise_var.get():
                    audio = enhance_speech(audio, settings.SAMPLE_RATE)

                result = self.transcriber.transcribe_numpy(
                    audio, sample_rate=settings.SAMPLE_RATE
                )
                self._transcription_result = result
                self.after(0, self._show_transcription, result)
            except Exception as e:
                log.error(f"Transcription failed: {e}")
                self.after(0, self._show_error, f"\u041e\u0448\u0438\u0431\u043a\u0430: {e}")
            finally:
                self.after(0, lambda: self.transcribe_btn.configure(
                    state="normal",
                    text="\U0001f4ac \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
                ))

        threading.Thread(target=do_transcribe, daemon=True).start()

    def _show_transcription(self, result: TranscriptionResult):
        self.transcript_view.clear()
        if result.segments:
            for seg in result.segments:
                self.transcript_view.append_text(seg.text, speaker=seg.speaker)
        else:
            self.transcript_view.set_text(result.text)
        log.info(f"Transcription complete. Language: {result.language}")

    # ── Analysis ──

    def _run_analysis(self):
        text = self.transcript_view.get_text()
        if not text.strip():
            log.warning("No transcript to analyze")
            return

        self.analyze_btn.configure(state="disabled", text="\u23f3 \u0410\u043d\u0430\u043b\u0438\u0437...")

        def do_analysis():
            try:
                result = self.summarizer.full_analysis(text)

                self.after(0, self.analysis_panel.set_summary, result.get("summary", ""))
                self.after(0, self.analysis_panel.set_actions, result.get("action_items", []))
                self.after(0, self.analysis_panel.set_key_points, result.get("key_points", []))

                translation = result.get("translation", "")
                if translation:
                    self.after(0, self.analysis_panel.set_translation, text, translation)

                dialogue = result.get("dialogue", "")
                if dialogue:
                    self.after(0, self.analysis_panel.set_dialogue, dialogue)

                if self._current_rec_id:
                    import json
                    self._storage.update_recording(
                        self._current_rec_id,
                        summary=result.get("summary", ""),
                        action_items_json=json.dumps(
                            result.get("action_items", []), ensure_ascii=False
                        ),
                        key_points_json=json.dumps(
                            result.get("key_points", []), ensure_ascii=False
                        ),
                    )

                log.info("Analysis complete")
            except Exception as e:
                log.error(f"Analysis failed: {e}")
                self.after(0, self._show_error, f"\u041e\u0448\u0438\u0431\u043a\u0430 \u0430\u043d\u0430\u043b\u0438\u0437\u0430: {e}")
            finally:
                self.after(0, lambda: self.analyze_btn.configure(
                    state="normal", text="\U0001f916 \u0410\u043d\u0430\u043b\u0438\u0437"
                ))

        threading.Thread(target=do_analysis, daemon=True).start()

    # ── Storage ──

    def _save_recording(self, duration: float):
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = f"Recording {timestamp}"
        audio_dir = Storage.get_audio_dir()
        audio_path = str(audio_dir / f"{timestamp}.wav")

        # High-quality WAV (44.1kHz)
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

    # ── File Loading ──

    def _load_file(self):
        filepath = filedialog.askopenfilename(
            filetypes=[
                ("\u0410\u0443\u0434\u0438\u043e", "*.wav *.mp3 *.m4a *.ogg *.flac *.webm"),
                ("\u0412\u0441\u0435", "*.*"),
            ]
        )
        if not filepath:
            return

        self.transcribe_btn.configure(
            state="disabled", text="\u23f3 \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f..."
        )
        self.transcript_view.clear()
        self.analysis_panel.clear()

        def do_transcribe():
            try:
                result = self.transcriber.transcribe_file(filepath)
                self._transcription_result = result

                # Batch diarization for uploaded files
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
                self.after(0, self._show_error, f"\u041e\u0448\u0438\u0431\u043a\u0430: {e}")
            finally:
                self.after(0, lambda: self.transcribe_btn.configure(
                    state="normal",
                    text="\U0001f4ac \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
                ))

        threading.Thread(target=do_transcribe, daemon=True).start()

    # ── Export ──

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

    # ── Helpers ──

    def _show_error(self, message: str):
        self.recording_panel.status_label.configure(text=message, text_color="#E53935")
