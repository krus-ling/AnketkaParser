import asyncio
import math
import random
import os
import datetime
from playwright.async_api import Page
from core.bot_state import state
from core.dom_synchronizer import DOMSynchronizer
from core import config
from core.telegram_notifier import notifier

from engines.mixins import (
    ModalMixin,
    FeedbackRewardMixin,
    BaseQuestionMixin,
    OpenTextMixin
)

MONTH_NAMES = {
    1: ["январь", "января", "01", "1"],
    2: ["февраль", "февраля", "02", "2"],
    3: ["март", "марта", "03", "3"],
    4: ["апрель", "апреля", "04", "4"],
    5: ["май", "мая", "05", "5"],
    6: ["июнь", "июня", "06", "6"],
    7: ["июль", "июля", "07", "7"],
    8: ["август", "августа", "08", "8"],
    9: ["сентябрь", "сентября", "09", "9"],
    10: ["октябрь", "октября", "10"],
    11: ["ноябрь", "ноября", "11"],
    12: ["декабрь", "декабря", "12"]
}


async def human_sleep(min_sec: float, max_sec: float):
    """Имитация человеческой паузы перед действием."""
    await state.check_pause()
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def human_reading_delay(text: str = ""):
    """
    Интеллектуальная задержка на чтение вопроса (защита от антифрода).
    Время пропорционально объему текста: ~180-220 слов в минуту у человека.
    """
    if not getattr(config, "HUMAN_LIKE_DELAYS", True):
        await human_sleep(0.5, 1.2)
        return

    await state.check_pause()
    word_count = len(text.split()) if text else 5
    # Базовая пауза (1.2 - 2.0 сек) + ~150-220 мс на слово
    calculated = random.uniform(1.2, 2.0) + (word_count * random.uniform(0.12, 0.20))
    # Ограничиваем разумным диапазоном от 1.5 до 7.0 секунд
    delay = min(7.0, max(1.5, calculated))
    await asyncio.sleep(delay)


async def smooth_mouse_move(page: Page, target_x: float, target_y: float, steps: int = 15):
    """Имитация движения мыши по нелинейной кривой Безье с естественным джиттером."""
    try:
        # Стартовая позиция со случайным смещением
        start_x = random.randint(100, 400)
        start_y = random.randint(100, 400)
        # Контрольная точка искривления кривой Безье
        ctrl_x = (start_x + target_x) / 2 + random.uniform(-60, 60)
        ctrl_y = (start_y + target_y) / 2 + random.uniform(-40, 40)

        for i in range(1, steps + 1):
            t = i / steps
            # Квадратичная кривая Безье: B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
            bx = ((1 - t) ** 2) * start_x + 2 * (1 - t) * t * ctrl_x + (t ** 2) * target_x
            by = ((1 - t) ** 2) * start_y + 2 * (1 - t) * t * ctrl_y + (t ** 2) * target_y
            # Микро-джиттер руки человека
            jitter_x = random.uniform(-1.5, 1.5)
            jitter_y = random.uniform(-1.5, 1.5)
            await page.mouse.move(bx + jitter_x, by + jitter_y)
            await asyncio.sleep(random.uniform(0.008, 0.016))
    except Exception:
        pass


async def human_click(page: Page, element) -> bool:
    """Человекоподобный клик с плавным наведением в случайную область элемента."""
    try:
        box = await element.bounding_box()
        if not box or box.get("width", 0) == 0:
            await element.click(force=True)
            return True

        # Клик не строго в центр (что детектируется антифродом), а с небольшим случайным смещением
        offset_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
        offset_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)

        if getattr(config, "HUMAN_LIKE_DELAYS", True):
            await smooth_mouse_move(page, offset_x, offset_y)
            await asyncio.sleep(random.uniform(0.06, 0.14))

        await page.mouse.click(offset_x, offset_y)
        return True
    except Exception:
        try:
            await element.click(force=True)
            return True
        except Exception:
            return False


