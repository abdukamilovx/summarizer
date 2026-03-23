"""
Main application window for VoiceScribe Desktop.

Compact right-side docked panel with collapsible transcript tabs.
Minimizes to system tray.
"""
import customtkinter as ctk
import numpy as np
import threading
import sys
from tkinter import filedialog
from typing import Optional

from audio.capture import AudioCapture, AudioChunk, WAV_SAMPLE_RATE
from audio.preprocessor import enhance_speech
from transcription.whisper_api import WhisperAPITranscriber
from transcription.streaming import StreamingTranscriber
from transcription.corrector import TranscriptCorrector
from transcription.engine import TranscriptionResult
from analysis.summarizer import Summarizer
from ui.transcript_view import TranscriptMultiView, AnalysisWindow
from ui.components.waveform import WaveformCanvas
from utils.config import settings
from utils.storage import Storage
from utils.logger import log

import soundfile as sf


# ── Collapsible panel widget ─────────────────────────────────────────────────

class _CollapsiblePanel(ctk.CTkFrame):
    """Panel with a clickable header that collapses/expands its content."""

    def __init__(self, master, title: str, header_color: str = "#E0E0E0", **kwargs):
        super().__init__(master, **kwargs)
        self._expanded = True
        self._title = title

        # Header bar (clickable)
        self._header = ctk.CTkButton(
            self, text=f"▼  {title}", anchor="w",
            font=("Segoe UI", 12, "bold"), text_color=header_color,
            fg_color="#2B2B2B", hover_color="#3B3B3B",
            height=30, corner_radius=4,
            command=self._toggle,
        )
        self._header.pack(fill="x", padx=2, pady=(2, 0))

        # Content frame
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=2, pady=2)

        # Text box inside content
        self.textbox = ctk.CTkTextbox(
            self.content, font=("Segoe UI", 12), wrap="word",
            state="disabled", height=120,
        )
        self.textbox.pack(fill="both", expand=True)

        # Copy button (small, in header area)
        self._copy_btn = ctk.CTkButton(
            self._header, text="📋", width=28, height=24,
            font=("Segoe UI", 11), fg_color="transparent",
            hover_color="#555555", command=self._copy_text,
        )
        # Place copy button on the right side of header
        self._copy_btn.place(relx=1.0, rely=0.5, anchor="e", x=-5)

    def _toggle(self):
        if self._expanded:
            self.content.pack_forget()
            self._header.configure(text=f"▶  {self._title}")
        else:
            self.content.pack(fill="both", expand=True, padx=2, pady=2)
            self._header.configure(text=f"▼  {self._title}")
        self._expanded = not self._expanded

    def _copy_text(self):
        text = self.textbox.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def append(self, text: str):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", f"{text}\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def set_text(self, text: str):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        if text:
            self.textbox.insert("1.0", text)
        self.textbox.configure(state="disabled")

    def get_text(self) -> str:
        return self.textbox.get("1.0", "end").strip()

    def clear(self):
        self.set_text("")


# ── Main Window ──────────────────────────────────────────────────────────────

