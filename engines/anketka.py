import asyncio
import random
import math
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep, MONTH_NAMES
from core.bot_state import state
from core.dom_synchronizer import DOMSynchronizer
from engines.mixins import InfoScreenMixin


class AnketkaEngine(InfoScreenMixin, BaseSurveyEngine):
    async def click_next(self, page: Page) -> bool:
        decision = await state.wait_debug_confirm()
        if decision == "RETRY":
            print("[🔄] Отменяем переход по кнопке «Вперед». Сбрасываем выбранные варианты...")
            await page.evaluate("""() => {
                let active = document.querySelector('.step.active, .es__root') || document.body;
                active.querySelectorAll('input:checked').forEach(i => {
                    i.click();
                    i.checked = false;
                    i.dispatchEvent(new Event('change', {bubbles: true}));
                });
                let activeCustom = active.querySelectorAll('.es__answer-label.active, [aria-checked="true"]');
                activeCustom.forEach(el => {
                    let btn = el.querySelector('[role="button"], input') || el;
                    btn.click();
                });
            }""")
            return False

        try:
            await DOMSynchronizer.sync_memory(page, self.brain)
        except:
            pass

        selectors = [
            "#nextSurvey",
            "[data-testid='next-survey']",
            "button:has-text('Вперед')",
            "button:has-text('Далее')",
            "button:has-text('Продолжить')"
        ]

        for sel in selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    try:
                        box = await btn.bounding_box()
                        if box:
                            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    except:
                        pass
                    await btn.click(force=True, timeout=1500)
                    print(f"[i] [ANKETKA] Нажата кнопка: {sel}")
                    return True
            except Exception:
                continue

        clicked_div = await page.evaluate("""() => {
            let activeContainer = document.querySelector('.step.active, .es__root') || document.body;
            let buttons = Array.from(activeContainer.querySelectorAll('button, #nextSurvey, [data-testid="next-survey"], div[class*="button"], div[class*="Button"], a.btn, div.btn, span.btn, .btn-green, .btn-primary')).filter(el => {
                if (el.offsetParent === null) return false;
                let txt = (el.innerText || '').trim().toLowerCase();
                if (txt.length > 50) return false;
                return ['вперед', 'далее', 'продолжить', 'начать опрос', 'подобрать опрос', 'получить', 'старт', 'завершить'].some(kw => txt === kw || txt.includes(kw));
            });

            if (buttons.length > 0) {
                buttons.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
                let target = buttons[0];
                target.scrollIntoView({behavior: 'smooth', block: 'center'});
                target.click();
                return target.innerText.trim();
            }
            return null;
        }""")

        if clicked_div:
            print(f"[i] [ANKETKA] Нажата кнопка (JS): «{clicked_div}»")
            return True
        return False

    async def handle_child_matrix_dropdowns(self, page: Page) -> bool:
        is_child_table = await page.evaluate("""() => {
            let table = document.querySelector('.matrix-container table, .table-component table');
            if (!table) return false;
            let txt = (document.body.innerText || '').toLowerCase();
            return (txt.includes('ребенк') || txt.includes('дет')) && (txt.includes('числ') || txt.includes('месяц') || txt.includes('год'));
        }""")

        if not is_child_table:
            return False

        print("\n[👶] Обнаружена таблица с данными ребенка. Заполняем по профилю: 05.03.2023, Мужской...")

        child_day = 5
        child_month_aliases = ["марта", "март", "03", "3"]
        child_year = 2023
        child_gender = self.profile_personal.get("child_gender", "Мужской")

        filled = await page.evaluate("""async ({day, monthAliases, year, gender}) => {
            let table = document.querySelector('.matrix-container table, .table-component table');
            if (!table) return false;

            let headerRow = table.querySelector('tr.table-row-0') || table.querySelector('thead tr');
            if (!headerRow) return false;
            let colHeaders = Array.from(headerRow.querySelectorAll('td, th')).map(c => (c.innerText || '').trim().toLowerCase());

            let rows = Array.from(table.querySelectorAll('tr[data-row-id]'));
            if (rows.length === 0) return false;

            for (let row of rows) {
                let cells = Array.from(row.querySelectorAll('td'));
                for (let i = 0; i < cells.length; i++) {
                    let cell = cells[i];
                    let colName = colHeaders[i] || '';

                    let targetVals = [];
                    if (colName.includes('числ') || colName.includes('день')) {
                        targetVals = [String(day), String(day).padStart(2, '0')];
                    } else if (colName.includes('месяц')) {
                        targetVals = monthAliases;
                    } else if (colName.includes('год')) {
                        targetVals = [String(year)];
                    } else if (colName.includes('пол')) {
                        targetVals = [gender];
                    }

                    if (targetVals.length === 0) continue;

                    let wrap = cell.querySelector('.select-wrap');
                    if (!wrap) continue;

                    let searchInp = wrap.querySelector('input.select-search');
                    if (searchInp) {
                        searchInp.value = '';
                        searchInp.dispatchEvent(new Event('input', {bubbles: true}));
                    }

                    let trigger = wrap.querySelector('[data-testid="input"], .select-input') || wrap;
                    trigger.click();
                    await new Promise(r => setTimeout(r, 200));

                    let items = Array.from(wrap.querySelectorAll('.select-dropdown-item'));
                    let found = items.find(it => {
                        let itTxt = (it.innerText || '').trim().toLowerCase();
                        return targetVals.some(tv => itTxt === tv.toLowerCase() || itTxt.startsWith(tv.toLowerCase()));
                    });

                    if (found) {
                        found.click();
                        await new Promise(r => setTimeout(r, 200));
                    }
                }
            }
            return true;
        }""", {"day": child_day, "monthAliases": child_month_aliases, "year": child_year, "gender": child_gender})

        return filled

    async def handle_composite_demographics(self, page: Page) -> bool:
        target_gender = self.profile_personal.get("gender", "Мужской")
        gender_clicked = await page.evaluate("""(gender) => {
            let labels = Array.from(document.querySelectorAll('label, div.answer-item, button, span')).filter(el => {
                return el.offsetParent !== null && (el.innerText || '').trim().toLowerCase() === gender.toLowerCase();
            });
            if (labels.length > 0) {
                let target = labels[0];
                let input = target.querySelector('input') || target;
                input.click();
                return true;
            }
            return false;
        }""", target_gender)

        if gender_clicked:
            print(f"[i] [ANKETKA] Автозаполнение пола: «{target_gender}»")
            await human_sleep(0.3, 0.6)

        day_val = str(int(self.profile_personal.get("birth_day", "27")))
        month_int = int(self.profile_personal.get("birth_month", "6"))
        year_val = str(self.profile_personal.get("birth_year", "2005"))
        month_aliases = MONTH_NAMES.get(month_int, [str(month_int)])

        filled_native = await page.evaluate("""({day, month, year, monthAliases}) => {
            let selects = Array.from(document.querySelectorAll('select')).filter(s => s.offsetParent !== null);
            if (selects.length >= 3) {
                function setVal(sel, targets) {
                    for (let opt of sel.options) {
                        let optText = opt.text.trim().toLowerCase();
                        let optVal = opt.value.trim().toLowerCase();
                        if (targets.some(t => t.toLowerCase() === optVal || t.toLowerCase() === optText || optText.includes(t.toLowerCase()))) {
                            sel.value = opt.value;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            sel.dispatchEvent(new Event('input', {bubbles: true}));
                            return true;
                        }
                    }
                    return false;
                }

                setVal(selects[0], [day]);
                setVal(selects[1], [month, ...monthAliases]);
                setVal(selects[2], [year]);
                return true;
            }
            return false;
        }""", {"day": day_val, "month": str(month_int), "year": year_val, "monthAliases": month_aliases})

        if filled_native:
            print(f"[i] [ANKETKA] Дата рождения заполнена: {day_val}.{month_int}.{year_val}")
            await human_sleep(0.6, 1.0)
            return True
        return False

    async def extract_question_text(self, page: Page) -> str:
        text = await page.evaluate("""() => {
            let headers = Array.from(document.querySelectorAll('.es__question-h1, [data-testid="header-title"], .question-header, h1, h2, h3'));
            let valid = headers.map(h => (h.innerText || '').trim()).filter(t => t.length > 3 && !t.toLowerCase().includes('время опросов'));
            return valid.length > 0 ? valid[0] : '';
        }""")

        if not text:
            from engines.js_snippets import JS_EXTRACT_QUESTION_TEXT
            text = await page.evaluate(JS_EXTRACT_QUESTION_TEXT)

        return text if text else "Выберите подходящий вариант"

    def _apply_alternative_logic(self, options_texts, decision, is_multi, q_key="default"):
        if not hasattr(self, "last_selected_by_q"):
            self.last_selected_by_q = {}

        if getattr(state, "force_alternative", False):
            last_idx = self.last_selected_by_q.get(q_key, [])
            bad_words = ["ничего", "затрудняюсь", "не знаю", "другое", "нет домашних", "нет детей"]
            valid_indices = [i for i in range(len(options_texts)) if
                             not any(w in options_texts[i].lower() for w in bad_words)]
            if not valid_indices:
                valid_indices = list(range(len(options_texts)))

            if not is_multi:
                diff_indices = [i for i in valid_indices if i not in last_idx]
                if not diff_indices:
                    diff_indices = [i for i in range(len(options_texts)) if i not in last_idx]
                if diff_indices:
                    decision.selected_indices = [random.choice(diff_indices)]
            else:
                new_comb = []
                for _ in range(15):
                    k = random.randint(1, min(3, len(valid_indices)))
                    sample = sorted(random.sample(valid_indices, k))
                    if set(sample) != set(last_idx):
                        new_comb = sample
                        break
                if not new_comb:
                    diff = [i for i in valid_indices if i not in last_idx]
                    new_comb = diff[:2] if diff else [valid_indices[0]]
                decision.selected_indices = new_comb

            print(f"[🔄] Сформирован альтернативный ответ (исключен прошлый выбор: {last_idx})")

        self.last_selected_by_q[q_key] = decision.selected_indices
        return decision

    async def handle_dashboard(self, page: Page, body_lower: str) -> bool:
        """Поиск и запуск доступных опросов на странице профиля Анкетки."""
        from engines.js_snippets import JS_SCAN_ANKETKA_SURVEYS
        try:
            res = await page.evaluate(JS_SCAN_ANKETKA_SURVEYS)
            if res and res.get("found"):
                title = res.get("text", "")
                href = res.get("href", "")
                print(f"\n[🚀] [АНКЕТКА] Обнаружен доступный опрос: «{title}»")
                if href:
                    print(f"[🔗] Ссылка: {href}")
                await human_sleep(2.0, 3.5)
                return True
        except Exception as e:
            print(f"[!] Ошибка сканирования дашборда Анкетки: {e}")
        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:

        # 0. ПРОВЕРКА ЛИЧНОГО КАБИНЕТА / ДАШБОРДА АНКЕТКИ (/profile)
        if "/profile" in page.url.lower() or "доступные опросы" in body_lower or "быстрый опрос" in body_lower:
            if await self.handle_dashboard(page, body_lower):
                return True

        # ПЕРЕХВАТ НАГРАДЫ АНКЕТКИ
        if "выберите награду" in body_lower or "survey-finish" in page.url.lower():
            if await self.handle_anketka_reward(page):
                return True

        if await self.handle_info_screen(page):
            await human_sleep(1.5, 2.5)
            return True

        if await self.handle_child_matrix_dropdowns(page):
            await human_sleep(1.0, 1.8)
            clicked = await self.click_next(page)
            if not clicked:
                return await self.process_step(page, body_lower)
            return True

        # ВЫПАДАЮЩИЕ СПИСКИ АНКЕТКИ (.select-wrap)
        if await self.handle_custom_dropdowns(page):
            return True

        has_dob = await page.evaluate("() => document.querySelectorAll('select').length >= 2")
        if has_dob or ("день" in body_lower and "месяц" in body_lower and "год" in body_lower and (
        await page.query_selector("select"))):
            if await self.handle_composite_demographics(page):
                await human_sleep(0.8, 1.4)
                clicked = await self.click_next(page)
                if not clicked:
                    return await self.process_step(page, body_lower)
                return True

        # УМНЫЙ ПАРСИНГ БЛОКОВ (Поддержка как одиночных, так и групповых вопросов)
        blocks_data = await page.evaluate("""() => {
            let activeRoot = document.querySelector('.step.active, .es__root') || document.body;
            let qBlocks = Array.from(activeRoot.querySelectorAll('.question-container:not(.type_group)'));
            if (qBlocks.length === 0) qBlocks = [activeRoot];

            let result = [];
            qBlocks.forEach((block, bIdx) => {
                let isAnswered = block.querySelectorAll('.es__answer-label.active, .es__answer-label.selected, input:checked').length > 0;

                // Игнорируем пустые заголовки, ищем настоящий текст вопроса внутри блока
                let headers = Array.from(block.querySelectorAll('.es__question-h1, [data-testid="header-title"], h1, h2, h3, .wrapper-html'));
                let validHeader = headers.find(h => (h.innerText || '').trim().length > 3);
                let qTitle = validHeader ? (validHeader.innerText || '').trim() : '';

                let selector = [
                    'div[class*="scale-item"]', 'div[class*="scale-answer"]',
                    'li.choice-item', 'div.choice-item', 'div[class*="AnswerRow"]', 'div[class*="answer-row"]',
                    'div[class*="LogoItem"]', 'div[class*="GridItem"]', 'div[class*="answer-item"]', 'div[class*="es__answer-item"]',
                    '.answer-item', 'label.option-label', '.LogoItem', '.scale-item'
                ].join(', ');

                let nodes = Array.from(block.querySelectorAll(selector)).filter(n => {
                    return n.offsetParent !== null && !n.className.includes('Button') && !n.className.includes('btn') && (n.innerText || '').trim().length > 0;
                });

                let opts = nodes.map((node, idx) => {
                    let directText = (node.innerText || '').trim();
                    // ИСПРАВЛЕНИЕ: Удаляем нумерацию ТОЛЬКО при наличии точки/скобки. Больше не трогаем диапазоны цен!
                    let cleanDirect = directText.replace(/^\\d+[\\.\\)]\\s+/, '').trim();

                    let attrCandidate = '';
                    let attrSources = [node, ...Array.from(node.querySelectorAll('*'))];
                    for (let el of attrSources) {
                        let val = el.getAttribute('data-name') || el.getAttribute('data-title') || el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || '';
                        val = val.trim();
                        if (val.length > 1 && !/^[0-9a-f]{1,4}$/i.test(val) && !val.toLowerCase().startsWith('http')) {
                            attrCandidate = val;
                            break;
                        }
                    }
                    let finalName = attrCandidate || (cleanDirect || directText || `Вариант ${idx + 1}`);
                    return {index: idx, text: finalName};
                });

                let isMulti = block.querySelector('input[type="checkbox"], .type_multi') !== null;

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

        any_answered_now = False

        for b in blocks_data:
            if b["is_answered"]:
                continue
            if not b["options"]:
                continue

            q_text = b["question_text"] or await self.extract_question_text(page)
            opts_texts = [o["text"] for o in b["options"]]
            is_multi = b["is_multi"]
            b_idx = b["block_idx"]

            print("\n" + "=" * 60)
            print(f"[?] ВОПРОС [{b_idx + 1}/{len(blocks_data)}]: {q_text}")
            print(f"[*] ВСЕГО ВАРИАНТОВ: {len(opts_texts)}")
            for idx, text in enumerate(opts_texts[:15]):
                print(f"    [{idx}] {text}")

            decision = self.brain.decide(q_text, opts_texts, is_multi)
            decision = self._apply_alternative_logic(opts_texts, decision, is_multi, q_key=f"b_{b_idx}")

            selected_names = [opts_texts[i] for i in decision.selected_indices if i < len(opts_texts)]
            print(f"[LLM] ВЫБРАНО ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_names}")
            print(f"[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)

            for opt_idx in decision.selected_indices:
                await page.evaluate("""({bIdx, optIdx}) => {
                    let activeRoot = document.querySelector('.step.active, .es__root') || document.body;
                    let qBlocks = Array.from(activeRoot.querySelectorAll('.question-container:not(.type_group)'));
                    if (qBlocks.length === 0) qBlocks = [activeRoot];
                    let targetBlock = qBlocks[bIdx];
                    if (!targetBlock) return;

                    let selector = 'div[class*="scale-item"], div[class*="scale-answer"], li.choice-item, div.choice-item, div[class*="AnswerRow"], div[class*="answer-row"], div[class*="LogoItem"], div[class*="GridItem"], div[class*="answer-item"], div[class*="es__answer-item"], .answer-item, label.option-label, .LogoItem, .scale-item';
                    let nodes = Array.from(targetBlock.querySelectorAll(selector)).filter(n => n.offsetParent !== null && !n.className.includes('Button') && !n.className.includes('btn') && (n.innerText || '').trim().length > 0);
                    if (nodes[optIdx]) {
                        let target = nodes[optIdx];
                        target.scrollIntoView({behavior: 'smooth', block: 'center'});
                        let inp = target.querySelector('input, [role="button"]');
                        if (inp) inp.click(); else target.click();
                    }
                }""", {"bIdx": b_idx, "optIdx": opt_idx})
                await human_sleep(0.3, 0.5)

            any_answered_now = True

        # Сбрасываем флаг альтернативы после отработки страницы
        setattr(state, "force_alternative", False)

        # Текстовые поля ввода (если вариантов вообще не было)
        if not any_answered_now and not any(b["options"] for b in blocks_data):
            has_real_text = await page.evaluate("""() => {
                let inps = Array.from(document.querySelectorAll("textarea, input[type='text'], input[type='number'], input:not([type])"));
                let valid = inps.find(i => {
                    if (i.offsetParent === null) return false;
                    let cls = (i.className || '').toLowerCase();
                    if (cls.includes('search') || cls.includes('select')) return false;
                    if (i.closest('.select-wrap, .selectize-control, .choices, .portal, [data-testid="dropdown-container"]')) return false;
                    return true;
                });
                return valid ? true : false;
            }""")

            if has_real_text:
                text_input = await page.query_selector(
                    "textarea, input[type='text']:not(.select-search), input[type='number']")
                if text_input:
                    q_text = await self.extract_question_text(page)
                    print(f"\n[?] ТЕКСТОВЫЙ ВОПРОС: {q_text}")
                    from core.rules_engine import RulesEngine
                    rules = RulesEngine(self.brain.profile)
                    ans = rules.apply_open_text_rules(q_text.lower(), False) or "Хорошо"
                    await text_input.fill(ans)
                    print(f"[i] Заполнено текстом: «{ans}»")
                    await human_sleep(0.8, 1.4)
                    clicked = await self.click_next(page)
                    if not clicked:
                        return await self.process_step(page, body_lower)
                    return True
            return False

        if any_answered_now:
            await human_sleep(0.8, 1.4)
            clicked = await self.click_next(page)
            if not clicked:
                return await self.process_step(page, body_lower)
            return True

        # Если на странице не было активных вопросов (инфо-экран) или все вопросы уже отвечены
        next_btn = await page.query_selector("#nextSurvey, [data-testid='next-survey'], button:has-text('Вперед'), button:has-text('Далее')")
        if next_btn and await next_btn.is_visible():
            print("[i] [ANKETKA] Информационный экран или вопросы уже отвечены. Нажимаем «Вперед»...")
            await human_sleep(0.6, 1.2)
            clicked = await self.click_next(page)
            if clicked:
                return True

        return False

    async def handle_anketka_reward(self, page: Page) -> bool:
        """Автоматический выбор денежного вознаграждения на финальном экране Анкетки"""
        try:
            await human_sleep(1.0, 1.5)

            # 1. Поиск через Playwright Locator (надежно пробивает Next.js / React)
            card = page.locator("div[class*='option_card']").filter(has_text="Деньги")
            btn = card.locator("button:has-text('Выбрать')")

            if await btn.count() > 0:
                await btn.first.scroll_into_view_if_needed()
                await asyncio.sleep(0.3)
                await btn.first.click(force=True)
                print("[✓] [ANKETKA] Выбрана награда: «Деньги»!")
                await human_sleep(2.0, 3.0)
                return True

            # 2. Фолбэк через JavaScript-клик по карточке с деньгами
            clicked = await page.evaluate("""() => {
                let cards = Array.from(document.querySelectorAll('div[class*="option_card"], .select-reward-page_option_card__WR4OX'));
                for (let c of cards) {
                    let txt = (c.innerText || '').toLowerCase();
                    if (txt.includes('деньги') || txt.includes('₽') || txt.includes('руб')) {
                        let b = c.querySelector('button.select-reward-page_select_button__B9XtU, button:not([class*="info"])');
                        if (b) {
                            b.click();
                            return true;
                        }
                    }
                }
                // Резерв: кликаем по кнопке в блоке с деньгами, избегая благотворительности
                let moneyCard = Array.from(document.querySelectorAll('div, section, article')).find(el => {
                    let t = (el.innerText || '').toLowerCase();
                    return (t.includes('деньги') || t.includes('рубл') || t.includes('₽')) && !t.includes('благотворит') && !t.includes('статьи');
                });
                let firstBtn = moneyCard ? moneyCard.querySelector('button') : null;
                if (firstBtn) {
                    firstBtn.click();
                    return true;
                }
                return false;
            }""")

            if clicked:
                print("[✓] [ANKETKA] Нажата кнопка получения денег (JS)!")
                await human_sleep(2.0, 3.0)
                return True
        except Exception as e:
            print(f"[!] Ошибка при выборе награды: {e}")
        return False

    async def handle_custom_dropdowns(self, page: Page) -> bool:
        """Обработка кастомных выпадающих списков Anketka (.select-wrap)."""
        dropdowns_data = await page.evaluate("""() => {
            let activeRoot = document.querySelector('.step.active, .es__root') || document.body;
            let wraps = Array.from(activeRoot.querySelectorAll('.select-wrap')).filter(w => w.offsetParent !== null);
            if (wraps.length === 0) return null;

            let result = [];
            wraps.forEach((wrap, wIdx) => {
                let valText = (wrap.querySelector('.select-input-values')?.innerText || '').trim().toLowerCase();
                let isAnswered = valText && !valText.includes('выберите') && !valText.includes('select');

                let qContainer = wrap.closest('.question-container') || activeRoot;
                let header = qContainer.querySelector('.es__question-h1, [data-testid="header-title"], h1, h2, h3');
                let mainTitle = header ? (header.innerText || '').trim() : '';
                let pageHeader = activeRoot.querySelector('.es__question-h1, [data-testid="header-title"], h1');
                let rootTitle = pageHeader ? (pageHeader.innerText || '').trim() : '';
                let labelEl = wrap.closest('label') || (wrap.parentElement ? wrap.parentElement.querySelector('label, [class*="label"], .select-label, span') : null) || wrap.previousElementSibling;
                let subLabel = labelEl ? (labelEl.innerText || '').trim() : '';
                let qTitle = mainTitle || rootTitle || subLabel || '';
                if (subLabel && subLabel !== qTitle && !qTitle.includes(subLabel)) {
                    qTitle = qTitle ? `${qTitle} (${subLabel})` : subLabel;
                }

                let items = Array.from(wrap.querySelectorAll('.select-dropdown-item'));
                let opts = items.map((it, idx) => (it.innerText || '').trim()).filter(t => t.length > 0);

                result.push({
                    wrap_idx: wIdx,
                    is_answered: isAnswered,
                    question_text: qTitle,
                    options: opts
                });
            });

            return result;
        }""")

        if not dropdowns_data:
            return False

        unanswered = [d for d in dropdowns_data if not d["is_answered"]]
        if not unanswered:
            return False

        for d in unanswered:
            q_text = d["question_text"] or await self.extract_question_text(page)
            w_idx = d["wrap_idx"]
            opts_texts = d["options"]

            # Если список вариантов еще не развернут в DOM
            if not opts_texts:
                await page.evaluate("""(wIdx) => {
                    let activeRoot = document.querySelector('.step.active, .es__root') || document.body;
                    let wraps = Array.from(activeRoot.querySelectorAll('.select-wrap')).filter(w => w.offsetParent !== null);
                    let target = wraps[wIdx];
                    if (target) {
                        let trigger = target.querySelector('[data-testid="input"], .select-input') || target;
                        trigger.click();
                    }
                }""", w_idx)
                await asyncio.sleep(0.3)
                opts_texts = await page.evaluate("""(wIdx) => {
                    let activeRoot = document.querySelector('.step.active, .es__root') || document.body;
                    let wraps = Array.from(activeRoot.querySelectorAll('.select-wrap')).filter(w => w.offsetParent !== null);
                    let target = wraps[wIdx];
                    if (!target) return [];
                    let items = Array.from(target.querySelectorAll('.select-dropdown-item'));
                    return items.map(it => (it.innerText || '').trim()).filter(t => t.length > 0);
                }""", w_idx)

            if not opts_texts:
                continue

            print("\n" + "=" * 60)
            print(f"[🔽] [ANKETKA] ВЫПАДАЮЩИЙ СПИСОК: {q_text}")
            print(f"[*] ВСЕГО ВАРИАНТОВ: {len(opts_texts)}")
            for idx, text in enumerate(opts_texts[:15]):
                print(f"    [{idx}] {text}")

            decision = self.brain.decide(q_text, opts_texts, is_multiselect=False)
            decision = self._apply_alternative_logic(opts_texts, decision, is_multi=False, q_key=f"anketka_dd_{w_idx}")

            chosen_idx = decision.selected_indices[0] if decision.selected_indices else 0
            chosen_name = opts_texts[chosen_idx] if chosen_idx < len(opts_texts) else ""
            print(f"[LLM] ВЫБРАНО: [{chosen_idx}] -> {chosen_name}")
            print(f"[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)

            # Открываем меню и выбираем целевой год
            await page.evaluate("""async ({wIdx, optIdx}) => {
                let activeRoot = document.querySelector('.step.active, .es__root') || document.body;
                let wraps = Array.from(activeRoot.querySelectorAll('.select-wrap')).filter(w => w.offsetParent !== null);
                let target = wraps[wIdx];
                if (!target) return;

                let trigger = target.querySelector('[data-testid="input"], .select-input') || target;
                trigger.click();
                await new Promise(r => setTimeout(r, 200));

                let items = Array.from(target.querySelectorAll('.select-dropdown-item'));
                let item = items[optIdx];
                if (item) {
                    item.scrollIntoView({block: 'center'});
                    item.click();
                }
            }""", {"wIdx": w_idx, "optIdx": chosen_idx})

            await human_sleep(0.5, 0.8)

        await human_sleep(0.8, 1.4)
        clicked = await self.click_next(page)
        if not clicked:
            return await self.process_step(page, (await page.content()).lower())
        return True