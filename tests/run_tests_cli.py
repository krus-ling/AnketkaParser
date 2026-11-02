import asyncio
import os
import sys
import threading
from http.server import HTTPServer

# Гарантируем видимость пакетов core и engines независимо от способа запуска
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Принудительно включаем headless-режим для CLI-тестов
os.environ["BROWSER_HEADLESS"] = "true"
import core.config
core.config.BROWSER_HEADLESS = True

from tests.test_gui import MockServerHandler
from core.brain import SurveyBrain
from engines.router import SurveyRouter


def start_server():
    try:
        server = HTTPServer(('127.0.0.1', 8888), MockServerHandler)
        server.serve_forever()
    except OSError:
        pass


async def run_single_test(url: str, router: SurveyRouter) -> bool:
    print(f"\n[TEST START] Running test: {url}")
    try:
        await asyncio.wait_for(router.run(url), timeout=40.0)
        return True
    except asyncio.TimeoutError:
        print(f"[TEST TIMEOUT] 40s exceeded for: {url}")
        return False
    except Exception as e:
        print(f"[TEST ERROR] {url}: {e}")
        return False


async def main():
    threading.Thread(target=start_server, daemon=True).start()
    await asyncio.sleep(0.5)

    test_urls = [
        "http://127.0.0.1:8888/survstat",
        "http://127.0.0.1:8888/oprosso",
        "http://127.0.0.1:8888/pthwy",
        "http://127.0.0.1:8888/anketka",
        "http://127.0.0.1:8888/cloudsurvey",
        "http://127.0.0.1:8888/surveystudio",
        "http://127.0.0.1:8888/anketolog",
        "http://127.0.0.1:8888/profiresearch",
        "http://127.0.0.1:8888/chat",
    ]

    brain = SurveyBrain()
    router = SurveyRouter(brain=brain)

    results = {}
    for url in test_urls:
        success = await run_single_test(url, router)
        results[url] = success
        await asyncio.sleep(1.0)

    print("\n" + "=" * 55)
    print("📋 SUMMARY OF CLI AUTOMATED E2E TESTS:")
    for url, res in results.items():
        name = url.split('/')[-1].upper()
        status = "✅ PASSED" if res else "❌ FAILED"
        print(f"  • {name:<18} -> {status}")
    print("=" * 55)

    all_passed = all(results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
