import asyncio
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep


class ProfiResearchEngine(BaseSurveyEngine):

    async def click_next(self, page: Page) -> bool:
        """Улучшенное нажатие кнопки Далее на платформе ProfiResearch."""
        # Список селекторов от самых точных к самым широким
        selectors = [
            "#next",  # Любой элемент с id="next" (хоть div, хоть button)
            "button[name='goto']",  # Специфичная кнопка ProfiResearch
            ".bg-green",  # Любой элемент с классом bg-green
            ".btn",  # Любой элемент с классом btn
            "text='Далее'",  # ЛЮБОЙ видимый тег с текстом "Далее"
            "text='Вперед'"  # ЛЮБОЙ видимый тег с текстом "Вперед"
        ]

        for sel in selectors:
            try:
                # Ищем все элементы по селектору
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(force=True)
                        print(f"[i] [PROFIRESEARCH] Нажата кнопка: «Далее» (найдено по: {sel})")
                        return True
            except Exception:
                continue

        return False

    async def handle_combobox_city(self, page: Page) -> bool:
        """Специальный обработчик выбора города для ProfiResearch."""
        target_city = self.profile_personal.get("city", "Москва")

        # 1. Попытка кликнуть по быстрым ссылкам под полем
        fast_clicked = await page.evaluate("""(city) => {
            let fastLinks = Array.from(document.querySelectorAll('.pr-geo-fastoptions span, .pr-geo-fastoptions a, .pr-elem'));
            let target = fastLinks.find(el => el.innerText.trim().toLowerCase() === city.toLowerCase());
            if (target) {
                target.scrollIntoView({behavior: 'smooth', block: 'center'});
                target.click();
                return true;
            }
            return false;
        }""", target_city)

        if fast_clicked:
            print(f"[✓] [PROFIRESEARCH] Город «{target_city}» выбран из быстрых ссылок")
            return True

        # 2. Если быстрой ссылки нет, взаимодействуем с Selectize.js
        sel_input = await page.query_selector('.selectize-input input')
        if sel_input and await sel_input.is_visible():
            print(f"\n[i] [PROFIRESEARCH] Ввод города: «{target_city}»...")
            await sel_input.scroll_into_view_if_needed()
            await sel_input.click(force=True)
            await page.keyboard.type(target_city, delay=100)
            await human_sleep(1.0, 1.5)

            # Ждем появления дропдауна и кликаем
            options = await page.query_selector_all('.selectize-dropdown-content .option')
            for opt in options:
                text = await opt.inner_text()
                if target_city.lower() in text.lower():
                    await opt.click(force=True)
                    print(f"[✓] [PROFIRESEARCH] Город «{target_city}» выбран из списка")
                    return True

            await page.keyboard.press("Enter")
            return True

        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:
        # 1. Перехват вопроса о городе
        is_city_question = await page.evaluate("""() => {
            let qEl = document.querySelector('pr-question-title, .pr-question-title, h-block, h1, h2, h3, .question-text');
            let txt = qEl ? qEl.innerText.toLowerCase() : '';
            let hasCityEl = document.querySelector('.pr-city, input[placeholder*="город"], .selectize-control') !== null;
            return (txt.includes('город') || txt.includes('проживаете') || txt.includes('живете')) && hasCityEl;
        }""")

        if is_city_question:
            handled = await self.handle_combobox_city(page)
            if handled:
                await human_sleep(1.0, 1.5)
                await self.click_next(page)
                return True

        total_handled = 0

        for _ in range(15):
            data = await page.evaluate("""() => {
                // Умный поиск реального заголовка вопроса, игнорируя системные подсказки
                function getClosestTitle(el) {
                    let qContainer = el.closest('form.pr-question, div.pr-question, .pr-question-main');
                    if (qContainer) {
                        let titleEl = qContainer.querySelector('pr-question-title, h-block');
                        if (titleEl) return titleEl.innerText.trim();
                    }

                    let allTitles = Array.from(document.querySelectorAll('pr-question-title, .pr-question-title, h-block, h1, h2, h3, .question-text'));
                    for (let i = allTitles.length - 1; i >= 0; i--) {
                        if (allTitles[i].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) {
                            let text = allTitles[i].innerText.trim();
                            let lower = text.toLowerCase();
                            if (text.length > 2 && !lower.includes('оцените по шкале') && !lower.includes('выберите один') && !lower.includes('выберите все') && !lower.includes('подходящие ответы') && !lower.includes('введите текст')) {
                                return text;
                            }
                        }
                    }
                    let fallback = document.querySelector('pr-question-title, h-block, .question-text');
                    return fallback ? fallback.innerText.trim() : '';
                }

                // 2. Ищем ПУСТЫЕ текстовые поля (исключая поля "Другое" в чекбоксах)
                let textInputs = Array.from(document.querySelectorAll('textarea, input[type="text"]:not([readonly]), input[type="number"], input[type="email"], input[type="tel"]')).filter(i => {
                    if (i.value.trim() !== '') return false;
                    // Пропускаем невидимые, кроме тех что скрыты специфично фреймворком но интерактивны
                    if (i.offsetParent === null && !i.closest('.selectize-input')) return false;

                    let row = i.closest('tr.pr-row, .pr-row');
                    if (row && row.querySelector('input[type="radio"], input[type="checkbox"]')) return false;
                    return true;
                });

                if (textInputs.length > 0) {
                    let inp = textInputs[0];
                    inp.setAttribute('data-bot-target', 'true');

                    let qText = getClosestTitle(inp);
                    let subTitle = '';
                    let row = inp.closest('tr.pr-row');

                    if (row) {
                        let tEl = row.querySelector('pr-row-title, .pr-cell-head, label');
                        if (tEl) subTitle = tEl.innerText.trim();
                    } else if (inp.parentElement) {
                        let clone = inp.parentElement.cloneNode(true);
                        let inps = clone.querySelectorAll('input, textarea, select');
                        inps.forEach(e => e.remove());
                        subTitle = clone.innerText.trim();
                    }

                    let finalQ = qText;
                    if (subTitle && subTitle.length > 0 && subTitle.length < 50 && subTitle !== qText) {
                        finalQ = `${qText} -> ${subTitle}`;
                    }

                    return {targetType: 'text', questionText: finalQ, options: []};
                }

                // 3. Ищем ВЫПАДАЮЩИЕ СПИСКИ (select) с учетом плагина Selectize.js
                let selects = Array.from(document.querySelectorAll('select')).filter(s => {
                    if (s.disabled) return false;

                    // Разрешаем скрытые селекты ТОЛЬКО если они обернуты в selectize
                    let isSelectize = s.classList.contains('selectized') || (s.nextElementSibling && s.nextElementSibling.classList.contains('selectize-control'));
                    if (s.offsetParent === null && !isSelectize) return false;

                    let val = s.value;
                    let text = s.options[s.selectedIndex] ? s.options[s.selectedIndex].innerText.trim() : '';
                    return !val || val === '0' || text === '' || text.toLowerCase().includes('выбер') || text.includes('---') || text.toLowerCase().includes('начните вводить');
                });

                if (selects.length > 0) {
                    let sel = selects[0];
                    sel.setAttribute('data-bot-target', 'true');

                    let qText = getClosestTitle(sel);
                    let rawOptions = Array.from(sel.querySelectorAll('option')).filter(o => {
                        let t = o.innerText.trim();
                        let v = o.value;
                        return t && v !== '0' && v !== '' && !t.toLowerCase().includes('выбер') && !t.includes('---') && !t.toLowerCase().includes('начните вводить');
                    });

                    let subTitle = '';
                    let container = sel.closest('td, .pr-cell') || sel.parentElement;
                    if (container && container.nextElementSibling) {
                        subTitle = container.nextElementSibling.innerText.trim();
                    } else if (sel.parentElement) {
                        let clone = sel.parentElement.cloneNode(true);
                        let inps = clone.querySelectorAll('input, textarea, select');
                        inps.forEach(e => e.remove());
                        subTitle = clone.innerText.trim();
                    }

                    let finalQ = qText;
                    if (subTitle && subTitle.length > 0 && subTitle.length < 50 && subTitle !== qText) {
                        finalQ = `${qText} -> ${subTitle}`;
                    }

                    return {
                        targetType: 'select',
                        questionText: finalQ,
                        options: rawOptions.map(o => o.innerText.trim())
                    };
                }

                // 4. Ищем Радио-кнопки и чекбоксы
                let choiceRows = Array.from(document.querySelectorAll('tr.pr-row')).filter(r => {
                    if (r.offsetParent === null) return false;
                    return r.querySelector('input[type="radio"], input[type="checkbox"]') !== null;
                });

                if (choiceRows.length > 0) {
                    let isAnswered = choiceRows.some(r => {
                        let inp = r.querySelector('input[type="radio"], input[type="checkbox"]');
                        return inp && inp.checked;
                    });

                    if (!isAnswered) {
                        let qText = getClosestTitle(choiceRows[0]);
                        let isMulti = choiceRows.some(r => r.querySelector('input[type="checkbox"]') !== null);
                        let options = choiceRows.map((r, i) => {
                            let tEl = r.querySelector('pr-row-title, .pr-cell-head, label');
                            return tEl ? tEl.innerText.trim() : `Вариант ${i + 1}`;
                        });
                        return {targetType: 'choices', questionText: qText, options: options, isMulti: isMulti};
                    }
                }

                let fallback = document.querySelector('pr-question-title, .question-text');
                return {
                    targetType: 'done_or_info',
                    questionText: fallback ? fallback.innerText.trim() : '',
                    options: []
                };
            }""")

            if not data:
                break

            if data["targetType"] == "done_or_info":
                if total_handled == 0 and data["questionText"]:
                    print(f"\n📄 [ИНФО-ЭКРАН]: {data['questionText']}")
                break

            elif data["targetType"] == "text":
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                print(f"\n[№ {self.brain.stats.get('total_answered', 0)}] ОТКРЫТЫЙ ВОПРОС: {data['questionText']}")
                ans_text = self.brain.answer_open_text(data["questionText"])

                if ans_text:
                    print(f"✍️  [ВВОД]: {ans_text}")
                    await page.evaluate("""(text) => {
                        let inp = document.querySelector('textarea[data-bot-target="true"], input[data-bot-target="true"]');
                        if (inp) {
                            inp.focus();
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
                        let inp = document.querySelector('textarea[data-bot-target="true"], input[data-bot-target="true"]');
                        if (inp) inp.removeAttribute('data-bot-target');
                    }""")
                    break

            elif data["targetType"] == "select":
                print("\n" + "=" * 60)
                print(f"[?] ВОПРОС (ВЫПАДАЮЩИЙ СПИСОК): {data['questionText']}")
                print(f"[*] ВСЕГО ВАРИАНТОВ: {len(data['options'])}")
                for idx, text in enumerate(data["options"][:15]):
                    print(f"    [{idx}] {text}")

                decision = self.brain.decide(data["questionText"], data["options"], is_multiselect=False)

                if decision.selected_indices:
                    try:
                        self.brain.stats['total_answered'] += 1
                    except Exception:
                        pass

                    selected_name = data["options"][decision.selected_indices[0]]
                    print(f"[№ {self.brain.stats.get('total_answered', 0)}] ВЫБРАНО: -> ['{selected_name}']")
                    print(f"[LLM] ЛОГИКА: {decision.reasoning}")
                    print("=" * 60)

                    await page.evaluate("""(optText) => {
                        let sel = document.querySelector('select[data-bot-target="true"]');
                        if (sel) {
                            let options = Array.from(sel.querySelectorAll('option'));
                            let targetOpt = options.find(o => {
                                let oText = o.innerText.trim();
                                return oText === optText || oText.includes(optText) || optText.includes(oText);
                            });

                            if (targetOpt) {
                                sel.value = targetOpt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                sel.dispatchEvent(new Event('input', {bubbles: true}));
                                if (typeof window.jQuery !== 'undefined') {
                                    let $sel = window.jQuery(sel);
                                    if ($sel[0].selectize) {
                                        $sel[0].selectize.setValue(targetOpt.value);
                                    } else {
                                        $sel.trigger('change');
                                    }
                                }
                            }
                            sel.removeAttribute('data-bot-target');
                        }
                    }""", selected_name)
                    total_handled += 1
                    await human_sleep(0.5, 1.0)
                else:
                    print("[LLM] ВЫБРАНО: -> НИЧЕГО (Ожидание выбора в GUI)")
                    print("=" * 60)
                    await page.evaluate("""() => {
                        let sel = document.querySelector('select[data-bot-target="true"]');
                        if (sel) sel.removeAttribute('data-bot-target');
                    }""")
                    break

            elif data["targetType"] == "choices":
                print("\n" + "=" * 60)
                print(f"[?] ВОПРОС: {data['questionText']}")
                print(f"[i] ТИП: {'Множественный выбор' if data['isMulti'] else 'Одиночный выбор'}")
                print(f"[*] ВСЕГО ВАРИАНТОВ: {len(data['options'])}")
                for idx, text in enumerate(data["options"][:15]):
                    print(f"    [{idx}] {text}")

                decision = self.brain.decide(data["questionText"], data["options"], data["isMulti"])

                if decision.selected_indices:
                    try:
                        self.brain.stats['total_answered'] += 1
                    except Exception:
                        pass

                    selected_names = [data["options"][i] for i in decision.selected_indices if i < len(data["options"])]
                    print(
                        f"[№ {self.brain.stats.get('total_answered', 0)}] ВЫБРАНО ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_names}")
                    print(f"[LLM] ЛОГИКА: {decision.reasoning}")
                    print("=" * 60)

                    for sel_idx in decision.selected_indices:
                        await page.evaluate("""(idx) => {
                            let rows = Array.from(document.querySelectorAll('tr.pr-row')).filter(r => r.offsetParent !== null && r.querySelector('input[type="radio"], input[type="checkbox"]'));
                            if (rows[idx]) {
                                let input = rows[idx].querySelector('input[type="radio"], input[type="checkbox"]');
                                if (input) {
                                    input.scrollIntoView({behavior: 'smooth', block: 'center'});
                                    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                                        input.dispatchEvent(new MouseEvent(evt, {
                                            bubbles: true,
                                            cancelable: true,
                                            view: window
                                        }));
                                    });
                                    input.checked = true;
                                    input.dispatchEvent(new Event('change', {bubbles: true}));
                                } else {
                                    rows[idx].click();
                                }

                                // Если в этой строке есть поле "Другое", заполняем его
                                let textInp = rows[idx].querySelector('input[type="text"]');
                                if (textInp) {
                                    let label = rows[idx].querySelector('pr-row-title, .pr-cell-head, label');
                                    let val = label ? label.innerText.replace(/\\(.*\\)/g, '').trim() : "Свой вариант";
                                    textInp.value = val || "Другое";
                                    textInp.dispatchEvent(new Event('input', {bubbles: true}));
                                    textInp.dispatchEvent(new Event('change', {bubbles: true}));
                                }
                            }
                        }""", sel_idx)
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