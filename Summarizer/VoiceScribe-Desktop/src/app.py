"""
Application initialization and entry point.
"""
import customtkinter as ctk

from utils.config import settings
from utils.logger import log


def run():
    log.info("Starting VoiceScribe Desktop...")

    ctk.set_appearance_mode(settings.APPEARANCE_MODE)
    ctk.set_default_color_theme(settings.COLOR_THEME)

    from ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()
