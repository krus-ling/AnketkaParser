import os
import asyncio
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, Error as PlaywrightError

from core.brain import SurveyBrain
from core.bot_state import state
from core.logger import session_logger
from core import config

from engines.anketka import AnketkaEngine
from engines.cloudsurvey import CloudSurveyEngine
from engines.chat_survey import ChatSurveyEngine
from engines.profiresearch import ProfiResearchEngine
from engines.anketolog import AnketologEngine
from engines.surveystudio import SurveyStudioEngine
from engines.sawtooth import SawtoothEngine
from engines.base import human_sleep

from engines.js_snippets import (
    JS_ROUTER_CHECK_START_PAGE,
    JS_ROUTER_CLICK_START_BTN,
    JS_ROUTER_CHECK_FINISHED,
    JS_SCAN_PANEL_SURVEYS,
    JS_SCAN_ANKETKA_SURVEYS,
    JS_HANDLE_SURVEY_HUB,
    JS_CHECK_AND_HANDLE_FINISH_ACTIONS,
    JS_SOLVE_PRESURVEY_DEMOGRAPHICS
)
from engines.panel_manager import PANEL_SITES, get_platform_cabinet_url, PanelManager
from engines.demographics import DemographicsManager



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

    async def save_error_snapshot(self, page: Page, reason: str = "ERROR"):
        """Сохранение диагностического снимка ошибки через активный или базовый движок."""
        try:
            target_engine = getattr(state, "active_engine", None) or self.cloud_engine
            if target_engine and hasattr(target_engine, "save_error_snapshot"):
                await target_engine.save_error_snapshot(page, reason)
            elif self.cloud_engine and hasattr(self.cloud_engine, "save_error_snapshot"):
                await self.cloud_engine.save_error_snapshot(page, reason)
        except Exception as e:
            print(f"[!] Не удалось сохранить снимок ошибки: {e}")

    async def detect_and_dispatch(self, page: Page, body_text: str) -> str:
        url = page.url.lower()
        body_lower = body_text.lower()

        # === 1. АБСОЛЮТНЫЙ ПЕРЕХВАТ ФИНАЛА (Python-уровень) ===
        if "survey-finish" in url or "выберите награду" in body_lower or "заберите свою первую награду" in body_lower:
            print("\n[🎁] Обнаружен финальный экран Анкетки! Забираем «Деньги»...")
            await self.anketka_engine.handle_anketka_reward(page)
            return 'SUCCESS_END'

        # Перехват по системным URL
        if any(w in url for w in ["survey-finished", "state=fail", "screenout", "disqualified"]):
            return 'SCREENOUT'
        if any(w in url for w in ["completed", "success", "state=success"]):
            return 'SUCCESS_END'

        # Перехват по тексту страницы
        if "увы, нужное число ответов" in body_lower or "опрос завершен неудачно" in body_lower or "вы не подошли" in body_lower or "к сожалению, вы" in body_lower:
            return 'SCREENOUT'
        if "опрос успешно завершен" in body_lower or "вознаграждение зачислено" in body_lower or "вы изменили мир" in body_lower:
            return 'SUCCESS_END'

        # === 2. Обработка стартовых страниц ===
        if await page.evaluate(JS_ROUTER_CHECK_START_PAGE):
            print("\n[i] Обнаружена стартовая страница с инструкцией. Нажимаем «Продолжить»...")
            await self._fill_presurvey_demographics(page)

            await page.evaluate("""() => {
                document.querySelectorAll('[target="_blank"]').forEach(el => el.removeAttribute('target'));
                window.open = function (url) {
                    window.location.href = url;
                    return window;
                };

                let checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                for (let cb of checkboxes) {
                    if (!cb.checked) {
                        let container = cb.closest('label, .checkbox-item, div') || cb.parentElement;
                        let txt = (container.innerText || '').toLowerCase();
                        let pTxt = (container.parentElement ? container.parentElement.innerText : '').toLowerCase();
                        if (txt.includes('согласен') || txt.includes('ознакомлен') || pTxt.includes('согласен') || pTxt.includes('ознакомлен')) {
                            let label = cb.closest('label') || document.querySelector(`label[for="${cb.id}"]`) || container;
                            label.scrollIntoView({behavior: 'smooth', block: 'center'});
                            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                                label.dispatchEvent(new MouseEvent(evt, {
                                    bubbles: true,
                                    cancelable: true,
                                    view: window
                                }));
                            });
                            if (label.click) label.click();
                            try {
                                let tracker = cb._valueTracker;
                                if (tracker) tracker.setValue('');
                                Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "checked").set.call(cb, true);
                            } catch (e) {
                            }
                            cb.checked = true;
                            cb.dispatchEvent(new Event('input', {bubbles: true}));
                            cb.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    }
                }
            }""")
            await human_sleep(0.5, 1.0)

            btn_clicked = False
            selectors = [
                "button.startButton__d0j10", "a[data-testid='start-button']",
                "button:has-text('Продолжить')", "button:has-text('Начать')",
                "a:has-text('Продолжить')", "a:has-text('Начать')",
                "button", "a.btn", "a[class*='button']", ".shared-btn"
            ]

            for sel in selectors:
                try:
                    elements = await page.query_selector_all(sel)
                    for btn in elements:
                        if await btn.is_visible():
                            is_invalid = await btn.evaluate(
                                "el => el.disabled || el.getAttribute('tabindex') === '-1' || el.closest('[class*=\"disabled\"]') !== null || el.closest('[class*=\"Disable\"]') !== null")
                            if is_invalid:
                                continue

                            txt = (await btn.inner_text()).strip().lower()
                            if txt in ['продолжить', 'начать', 'начать опрос', 'подобрать опрос', 'согласен',
                                       'к опросу'] or "start" in sel.lower():
                                await btn.scroll_into_view_if_needed()
                                await human_sleep(0.3, 0.6)
                                await btn.click(force=True)
                                btn_clicked = True
                                break
                except Exception:
                    continue
                if btn_clicked:
                    break

            if not btn_clicked:
                await page.evaluate(JS_ROUTER_CLICK_START_BTN)

            await human_sleep(2.0, 3.0)
            return 'SUCCESS'

        finish_status = await page.evaluate(JS_ROUTER_CHECK_FINISHED)
        if finish_status:
            await self.anketka_engine.handle_completion_and_feedback(page, body_text)
            await self.anketka_engine.handle_anketka_reward(page)
            return finish_status

        if await self.anketka_engine.handle_modal_popup(page):
            return 'SUCCESS'

        # === 2.5. ОБРАБОТКА ХАБА / ЭКРАНА ВЫБОРА ОПРОСОВ (Survstat, Router-Client и др.) ===
        is_hub = (
            "router-client.survstat" in url or "survstat" in url or
            "выберите новый опрос" in body_lower or "выберите опрос" in body_lower or
            (await page.query_selector("[class*='SurveyLinksPage'], [class*='SurveyLink_surveyLink']")) is not None
        )
        if is_hub:
            hub_result = await page.evaluate(JS_HANDLE_SURVEY_HUB)
            if hub_result and hub_result.get("found"):
                selected_title = hub_result.get("text", "")
                print(f"\n[🎯] [ХАБ ОПРОСОВ] Выбран доступный опрос: «{selected_title}»")
                await human_sleep(2.0, 4.0)
                try:
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                except Exception:
                    pass
                return 'SUCCESS'
            elif hub_result and hub_result.get("action") == "back_to_cabinet":
                print("[i] [ХАБ ОПРОСОВ] Доступных опросов в хабе нет. Возвращаемся в личный кабинет...")
                await human_sleep(2.0, 3.5)
                return 'SUCCESS'

        # === 3. Маршрутизация по платформам и движкам ===
        is_chat = "chat" in url or "bot" in url or (
            await page.query_selector("div.chat-container, div[class*='Chat']")) is not None
        is_profi = "profiresearch" in url
        is_surveystudio = "survey-studio" in url or "surveystudio" in url
        is_sawtooth = "sawtooth" in url or "survey.dataction.biz" in url or "ciwweb.pl" in url
        is_anketka = "anketka" in url or "enjoysurvey" in url
        is_anketolog = "anketolog" in url or (await page.query_selector("body.survey-fill")) is not None

        if is_chat:
            state.active_engine = self.chat_engine
            handled = await self.chat_engine.process_step(page, body_text.lower())
        elif is_surveystudio:
            state.active_engine = self.surveystudio_engine
            handled = await self.surveystudio_engine.process_step(page, body_text.lower())
        elif is_anketolog:
            state.active_engine = self.anketolog_engine
            handled = await self.anketolog_engine.process_step(page, body_text.lower())
        elif is_sawtooth:
            state.active_engine = self.sawtooth_engine
            handled = await self.sawtooth_engine.process_step(page, body_text.lower())
        elif is_profi:
            state.active_engine = self.profi_engine
            handled = await self.profi_engine.process_step(page, body_text.lower())
        elif is_anketka:
            state.active_engine = self.anketka_engine
            handled = await self.anketka_engine.process_step(page, body_text.lower())
        else:
            state.active_engine = self.cloud_engine
            handled = await self.cloud_engine.process_step(page, body_text.lower())

        return 'SUCCESS' if handled else 'UNHANDLED'

    async def _check_network(self, context):
        """Проверка IP-адреса и геолокации браузера при старте."""
        if not getattr(config, "CHECK_BROWSER_IP", True):
            return

        try:
            temp_page = await context.new_page()
            response = await temp_page.goto("http://ip-api.com/json", timeout=10000)
            if response and response.status == 200:
                data = await response.json()
                ip = data.get("query", "Неизвестно")
                country = data.get("country", "")
                country_code = data.get("countryCode", "")
                city = data.get("city", "")

                print(f"\n[🌐 СЕТЬ] Внешний IP браузера: {ip} ({country_code} - {country}, {city})")
                if country_code and country_code.upper() != "RU":
                    print("⚠️ " * 30)
                    print(f"[⚠️ ВНИМАНИЕ СЕТЬ] Браузер подключен из страны «{country}» (не РФ)!")
                    print("👉 Российские опросники (Анкетка, Анкетолог и др.) часто блокируют зарубежные IP.")
                    print("👉 Рекомендация: отключите System Proxy/TUN в вашем VPN-клиенте (оставив VPN только")
                    print("   для Gemini в GEMINI_PROXY), либо настройте российский прокси в BROWSER_PROXY.")
                    print("⚠️ " * 30 + "\n")
                    try:
                        from core.telegram_notifier import notifier
                        notifier.notify_ip_warning(ip, f"{country} ({country_code})")
                    except Exception:
                        pass
                else:
                    print("[✓ СЕТЬ] Геолокация РФ подтверждена. Риск блокировок опросниками минимален.\n")
            await temp_page.close()
        except Exception:
            pass

    async def _apply_stealth(self, page: Page):
        """Применение комплексной защиты от обнаружения автоматизации."""
        try:
            from playwright_stealth import stealth_async
            await stealth_async(page)
        except Exception:
            pass

        try:
            await page.add_init_script("""() => {
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.navigator.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
            }""")
        except Exception:
            pass

    async def run(self, start_url: str, on_url_change=None, auto_farm: bool = False, multi_site: bool = False):
        session_logger.start()

        def setup_page_listeners(target_page: Page):
            if on_url_change:
                target_page.on(
                    "framenavigated",
                    lambda frame, p=target_page: on_url_change(p.url) if frame == p.main_frame else None
                )
            def on_console(msg):
                try:
                    state.browser_logs.append(f"[{msg.type.upper()}] {msg.text}")
                    if len(state.browser_logs) > 50:
                        state.browser_logs.pop(0)
                except Exception:
                    pass
            def on_page_error(err):
                try:
                    state.browser_logs.append(f"[PAGE_ERROR] {str(err)}")
                    if len(state.browser_logs) > 50:
                        state.browser_logs.pop(0)
                except Exception:
                    pass
            target_page.on("console", on_console)
            target_page.on("pageerror", on_page_error)

        hub_file = os.path.abspath(os.path.join(config.BASE_DIR, "data", "hub.html"))
        if not os.path.exists(hub_file):
            hub_file = os.path.abspath(os.path.join(os.getcwd(), "data", "hub.html"))
        hub_url = f"file:///{hub_file.replace(os.sep, '/')}"

        is_multi = multi_site or "hub.html" in start_url.lower() or "hub://" in start_url.lower()
        if is_multi:
            start_url = hub_url
            auto_farm = True

        current_site_idx = 0

        async with async_playwright() as p:
            profile_dir = os.path.join(os.getcwd(), "bot_profile")
            os.makedirs(profile_dir, exist_ok=True)

            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-default-browser-check"
            ]
            if getattr(config, "BROWSER_DIRECT", False):
                launch_args.append("--no-proxy-server")

            proxy_settings = None
            if getattr(config, "BROWSER_PROXY", None):
                proxy_settings = {"server": config.BROWSER_PROXY}

            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=config.BROWSER_HEADLESS,
                viewport={"width": config.BROWSER_WIDTH, "height": config.BROWSER_HEIGHT},
                args=launch_args,
                proxy=proxy_settings
            )
            await self._check_network(context)
            page = context.pages[0] if context.pages else await context.new_page()
            await self._apply_stealth(page)

            state.active_page = page
            state.active_engine = self.cloud_engine
            self.last_tracked_url = ""
            self.home_dashboard_url = start_url
            setup_page_listeners(page)

            print(f"[+] Открываем ссылку: {start_url}")
            try:
                await page.goto(start_url, wait_until="load", timeout=60000)
                await human_sleep(2.0, 3.0)

                stuck_counter = 0
                last_body_hash = ""
                body_text = ""

                while True:
                    if len(context.pages) > 1:
                        new_page = context.pages[-1]
                        for prev_p in context.pages[:-1]:
                            if not prev_p.is_closed():
                                await prev_p.close()
                        page = new_page
                        await self._apply_stealth(page)
                        state.active_page = page
                        setup_page_listeners(page)
                        print(f"\n[🔗] Опрос открылся в новой вкладке. Переключаемся...")
                        await page.bring_to_front()
                        await human_sleep(1.0, 2.0)
                        stuck_counter = 0
                        last_body_hash = ""

                    if page.is_closed():
                        print("\n[!] Окно браузера закрыто пользователем. Завершение работы.")
                        break

                    # === ПРОВЕРКА НА ПАУЗУ ИЗ GUI ===
                    if state.is_paused:
                        print("\n[⏸] БОТ НА ПАУЗЕ: Все процессы, сканирование и таймеры заморожены.")
                        print("[⏸] Нажмите кнопку «▶ Возобновить» в GUI, чтобы продолжить.")
                        try:
                            if "hub.html" in page.url.lower():
                                await page.evaluate("() => { if (typeof toggleTimer === 'function' && !isPaused) toggleTimer(); }")
                        except Exception:
                            pass

                        while state.is_paused:
                            if page.is_closed():
                                break
                            await asyncio.sleep(0.5)

                        print("[▶] СНЯТО С ПАУЗЫ: Возобновляем работу бота...\n")
                        try:
                            if "hub.html" in page.url.lower():
                                await page.evaluate("() => { if (typeof toggleTimer === 'function' && isPaused) toggleTimer(); }")
                        except Exception:
                            pass

                    current_url = page.url
                    if current_url != self.last_tracked_url:
                        self.last_tracked_url = current_url
                        if on_url_change:
                            on_url_change(current_url)

                    # === 0.0. ПРОВЕРКА НА СТРАНИЦУ ЦЕНТРА ОПРОСОВ (hub.html) ===
                    if page.url.startswith("file://") and "hub.html" in page.url.lower():
                        self._dash_poll_count = 0
                        await asyncio.sleep(1.0)
                        continue

                    # Получаем текстовое содержимое страницы безопасно
                    try:
                        body_text = await page.inner_text("body")
                    except Exception:
                        body_text = ""

                    # === 0.05. ПРОВЕРКА НА БРАУЗЕРНУЮ СЕТЕВУЮ ОШИБКУ (DEAD LINK / TIMEOUT / ERR_CONNECTION) ===
                    is_net_error = any(e in body_text.lower() for e in [
                        "не удается получить доступ к сайту",
                        "превышено время ожидания ответа",
                        "err_connection_timed_out",
                        "err_connection_refused",
                        "err_name_not_resolved",
                        "dns_probe_finished"
                    ])
                    if is_net_error:
                        print(f"\n[⚠️] Опрос недоступен (сетевая ошибка / timeout): {current_url}")
                        print("[🔄] Возвращаемся в личный кабинет платформы...")
                        cab_url = get_platform_cabinet_url(self.home_dashboard_url or current_url)
                        try:
                            await page.goto(cab_url, wait_until="domcontentloaded", timeout=15000)
                            await human_sleep(2.0, 3.5)
                        except Exception:
                            pass
                        continue

                    # === 0. ПРОВЕРКА НА СТРАНИЦУ АВТОРИЗАЦИИ / ВХОДА ===
                    is_login_page = any(kw in current_url.lower() for kw in ["/login", "/auth", "/signin", "auth.anketka", "passport."])
                    if not is_login_page:
                        try:
                            has_pw = await page.evaluate("() => !!document.querySelector('input[type=\"password\"]')")
                            is_login_page = has_pw and any(w in body_text.lower() for w in ["вход", "войти", "пароль", "авторизац"])
                        except Exception:
                            has_pw = False

                    if is_login_page:
                        print("\n" + "=" * 60)
                        print("[🔑] ОБНАРУЖЕНА СТРАНИЦА ВХОДА В АККАУНТ!")
                        print(f"👉 URL: {current_url}")
                        print("👉 Пожалуйста, войдите в свой аккаунт в окне браузера.")
                        print("👉 После входа бот автоматически сохранит сессию и продолжит работу.")
                        print("=" * 60 + "\n")
                        try:
                            from core.telegram_notifier import notifier
                            notifier.notify_manual_action(f"Требуется авторизация в аккаунте: {current_url}")
                        except Exception:
                            pass

                        while not page.is_closed():
                            await asyncio.sleep(2.0)
                            if page.url != current_url:
                                new_u = page.url.lower()
                                if not any(kw in new_u for kw in ["/login", "/auth", "/signin"]):
                                    print("[✓] Авторизация успешна! Продолжаем работу...")
                                    stuck_counter = 0
                                    last_body_hash = ""
                                    break
                        continue

                    # === 0.1. УНИВЕРСАЛЬНАЯ ПРОВЕРКА НА ЛИЧНЫЙ КАБИНЕТ / ПАНЕЛЬ ОПРОСОВ (ДАШБОРД) ===
                    is_dashboard = PanelManager.is_dashboard(current_url, getattr(self, "home_dashboard_url", None))

                    if is_dashboard:
                        # Если бот только что зашел на сайт, даем время на полную подгрузку страницы, API и скрытие спиннеров
                        if getattr(self, "_dash_poll_count", 0) == 0:
                            try:
                                await page.wait_for_load_state('domcontentloaded', timeout=8000)
                                await human_sleep(2.0, 3.5)
                            except Exception:
                                pass

                        survey_clicked = await self._try_click_panel_survey(page, on_url_change)

                        if survey_clicked:
                            print("[🚀] Опрос успешно запущен из личного кабинета!")
                            stuck_counter = 0
                            last_body_hash = ""
                            self._dash_poll_count = 0
                            self.brain.stats = {"total_answered": 0, "from_memory": 0, "from_rules": 0, "from_llm": 0}
                            self.brain.last_action = None
                            await human_sleep(2.0, 4.0)
                            continue
                        else:
                            stuck_counter = 0
                            dash_poll = getattr(self, "_dash_poll_count", 0) + 1
                            self._dash_poll_count = dash_poll

                            cur_domain = urlparse(current_url).netloc or "панель"
                            max_polls = 4 if is_multi else 10

                            is_empty_text = any(phrase in body_text.lower() for phrase in [
                                "опросы закончились", "нет доступных опросов", "пока нет опросов",
                                "в данный момент нет опросов", "на данный момент опросов нет",
                                "похоже, пока опросы закончились", "нет активных опросов"
                            ])
                            if is_empty_text and is_multi:
                                print(f"[i] [ЛИЧНЫЙ КАБИНЕТ] На платформе {cur_domain} обнаружено сообщение об отсутствии доступных опросов.")
                                dash_poll = max_polls

                            print(f"[⏳] ЛИЧНЫЙ КАБИНЕТ ({cur_domain}): Доступных опросов пока нет. Сканирую страницу... (проверка #{dash_poll}/{max_polls})")

                            if dash_poll < max_polls:
                                if dash_poll == 1:
                                    # Даем время SPA-компонентам отрисовать карточки опросов
                                    await human_sleep(3.0, 4.5)
                                    continue
                                elif dash_poll == 2:
                                    # Разово обновляем страницу для получения свежих опросов
                                    print(f"[🔄] Обновляем страницу {cur_domain} для повторной проверки...")
                                    try:
                                        await page.reload()
                                        await page.wait_for_load_state('domcontentloaded', timeout=10000)
                                    except Exception:
                                        pass
                                    await human_sleep(3.0, 4.5)
                                    continue
                                elif dash_poll == 3:
                                    # Дополнительное терпеливое ожидание догрузки данных
                                    await human_sleep(3.0, 4.0)
                                    continue

                            # Если опросов нет и после всех терпеливых проверок (dash_poll >= 4):
                            if is_multi:
                                matched_idx = next(
                                    (i for i, s in enumerate(PANEL_SITES) if s["domain"] in cur_domain.lower() or s["id"] in cur_domain.lower()),
                                    current_site_idx
                                )
                                curr_site = PANEL_SITES[matched_idx]
                                current_site_idx = (matched_idx + 1) % len(PANEL_SITES)
                                next_site = PANEL_SITES[current_site_idx]

                                print("\n" + "═" * 65)
                                print(f"[⏳] [МУЛЬТИ-РОТАЦИЯ] На платформе «{curr_site['name']}» ({cur_domain}) доступных опросов нет.")
                                print(f"[🚀] Возвращаемся в Центр Опросов и переходим к следующему сайту: «{next_site['name']}»...")
                                print("═" * 65 + "\n")

                                self._dash_poll_count = 0
                                target_hub_url = f"{hub_url}?next={next_site['id']}"
                                try:
                                    await page.goto(target_hub_url, wait_until="domcontentloaded", timeout=15000)
                                except Exception:
                                    pass
                                stuck_counter = 0
                                last_body_hash = ""
                                await human_sleep(1.0, 2.0)
                                continue

                            elif auto_farm:
                                if dash_poll % 10 == 0:
                                    print(f"[🔄] [АВТОФАРМИНГ] Периодическое обновление страницы {cur_domain}...")
                                    try:
                                        await page.reload()
                                        await page.wait_for_load_state('domcontentloaded', timeout=10000)
                                    except Exception:
                                        pass
                                    await human_sleep(2.0, 4.0)
                                else:
                                    await asyncio.sleep(2.0)
                                continue
                            else:
                                print(f"\n[i] На платформе «{cur_domain}» доступных опросов нет. Завершение работы.")
                                self._dash_poll_count = 0
                                if state.is_debug and not page.is_closed():
                                    print("[!] ОТЛАДОЧНЫЙ РЕЖИМ: Браузер оставлен открытым. Нажмите '✅ Подтвердить шаг' в GUI для выхода.")
                                    await state.wait_debug_confirm()
                                break
                    else:
                        self._dash_poll_count = 0

                    # === 0.2. ПРОВЕРКА НА ХАБ ВЫБОРА ОПРОСОВ (ROUTER-CLIENT.SURVSTAT И ДР.) ===
                    is_hub = (
                        "router-client.survstat" in current_url.lower() or
                        (await page.query_selector("[class*='SurveyLinksPage'], [class*='SurveyLink_surveyLink']")) is not None
                    )
                    if is_hub:
                        hub_res = await page.evaluate(JS_HANDLE_SURVEY_HUB)
                        if hub_res and hub_res.get("found"):
                            print(f"\n[🎯] [ХАБ ОПРОСОВ] Выбран доступный опрос: «{hub_res.get('text', '')}»")
                            stuck_counter = 0
                            last_body_hash = ""
                            await human_sleep(2.5, 4.0)
                            try:
                                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                            except Exception:
                                pass
                            continue
                        elif hub_res and hub_res.get("action") == "back_to_cabinet":
                            print("[i] [ХАБ ОПРОСОВ] Опросов в хабе нет. Возвращаемся в личный кабинет...")
                            stuck_counter = 0
                            last_body_hash = ""
                            await human_sleep(2.0, 3.5)
                            continue

                    # === 0.3. ПРОВЕРКА НА ПРЕ-ОПРОСНЫЙ ДЕМОГРАФИЧЕСКИЙ ЭКРАН (PreSurveyPage) ===
                    is_presurvey = await DemographicsManager.is_presurvey_screen(page)
                    if is_presurvey:
                        print("\n[👶] [ПРЕ-ОПРОС] Заполняем демографические поля (Пол, Дата рождения)...")
                        profile_data = getattr(self.brain, "profile", {})
                        actions = await DemographicsManager.fill_demographics(page, profile_data)
                        if actions:
                            print(f"[👶] [ДЕМОГРАФИЯ] Заполнены поля стартового экрана: {', '.join(actions)}")
                        await human_sleep(0.8, 1.5)

                        if await DemographicsManager.click_start_button(page):
                            print("[i] [ПРЕ-ОПРОС] Нажата кнопка «Начать опрос»")

                        stuck_counter = 0
                        last_body_hash = ""
                        await human_sleep(2.5, 4.5)
                        try:
                            await page.wait_for_load_state('domcontentloaded', timeout=10000)
                        except Exception:
                            pass
                        continue

                    try:
                        signature = await page.evaluate("""() => {
                            let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"])'));
                            let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;
                            return (active.innerText || '').trim().substring(0, 800);
                        }""")
                        body_text = await page.inner_text("body")
                    except Exception:
                        if page.is_closed():
                            break
                        await asyncio.sleep(1.0)
                        continue

                    current_hash = hash(signature)
                    if current_hash == last_body_hash:
                        stuck_counter += 1
                        if stuck_counter == 2:
                            print("[🔄] Страница не сменилась после действия. Выполняем прямой триггер кнопки перехода...")
                            try:
                                await page.evaluate("""() => {
                                    let btn = document.querySelector('button[name="_NNext"], .question-card__navigation button, button.button_theme_primary, input[name="_NNext"], .mrNext, button[type="submit"]');
                                    if (btn) {
                                        btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                                        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                                            btn.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                                        });
                                        if (btn.click) btn.click();
                                    }
                                }""")
                            except Exception:
                                pass
                    else:
                        stuck_counter = 0
                        last_body_hash = current_hash

                    if stuck_counter >= 3:
                        print("\n" + "⚠️ " * 30 + "\n[!] Бот не смог выполнить действие на этом шаге.")
                        if state.active_engine:
                            await state.active_engine.save_error_snapshot(page, "ROUTER_STUCK")

                        if state.is_debug:
                            print("[!] ОТЛАДОЧНЫЙ РЕЖИМ: Нажмите '✅ Подтвердить шаг' в интерфейсе, чтобы продолжить.")
                            await state.wait_debug_confirm()
                            stuck_counter = 0
                        else:
                            print("[!] Ожидание ручного действия (выберите ответ / нажмите кнопку в окне браузера)...")
                            while not page.is_closed():
                                await asyncio.sleep(1.5)
                                if page.url != self.last_tracked_url:
                                    self.last_tracked_url = page.url
                                    if on_url_change:
                                        on_url_change(page.url)

                                try:
                                    new_signature = await page.evaluate("""() => {
                                        let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"])'));
                                        let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;
                                        return (active.innerText || '').trim().substring(0, 800);
                                    }""")
                                    if hash(new_signature) != last_body_hash:
                                        print("[✓] Обнаружено ручное изменение страницы! Продолжаем работу...")
                                        stuck_counter = 0
                                        last_body_hash = hash(new_signature)
                                        break
                                except Exception:
                                    break
                        continue

                    try:
                        status = await self.detect_and_dispatch(page, body_text)
                    except Exception as step_err:
                        print(f"[!] Внутренняя ошибка парсера: {step_err}")
                        status = 'UNHANDLED'

                    if status in ['SUCCESS_END', 'SCREENOUT', 'FINISHED']:
                        print("\n" + "=" * 65 + "\n📊 ИТОГОВАЯ СТАТИСТИКА ПРОХОЖДЕНИЯ ОПРОСА:")
                        if status in ['SUCCESS_END', 'FINISHED']:
                            print("   • Результат:                          ✅ УСПЕШНО (Вознаграждение получено)")
                        elif status == 'SCREENOUT':
                            print("   • Результат:                          ❌ ОТСЕВ (Квота заполнена / Не подошли)")

                        print(f"   • Всего ответов дано:                 {self.brain.stats.get('total_answered', 0)}")
                        print(f"   • Использовано из базы памяти (Memory): {self.brain.stats.get('from_memory', 0)}")
                        print(f"   • Решено правилами/профилем (Rules):   {self.brain.stats.get('from_rules', 0)}")
                        print(f"   • Обработано нейросетью (LLM):          {self.brain.stats.get('from_llm', 0)}\n" + "=" * 65)
                        print("🎉 [ГОТОВО] Сценарий опроса завершен.")
                        await human_sleep(1.0, 2.0)

                        # Универсальный пост-опросный переход (поиск опросов на текущей странице, клик «Подобрать опрос», кабинет)
                        post_action = await self.handle_universal_post_survey(page, on_url_change)
                        if post_action == 'NEW_SURVEY_STARTED':
                            stuck_counter = 0
                            last_body_hash = ""
                            self.brain.stats = {"total_answered": 0, "from_memory": 0, "from_rules": 0, "from_llm": 0}
                            self.brain.last_action = None
                            continue

                        # Если на данном сайте опросов больше нет:
                        if is_multi:
                            curr_domain = urlparse(page.url).netloc.lower()
                            matched_idx = next(
                                (i for i, s in enumerate(PANEL_SITES) if s["domain"] in curr_domain or s["id"] in curr_domain),
                                current_site_idx
                            )
                            curr_site = PANEL_SITES[matched_idx]
                            current_site_idx = (matched_idx + 1) % len(PANEL_SITES)
                            next_site = PANEL_SITES[current_site_idx]

                            print("\n" + "═" * 65)
                            print(f"[⏳] [МУЛЬТИ-РОТАЦИЯ] На платформе «{curr_site['name']}» все доступные опросы завершены.")
                            print(f"[⏳] Ожидание 15 секунд... (Если хотите остаться на «{curr_site['name']}», выполните действие в браузере)")
                            print(f"[⏳] При бездействии бот автоматически вернется в Центр Опросов и перейдет к: «{next_site['name']}»...")
                            print("═" * 65 + "\n")

                            user_interacted = False
                            start_wait_url = page.url
                            for _ in range(15):
                                if page.is_closed():
                                    break
                                if state.is_paused:
                                    user_interacted = True
                                    break
                                if page.url != start_wait_url:
                                    print("[✓] Обнаружено действие пользователя! Остаемся на текущем сайте.")
                                    user_interacted = True
                                    break
                                await asyncio.sleep(1.0)

                            if not user_interacted and not page.is_closed():
                                print(f"\n[🚀] [МУЛЬТИ-РОТАЦИЯ] Возвращаемся в Центр Опросов. Следующий сайт: «{next_site['name']}»...")
                                target_hub_url = f"{hub_url}?next={next_site['id']}"
                                try:
                                    await page.goto(target_hub_url, wait_until="domcontentloaded", timeout=15000)
                                except Exception:
                                    pass
                                stuck_counter = 0
                                last_body_hash = ""
                                continue
                            else:
                                break
                        elif auto_farm:
                            print("\n[⏳] АВТОФАРМИНГ: Ожидание новых опросов на текущей панели...")
                            survey_started = False
                            poll_attempts = 0
                            while not page.is_closed():
                                if page.url != self.last_tracked_url:
                                    self.last_tracked_url = page.url
                                    if on_url_change:
                                        on_url_change(page.url)

                                if await self._try_click_panel_survey(page, on_url_change):
                                    survey_started = True
                                    break

                                poll_attempts += 1
                                if poll_attempts % 30 == 0:
                                    print("[i] Опросов пока нет. Обновляем страницу...")
                                    try:
                                        await page.reload()
                                    except Exception:
                                        pass
                                await asyncio.sleep(2.0)

                            if survey_started:
                                stuck_counter = 0
                                last_body_hash = ""
                                self.brain.stats = {"total_answered": 0, "from_memory": 0, "from_rules": 0, "from_llm": 0}
                                self.brain.last_action = None
                                continue
                            else:
                                break
                        else:
                            if state.is_debug and not page.is_closed():
                                print("\n" + "🔍 " * 25)
                                print("[!] ОТЛАДОЧНЫЙ РЕЖИМ: Опрос завершен/вопросы закончились, браузер ОСТАВЛЕН ОТКРЫТЫМ.")
                                print("[!] Нажмите '✅ Подтвердить шаг' в GUI для выхода, либо закройте окно браузера вручную.")
                                print("🔍 " * 25 + "\n")
                                await state.wait_debug_confirm()
                            return

                    elif status == 'UNHANDLED':
                        stuck_counter += 1
                    await human_sleep(1.5, 2.5)

            except PlaywrightError as pe:
                if "closed" in str(pe).lower():
                    print("\n[!] Окно браузера закрыто. Остановка.")
                else:
                    print(f"\n[!] Ошибка браузера: {pe}")
                    try:
                        if page and not page.is_closed():
                            await self.save_error_snapshot(page, f"BROWSER_ERROR: {str(pe)[:40]}")
                    except Exception:
                        pass
            except Exception as e:
                print(f"\n[!] Ошибка выполнения: {e}")
                try:
                    if page and not page.is_closed():
                        await self.save_error_snapshot(page, f"EXEC_ERROR: {str(e)[:40]}")
                except Exception:
                    pass
            finally:
                try:
                    if state.is_debug and context and not page.is_closed():
                        print("\n" + "🔍 " * 25)
                        print("[!] ОТЛАДОЧНЫЙ РЕЖИМ: Браузер НЕ закрывается автоматически.")
                        print("[!] Окно браузера открыто для осмотра. Закройте его вручную на крестик, когда закончите.")
                        print("🔍 " * 25 + "\n")
                        while not page.is_closed():
                            await asyncio.sleep(1.0)
                    if context:
                        await context.close()
                except Exception:
                    pass
                finally:
                    session_logger.stop()

    async def _fill_presurvey_demographics(self, page: Page) -> bool:
        """Заполнение демографических полей (Пол, Дата рождения) на пре-опросных и стартовых экранах."""
        profile_data = getattr(self.brain, "profile", {})
        actions = await DemographicsManager.fill_demographics(page, profile_data)
        if actions:
            print(f"[👶] [ДЕМОГРАФИЯ] Заполнены поля стартового экрана: {', '.join(actions)}")
            return True
        return False

    async def handle_universal_post_survey(self, page: Page, on_url_change=None) -> str:
        """Универсальная обработка экрана окончания опроса через PanelManager."""
        return await PanelManager.handle_universal_post_survey(page, on_url_change, self._apply_stealth)

    async def _try_click_panel_survey(self, page: Page, update_url_callback=None) -> bool:
        """Универсальный поиск и запуск доступного опроса через PanelManager."""
        return await PanelManager.try_click_panel_survey(page, update_url_callback, self._apply_stealth)

    _try_click_anketka_survey = _try_click_panel_survey

    async def _try_click_other_panel_survey(self, page: Page, update_url_callback=None) -> bool:
        return await PanelManager.try_click_panel_survey(page, update_url_callback, self._apply_stealth)

    async def handle_anketka_post_finish(self, page: Page, update_url_callback=None) -> bool:
        """Обработка завершения опроса на Анкетке."""
        return await PanelManager.handle_anketka_post_finish(page, update_url_callback, self._apply_stealth)
