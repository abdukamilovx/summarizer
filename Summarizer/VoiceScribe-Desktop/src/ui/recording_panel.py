"""
Recording control panel with start/stop, timer, source indicators.
"""
import customtkinter as ctk
from datetime import datetime, timedelta
from typing import Callable, Optional


class RecordingPanel(ctk.CTkFrame):
    """Top panel with record button, timer, and audio source indicators."""

    def __init__(
        self,
        master,
        on_start: Optional[Callable] = None,
        on_stop: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)

        self._on_start = on_start
        self._on_stop = on_stop
        self._is_recording = False
        self._start_time: Optional[datetime] = None
        self._timer_id: Optional[str] = None

        self._build_ui()

    def _build_ui(self):
        # Record button
        self.record_btn = ctk.CTkButton(
            self,
            text="\u23fa  \u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044c",
            command=self._toggle_recording,
            width=220,
            height=50,
            font=("Segoe UI", 16, "bold"),
            fg_color="#E53935",
            hover_color="#B71C1C",
            corner_radius=12,
        )
        self.record_btn.pack(side="left", padx=(10, 20))

        # Timer
        self.timer_label = ctk.CTkLabel(
            self,
            text="00:00:00",
            font=("Consolas", 36, "bold"),
        )
        self.timer_label.pack(side="left", padx=20)

        # Source indicators frame
        sources_frame = ctk.CTkFrame(self, fg_color="transparent")
        sources_frame.pack(side="left", padx=20)

        self.mic_label = ctk.CTkLabel(
            sources_frame,
            text="\U0001f3a4 \u041c\u0438\u043a\u0440\u043e\u0444\u043e\u043d",
            font=("Segoe UI", 12),
            text_color="#4CAF50",
        )
        self.mic_label.pack(side="left", padx=8)

        self.system_label = ctk.CTkLabel(
            sources_frame,
            text="\U0001f50a \u0421\u0438\u0441\u0442\u0435\u043c\u043d\u044b\u0439 \u0437\u0432\u0443\u043a",
            font=("Segoe UI", 12),
            text_color="#2196F3",
        )
        self.system_label.pack(side="left", padx=8)

        # Status
        self.status_label = ctk.CTkLabel(
            self,
            text="\u0413\u043e\u0442\u043e\u0432 \u043a \u0437\u0430\u043f\u0438\u0441\u0438",
            font=("Segoe UI", 13),
            text_color="gray",
        )
        self.status_label.pack(side="right", padx=15)

    def _toggle_recording(self):
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._is_recording = True
        self._start_time = datetime.now()

        self.record_btn.configure(
            text="\u23f9  \u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c",
            fg_color="#1976D2",
            hover_color="#0D47A1",
        )
        self.status_label.configure(text="\u0417\u0430\u043f\u0438\u0441\u044c...", text_color="#E53935")
        self._update_timer()

        if self._on_start:
            self._on_start()

    def _stop_recording(self):
        self._is_recording = False

        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None

        self.record_btn.configure(
            text="\u23fa  \u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044c",
            fg_color="#E53935",
            hover_color="#B71C1C",
        )
        self.status_label.configure(text="\u0417\u0430\u043f\u0438\u0441\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430", text_color="#4CAF50")

        if self._on_stop:
            self._on_stop()

    def _update_timer(self):
        if not self._is_recording or not self._start_time:
            return

        elapsed = datetime.now() - self._start_time
        total_sec = int(elapsed.total_seconds())
        h, remainder = divmod(total_sec, 3600)
        m, s = divmod(remainder, 60)
        self.timer_label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")

        self._timer_id = self.after(500, self._update_timer)

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time and self._is_recording:
            return (datetime.now() - self._start_time).total_seconds()
        return 0
