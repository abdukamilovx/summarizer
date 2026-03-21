"""
Transcript display and analysis panels.

Dual-path design:
- Text appears INSTANTLY from 1-sec Whisper chunks
- Every 5 chunks: blocks are replaced with corrected text + translation
- Correction = re-transcription with Whisper (5-sec combined) + GPT word comparison
"""
import re
from itertools import zip_longest

import customtkinter as ctk
from typing import Optional

SPEAKER_COLORS = ["#42A5F5", "#66BB6A", "#FFA726", "#AB47BC", "#EF5350", "#26C6DA"]


class TranscriptView(ctk.CTkFrame):
    """Left panel showing the live/final transcript.

    Blocks are appended instantly (1-sec chunks).
    Every 5 blocks, the group is replaced with corrected + translated text.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._speaker_color_map: dict[str, str] = {}
        self._block_marks: list[str] = []  # Mark names for each block start
        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkLabel(
            self,
            text="\U0001f4dd \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
        )
        header.pack(fill="x", padx=10, pady=(10, 5))

        self.textbox = ctk.CTkTextbox(
            self,
            font=("Segoe UI", 14),
            wrap="word",
            state="disabled",
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tw = self.textbox._textbox

        # Speaker color tags
        for i, color in enumerate(SPEAKER_COLORS):
            tw.tag_configure(
                f"speaker_{i}", foreground=color, font=("Segoe UI", 14, "bold")
            )

        # Translation tag (blue italic, indented)
        tw.tag_configure(
            "translation_inline", foreground="#64B5F6",
            font=("Segoe UI", 12, "italic"), lmargin1=20, lmargin2=20,
        )

    def _get_speaker_tag(self, speaker: str) -> str:
        """Get or assign a color tag for a speaker."""
        if speaker not in self._speaker_color_map:
            idx = len(self._speaker_color_map) % len(SPEAKER_COLORS)
            self._speaker_color_map[speaker] = f"speaker_{idx}"
        return self._speaker_color_map[speaker]

    def append_text(self, text: str, speaker: Optional[str] = None):
        """Append text immediately. Creates a new block with a mark."""
        self.textbox.configure(state="normal")
        tw = self.textbox._textbox

        # Place a mark at the start of this block
        block_id = f"block_{len(self._block_marks)}"
        tw.mark_set(block_id, "end-1c")
        tw.mark_gravity(block_id, "left")
        self._block_marks.append(block_id)

        if speaker:
            tag = self._get_speaker_tag(speaker)
            tw.insert("end", f"[{speaker}]: ", tag)
            tw.insert("end", f"{text}\n")
        else:
            tw.insert("end", f"{text}\n")

        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def append_translation(self, text: str):
        """Append inline translation below the last block."""
        self.textbox.configure(state="normal")
        tw = self.textbox._textbox
        tw.insert("end", f"  \u2192 {text}\n", "translation_inline")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def update_block_group(
        self,
        start_idx: int,
        end_idx: int,
        corrected_text: str,
        translated_text: Optional[str] = None,
        speaker: Optional[str] = None,
    ):
        """Replace blocks [start_idx..end_idx] with corrected text + optional translation.

        Used by the slow path: after re-transcription and GPT comparison,
        the group of instant blocks is replaced with the corrected version.
        """
        if start_idx >= len(self._block_marks):
            return
        end_idx = min(end_idx, len(self._block_marks) - 1)

        self.textbox.configure(state="normal")
        tw = self.textbox._textbox

        try:
            start_mark = self._block_marks[start_idx]
            start_pos = tw.index(start_mark)

            # Find end of range: next block after end_idx, or end of text
            if end_idx + 1 < len(self._block_marks):
                end_pos = tw.index(self._block_marks[end_idx + 1])
            else:
                end_pos = tw.index("end-1c")

            # Delete the entire range
            tw.delete(start_pos, end_pos)

            # Insert corrected text at start_mark
            if speaker:
                tag = self._get_speaker_tag(speaker)
                tw.insert(start_mark, f"[{speaker}]: {corrected_text}\n", tag)
            else:
                tw.insert(start_mark, f"{corrected_text}\n")

            # Insert translation below if provided
            if translated_text:
                # Find end of the corrected line
                corrected_end = tw.index(f"{start_mark} lineend+1c")
                tw.insert(corrected_end, f"  \u2192 {translated_text}\n", "translation_inline")

        except Exception:
            # Fallback: append
            tw.insert("end", f"{corrected_text}\n")
            if translated_text:
                tw.insert("end", f"  \u2192 {translated_text}\n", "translation_inline")

        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def set_text(self, text: str):
        """Replace all text (used for final display after recording stops)."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self._speaker_color_map.clear()
        self._block_marks.clear()
        tw = self.textbox._textbox

        for line in text.split("\n"):
            if m := re.match(r'\[(.+?)\]:\s*(.*)', line):
                speaker, content = m.group(1), m.group(2)
                tag = self._get_speaker_tag(speaker)
                block_id = f"block_{len(self._block_marks)}"
                tw.mark_set(block_id, "end-1c")
                tw.mark_gravity(block_id, "left")
                self._block_marks.append(block_id)
                tw.insert("end", f"[{speaker}]: ", tag)
                tw.insert("end", f"{content}\n")
            elif line.strip().startswith("\u2192"):
                tw.insert("end", f"{line}\n", "translation_inline")
            elif line.strip():
                block_id = f"block_{len(self._block_marks)}"
                tw.mark_set(block_id, "end-1c")
                tw.mark_gravity(block_id, "left")
                self._block_marks.append(block_id)
                tw.insert("end", f"{line}\n")

        self.textbox.configure(state="disabled")

    def get_text(self) -> str:
        return self.textbox.get("1.0", "end").strip()

    def clear(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self._speaker_color_map.clear()
        self._block_marks.clear()


class AnalysisPanel(ctk.CTkFrame):
    """Right panel with tabs for summary, action items, key points, translation, dialogue."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._dialogue_speaker_map: dict[str, str] = {}
        self._build_ui()

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=5, pady=5)

        # Tabs
        self.summary_tab = self.tabview.add("\U0001f4cb \u0420\u0435\u0437\u044e\u043c\u0435")
        self.actions_tab = self.tabview.add("\u2705 \u0417\u0430\u0434\u0430\u0447\u0438")
        self.points_tab = self.tabview.add("\U0001f4cc \u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435")
        self.translate_tab = self.tabview.add("\U0001f310 \u041f\u0435\u0440\u0435\u0432\u043e\u0434")
        self.dialogue_tab = self.tabview.add("\U0001f4ac \u0414\u0438\u0430\u043b\u043e\u0433")

        # Summary
        self.summary_text = ctk.CTkTextbox(
            self.summary_tab, wrap="word", font=("Segoe UI", 13), state="disabled"
        )
        self.summary_text.pack(fill="both", expand=True)

        # Actions
        self.actions_scroll = ctk.CTkScrollableFrame(self.actions_tab)
        self.actions_scroll.pack(fill="both", expand=True)

        # Key points
        self.points_text = ctk.CTkTextbox(
            self.points_tab, wrap="word", font=("Segoe UI", 13), state="disabled"
        )
        self.points_text.pack(fill="both", expand=True)

        # Translation
        self.translate_text = ctk.CTkTextbox(
            self.translate_tab, wrap="word", font=("Segoe UI", 13), state="disabled"
        )
        self.translate_text.pack(fill="both", expand=True)
        self.translate_text._textbox.tag_configure("original", foreground="#B0BEC5")
        self.translate_text._textbox.tag_configure(
            "translation", foreground="#64B5F6", lmargin1=15, lmargin2=15
        )

        # Dialogue
        self.dialogue_text = ctk.CTkTextbox(
            self.dialogue_tab, wrap="word", font=("Segoe UI", 13), state="disabled"
        )
        self.dialogue_text.pack(fill="both", expand=True)

        for i, color in enumerate(SPEAKER_COLORS):
            self.dialogue_text._textbox.tag_configure(
                f"dlg_speaker_{i}", foreground=color, font=("Segoe UI", 13, "bold")
            )
        self.dialogue_text._textbox.tag_configure("dlg_text", foreground="#E0E0E0")
        self.dialogue_text._textbox.tag_configure(
            "dlg_translation", foreground="#90CAF9",
            font=("Segoe UI", 12, "italic"), lmargin1=20, lmargin2=20,
        )

    def set_summary(self, text: str):
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", text)
        self.summary_text.configure(state="disabled")

    def set_actions(self, actions: list[dict]):
        for w in self.actions_scroll.winfo_children():
            w.destroy()

        for i, action in enumerate(actions, 1):
            task = action.get("task", "")
            assignee = action.get("assignee", "")
            priority = action.get("priority", "medium")

            color = {"high": "#E53935", "medium": "#FF9800", "low": "#4CAF50"}.get(
                priority, "#FF9800"
            )

            frame = ctk.CTkFrame(self.actions_scroll)
            frame.pack(fill="x", padx=5, pady=3)

            prio_label = ctk.CTkLabel(
                frame,
                text=f"[{priority.upper()}]",
                font=("Segoe UI", 11, "bold"),
                text_color=color,
                width=70,
            )
            prio_label.pack(side="left", padx=5)

            task_label = ctk.CTkLabel(
                frame,
                text=task,
                font=("Segoe UI", 12),
                anchor="w",
                wraplength=300,
            )
            task_label.pack(side="left", fill="x", expand=True, padx=5)

            if assignee:
                who_label = ctk.CTkLabel(
                    frame,
                    text=f"\u2192 {assignee}",
                    font=("Segoe UI", 11),
                    text_color="gray",
                )
                who_label.pack(side="right", padx=5)

    def set_key_points(self, points: list[str]):
        self.points_text.configure(state="normal")
        self.points_text.delete("1.0", "end")
        for point in points:
            self.points_text.insert("end", f"\u2022 {point}\n\n")
        self.points_text.configure(state="disabled")

    def set_translation(self, original: str, translated: str):
        """Display original and translated text side-by-side, sentence by sentence."""
        self.translate_text.configure(state="normal")
        self.translate_text.delete("1.0", "end")

        orig_sentences = _split_sentences(original)
        trans_sentences = _split_sentences(translated)

        for orig, trans in zip_longest(orig_sentences, trans_sentences, fillvalue=""):
            if orig:
                self.translate_text._textbox.insert("end", f"{orig}\n", "original")
            if trans:
                self.translate_text._textbox.insert("end", f"  \u2192 {trans}\n", "translation")
            self.translate_text._textbox.insert("end", "\n")

        self.translate_text.configure(state="disabled")

    def set_dialogue(self, text: str):
        """Display structured dialogue with colored speaker names."""
        self.dialogue_text.configure(state="normal")
        self.dialogue_text.delete("1.0", "end")
        self._dialogue_speaker_map.clear()

        tw = self.dialogue_text._textbox

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                tw.insert("end", "\n")
                continue

            if line.startswith("\u2192") or line.startswith("→"):
                tw.insert("end", f"  {line}\n", "dlg_translation")
            elif m := re.match(r'\[(.+?)\]:\s*(.*)', line):
                speaker, content = m.group(1), m.group(2)
                tag = self._get_dialogue_speaker_tag(speaker)
                tw.insert("end", f"[{speaker}]: ", tag)
                tw.insert("end", f"{content}\n", "dlg_text")
            else:
                tw.insert("end", f"{line}\n", "dlg_text")

        self.dialogue_text.configure(state="disabled")

    def _get_dialogue_speaker_tag(self, speaker: str) -> str:
        if speaker not in self._dialogue_speaker_map:
            idx = len(self._dialogue_speaker_map) % len(SPEAKER_COLORS)
            self._dialogue_speaker_map[speaker] = f"dlg_speaker_{idx}"
        return self._dialogue_speaker_map[speaker]

    def clear(self):
        self.set_summary("")
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


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]