class BaseSurveyEngine(ModalMixin, FeedbackRewardMixin, BaseQuestionMixin, OpenTextMixin):
    """
    Базовый класс движка-парсера.
    Обеспечивает только фундаментальную механику: клики, задержки и синхронизацию.
    Вся бизнес-логика опросов унаследована через миксины.
    """
    def __init__(self, brain):
        self.brain = brain
        self.profile = brain.profile
        self.profile_personal = brain.profile.get("personal", {})
        self.last_handled_question = ""

    async def sync_memory_from_dom(self, page: Page):
        """Синхронизация фактически выбранных ответов со страницы в SQLite память."""
        try:
            await DOMSynchronizer.sync_memory(page, self.brain)
        except Exception as e:
            print(f"[!] Ошибка синхронизации DOM: {e}")

    async def click_next(self, page: Page) -> bool:
        """Базовое нажатие кнопки 'Далее'."""
        await state.wait_debug_confirm()
        await self.sync_memory_from_dom(page)

        selectors = [
            "button[name='_NNext']", ".question-card__navigation button", "button.button_theme_primary",
            "input[name='_NNext']", "[name='_NNext']", ".mrNext", "input.mrNext",
            "button:has-text('ДАЛЕЕ')", "button:has-text('Далее')",
            "button:has-text('Вперед')", "button:has-text('ВПЕРЕД')",
            "button:has-text('Продолжить')", "button:has-text('ПРОДОЛЖИТЬ')",
            "button:has-text('Следующий')", "button:has-text('Дальше')",
            "button:has-text('Начать опрос')", "button:has-text('Начать')",
            "[class*='Button_button__']", "[class*='Button_button']:not([class*='Container'])",
            "div:has-text('Начать опрос')",
            "button[data-role='next-btn']", "button[data-testid*='next']",
            ".btn-next", ".btn-primary", "button[type='submit']",
            "input[type='submit'][value*='Далее']", "input[type='submit'][value*='ДАЛЕЕ']",
            "[role='button']:has-text('ДАЛЕЕ')", "[role='button']:has-text('Далее')"
        ]

        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if not await btn.is_visible():
                        continue

                    txt = (await btn.inner_text() or await btn.get_attribute("value") or "").strip()
                    if len(txt) > 25 and not any(k in sel for k in ["[name=", ".question-card__navigation"]):
                        continue
                    if any(bad in txt.lower() for bad in ["нажмите", "пожалуйста", "чтобы", "опрос"]):
                        continue

                    await btn.scroll_into_view_if_needed()
                    await human_click(page, btn)
                    try:
                        await btn.evaluate("""el => {
                            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                                el.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                            });
                            if (el.click) el.click();
                        }""")
                    except Exception:
                        pass

                    print(f"[i] [BASE] Нажата кнопка (найдено по: {sel})")
                    return True
            except Exception:
                continue

        return False

    async def save_error_snapshot(self, page: Page, reason: str = "ERROR"):
        import json
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"error_{timestamp}"
        folder_path = os.path.join(config.BASE_DIR, "data", "error_questions", folder_name)
        os.makedirs(folder_path, exist_ok=True)

        screenshot_path = os.path.join(folder_path, "screenshot.png")
        html_path = os.path.join(folder_path, "page.html")
        elements_path = os.path.join(folder_path, "interactive_elements.json")
        log_path = os.path.join(folder_path, "debug_log.txt")

        try:
            await page.screenshot(path=screenshot_path, full_page=True)
            html_content = await page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception as e:
            print(f"[!] Ошибка сохранения скриншота/HTML: {e}")

        # Считываем актуальный заголовок и заголовок страницы
        page_title = ""
        try:
            page_title = await page.title()
        except Exception:
            pass

        live_question = "Не удалось извлечь заголовок"
        try:
            live_question = await page.evaluate("""() => {
                let headers = Array.from(document.querySelectorAll(
                    '.question__label, [role="heading"], .es__question-h1, [data-testid="header-title"], ' +
                    '.header1, .header2, .question-text, .question__title, .mrQuestionText, .question-card__text, ' +
                    '.tiptap, .ProseMirror, [data-test-id*="test__content"] p, h1, h2, h3'
                ));
                let valid = headers.map(h => (h.innerText || '').trim()).filter(t => t.length > 3 && !t.toLowerCase().includes('время опросов'));
                return valid.length > 0 ? valid.join(' | ') : "Не удалось извлечь заголовок";
            }""")
        except Exception:
            pass

        # Детальная инспекция интерактивных элементов на странице
        dom_summary = {}
        try:
            dom_summary = await page.evaluate("""() => {
                let buttons = Array.from(document.querySelectorAll('button, [role="button"], a.btn, input[type="submit"], input[type="button"], [class*="Button_button"], [data-testid*="next"], [data-testid*="start"]'))
                    .filter(el => el.getBoundingClientRect().height > 0)
                    .map(b => ({
                        tag: b.tagName.toLowerCase(),
                        id: b.id || '',
                        className: (b.className || '').toString(),
                        testid: b.getAttribute('data-testid') || '',
                        text: (b.innerText || b.value || '').trim().substring(0, 80),
                        disabled: b.disabled || b.classList.contains('disabled') || b.getAttribute('aria-disabled') === 'true'
                    }));

                let inputs = Array.from(document.querySelectorAll('input, select, textarea'))
                    .filter(el => el.offsetParent !== null || el.type === 'radio' || el.type === 'checkbox')
                    .map(inp => ({
                        tag: inp.tagName.toLowerCase(),
                        type: inp.type || '',
                        id: inp.id || '',
                        name: inp.name || '',
                        className: (inp.className || '').toString(),
                        value: (inp.value || '').substring(0, 50),
                        checked: inp.checked || false,
                        placeholder: inp.placeholder || ''
                    }));

                let options = Array.from(document.querySelectorAll(
                    '.choice__option, .answer-item, .choice-item, [data-testid*="choice.option"], [data-testid*="value"], .radio, .checkbox, [role="radio"], [role="checkbox"]'
                )).filter(o => o.getBoundingClientRect().height > 0)
                  .map((o, idx) => ({
                      idx: idx,
                      text: (o.innerText || '').trim().replace(/\\s+/g, ' ').substring(0, 100),
                      active: o.classList.contains('active') || o.classList.contains('selected') || o.classList.contains('checked') || o.querySelector('input:checked') !== null
                  }));

                let modals = Array.from(document.querySelectorAll('.modal.in, .modal.show, [role="dialog"], [aria-modal="true"]'))
                    .filter(m => m.getBoundingClientRect().height > 0)
                    .map(m => (m.innerText || '').trim().replace(/\\s+/g, ' ').substring(0, 120));

                return {
                    buttons: buttons,
                    inputs: inputs,
                    options: options,
                    modals: modals
                };
            }""")
            with open(elements_path, "w", encoding="utf-8") as f:
                json.dump(dom_summary, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[!] Ошибка сохранения interactive_elements.json: {e}")

        # Оповещение в Telegram (если включено)
        try:
            notifier.notify_manual_action(f"Сбой бота: {reason}\nЭкран: {live_question[:120]}", screenshot_path)
        except Exception:
            pass

        active_eng = getattr(state, "active_engine", None)
        eng_name = active_eng.__class__.__name__ if active_eng else self.__class__.__name__

        log_content = [
            "=== ОТЛАДОЧНЫЙ ЛОГ ===",
            f"Время: {timestamp}",
            f"Движок (Парсер): {eng_name}",
            f"URL страницы: {page.url}",
            f"Заголовок вкладки: {page_title}",
            f"Детальная причина остановки: {reason}\n",
            "--- СТАТИСТИКА БОТА ---",
            f"total_answered: {self.brain.stats.get('total_answered', 0)}",
            f"from_memory: {self.brain.stats.get('from_memory', 0)}",
            f"from_rules: {self.brain.stats.get('from_rules', 0)}",
            f"from_llm: {self.brain.stats.get('from_llm', 0)}\n",
            "--- ТЕКУЩИЙ ЭКРАН В МОМЕНТ СБОЯ ---",
            f"[?] ВОПРОС НА ЭКРАНЕ: {live_question}",
        ]

        # Сводка DOM на экране
        if dom_summary:
            log_content.append("\n--- АКТИВНЫЕ ЭЛЕМЕНТЫ НА ЭКРАНЕ ---")
            btns_info = dom_summary.get("buttons", [])
            log_content.append(f"Кнопки ({len(btns_info)}):")
            for b in btns_info[:6]:
                log_content.append(f"  • [{b.get('tag')}] «{b.get('text')}» (disabled={b.get('disabled')}, testid='{b.get('testid')}', class='{b.get('className')[:40]}')")

            opts_info = dom_summary.get("options", [])
            log_content.append(f"Варианты ответов ({len(opts_info)}):")
            for o in opts_info[:8]:
                log_content.append(f"  • [{'V' if o.get('active') else ' '}] «{o.get('text')}»")

            inps_info = dom_summary.get("inputs", [])
            log_content.append(f"Поля ввода ({len(inps_info)}):")
            for inp in inps_info[:6]:
                log_content.append(f"  • [{inp.get('type')}] name='{inp.get('name')}', val='{inp.get('value')}', ph='{inp.get('placeholder')}'")

            modals_info = dom_summary.get("modals", [])
            if modals_info:
                log_content.append(f"Модальные окна ({len(modals_info)}):")
                for m in modals_info:
                    log_content.append(f"  ⚠️ {m}")

        # История последних действий
        action_hist = getattr(self.brain, "action_history", [])
        if action_hist:
            log_content.append("\n--- ИСТОРИЯ ПОСЛЕДНИХ ДЕЙСТВИЙ БОТА (ПОСЛЕДНИЕ ДО СБОЯ) ---")
            for step_i, act in enumerate(reversed(action_hist[-5:]), 1):
                log_content.append(f"Шаг #{len(action_hist) - step_i + 1} ({act.get('type')}):")
                log_content.append(f"  [?] Вопрос: {act.get('question', '')[:100]}")
                if act.get('options'):
                    log_content.append(f"  [*] Варианты: {act.get('options')[:6]}")
                log_content.append(f"  [V] Выбор: {act.get('selected_texts') or act.get('answer')}")
                log_content.append(f"  [i] Логика: {act.get('reasoning')}\n")

        # Консольные логи браузера
        browser_logs = getattr(state, "browser_logs", [])
        if browser_logs:
            log_content.append("--- ЛОГИ КОНСОЛИ БРАУЗЕРА (CHROME CONSOLE) ---")
            for clog in browser_logs[-15:]:
                log_content.append(f"  {clog}")

        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(log_content))
        except Exception:
            pass

        print(f"\n[📸] КРИТИЧЕСКИЙ СБОЙ ЗАФИКСИРОВАН!")
        print(f" ├─ Папка: {folder_path}")
        print(f" └─ Зафиксирован текущий экран: «{live_question[:50]}...»")
