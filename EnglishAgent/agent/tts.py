import io
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf
from openai import OpenAI


class TextToSpeech:
    def __init__(self, api_key: str, voice: str = "nova"):
        self.client = OpenAI(api_key=api_key)
        self.voice = voice
        self.enabled = True
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def speak(self, text: str):
        """Speak text in a background thread so UI doesn't freeze."""
        if not self.enabled:
            return
        self._stop_event.clear()
        thread = threading.Thread(target=self._play, args=(text,), daemon=True)
        thread.start()

    def _play(self, text: str):
        with self._lock:
            try:
                response = self.client.audio.speech.create(
                    model="tts-1",
                    voice=self.voice,
                    input=text,
                    response_format="wav",
                )

                audio_data = io.BytesIO(response.content)
                data, samplerate = sf.read(audio_data, dtype="float32")

                if self._stop_event.is_set():
                    return

                sd.play(data, samplerate)
                sd.wait()
            except Exception as e:
                print(f"TTS error: {e}")

    def stop(self):
        """Stop any currently playing audio."""
        self._stop_event.set()
        try:
            sd.stop()
        except Exception:
            pass

    def toggle(self) -> bool:
        """Toggle TTS on/off. Returns new state."""
        self.enabled = not self.enabled
        if not self.enabled:
            self.stop()
        return self.enabled