class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VoiceScribe")
        self._setup_geometry()

        # State
        self._audio_capture: Optional[AudioCapture] = None
        self._audio_buffer: list[np.ndarray] = []
        self._hq_audio_buffer: list[np.ndarray] = []
        self._transcription_result: Optional[TranscriptionResult] = None
        self._streaming_transcriber: Optional[StreamingTranscriber] = None
        self._current_rec_id: Optional[str] = None
        self._is_stopping = False
        self._corrector: Optional[TranscriptCorrector] = None
        self._analysis_window: Optional[AnalysisWindow] = None
        self._local_translator = None
        self._transcriber: Optional[WhisperAPITranscriber] = None
        self._summarizer: Optional[Summarizer] = None
        self._storage = Storage()

        # Tray support
        self._tray_icon = None
        self.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

        self._build_ui()
        self._init_local_translator()
        self._setup_tray()

    def _setup_geometry(self):
        """Dock window to right side of screen, full height."""
        w = 420
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = screen_w - w
        self.geometry(f"{w}x{screen_h - 80}+{x}+0")
        self.minsize(360, 600)
        self.attributes("-topmost", False)

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
            except Exception as e:
                log.warning(f"Local translator init failed: {e}")
        threading.Thread(target=load, daemon=True).start()

    # -- Tray --

    def _setup_tray(self):
        """Setup system tray icon."""
        try:
            import pystray
            from PIL import Image, ImageDraw

            # Create a simple icon
            img = Image.new("RGB", (64, 64), "#1a1a2e")
            draw = ImageDraw.Draw(img)
            draw.ellipse([12, 12, 52, 52], fill="#E53935")
            draw.ellipse([22, 22, 42, 42], fill="#1a1a2e")

            menu = pystray.Menu(
                pystray.MenuItem("Показать", self._restore_from_tray, default=True),
                pystray.MenuItem("Выход", self._quit_app),
            )
            self._tray_icon = pystray.Icon("VoiceScribe", img, "VoiceScribe", menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        except ImportError:
            log.info("pystray not installed — tray icon disabled. pip install pystray pillow")

    def _minimize_to_tray(self):
        """Hide window to tray instead of closing."""
        if self._tray_icon:
            self.withdraw()
        else:
            self._quit_app()

    def _restore_from_tray(self, icon=None, item=None):
        self.after(0, self._do_restore)

    def _do_restore(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
        self.destroy()

    # -- UI --

    def _build_ui(self):
        # Scrollable main container
        self._main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._main_scroll.pack(fill="both", expand=True, padx=6, pady=6)
        container = self._main_scroll

        # ═══ SECTION: File Upload ═══
        sec_files = ctk.CTkFrame(container, fg_color="#1E1E2E", corner_radius=8)
        sec_files.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(sec_files, text="📂 Загрузка файлов", font=("Segoe UI", 12, "bold"),
                      text_color="#A0A0A0").pack(anchor="w", padx=8, pady=(6, 2))

        btn_row = ctk.CTkFrame(sec_files, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkButton(btn_row, text="📄 Текст", width=90, height=32,
                       command=self._load_text_file).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="🎤 Голос", width=90, height=32,
                       command=self._load_audio_file).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="🎬 Видео", width=90, height=32,
                       command=self._load_video_file).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="📤 TXT", width=60, height=32, fg_color="#333",
                       command=lambda: self._export("txt")).pack(side="right", padx=2)
        ctk.CTkButton(btn_row, text="📤 SRT", width=60, height=32, fg_color="#333",
                       command=lambda: self._export("srt")).pack(side="right", padx=2)

        # ═══ SECTION: Recording Controls ═══
        sec_rec = ctk.CTkFrame(container, fg_color="#1E1E2E", corner_radius=8)
        sec_rec.pack(fill="x", pady=4)

        # Timer
        self.timer_label = ctk.CTkLabel(sec_rec, text="00:00:00",
                                         font=("Consolas", 28, "bold"))
        self.timer_label.pack(pady=(8, 4))

        # Start / Stop buttons
        btn_rec_row = ctk.CTkFrame(sec_rec, fg_color="transparent")
        btn_rec_row.pack(fill="x", padx=8, pady=2)

        self._start_btn = ctk.CTkButton(
            btn_rec_row, text="⏺  Начать", height=42,
            font=("Segoe UI", 14, "bold"),
            fg_color="#E53935", hover_color="#B71C1C",
            command=self._on_start_recording,
        )
        self._start_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))

        self._stop_btn = ctk.CTkButton(
            btn_rec_row, text="⏹  Стоп", height=42,
            font=("Segoe UI", 14, "bold"),
            fg_color="#1976D2", hover_color="#0D47A1",
            state="disabled", command=self._on_stop_recording,
        )
        self._stop_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

        # Status
        self.status_label = ctk.CTkLabel(sec_rec, text="Готов к записи",
                                          font=("Segoe UI", 11), text_color="gray")
        self.status_label.pack(pady=(2, 4))

        # Waveform
        self.waveform = WaveformCanvas(sec_rec, height=40)
        self.waveform.pack(fill="x", padx=8, pady=(0, 6))

        # ═══ SECTION: Settings (compact) ═══
        sec_set = ctk.CTkFrame(container, fg_color="#1E1E2E", corner_radius=8)
        sec_set.pack(fill="x", pady=4)

        # Language selectors
        lang_row = ctk.CTkFrame(sec_set, fg_color="transparent")
        lang_row.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(lang_row, text="🔤", font=("Segoe UI", 12)).pack(side="left", padx=(0, 4))

        lang_values = [
            "—", "Auto", "English", "Russian", "Uzbek",
            "Chinese", "Japanese", "Korean",
            "German", "French", "Spanish",
            "Turkish", "Arabic", "Hindi",
        ]
        self._lang_vars: list[ctk.StringVar] = []
        for i in range(4):
            var = ctk.StringVar(value="Auto" if i == 0 else "—")
            ctk.CTkOptionMenu(
                lang_row, variable=var, width=80, values=lang_values,
                font=("Segoe UI", 10), height=26,
            ).pack(side="left", padx=1)
            self._lang_vars.append(var)

        # Toggles row 1
        tog1 = ctk.CTkFrame(sec_set, fg_color="transparent")
        tog1.pack(fill="x", padx=8, pady=2)

        self._mic_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(tog1, text="🎤 Mic", variable=self._mic_var,
                       width=40, height=20).pack(side="left", padx=4)
        self._system_audio_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(tog1, text="🔊 System", variable=self._system_audio_var,
                       width=40, height=20).pack(side="left", padx=4)

        # Toggles row 2
        tog2 = ctk.CTkFrame(sec_set, fg_color="transparent")
        tog2.pack(fill="x", padx=8, pady=(2, 6))

        self._realtime_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(tog2, text="RT", variable=self._realtime_var,
                       width=40, height=20).pack(side="left", padx=4)
        self._translate_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(tog2, text="🌐", variable=self._translate_var,
                       width=40, height=20).pack(side="left", padx=4)
        self._denoise_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(tog2, text="DN", variable=self._denoise_var,
                       width=40, height=20).pack(side="left", padx=4)
        self._correction_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(tog2, text="AI", variable=self._correction_var,
                       width=40, height=20).pack(side="left", padx=4)
        self._diarize_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(tog2, text="👥", variable=self._diarize_var,
                       width=40, height=20).pack(side="left", padx=4)

        # ═══ SECTION: 4 Collapsible Panels ═══
        self.panel_raw = _CollapsiblePanel(
            container, title="1. Транскрипция", header_color="#4CAF50")
        self.panel_raw.pack(fill="both", expand=True, pady=2)

        self.panel_raw_translation = _CollapsiblePanel(
            container, title="2. Перевод", header_color="#64B5F6")
        self.panel_raw_translation.pack(fill="both", expand=True, pady=2)

        self.panel_corrected = _CollapsiblePanel(
            container, title="3. AI Коррекция", header_color="#FFA726")
        self.panel_corrected.pack(fill="both", expand=True, pady=2)

        self.panel_corrected_translation = _CollapsiblePanel(
            container, title="4. Перевод (AI)", header_color="#AB47BC")
        self.panel_corrected_translation.pack(fill="both", expand=True, pady=2)

        # ═══ SECTION: Actions ═══
        sec_actions = ctk.CTkFrame(container, fg_color="#1E1E2E", corner_radius=8)
        sec_actions.pack(fill="x", pady=4)

        act_row = ctk.CTkFrame(sec_actions, fg_color="transparent")
        act_row.pack(fill="x", padx=8, pady=6)

        self.analyze_btn = ctk.CTkButton(
            act_row, text="🤖 Анализ", height=36,
            font=("Segoe UI", 13, "bold"),
            fg_color="#7C3AED", hover_color="#5B21B6",
            command=self._run_analysis,
        )
        self.analyze_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))

        self.transcribe_btn = ctk.CTkButton(
            act_row, text="💬 Транскрибация", height=36,
            font=("Segoe UI", 13, "bold"),
            fg_color="#0D9488", hover_color="#065F53",
            command=self._transcribe_buffer,
        )
        self.transcribe_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

        # ═══ SECTION: Telegram ═══
        sec_tg = ctk.CTkFrame(container, fg_color="#1E1E2E", corner_radius=8)
        sec_tg.pack(fill="x", pady=(4, 0))

        tg_row = ctk.CTkFrame(sec_tg, fg_color="transparent")
        tg_row.pack(fill="x", padx=8, pady=6)

        ctk.CTkButton(
            tg_row, text="📨 Отправить в Telegram", height=34,
            font=("Segoe UI", 12, "bold"),
            fg_color="#0088CC", hover_color="#006699",
            command=self._send_to_telegram,
        ).pack(fill="x")

        self._tg_status = ctk.CTkLabel(sec_tg, text="", font=("Segoe UI", 10),
                                        text_color="gray")
        self._tg_status.pack(pady=(0, 4))

        # Backward compatibility — create a TranscriptMultiView as hidden reference
        self.transcript_view = _TranscriptBridge(
            self.panel_raw, self.panel_raw_translation,
            self.panel_corrected, self.panel_corrected_translation,
        )

        # Recording state
        self._is_recording = False
        self._rec_start_time = None
        self._timer_after_id = None

    # -- Recording Timer --

    def _start_timer(self):
        from datetime import datetime
        self._rec_start_time = datetime.now()
        self._update_timer()

    def _stop_timer(self):
        if self._timer_after_id:
            self.after_cancel(self._timer_after_id)
            self._timer_after_id = None

    def _update_timer(self):
        if self._rec_start_time:
            from datetime import datetime
            elapsed = (datetime.now() - self._rec_start_time).total_seconds()
            h, r = divmod(int(elapsed), 3600)
            m, s = divmod(r, 60)
            self.timer_label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        self._timer_after_id = self.after(500, self._update_timer)

    # -- Recording --

    def _on_start_recording(self):
        log.info("Starting recording...")
        self._is_recording = True
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self.status_label.configure(text="🔴 Запись...", text_color="#E53935")

        self._audio_buffer.clear()
        self._hq_audio_buffer.clear()
        self.panel_raw.clear()
        self.panel_raw_translation.clear()
        self.panel_corrected.clear()
        self.panel_corrected_translation.clear()
        self.waveform.reset()
        self._start_timer()

        do_translate = self._translate_var.get()
        do_correct = self._correction_var.get()
        do_denoise = self._denoise_var.get()
        whisper_lang = self._get_whisper_language()
        whisper_prompt = self._get_whisper_prompt()

        self._corrector = None
        if do_correct:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_path = str(Storage.get_audio_dir() / f"{ts}_raw.txt")
            self._corrector = TranscriptCorrector(
                raw_file_path=raw_path, correction_interval=3,
                on_corrected=self._on_periodic_correction,
            )

        if self._realtime_var.get() and settings.OPENAI_API_KEY:
            self._streaming_transcriber = StreamingTranscriber(
                transcriber=self.transcriber,
                sample_rate=settings.SAMPLE_RATE,
                fast_interval=5.0, group_size=2,
                language=whisper_lang, prompt=whisper_prompt,
                on_raw_text=self._on_raw_text,
                on_raw_translation=self._on_raw_translation if do_translate else None,
                on_corrected=self._on_corrected if do_correct else None,
                on_corrected_translation=(
                    self._on_corrected_translation if (do_translate and do_correct) else None
                ),
                translate_to_russian=do_translate,
                noise_reduction=do_denoise,
                corrector=self._corrector,
                local_translator=self._local_translator,
                live_correction=do_correct,
            )
            self._streaming_transcriber.start()

        do_mic = self._mic_var.get()
        do_system = self._system_audio_var.get()
        if not do_mic and not do_system:
            do_mic = True
        self._audio_capture = AudioCapture(
            sample_rate=settings.SAMPLE_RATE, chunk_duration=0.1,
            capture_microphone=do_mic, capture_system=do_system,
        )
        self._audio_capture.on_audio(self._on_audio_chunk)
        self._audio_capture.on_hq_audio(self._on_hq_audio_chunk)
        try:
            self._audio_capture.start()
        except Exception as e:
            log.error(f"Failed to start capture: {e}")
            self.status_label.configure(text=f"Error: {e}", text_color="#E53935")

    def _on_stop_recording(self):
        if self._is_stopping:
            return
        self._is_stopping = True
        self._is_recording = False
        self._stop_timer()
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self.status_label.configure(text="⏳ Завершение...", text_color="#FF9800")

        if self._audio_capture:
            self._audio_capture.stop()
            self._audio_capture = None

        def finalize():
            try:
                if self._streaming_transcriber:
                    result = self._streaming_transcriber.stop()
                    self._transcription_result = result
                    self._streaming_transcriber = None

                    if self._diarize_var.get() and result.segments and self._audio_buffer:
                        from transcription.diarizer import SpeakerDiarizer
                        diarizer = SpeakerDiarizer(sample_rate=settings.SAMPLE_RATE)
                        full_audio = np.concatenate(self._audio_buffer)
                        result.segments = diarizer.diarize(full_audio, result.segments)
                        self._transcription_result = result

                    if self._corrector and result.segments:
                        labeled = [
                            f"[{s.speaker}]: {s.text.strip()}" if s.speaker else s.text.strip()
                            for s in result.segments
                        ]
                        self._corrector.replace_chunks(labeled)
                        self._corrector.force_correction()

                total_samples = sum(len(b) for b in self._audio_buffer)
                duration = total_samples / settings.SAMPLE_RATE

                if self._audio_buffer and duration > 0.5:
                    self._save_recording(duration)

                self.after(0, lambda: self.status_label.configure(
                    text="✅ Запись завершена", text_color="#4CAF50"))
            except Exception as e:
                log.error(f"Finalization error: {e}")
                self.after(0, lambda: self.status_label.configure(
                    text=f"Error: {e}", text_color="#E53935"))
            finally:
                self._is_stopping = False

        threading.Thread(target=finalize, daemon=True).start()

    # -- Audio callbacks --

    def _on_audio_chunk(self, chunk: AudioChunk):
        self._audio_buffer.append(chunk.data)
        if self._streaming_transcriber:
            self._streaming_transcriber.add_audio(chunk.data)
        rms = float(np.sqrt(np.mean(chunk.data ** 2)))
        self.after(0, self.waveform.push_level, min(1.0, rms * 10))

    def _on_hq_audio_chunk(self, chunk: AudioChunk):
        self._hq_audio_buffer.append(chunk.data)

    # -- Panel callbacks --

    def _on_raw_text(self, text: str, speaker: Optional[str] = None):
        prefix = f"[{speaker}]: " if speaker else ""
        self.after(0, self.panel_raw.append, f"{prefix}{text}")

    def _on_raw_translation(self, text: str):
        self.after(0, self.panel_raw_translation.append, text)

    def _on_corrected(self, text: str, speaker: Optional[str] = None):
        prefix = f"[{speaker}]: " if speaker else ""
        self.after(0, self.panel_corrected.append, f"{prefix}{text}")

    def _on_corrected_translation(self, text: str):
        self.after(0, self.panel_corrected_translation.append, text)

    def _on_periodic_correction(self, corrected_text: str):
        def update():
            self.panel_corrected.set_text(corrected_text)
            self.status_label.configure(text="✅ Текст скорректирован", text_color="#4CAF50")
        self.after(0, update)

    # -- File loading --

    def _load_text_file(self):
        fp = filedialog.askopenfilename(filetypes=[("Text", "*.txt *.srt *.vtt"), ("All", "*.*")])
        if fp:
            with open(fp, "r", encoding="utf-8") as f:
                self.panel_raw.set_text(f.read())

    def _load_audio_file(self):
        fp = filedialog.askopenfilename(
            filetypes=[("Audio", "*.wav *.mp3 *.m4a *.ogg *.flac *.webm"), ("All", "*.*")])
        if fp:
            self._load_and_transcribe(fp)

    def _load_video_file(self):
        fp = filedialog.askopenfilename(
            filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All", "*.*")])
        if fp:
            self._load_and_transcribe(fp)

    def _load_and_transcribe(self, filepath: str):
        self.transcribe_btn.configure(state="disabled", text="⏳...")
        self.panel_raw.clear()

        def do_transcribe():
            try:
                result = self.transcriber.transcribe_file(filepath)
                self._transcription_result = result
                self.after(0, lambda: self.panel_raw.set_text(result.text))
            except Exception as e:
                log.error(f"File transcription failed: {e}")
                self.after(0, lambda: self.status_label.configure(
                    text=f"Error: {e}", text_color="#E53935"))
            finally:
                self.after(0, lambda: self.transcribe_btn.configure(
                    state="normal", text="💬 Транскрибация"))

        threading.Thread(target=do_transcribe, daemon=True).start()

    # -- Transcription --

    def _transcribe_buffer(self):
        if not self._audio_buffer:
            return
        self.transcribe_btn.configure(state="disabled", text="⏳...")

        def do_transcribe():
            try:
                audio = np.concatenate(self._audio_buffer)
                if self._denoise_var.get():
                    audio = enhance_speech(audio, settings.SAMPLE_RATE)
                result = self.transcriber.transcribe_numpy(audio, sample_rate=settings.SAMPLE_RATE)
                self._transcription_result = result
                self.after(0, lambda: self.panel_raw.set_text(result.text))
            except Exception as e:
                log.error(f"Transcription failed: {e}")
            finally:
                self.after(0, lambda: self.transcribe_btn.configure(
                    state="normal", text="💬 Транскрибация"))

        threading.Thread(target=do_transcribe, daemon=True).start()

    # -- Analysis --

    def _run_analysis(self):
        text = self.transcript_view.get_text()
        if not text.strip():
            return

        if self._analysis_window is None or not self._analysis_window.winfo_exists():
            self._analysis_window = AnalysisWindow(self)
        else:
            self._analysis_window.focus()

        self._analysis_window.clear()
        self.analyze_btn.configure(state="disabled", text="⏳...")

        def do_analysis():
            try:
                result = self.summarizer.full_analysis(text)

                def update_ui():
                    if self._analysis_window and self._analysis_window.winfo_exists():
                        self._analysis_window.set_summary(result.get("summary", ""))
                        self._analysis_window.set_protocol(result.get("protocol", ""))
                        self._analysis_window.set_actions(result.get("action_items", []))
                        self._analysis_window.set_key_points(result.get("key_points", []))
                        translation = result.get("translation", "")
                        if translation:
                            self._analysis_window.set_translation(text, translation)
                        dialogue = result.get("dialogue", "")
                        if dialogue:
                            self._analysis_window.set_dialogue(dialogue)
                self.after(0, update_ui)
            except Exception as e:
                log.error(f"Analysis failed: {e}")
            finally:
                self.after(0, lambda: self.analyze_btn.configure(
                    state="normal", text="🤖 Анализ"))

        threading.Thread(target=do_analysis, daemon=True).start()

    # -- Telegram --

    def _send_to_telegram(self):
        """Send current transcript + translation to Telegram bot."""
        text = self.transcript_view.get_text()
        translation = self.panel_corrected_translation.get_text() or self.panel_raw_translation.get_text()
        if not text.strip():
            self._tg_status.configure(text="⚠️ Нет текста", text_color="#FF9800")
            return

        self._tg_status.configure(text="📨 Отправка...", text_color="#0088CC")

        def send():
            try:
                from telegram import Bot
                bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                if not settings.TELEGRAM_BOT_TOKEN:
                    self.after(0, lambda: self._tg_status.configure(
                        text="⚠️ TELEGRAM_BOT_TOKEN не задан", text_color="#E53935"))
                    return

                import asyncio
                msg = f"📝 **Транскрипция:**\n{text}"
                if translation:
                    msg += f"\n\n🇷🇺 **Перевод:**\n{translation}"

                # Split if needed
                chunks = [msg[i:i + 4000] for i in range(0, len(msg), 4000)]

                async def do_send():
                    # Get bot updates to find chat_id
                    updates = await bot.get_updates(limit=1)
                    if not updates:
                        return "⚠️ Отправь /start боту"
                    chat_id = updates[-1].effective_chat.id
                    for chunk in chunks:
                        await bot.send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")
                    return "✅ Отправлено!"

                result = asyncio.run(do_send())
                self.after(0, lambda: self._tg_status.configure(
                    text=result, text_color="#4CAF50" if "✅" in result else "#FF9800"))
            except Exception as e:
                log.error(f"Telegram send error: {e}")
                self.after(0, lambda: self._tg_status.configure(
                    text=f"❌ {str(e)[:40]}", text_color="#E53935"))

        threading.Thread(target=send, daemon=True).start()

    # -- Storage --

    def _save_recording(self, duration: float):
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_dir = Storage.get_audio_dir()
        audio_path = str(audio_dir / f"{timestamp}.wav")

        if self._hq_audio_buffer:
            hq_audio = np.concatenate(self._hq_audio_buffer)
            sf.write(audio_path, hq_audio, WAV_SAMPLE_RATE)
        else:
            audio = np.concatenate(self._audio_buffer)
            sf.write(audio_path, audio, settings.SAMPLE_RATE)

        transcript = self._transcription_result.text if self._transcription_result else ""
        segments = [
            {"start": s.start, "end": s.end, "text": s.text, "speaker": s.speaker}
            for s in (self._transcription_result.segments if self._transcription_result else [])
        ]
        language = self._transcription_result.language if self._transcription_result else ""

        self._current_rec_id = self._storage.save_recording(
            title=f"Recording {timestamp}", duration_sec=duration,
            audio_path=audio_path, transcript=transcript,
            language=language, segments=segments,
        )
        log.info(f"Recording saved: {self._current_rec_id}")

    # -- Export --

    def _export(self, fmt: str):
        text = self.transcript_view.get_text()
        if not text.strip():
            return
        ext_map = {"txt": ".txt", "srt": ".srt"}
        filepath = filedialog.asksaveasfilename(
            defaultextension=ext_map.get(fmt, ".txt"),
            filetypes=[(fmt.upper(), f"*{ext_map.get(fmt, '.txt')}")],
        )
        if filepath:
            from utils.export import export_transcript
            segments = self._transcription_result.segments if self._transcription_result else []
            export_transcript(text, segments, filepath, fmt)

    # -- Helpers --

    _LANG_MAP = {
        "Auto": None, "—": None,
        "English": "en", "Russian": "ru", "Uzbek": "uz",
        "Chinese": "zh", "Japanese": "ja", "Korean": "ko",
        "German": "de", "French": "fr", "Spanish": "es",
        "Turkish": "tr", "Arabic": "ar", "Hindi": "hi",
        "Italian": "it", "Portuguese": "pt", "Ukrainian": "uk",
    }

    _LANG_PROMPTS = {
        "uz": "Assalomu alaykum. Bugun biz muhim masalalarni muhokama qilamiz.",
        "ru": "Здравствуйте. Сегодня мы обсудим важные вопросы.",
        "en": "Hello. Today we will discuss important matters.",
    }

    def _get_selected_languages(self) -> list[str]:
        langs, seen = [], set()
        for var in self._lang_vars:
            code = self._LANG_MAP.get(var.get())
            if code and code not in seen:
                langs.append(code)
                seen.add(code)
        return langs

    def _get_whisper_language(self) -> Optional[str]:
        langs = self._get_selected_languages()
        return langs[0] if len(langs) == 1 else None

    def _get_whisper_prompt(self) -> Optional[str]:
        langs = self._get_selected_languages()
        hints = [self._LANG_PROMPTS[l] for l in langs if l in self._LANG_PROMPTS]
        return " ".join(hints) if hints else None

    def _show_error(self, message: str):
        self.status_label.configure(text=message, text_color="#E53935")


# ── Bridge: maps old TranscriptMultiView API to collapsible panels ───────────

class _TranscriptBridge:
    """Adapter so existing code (analysis, callbacks) can use .get_text(), etc."""

    def __init__(self, raw, raw_tr, corrected, corrected_tr):
        self.panel_raw = raw
        self.panel_raw_translation = raw_tr
        self.panel_corrected = corrected
        self.panel_corrected_translation = corrected_tr

    def append_raw(self, text, speaker=None):
        prefix = f"[{speaker}]: " if speaker else ""
        self.panel_raw.append(f"{prefix}{text}")

    def append_raw_translation(self, text):
        self.panel_raw_translation.append(text)

    def set_corrected(self, text):
        self.panel_corrected.set_text(text)

    def append_corrected(self, text, speaker=None):
        prefix = f"[{speaker}]: " if speaker else ""
        self.panel_corrected.append(f"{prefix}{text}")

    def append_corrected_translation(self, text):
        self.panel_corrected_translation.append(text)

    def get_text(self) -> str:
        corrected = self.panel_corrected.get_text()
        return corrected if corrected else self.panel_raw.get_text()

    def clear(self):
        self.panel_raw.clear()
        self.panel_raw_translation.clear()
        self.panel_corrected.clear()
        self.panel_corrected_translation.clear()
