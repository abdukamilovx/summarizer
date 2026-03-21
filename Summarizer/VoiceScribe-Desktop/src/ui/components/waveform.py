"""
Real-time audio waveform visualization widget.
"""
import customtkinter as ctk
import tkinter as tk
from collections import deque


class WaveformCanvas(ctk.CTkFrame):
    """Displays a live audio waveform as vertical bars."""

    def __init__(
        self,
        master,
        bar_count: int = 60,
        bar_color: str = "#3B82F6",
        bg_color: str = "transparent",
        **kwargs,
    ):
        super().__init__(master, **kwargs)

        self.bar_count = bar_count
        self.bar_color = bar_color
        self._levels = deque([0.05] * bar_count, maxlen=bar_count)

        self.canvas = tk.Canvas(
            self,
            bg=self._get_bg(),
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_resize)

        self._width = 0
        self._height = 0

    def _get_bg(self) -> str:
        mode = ctk.get_appearance_mode()
        return "#1a1a2e" if mode == "Dark" else "#f0f0f0"

    def _on_resize(self, event):
        self._width = event.width
        self._height = event.height
        self._redraw_bars()

    def push_level(self, level: float):
        """Add a new audio level (0.0 - 1.0) and redraw."""
        self._levels.append(max(0.03, min(1.0, level)))
        self._redraw_bars()

    def _redraw_bars(self):
        if self._width == 0 or self._height == 0:
            return

        self.canvas.delete("all")

        bar_width = max(2, (self._width - self.bar_count) / self.bar_count)
        gap = 2
        total_bar = bar_width + gap
        start_x = (self._width - total_bar * self.bar_count) / 2
        center_y = self._height / 2
        max_bar_h = self._height * 0.9

        for i, level in enumerate(self._levels):
            x = start_x + i * total_bar
            h = max(2, level * max_bar_h)
            y1 = center_y - h / 2
            y2 = center_y + h / 2

            self.canvas.create_rectangle(
                x, y1, x + bar_width, y2,
                fill=self.bar_color,
                outline="",
            )

    def reset(self):
        """Clear the waveform."""
        self._levels = deque([0.05] * self.bar_count, maxlen=self.bar_count)
        self._redraw_bars()
