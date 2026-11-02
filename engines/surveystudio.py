import base64
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep
from core.bot_state import state
from engines.js_snippets import (
    JS_SURVEYSTUDIO_FALLBACK_NEXT_BTN, JS_SURVEYSTUDIO_CHECK_MATRIX,
    JS_SURVEYSTUDIO_SELECT_MATRIX_CHOICE, JS_SURVEYSTUDIO_PROCESS_STEP,
    JS_SURVEYSTUDIO_FILL_TEXT
)


class SurveyStudioEngine(BaseSurveyEngine):

    async def click_next(self, page: Page) -> bool:
        await state.wait_debug_confirm()
        await self.sync_memory_from_dom(page)

        selectors = [
            "#processingGoForwardBtn", ".next-button",
            "button:has-text('ДАЛЕЕ')", "button:has-text('Далее')",
            "button:has-text('НАЧАТЬ')", "button:has-text('Начать')",
            "button:has-text('ПРОДОЛЖИТЬ')", "button:has-text('Продолжить')",
            "div:has-text('ДАЛЕЕ')", "div:has-text('Далее')"
        ]
        for sel in selectors:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=500):
                    await locator.scroll_into_view_if_needed()
                    await locator.click(force=True)
                    print(f"[i] [SURVEY-STUDIO] Нажата кнопка (найдено по: {sel})")
                    return True
            except Exception:
                continue

        try:
            btn_handle = await page.evaluate_handle(JS_SURVEYSTUDIO_FALLBACK_NEXT_BTN)
            if not await btn_handle.evaluate("el => !el"):
                await btn_handle.scroll_into_view_if_needed()
                await btn_handle.evaluate("""el => {
                    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                        el.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                    });
                    if (el.click) el.click();
                }""")
                try:
                    await btn_handle.click(force=True, timeout=1500)
                except Exception:
                    pass
                txt = await btn_handle.evaluate("el => (el.innerText || el.value || '').trim()")
                print(f"[i] [SURVEY-STUDIO] Нажата кнопка (fallback): «{txt or 'Далее'}»")
                return True
        except Exception:
            pass
        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:
        # 1. Получаем данные с JS-парсера SurveyStudio
        data = await page.evaluate(JS_SURVEYSTUDIO_PROCESS_STEP)

        if not data:
            return False

        # Обработка информационного экрана (раньше блокировалось ранним return False)
        if data.get("targetType") == "done_or_info":
            q_text = data.get("questionText", "")
            if q_text:
                print(f"\n📄 [SURVEYSTUDIO] [ИНФО-ЭКРАН]: {q_text}")
            await human_sleep(1.0, 1.5)
            await self.click_next(page)
            return True

        # 2. Перехват: Если есть картинки, вызываем зрение
        options = data.get("options", [])
        if any("[Картинка:" in opt for opt in options):
            print("\n👁️ [VISION] Обнаружены картинки! Включаем визуальный анализ...")

            await page.evaluate("""() => {
                let cells = document.querySelectorAll('.grid__cell, .ss-choice-item');
                cells.forEach((cell, idx) => {
                    let img = cell.querySelector('img');
                    if (img) {
                        let rect = img.getBoundingClientRect();
                        let badge = document.createElement('div');
                        badge.className = 'bot-vision-badge';
                        badge.style.cssText = `position:fixed; top:${rect.top + 10}px; left:${rect.left + 10}px; background:red; color:white; font-size:22px; font-weight:bold; padding:4px 10px; z-index:999999; border: 2px solid white; border-radius: 4px; box-shadow: 2px 2px 5px rgba(0,0,0,0.5);`;
                        badge.innerText = `[${idx}]`;
                        document.body.appendChild(badge);
                    }
                });
            }""")

            await human_sleep(0.5, 1.0)

            print("[👁️ VISION] Делаем снимок экрана для ИИ...")
            q_container = await page.query_selector('.question-content, .ss-answers')
            image_bytes = await q_container.screenshot(type='jpeg', quality=70) if q_container else await page.screenshot(type='jpeg', quality=70)
            base64_img = base64.b64encode(image_bytes).decode('utf-8')

            await page.evaluate("() => document.querySelectorAll('.bot-vision-badge').forEach(e => e.remove())")

            recognized_brands = self.brain.llm.recognize_image_options(base64_img)

            if recognized_brands:
                print("\n[👁️ VISION] Замена вариантов завершена:")
                for i in range(len(options)):
                    idx_str = str(i)
                    if idx_str in recognized_brands:
                        old_name = options[i]
                        options[i] = recognized_brands[idx_str]
                        print(f"  [{i}] {old_name} ➔ {options[i]}")

            data["options"] = options

        total_handled = 0
        matrix_data = await page.evaluate(JS_SURVEYSTUDIO_CHECK_MATRIX)

        if matrix_data and matrix_data["rows"]:
            unanswered = [r for r in matrix_data["rows"] if not r["isAnswered"]]
            if unanswered:
                col_options = matrix_data["colHeaders"]
                print("\n" + "=" * 60 + f"\n📊 [ТАБЛИЦА / МАТРИЦА]: {matrix_data['qText']}\n[*] Всего строк: {len(matrix_data['rows'])} | Осталось заполнить: {len(unanswered)}\n[*] Варианты колонок ({len(col_options)}): {col_options}\n" + "=" * 60)
                for r in unanswered:
                    row_q = f"{matrix_data['qText']} -> {r['title']}"
                    current_options = col_options[:r["inputsCount"]] if len(col_options) >= r["inputsCount"] else [f"Вариант {k + 1}" for k in range(r["inputsCount"])]
                    decision = self.brain.decide(row_q, current_options, is_multiselect=r["isMulti"])
                    chosen_idx = decision.selected_indices[0] if decision.selected_indices and decision.selected_indices[0] < len(current_options) else len(current_options) // 2
                    print(f"  🔹 {r['title']} ➔ [{current_options[chosen_idx]}] (Логика: {decision.reasoning})")
                    await page.evaluate(JS_SURVEYSTUDIO_SELECT_MATRIX_CHOICE, {"rowIndex": r["rowIndex"], "colIdx": chosen_idx})
                    total_handled += 1
                    await human_sleep(0.1, 0.3)
                await human_sleep(1.0, 1.5)
                await self.click_next(page)
                return True

        if data["targetType"] == "text":
            print(f"\n[?] ОТКРЫТЫЙ ВОПРОС: {data['questionText']}")
            ans_text = self.brain.answer_open_text(data["questionText"])
            if ans_text:
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                print(f"✍️  [ВВОД]: {ans_text}")
                target_input = await page.query_selector('[data-bot-target="true"]')
                if target_input:
                    await target_input.scroll_into_view_if_needed()
                    await target_input.click(force=True)
                    await page.evaluate(JS_SURVEYSTUDIO_FILL_TEXT, {"inp": target_input, "txt": ans_text})
                    await target_input.fill(ans_text)
                    await human_sleep(0.5, 0.8)
                    await self.click_next(page)
                    return True

        elif data["targetType"] == "choices":
            print("\n" + "=" * 60)
            print(f"[?] ВОПРОС: {data['questionText']}")
            print(f"[i] ТИП: {'Множественный выбор' if data['isMulti'] else 'Одиночный выбор'}")
            print(f"[*] ВСЕГО ВАРИАНТОВ: {len(data['options'])}")
            for idx, text in enumerate(data["options"][:15]):
                print(f"    [{idx}] {text}")

            decision = self.brain.decide(data["questionText"], data["options"], data["isMulti"])
            chosen_indices = decision.selected_indices if decision.selected_indices else [0]
            selected_names = [data["options"][i] for i in chosen_indices if i < len(data["options"])]
            print(f"[ВЫБРАНО ({len(chosen_indices)})]: {chosen_indices} -> {selected_names}\n[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)

            for sel_idx in chosen_indices:
                await page.evaluate("""(idx) => {
                    let inputs = Array.from(document.querySelectorAll('.question-content input[type="radio"], .question-content input[type="checkbox"], .ss-answers input'));
                    let inp = inputs[idx];
                    if (inp) {
                        let label = inp.closest('label') || document.querySelector(`label[for="${inp.id}"]`) || inp.parentElement;
                        label.scrollIntoView({behavior: 'smooth', block: 'center'});
                        label.click();
                        inp.checked = true;
                        inp.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""", sel_idx)
                await human_sleep(0.2, 0.4)

            await human_sleep(0.8, 1.2)
            await self.click_next(page)
            return True

        return False
