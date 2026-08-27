# Чат-опросы (MakeSense / ИИ-интервьюер)

import random
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep

class ChatSurveyEngine(BaseSurveyEngine):
    async def process_step(self, page: Page, body_lower: str) -> bool:
        start_btn = await page.query_selector("button:has-text('Начать чат'), div.black-button:has-text('Начать чат')")
        chat_input = await page.query_selector("input[placeholder*='текст'], textarea[placeholder*='текст'], input[placeholder*='вводить']")

        if start_btn and await start_btn.is_visible() and not chat_input:
            print("[i] [CHAT] Нажата кнопка «Начать чат»")
            await start_btn.click(force=True)
            await human_sleep(2.0, 3.5)
            return True

        chat_submit_btn = await page.query_selector("button:has-text('Отправить'), div:has-text('Отправить')")
        if chat_submit_btn and await chat_submit_btn.is_visible():
            raw_elements = await page.query_selector_all("xpath=//button[contains(., 'Отправить')]/ancestor::div[position()<4]//label | //button[contains(., 'Отправить')]/ancestor::div[position()<4]//div[contains(@class, 'radio')]")
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

        if not interviewer_question or interviewer_question == self.last_handled_question:
            return False

        print(f"\n💬 [ИИ-ИНТЕРВЬЮЕР]: {interviewer_question}")
        reply_text = self.brain.generate_chat_response(interviewer_question)
        print(f"🤖 [ОТВЕТ]: {reply_text}")

        await chat_input.scroll_into_view_if_needed()
        await chat_input.click(force=True)
        await chat_input.fill("")
        await page.keyboard.type(reply_text, delay=random.randint(40, 75))
        await human_sleep(0.4, 0.7)
        await page.keyboard.press("Enter")

        send_btn = await page.query_selector("button[type='submit'], button[class*='send'], div[class*='send']")
        if send_btn and await send_btn.is_visible():
            await send_btn.click(force=True)

        self.last_handled_question = interviewer_question
        await human_sleep(3.0, 5.0)
        return True