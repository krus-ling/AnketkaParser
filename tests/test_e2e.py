# E2E (End-to-End / «сквозное тестирование») — это тип тестирования, при котором система проверяется целиком
# от начала до конца. В отличие от тестов отдельных функций, E2E запускает локальный веб-сервер,
# открывает настоящий браузер Playwright, заполняет формы, опрашивает LLM и
# проверяет успешное завершение опроса вплоть до финального экрана.

import asyncio
import sys
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
from brain import SurveyBrain
from engines import SurveyRouter

def start_server():
    handler = partial(SimpleHTTPRequestHandler, directory=str(TESTS_DIR))
    server = HTTPServer(("127.0.0.1", config.E2E_SERVER_PORT), handler)
    server.serve_forever()

async def run_e2e_test():
    print("=" * 65)
    print(f"🚀 ЗАПУСК СКВОЗНОГО ТЕСТИРОВАНИЯ (E2E MOCK SURVEY) [{config.LLM_MODEL}]")
    print("=" * 65)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    print(f"[+] Тестовый сервер поднят на http://127.0.0.1:{config.E2E_SERVER_PORT}/mock_survey.html")

    brain = SurveyBrain()
    router = SurveyRouter(brain=brain)

    test_url = f"http://127.0.0.1:{config.E2E_SERVER_PORT}/mock_survey.html"
    await router.run(test_url)

if __name__ == "__main__":
    asyncio.run(run_e2e_test())