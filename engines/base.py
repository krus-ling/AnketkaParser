import asyncio
import math
import random
import re
from playwright.async_api import Page
from brain import SurveyBrain
from bot_state import state
from engines.js_snippets import JS_SYNC_MEMORY


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
    await state.check_pause()
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def smooth_mouse_move(page: Page, target_x: float, target_y: float, steps: int = 10):
    current_mouse = {"x": random.randint(100, 300), "y": random.randint(100, 300)}
    for i in range(1, steps + 1):
        t = i / steps
        intermediate_x = current_mouse["x"] + (target_x - current_mouse["x"]) * t + math.sin(t * math.pi) * 15
        intermediate_y = current_mouse["y"] + (target_y - current_mouse["y"]) * t + math.cos(t * math.pi) * 8
        await page.mouse.move(intermediate_x, intermediate_y)
        await asyncio.sleep(0.01)


class BaseSurveyEngine:
    def __init__(self, brain: SurveyBrain):
        self.brain = brain
        self.profile = brain.profile
        self.profile_personal = brain.profile.get("personal", {})
        self.last_handled_question = ""

    async def sync_memory_from_dom(self, page: Page):
        try:
            data = await page.evaluate(JS_SYNC_MEMORY)

            if not data:
                return

            for item in data:
                q_text = item['q']
                if item['type'] == 'text':
                    self.brain.memory.save_record(q_text, "open_text", None, item['val'], item['val'],
                                                  "Синхронизировано со страницей (финальный ответ)")
                elif item['type'] in ['choices', 'select']:
                    q_type = "multiselect" if len(item['indices']) > 1 else "single"
                    self.brain.memory.save_record(q_text, q_type, item['opts'], item['indices'], item['texts'],
                                                  "Синхронизировано со страницей (финальный ответ)")

        except Exception as e:
            print(f"[!] Ошибка фоновой синхронизации памяти: {e}")

    async def handle_modal_popup(self, page: Page) -> bool:
        ok_selectors = [
            "xpath=//button[normalize-space()='Ок' or normalize-space()='OK' or normalize-space()='ок']",
            "xpath=//div[normalize-space()='Ок' or normalize-space()='OK' or normalize-space()='ок']",
            "button:has-text('Ок')", "button:has-text('OK')", "div:has-text('Ок')",
            ".btn-ok", "button[class*='ok']", "div[class*='ok']"
        ]

        ok_btn = None
        for sel in ok_selectors:
            try:
                btns = await page.query_selector_all(sel)
                for b in btns:
                    if await b.is_visible():
                        txt = (await b.inner_text()).strip()
                        if txt in ["Ок", "OK", "Ok", "ок"]:
                            ok_btn = b
                            break
                if ok_btn:
                    break
            except Exception:
                continue

        if not ok_btn:
            return False

        modal_input = None
        for m_sel in [
            "xpath=//input[not(@type='hidden') and not(@type='submit') and not(@type='button') and not(@type='radio') and not(@type='checkbox')]",
            "div[class*='modal'] input", "input[type='text']", "textarea"]:
            try:
                inputs = await page.query_selector_all(m_sel)
                for inp in inputs:
                    if await inp.is_visible():
                        modal_input = inp
                        break
                if modal_input:
                    break
            except Exception:
                continue

        if not modal_input:
            return False

        modal_title = await page.evaluate("""() => {
            let okBtn = Array.from(document.querySelectorAll('button, div')).find(el => {
                let t = (el.innerText || '').trim();
                return (t === 'Ок' || t === 'OK' || t === 'ок') && el.offsetParent !== null;
            });
            if (okBtn) {
                let parent = okBtn.closest('div[class*="modal"], div[class*="dialog"], div[class*="popup"]') || okBtn.parentElement.parentElement;
                if (parent) {
                    let titles = Array.from(parent.querySelectorAll('h1, h2, h3, h4, div, p, span'))
                        .map(el => el.innerText.trim())
                        .filter(t => t.length > 3 && t !== 'Ок' && t !== 'Отмена' && t !== 'OK');
                    return titles[0] || "Уточните вариант ответа";
                }
            }
            return "Уточните вариант ответа";
        }""")

        print("\n" + "=" * 60)
        print(f"🪟 [МОДАЛЬНОЕ ОКНО]: {modal_title}")
        answer = self.brain.answer_open_text(modal_title)
        print(f"✍️  [ВВОД]: {answer}")
        print("=" * 60)

        await modal_input.scroll_into_view_if_needed()
        await modal_input.click(force=True)
        await human_sleep(0.3, 0.5)
        await modal_input.fill("")
        await page.keyboard.type(answer, delay=random.randint(40, 80))
        await human_sleep(0.5, 0.8)

        await ok_btn.scroll_into_view_if_needed()
        box = await ok_btn.bounding_box()
        if box:
            await smooth_mouse_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await ok_btn.click(force=True)
        await human_sleep(1.5, 2.5)
        return True

    async def handle_completion_and_feedback(self, page: Page, body_text: str) -> bool:
        body_lower = body_text.lower()
        if not ((
                        "вы изменили мир" in body_lower or "оцените пройденный опрос" in body_lower or "подобрать опрос" in body_lower) and (
                        "понравился" in body_lower or "баллов" in body_lower or "зачислено" in body_lower)):
            return False

        print("\n" + "=" * 60)
        print("🎉 [ФИНАЛ ОПРОСА] Опрос успешно завершен!")
        reward_match = re.search(r'(\d+)\s*(?:баллов|балла|балл|руб|₽)', body_text, re.IGNORECASE)
        print(f"💰 [БАЛАНС]: +{reward_match.group(0) if reward_match else 'начислено'}")

        rating_selectors = ["xpath=//label[contains(., 'Очень понравился') or contains(., 'Понравился')]",
                            "xpath=//span[normalize-space()='Понравился' or normalize-space()='Очень понравился']"]
        for sel in rating_selectors:
            elements = await page.query_selector_all(sel)
            for el in elements:
                if await el.is_visible():
                    await el.click(force=True)
                    print("⭐ [ОЦЕНКА]: Выбран вариант «Понравился»")
                    await human_sleep(0.4, 0.7)
                    break
            break

        comment_box = await page.query_selector("textarea, input[placeholder*='комментарий']")
        if comment_box and await comment_box.is_visible():
            await comment_box.click(force=True)
            await comment_box.fill("")
            await page.keyboard.type("Интересный и понятный опрос, всё понравилось!", delay=random.randint(25, 55))
            await human_sleep(0.5, 0.9)

        next_survey_btn = await page.query_selector(
            "button:has-text('Подобрать опрос'), div:has-text('Подобрать опрос'), button[class*='Button_button']")
        if next_survey_btn and await next_survey_btn.is_visible():
            await next_survey_btn.click(force=True)
            print("🚀 [СЛЕДУЮЩИЙ ОПРОС]: Нажата кнопка перехода")
            print("=" * 60)
            await human_sleep(3.0, 5.0)
            return True
        return False

    async def handle_anketka_reward(self, page: Page) -> bool:
        try:
            money_selectors = [".reward-card", "div[class*='reward']", "label:has-text('Деньги')",
                               "button:has-text('Деньги')"]
            for sel in money_selectors:
                cards = await page.query_selector_all(sel)
                for card in cards:
                    card_text = (await card.inner_text()).strip()
                    if await card.is_visible() and "деньги" in card_text.lower():
                        amount_match = re.search(r'(\d+)\s*(?:руб|₽)', card_text, re.IGNORECASE)
                        amount_str = f"+{amount_match.group(1)} руб." if amount_match else "начислены рубли"
                        await card.click(force=True)
                        print(f"\n💰 [ВОЗНАГРАЖДЕНИЕ] Выбран вариант: «Деньги» ({amount_str})")
                        await human_sleep(0.8, 1.2)

                        confirm_btn = await page.query_selector(
                            "button:has-text('Получить'), button:has-text('Подтвердить'), button:has-text('Далее')")
                        if confirm_btn and await confirm_btn.is_visible():
                            await confirm_btn.click(force=True)
                            print("🎉 [СТАТУС] Начисление зафиксировано!")
                        return True
        except Exception as e:
            print(f"[!] Ошибка выбора вознаграждения: {e}")
        return False

    async def handle_open_text_question(self, page: Page, question_text: str) -> bool:
        has_real_input = await page.evaluate("""() => {
            let inps = Array.from(document.querySelectorAll("input[type='text'], input[type='number'], input[inputmode='numeric'], input:not([type]), textarea, div[contenteditable='true']")).filter(el => {
                if (el.offsetParent === null) return false;
                let ph = (el.placeholder || '').toLowerCase();
                let cls = (el.className || '').toLowerCase();
                let parentCls = (el.parentElement ? el.parentElement.className : '').toLowerCase();
                if (ph.includes('день') || ph.includes('месяц') || ph.includes('год') || ph.includes('списка') || ph.includes('город')) return false;
                if (cls.includes('combobox') || parentCls.includes('combobox') || cls.includes('select') || parentCls.includes('select')) return false;
                return true;
            });
            return inps.length > 0;
        }""")

        if not has_real_input:
            return False

        text_inputs = await page.query_selector_all(
            "input[type='text'], input[type='number'], input[inputmode='numeric'], input:not([type]), textarea, div[contenteditable='true']")
        visible_inputs = [inp for inp in text_inputs if await inp.is_visible()]
        if not visible_inputs:
            return False

        target_input = visible_inputs[0]
        answer_text = self.brain.answer_open_text(question_text)
        print(f"\n[?] ОТКРЫТЫЙ ВОПРОС: {question_text}\n✍️  [ВВОД ТЕКСТА]: {answer_text}")

        await target_input.scroll_into_view_if_needed()
        await target_input.click(force=True)
        await human_sleep(0.3, 0.6)
        await target_input.fill("")

        input_type = await target_input.get_attribute("type")
        if input_type == "number":
            answer_text = re.sub(r'\D', '', answer_text)
            if not answer_text:
                answer_text = str(self.profile_personal.get("age", 21))

        await page.keyboard.type(answer_text, delay=random.randint(50, 90))
        await human_sleep(0.6, 1.2)
        await self.click_next(page)
        await human_sleep(2.0, 3.5)

        return True

    async def extract_question_text(self, page: Page) -> str:
        q_selectors = [
            ".header-row", ".header1", ".header2", "[class*='question-header']", "[class*='question-title']",
            "[class*='question-text']",
            "[class*='HeaderStyled']", "[class*='QuestionHeader']", "[class*='questionTitle']",
            ".question-header", ".question-title", ".question-text", "h1", "h2", "h3", ".title"
        ]

        generic_phrases = [
            "выберите подходящий вариант",
            "выберите один или несколько вариантов",
            "выберите вариант ответа",
            "укажите один или несколько вариантов"
        ]

        best_text = ""
        for qs in q_selectors:
            try:
                elements = await page.query_selector_all(qs)
                for el in elements:
                    if await el.is_visible():
                        t = (await el.inner_text()).strip()
                        t_clean = ' '.join(t.replace('\n', ' ').split())

                        if len(t_clean) > 5 and not t_clean.lower().startswith("страница"):
                            is_generic = any(phrase in t_clean.lower() for phrase in generic_phrases)
                            if not is_generic:
                                return t_clean
                            elif not best_text:
                                best_text = t_clean
            except Exception:
                continue

        return best_text if best_text else "Выберите подходящий вариант"

    async def click_next(self, page: Page) -> bool:
        await state.wait_debug_confirm()
        try:
            await self.sync_memory_from_dom(page)
        except Exception:
            pass

        selectors = [
            "button:has-text('ДАЛЕЕ')",
            "button:has-text('Далее')",
            "button:has-text('Вперед')",
            "button:has-text('Продолжить')",
            ".btn-next",
            "button[type='submit']",
            "text=ДАЛЕЕ",
            "text=Далее",
            "text=Вперед"
        ]

        for sel in selectors:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=1000):
                    await locator.scroll_into_view_if_needed()
                    await locator.click(force=True)
                    print(f"[i] [BASE] Нажата кнопка (найдено по: {sel})")
                    return True
            except Exception:
                continue

        return False