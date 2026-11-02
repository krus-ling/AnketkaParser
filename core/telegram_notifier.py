"""
Telegram Notifier Module for AnketkaParser.
Отправка уведомлений о завершении опросов, начисленных баллах/деньгах,
капчах и предупреждениях о сети.
"""

import os
import requests
from typing import Optional
from core import config


class TelegramNotifier:
    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: Optional[bool] = None,
        proxy: Optional[str] = None
    ):
        self.token = token or getattr(config, "TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or getattr(config, "TELEGRAM_CHAT_ID", "")
        self.enabled = (
            enabled if enabled is not None
            else getattr(config, "TELEGRAM_NOTIFICATIONS_ENABLED", False)
        )
        self.proxy = proxy or getattr(config, "GEMINI_PROXY", None)

    @property
    def is_active(self) -> bool:
        return bool(self.enabled and self.token and self.chat_id)

    def _get_proxies(self) -> Optional[dict]:
        if self.proxy:
            return {"http": self.proxy, "https": self.proxy}
        return None

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Отправка текстового сообщения в Telegram."""
        if not self.is_active:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }

        try:
            resp = requests.post(
                url,
                json=payload,
                proxies=self._get_proxies(),
                timeout=10
            )
            return resp.status_code == 200
        except Exception as e:
            # Если через прокси не прошло — пробуем прямое соединение
            try:
                resp = requests.post(url, json=payload, timeout=10)
                return resp.status_code == 200
            except Exception:
                return False

    def send_photo(self, photo_path: str, caption: str = "") -> bool:
        """Отправка скриншота/фото в Telegram."""
        if not self.is_active or not os.path.exists(photo_path):
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        data = {
            "chat_id": self.chat_id,
            "caption": caption[:1024],
            "parse_mode": "HTML"
        }

        try:
            with open(photo_path, "rb") as f:
                resp = requests.post(
                    url,
                    data=data,
                    files={"photo": f},
                    proxies=self._get_proxies(),
                    timeout=20
                )
                return resp.status_code == 200
        except Exception:
            try:
                with open(photo_path, "rb") as f:
                    resp = requests.post(url, data=data, files={"photo": f}, timeout=20)
                    return resp.status_code == 200
            except Exception:
                return False

    def notify_survey_completed(self, platform_name: str, reward_text: str = ""):
        """Оповещение об успешном прохождении опроса."""
        msg = (
            f"🎉 <b>Опрос успешно завершён!</b>\n"
            f"📊 <b>Платформа:</b> {platform_name}\n"
        )
        if reward_text:
            msg += f"💰 <b>Вознаграждение:</b> {reward_text}\n"
        self.send_message(msg)

    def notify_manual_action(self, reason: str, screenshot_path: Optional[str] = None):
        """Оповещение о необходимости ручного вмешательства (капча, застревание)."""
        msg = (
            f"⚠️ <b>Требуется действие пользователя!</b>\n"
            f"❓ <b>Причина:</b> {reason}\n"
            f"👉 Пожалуйста, откройте окно браузера и подтвердите действие."
        )
        if screenshot_path and os.path.exists(screenshot_path):
            self.send_photo(screenshot_path, caption=msg)
        else:
            self.send_message(msg)

    def notify_ip_warning(self, ip: str, country: str):
        """Предупреждение о нероссийском IP адресе."""
        msg = (
            f"🌐 <b>Внимание: Нероссийский IP!</b>\n"
            f"📍 IP: <code>{ip}</code> ({country})\n"
            f"⚠️ Опросники РФ могут заблокировать аккаунт или отклонить выплату при работе через иностранный VPN."
        )
        self.send_message(msg)


# Глобальный экземпляр
notifier = TelegramNotifier()
