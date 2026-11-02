import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Настройка безопасной кодировки вывода терминала (Windows UTF-8 поддержка)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Пути к файлам проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Загрузка переменных окружения из .env (если файл существует)
load_dotenv(BASE_DIR / ".env")

PROFILE_PATH = Path(os.getenv("PROFILE_PATH", str(BASE_DIR / "data" / "profile.json")))
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "survey_memory.db")))

# Настройки LLM (по умолчанию локальная Ollama)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:14b")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "25.0"))

# Настройки окна браузера и антидетекта
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() in ("true", "1", "yes")
BROWSER_WIDTH = int(os.getenv("BROWSER_WIDTH", "1600"))
BROWSER_HEIGHT = int(os.getenv("BROWSER_HEIGHT", "1200"))
E2E_SERVER_PORT = int(os.getenv("E2E_SERVER_PORT", "8888"))

# Настройки для зрения (Google Gemini Free Tier или совместимый API)
VISION_BASE_URL = os.getenv("VISION_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
VISION_API_KEY = os.getenv("VISION_API_KEY", "")
VISION_MODEL = os.getenv("VISION_MODEL", "gemini-2.5-flash")

# Локальный прокси для обхода блокировок Google API (если требуется)
GEMINI_PROXY = os.getenv("GEMINI_PROXY", "http://127.0.0.1:7890")

# Сетевые настройки браузера (раздельная маршрутизация / обход VPN)
# BROWSER_PROXY: явный прокси для Chromium (например, "http://login:pass@ru-proxy.com:8080" или "socks5://127.0.0.1:1080")
BROWSER_PROXY = os.getenv("BROWSER_PROXY", None)
# BROWSER_DIRECT: если True, Chromium игнорирует системный WinINet прокси Windows (--no-proxy-server)
BROWSER_DIRECT = os.getenv("BROWSER_DIRECT", "false").lower() in ("true", "1", "yes")
# Проверять ли внешний IP браузера при старте
CHECK_BROWSER_IP = os.getenv("CHECK_BROWSER_IP", "true").lower() in ("true", "1", "yes")

# Настройки реалистичного поведения (Human-like delays & movements)
HUMAN_LIKE_DELAYS = os.getenv("HUMAN_LIKE_DELAYS", "true").lower() in ("true", "1", "yes")

# Настройки уведомлений в Telegram
TELEGRAM_NOTIFICATIONS_ENABLED = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "false").lower() in ("true", "1", "yes")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

