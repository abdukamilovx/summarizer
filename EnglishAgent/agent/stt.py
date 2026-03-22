import io
import tempfile
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf
from openai import OpenAI


class SpeechToText:
    def __init__(self, api_key: str, sample_rate: int = 16000):
        self.client = OpenAI(api_key=api_key)
        self.sample_rate = sample_rate
        self.recording = False
        self._frames: list[np.ndarray] = []
        self._stream = None

    def start_recording(self):
        """Start recording from microphone."""
        self._frames = []
        self.recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()

    def _audio_callback(self, indata, frames, time, status):
        if self.recording:
            self._frames.append(indata.copy())

    def stop_recording(self) -> bytes:
        """Stop recording and return raw audio data."""
        self.recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._frames:
            return b""

        audio = np.concatenate(self._frames, axis=0)
        buf = io.BytesIO()
        sf.write(buf, audio, self.sample_rate, format="WAV")
        return buf.getvalue()

    def transcribe(self, audio_bytes: bytes) -> str:
        """Send audio to OpenAI Whisper API and return text."""
        if not audio_bytes:
            return ""

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "recording.wav"

        response = self.client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
        )
        return response.text.strip()

    def stop_and_transcribe(self, callback):
        """Stop recording, transcribe in background, call callback with text."""
        audio_bytes = self.stop_recording()
        if not audio_bytes:
            callback("")
            return

        def _work():
            try:
                text = self.transcribe(audio_bytes)
            except Exception as e:
                print(f"STT error: {e}")
                text = ""
            callback(text)

        thread = threading.Thread(target=_work, daemon=True)
        thread.start()
