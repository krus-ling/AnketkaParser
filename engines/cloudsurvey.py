import asyncio
import random
import re
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep


class CloudSurveyEngine(BaseSurveyEngine):
    async def click_next(self, page: Page) -> bool:
        selectors = [
            "#nextSurvey",
            "button[data-testid='next-survey']",
            "button#__next",
            "button[id='__next']",
            "#processingGoForwardBtn",
            ".next-button"
        ]
        for sel in selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.scroll_into_view_if_needed()
                    await btn.click(force=True)
                    print(f"[i] [CLOUDSURVEY] Нажата кнопка перехода: {sel}")
                    return True
            except Exception:
                continue

        btn_handle = await page.evaluate_handle("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let kws = ['далее', 'вперед', 'продолжить', 'начать опрос', 'начать', 'подобрать опрос', 'старт', 'получить', 'согласен', 'принимаю', 'принять', 'понятно', 'перейти', 'к опросу'];
            let candidates = Array.from(active.querySelectorAll('button, a, div, span, input[type="submit"], input[type="button"]')).filter(el => {
                if (el.offsetParent === null) return false;
                let style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0' || el.disabled) return false;
                let txt = (el.innerText || el.value || '').trim().toLowerCase();
                if (txt.length === 0 || txt.length > 50) return false;
                let isBtn = el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'INPUT' || (el.className || '').toLowerCase().includes('btn') || (el.className || '').toLowerCase().includes('button');
                let hasKw = kws.some(kw => txt === kw || txt.includes(kw));
                return isBtn && hasKw;
            });
            if (candidates.length > 0) {
                candidates.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
                return candidates[0];
            }
            return null;
        }""")

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
            except Exception:
                pass
            print(f"[i] [CLOUDSURVEY] Нажата кнопка: «{txt or 'Далее'}»")
            return True
        return False

    async def _visible_step_kind(self, page: Page) -> dict:
        try:
            return await page.evaluate("""() => {
                const norm = s => (s || '').toLowerCase().replace(/ё/g, 'е');

                function vis(el) {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const st = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
                }

                const active = document.querySelector('.step.active');
                let txt = (active && vis(active)) ? (active.innerText || '') : '';
                if (txt.trim().length < 8) {
                    const headers = Array.from(document.querySelectorAll(
                        'h1,h2,h3,h4,.question-text,[class*="question-header"],[class*="HeaderStyled"]'
                    )).filter(vis);
                    txt = headers.map(n => n.innerText || '').join('\\n') || (document.body.innerText || '');
                }
                txt = norm(txt);
                const isCity = txt.includes('населенн') || txt.includes('проживаете') || txt.includes('живете')
                    || (txt.includes('город') && !txt.includes('рожден'));
                const isDate = txt.includes('рожден') || (txt.includes('число') && txt.includes('месяц'));
                const isGender = (txt.includes('мужской') || txt.includes('женский')) && !isCity;
                const isIntro = txt.includes('время опросов');
                return {isCity, isDate, isGender, isIntro};
            }""") or {}
        except Exception:
            return {}

    async def _pick_custom_dropdown(self, page: Page, trigger, vals: list, field_name: str,
                                    partial: bool = False) -> bool:
        expected_l = [str(v).strip().lower().replace("ё", "е") for v in vals if str(v).strip()]
        if not expected_l or not trigger:
            return False

        async def _read() -> str:
            try:
                txt = await trigger.evaluate("""el => {
                    const wrap = el.closest('.select-wrap, [data-testid="input"], div[class*="select-input"]') || el;
                    const inp = wrap.querySelector && wrap.querySelector('input');
                    if (inp && inp.value) return String(inp.value).trim();
                    const t = (wrap.innerText || el.innerText || '').trim();
                    return t.split('\\n').map(s => s.trim()).filter(Boolean)[0] || '';
                }""")
                return (txt or "").strip()
            except Exception:
                return ""

        def _matches(shown: str) -> bool:
            s = (shown or "").strip().lower().replace("ё", "е")
            if not s or "выбер" in s or len(s) > 80:
                return False
            return any(s == v or v in s for v in expected_l)

        shown0 = await _read()
        if _matches(shown0):
            print(f"[✓] {field_name}: уже «{shown0}»")
            return True

        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.12)
        except Exception:
            pass

        await trigger.scroll_into_view_if_needed()
        await human_sleep(0.15, 0.3)

        async def _list_open() -> bool:
            return await page.evaluate("""() => {
                const sels = '[data-testid="dropdown-list"], [data-testid^="item-"], .select-dropdown-item, [role="listbox"], [role="option"], .dropdown-option';
                return Array.from(document.querySelectorAll(sels)).some(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 8 && r.height > 8;
                });
            }""")

        opened = False
        box = await trigger.bounding_box()
        if box:
            await page.mouse.click(box["x"] + max(8, min(36, box["width"] * 0.25)), box["y"] + box["height"] / 2)
            await human_sleep(0.35, 0.55)
            opened = await _list_open()

        if not opened:
            try:
                await trigger.click(timeout=1500)
            except Exception:
                try:
                    await trigger.click(force=True, timeout=1500)
                except Exception as e:
                    print(f"[!] {field_name}: не удалось открыть список ({e})")
                    return False
            await human_sleep(0.35, 0.55)
            opened = await _list_open()

        if not opened:
            print(f"[!] {field_name}: выпадающий список не открылся")
            return False

        try:
            await page.keyboard.type(str(vals[0]), delay=40)
            await human_sleep(0.45, 0.7)
        except Exception:
            pass

        async def _find_item():
            return await page.evaluate_handle("""({vals, partial}) => {
                const expected = vals.map(v => String(v).trim().toLowerCase().replace(/ё/g, 'е'));

                function vis(el) {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                }

                const items = Array.from(document.querySelectorAll(
                    '[data-testid^="item-"], .select-dropdown-item, [role="option"], .dropdown-option, li, div[class*="dropdown-item"]'
                )).filter(el => vis(el));
                let fuzzy = null;
                for (const it of items) {
                    const txt = (it.innerText || it.textContent || '').trim().toLowerCase().replace(/ё/g, 'е');
                    if (!txt || txt.length > 80) continue;
                    for (const v of expected) {
                        if (txt === v) return it;
                        if ((partial || true) && txt.includes(v) && !fuzzy) fuzzy = it;
                    }
                }
                return fuzzy;
            }""", {"vals": vals, "partial": partial})

        item_el = (await _find_item()).as_element()
        if not item_el:
            list_el = await page.query_selector('[data-testid="dropdown-list"], [role="listbox"]')
            if list_el:
                try:
                    await list_el.hover(timeout=600)
                except Exception:
                    pass
                for _ in range(30):
                    item_el = (await _find_item()).as_element()
                    if item_el:
                        break
                    await page.mouse.wheel(0, 240)
                    await asyncio.sleep(0.07)

        if not item_el:
            print(f"[!] {field_name}: не удалось найти «{vals[0]}» в списке")
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return False

        await item_el.scroll_into_view_if_needed()
        try:
            # Эмуляция полного цикла событий для React/Vue
            await item_el.evaluate("""el => {
                el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                el.click();
            }""")
            await item_el.click(timeout=2000)
        except Exception:
            try:
                await item_el.click(force=True, timeout=1500)
            except Exception as e:
                print(f"[!] {field_name}: клик по «{vals[0]}» не сработал ({e})")
                return False

        await human_sleep(0.3, 0.5)
        shown = await _read()
        if _matches(shown):
            print(f"[✓] {field_name}: «{shown or vals[0]}»")
            return True

        print(f"[!] {field_name}: ожидали «{vals[0]}», в поле «{shown or 'пусто'}»")
        return False

    async def handle_combobox_city(self, page: Page) -> bool:
        target_city = self.profile_personal.get("city", "Москва")

        already_selected = await page.evaluate("""(city) => {
            const norm = s => (s || '').toLowerCase().replace(/ё/g, 'е');
            city = norm(city);

            function vis(el) {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                return r.width > 8 && r.height > 8 && el.offsetParent !== null;
            }

            const wraps = Array.from(document.querySelectorAll(
                '.select-wrap, [data-testid="input"], div[class*="select-input"], input[placeholder*="Город"], input[name*="city"]'
            )).filter(vis);
            const leaves = wraps.filter(w => !wraps.some(o => o !== w && o.contains(w)));
            for (const w of leaves) {
                const inp = w.querySelector('input');
                let val = (inp && inp.value) ? inp.value : '';
                if (!val) {
                    const te = w.querySelector('.text-truncate, [data-testid="input"]') || w;
                    val = (te.innerText || '').trim().split('\\n')[0] || '';
                }
                val = norm(val);
                if (!val || val.length > 80) continue;
                if (val.includes('выбер') || val.includes('населенн')) continue;
                if (val.includes(city)) return true;
            }
            return false;
        }""", target_city)

        if already_selected:
            print(f"[✓] [CLOUDSURVEY] Город «{target_city}» уже выбран в форме")
            return True

        print(f"\n[i] [CLOUDSURVEY] Ввод города проживания: «{target_city}»...")

        trigger_handle = await page.evaluate_handle("""() => {
            function vis(el) {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                return r.width > 20 && r.height > 10 && el.offsetParent !== null;
            }

            const active = document.querySelector('.step.active') || document.body;
            let wraps = Array.from(active.querySelectorAll(
                '.select-wrap, div[class*="select-input"], [data-testid="input"], input[placeholder*="Город"], input[name*="city"]'
            )).filter(vis);
            wraps = wraps.filter(w => !wraps.some(o => o !== w && o.contains(w)));
            const wrap = wraps[0];
            if (!wrap) return null;
            return wrap.querySelector('[data-testid="input"], .select-input, .text-truncate, input') || wrap;
        }""")
        trigger_el = trigger_handle.as_element()

        if not trigger_el:
            print("[!] [CLOUDSURVEY] Поле города не найдено")
            return False

        if await self._pick_custom_dropdown(page, trigger_el, [target_city], "Город", partial=True):
            await asyncio.sleep(0.4)
            return True

        # === ЖЕСТКИЙ FALLBACK ДЛЯ УПРЯМЫХ ДРОПДАУНОВ ===
        print(f"[i] [CLOUDSURVEY] Запасной алгоритм выбора города: «{target_city}»")
        try:
            await trigger_el.scroll_into_view_if_needed()
            await trigger_el.click(force=True)
            await human_sleep(0.5, 0.8)
            await trigger_el.fill("")  # Гарантированная очистка
            await page.keyboard.type(target_city, delay=80)
            await human_sleep(1.0, 1.5)  # Ждем отрисовку списка

            # Явный поиск и клик по элементу списка
            clicked = await page.evaluate("""(city) => {
                const norm = s => (s || '').toLowerCase().replace(/ё/g, 'е');
                city = norm(city);
                const items = Array.from(document.querySelectorAll(
                    '[role="option"], .dropdown-item, .select-dropdown-item, li, div[class*="dropdown"], div[class*="suggestion"]'
                )).filter(el => {
                    if (!el.offsetParent) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });

                for (const item of items) {
                    const txt = norm(item.innerText || item.textContent || '');
                    if (txt === city || txt.includes(city)) {
                        item.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                        item.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                        item.click();
                        return true;
                    }
                }
                return false;
            }""", target_city)

            if not clicked:
                print("[i] [CLOUDSURVEY] Клик по списку не сработал, пробуем ArrowDown + Enter")
                await page.keyboard.press("ArrowDown")
                await human_sleep(0.2)
                await page.keyboard.press("Enter")

            await human_sleep(0.5, 1.0)
            return True
        except Exception as e:
            print(f"[!] [CLOUDSURVEY] Не удалось выбрать город: {e}")
            return False

    async def extract_question_text(self, page: Page) -> str:
        return await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let headers = Array.from(active.querySelectorAll('.question-text, .header1, .header2, div[class*="question-header"], div[class*="QuestionHeader"], div[class*="question-title"], div[class*="HeaderStyled"], h1, h2, h3, h4, p')).filter(h => h.offsetParent !== null);

            const genericPhrases = [
                'выберите подходящий вариант',
                'выберите один или несколько вариантов',
                'выберите вариант ответа',
                'укажите один или несколько вариантов',
                'выберите ответ'
            ];

            let bestText = "";

            for (let h of headers) {
                let txt = (h.innerText || '').trim().replace(/\\s+/g, ' ');
                if (txt.length > 5 && !txt.toLowerCase().includes('время опросов') && !txt.toLowerCase().includes('пожалуйста') && !txt.toLowerCase().match(/^вопрос\\s*\\d+$/)) {
                    let isGeneric = genericPhrases.some(phrase => txt.toLowerCase().includes(phrase));
                    if (!isGeneric) {
                        return txt; // Нашли хороший, конкретный текст вопроса
                    }
                    if (!bestText) {
                        bestText = txt; // Сохраняем как запасной вариант
                    }
                }
            }

            // Если нашли только общий заголовок, ищем реальный текст вопроса в соседних элементах (например, <p> после <h2>)
            if (bestText && genericPhrases.some(p => bestText.toLowerCase().includes(p))) {
                for (let h of headers) {
                    let next = h.nextElementSibling;
                    while (next) {
                        let txt = (next.innerText || '').trim().replace(/\\s+/g, ' ');
                        if (txt.length > 10 && !genericPhrases.some(p => txt.toLowerCase().includes(p))) {
                            return txt;
                        }
                        next = next.nextElementSibling;
                    }
                }
            }

            return bestText || "Выберите подходящий вариант";
        }""")

    async def handle_info_screen(self, page: Page) -> bool:
        info_text = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let interactive = active.querySelectorAll(
                'input:not([type="submit"]):not([type="button"]):not([type="hidden"]), textarea, select, button, [role="radio"], [role="checkbox"], [role="button"], .answer-item, .scale-item, div[class*="Answer"], li.choice-item, label.option-label, .LogoItem, div[class*="scale-answer"], .select-wrap, div[class*="select-input"]'
            );
            let visibleInteractive = Array.from(interactive).filter(el => {
                if (el.offsetParent === null) return false;
                if (el.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"], [class*="edgelables"]')) return false;
                let txt = (el.innerText || el.value || '').trim().toLowerCase();
                let navKws = ['далее', 'вперед', 'продолжить', 'начать', 'старт', 'понятно', 'согласен', 'принимаю'];
                if (navKws.some(kw => txt === kw || txt.includes(kw))) return false;
                return true;
            });
            if (visibleInteractive.length > 0) return null;
            let textNodes = Array.from(active.querySelectorAll('h1, h2, h3, h4, p, div, span, b, strong'))
                .filter(el => el.offsetParent !== null)
                .map(el => (el.innerText || '').trim())
                .filter(t => t.length > 4);
            let unique = [...new Set(textNodes)].filter(t =>
                !['далее', 'вперед', 'продолжить', 'время опросов', 'пожалуйста'].some(w => t.toLowerCase() === w)
            );
            return unique.length > 0 ? unique.join('\\n') : null;
        }""")
        if not info_text:
            return False
        print("\n" + "=" * 60)
        print("📄 [ИНФОРМАЦИОННЫЙ ЭКРАН / ОЗНАКОМЛЕНИЕ С МАТЕРИАЛОМ]:")
        for line in info_text.split('\n')[:6]:
            print(f"   ℹ️  {line}")
        print("=" * 60)
        self.brain.ad_context = info_text
        await human_sleep(2.5, 4.0)
        await self.click_next(page)
        return True

    async def handle_progressive_blocks(self, page: Page) -> bool:
        total_handled = 0
        max_substeps = 25
        for _ in range(max_substeps):
            block_data = await page.evaluate("""() => {
                let active = document.querySelector('.step.active') || document.body;
                let blockSelector = [
                    'div[class*="questionrouter-container"]',
                    'div[class*="QuestionContainerStyled"]',
                    'div[class*="styled__BlockStyled"]',
                    'div[class*="styled_BlockStyled"]',
                    'div[class*="blk-answer-block"]',
                    'div[class*="QuestionBlock"]',
                    'div[class*="question-block"]',
                    'div[class*="CellContainer"]',
                    'div.holder-block',
                    'div[id*="demo-b"]',
                    'div[id*="matrix-b"]'
                ].join(', ');
                let candidateCards = Array.from(active.querySelectorAll(blockSelector)).filter(el => {
                    if (el.offsetParent === null) return false;
                    let cls = (el.className || '').toLowerCase();
                    if (cls.includes('edgelabel') || cls.includes('labelsstyled') || cls.includes('edge-label')) return false;
                    return el.querySelectorAll(
                        'div[class*="scale-item"], div[class*="scale-answer-content"], div[class*="AnswerStyled"], li.choice-item, .answer-item, .scale-item, label.option-label, .LogoItem, input[type="text"]:not([placeholder*="списка"]):not([placeholder*="город"]), input[type="number"], input[inputmode="numeric"], textarea'
                    ).length > 0;
                });
                let questionBlocks = candidateCards.filter(c => !candidateCards.some(other => other !== c && c.contains(other)));
                if (questionBlocks.length === 0) return null;
                questionBlocks.forEach((b, i) => b.setAttribute('data-dyn-id', String(i)));

                const genericPhrases = [
                    'выберите подходящий вариант',
                    'выберите один или несколько вариантов',
                    'выберите вариант ответа',
                    'укажите один или несколько вариантов'
                ];

                for (let idx = 0; idx < questionBlocks.length; idx++) {
                    let blk = questionBlocks[idx];
                    let isMarked = blk.getAttribute('data-bot-answered') === 'true';
                    let itemSelector = [
                        'div[class*="scale-answer-content"]',
                        'div[class*="scale-item"]',
                        'div[class*="styled__AnswerStyled"]',
                        'div[class*="styled_AnswerStyled"]',
                        'div[class*="AnswerRow"]',
                        'li.choice-item',
                        'div.choice-item',
                        'div[class*="LogoItem"]',
                        'label.option-label',
                        '.answer-item',
                        '.scale-item',
                        '.LogoItem'
                    ].join(', ');
                    let candidates = Array.from(blk.querySelectorAll(itemSelector)).filter(n => {
                        if (n.offsetParent === null) return false;
                        let style = window.getComputedStyle(n);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                        let rect = n.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return false;
                        if (n.className.includes('btn') && !n.className.includes('scale')) return false;
                        if (n.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"], [class*="edgelables"]')) return false;
                        return (n.innerText || '').trim().length > 0;
                    });
                    let leafItems = candidates.filter(c => !candidates.some(other => other !== c && c.contains(other)));
                    let textInput = blk.querySelector('textarea, input[type="text"]:not([placeholder*="списка"]):not([placeholder*="город"]), input[type="number"], input[inputmode="numeric"]');
                    if (textInput && (textInput.id.includes('_other') || textInput.name.includes('_other'))) textInput = null;
                    let hasTextInput = textInput !== null && textInput.offsetParent !== null;
                    let isAnswered = isMarked;
                    if (!isAnswered) {
                        if (blk.querySelector('input:checked') !== null || blk.querySelector('[aria-checked="true"]') !== null || blk.querySelector('[data-selected="true"]') !== null) {
                            isAnswered = true;
                        }
                        if (!isAnswered) {
                            for (let it of leafItems) {
                                let cls = (it.className || '').toLowerCase();
                                let parentCls = (it.parentElement?.className || '').toLowerCase();
                                let grandCls = (it.parentElement?.parentElement?.className || '').toLowerCase();
                                let hasSel = (c) => c.includes('selected') || c.includes('checked') || c.includes('answer-active') || c.includes('active-item');
                                let isSelected = hasSel(cls) || hasSel(parentCls);
                                if (!grandCls.includes('step') && hasSel(grandCls)) {
                                    isSelected = true;
                                }
                                if (isSelected) {
                                    isAnswered = true;
                                    break;
                                }
                            }
                        }
                        if (hasTextInput && textInput && textInput.value && textInput.value.trim().length > 0) {
                            isAnswered = true;
                        }
                    }
                    if (!isAnswered) {
                        let mainHeaderEl = Array.from(active.querySelectorAll('h1, h2, h3, h4, .question-text, div[class*="question-header"], div[class*="HeaderStyled"], .page-header .header')).find(h => {
                            if (h.offsetParent === null) return false;
                            return !h.closest(blockSelector);
                        });
                        let mainHeader = mainHeaderEl ? (mainHeaderEl.innerText || '').trim() : '';

                        // Фильтрация главного заголовка от общих фраз
                        let isMainGeneric = genericPhrases.some(p => mainHeader.toLowerCase().includes(p));
                        if (isMainGeneric) mainHeader = '';

                        let titleEl = Array.from(blk.querySelectorAll(
                            'div[class*="question-content"], div[class*="question-header"], div[class*="Header"], div[class*="title"], div[class*="question-text"], .question-text, div[style*="font-weight"], h1, h2, h3, h4, p, b, strong'
                        )).find(t => {
                            if (t.closest(itemSelector) || t.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"]')) return false;
                            let txt = (t.innerText || '').trim();
                            return txt.length > 2 && !txt.toLowerCase().includes('пожалуйста') && !txt.toLowerCase().includes('оцените по шкале') && !genericPhrases.some(p => txt.toLowerCase().includes(p));
                        });
                        let blockTitle = titleEl ? (titleEl.innerText || '').trim() : '';

                        let finalQ = '';
                        if (mainHeader && blockTitle && mainHeader !== blockTitle) {
                            finalQ = `${mainHeader} -> ${blockTitle}`;
                        } else {
                            finalQ = blockTitle || mainHeader || `Вопрос ${idx + 1}`;
                        }

                        let options = leafItems.map(i => {
                            let directText = (i.innerText || '').trim();
                            let cleanDirect = directText.replace(/^\\d+[\\.\\)\\-]\\s*/, '').trim();
                            let attrCandidate = '';
                            for (let el of [i, ...i.querySelectorAll('*')]) {
                                let val = el.getAttribute('data-name') || el.getAttribute('data-title') || el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || '';
                                val = val.trim();
                                if (val.length > 1 && !/^[0-9a-f]{1,4}$/i.test(val) && !val.toLowerCase().startsWith('http')) {
                                    attrCandidate = val;
                                    break;
                                }
                            }
                            if (attrCandidate) return attrCandidate;
                            if (cleanDirect.length > 0) return cleanDirect;
                            return directText || 'Вариант';
                        });
                        let isMulti = blk.querySelector('input[type="checkbox"], li[data-question-type="CheckBox"]') !== null || (blk.innerText || '').toLowerCase().includes('все подходящие');
                        return {
                            dynId: String(idx),
                            questionText: finalQ,
                            options: options,
                            hasTextInput: hasTextInput,
                            isMulti: isMulti
                        };
                    }
                }
                return {allAnswered: true};
            }""")

            if not block_data:
                return False
            if block_data.get("allAnswered"):
                if total_handled > 0:
                    await human_sleep(0.5, 0.8)
                await self.click_next(page)
                return True

            if block_data["hasTextInput"] and not block_data["options"]:
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                print(
                    f"\n[№ {self.brain.stats.get('total_answered', 0)}] ОТКРЫТЫЙ ВОПРОС: {block_data['questionText']}")
                ans_text = self.brain.answer_open_text(block_data['questionText'])
                print(f"✍️  [ВВОД]: {ans_text}")
                await page.evaluate("""({dynId, text}) => {
                    let active = document.querySelector('.step.active') || document.body;
                    let blk = active.getAttribute('data-dyn-id') === String(dynId) ? active : active.querySelector(`[data-dyn-id="${dynId}"]`);
                    if (blk) {
                        let inp = blk.querySelector('textarea, input[type="text"], input[type="number"], input[inputmode="numeric"]');
                        if (inp) {
                            inp.focus();
                            let type = (inp.getAttribute('type') || '').toLowerCase();
                            let mode = (inp.getAttribute('inputmode') || '').toLowerCase();
                            if (type === 'number' || mode === 'numeric') {
                                text = text.replace(/\\D/g, '');
                                if (!text) text = "21";
                            }
                            inp.value = text;
                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                        blk.setAttribute('data-bot-answered', 'true');
                    }
                }""", {"dynId": block_data["dynId"], "text": ans_text})
                total_handled += 1
                await human_sleep(0.4, 0.7)

            elif len(block_data["options"]) >= 2:
                print("\n" + "=" * 60)
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                print(f"[№ {self.brain.stats.get('total_answered', 0)}] ВОПРОС: {block_data['questionText']}")
                print(f"[i] ТИП: {'Множественный выбор' if block_data['isMulti'] else 'Одиночный выбор'}")
                print(f"[*] ВСЕГО ВАРИАНТОВ: {len(block_data['options'])}")
                for idx, text in enumerate(block_data['options'][:15]):
                    print(f"    [{idx}] {text}")
                decision = self.brain.decide(block_data['questionText'], block_data['options'], block_data['isMulti'])
                selected_names = [block_data['options'][i] for i in decision.selected_indices if
                                  i < len(block_data['options'])]
                print(
                    f"[LLM] ВЫБРАНО ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_names[:8]}")
                print(f"[LLM] ЛОГИКА: {decision.reasoning}")
                print("=" * 60)
                for sel_idx in decision.selected_indices:
                    await page.evaluate("""({dynId, optIdx}) => {
                        let active = document.querySelector('.step.active') || document.body;
                        let blk = active.getAttribute('data-dyn-id') === String(dynId) ? active : active.querySelector(`[data-dyn-id="${dynId}"]`);
                        if (blk) {
                            let itemSelector = [
                                'div[class*="scale-answer-content"]',
                                'div[class*="scale-item"]',
                                'div[class*="styled__AnswerStyled"]',
                                'div[class*="styled_AnswerStyled"]',
                                'div[class*="AnswerRow"]',
                                'li.choice-item',
                                'div.choice-item',
                                'div[class*="LogoItem"]',
                                'label.option-label',
                                '.answer-item',
                                '.scale-item',
                                '.LogoItem'
                            ].join(', ');
                            let candidates = Array.from(blk.querySelectorAll(itemSelector)).filter(n => {
                                if (n.offsetParent === null) return false;
                                let style = window.getComputedStyle(n);
                                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                                let rect = n.getBoundingClientRect();
                                if (rect.width === 0 || rect.height === 0) return false;
                                if (n.className.includes('btn') && !n.className.includes('scale')) return false;
                                if (n.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"], [class*="edgelables"]')) return false;
                                return true;
                            });
                            let leafItems = candidates.filter(c => !candidates.some(other => other !== c && c.contains(other)));
                            if (leafItems[optIdx]) {
                                let target = leafItems[optIdx];
                                let clickTarget = target.querySelector('input, div[class*="ContentContainer"], div[class*="contentOnlyAnswer"], div[class*="scale-answer-content"], span, label, div.circle, div.radiobox, div.checkbox') || target;
                                clickTarget.scrollIntoView({behavior: 'smooth', block: 'center'});
                                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                                    clickTarget.dispatchEvent(new MouseEvent(evt, {
                                        bubbles: true,
                                        cancelable: true,
                                        view: window
                                    }));
                                });
                                if (target !== clickTarget) {
                                    target.dispatchEvent(new MouseEvent('click', {
                                        bubbles: true,
                                        cancelable: true,
                                        view: window
                                    }));
                                }
                                if (clickTarget.click) clickTarget.click();
                                target.classList.add('selected');
                                let inp = target.querySelector('input');
                                if (inp) {
                                    inp.checked = true;
                                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                                }
                            }
                            blk.setAttribute('data-bot-answered', 'true');
                        }
                    }""", {"dynId": block_data["dynId"], "optIdx": sel_idx})
                    await human_sleep(0.3, 0.5)
                total_handled += 1
                await human_sleep(0.5, 0.8)

        if total_handled > 0:
            await human_sleep(0.6, 1.0)
            await self.click_next(page)
            return True
        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:

        # === Обработка стартовых страниц типа "Expertnoe Mnenie" ===
        has_start_page = await page.evaluate("""() => {
            let txt = document.body.innerText.toLowerCase();
            let hasBtn = Array.from(document.querySelectorAll('button, [role="button"]')).some(el => {
                if (!el.offsetParent) return false;
                let t = (el.innerText || '').trim().toLowerCase();
                return t === 'продолжить' || t === 'начать' || t === 'начать опрос';
            });
            return hasBtn && (txt.includes('внимательно') || txt.includes('рейтинг') || txt.includes('проверочные'));
        }""")

        if has_start_page:
            print("\n[i] [CLOUDSURVEY] Стартовая страница. Нажимаем «Продолжить»...")
            await page.evaluate("""() => {
                let btn = Array.from(document.querySelectorAll('button, [role="button"], div, span')).find(el => {
                    if (!el.offsetParent) return false;
                    let t = (el.innerText || '').trim().toLowerCase();
                    return t === 'продолжить' || t === 'начать';
                });
                if (btn) {
                    btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                    btn.click();
                }
            }""")
            await human_sleep(2.0, 3.0)

            return True

        try:
            await page.wait_for_function("""() => {
                let roots = document.querySelectorAll('#root, #app, #__next, main, .main');
                for (let r of roots) {
                    if (r.innerHTML.trim() === '') return false;
                }
                return document.body.innerText.trim().length > 10 || document.querySelectorAll('button, input').length > 0;
            }""", timeout=6000)
            await asyncio.sleep(0.5)
        except Exception:
            pass

        kind = await self._visible_step_kind(page)
        if kind.get("isCity") and not kind.get("isDate"):
            handled_city = await self.handle_combobox_city(page)
            if handled_city:
                await human_sleep(1.0, 1.5)
                await self.click_next(page)
                await human_sleep(2.0, 3.0)
                return True

        if (kind.get("isDate") or kind.get("isGender") or kind.get("isIntro")) and not kind.get("isCity"):
            handled = await self.handle_composite_demographics(page)
            if handled:
                await human_sleep(2.0, 3.0)
                return True

        if await self.handle_info_screen(page):
            await human_sleep(1.5, 2.5)
            return True

        if await self.handle_progressive_blocks(page):
            await human_sleep(1.5, 2.5)
            return True

        question_text = await self.extract_question_text(page)

        dropdown_data = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let select = Array.from(active.querySelectorAll('select')).find(s => {
                if (s.disabled) return false;
                let isVis = s.offsetParent !== null;
                let isHiddenSelect2 = s.classList.contains('select2-hidden-accessible') || s.classList.contains('ss-search-select');
                if (!isVis && !isHiddenSelect2) return false;
                let selectedOpts = Array.from(s.selectedOptions).filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'));
                return selectedOpts.length === 0;
            });
            if (select) {
                let options = Array.from(select.querySelectorAll('option'))
                    .filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'))
                    .map(o => o.innerText.replace(/\\s+/g, ' ').trim());
                if (options.length > 0) {
                    select.setAttribute('data-bot-target-select', 'true');
                    return {options: options, isMulti: select.multiple};
                }
            }
            return null;
        }""")

        if dropdown_data:
            options_texts = dropdown_data["options"]
            is_multi = dropdown_data["isMulti"]
            print("\n" + "=" * 60)
            try:
                self.brain.stats['total_answered'] += 1
                print(f"[№ {self.brain.stats['total_answered']}] ВЫПАДАЮЩИЙ СПИСОК: {question_text}")
            except Exception:
                print(f"[?] ВЫПАДАЮЩИЙ СПИСОК: {question_text}")
            print(f"[*] ВСЕГО ВАРИАНТОВ: {len(options_texts)}")
            for idx, text in enumerate(options_texts[:15]):
                print(f"    [{idx}] {text}")
            decision = self.brain.decide(question_text, options_texts, is_multiselect=is_multi)
            chosen_indices = decision.selected_indices if decision.selected_indices else [0]
            selected_names = [options_texts[i] for i in chosen_indices if i < len(options_texts)]
            print(f"[LLM] ВЫБРАНО ({len(chosen_indices)}): {chosen_indices} -> {selected_names[:8]}")
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
                    }
                }""", sel_idx)
                await human_sleep(0.3, 0.6)
            await page.evaluate("""() => {
                let sel = document.querySelector('select[data-bot-target-select="true"]');
                if (sel) sel.removeAttribute('data-bot-target-select');
            }""")
            await human_sleep(0.8, 1.4)
            await self.click_next(page)
            return True

        raw_options = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let selector = [
                'div[class*="styled__AnswerStyled"]',
                'div[class*="scale-item"]',
                'div[class*="scale-answer"]',
                'div[class*="AnswerRow"]',
                'div[class*="answer-row"]',
                'li.choice-item',
                'div.choice-item',
                'div[class*="LogoItem"]',
                'div[class*="GridItem"]',
                'label.option-label',
                '.answer-item',
                '.scale-item',
                '.LogoItem',
                '.grid__cell'
            ].join(', ');
            let candidates = Array.from(active.querySelectorAll(selector)).filter(el => {
                if (el.offsetParent === null) return false;
                let style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                let rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return false;
                let txt = (el.innerText || '').trim();
                let hasImgAttr = Array.from(el.querySelectorAll('img')).some(img => img.getAttribute('title') || img.getAttribute('alt') || img.getAttribute('data-template'));
                if ((!txt && !hasImgAttr) || txt.length > 100) return false;
                let cls = (el.className || '').toLowerCase();
                if (cls.includes('button') || cls.includes('btn') || (cls.includes('container') && !cls.includes('scale-item'))) return false;
                if (el.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"], [class*="edgelables"]')) return false;
                return true;
            });
            let leafOptions = candidates.filter(c => !candidates.some(other => other !== c && c.contains(other)));
            if (leafOptions.length < 2) {
                let generic = Array.from(active.querySelectorAll('button, [role="radio"], [role="checkbox"], [role="button"], div[class*="radio"], div[class*="Radio"], div[class*="option"], div[class*="Option"], div[class*="answer"], div[class*="Answer"], div[class*="choice"], div[class*="Choice"], .btn')).filter(el => {
                    if (el.offsetParent === null) return false;
                    let style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    let txt = (el.innerText || '').trim().toLowerCase();
                    if (!txt || txt.length > 100) return false;
                    let kws = ['далее', 'вперед', 'продолжить', 'начать', 'старт', 'получить', 'выберите ответ', 'назад'];
                    if (kws.some(kw => txt === kw || txt.includes(kw))) return false;
                    return true;
                });
                leafOptions = generic.filter(c => !generic.some(other => other !== c && c.contains(other)));
            }
            if (leafOptions.length < 2) return [];
            return leafOptions.map((node, idx) => {
                let directText = (node.innerText || '').trim();
                let cleanDirect = directText.replace(/^\\d+[\\.\\)\\-]\\s*/, '').trim();
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
        }""")

        if not raw_options:
            return await self.handle_open_text_question(page, question_text)

        options_texts = [o["text"] for o in raw_options]
        is_multi = (await page.query_selector(
            "input[type='checkbox'], li[data-question-type='CheckBox']")) is not None or any(
            w in body_lower for w in ["несколько", "все подходящие", "отметьте"])

        print("\n" + "=" * 60)
        try:
            self.brain.stats['total_answered'] += 1
            print(f"[№ {self.brain.stats['total_answered']}] ВОПРОС: {question_text}")
        except Exception:
            print(f"[?] ВОПРОС: {question_text}")
        print(f"[i] ТИП: {'Множественный выбор' if is_multi else 'Одиночный выбор'}")
        print(f"[*] ВСЕГО ВАРИАНТОВ: {len(options_texts)}")
        for idx, text in enumerate(options_texts[:15]):
            print(f"    [{idx}] {text}")

        decision = self.brain.decide(question_text, options_texts, is_multi)
        selected_names = [options_texts[i] for i in decision.selected_indices if i < len(options_texts)]
        print(f"[LLM] ВЫБРАНО ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_names[:8]}")
        print(f"[LLM] ЛОГИКА: {decision.reasoning}")
        print("=" * 60)

        for idx in decision.selected_indices:
            opt_handle = await page.evaluate_handle("""(optIdx) => {
                let active = document.querySelector('.step.active') || document.body;
                let selector = 'div[class*="styled__AnswerStyled"], div[class*="scale-item"], div[class*="scale-answer"], div[class*="AnswerRow"], div[class*="answer-row"], li.choice-item, div.choice-item, div[class*="LogoItem"], div[class*="GridItem"], label.option-label, .answer-item, .scale-item, .LogoItem, .grid__cell';
                let candidates = Array.from(active.querySelectorAll(selector)).filter(el => {
                    if (el.offsetParent === null) return false;
                    let style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    let rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return false;
                    if (el.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"]')) return false;
                    return true;
                });
                let leafOptions = candidates.filter(c => !candidates.some(other => other !== c && c.contains(other)));
                if (leafOptions.length < 2) {
                    let generic = Array.from(active.querySelectorAll('button, [role="radio"], [role="checkbox"], [role="button"], div[class*="radio"], div[class*="Radio"], div[class*="option"], div[class*="Option"], div[class*="answer"], div[class*="Answer"], div[class*="choice"], div[class*="Choice"], .btn')).filter(el => {
                        if (el.offsetParent === null) return false;
                        let style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0' || el.disabled) return false;
                        let txt = (el.innerText || '').trim().toLowerCase();
                        if (!txt || txt.length > 100) return false;
                        let kws = ['далее', 'вперед', 'продолжить', 'начать', 'старт', 'получить', 'выберите ответ', 'назад'];
                        if (kws.some(kw => txt === kw || txt.includes(kw))) return false;
                        return true;
                    });
                    leafOptions = generic.filter(c => !generic.some(other => other !== c && c.contains(other)));
                }
                let target = leafOptions[optIdx];
                if (!target) return null;
                return target.querySelector('input, div[class*="ContentContainer"], div[class*="contentOnlyAnswer"], div[class*="scale-answer-content"], span, label, div.circle, div.radiobox, div.checkbox') || target;
            }""", idx)

            if not await opt_handle.evaluate("el => !el"):
                await opt_handle.scroll_into_view_if_needed()
                await opt_handle.evaluate("""el => {
                    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                        el.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                    });
                    if (el.click) el.click();
                }""")
                try:
                    await opt_handle.click(force=True, timeout=1500)
                except Exception:
                    pass
                await human_sleep(0.3, 0.5)

        await human_sleep(0.8, 1.4)
        await self.click_next(page)
        return True

    async def handle_open_text_question(self, page: Page, question_text: str) -> bool:
        has_real_input = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let inps = Array.from(active.querySelectorAll("input[type='text'], input[type='number'], input[inputmode='numeric'], input:not([type]), textarea, div[contenteditable='true']")).filter(el => {
                if (el.offsetParent === null) return false;
                let idStr = (el.id || '').toLowerCase();
                let nameStr = (el.name || '').toLowerCase();
                if (idStr.includes('_other') || nameStr.includes('_other')) return false;
                let cell = el.closest('[data-rowidx], .grid__cell, tr, .question__list-item, .pr-row, div.ss-table-row, label, .answer-item');
                if (cell && cell.querySelector('input[type="radio"], input[type="checkbox"]')) return false;
                let ph = (el.placeholder || '').toLowerCase();
                let cls = (el.className || '').toLowerCase();
                let parentCls = (el.parentElement ? el.parentElement.className : '').toLowerCase();
                if (ph.includes('день') || ph.includes('месяц') || ph.includes('год') || ph.includes('списка') || ph.includes('город')) return false;
                if (cls.includes('combobox') || parentCls.includes('combobox') || cls.includes('select') || parentCls.includes('select')) return false;
                return true;
            });
            return inps.length > 0;
        }""")
        if not has_real_input:
            return False

        text_inputs = await page.query_selector_all(
            "input[type='text'], input[type='number'], input[inputmode='numeric'], input:not([type]), textarea, div[contenteditable='true']")
        visible_inputs = [inp for inp in text_inputs if await inp.is_visible()]
        if not visible_inputs:
            return False

        target_input = visible_inputs[0]
        answer_text = self.brain.answer_open_text(question_text)
        print(f"\n[?] ОТКРЫТЫЙ ВОПРОС: {question_text}\n✍️  [ВВОД ТЕКСТА]: {answer_text}")

        await target_input.scroll_into_view_if_needed()
        await target_input.click(force=True)
        await human_sleep(0.3, 0.6)
        await page.evaluate("""({inp, txt}) => {
            let type = (inp.getAttribute('type') || '').toLowerCase();
            let mode = (inp.getAttribute('inputmode') || '').toLowerCase();
            if (type === 'number' || mode === 'numeric') {
                txt = txt.replace(/\\D/g, '');
                if (!txt) txt = "21";
            }
            inp.value = '';
            inp.focus();
        }""", {"inp": target_input, "txt": answer_text})

        input_type = await target_input.get_attribute("type")
        if input_type == "number":
            answer_text = re.sub(r'\D', '', answer_text)
            if not answer_text:
                answer_text = str(self.profile_personal.get("age", 21))

        await page.keyboard.type(answer_text, delay=random.randint(50, 90))
        await human_sleep(0.6, 1.2)
        await self.click_next(page)
        await human_sleep(2.0, 3.5)
        return True