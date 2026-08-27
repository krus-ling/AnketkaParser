from pathlib import Path

# Пути к файлам проекта
ROOT_DIR = Path(__file__).resolve().parent
PROFILE_PATH = ROOT_DIR / "profile.json"
DB_PATH = ROOT_DIR / "survey_memory.db"

# Настройки LLM
LLM_BASE_URL = "http://localhost:11434/v1"
LLM_API_KEY = "ollama"
LLM_MODEL = "qwen2.5:14b"
LLM_TIMEOUT = 15.0

# Настройки окна браузера
BROWSER_HEADLESS = False
BROWSER_WIDTH = 1200
BROWSER_HEIGHT = 800
E2E_SERVER_PORT = 8888