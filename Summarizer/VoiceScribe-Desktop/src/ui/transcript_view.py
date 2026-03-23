"""
Multi-panel transcript display — Timekettle-style synchronous view.

Panel 1: Raw real-time transcription (<1s latency, direct Whisper output)
Panel 2: Sync translation of raw transcription
Panel 3: AI-corrected transcription with speaker diarization
Panel 4: Translation of corrected transcription
"""
import re
from itertools import zip_longest

import customtkinter as ctk
from typing import Optional

SPEAKER_COLORS = ["#42A5F5", "#66BB6A", "#FFA726", "#AB47BC", "#EF5350", "#26C6DA"]


class _TextPanel(ctk.CTkFrame):
    """Single scrollable text panel with a header and copy button."""

    def __init__(self, master, title: str, header_color: str = "#E0E0E0", **kwargs):
        super().__init__(master, **kwargs)
        self._speaker_color_map: dict[str, str] = {}

        # Header row with title + copy button
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(
            header_frame, text=title,
            font=("Segoe UI", 13, "bold"),
            text_color=header_color,
            anchor="w",
        ).pack(side="left")

        self._copy_btn = ctk.CTkButton(
            header_frame, text="\U0001f4cb", width=32, height=24,
            font=("Segoe UI", 12), fg_color="transparent",
            hover_color="#444444", command=self._copy_text,
        )
        self._copy_btn.pack(side="right", padx=2)

        self.textbox = ctk.CTkTextbox(
            self, font=("Segoe UI", 13), wrap="word", state="disabled",
        )
        self.textbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        tw = self.textbox._textbox
        for i, color in enumerate(SPEAKER_COLORS):
            tw.tag_configure(
                f"speaker_{i}", foreground=color, font=("Segoe UI", 13, "bold"),
            )
        tw.tag_configure(
            "translation", foreground="#64B5F6",
            font=("Segoe UI", 12, "italic"), lmargin1=10, lmargin2=10,
        )

    def _copy_text(self):
        """Copy panel text to clipboard."""
        text = self.get_text()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            # Visual feedback
            old_text = self._copy_btn.cget("text")
            self._copy_btn.configure(text="\u2705")
            self.after(1500, lambda: self._copy_btn.configure(text=old_text))

    def _get_speaker_tag(self, speaker: str) -> str:
        if speaker not in self._speaker_color_map:
            idx = len(self._speaker_color_map) % len(SPEAKER_COLORS)
            self._speaker_color_map[speaker] = f"speaker_{idx}"
        return self._speaker_color_map[speaker]

    def append(self, text: str, speaker: Optional[str] = None, tag: Optional[str] = None):
        self.textbox.configure(state="normal")
        tw = self.textbox._textbox
        if speaker:
            stag = self._get_speaker_tag(speaker)
            tw.insert("end", f"[{speaker}]: ", stag)
        if tag:
            tw.insert("end", f"{text}\n", tag)
        else:
            tw.insert("end", f"{text}\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def set_text(self, text: str):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self._speaker_color_map.clear()
        tw = self.textbox._textbox
        for line in text.split("\n"):
            if m := re.match(r'\[(.+?)\]:\s*(.*)', line):
                speaker, content = m.group(1), m.group(2)
                stag = self._get_speaker_tag(speaker)
                tw.insert("end", f"[{speaker}]: ", stag)
                tw.insert("end", f"{content}\n")
            elif line.strip():
                tw.insert("end", f"{line}\n")
        self.textbox.configure(state="disabled")

    def get_text(self) -> str:
        return self.textbox.get("1.0", "end").strip()

    def clear(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self._speaker_color_map.clear()


class TranscriptMultiView(ctk.CTkFrame):
    """4-panel synchronous transcript display.

    Layout (2x2 grid):
        ┌──────────────────┬──────────────────┐
        │  Raw transcript   │  Raw translation  │
        │  (Panel 1)        │  (Panel 2)        │
        ├──────────────────┼──────────────────┤
        │  Corrected text   │  Corrected transl │
        │  (Panel 3)        │  (Panel 4)        │
        └──────────────────┴──────────────────┘
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.panel_raw = _TextPanel(
            self, title="1. Live Transcription",
            header_color="#4CAF50",
        )
        self.panel_raw.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=(0, 2))

        self.panel_raw_translation = _TextPanel(
            self, title="2. Live Translation",
            header_color="#64B5F6",
        )
        self.panel_raw_translation.grid(row=0, column=1, sticky="nsew", padx=(2, 0), pady=(0, 2))

        self.panel_corrected = _TextPanel(
            self, title="3. AI Corrected + Speakers",
            header_color="#FFA726",
        )
        self.panel_corrected.grid(row=1, column=0, sticky="nsew", padx=(0, 2), pady=(2, 0))

        self.panel_corrected_translation = _TextPanel(
            self, title="4. Corrected Translation",
            header_color="#AB47BC",
        )
        self.panel_corrected_translation.grid(row=1, column=1, sticky="nsew", padx=(2, 0), pady=(2, 0))

    # -- Panel 1: Raw transcription (instant, <1s) --

    def append_raw(self, text: str, speaker: Optional[str] = None):
        self.panel_raw.append(text, speaker=speaker)

    # -- Panel 2: Raw translation (sync with Panel 1) --

    def append_raw_translation(self, text: str):
        self.panel_raw_translation.append(text, tag="translation")

    # -- Panel 3: AI-corrected text with speakers --

    def set_corrected(self, text: str):
        self.panel_corrected.set_text(text)

    def append_corrected(self, text: str, speaker: Optional[str] = None):
        self.panel_corrected.append(text, speaker=speaker)

    # -- Panel 4: Corrected translation --

    def set_corrected_translation(self, text: str):
        self.panel_corrected_translation.set_text(text)

    def append_corrected_translation(self, text: str):
        self.panel_corrected_translation.append(text, tag="translation")

    # -- Common --

    def get_raw_text(self) -> str:
        return self.panel_raw.get_text()

    def get_corrected_text(self) -> str:
        return self.panel_corrected.get_text()

    def get_text(self) -> str:
        """Return best available text (corrected if available, else raw)."""
        corrected = self.get_corrected_text()
        return corrected if corrected else self.get_raw_text()

    def clear(self):
        self.panel_raw.clear()
        self.panel_raw_translation.clear()
        self.panel_corrected.clear()
        self.panel_corrected_translation.clear()


class AnalysisWindow(ctk.CTkToplevel):
    """Popup window for analysis results (Panel 5)."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Analysis")
        self.geometry("900x700")
        self.minsize(700, 500)
        self._dialogue_speaker_map: dict[str, str] = {}
        self._build_ui()

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.summary_tab = self.tabview.add("\U0001f4cb Summary")
        self.protocol_tab = self.tabview.add("\U0001f4dd Protocol")
        self.actions_tab = self.tabview.add("\u2705 Actions")
        self.points_tab = self.tabview.add("\U0001f4cc Key Points")
        self.translate_tab = self.tabview.add("\U0001f310 Translation")
        self.dialogue_tab = self.tabview.add("\U0001f4ac Dialogue")

        # Summary
        self._summary_copy = self._make_copy_btn(self.summary_tab, "summary")
        self.summary_text = ctk.CTkTextbox(
            self.summary_tab, wrap="word", font=("Segoe UI", 13), state="disabled",
        )
        self.summary_text.pack(fill="both", expand=True)

        # Protocol (Meeting Minutes)
        self._protocol_copy = self._make_copy_btn(self.protocol_tab, "protocol")
        self.protocol_text = ctk.CTkTextbox(
            self.protocol_tab, wrap="word", font=("Segoe UI", 13), state="disabled",
        )
        self.protocol_text.pack(fill="both", expand=True)

        # Actions
        self._actions_copy = self._make_copy_btn(self.actions_tab, "actions")
        self.actions_scroll = ctk.CTkScrollableFrame(self.actions_tab)
        self.actions_scroll.pack(fill="both", expand=True)

        # Key points
        self._points_copy = self._make_copy_btn(self.points_tab, "points")
        self.points_text = ctk.CTkTextbox(
            self.points_tab, wrap="word", font=("Segoe UI", 13), state="disabled",
        )
        self.points_text.pack(fill="both", expand=True)

        # Translation
        self._translate_copy = self._make_copy_btn(self.translate_tab, "translate")
        self.translate_text = ctk.CTkTextbox(
            self.translate_tab, wrap="word", font=("Segoe UI", 13), state="disabled",
        )
        self.translate_text.pack(fill="both", expand=True)
        self.translate_text._textbox.tag_configure("original", foreground="#B0BEC5")
        self.translate_text._textbox.tag_configure(
            "trans", foreground="#64B5F6", lmargin1=15, lmargin2=15,
        )

        # Dialogue
        self._dialogue_copy = self._make_copy_btn(self.dialogue_tab, "dialogue")
        self.dialogue_text = ctk.CTkTextbox(
            self.dialogue_tab, wrap="word", font=("Segoe UI", 13), state="disabled",
        )
        self.dialogue_text.pack(fill="both", expand=True)
        for i, color in enumerate(SPEAKER_COLORS):
            self.dialogue_text._textbox.tag_configure(
                f"dlg_speaker_{i}", foreground=color, font=("Segoe UI", 13, "bold"),
            )
        self.dialogue_text._textbox.tag_configure("dlg_text", foreground="#E0E0E0")
        self.dialogue_text._textbox.tag_configure(
            "dlg_translation", foreground="#90CAF9",
            font=("Segoe UI", 12, "italic"), lmargin1=20, lmargin2=20,
        )

    def _make_copy_btn(self, parent, tab_key: str) -> ctk.CTkButton:
        """Create a copy button at the top of a tab."""
        btn = ctk.CTkButton(
            parent, text="\U0001f4cb Copy", width=80, height=28,
            font=("Segoe UI", 12), fg_color="#333333",
            hover_color="#555555",
            command=lambda: self._copy_tab(tab_key, btn),
        )
        btn.pack(anchor="e", padx=8, pady=(4, 2))
        return btn

    def _copy_tab(self, tab_key: str, btn: ctk.CTkButton):
        """Copy content of a specific tab to clipboard."""
        text_map = {
            "summary": lambda: self.summary_text.get("1.0", "end").strip(),
            "protocol": lambda: self.protocol_text.get("1.0", "end").strip(),
            "actions": lambda: "\n".join(
                f"- {w.winfo_children()[1].cget('text')}" if len(w.winfo_children()) > 1 else ""
                for w in self.actions_scroll.winfo_children()
            ),
            "points": lambda: self.points_text.get("1.0", "end").strip(),
            "translate": lambda: self.translate_text.get("1.0", "end").strip(),
            "dialogue": lambda: self.dialogue_text.get("1.0", "end").strip(),
        }
        getter = text_map.get(tab_key)
        text = getter() if getter else ""
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            old_text = btn.cget("text")
            btn.configure(text="\u2705 Copied!")
            self.after(1500, lambda: btn.configure(text=old_text))

    def set_summary(self, text: str):
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", text)
        self.summary_text.configure(state="disabled")

    def set_protocol(self, text: str):
        self.protocol_text.configure(state="normal")
        self.protocol_text.delete("1.0", "end")
        self.protocol_text.insert("1.0", text)
        self.protocol_text.configure(state="disabled")

    def set_actions(self, actions: list[dict]):
        for w in self.actions_scroll.winfo_children():
            w.destroy()
        for action in actions:
            task = action.get("task", "")
            assignee = action.get("assignee", "")
            priority = action.get("priority", "medium")
            color = {"high": "#E53935", "medium": "#FF9800", "low": "#4CAF50"}.get(
                priority, "#FF9800",
            )
            frame = ctk.CTkFrame(self.actions_scroll)
            frame.pack(fill="x", padx=5, pady=3)
            ctk.CTkLabel(
                frame, text=f"[{priority.upper()}]",
                font=("Segoe UI", 11, "bold"), text_color=color, width=70,
            ).pack(side="left", padx=5)
            ctk.CTkLabel(
                frame, text=task, font=("Segoe UI", 12),
                anchor="w", wraplength=400,
            ).pack(side="left", fill="x", expand=True, padx=5)
            if assignee:
                ctk.CTkLabel(
                    frame, text=f"\u2192 {assignee}",
                    font=("Segoe UI", 11), text_color="gray",
                ).pack(side="right", padx=5)

    def set_key_points(self, points: list[str]):
        self.points_text.configure(state="normal")
        self.points_text.delete("1.0", "end")
        for point in points:
            self.points_text.insert("end", f"\u2022 {point}\n\n")
        self.points_text.configure(state="disabled")

    def set_translation(self, original: str, translated: str):
        self.translate_text.configure(state="normal")
        self.translate_text.delete("1.0", "end")
        orig_s = _split_sentences(original)
        trans_s = _split_sentences(translated)
        for o, t in zip_longest(orig_s, trans_s, fillvalue=""):
            if o:
                self.translate_text._textbox.insert("end", f"{o}\n", "original")
            if t:
                self.translate_text._textbox.insert("end", f"  \u2192 {t}\n", "trans")
            self.translate_text._textbox.insert("end", "\n")
        self.translate_text.configure(state="disabled")

    def set_dialogue(self, text: str):
        self.dialogue_text.configure(state="normal")
        self.dialogue_text.delete("1.0", "end")
        self._dialogue_speaker_map.clear()
        tw = self.dialogue_text._textbox
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                tw.insert("end", "\n")
            elif line.startswith("\u2192") or line.startswith("→"):
                tw.insert("end", f"  {line}\n", "dlg_translation")
            elif m := re.match(r'\[(.+?)\]:\s*(.*)', line):
                speaker, content = m.group(1), m.group(2)
                tag = self._get_dlg_tag(speaker)
                tw.insert("end", f"[{speaker}]: ", tag)
                tw.insert("end", f"{content}\n", "dlg_text")
            else:
                tw.insert("end", f"{line}\n", "dlg_text")
        self.dialogue_text.configure(state="disabled")

    def _get_dlg_tag(self, speaker: str) -> str:
        if speaker not in self._dialogue_speaker_map:
            idx = len(self._dialogue_speaker_map) % len(SPEAKER_COLORS)
            self._dialogue_speaker_map[speaker] = f"dlg_speaker_{idx}"
        return self._dialogue_speaker_map[speaker]

    def clear(self):
        self.set_summary("")
        self.set_protocol("")
        for w in self.actions_scroll.winfo_children():
            w.destroy()
        self.set_key_points([])
        self.translate_text.configure(state="normal")
        self.translate_text.delete("1.0", "end")
        self.translate_text.configure(state="disabled")
        self.dialogue_text.configure(state="normal")
        self.dialogue_text.delete("1.0", "end")
        self.dialogue_text.configure(state="disabled")
        self._dialogue_speaker_map.clear()


# Keep backward compat aliases
TranscriptView = TranscriptMultiView
AnalysisPanel = AnalysisWindow


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]
