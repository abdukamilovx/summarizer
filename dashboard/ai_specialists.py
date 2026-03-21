"""
AI Specialists module for Pearl Project Management
Интеграция специалистов ИИ
"""

# Заглушка для импорта в bot.py
SPECIALISTS_CONFIG = {}

def get_specialist(name):
    return SPECIALISTS_CONFIG.get(name)

def list_specialists():
    return list(SPECIALISTS_CONFIG.keys())
