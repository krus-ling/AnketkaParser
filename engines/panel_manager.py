import asyncio
from urllib.parse import urlparse
from playwright.async_api import Page
from core.bot_state import state
from engines.base import human_sleep
from engines.js_snippets import (
    JS_SCAN_PANEL_SURVEYS,
    JS_HANDLE_SURVEY_HUB,
    JS_CHECK_AND_HANDLE_FINISH_ACTIONS
)

# Список сайтов для циклического мульти-фарминга (Центр Опросов)
PANEL_SITES = [
    {
        "id": "anketka",
        "name": "Анкетка",
        "url": "https://www.anketka.ru/profile",
        "domain": "anketka.ru"
    },
    {
        "id": "internetopros",
        "name": "ИнтернетОпрос",
        "url": "https://internetopros.ru/private",
        "domain": "internetopros.ru"
    },
    {
        "id": "anketolog",
        "name": "Анкетолог",
        "url": "https://panel.anketolog.ru/survey/invite/invitelist",
        "domain": "anketolog.ru"
    },
    {
        "id": "expertnoemnenie",
        "name": "Экспертное Мнение",
        "url": "https://panel.expertnoemnenie.ru/surveys",
        "domain": "expertnoemnenie.ru"
    },
    {
        "id": "profiresearch",
        "name": "ProfiResearch",
        "url": "https://profiresearch.net/user/",
        "domain": "profiresearch.net"
    },
    {
        "id": "moemnenie",
        "name": "МоёМнение",
        "url": "https://www.moemnenie.ru/profile",
        "domain": "moemnenie.ru"
    },
    {
        "id": "youthink",
        "name": "YouThink",
        "url": "https://youthink.io/tasks",
        "domain": "youthink.io"
    }
]


def get_platform_cabinet_url(current_url: str) -> str:
    """Определяет URL личного кабинета платформы по текущему URL опроса."""
    url_low = current_url.lower()
    if "127.0.0.1" in url_low or "localhost" in url_low:
        return "http://127.0.0.1:8888/"
    elif "survstat" in url_low or "internetopros" in url_low:
        return "https://internetopros.ru/private"
    elif "anketka" in url_low or "enjoysurvey" in url_low or "enjoypanel" in url_low:
        return "https://www.anketka.ru/profile"
    elif "anketolog" in url_low:
        return "https://panel.anketolog.ru/survey/invite/invitelist"
    elif "expertnoemnenie" in url_low or "survey-studio" in url_low or "surveystudio" in url_low:
        return "https://panel.expertnoemnenie.ru/surveys"
    elif "profiresearch" in url_low:
        return "https://profiresearch.net/user/"
    elif "moemnenie" in url_low:
        return "https://www.moemnenie.ru/profile"
    elif "youthink" in url_low:
        return "https://youthink.io/tasks"
    else:
        p = urlparse(current_url)
        return f"{p.scheme}://{p.netloc}/"


