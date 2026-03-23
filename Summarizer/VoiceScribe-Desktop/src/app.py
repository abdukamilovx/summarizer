"""
Application initialization and entry point.
"""
import customtkinter as ctk

from utils.config import settings
from utils.logger import log


def run():
    log.info("Starting VoiceScribe Desktop...")

    # Start Telegram bot in background (if token is set)
    from telegram_bot import run_bot_background
    run_bot_background()

    ctk.set_appearance_mode(settings.APPEARANCE_MODE)
    ctk.set_default_color_theme(settings.COLOR_THEME)

    from ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()
