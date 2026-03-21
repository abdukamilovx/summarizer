"""
Main application window for VoiceScribe Desktop.
"""
import customtkinter as ctk
import numpy as np
import threading
import io
import soundfile as sf
from tkinter import filedialog
from typing import Optional

from audio.capture import AudioCapture, AudioChunk
from audio.mixer import AudioMixer
from transcription.whisper_api import WhisperAPITranscriber
from transcription.engine import TranscriptionResult
from analysis.summarizer import Summarizer
from ui.recording_panel import RecordingPanel
from ui.transcript_view import TranscriptView, AnalysisPanel
from ui.components.waveform import WaveformCanvas
from utils.config import settings
from utils.logger import log


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
        self._transcription_result: Optional[TranscriptionResult] = None

        # Services (lazy init)
        self._transcriber: Optional[WhisperAPITranscriber] = None
        self._summarizer: Optional[Summarizer] = None

        self._build_ui()

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

        # Main content: transcript (left) + analysis (right)
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
            bottom,
            text="\U0001f4c4 \u042d\u043a\u0441\u043f\u043e\u0440\u0442 TXT",
            command=lambda: self._export("txt"),
            width=120,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            bottom,
            text="\U0001f3ac \u042d\u043a\u0441\u043f\u043e\u0440\u0442 SRT",
            command=lambda: self._export("srt"),
            width=120,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            bottom,
            text="\U0001f4c2 \u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0444\u0430\u0439\u043b",
            command=self._load_file,
            width=150,
        ).pack(side="left", padx=5)

        self.analyze_btn = ctk.CTkButton(
            bottom,
            text="\U0001f916 \u0410\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
            command=self._run_analysis,
            width=180,
            fg_color="#7C3AED",
            hover_color="#5B21B6",
        )
        self.analyze_btn.pack(side="right", padx=5)

        self.transcribe_btn = ctk.CTkButton(
            bottom,
            text="\U0001f4ac \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
            command=self._transcribe_buffer,
            width=180,
            fg_color="#0D9488",
            hover_color="#065F53",
        )
        self.transcribe_btn.pack(side="right", padx=5)

    # ── Recording ──

    def _on_start_recording(self):
        log.info("Starting recording...")
        self._audio_buffer.clear()
        self.transcript_view.clear()
        self.analysis_panel.clear()
        self.waveform.reset()

        self._audio_capture = AudioCapture(
            sample_rate=settings.SAMPLE_RATE,
            capture_microphone=True,
            capture_system=True,
        )
        self._audio_capture.on_audio(self._on_audio_chunk)

        try:
            self._audio_capture.start()
        except Exception as e:
            log.error(f"Failed to start capture: {e}")
            self.recording_panel.status_label.configure(
                text=f"\u041e\u0448\u0438\u0431\u043a\u0430: {e}", text_color="#E53935"
            )

    def _on_stop_recording(self):
        log.info("Stopping recording...")
        if self._audio_capture:
            self._audio_capture.stop()
            self._audio_capture = None

        # Flush mixer
        flushed = self._mixer.flush(settings.SAMPLE_RATE)
        if flushed:
            self._audio_buffer.append(flushed.data)

        total_samples = sum(len(b) for b in self._audio_buffer)
        duration = total_samples / settings.SAMPLE_RATE
        log.info(f"Recording stopped. Duration: {duration:.1f}s, Samples: {total_samples}")

    def _on_audio_chunk(self, chunk: AudioChunk):
        """Called from audio capture thread."""
        mixed = self._mixer.add_chunk(chunk)
        if mixed is not None:
            self._audio_buffer.append(mixed.data)

            # Update waveform on UI thread
            rms = float(np.sqrt(np.mean(mixed.data ** 2)))
            level = min(1.0, rms * 10)  # amplify for visibility
            self.after(0, self.waveform.push_level, level)

    # ── Transcription ──

    def _transcribe_buffer(self):
        if not self._audio_buffer:
            log.warning("No audio to transcribe")
            return

        self.transcribe_btn.configure(state="disabled", text="\u23f3 \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f...")

        def do_transcribe():
            try:
                audio = np.concatenate(self._audio_buffer)
                log.info(f"Transcribing {len(audio)/settings.SAMPLE_RATE:.1f}s of audio...")

                result = self.transcriber.transcribe_numpy(
                    audio, sample_rate=settings.SAMPLE_RATE
                )
                self._transcription_result = result

                self.after(0, self._show_transcription, result)
            except Exception as e:
                log.error(f"Transcription failed: {e}")
                self.after(0, self._show_error, f"\u041e\u0448\u0438\u0431\u043a\u0430 \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u0438: {e}")
            finally:
                self.after(0, lambda: self.transcribe_btn.configure(
                    state="normal", text="\U0001f4ac \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u043e\u0432\u0430\u0442\u044c"
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
                log.info("Analysis complete")
            except Exception as e:
                log.error(f"Analysis failed: {e}")
                self.after(0, self._show_error, f"\u041e\u0448\u0438\u0431\u043a\u0430 \u0430\u043d\u0430\u043b\u0438\u0437\u0430: {e}")
            finally:
                self.after(0, lambda: self.analyze_btn.configure(
                    state="normal", text="\U0001f916 \u0410\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u0442\u044c"
                ))

        threading.Thread(target=do_analysis, daemon=True).start()

    # ── File Loading ──

    def _load_file(self):
        filepath = filedialog.askopenfilename(
            filetypes=[
                ("\u0410\u0443\u0434\u0438\u043e \u0444\u0430\u0439\u043b\u044b", "*.wav *.mp3 *.m4a *.ogg *.flac *.webm"),
                ("\u0412\u0441\u0435 \u0444\u0430\u0439\u043b\u044b", "*.*"),
            ]
        )
        if not filepath:
            return

        self.transcribe_btn.configure(state="disabled", text="\u23f3 \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f...")
        self.transcript_view.clear()
        self.analysis_panel.clear()

        def do_transcribe():
            try:
                result = self.transcriber.transcribe_file(filepath)
                self._transcription_result = result
                self.after(0, self._show_transcription, result)
            except Exception as e:
                log.error(f"File transcription failed: {e}")
                self.after(0, self._show_error, f"\u041e\u0448\u0438\u0431\u043a\u0430: {e}")
            finally:
                self.after(0, lambda: self.transcribe_btn.configure(
                    state="normal", text="\U0001f4ac \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u043e\u0432\u0430\u0442\u044c"
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
            filetypes=[(f"{fmt.upper()} files", f"*{ext_map.get(fmt, '.txt')}")],
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
