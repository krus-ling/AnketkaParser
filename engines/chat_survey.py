import random
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep
from core.bot_state import state


class ChatSurveyEngine(BaseSurveyEngine):
    def __init__(self, brain):
        super().__init__(brain)
        self.last_handled_question = ""

    async def process_step(self, page: Page, body_lower: str) -> bool:
        start_btn = await page.query_selector("button:has-text('Начать чат'), div.black-button:has-text('Начать чат')")
        chat_input = await page.query_selector(
            "input[type='text'], textarea, input[placeholder*='текст'], input[placeholder*='вводить']")

        if start_btn and await start_btn.is_visible() and not chat_input:
            print("[i] [CHAT] Нажата кнопка «Начать чат»")
            await start_btn.click(force=True)
            await human_sleep(2.0, 3.5)
            return True

        chat_submit_btn = await page.query_selector("button:has-text('Отправить'), [role='button']:has-text('Отправить'), [class*='send']:has-text('Отправить')")
        if chat_submit_btn and await chat_submit_btn.is_visible():
            raw_elements = await page.query_selector_all(
                "xpath=//button[contains(., 'Отправить')]/ancestor::div[position()<4]//label | //button[contains(., 'Отправить')]/ancestor::div[position()<4]//div[contains(@class, 'radio')]")
            visible_raw = [el for el in raw_elements if await el.is_visible()]

            if len(visible_raw) >= 2:
                q_text = await page.evaluate("""() => {
                    let btn = Array.from(document.querySelectorAll('button, div')).find(b => (b.innerText || '').trim() === 'Отправить');
                    if (btn) {
                        let parent = btn.closest('div[class*="message"]') || btn.parentElement.parentElement;
                        if (parent) {
                            let textNodes = Array.from(parent.querySelectorAll('div, p, span')).map(n => n.innerText.trim());
                            return textNodes.find(t => t.includes('?')) || "Выберите вариант";
                        }
                    }
                    return "Выберите вариант";
                }""")

                if q_text != self.last_handled_question:
                    options_texts = [(await el.inner_text()).strip() for el in visible_raw]
                    decision = self.brain.decide(q_text, options_texts, is_multiselect=False)
                    idx = decision.selected_indices[0] if decision.selected_indices else 0
                    await visible_raw[idx].click(force=True)
                    await human_sleep(0.5, 0.8)

                    await state.wait_debug_confirm()
                    await chat_submit_btn.click(force=True)

                    self.last_handled_question = q_text
                    await human_sleep(3.0, 4.5)
                    return True

        if not chat_input or not await chat_input.is_visible():
            return False

        interviewer_question = await page.evaluate("""() => {
            let elements = Array.from(document.querySelectorAll('div, p, span')).filter(el => {
                if (el.offsetParent === null) return false;
                let txt = (el.innerText || '').trim();
                return txt.length > 5 && (txt.includes('?') || txt.toLowerCase().startsWith('как') || txt.toLowerCase().startsWith('сколько') || txt.toLowerCase().startsWith('где'));
            });
            return elements.length > 0 ? elements[elements.length - 1].innerText.trim() : "";
        }""")

        if not interviewer_question or interviewer_question == getattr(self, 'last_handled_question', ""):
            return False

        print(f"\n💬 [ИИ-ИНТЕРВЬЮЕР]: {interviewer_question}")
        reply_text = self.brain.generate_chat_response(interviewer_question)
        print(f"🤖 [ОТВЕТ]: {reply_text}")

        await chat_input.scroll_into_view_if_needed()
        await chat_input.click(force=True)
        await chat_input.fill("")
        await page.keyboard.type(reply_text, delay=random.randint(40, 75))

        # Снимаем фокус
        await page.evaluate("() => { if(document.activeElement) document.activeElement.blur(); }")
        await human_sleep(0.4, 0.7)

        # Ждем подтверждения от пользователя в режиме отладки
        await state.wait_debug_confirm()

        # Нажимаем Enter на всякий случай
        await page.keyboard.press("Enter")

        # ====================================================
        # НОВАЯ НАДЕЖНАЯ ЛОГИКА НАЖАТИЯ КНОПКИ ОТПРАВИТЬ
        # ====================================================
        clicked = False
        send_selectors = [
            "button:has-text('Отправить')",
            "div[role='button']:has-text('Отправить')",
            "#send-btn",
            "button[type='submit']",
            "button[class*='send']",
            ".btn"
        ]

        for sel in send_selectors:
            elements = await page.query_selector_all(sel)
            for el in elements:
                if await el.is_visible():
                    btn_text = (await el.inner_text()).strip().lower()
                    if len(btn_text) < 30 and (
                            "отправить" in btn_text or "далее" in btn_text or sel in ["#send-btn", ".btn"]):
                        await el.scroll_into_view_if_needed()
                        await el.click(force=True)
                        clicked = True
                        break
            if clicked:
                break

        if not clicked:
            # Резервный выстрел через JS
            await page.evaluate("""() => {
                let btns = Array.from(document.querySelectorAll('button, div, span, a')).filter(b => {
                    let t = (b.innerText || '').trim().toLowerCase();
                    return t === 'отправить' || t === 'send';
                });
                let visibleBtn = btns.find(b => b.getBoundingClientRect().height > 0);
                if (visibleBtn) visibleBtn.click();
            }""")

        self.last_handled_question = interviewer_question
        await human_sleep(3.0, 5.0)
        return True