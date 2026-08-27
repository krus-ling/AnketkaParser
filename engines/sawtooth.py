import asyncio
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep
from bot_state import state


class SawtoothEngine(BaseSurveyEngine):
    async def click_next(self, page: Page) -> bool:
        """Нажатие кнопки Далее на платформе Sawtooth Software."""
        await state.wait_debug_confirm()

        try:
            await self.sync_memory_from_dom(page)
        except Exception:
            pass

        selectors = [
            "#next_button",
            "input[name='sys_next_button']",
            "input[type='submit'][value*='Далее']",
            ".submit_button",
            "text='Далее >>'"
        ]

        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(force=True)
                        print(f"[i] [SAWTOOTH] Нажата кнопка (найдено по: {sel})")
                        return True
            except Exception:
                continue

        return await super().click_next(page)

    async def process_step(self, page: Page, body_lower: str) -> bool:
        total_handled = 0

        for attempt in range(6):
            try:
                data = await page.evaluate("""() => {
                    function isVisible(el) {
                        if (!el || el.nodeType !== 1) return false;
                        if (el.offsetParent === null) return false;
                        let style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none') return false;
                        let rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }

                    function getCleanText(el) {
                        if (!el) return "";
                        let ru = el.querySelector('span._ru, ._ru');
                        if (ru) {
                            let t = (ru.innerText || ru.textContent || "").trim();
                            if (t) return t;
                        }
                        let img = el.querySelector('img');
                        if (img) {
                            let t = img.getAttribute('title') || img.getAttribute('data-template') || img.getAttribute('alt') || "";
                            if (t) return t.trim();
                        }
                        let clone = el.cloneNode(true);
                        Array.from(clone.querySelectorAll('._uk, ._kz, ._tj, ._ge, ._ar, ._md, ._az, ._uz, ._kg')).forEach(s => s.remove());
                        return (clone.innerText || clone.textContent || "").replace(/\\s+/g, ' ').trim();
                    }

                    // 1. Полный сбор заголовков
                    let headerEls = Array.from(document.querySelectorAll('.header1, .header2, .question_text, .question_title')).filter(isVisible);
                    let qText = headerEls.map(getCleanText).filter(Boolean).join(' ');
                    if (!qText) qText = document.title || "Вопрос";

                    // 2. ВЫПАДАЮЩИЕ СПИСКИ (в т.ч. скрытые через Select2)
                    let selectEls = Array.from(document.querySelectorAll('select')).filter(s => {
                        if (s.disabled) return false;
                        if (!isVisible(s) && !s.classList.contains('select2-hidden-accessible')) return false;

                        let selectedOpts = Array.from(s.selectedOptions).filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'));
                        return selectedOpts.length === 0;
                    });

                    if (selectEls.length > 0) {
                        let selectEl = selectEls[0];
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

                    // 3. Варианты ответа (чекбоксы / радиокнопки)
                    let inputs = Array.from(document.querySelectorAll('.question_body input[type="radio"], .question_body input[type="checkbox"]'));
                    if (inputs.length === 0) {
                        inputs = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                    }

                    let choiceInputs = inputs.filter(inp => {
                        let n = inp.name || "";
                        let i = inp.id || "";
                        return !n.startsWith('sys_') && !n.startsWith('hid_') && !i.includes('_other') && !n.includes('_other');
                    });

                    if (choiceInputs.length > 0) {
                        let isAnswered = choiceInputs.some(inp => inp.checked);

                        if (!isAnswered) {
                            let isMulti = choiceInputs.some(inp => inp.type === 'checkbox');
                            let options = choiceInputs.map((inp, i) => {
                                let text = "";
                                // Безопасное получение label через нативное свойство
                                let label = (inp.labels && inp.labels.length > 0) ? inp.labels[0] : null;
                                if (label) {
                                    text = getCleanText(label);
                                }
                                if (!text) {
                                    let row = inp.closest('.clickable, .response_row, td, tr');
                                    if (row) text = getCleanText(row);
                                }
                                return text || `Вариант ${i + 1}`;
                            });
                            return {targetType: 'choices', questionText: qText, options: options, isMulti: isMulti};
                        }
                        return {targetType: 'done_or_info', questionText: qText, options: []};
                    }

                    // 4. Открытый ввод текста
                    let textInputs = Array.from(document.querySelectorAll('input[type="text"]:not([readonly]), textarea')).filter(i => {
                        if (!isVisible(i)) return false;
                        let idStr = i.id || "";
                        let nameStr = i.name || "";
                        if (idStr.includes('_other') || nameStr.includes('_other')) return false;
                        return i.value.trim() === '';
                    });

                    if (textInputs.length > 0) {
                        let inp = textInputs[0];
                        inp.setAttribute('data-bot-target', 'true');
                        return {targetType: 'text', questionText: qText, options: []};
                    }

                    return {targetType: 'done_or_info', questionText: qText, options: []};
                }""")
            except Exception as e:
                # Если контекст разрушен из-за навигации, просто ждем 1 сек и пробуем снова
                await asyncio.sleep(1.0)
                continue

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

                    try:
                        await page.evaluate("""(text) => {
                            let inp = document.querySelector('[data-bot-target="true"]');
                            if (inp) {
                                inp.focus();
                                inp.value = text;
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                inp.removeAttribute('data-bot-target');
                            }
                        }""", ans_text)
                    except Exception:
                        pass
                    total_handled += 1
                    await human_sleep(0.5, 1.0)
                else:
                    print("[!] ВЫБРАНО: -> НИЧЕГО (Ожидание ручного действия)")
                    try:
                        await page.evaluate("""() => {
                            let inp = document.querySelector('[data-bot-target="true"]');
                            if (inp) inp.removeAttribute('data-bot-target');
                        }""")
                    except Exception:
                        pass
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
                        try:
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
                        except Exception:
                            pass
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

                    for sel_idx in chosen_indices:
                        try:
                            await page.evaluate("""(idx) => {
                                let inputs = Array.from(document.querySelectorAll('.question_body input[type="radio"], .question_body input[type="checkbox"]'));
                                if (inputs.length === 0) inputs = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]'));

                                let choiceInputs = inputs.filter(inp => {
                                    let n = inp.name || "";
                                    let i = inp.id || "";
                                    return !n.startsWith('sys_') && !n.startsWith('hid_') && !i.includes('_other') && !n.includes('_other');
                                });

                                if (choiceInputs[idx]) {
                                    let targetInput = choiceInputs[idx];
                                    let targetId = targetInput.id || "";
                                    let graph = targetId ? document.getElementById(targetId + '_graphical') : null;
                                    let label = (targetInput.labels && targetInput.labels.length > 0) ? targetInput.labels[0] : null;
                                    let row = targetInput.closest('.clickable, tr');

                                    if (!targetInput.checked) {
                                        if (graph && graph.offsetParent !== null) {
                                            graph.click();
                                        } else if (label && label.offsetParent !== null) {
                                            label.click();
                                        } else if (row) {
                                            row.click();
                                        } else {
                                            targetInput.click();
                                        }

                                        if (!targetInput.checked) {
                                            targetInput.checked = true;
                                            targetInput.dispatchEvent(new Event('change', {bubbles: true}));
                                            if (graph) {
                                                graph.classList.add(targetInput.type === 'checkbox' ? 'checkbox_selected' : 'radiobox_selected');
                                            }
                                        }
                                    }
                                }
                            }""", sel_idx)
                        except Exception:
                            pass
                        await human_sleep(0.3, 0.6)

                    total_handled += 1
                    break

        if total_handled > 0 or (data and data.get("targetType") == "done_or_info"):
            await human_sleep(1.0, 1.5)
            await self.click_next(page)
            return True

        return False