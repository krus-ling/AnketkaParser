import asyncio
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep
from bot_state import state


class SurveyStudioEngine(BaseSurveyEngine):

    async def click_next(self, page: Page) -> bool:
        """Нажатие кнопки Далее на платформе SurveyStudio."""
        await state.wait_debug_confirm()
        try:
            await self.sync_memory_from_dom(page)
        except Exception:
            pass

        # Используем надежные локаторы Playwright (без невалидных кавычек в text=)
        selectors = [
            "#processingGoForwardBtn",
            ".next-button",
            "button:has-text('ДАЛЕЕ')",
            "button:has-text('Далее')",
            "button:has-text('НАЧАТЬ')",
            "button:has-text('Начать')",
            "div:has-text('ДАЛЕЕ')",
            "div:has-text('Далее')",
            "text=ДАЛЕЕ",
            "text=Далее"
        ]

        for sel in selectors:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=1000):
                    await locator.scroll_into_view_if_needed()
                    await locator.click(force=True)
                    print(f"[i] [SURVEY-STUDIO] Нажата кнопка (найдено по: {sel})")
                    return True
            except Exception:
                continue

        # Fallback: поиск по всем кнопкам и div с ключевыми словами через JS
        try:
            btn_handle = await page.evaluate_handle("""() => {
                let kws = ['далее', 'вперед', 'продолжить', 'начать'];
                let candidates = Array.from(document.querySelectorAll('button, div, span, a')).filter(el => {
                    if (el.offsetParent === null) return false;
                    let style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    let txt = (el.innerText || el.value || '').trim().toLowerCase();
                    if (txt.length === 0 || txt.length > 50) return false;
                    let isBtn = el.tagName === 'BUTTON' || el.tagName === 'A' || (el.className || '').toLowerCase().includes('btn') || (el.className || '').toLowerCase().includes('button');
                    let hasKw = kws.some(kw => txt === kw || txt.includes(kw));
                    return isBtn && hasKw;
                });
                if (candidates.length > 0) {
                    // Сортируем по количеству вложенных элементов, чтобы выбрать самый конкретный (листья дерева)
                    candidates.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
                    return candidates[0];
                }
                return null;
            }""")

            if not await btn_handle.evaluate("el => !el"):
                await btn_handle.scroll_into_view_if_needed()
                # Эмуляция полного цикла событий мыши для React/Vue
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
        total_handled = 0

        # 1. ПРОВЕРКА МАТРИЦ (Таблицы)
        matrix_data = await page.evaluate("""() => {
            let isMatrix = document.querySelector('#ssDesktopTable, .ss-desktop-table, .ss-table-body-container, .ss-answers-table-singlechoice, .ss-answers-table-multiplechoice') !== null;
            if (!isMatrix) return null;

            function isVisible(el) {
                if (!el) return false;
                let rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden' && window.getComputedStyle(el).display !== 'none';
            }

            let titles = Array.from(document.querySelectorAll('.question-text, .ss-question-title, h2, h3'));
            let visibleTitle = titles.find(isVisible);
            let qText = visibleTitle ? visibleTitle.innerText.trim() : 'Матричный вопрос';

            let bodyRows = Array.from(document.querySelectorAll('#ssDesktopTableBodyContainer .ss-table-row, .ss-table-body-container .ss-table-row, div.ss-table-row')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]'));
            let colHeaders = [];

            if (bodyRows.length > 0) {
                let firstRowInputs = Array.from(bodyRows[0].querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));
                let headerCells = Array.from(document.querySelectorAll('.ss-table-header .ss-table-cell, thead th, .ss-table-header > div, .ss-desktop-table-header th')).filter(isVisible);
                let validHeaders = headerCells.length >= firstRowInputs.length ? headerCells.slice(-firstRowInputs.length) : headerCells;

                colHeaders = firstRowInputs.map((inp, idx) => {
                    let t = '';
                    let label = document.querySelector(`label[for="${inp.id}"]`);
                    if (label && isVisible(label)) t = label.innerText.replace(/\\s+/g, ' ').trim();
                    if (!t) t = inp.getAttribute('data-title') || inp.getAttribute('title') || inp.getAttribute('aria-label') || '';
                    if (!t && validHeaders[idx]) t = validHeaders[idx].innerText.replace(/\\s+/g, ' ').trim();
                    if (t && t.length > 40) {
                        let matchNum = t.match(/^[0-9\\.]+/);
                        t = matchNum ? matchNum[0] + " (оценка)" : t.substring(0, 35) + "...";
                    }
                    return t && !t.includes('ОДИН ОТВЕТ') ? t : `Вариант ${idx + 1}`;
                });
            }

            let leftRows = Array.from(document.querySelectorAll('.ss-first-table-container .ss-table-row, .ss-first-table-container div[data-row-code], .ss-first-table-container td, tbody th')).filter(el => isVisible(el) && el.innerText.trim().length > 0);
            let rows = [];
            if (bodyRows.length > 0) {
                bodyRows.forEach((rEl, i) => {
                    let rowInputs = Array.from(rEl.querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));
                    if (rowInputs.length === 0) return;
                    let isAnswered = rowInputs.some(inp => inp.checked);
                    let titleEl = leftRows[i] || rEl.querySelector('.ss-table-row-title, .ss-row-title, td:first-child, .title, label');
                    let title = titleEl ? titleEl.innerText.replace(/\\s+/g, ' ').trim() : `Строка ${i + 1}`;
                    rows.push({
                        rowIndex: i,
                        title: title,
                        isAnswered: isAnswered,
                        inputsCount: rowInputs.length,
                        isMulti: rEl.querySelector('input[type="checkbox"]') !== null
                    });
                });
            }
            return {qText: qText, colHeaders: colHeaders, rows: rows};
        }""")

        if matrix_data and matrix_data["rows"]:
            unanswered = [r for r in matrix_data["rows"] if not r["isAnswered"]]
            if not unanswered:
                pass  # Проваливаемся к обычной проверке, вдруг там еще что-то есть
            else:
                col_options = matrix_data["colHeaders"]
                print("\n" + "=" * 60)
                print(f"📊 [ТАБЛИЦА / МАТРИЦА]: {matrix_data['qText']}")
                print(f"[*] Всего строк: {len(matrix_data['rows'])} | Осталось заполнить: {len(unanswered)}")
                print(f"[*] Варианты колонок ({len(col_options)}): {col_options}")
                print("=" * 60)
                for r in unanswered:
                    row_q = f"{matrix_data['qText']} -> {r['title']}"
                    current_options = col_options[:r["inputsCount"]] if len(col_options) >= r["inputsCount"] else [
                        f"Вариант {k + 1}" for k in range(r["inputsCount"])]
                    decision = self.brain.decide(row_q, current_options, is_multiselect=r["isMulti"])
                    chosen_idx = decision.selected_indices[0] if decision.selected_indices and \
                                                                 decision.selected_indices[0] < len(
                        current_options) else len(current_options) // 2
                    chosen_text = current_options[chosen_idx]
                    print(f"  🔹 {r['title']} ➔ [{chosen_text}] (Логика: {decision.reasoning})")
                    await page.evaluate("""({rowIndex, colIdx}) => {
                        function isVisible(el) {
                            return el.getBoundingClientRect().height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                        }

                        let bodyRows = Array.from(document.querySelectorAll('#ssDesktopTableBodyContainer .ss-table-row, .ss-table-body-container .ss-table-row, div.ss-table-row')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]'));
                        if (bodyRows[rowIndex]) {
                            let row = bodyRows[rowIndex];
                            let inputs = Array.from(row.querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));
                            if (inputs[colIdx]) {
                                let targetInput = inputs[colIdx];
                                let clickable = targetInput.closest('label') || targetInput.closest('.pretty') || targetInput;
                                clickable.scrollIntoView({behavior: 'smooth', block: 'center'});
                                clickable.click();
                                targetInput.checked = true;
                                targetInput.dispatchEvent(new Event('change', {bubbles: true}));
                            }
                        }
                    }""", {"rowIndex": r["rowIndex"], "colIdx": chosen_idx})
                    total_handled += 1
                    await human_sleep(0.1, 0.3)
                await human_sleep(1.0, 1.5)
                await self.click_next(page)
                return True

        # 2. ОБЫЧНЫЕ ВОПРОСЫ (Исправленный парсер)
        data = await page.evaluate("""() => {
            function isVisible(el) {
                if (!el) return false;
                let rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden' && window.getComputedStyle(el).display !== 'none';
            }

            // 1. Получаем текст вопроса
            let qText = "";
            let titles = Array.from(document.querySelectorAll('.question-text, .ss-question-title, h2, h3, h4, .header1, .header2'));
            for (let t of titles) {
                if (isVisible(t)) {
                    qText = t.innerText.replace(/\\s+/g, ' ').trim();
                    if (qText.length > 5) break;
                }
            }
            if (!qText) qText = document.title || "Неизвестный вопрос";

            let container = document.querySelector('.question-content, .ss-answers, .step.active') || document.body;

            // 2. ПРОВЕРКА ТЕКСТОВЫХ ПОЛЕЙ (Приоритет выше, чем у селектов, чтобы не путать "сумму" с выпадающим списком)
            let textInputs = Array.from(container.querySelectorAll('input[type="text"], input[type="number"], input[inputmode="numeric"], textarea')).filter(i => {
                if (!isVisible(i)) return false;
                if (i.id.includes('_other') || i.name.includes('_other')) return false;
                let parent = i.parentElement;
                for (let k = 0; k < 3; k++) {
                    if (parent && parent.querySelector('input[type="radio"], input[type="checkbox"]')) return false;
                    parent = parent.parentElement;
                }
                return i.value.trim() === '';
            });

            if (textInputs.length > 0) {
                textInputs[0].setAttribute('data-bot-target', 'true');
                return {targetType: 'text', questionText: qText, options: []};
            }

            // 3. ПРОВЕРКА ВЫПАДАЮЩИХ СПИСКОВ (Select)
            let selectEl = Array.from(container.querySelectorAll('select')).find(s => {
                if (s.disabled) return false;
                if (!isVisible(s) && !s.classList.contains('select2-hidden-accessible') && !s.classList.contains('ss-search-select')) return false;
                let selectedOpts = Array.from(s.selectedOptions).filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'));
                return selectedOpts.length === 0; // Еще не отвечено
            });

            if (selectEl) {
                let options = Array.from(selectEl.querySelectorAll('option'))
                    .filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'))
                    .map(o => o.innerText.replace(/\\s+/g, ' ').trim());
                if (options.length > 0) {
                    selectEl.setAttribute('data-bot-target-select', 'true');
                    return {targetType: 'select', questionText: qText, options: options, isMulti: selectEl.multiple};
                }
            }

            // 4. ПРОВЕРКА ВАРИАНТОВ ОТВЕТА (Radio/Checkbox)
            let choiceRows = Array.from(container.querySelectorAll('label, .grid__cell, tr, .ss-choice-item')).filter(r => {
                return isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]') !== null;
            });

            // Оставляем только самые глубокие элементы (убираем родительские обертки, если они тоже попали)
            choiceRows = choiceRows.filter(r => !choiceRows.some(other => other !== r && other.contains(r)));

            if (choiceRows.length >= 2) {
                let isAnswered = choiceRows.some(r => {
                    let inp = r.querySelector('input[type="radio"], input[type="checkbox"]');
                    return inp && inp.checked;
                });

                if (!isAnswered) {
                    let isMulti = choiceRows.some(r => r.querySelector('input[type="checkbox"]') !== null);
                    let options = choiceRows.map((r, i) => {
                        // Надежное получение текста: берем весь текст лейбла/строки и чистим его
                        let t = r.innerText.replace(/\\s+/g, ' ').trim();

                        // Если вдруг текст пустой, ищем вложенные элементы
                        if (!t || t.length < 2) {
                            let label = r.querySelector('label, span, div');
                            if (label) t = label.innerText.replace(/\\s+/g, ' ').trim();
                        }

                        // Проверка на поле "Свой вариант"
                        let inpField = r.querySelector('input[type="text"]');
                        if (inpField) {
                            t = "Свой вариант" + (inpField.placeholder ? ": " + inpField.placeholder : "");
                        }
                        return t || `Вариант ответа ${i + 1}`;
                    });
                    return {targetType: 'choices', questionText: qText, options: options, isMulti: isMulti};
                }
            }

            return {targetType: 'done_or_info', questionText: qText, options: []};
        }""")

        if not data:
            return False

        if data["targetType"] == "done_or_info":
            if total_handled == 0 and data["questionText"]:
                print(f"\n📄 [ИНФО-ЭКРАН]: {data['questionText']}")
            # Если это инфо-экран, просто жмем далее
            if total_handled == 0:
                await human_sleep(1.0, 1.5)
                await self.click_next(page)
                return True
            return False

        elif data["targetType"] == "text":
            print(f"\n[?] ОТКРЫТЫЙ ВОПРОС: {data['questionText']}")
            ans_text = self.brain.answer_open_text(data["questionText"])
            if ans_text:
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                print(f"✍️  [ВВОД]: {ans_text}")
                await page.evaluate("""(text) => {
                    let inp = document.querySelector('[data-bot-target="true"]');
                    if (inp) {
                        inp.focus();
                        if (inp.type === 'number') {
                            text = text.replace(/\\D/g, '');
                            if (!text) text = "1500";
                        }
                        inp.value = text;
                        inp.dispatchEvent(new Event('input', {bubbles: true}));
                        inp.dispatchEvent(new Event('change', {bubbles: true}));
                        inp.removeAttribute('data-bot-target');
                    }
                }""", ans_text)
                total_handled += 1
                await human_sleep(0.5, 1.0)
                await self.click_next(page)
                return True

        elif data["targetType"] == "select":
            print("\n" + "=" * 60)
            print(f"[?] ВЫПАДАЮЩИЙ СПИСОК: {data['questionText']}")
            print(f"[*] ВСЕГО ВАРИАНТОВ: {len(data['options'])}")
            decision = self.brain.decide(data["questionText"], data["options"], data["isMulti"])
            chosen_indices = decision.selected_indices if decision.selected_indices else [0]
            if chosen_indices and len(data['options']) > 0:
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                selected_names = [data["options"][i] for i in chosen_indices if i < len(data["options"])]
                print(f"[ВЫБРАНО ({len(chosen_indices)}): {chosen_indices} -> {selected_names}")
                print(f"[LLM] ЛОГИКА: {decision.reasoning}")
                print("=" * 60)
                for sel_idx in chosen_indices:
                    await page.evaluate("""(idx) => {
                        let sel = document.querySelector('select[data-bot-target-select="true"]');
                        if (sel) {
                            let opts = Array.from(sel.querySelectorAll('option')).filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'));
                            if (opts[idx]) {
                                sel.value = opts[idx].value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                if (window.jQuery) window.jQuery(sel).trigger('change');
                            }
                            sel.removeAttribute('data-bot-target-select');
                        }
                    }""", sel_idx)
                    await human_sleep(0.3, 0.6)
                total_handled += 1
                await self.click_next(page)
                return True

        elif data["targetType"] == "choices":
            print("\n" + "=" * 60)
            print(f"[?] ВОПРОС: {data['questionText']}")
            print(f"[*] ВСЕГО ВАРИАНТОВ: {len(data['options'])}")
            for idx, text in enumerate(data['options']):
                print(f"    [{idx}] {text}")

            decision = self.brain.decide(data["questionText"], data["options"], data["isMulti"])
            chosen_indices = decision.selected_indices if decision.selected_indices else [0]
            if chosen_indices and len(data['options']) > 0:
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                selected_names = [data["options"][i] for i in chosen_indices if i < len(data["options"])]
                print(f"[ВЫБРАНО ({len(chosen_indices)}): {chosen_indices} -> {selected_names}")
                print(f"[LLM] ЛОГИКА: {decision.reasoning}")
                print("=" * 60)
                for sel_idx in chosen_indices:
                    await page.evaluate("""({idx}) => {
                        function isVisible(el) {
                            if (!el) return false;
                            let style = window.getComputedStyle(el);
                            if (style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none') return false;
                            let rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        }

                        let container = document.querySelector('.question-content, .ss-answers, .step.active') || document.body;
                        let rows = Array.from(container.querySelectorAll('label, .grid__cell, tr, .ss-choice-item')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]') !== null);
                        rows = rows.filter(r => !rows.some(other => other !== r && other.contains(r)));

                        if (rows[idx]) {
                            let clickable = rows[idx].querySelector('label') || rows[idx].querySelector('.pretty') || rows[idx];
                            clickable.scrollIntoView({behavior: 'smooth', block: 'center'});
                            clickable.click();
                            let targetInput = rows[idx].querySelector('input[type="radio"], input[type="checkbox"]');
                            if (targetInput && !targetInput.checked) {
                                targetInput.checked = true;
                                targetInput.dispatchEvent(new Event('change', {bubbles: true}));
                            }
                        }
                    }""", {"idx": sel_idx})
                    await human_sleep(0.3, 0.6)
                total_handled += 1
                await self.click_next(page)
                return True

        return False