import asyncio
import random
import math
import re
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep
from core.bot_state import state
from core.dom_synchronizer import DOMSynchronizer
from engines.mixins import (
    ProgressiveBlocksMixin,
    DemographicsMixin,
    InfoScreenMixin
)

from engines.js_snippets import (
    JS_FIND_FALLBACK_NEXT_BTN,
    JS_CHECK_DEMOGRAPHICS,
    JS_EXTRACT_QUESTION_TEXT
)


class CloudSurveyEngine(ProgressiveBlocksMixin, DemographicsMixin, InfoScreenMixin, BaseSurveyEngine):

    async def click_next(self, page: Page) -> bool:
        decision = await state.wait_debug_confirm()
        if decision == "RETRY":
            print("[🔄] Отменяем переход по кнопке «Далее». Сбрасываем выбранные варианты...")
            await page.evaluate("""() => {
                let active = document.querySelector('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"]), .survey-page, .survey-block, .page-content') || document.body;
                active.querySelectorAll('input:checked').forEach(i => {
                    i.click();
                    i.checked = false;
                    i.dispatchEvent(new Event('change', {bubbles: true}));
                });
                let activeCustom = active.querySelectorAll('.option__QmiJR.Active__IgXHd, label.selected, label.active, [aria-checked="true"], .choice__option_checked, [class*="checked_yes"]');
                activeCustom.forEach(el => {
                    let btn = el.querySelector('[role="button"], input, label') || el;
                    btn.click();
                });
                active.querySelectorAll('textarea, input[type="text"]:not([class*="search"])').forEach(i => {
                    i.value = '';
                    i.dispatchEvent(new Event('input', {bubbles: true}));
                    i.dispatchEvent(new Event('change', {bubbles: true}));
                });
            }""")
            return False

        try:
            await DOMSynchronizer.sync_memory(page, self.brain)
        except:
            pass

        try:
            await page.evaluate("""() => {
                document.querySelectorAll('a[target="_blank"]').forEach(el => {
                    let txt = (el.innerText || '').toLowerCase();
                    if (txt.includes('далее') || txt.includes('продолжить') || txt.includes('завершить') || txt.includes('готово')) {
                        el.removeAttribute('target');
                    }
                });
            }""")
        except:
            pass

        try:
            pre_count = await page.evaluate("""() => {
                let active = document.querySelector('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"]), .survey-page, .survey-block, .page-content') || document.body;
                let btns = Array.from(active.querySelectorAll('button, a, input[type="submit"], input[type="button"]')).filter(el => {
                    if (el.offsetParent === null) return false;
                    let t = (el.innerText || el.value || '').toLowerCase();
                    return t.includes('далее') || t.includes('продолжить') || t.includes('завершить') || el.getAttribute('data-role') === 'next-btn';
                });
                return btns.length;
            }""")

            await page.evaluate("""() => {
                if (document.activeElement) document.activeElement.blur();
                document.body.focus();
            }""")
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.8)

            is_transitioning = await page.evaluate("""(preCount) => {
                let active = document.querySelector('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"]), .survey-page, .survey-block, .page-content');
                if (!active) active = document.body;

                let btns = Array.from(active.querySelectorAll('button, a, input[type="submit"], input[type="button"]')).filter(el => {
                    if (el.offsetParent === null) return false;
                    let t = (el.innerText || el.value || '').toLowerCase();
                    return (t.includes('далее') || t.includes('продолжить') || t.includes('завершить') || el.getAttribute('data-role') === 'next-btn') && !el.disabled && !el.classList.contains('disabled');
                });

                if (btns.length < preCount) return true;
                return false;
            }""", pre_count)

            if is_transitioning and pre_count > 0:
                print("[i] [CLOUDSURVEY] Успешный переход по клавише Enter!")
                await human_sleep(1.2, 1.8)
                return True

        except Exception as e:
            if "Execution context was destroyed" in str(e) or "Target page" in str(e):
                print("[i] [CLOUDSURVEY] Успешный переход по клавише Enter (перезагрузка страницы)!")
                await human_sleep(1.2, 1.8)
                return True

        selectors = [
            # 1. Приоритетные селекторы движков (Ipsos / Dimensions / mrIWeb / CloudSurvey / Pythia / Pathway)
            "button[data-testid='respondent.nextButton']",
            "button[name='_NNext']",
            ".question-card__navigation button",
            "button.button_theme_primary",
            "input[name='_NNext']",
            "[name='_NNext']",
            ".mrNext",
            "button[data-role='next-btn']",
            "button[data-testid='next-btn']",
            "button[data-test='next-btn']",
            "button[data-testid='next-survey']",
            "button#__next",
            "button[id='__next']",
            "#processingGoForwardBtn",
            ".next-button",
            ".page__button-next",
            "#nextSurvey",
            "button[type='submit']",

            # Oprosso стрелка вниз / кнопка перехода
            "div.arrow__IHQLS",
            "div[class*='arrow__']",
            "svg[class*='arrow_castom']",

            # 2. Нативные <button> с текстом перехода
            "button:has-text('ДАЛЕЕ')",
            "button:has-text('Далее')",
            "button:has-text('Вперед')",
            "button:has-text('ВПЕРЕД')",
            "button:has-text('Продолжить')",
            "button:has-text('ПРОДОЛЖИТЬ')",
            "button:has-text('Следующий')",
            "button:has-text('Завершить')",
            "button:has-text('Начать опрос')",
            "button:has-text('Начать')",
            "[class*='Button_button__']",
            "[class*='Button_button']:not([class*='Container'])",
            "div:has-text('Начать опрос')",

            # 3. Кнопки <input type="submit">
            "input[type='submit'][value*='Далее']",
            "input[type='submit'][value*='ДАЛЕЕ']",
            "input[type='submit']",

            # 4. Ссылки <a>
            "a:has-text('ДАЛЕЕ')",
            "a:has-text('Далее')",
            "a:has-text('Продолжить')",

            # 5. Элементы с явной ролью role="button"
            "[role='button']:has-text('ДАЛЕЕ')",
            "[role='button']:has-text('Далее')",
            "[role='button']:has-text('Продолжить')"
        ]

        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if not await btn.is_visible():
                        continue

                    # Проверяем текст: кнопка не может быть длинным абзацем инструкции
                    txt = (await btn.inner_text() or await btn.get_attribute("value") or "").strip()
                    if len(txt) > 25 and not any(k in sel for k in ["[name=", ".question-card__navigation"]):
                        continue
                    if any(bad in txt.lower() for bad in ["нажмите", "пожалуйста", "чтобы", "опрос", "внимание", "инструкц"]):
                        continue

                    tag_name = await btn.evaluate("el => el.tagName.toLowerCase()")
                    if tag_name in ["span", "div", "p", "label", "h1", "h2", "h3", "h4"]:
                        is_btn = await btn.evaluate("""el => {
                            let role = el.getAttribute('role');
                            let style = window.getComputedStyle(el);
                            return role === 'button' || style.cursor === 'pointer' || !!el.closest('button, a, [role="button"]');
                        }""")
                        if not is_btn:
                            continue

                    await btn.scroll_into_view_if_needed()
                    await asyncio.sleep(0.15)

                    # Физический клик
                    try:
                        box = await btn.bounding_box()
                        if box:
                            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    except Exception:
                        pass

                    # Программный клик
                    try:
                        await btn.click(force=True, timeout=1200)
                    except Exception:
                        pass

                    # DOM dispatch событий для React SPA
                    try:
                        await btn.evaluate("""el => {
                            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                                el.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                            });
                            if (el.click) el.click();
                        }""")
                    except Exception:
                        pass

                    print(f"[i] [CLOUDSURVEY] Нажата кнопка перехода: {sel}")
                    await human_sleep(1.2, 1.8)
                    return True
            except Exception:
                continue

        btn_handle = await page.evaluate_handle(JS_FIND_FALLBACK_NEXT_BTN)
        if not await btn_handle.evaluate("el => !el"):
            txt = await btn_handle.evaluate("el => (el.innerText || el.value || '').trim()")
            await btn_handle.scroll_into_view_if_needed()
            await btn_handle.evaluate("""el => {
                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                    el.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                });
                if (el.click) el.click();
            }""")
            try:
                await btn_handle.click(force=True, timeout=1500)
            except:
                pass
            print(f"[i] [CLOUDSURVEY] Нажата кнопка (fallback): «{txt or 'Далее'}»")
            await human_sleep(1.2, 1.8)
            return True

        return False

    async def extract_question_text(self, page: Page) -> str:
        return await page.evaluate(JS_EXTRACT_QUESTION_TEXT)

    def _apply_alternative_logic(self, options_texts, decision, is_multi, q_key="default"):
        if not hasattr(self, "last_selected_by_q"):
            self.last_selected_by_q = {}

        if getattr(state, "force_alternative", False):
            last_idx = self.last_selected_by_q.get(q_key, [])
            available = [i for i in range(len(options_texts)) if i not in last_idx]

            safe_available = [i for i in available if not any(bad in options_texts[i].lower() for bad in
                                                              ["ничего", "затрудняюсь", "не знаю", "другое",
                                                               "свой вариант"])]
            if not safe_available:
                safe_available = available

            if safe_available:
                if not is_multi:
                    decision.selected_indices = [random.choice(safe_available)]
                else:
                    count = max(1, min(4, math.ceil(len(safe_available) / 2)))
                    decision.selected_indices = random.sample(safe_available, count)

            print(f"\n[🔄] СРАБОТАЛ РЕЖИМ «ОТВЕТИТЬ ИНАЧЕ». Исключены прошлые варианты: {last_idx}")

        self.last_selected_by_q[q_key] = decision.selected_indices
        return decision

    async def handle_matrix_tables(self, page: Page) -> bool:
        """Поиск и заполнение матричных вопросов (таблицы с радиокнопками/чекбоксами в строках)."""
        matrix_data = await page.evaluate("""() => {
            let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"]), .survey-page, .survey-block, .page-content'));
            let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;

            // 1. Ищем только листовые (конечные) контейнеры таблиц без дублирования
            let rawTables = Array.from(active.querySelectorAll('.question-table, table, .matrix-table')).filter(t => {
                if (t.getBoundingClientRect().height === 0) return false;
                return t.querySelectorAll('input[type="radio"], input[type="checkbox"]').length >= 2;
            });

            if (rawTables.length === 0) {
                rawTables = Array.from(active.querySelectorAll('fieldset.question_type_table')).filter(t => {
                    return t.getBoundingClientRect().height > 0 && t.querySelectorAll('input[type="radio"], input[type="checkbox"]').length >= 2;
                });
            }

            let tables = rawTables.filter(t => !rawTables.some(other => other !== t && t.contains(other)));
            if (tables.length === 0) return null;

            let result = [];
            tables.forEach((table, tIdx) => {
                let fieldset = table.closest('fieldset.question, .page__component') || table;
                let mainTitleEl = fieldset.querySelector('.question__label, [role="heading"], .question-text, .question__title, h1, h2, h3, h4, .markdown strong');
                let mainTitle = mainTitleEl ? (mainTitleEl.innerText || '').trim() : 'Оцените следующие пункты';

                // Заголовки столбцов
                let colHeaderEls = Array.from(fieldset.querySelectorAll('.question-table__columns-header [role="columnheader"], thead th, thead td, .matrix__block--header .matrix__cell, th[scope="col"]'));
                let colHeaders = colHeaderEls.map(el => (el.innerText || '').trim()).filter(Boolean);

                if (colHeaders.length === 0) {
                    let mobileColEls = Array.from(fieldset.querySelectorAll('.question-table__column-title-mobile, .question-table__label-text'));
                    colHeaders = [...new Set(mobileColEls.map(el => (el.innerText || '').trim()).filter(Boolean))];
                }

                // 2. СТРОГИЙ поиск строк: берем только прямых потомков с role="row"
                let rowEls = [];
                let yandexRows = Array.from(fieldset.querySelectorAll('.question-table__rows > [role="row"]'));

                if (yandexRows.length > 0) {
                    rowEls = yandexRows;
                } else {
                    let tableRows = Array.from(table.querySelectorAll('tbody > tr'));
                    if (tableRows.length > 0) {
                        rowEls = tableRows;
                    } else {
                        rowEls = Array.from(table.querySelectorAll('tr, .matrix__row')).filter(r => {
                            return !r.querySelector('th:only-child') && r.querySelectorAll('input[type="radio"], input[type="checkbox"]').length > 0;
                        });
                    }
                }

                rowEls.forEach((row, rIdx) => {
                    let inputs = Array.from(row.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                    if (inputs.length === 0) return;

                    let isAnswered = inputs.some(i => i.checked) || row.querySelectorAll('.choice__option_checked, [class*="control_checked"], [class*="checked_yes"]').length > 0;

                    let rowTitleEl = row.querySelector('.question-table__row-header-text, .question-table__row-header, [role="rowheader"], td:first-child, th');
                    let rowTitle = rowTitleEl ? (rowTitleEl.innerText || '').trim() : `Строка ${rIdx + 1}`;

                    if (colHeaders.length === 0 || colHeaders.length < inputs.length) {
                        colHeaders = inputs.map((_, i) => `Вариант ${i + 1}`);
                    }

                    result.push({
                        tableIndex: tIdx,
                        rowIndex: rIdx,
                        isAnswered: isAnswered,
                        mainTitle: mainTitle,
                        rowTitle: rowTitle,
                        questionText: `${mainTitle} -> ${rowTitle}`,
                        colHeaders: colHeaders,
                        isMulti: inputs.some(i => i.type === 'checkbox')
                    });
                });
            });

            return result;
        }""")

        if not matrix_data:
            return False

        unanswered_rows = [r for r in matrix_data if not r["isAnswered"]]
        if not unanswered_rows:
            return False

        print(f"\n[📊] Обнаружена матричная таблица. Неотвеченных строк: {len(unanswered_rows)}")

        for r_info in unanswered_rows:
            q_text = r_info["questionText"]
            options_texts = r_info["colHeaders"]
            is_multi = r_info["isMulti"]
            t_idx = r_info["tableIndex"]
            r_idx = r_info["rowIndex"]

            print("\n" + "=" * 60)
            try:
                self.brain.stats['total_answered'] += 1
                print(f"[№ {self.brain.stats['total_answered']}] МАТРИЦА (СТРОКА {r_idx + 1}): {r_info['rowTitle']}")
            except Exception:
                print(f"[?] МАТРИЦА: {q_text}")

            print(f"[*] ВСЕГО КОЛОНОК: {len(options_texts)}")
            for idx, text in enumerate(options_texts):
                print(f"    [{idx}] {text}")

            decision = self.brain.decide(q_text, options_texts, is_multi)
            decision = self._apply_alternative_logic(options_texts, decision, is_multi, q_key=f"matrix_{t_idx}_{r_idx}")

            chosen_indices = decision.selected_indices if decision.selected_indices else [0]
            selected_names = [options_texts[i] for i in chosen_indices if i < len(options_texts)]
            print(f"[LLM] ВЫБРАНО: {chosen_indices} -> {selected_names}")
            print(f"[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)

            for col_idx in chosen_indices:
                await page.evaluate("""({tIdx, rIdx, colIdx}) => {
                    let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"]), .survey-page, .survey-block, .page-content'));
                    let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;

                    let rawTables = Array.from(active.querySelectorAll('.question-table, table, .matrix-table')).filter(t => {
                        return t.querySelectorAll('input[type="radio"], input[type="checkbox"]').length >= 2;
                    });
                    if (rawTables.length === 0) {
                        rawTables = Array.from(active.querySelectorAll('fieldset.question_type_table')).filter(t => {
                            return t.querySelectorAll('input[type="radio"], input[type="checkbox"]').length >= 2;
                        });
                    }
                    let tables = rawTables.filter(t => !rawTables.some(other => other !== t && t.contains(other)));
                    let table = tables[tIdx];
                    if (!table) return;

                    let fieldset = table.closest('fieldset.question, .page__component') || table;
                    let rowEls = Array.from(fieldset.querySelectorAll('.question-table__rows > [role="row"]'));
                    if (rowEls.length === 0) {
                        rowEls = Array.from(table.querySelectorAll('tbody > tr, tr, .matrix__row')).filter(r => r.querySelectorAll('input[type="radio"], input[type="checkbox"]').length > 0);
                    }

                    let row = rowEls[rIdx];
                    if (!row) return;

                    let inputs = Array.from(row.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                    let targetInput = inputs[colIdx];
                    if (targetInput) {
                        let label = targetInput.id ? document.querySelector(`label[for="${targetInput.id}"]`) : null;
                        if (!label) {
                            label = targetInput.closest('.choice__option, .question-table__row-option')?.querySelector('label');
                        }
                        let clickable = label || targetInput;
                        clickable.scrollIntoView({behavior: 'smooth', block: 'center'});
                        clickable.click();
                    }
                }""", {"tIdx": t_idx, "rIdx": r_idx, "colIdx": col_idx})
                await human_sleep(0.3, 0.5)

        return True

    async def handle_open_text_blocks(self, page: Page) -> bool:
        input_handles = await page.query_selector_all(
            "input.input__input, input.input__control, input.mrEdit, "
            ".question-card input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='submit']):not([type='button']):not([type='image']):not([type='file']), "
            ".oe1 input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='submit']):not([type='button']):not([type='image']):not([type='file']), "
            "fieldset.question input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='submit']):not([type='button']):not([type='image']):not([type='file']), "
            ".question-container input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='submit']):not([type='button']):not([type='image']):not([type='file']), "
            ".page__questions input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='submit']):not([type='button']):not([type='image']):not([type='file']), "
            ".page__component input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='submit']):not([type='button']):not([type='image']):not([type='file']), "
            ".survey-question input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='submit']):not([type='button']):not([type='image']):not([type='file']), "
            "input[type='text'], input[type='number'], input[type='tel'], input[inputmode='numeric'], input:not([type]), "
            "textarea"
        )

        valid_inputs = []
        seen_names = set()
        for inp in input_handles:
            try:
                if not await inp.is_visible():
                    continue
                is_invalid = await inp.evaluate("""el => {
                    let type = (el.getAttribute('type') || '').toLowerCase();
                    if (['hidden', 'radio', 'checkbox', 'submit', 'button', 'image', 'file', 'reset'].includes(type)) return true;
                    if (el.closest('.select-wrap, .selectize-control, .choices, .portal, [data-testid="dropdown-container"], .combobox, .select, [class*="CitySelect"]')) return true;
                    let row = el.closest('[data-rowidx], .grid__cell, tr, .question__list-item, .pr-row, div.ss-table-row, label, .answer-item, .choice__option');
                    if (row && row.querySelector('input[type="radio"], input[type="checkbox"]')) {
                        let chk = row.querySelector('input[type="radio"], input[type="checkbox"]');
                        if (chk && !chk.checked) return true;
                    }
                    return false;
                }""")
                if is_invalid:
                    continue

                name_attr = await inp.get_attribute("name")
                if name_attr and name_attr in seen_names:
                    continue
                if name_attr:
                    seen_names.add(name_attr)

                valid_inputs.append(inp)
            except Exception:
                continue

        if not valid_inputs:
            return False

        all_already_filled = True
        for inp in valid_inputs:
            val = await inp.input_value()
            if not val.strip():
                all_already_filled = False
                break

        if all_already_filled:
            return False

        print(f"\n[📝] Обнаружено текстовых вопросов на странице: {len(valid_inputs)}")

        for i, inp in enumerate(valid_inputs):
            q_text = await inp.evaluate("""el => {
                let container = el.closest('fieldset.question, .page__component, .question-container, .form-group, .question-card, .survey-question, .question-block, .question, #SurveyContents') || el.parentElement;
                if (!container) return '';
                let titleEl = container.querySelector('.question__label, [role="heading"], .question-text, .question__title, .question-card__text, .mrQuestionText, .header1, .header2, h1, h2, h3, h4, .markdown strong, .wrapper-html');
                return titleEl ? (titleEl.innerText || '').trim() : '';
            }""")

            if not q_text:
                q_text = await self.extract_question_text(page)

            ans = self.brain.answer_open_text(q_text)

            is_numeric = await inp.evaluate("""el => {
                let t = (el.getAttribute('type') || '').toLowerCase();
                let m = (el.getAttribute('inputmode') || '').toLowerCase();
                let s = (el.getAttribute('step') || '').toLowerCase();
                let cls = (el.className || '').toLowerCase();
                return t === 'number' || m === 'numeric' || s === 'any' || s === '1' || cls.includes('number') || cls.includes('numeric') || cls.includes('chisato');
            }""")

            q_lower = q_text.lower()
            if any(w in q_lower for w in ["номер телефона", "телефон", "мобильный", "phone"]):
                has_prefix = await inp.evaluate("""el => {
                    let prev = el.previousElementSibling || (el.parentElement ? el.parentElement.previousElementSibling : null);
                    let txt = (prev ? prev.innerText : '') || '';
                    return txt.includes('+7') || txt.includes('8') || el.getAttribute('maxlength') === '10';
                }""")
                clean_phone = re.sub(r'\D', '', ans)
                if has_prefix or (len(clean_phone) == 11 and (clean_phone.startswith('7') or clean_phone.startswith('8'))):
                    if len(clean_phone) == 11 and (clean_phone.startswith('7') or clean_phone.startswith('8')):
                        clean_phone = clean_phone[1:]
                ans = clean_phone
            elif is_numeric or any(w in q_lower for w in ["лет", "возраст", "сколько вам", "год рождения", "укажите число"]):
                clean_num = re.sub(r'\D', '', ans)
                if clean_num:
                    ans = clean_num
                elif "год" in q_lower:
                    ans = "2005"
                else:
                    ans = "21"

            print(f" ├─ [{i + 1}/{len(valid_inputs)}] {q_text}")
            print(f" └─ ✍️  Ввод: «{ans}»")

            await inp.scroll_into_view_if_needed()
            try:
                await inp.click(force=True)
            except Exception:
                pass
            await human_sleep(0.1, 0.2)
            await inp.fill(ans)

            # Синхронизация React state и связанных mirror-инпутов
            await inp.evaluate("""(el, val) => {
                try {
                    let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set ||
                                 Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
                    if (setter) setter.call(el, val);
                    else el.value = val;
                    if (el._valueTracker) el._valueTracker.setValue('');
                } catch(e) {}
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new Event('blur', {bubbles: true}));
                if (el.name) {
                    document.querySelectorAll(`input[name="${el.name}"], textarea[name="${el.name}"]`).forEach(m => {
                        if (m !== el) {
                            try {
                                let s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                                if (s) s.call(m, val);
                                else m.value = val;
                            } catch(e) {}
                            m.dispatchEvent(new Event('input', {bubbles: true}));
                            m.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    });
                }
            }""", ans)
            await human_sleep(0.2, 0.4)

        # Проверяем, есть ли на странице еще неотвеченные вопросы с вариантами ответов (радио/чекбоксы)
        blocks_data = await self._get_blocks_data(page)
        unanswered_choices = [b for b in blocks_data if not b["is_answered"] and b["options"]]

        if unanswered_choices:
            print(f"[i] [CLOUDSURVEY] Текстовые поля заполнены, но на странице еще есть вопросы с выбором ({len(unanswered_choices)}). Передаем управление в цикл вариантов.")
            return False

        await human_sleep(0.8, 1.4)
        clicked = await self.click_next(page)
        if not clicked:
            return await self.process_step(page, (await page.content()).lower())
        return True

    async def _capture_page_context(self, page: Page):
        page_intro = await page.evaluate("""() => {
            let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"]), .survey-page, .survey-block, .page-content'));
            let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;

            let introNodes = Array.from(active.querySelectorAll('.widget-markup, .page-intro, .instruction, div[class*="description"], div[class*="Description"], .survey-note'));
            let texts = introNodes
                .filter(el => el.getBoundingClientRect().height > 0 && window.getComputedStyle(el).display !== 'none')
                .map(el => (el.innerText || '').trim())
                .filter(t => t.length > 15);

            return texts.join('\\n');
        }""")

        if page_intro and page_intro != getattr(self, "_last_intro_text", None):
            self._last_intro_text = page_intro
            self.brain.ad_context = page_intro
            print(f"[i] [КОНТЕКСТ СТРАНИЦЫ ЗАХВАЧЕН]: «{page_intro[:90]}...»")

    async def _get_blocks_data(self, page: Page):
        """Извлекает обычные блоки вопросов (исключая матрицы-таблицы)."""
        return await page.evaluate("""() => {
            let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"]), .survey-page, .survey-block, .page-content'));
            let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;

            let blockSelectors = [
                'fieldset.question:not(.question_type_table):not([class*="table"])',
                '.page__component:not(:has(.question-table))',
                '.question-container:not(.type_group):not([class*="table"])',
                '.survey-question:not([class*="matrix"])',
                '.question-block:not([class*="matrix"])',
                'div[class*="QuestionContainer"]',
                'div[class*="styled__BlockStyled"]',
                'div[class*="styled_BlockStyled"]',
                '.choice-view',
                '.blocks-container',
                '[data-test-id*="test__content"]'
            ].join(', ');

            let candidates = Array.from(active.querySelectorAll(blockSelectors)).filter(el => {
                if (el.getBoundingClientRect().height === 0) return false;
                if (el.classList.contains('question_type_table') || el.querySelector('.question-table, table')) return false;
                let style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                return el.querySelectorAll('.choice__option, .answer-item, .choice-item, label, button.option__QmiJR, input[type="radio"], input[type="checkbox"], button[class*="button"], [data-testid*="respondent.choice.option"], .choice-options .radio').length >= 2;
            });

            let qBlocks = candidates.filter(b => !candidates.some(other => other !== b && b.contains(other)));
            if (qBlocks.length === 0) qBlocks = [active];

            let result = [];
            qBlocks.forEach((block, bIdx) => {
                if (block.classList.contains('question_type_table') || block.querySelector('.question-table, table')) return;

                let inputs = Array.from(block.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                let hasCheckedInput = inputs.some(i => i.checked);
                let hasCheckedClass = block.querySelectorAll(
                    '.choice__option_checked, [class*="checked_yes"], [class*="_checked"], .selected, .active, [class*="selected" i], [class*="active" i], [class*="Active__"], .Active__IgXHd, [aria-checked="true"], [aria-pressed="true"], [aria-selected="true"], [class*="border-gray-400"], [class*="bg-gray-50"]'
                ).length > 0;

                let hasText = Array.from(block.querySelectorAll('input:not([type="radio"]):not([type="checkbox"]):not([type="hidden"]):not([type="submit"]):not([type="button"]):not([class*="search"]), textarea'))
                    .some(t => t.value && t.value.trim().length > 0);

                let isAnswered = hasCheckedInput || hasCheckedClass || hasText;

                let titleEl = block.querySelector('.question__label, [role="heading"], .question-text, .question__title, .header1, .header2, .tiptap, .ProseMirror, [data-test-id*="test__content"] p, h1, h2, h3, h4, .markdown strong, .wrapper-html');
                let qTitle = titleEl ? (titleEl.innerText || '').trim() : '';

                let optSelector = [
                    'div.choice__option', 'div[class*="styled__AnswerStyled"]', 'div[class*="scale-item"]',
                    'div[class*="scale-answer"]', 'div[class*="AnswerRow"]', 'div[class*="answer-row"]',
                    'li.choice-item', 'div.choice-item', 'div[class*="LogoItem"]', 'div[class*="GridItem"]',
                    'label.option-label', '.answer-item', '.scale-item', '.LogoItem', '.grid__cell',
                    'button.option__QmiJR', 'label.question-list__item',
                    '[data-testid*="respondent.choice.option"]', '.choice-options .radio', '.choice-option'
                ].join(', ');

                let optNodes = Array.from(block.querySelectorAll(optSelector)).filter(el => {
                    if (el.getBoundingClientRect().height === 0) return false;
                    let style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    let txt = (el.innerText || '').trim();
                    if (!txt || txt.length > 120) return false;
                    let cls = (el.className || '').toLowerCase();
                    if (cls.includes('btn') && !cls.includes('option')) return false;
                    if (el.closest('.special-options-as-buttons, [data-testid*="special-option"], [data-cy="noopinion"]')) return false;
                    return true;
                });

                let leafOptions = optNodes.filter(c => !optNodes.some(other => other !== c && c.contains(other)));

                if (leafOptions.length < 2) {
                    let generic = Array.from(block.querySelectorAll('button:not([class*="notSure"]), [role="radio"], [role="checkbox"], [role="button"], div[class*="radio"], div[class*="Radio"], div[class*="option"], div[class*="Option"], div[class*="answer"], div[class*="Answer"], div[class*="choice"], div[class*="Choice"]')).filter(el => {
                        if (el.getBoundingClientRect().height === 0) return false;
                        let style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0' || el.disabled) return false;
                        if (el.closest('.special-options-as-buttons, [data-testid*="special-option"], [data-cy="noopinion"]')) return false;
                        let txt = (el.innerText || '').trim().toLowerCase();
                        if (!txt || txt.length > 100) return false;
                        let kws = ['далее', 'вперед', 'продолжить', 'начать', 'старт', 'получить', 'назад', 'затрудняюсь'];
                        if (kws.some(kw => txt === kw || txt.includes(kw))) return false;
                        return true;
                    });
                    leafOptions = generic.filter(c => !generic.some(other => other !== c && c.contains(other)));
                }

                let opts = leafOptions.map((node, idx) => {
                    let directText = (node.innerText || '').trim();
                    let cleanDirect = directText.replace(/^\\d+[\\.\\)]\\s+/, '').replace(/^\\d+\\s+-\\s+/, '').trim();

                    let attrCandidate = '';
                    for (let el of [node, ...node.querySelectorAll('*')]) {
                        let val = el.getAttribute('data-name') || el.getAttribute('data-title') || el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('data-template') || '';
                        val = val.trim();
                        if (val.length > 1 && !/^[0-9a-f]{1,4}$/i.test(val) && !val.toLowerCase().startsWith('http')) {
                            attrCandidate = val;
                            break;
                        }
                    }

                    let isTextGarbage = !cleanDirect || /^[0-9a-f]{1,3}$/i.test(cleanDirect);
                    let finalName = attrCandidate ? attrCandidate : (!isTextGarbage ? cleanDirect : (directText || `Вариант ${idx + 1}`));
                    return {index: idx, text: finalName};
                });

                let isMulti = block.querySelector('input[type="checkbox"], li[data-question-type="CheckBox"], svg[class*="check"]') !== null || (block.innerText || '').toLowerCase().includes('все подходящие');

                result.push({
                    block_idx: bIdx,
                    is_answered: isAnswered,
                    question_text: qTitle,
                    options: opts,
                    is_multi: isMulti
                });
            });

            return result;
        }""")

    async def process_step(self, page: Page, body_lower: str) -> bool:
        try:
            await page.wait_for_function("""() => {
                let roots = document.querySelectorAll('#root, #app, #__next, main, .main, .pythia-surveys-root');
                for (let r of roots) {
                    if (r.innerHTML.trim() === '') return false;
                }
                return document.body.innerText.trim().length > 10 || document.querySelectorAll('button, input').length > 0;
            }""", timeout=6000)
            await asyncio.sleep(0.4)
        except:
            pass

        await self._capture_page_context(page)

        # Проверка на экран выбора опросов (Хаб Survstat / Router-Client)
        if "router-client.survstat" in page.url or (await page.query_selector("[class*='SurveyLinksPage'], [class*='SurveyLink_surveyLink']")) is not None:
            from engines.js_snippets import JS_HANDLE_SURVEY_HUB
            res = await page.evaluate(JS_HANDLE_SURVEY_HUB)
            if res and res.get("found"):
                print(f"\n[🎯] [CLOUDSURVEY] Выбран опрос в хабе: «{res.get('text', '')}»")
                await human_sleep(2.0, 3.5)
                return True
            elif res and res.get("action") == "back_to_cabinet":
                await human_sleep(2.0, 3.5)
                return True

        has_demog = await page.evaluate(JS_CHECK_DEMOGRAPHICS)
        if has_demog:
            if await self.handle_composite_demographics(page):
                await human_sleep(2.0, 3.0)
                await self.click_next(page)
                return True

        is_city_question = await page.evaluate("""() => {
            let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"])'));
            let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;
            let txt = (active.innerText || '').toLowerCase();
            let hasCityInput = active.querySelectorAll('input[placeholder*="списка"], input[placeholder*="город"], input[placeholder*="Город"], input[placeholder*="Выберите"], input[id*="city"], div.ComboBox, div.combobox-container, div[class*="select"], div[class*="Select"], input[type="text"], input:not([type])').length > 0;
            return (txt.includes('город') || txt.includes('проживаете') || txt.includes('живете') || txt.includes('населенный пункт')) && hasCityInput;
        }""")

        if is_city_question:
            if await self.handle_combobox_city(page):
                await human_sleep(1.0, 1.5)
                await self.click_next(page)
                return True

        if await self.handle_info_screen(page):
            await human_sleep(1.5, 2.5)
            return True

        if await self.handle_progressive_blocks(page):
            await human_sleep(1.5, 2.5)
            return True

        if await self.handle_open_text_blocks(page):
            return True

        # ДИНАМИЧЕСКИЙ ЦИКЛ ОБРАБОТКИ ВОПРОСОВ (ОБЫЧНЫЕ + МАТРИЦЫ)
        answered_anything = False

        for cascade_round in range(12):
            await self._capture_page_context(page)

            # 1. Сначала обрабатываем таблицы / матрицы
            if await self.handle_matrix_tables(page):
                answered_anything = True
                await asyncio.sleep(0.6)

            # 2. Затем обычные блоки
            blocks_data = await self._get_blocks_data(page)
            unanswered = [b for b in blocks_data if not b["is_answered"] and b["options"]]

            if not unanswered and not (await page.evaluate("""() => {
                let unansRows = Array.from(document.querySelectorAll('.question-table__rows > [role="row"], div[class*="question-table__row-"]')).filter(r => {
                    let inps = Array.from(r.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                    return inps.length > 0 && !inps.some(i => i.checked);
                });
                return unansRows.length > 0;
            }""")):
                # Все вопросы (и обычные, и матричные) на странице отвечены
                break

            for b in unanswered:
                q_text = b["question_text"] or await self.extract_question_text(page)
                opts_texts = [o["text"] for o in b["options"]]
                is_multi = b["is_multi"]
                b_idx = b["block_idx"]

                print("\n" + "=" * 60)
                try:
                    self.brain.stats['total_answered'] += 1
                    print(f"[№ {self.brain.stats['total_answered']}] ВОПРОС [{b_idx + 1}/{len(blocks_data)}]: {q_text}")
                except Exception:
                    print(f"[?] ВОПРОС [{b_idx + 1}/{len(blocks_data)}]: {q_text}")

                print(f"[i] ТИП: {'Множественный выбор' if is_multi else 'Одиночный выбор'}")
                print(f"[*] ВСЕГО ВАРИАНТОВ: {len(opts_texts)}")
                for idx, text in enumerate(opts_texts[:15]):
                    print(f"    [{idx}] {text}")

                decision = self.brain.decide(q_text, opts_texts, is_multi)

                if is_multi and len(decision.selected_indices) > 4 and not any(
                        w in q_text.lower() for w in ["все варианты", "все подходящие"]):
                    decision.selected_indices = decision.selected_indices[:4]

                decision = self._apply_alternative_logic(opts_texts, decision, is_multi, q_key=f"cloud_b_{b_idx}")

                selected_names = [opts_texts[i] for i in decision.selected_indices if i < len(opts_texts)]
                print(
                    f"[LLM] ВЫБРАНО ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_names[:8]}")
                print(f"[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)

                for opt_idx in decision.selected_indices:
                    await page.evaluate("""({bIdx, optIdx}) => {
                        let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"]), .survey-page, .survey-block, .page-content'));
                        let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;

                        let blockSelectors = [
                            'fieldset.question:not(.question_type_table):not([class*="table"])',
                            '.page__component:not(:has(.question-table))',
                            '.question-container:not(.type_group):not([class*="table"])',
                            '.survey-question', '.question-block', 'div[class*="QuestionContainer"]',
                            'div[class*="styled__BlockStyled"]', 'div[class*="styled_BlockStyled"]'
                        ].join(', ');

                        let candidates = Array.from(active.querySelectorAll(blockSelectors)).filter(el => {
                            if (el.getBoundingClientRect().height === 0) return false;
                            if (el.classList.contains('question_type_table') || el.querySelector('.question-table, table')) return false;
                            let style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                            return el.querySelectorAll('.choice__option, .answer-item, .choice-item, label, button.option__QmiJR, input[type="radio"], input[type="checkbox"], button[class*="button"]').length >= 2;
                        });

                        let qBlocks = candidates.filter(b => !candidates.some(other => other !== b && b.contains(other)));
                        if (qBlocks.length === 0) qBlocks = [active];

                        let targetBlock = qBlocks[bIdx] || active;

                        let optSelector = [
                            'div.choice__option', 'div[class*="styled__AnswerStyled"]', 'div[class*="scale-item"]',
                            'div[class*="scale-answer"]', 'div[class*="AnswerRow"]', 'div[class*="answer-row"]',
                            'li.choice-item', 'div.choice-item', 'div[class*="LogoItem"]', 'div[class*="GridItem"]',
                            'label.option-label', '.answer-item', '.scale-item', '.LogoItem', '.grid__cell',
                            'button.option__QmiJR', 'label.question-list__item',
                            '[data-testid*="respondent.choice.option"]', '[data-testid*="choice.option"]',
                            '[data-testid*="value"]', '.choice-options .radio', '.choice-option', '.choice-options .checkbox'
                        ].join(', ');

                        let optNodes = Array.from(targetBlock.querySelectorAll(optSelector)).filter(el => {
                            if (el.getBoundingClientRect().height === 0) return false;
                            let style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                            if (el.closest('.special-options-as-buttons, [data-testid*="special-option"], [data-cy="noopinion"]')) return false;
                            return true;
                        });

                        let leafOptions = optNodes.filter(c => !optNodes.some(other => other !== c && c.contains(other)));

                        if (leafOptions.length < 2) {
                            let generic = Array.from(targetBlock.querySelectorAll('button:not([class*="notSure"]), [role="radio"], [role="checkbox"], [role="button"], div[class*="radio"], div[class*="Radio"], div[class*="option"], div[class*="Option"], div[class*="answer"], div[class*="Answer"], div[class*="choice"], div[class*="Choice"]')).filter(el => {
                                if (el.getBoundingClientRect().height === 0) return false;
                                let style = window.getComputedStyle(el);
                                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0' || el.disabled) return false;
                                if (el.closest('.special-options-as-buttons, [data-testid*="special-option"], [data-cy="noopinion"]')) return false;
                                let txt = (el.innerText || '').trim().toLowerCase();
                                if (!txt || txt.length > 100) return false;
                                let kws = ['далее', 'вперед', 'продолжить', 'начать', 'старт', 'получить', 'назад', 'затрудняюсь'];
                                if (kws.some(kw => txt === kw || txt.includes(kw))) return false;
                                return true;
                            });
                            leafOptions = generic.filter(c => !generic.some(other => other !== c && c.contains(other)));
                        }

                        let target = leafOptions[optIdx];
                        if (!target) return;

                        target.scrollIntoView({behavior: 'smooth', block: 'center'});
                        let clickable = target.tagName === 'LABEL' ? target : (target.querySelector('input, label, [class*="label"], [class*="control"], [class*="radiobutton"], [role="radio"], [role="checkbox"]') || target);
                        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                            target.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                            if (clickable !== target) {
                                clickable.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                            }
                        });
                        if (clickable.click) clickable.click();
                        if (target !== clickable && target.click) target.click();
                        let inp = target.querySelector('input') || (target.tagName === 'INPUT' ? target : null);
                        if (inp && !inp.checked) {
                            try {
                                let tracker = inp._valueTracker;
                                if (tracker) tracker.setValue('');
                                let proto = Object.getPrototypeOf(inp);
                                let desc = Object.getOwnPropertyDescriptor(proto, 'checked') || Object.getOwnPropertyDescriptor(inp, 'checked');
                                if (desc && desc.set) desc.set.call(inp, true);
                                else inp.checked = true;
                            } catch(e) {}
                            inp.checked = true;
                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    }""", {"bIdx": b_idx, "optIdx": opt_idx})
                    await human_sleep(0.3, 0.5)

                answered_anything = True

            await asyncio.sleep(0.6)

        setattr(state, "force_alternative", False)

        if answered_anything:
            await human_sleep(0.6, 1.2)
            if "oprosso" in page.url.lower():
                try:
                    arrow = page.locator("div[class*='arrow__'], svg[class*='arrow_castom']").first
                    if await arrow.is_visible():
                        await arrow.click(force=True)
                    else:
                        await page.keyboard.press("ArrowDown")
                except Exception:
                    pass
            await self.click_next(page)
            return True

        print("[i] Все вопросы на странице отвечены. Нажимаем Далее/Enter...")
        await self.click_next(page)
        return True