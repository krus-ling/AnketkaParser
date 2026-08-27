import os
import asyncio
from playwright.async_api import async_playwright, Page, Error as PlaywrightError
from engines.anketka import AnketkaEngine
from engines.cloudsurvey import CloudSurveyEngine
from engines.chat_survey import ChatSurveyEngine
from engines.base import human_sleep
from brain import SurveyBrain
import config
from engines.profiresearch import ProfiResearchEngine
from engines.anketolog import AnketologEngine
from engines.surveystudio import SurveyStudioEngine
from engines.sawtooth import SawtoothEngine
from bot_state import state  # <-- Убедитесь, что state импортирован


class SurveyRouter:
    def __init__(self, brain: SurveyBrain):
        self.brain = brain
        self.anketka_engine = AnketkaEngine(brain)
        self.cloud_engine = CloudSurveyEngine(brain)
        self.chat_engine = ChatSurveyEngine(brain)
        self.profi_engine = ProfiResearchEngine(brain)
        self.anketolog_engine = AnketologEngine(brain)
        self.surveystudio_engine = SurveyStudioEngine(brain)
        self.sawtooth_engine = SawtoothEngine(brain)

    async def detect_and_dispatch(self, page: Page, body_text: str) -> str:
        url = page.url.lower()

        # === НОВОЕ: Обработка стартовых страниц опросников ===
        is_start_page = await page.evaluate("""() => {
            let bodyText = document.body.innerText.toLowerCase();
            let hasContinueBtn = Array.from(document.querySelectorAll('button, div, span')).some(el => {
                if (el.offsetParent === null) return false;
                let txt = (el.innerText || '').trim().toLowerCase();
                return txt === 'продолжить' || txt === 'начать' || txt === 'начать опрос' || txt === 'подобрать опрос';
            });
            let isIntroText = bodyText.includes('отвечайте внимательно') ||
                bodyText.includes('рейтинг участника') ||
                bodyText.includes('проверочные вопросы') ||
                bodyText.includes('внимательность');
            return hasContinueBtn && isIntroText;
        }""")

        if is_start_page:
            print("\n[i] Обнаружена стартовая страница с инструкцией. Нажимаем «Продолжить»...")
            await page.evaluate("""() => {
                let btn = Array.from(document.querySelectorAll('button, div, span')).find(el => {
                    if (el.offsetParent === null) return false;
                    let txt = (el.innerText || '').trim().toLowerCase();
                    return txt === 'продолжить' || txt === 'начать' || txt === 'начать опрос';
                });
                if (btn) {
                    btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                        btn.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                    });
                    if (btn.click) btn.click();
                }
            }""")
            await human_sleep(2.0, 3.0)
            return 'SUCCESS'
        # =========================================================

        is_finished = await page.evaluate("""() => {
            let container = document.querySelector('.step.active') || document.body;
            let txt = container.innerText.toLowerCase();
            return txt.includes('опрос успешно завершен') || txt.includes('вы изменили мир') || txt.includes('вознаграждени') || txt.includes('зачислено');
        }""")
        if is_finished:
            await self.anketka_engine.handle_completion_and_feedback(page, body_text)
            await self.anketka_engine.handle_anketka_reward(page)
            return 'FINISHED'

        if await self.anketka_engine.handle_modal_popup(page):
            return 'SUCCESS'

        is_cloud = (
                "cloudsurvey" in url or "survstat" in url or "enjoy" in url or
                "mock" in url or "127.0.0.1" in url or "localhost" in url or
                "expertnoemnenie" in url or "panel." in url or
                (await page.query_selector(
                    "button#__next, div[class*='QuestionDate'], .scale-main-answers-container, .date-control, div[class*='DropDown_container']")) is not None
        )

        is_chat = "chat" in url or "bot" in url or (
            await page.query_selector("div.chat-container, div[class*='Chat']")) is not None
        is_profi = "profiresearch" in url
        is_anketolog = "anketolog.ru" in url
        is_surveystudio = "survey-studio.com" in url or "surveystudio" in url
        is_sawtooth = "survey.dataction.biz" in url or "ciwweb.pl" in url

        if is_chat:
            handled = await self.chat_engine.process_step(page, body_text.lower())
        elif is_surveystudio:
            handled = await self.surveystudio_engine.process_step(page, body_text.lower())
        elif is_anketolog:
            handled = await self.anketolog_engine.process_step(page, body_text.lower())
        elif is_sawtooth:
            handled = await self.sawtooth_engine.process_step(page, body_text.lower())
        elif is_profi:
            handled = await self.profi_engine.process_step(page, body_text.lower())
        elif is_cloud:
            handled = await self.cloud_engine.process_step(page, body_text.lower())
        else:
            handled = await self.anketka_engine.process_step(page, body_text.lower())

        return 'SUCCESS' if handled else 'UNHANDLED'

    async def run(self, start_url: str):
        async with async_playwright() as p:
            profile_dir = os.path.join(os.getcwd(), "bot_profile")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars"
                ]
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            print(f"[+] Открываем ссылку: {start_url}")
            try:
                await page.goto(start_url, wait_until="load", timeout=60000)
                await human_sleep(2.0, 3.0)

                stuck_counter = 0
                last_body_hash = ""

                while True:
                    if page.is_closed():
                        print("\n[!] Окно браузера закрыто пользователем. Тест приостановлен.")
                        break

                    try:
                        body_text = await page.inner_text("body")
                    except Exception:
                        if page.is_closed():
                            break
                        await asyncio.sleep(1.0)
                        continue

                    current_hash = hash(body_text.strip()[:300])
                    if current_hash == last_body_hash:
                        stuck_counter += 1
                    else:
                        stuck_counter = 0
                        last_body_hash = current_hash

                    # === ИСПРАВЛЕНИЕ РЕЖИМА ОТЛАДКИ ПРИ ЗАВИСАНИИ ===
                    if stuck_counter >= 3:
                        print("\n" + "⚠️ " * 30)
                        print("[!] Бот не смог выполнить действие на этом шаге.")

                        if state.is_debug:
                            print("[!] ОТЛАДОЧНЫЙ РЕЖИМ: Нажмите '✅ Подтвердить шаг' в интерфейсе, чтобы продолжить.")
                            await state.wait_debug_confirm()  # Ждем нажатия кнопки в GUI!
                            stuck_counter = 0
                            print("[✓] Шаг подтвержден вручную. Продолжаем работу...")
                        else:
                            print("[!] Ожидание ручного действия (выберите ответ / нажмите кнопку в окне браузера)...")
                            print("⚠️ " * 30 + "\n")
                            while not page.is_closed():
                                await asyncio.sleep(1.5)
                                try:
                                    new_body = await page.inner_text("body")
                                    if hash(new_body.strip()[:300]) != last_body_hash:
                                        print("[✓] Обнаружено ручное изменение страницы! Продолжаем работу...")
                                        stuck_counter = 0
                                        last_body_hash = hash(new_body.strip()[:300])
                                        break
                                except Exception:
                                    break
                        continue
                    # ==================================================

                    try:
                        status = await self.detect_and_dispatch(page, body_text)
                    except Exception as step_err:
                        print(f"[!] Внутренняя ошибка парсера: {step_err}")
                        status = 'UNHANDLED'

                    if status == 'FINISHED':
                        print("\n" + "=" * 65)
                        print("📊 ИТОГОВАЯ СТАТИСТИКА ПРОХОЖДЕНИЯ ОПРОСА:")
                        print(f"   • Всего вопросов/подвопросов в анкете: 15")
                        print(
                            f"   • Успешно отвечено ботом:             {self.brain.stats.get('total_answered', 0)}/15")
                        print(f"   • Использовано из базы памяти (Memory): {self.brain.stats.get('from_memory', 0)}")
                        print(f"   • Решено правилами/профилем (Rules):   {self.brain.stats.get('from_rules', 0)}")
                        print(f"   • Обработано нейросетью (LLM):          {self.brain.stats.get('from_llm', 0)}")
                        print("=" * 65)
                        print("🎉 [ГОТОВО] Сценарий опроса завершен.")
                        await human_sleep(3.0, 5.0)
                        break
                    elif status == 'UNHANDLED':
                        stuck_counter += 1

                    await human_sleep(1.5, 2.5)

            except PlaywrightError as pe:
                if "closed" in str(pe).lower():
                    print("\n[!] Окно браузера было закрыто. Работа парсера остановлена.")
                else:
                    print(f"\n[!] Системная ошибка браузера: {pe}")
            except Exception as e:
                print(f"\n[!] Ошибка выполнения: {e}")
            finally:
                if not page.is_closed():
                    await context.close()