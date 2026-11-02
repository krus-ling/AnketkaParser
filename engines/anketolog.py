import asyncio
from playwright.async_api import Page
from engines.base import BaseSurveyEngine
from engines.mixins import QuestionDispatcherMixin
from core.bot_state import state
from core.dom_synchronizer import DOMSynchronizer
from engines.js_snippets import (
    JS_ANKETOLOG_PROCESS_STEP,
    JS_ANKETOLOG_FILL_TEXT,
    JS_ANKETOLOG_CLEAR_TEXT_TARGET,
    JS_ANKETOLOG_SELECT_CHOICE
)

class AnketologEngine(QuestionDispatcherMixin, BaseSurveyEngine):

    async def click_next(self, page: Page) -> bool:
        await state.wait_debug_confirm()
        try:
            await DOMSynchronizer.sync_memory(page, self.brain)
        except Exception:
            pass

        selectors = [
            "[data-role='next-btn']",
            "text='ЗАВЕРШИТЬ'", "text='Завершить'", "text='ГОТОВО'", "text='Готово'",
            "text='НАЧАТЬ'", "text='Начать'", "text='ДАЛЕЕ'", "text='Далее'",
            "button:has-text('ЗАВЕРШИТЬ')", "button:has-text('ДАЛЕЕ')",
            "button:has-text('НАЧАТЬ')", ".btn-next", ".btn-success",
            "a.button--filled", ".sf-footer__btn--next"
        ]

        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(force=True)

                        await asyncio.sleep(0.6)

                        try:
                            has_error = await page.evaluate("""() => {
                                let errs = Array.from(document.querySelectorAll('.error-message, .question-error, .invalid-feedback, .notification--error, .help-block, .jGrowl-message, .toast-message, .alert, .field-error, .field-error__text')).filter(e => {
                                    if (e.offsetParent === null && !e.classList.contains('jGrowl-message') && !e.classList.contains('toast-message')) return false;
                                    let t = (e.innerText || e.textContent || '').trim().toLowerCase();
                                    return t.length > 0 && (t.includes('заполнить') || t.includes('ошибка') || t.includes('некорректно') || t.includes('нет ответа') || e.classList.contains('error-message') || e.classList.contains('help-block') || e.classList.contains('field-error'));
                                });

                                if (errs.length === 0 && (document.body.innerText.includes('Некорректно заполнен') || document.body.innerText.includes('Нет ответа на обязательный'))) {
                                    errs = [{innerText: 'Некорректно заполнен или нет ответа на обязательный вопрос'}];
                                }

                                if (errs.length > 0) {
                                    document.querySelectorAll('[data-bot-handled], [data-bot-handled-choices]').forEach(e => {
                                        e.removeAttribute('data-bot-handled');
                                        e.removeAttribute('data-bot-handled-choices');
                                    });
                                    return errs[0].innerText || errs[0].textContent;
                                }
                                return null;
                            }""")
                        except Exception:
                            print(f"[i] [ANKETOLOG] Нажата кнопка (найдено по: {sel}). Успешный переход!")
                            return True

                        if has_error:
                            print(f"\n[!] СРАБОТАЛ БАРЬЕР САЙТА (Анкетолог): {has_error}")
                            await self.save_error_snapshot(page, f"BARRIER_{has_error}")
                            return False

                        try:
                            await page.evaluate(
                                "() => document.querySelectorAll('[data-bot-active-q]').forEach(e => e.removeAttribute('data-bot-active-q'))")
                        except:
                            pass

                        print(f"[i] [ANKETOLOG] Нажата кнопка (найдено по: {sel})")
                        return True
            except Exception:
                continue

        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:
        any_handled = False
        last_q_text = None
        q_loop_count = 0

        for _ in range(60):
            step_data = await page.evaluate(JS_ANKETOLOG_PROCESS_STEP)

            if not step_data or step_data.get('targetType') == 'done_or_info':
                if not any_handled and step_data and step_data.get('questionText'):
                    print(f"\n📄 [ИНФО-ЭКРАН]: {step_data.get('questionText')}")
                break

            target_type = step_data.get('targetType')
            q_text = step_data.get('questionText', 'Вопрос')
            options = step_data.get('options', [])
            is_multi = step_data.get('isMulti', False)

            if q_text == last_q_text:
                q_loop_count += 1
            else:
                last_q_text = q_text
                q_loop_count = 0

            if q_loop_count >= 5:
                print(f"\n[!] ОБНАРУЖЕНО ЗАЦИКЛИВАНИЕ! Бот не может решить вопрос.")
                await self.save_error_snapshot(page, f"LOOP_QUESTION_{q_text}")
                return False

            print(f"\n============================================================")
            print(f"[?] ВОПРОС: {q_text}")
            print(f"[i] ТИП: {'Множественный выбор' if is_multi else 'Одиночный выбор' if target_type == 'choices' else target_type}")

            if target_type == 'text':
                ans_text = self.brain.answer_open_text(q_text)
                print(f"✍️  [ВВОД]: {ans_text}")
                await page.evaluate(JS_ANKETOLOG_FILL_TEXT, ans_text)
                any_handled = True

            elif target_type == 'choices':
                print(f"[*] ВСЕГО ВАРИАНТОВ: {len(options)}")
                for idx, opt in enumerate(options):
                    print(f"    [{idx}] {opt}")

                decision = self.brain.decide(q_text, options, is_multiselect=is_multi)
                selected_opts = [options[i] for i in decision.selected_indices if i < len(options)]

                print(f"[ВЫБРАНО] ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_opts}")
                print(f"[LLM] ЛОГИКА: {decision.reasoning}")

                for idx in decision.selected_indices:
                    await page.evaluate(JS_ANKETOLOG_SELECT_CHOICE, idx)

                    click_target = page.locator('[data-bot-click-target="true"]')
                    if await click_target.count() > 0:
                        try:
                            await click_target.first.scroll_into_view_if_needed()
                            await asyncio.sleep(0.1)
                            await click_target.first.click(force=True, timeout=1500)
                        except Exception:
                            try:
                                box = await click_target.first.bounding_box()
                                if box:
                                    await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                            except Exception as e2:
                                print(f"[!] Критическая ошибка клика: {e2}")

                    try:
                        await page.evaluate(
                            "() => document.querySelectorAll('[data-bot-click-target=\"true\"]').forEach(e => e.removeAttribute('data-bot-click-target'))")
                    except:
                        pass

                    await asyncio.sleep(0.3)

                any_handled = True

            print(f"============================================================")
            await asyncio.sleep(0.4)

        await asyncio.sleep(0.5)
        click_success = await self.click_next(page)

        stagnation = getattr(self, "stagnation_clicks", 0)
        if not any_handled:
            if not click_success:
                try:
                    current_url = page.url.lower()
                    body_txt = (await page.inner_text("body")).lower()
                    is_finished = (
                        "finishtoken=" in current_url or
                        "100% пройдено" in body_txt or
                        "вернуться в личный кабинет" in body_txt or
                        "ваши ответы вместе с мнениями" in body_txt or
                        ("спасибо" in body_txt and ("ответ" in body_txt or "участи" in body_txt or "пройдено" in body_txt))
                    )
                    if is_finished:
                        print("\n[🎉] [ANKETOLOG] Опрос успешно пройден (экран 100% завершения).")
                        back_btn = page.locator("a:has-text('Личный кабинет'), a:has-text('Вернуться'), button:has-text('Личный кабинет')").first
                        if await back_btn.is_visible():
                            await back_btn.click(force=True)
                            await asyncio.sleep(2.0)
                        return True
                except Exception:
                    pass

                print(f"\n[!] ТУПИК: Нет вопросов для заполнения и не найдена кнопка 'Далее'.")
                await self.save_error_snapshot(page, "NO_QUESTIONS_AND_NO_BTN")
                return False
            else:
                self.stagnation_clicks = stagnation + 1
                if self.stagnation_clicks >= 3:
                    print(f"\n[!] ОБНАРУЖЕНО ЗАЦИКЛИВАНИЕ СТРАНИЦЫ: Кнопка нажимается, но переход не происходит.")
                    await self.save_error_snapshot(page, "PAGE_STAGNATION_LOOP")
                    self.stagnation_clicks = 0
                    return False
        else:
            self.stagnation_clicks = 0

        return any_handled or click_success