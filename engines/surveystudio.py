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

        selectors = [
            "#processingGoForwardBtn",
            ".next-button",
            "text='ДАЛЕЕ'",
            "text='Далее'",
            "text='НАЧАТЬ'",
            "text='Начать'"
        ]

        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(force=True)
                        print(f"[i] [SURVEY-STUDIO] Нажата кнопка (найдено по: {sel})")
                        return True
            except Exception:
                continue

        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:
        total_handled = 0

        for _ in range(25):
            matrix_data = await page.evaluate("""() => {
                let isMatrix = document.querySelector('#ssDesktopTable, .ss-desktop-table, .ss-table-body-container, .ss-answers-table-singlechoice, .ss-answers-table-multiplechoice') !== null;
                if (!isMatrix) return null;

                function isVisible(el) {
                    if (!el) return false;
                    let rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                }

                let titles = Array.from(document.querySelectorAll('.question-text, .ss-question-title'));
                let visibleTitle = titles.find(isVisible);
                let qText = visibleTitle ? visibleTitle.innerText.trim() : (document.title || 'Матричный вопрос');

                let bodyRows = Array.from(document.querySelectorAll('#ssDesktopTableBodyContainer .ss-table-row, .ss-table-body-container .ss-table-row, div.ss-table-row')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]'));

                let colHeaders = [];
                if (bodyRows.length > 0) {
                    // Берем инпуты из первой строки
                    let firstRowInputs = Array.from(bodyRows[0].querySelectorAll('input[type="radio"], input[type="checkbox"]'))
                        .filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));

                    // Собираем ячейки заголовка таблицы
                    let headerCells = Array.from(document.querySelectorAll('.ss-table-header .ss-table-cell, thead th, .ss-table-header > div, .ss-desktop-table-header th')).filter(isVisible);

                    // Отсекаем пустой левый верхний угол: берем только последние N ячеек (по числу инпутов)
                    let validHeaders = headerCells.length >= firstRowInputs.length ? headerCells.slice(-firstRowInputs.length) : headerCells;

                    colHeaders = firstRowInputs.map((inp, idx) => {
                        let t = '';

                        // 1. Пытаемся найти привязанный label
                        let label = document.querySelector(`label[for="${inp.id}"]`);
                        if (label && isVisible(label)) t = label.innerText.replace(/\\s+/g, ' ').trim();

                        // 2. Ищем скрытые атрибуты-подсказки SurveyStudio
                        if (!t) t = inp.getAttribute('data-title') || inp.getAttribute('title') || inp.getAttribute('aria-label') || '';

                        // 3. Достаем текст из шапки таблицы
                        if (!t && validHeaders[idx]) {
                            t = validHeaders[idx].innerText.replace(/\\s+/g, ' ').trim();
                        }

                        // Сокращаем слишком длинные оценки
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
                        let rowInputs = Array.from(rEl.querySelectorAll('input[type="radio"], input[type="checkbox"]'))
                            .filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));

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

                return {
                    qText: qText,
                    colHeaders: colHeaders,
                    rows: rows
                };
            }""")

            if matrix_data and matrix_data["rows"]:
                unanswered = [r for r in matrix_data["rows"] if not r["isAnswered"]]
                if not unanswered:
                    break

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
                            let inputs = Array.from(row.querySelectorAll('input[type="radio"], input[type="checkbox"]'))
                                .filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));

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

                break

            # 2. ОБЫЧНЫЕ ВОПРОСЫ
            data = await page.evaluate("""() => {
                function isVisible(el) {
                    if (!el) return false;
                    let rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                }

                function getTitle() {
                    let titles = Array.from(document.querySelectorAll('.question-text, .ss-question-title'));
                    let visibleTitle = titles.find(isVisible);
                    return visibleTitle ? visibleTitle.innerText.trim() : (document.title || '');
                }

                let qText = getTitle();
                let containerBlocks = Array.from(document.querySelectorAll('.question-content, .ss-answers'));
                let container = containerBlocks.find(isVisible) || document;

                // --- ПОДДЕРЖКА ВЫПАДАЮЩИХ СПИСКОВ (Select2) ---
                let selectEl = Array.from(container.querySelectorAll('select')).find(s => {
                    if (s.disabled) return false;
                    if (!isVisible(s) && !s.classList.contains('ss-search-select') && !s.classList.contains('select2-hidden-accessible')) return false;
                    let selectedOpts = Array.from(s.selectedOptions).filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'));
                    return selectedOpts.length === 0;
                });

                if (selectEl) {
                    let options = Array.from(selectEl.querySelectorAll('option'))
                        .filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'))
                        .map(o => o.innerText.replace(/\\s+/g, ' ').trim());

                    if (options.length > 0) {
                        selectEl.setAttribute('data-bot-target-select', 'true');
                        return {
                            targetType: 'select',
                            questionText: qText,
                            options: options,
                            isMulti: selectEl.multiple
                        };
                    }
                }

                // --- ТЕКСТОВЫЕ ВОПРОСЫ ---
                let textInputs = Array.from(container.querySelectorAll('input[type="text"]:not([readonly]), textarea, input[type="number"]')).filter(i => {
                    if (!isVisible(i)) return false;
                    let parent = i.parentElement;
                    for (let k = 0; k < 4; k++) {
                        if (!parent) break;
                        if (parent.querySelector('input[type="radio"], input[type="checkbox"]')) return false;
                        parent = parent.parentElement;
                    }
                    return i.value.trim() === '';
                });

                if (textInputs.length > 0) {
                    let inp = textInputs[0];
                    inp.setAttribute('data-bot-target', 'true');
                    return {targetType: 'text', questionText: qText, options: []};
                }

                // --- ВАРИАНТЫ ОТВЕТА (Радио/Галочки) ---
                let choiceRows = Array.from(container.querySelectorAll('.grid__cell, tr')).filter(r => {
                    return isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]') !== null;
                });

                if (choiceRows.length === 0) {
                    choiceRows = Array.from(container.querySelectorAll('label')).filter(r => {
                        return isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]') !== null;
                    });
                }

                if (choiceRows.length > 0) {
                    let isAnswered = choiceRows.some(r => {
                        let inp = r.querySelector('input[type="radio"], input[type="checkbox"]');
                        return inp && inp.checked;
                    });

                    if (!isAnswered) {
                        let isMulti = choiceRows.some(r => r.querySelector('input[type="checkbox"]') !== null);
                        let options = choiceRows.map((r, i) => {
                            let tEl = r.querySelector('.answer-text, .text, span');
                            let t = tEl ? tEl.innerText.trim() : "";

                            let inpField = r.querySelector('input[type="text"]');
                            if (inpField) {
                                if (inpField.placeholder) t = "Свой вариант: " + inpField.placeholder;
                                else t = "Свой вариант";
                            }
                            return t || `Вариант ответа ${i + 1}`;
                        });
                        return {targetType: 'choices', questionText: qText, options: options, isMulti: isMulti};
                    }
                }

                return {targetType: 'done_or_info', questionText: qText, options: []};
            }""")

            if not data:
                break

            if data["targetType"] == "done_or_info":
                if total_handled == 0 and data["questionText"]:
                    print(f"\n📄 [ИНФО-ЭКРАН]: {data['questionText']}")
                break

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
                else:
                    print("[!] ВЫБРАНО: -> НИЧЕГО (Ожидание ручного действия)")
                    await page.evaluate("""() => {
                        let inp = document.querySelector('[data-bot-target="true"]');
                        if (inp) inp.removeAttribute('data-bot-target');
                    }""")
                    break

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
                                    if (window.jQuery) {
                                        window.jQuery(sel).trigger('change');
                                    }
                                }
                                sel.removeAttribute('data-bot-target-select');
                            }
                        }""", sel_idx)
                        await human_sleep(0.3, 0.6)

                    total_handled += 1
                    break
                else:
                    print("[LLM] ВЫБРАНО: -> НИЧЕГО (Ожидание выбора в GUI)")
                    print("=" * 60)
                    break

            elif data["targetType"] == "choices":
                print("\n" + "=" * 60)
                print(f"[?] ВОПРОС: {data['questionText']}")
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

                    for idx_count, sel_idx in enumerate(chosen_indices):
                        await page.evaluate("""({idx}) => {
                            function isVisible(el) {
                                if (!el) return false;
                                if (el.offsetParent === null) return false;
                                let style = window.getComputedStyle(el);
                                if (style.visibility === 'hidden' || style.opacity === '0') return false;
                                let rect = el.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            }

                            let containerBlocks = Array.from(document.querySelectorAll('.question-content, .ss-answers')).filter(isVisible);
                            let container = containerBlocks.length > 0 ? containerBlocks[0] : document.body;

                            let rows = Array.from(container.querySelectorAll('.grid__cell, tr')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]'));
                            if (rows.length === 0) rows = Array.from(container.querySelectorAll('label')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]'));

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
                    break
                else:
                    print("[LLM] ВЫБРАНО: -> НИЧЕГО (Ожидание выбора в GUI)")
                    print("=" * 60)
                    break

        if total_handled > 0 or data.get("targetType") == "done_or_info":
            await human_sleep(1.0, 1.5)
            await self.click_next(page)
            return True

        return False