"""
VoiceScribe Desktop — AI-powered audio transcription and analysis.

Usage:
    python main.py
"""
import sys
import os

# Add src/ to Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import run

if __name__ == "__main__":
    run()