class PanelManager:
    """
    Менеджер работы с личными кабинетами опросников и дашбордами:
    - Поиск и клик по доступным опросам
    - Обработка экранов завершения (пост-опрос)
    - Навигация между панелями в режиме мульти-фарминга
    """

    @staticmethod
    def is_cabinet_page(url: str) -> bool:
        """Проверяет, указывает ли URL на страницу личного кабинета."""
        u = url.lower()
        if "surveystudio" in u or "survey-studio" in u:
            return False

        # Точные токены путей личных кабинетов
        cabinet_tokens = [
            "survey/invite", "invitelist", "archivelist", "/profile", "/private", "/cabinet",
            "/dashboard", "/account", "/tasks"
        ]
        if any(c in u for c in cabinet_tokens):
            return True

        # /surveys и /user должны проверяться по границам пути, чтобы не матчить surveystudio и т.д.
        for seg in ["/surveys", "/user"]:
            if seg in u:
                idx = u.find(seg)
                after = u[idx + len(seg):]
                if not after or after.startswith("/") or after.startswith("?") or after.startswith("#"):
                    return True

        return False

    @staticmethod
    def is_active_survey_url(url: str) -> bool:
        """Проверяет, является ли URL активным опросным маршрутом."""
        u = url.lower()
        if PanelManager.is_cabinet_page(u):
            return False
        return (
            any(s in u for s in [
                "/poll/", "redirect", "mriweb", "cawi", "sawtooth", "cloudsurvey",
                "surveystudio", "/ri/", "/proj/", "survstat", "oprosso", "pthwy"
            ]) or
            ("/survey/" in u and "panel.anketolog.ru" not in u) or
            "127.0.0.1" in u or "localhost" in u
        )

    @staticmethod
    def is_dashboard(url: str, home_dashboard_url: str = None) -> bool:
        """Проверяет, находится ли браузер на экране личного кабинета или дашборда."""
        u = url.lower()
        if PanelManager.is_active_survey_url(u):
            return False

        if PanelManager.is_cabinet_page(u):
            return True

        if any(p in u for p in [
            "anketka", "internetopros", "profiresearch", "anketolog",
            "expertnoemnenie", "moemnenie", "youthink", "rublklub", "voprosnik"
        ]):
            return True

        if (home_dashboard_url and
                urlparse(url).netloc.lower() == urlparse(home_dashboard_url).netloc.lower() and
                "127.0.0.1" not in u and "localhost" not in u):
            return True

        return False

    @staticmethod
    async def try_click_panel_survey(page: Page, update_url_callback=None, apply_stealth_fn=None) -> bool:
        """Универсальный поиск и запуск доступного опроса на панели."""
        try:
            res = await page.evaluate(JS_SCAN_PANEL_SURVEYS)
            if res and res.get("found"):
                title = res.get("text", "")
                href = res.get("href", "")
                print(f"\n[🚀] [ПАНЕЛЬ] Обнаружен доступный опрос: «{title}»")
                if href:
                    print(f"[🔗] Ссылка: {href}")

                await page.wait_for_timeout(2500)

                # Проверка на открытие попапа в новой вкладке
                context = page.context
                if len(context.pages) > 1:
                    new_p = context.pages[-1]
                    for p in context.pages[:-1]:
                        if not p.is_closed():
                            try:
                                await p.close()
                            except Exception:
                                pass
                    page = new_p
                    if apply_stealth_fn:
                        await apply_stealth_fn(page)
                    state.active_page = page

                try:
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                except Exception:
                    pass

                new_url = page.url
                if update_url_callback:
                    update_url_callback(new_url)
                print(f"[+] Переход выполнен, текущий URL: {new_url}")
                return True
        except Exception as e:
            print(f"[!] Ошибка поиска опроса на панели: {e}")

        return False

    @staticmethod
    async def handle_universal_post_survey(page: Page, on_url_change=None, apply_stealth_fn=None) -> str:
        """
        Универсальная обработка экрана завершения опроса:
        1. Проверяет карточки опросов прямо на текущем экране (хабы Survstat / Pythia).
        2. Ищет кнопки перехода («Подобрать опрос», «Другие опросы», «В кабинет»).
        3. Если кнопок нет — переходит в личный кабинет платформы.
        4. Сканирует страницу кабинета на новые опросы.
        """
        print("\n" + "=" * 60)
        print("🔍 [ПОСТ-ОПРОС] Анализ экрана завершения опроса...")
        print("=" * 60)

        # 1. ПРОВЕРКА КАРТОЧЕК ОПРОСОВ НА ТЕКУЩЕМ ЭКРАНЕ
        try:
            cb = page.locator("#selectSurveyConfirmation, input[type='checkbox']").first
            if await cb.count() > 0:
                try:
                    if not await cb.is_checked():
                        await cb.check(force=True)
                        await human_sleep(0.3, 0.6)
                except Exception:
                    pass

            hub_res = await page.evaluate(JS_HANDLE_SURVEY_HUB)
            if hub_res and hub_res.get("found"):
                print(f"[🎯] [ХАБ] Запущен опрос из списка: «{hub_res.get('text', '')}»")
                await human_sleep(2.0, 3.5)
                return 'NEW_SURVEY_STARTED'
        except Exception as e:
            print(f"[!] Ошибка проверки хаба: {e}")

        # 2. ПРОВЕРКА КНОПОК ПЕРЕХОДА
        try:
            finish_action = await page.evaluate(JS_CHECK_AND_HANDLE_FINISH_ACTIONS)
            if finish_action and finish_action.get("action") != "none":
                act = finish_action.get("action")
                btn_txt = finish_action.get("text", "") or finish_action.get("href", "")
                print(f"[i] [ПОСТ-ОПРОС] Нажата кнопка перехода: «{btn_txt}» ({act})")
                await human_sleep(2.5, 4.0)

                try:
                    cb = page.locator("#selectSurveyConfirmation, input[type='checkbox']").first
                    if await cb.count() > 0 and not await cb.is_checked():
                        await cb.check(force=True)
                        await human_sleep(0.3, 0.6)

                    hub_res = await page.evaluate(JS_HANDLE_SURVEY_HUB)
                    if hub_res and hub_res.get("found"):
                        print(f"[🎯] [ХАБ] Запущен новый опрос: «{hub_res.get('text', '')}»")
                        await human_sleep(2.0, 3.5)
                        return 'NEW_SURVEY_STARTED'
                except Exception:
                    pass
        except Exception as e:
            print(f"[!] Ошибка обработки кнопок завершения: {e}")

        # 3. ЕСЛИ ОПРОС НЕ НАЙДЕН — ПЕРЕХОДИМ В КАБИНЕТ
        if "127.0.0.1" in page.url.lower() or "localhost" in page.url.lower():
            print("[✓] [ТЕСТ] Локальный тестовый опрос успешно завершен.")
            return 'NO_SURVEYS_ON_SITE'

        target_cabinet = get_platform_cabinet_url(page.url)
        print(f"[🏠] [КАБИНЕТ] Переходим в личный кабинет платформы: {target_cabinet}")
        try:
            await page.goto(target_cabinet, wait_until="domcontentloaded", timeout=20000)
            await human_sleep(2.5, 4.5)
            if on_url_change:
                on_url_change(page.url)
        except Exception as e:
            print(f"[!] Ошибка перехода в кабинет {target_cabinet}: {e}")

        # 4. СКАНИРУЕМ СТРАНИЦУ КАБИНЕТА
        print("[🔎] [КАБИНЕТ] Сканируем страницу кабинета на наличие доступных опросов...")
        if await PanelManager.try_click_panel_survey(page, on_url_change, apply_stealth_fn):
            print("[🚀] [КАБИНЕТ] Обнаружен и запущен доступный опрос!")
            await human_sleep(2.0, 3.5)
            return 'NEW_SURVEY_STARTED'

        await human_sleep(2.0, 3.0)
        if await PanelManager.try_click_panel_survey(page, on_url_change, apply_stealth_fn):
            print("[🚀] [КАБИНЕТ] Доступный опрос запущен со второй попытки!")
            await human_sleep(2.0, 3.5)
            return 'NEW_SURVEY_STARTED'

        print(f"[i] [КАБИНЕТ] На платформе «{target_cabinet}» активных опросов прямо сейчас нет.")
        return 'NO_SURVEYS_ON_SITE'

    @staticmethod
    async def handle_anketka_post_finish(page: Page, update_url_callback=None, apply_stealth_fn=None) -> bool:
        """Специфичный пост-финиш для Анкетки."""
        print("\n[⏳] АВТОФАРМИНГ (Анкетка): Ищем опросы на текущей странице...")
        for _ in range(2):
            if await PanelManager.try_click_panel_survey(page, update_url_callback, apply_stealth_fn):
                return True
            await asyncio.sleep(1.0)

        print("[i] На текущей странице опросов нет. Переходим в /profile...")
        try:
            await page.goto("https://www.anketka.ru/profile", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2.0)
            if await PanelManager.try_click_panel_survey(page, update_url_callback, apply_stealth_fn):
                return True
        except Exception as e:
            print(f"[!] Ошибка при переходе в /profile: {e}")

        print("[i] Ожидание новых опросов на странице профиля...")
        return False
