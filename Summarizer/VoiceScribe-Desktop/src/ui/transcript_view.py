"""
Transcript display and analysis panels.
"""
import customtkinter as ctk
from typing import Optional


class TranscriptView(ctk.CTkFrame):
    """Left panel showing the live/final transcript."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
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

    def append_text(self, text: str, speaker: Optional[str] = None):
        """Append text to the transcript view."""
        self.textbox.configure(state="normal")
        prefix = f"[{speaker}]: " if speaker else ""
        self.textbox.insert("end", f"{prefix}{text}\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def set_text(self, text: str):
        """Replace all text."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self.textbox.configure(state="disabled")

    def get_text(self) -> str:
        return self.textbox.get("1.0", "end").strip()

    def clear(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")


class AnalysisPanel(ctk.CTkFrame):
    """Right panel with tabs for summary, action items, key points."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=5, pady=5)

        # Tabs
        self.summary_tab = self.tabview.add("\U0001f4cb \u0420\u0435\u0437\u044e\u043c\u0435")
        self.actions_tab = self.tabview.add("\u2705 \u0417\u0430\u0434\u0430\u0447\u0438")
        self.points_tab = self.tabview.add("\U0001f4cc \u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435")

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

    def clear(self):
        self.set_summary("")
        for w in self.actions_scroll.winfo_children():
            w.destroy()
        self.set_key_points([])
