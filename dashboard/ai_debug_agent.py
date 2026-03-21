"""
AI Debug Agent for Pearl Dashboard + Telegram
Автоматическая проверка и отладка связки по пользовательским запросам
"""
import requests, time

class PearlAIAgent:
    def __init__(self, dashboard_url, telegram_bot_token):
        self.dashboard_url = dashboard_url
        self.bot_token = telegram_bot_token

    def check_dashboard(self):
        try:
            r = requests.get(f'{self.dashboard_url}/api/debug/models')
            return r.json()
        except Exception as e:
            return {'error': str(e)}

    def check_telegram(self):
        try:
            r = requests.get(f'https://api.telegram.org/bot{self.bot_token}/getMe')
            return r.json()
        except Exception as e:
            return {'error': str(e)}

    def sync_check(self):
        dash = self.check_dashboard()
        tg = self.check_telegram()
        return {'dashboard': dash, 'telegram': tg}

    def run_auto_debug(self):
        result = self.sync_check()
        # Можно добавить дополнительные проверки и логику
        return result

# Пример использования:
# agent = PearlAIAgent('http://localhost:5050', 'YOUR_TELEGRAM_BOT_TOKEN')
# print(agent.run_auto_debug())
