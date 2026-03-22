import os
import sys

from dotenv import load_dotenv

from agent.teacher import EnglishTeacher
from agent.tts import TextToSpeech
from agent.stt import SpeechToText
from ui.chat_window import ChatWindow


def main():
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env file")
        print("Create a .env file with: OPENAI_API_KEY=sk-your-key-here")
        sys.exit(1)

    teacher = EnglishTeacher(api_key=api_key)
    tts = TextToSpeech(api_key=api_key, voice="nova")
    stt = SpeechToText(api_key=api_key)

    app = ChatWindow(teacher=teacher, tts=tts, stt=stt)
    app.mainloop()


if __name__ == "__main__":
    main()
