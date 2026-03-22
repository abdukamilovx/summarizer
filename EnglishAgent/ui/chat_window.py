import threading
import customtkinter as ctk

from agent.prompts import TeacherMode


class ChatWindow(ctk.CTk):
    def __init__(self, teacher, tts, stt):
        super().__init__()

        self.teacher = teacher
        self.tts = tts
        self.stt = stt
        self._is_recording = False

        self.title("English Teacher Agent")
        self.geometry("500x700")
        self.minsize(400, 500)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self._build_ui()
        self.after(500, self._start_lesson)

    def _build_ui(self):
        # Top bar
        top_frame = ctk.CTkFrame(self, fg_color="#4A90D9", corner_radius=0, height=50)
        top_frame.pack(fill="x")
        top_frame.pack_propagate(False)

        ctk.CTkLabel(
            top_frame,
            text="English Teacher",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="white",
        ).pack(side="left", padx=15, pady=10)

        self.sound_btn = ctk.CTkButton(
            top_frame,
            text="Sound: ON",
            width=100,
            height=30,
            fg_color="#3A7BC8",
            hover_color="#2E6AB0",
            command=self._toggle_sound,
        )
        self.sound_btn.pack(side="right", padx=5, pady=10)

        self.mode_btn = ctk.CTkButton(
            top_frame,
            text="Mode: Kids",
            width=100,
            height=30,
            fg_color="#3A7BC8",
            hover_color="#2E6AB0",
            command=self._toggle_mode,
        )
        self.mode_btn.pack(side="right", padx=5, pady=10)

        ctk.CTkButton(
            top_frame,
            text="New Lesson",
            width=100,
            height=30,
            fg_color="#3A7BC8",
            hover_color="#2E6AB0",
            command=self._new_lesson,
        ).pack(side="right", padx=5, pady=10)

        # Chat area
        self.chat_frame = ctk.CTkScrollableFrame(
            self, fg_color="#F0F4F8", corner_radius=0
        )
        self.chat_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Typing indicator
        self.typing_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#888888",
            anchor="w",
        )
        self.typing_label.pack(fill="x", padx=15, pady=(2, 0))

        # Input area
        input_frame = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=0, height=60)
        input_frame.pack(fill="x", side="bottom")
        input_frame.pack_propagate(False)

        # Mic button
        self.mic_btn = ctk.CTkButton(
            input_frame,
            text="🎤",
            width=45,
            height=40,
            corner_radius=20,
            fg_color="#E8E8E8",
            hover_color="#D0D0D0",
            text_color="#333333",
            font=ctk.CTkFont(size=18),
            command=self._toggle_recording,
        )
        self.mic_btn.pack(side="left", padx=(10, 5), pady=10)

        self.input_field = ctk.CTkEntry(
            input_frame,
            placeholder_text="Type or hold mic to speak...",
            font=ctk.CTkFont(size=14),
            height=40,
            corner_radius=20,
        )
        self.input_field.pack(side="left", fill="x", expand=True, padx=(5, 5), pady=10)
        self.input_field.bind("<Return>", lambda e: self._send_message())

        ctk.CTkButton(
            input_frame,
            text="Send",
            width=70,
            height=40,
            corner_radius=20,
            fg_color="#4A90D9",
            hover_color="#3A7BC8",
            command=self._send_message,
        ).pack(side="right", padx=(5, 10), pady=10)

    def _toggle_recording(self):
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._is_recording = True
        self.mic_btn.configure(
            fg_color="#FF4444",
            hover_color="#CC3333",
            text_color="white",
            text="⏹",
        )
        self.typing_label.configure(text="Listening...")
        self.tts.stop()
        self.stt.start_recording()

    def _stop_recording(self):
        self._is_recording = False
        self.mic_btn.configure(
            fg_color="#E8E8E8",
            hover_color="#D0D0D0",
            text_color="#333333",
            text="🎤",
        )
        self.typing_label.configure(text="Transcribing...")
        self.stt.stop_and_transcribe(
            callback=lambda text: self.after(0, self._on_transcription, text)
        )

    def _on_transcription(self, text: str):
        self.typing_label.configure(text="")
        if not text:
            return
        self.input_field.delete(0, "end")
        self.input_field.insert(0, text)
        self._send_message()

    def _add_bubble(self, text: str, is_user: bool):
        bubble_frame = ctk.CTkFrame(
            self.chat_frame,
            fg_color="#4A90D9" if is_user else "#FFFFFF",
            corner_radius=15,
        )

        anchor = "e" if is_user else "w"
        padx = (80, 10) if is_user else (10, 80)

        bubble_frame.pack(fill="x", padx=padx, pady=5, anchor=anchor)

        ctk.CTkLabel(
            bubble_frame,
            text=text,
            font=ctk.CTkFont(size=14),
            text_color="white" if is_user else "#333333",
            wraplength=350,
            justify="left",
            anchor="w",
        ).pack(padx=12, pady=8)

        # Auto-scroll to bottom
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    def _send_message(self):
        text = self.input_field.get().strip()
        if not text:
            return

        self.input_field.delete(0, "end")
        self._add_bubble(text, is_user=True)
        self._set_typing(True)

        thread = threading.Thread(target=self._get_response, args=(text,), daemon=True)
        thread.start()

    def _get_response(self, user_text: str):
        try:
            response = self.teacher.chat(user_text)
        except Exception as e:
            response = "Oops! Something went wrong. Please try again."
            print(f"Agent error: {e}")

        self.after(0, self._show_response, response)

    def _show_response(self, text: str):
        self._set_typing(False)
        self._add_bubble(text, is_user=False)
        self.tts.speak(text)

    def _set_typing(self, typing: bool):
        self.typing_label.configure(
            text="Teacher is typing..." if typing else ""
        )

    def _start_lesson(self):
        self._set_typing(True)
        thread = threading.Thread(target=self._init_lesson, daemon=True)
        thread.start()

    def _init_lesson(self):
        try:
            response = self.teacher.start_lesson()
        except Exception as e:
            response = "Hi there! I'm your English teacher. Let's learn together!"
            print(f"Agent error: {e}")
        self.after(0, self._show_response, response)

    def _new_lesson(self):
        self.teacher.reset()
        for widget in self.chat_frame.winfo_children():
            widget.destroy()
        self.tts.stop()
        self.after(300, self._start_lesson)

    def _toggle_mode(self):
        if self.teacher.mode == TeacherMode.KIDS:
            self.teacher.set_mode(TeacherMode.ADULT)
            self.mode_btn.configure(text="Mode: Adult")
        else:
            self.teacher.set_mode(TeacherMode.KIDS)
            self.mode_btn.configure(text="Mode: Kids")
        self._new_lesson()

    def _toggle_sound(self):
        enabled = self.tts.toggle()
        self.sound_btn.configure(text=f"Sound: {'ON' if enabled else 'OFF'}")
