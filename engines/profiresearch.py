import asyncio
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep
from engines.mixins import QuestionDispatcherMixin
from core.bot_state import state
from core.dom_synchronizer import DOMSynchronizer
from engines.js_snippets import (
    JS_PROFIRESEARCH_FAST_CITY, JS_PROFIRESEARCH_CHECK_CITY_Q,
    JS_PROFIRESEARCH_PROCESS_STEP, JS_PROFIRESEARCH_FILL_TEXT,
    JS_PROFIRESEARCH_CLEAR_TEXT_TARGET, JS_PROFIRESEARCH_SELECT_DROPDOWN,
    JS_PROFIRESEARCH_CLEAR_SELECT_TARGET, JS_PROFIRESEARCH_SELECT_CHOICE
)

class ProfiResearchEngine(QuestionDispatcherMixin, BaseSurveyEngine):

    async def click_next(self, page: Page) -> bool:
        await state.wait_debug_confirm()
        try:
            await DOMSynchronizer.sync_memory(page, self.brain)
        except Exception:
            pass

        selectors = ["#next", "button[name='goto']", ".bg-green", ".btn", "text='Далее'", "text='Вперед'"]
        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(force=True)
                        print(f"[i] [PROFIRESEARCH] Нажата кнопка: «Далее» (найдено по: {sel})")
                        return True
            except Exception: continue
        return False

    async def handle_combobox_city(self, page: Page) -> bool:
        target_city = self.profile_personal.get("city", "Москва")
        if await page.evaluate(JS_PROFIRESEARCH_FAST_CITY, target_city):
            print(f"[✓] [PROFIRESEARCH] Город «{target_city}» выбран из быстрых ссылок")
            return True

        sel_input = await page.query_selector('.selectize-input input')
        if sel_input and await sel_input.is_visible():
            print(f"\n[i] [PROFIRESEARCH] Ввод города: «{target_city}»...")
            await sel_input.scroll_into_view_if_needed()
            await sel_input.click(force=True)
            await page.keyboard.type(target_city, delay=100)
            await human_sleep(1.0, 1.5)

            options = await page.query_selector_all('.selectize-dropdown-content .option')
            for opt in options:
                if target_city.lower() in (await opt.inner_text()).lower():
                    await opt.click(force=True)
                    print(f"[✓] [PROFIRESEARCH] Город «{target_city}» выбран из списка")
                    return True
            await page.keyboard.press("Enter")
            return True
        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:
        # Сначала проверяем, не вопрос ли это про город
        if await page.evaluate(JS_PROFIRESEARCH_CHECK_CITY_Q):
            if await self.handle_combobox_city(page):
                await human_sleep(1.0, 1.5)
                await self.click_next(page)
                return True

        # Если обычный вопрос - передаем в универсальный диспетчер
        return await self.dispatch_questions(
            page=page,
            parse_js=JS_PROFIRESEARCH_PROCESS_STEP,
            fill_text_js=JS_PROFIRESEARCH_FILL_TEXT,
            clear_text_js=JS_PROFIRESEARCH_CLEAR_TEXT_TARGET,
            select_choice_js=JS_PROFIRESEARCH_SELECT_CHOICE,
            select_dropdown_js=JS_PROFIRESEARCH_SELECT_DROPDOWN,
            clear_dropdown_js=JS_PROFIRESEARCH_CLEAR_SELECT_TARGET
        )