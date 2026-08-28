import asyncio
import random
import re
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep
from engines.mixins import ProgressiveBlocksMixin

from engines.js_snippets import (
    JS_FIND_FALLBACK_NEXT_BTN,
    JS_CHECK_DEMOGRAPHICS,
    JS_MARK_DATE_CONTAINERS,
    JS_EXTRACT_QUESTION_TEXT,
    JS_CHECK_INFO_SCREEN
)


class CloudSurveyEngine(ProgressiveBlocksMixin, BaseSurveyEngine):
    async def click_next(self, page: Page) -> bool:
        selectors = [
            "input[name='_NNext']",
            ".mrNext",
            "button[data-testid='next-btn']",
            "button[data-test='next-btn']",
            ".page__button-next",
            "#nextSurvey",
            "button[data-testid='next-survey']",
            "button#__next",
            "button[id='__next']",
            "#processingGoForwardBtn",
            ".next-button",
            "button:has-text('ДАЛЕЕ')",
            "button:has-text('Далее')",
            "div:has-text('ДАЛЕЕ')",
            "div:has-text('Далее')"
        ]

        for sel in selectors:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=500):
                    await locator.scroll_into_view_if_needed()
                    await locator.click(force=True)
                    print(f"[i] [CLOUDSURVEY] Нажата кнопка перехода: {sel}")
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
            except Exception:
                pass
            print(f"[i] [CLOUDSURVEY] Нажата кнопка: «{txt or 'Далее'}»")
            return True

        return False

    async def handle_composite_demographics(self, page: Page) -> bool:
        has_intro = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let text = (active.innerText || '').toLowerCase();
            return text.includes('время опросов');
        }""")

        if has_intro:
            print("\n" + "=" * 50)
            print("[i] [CLOUDSURVEY] Приветственный экран. Нажимаем «Начать опрос»...")
            print("=" * 50)
            await self.click_next(page)
            return True

        has_gender_el = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let text = (active.innerText || '').toLowerCase();
            let hasRadio = active.querySelectorAll('input[type="radio"], div[class*="radio"], div[class*="Radio"], .answer-item, .choice-item, div.circle').length > 0;
            return (text.includes('мужской') || text.includes('женский')) && hasRadio;
        }""")

        has_date_el = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            return active.querySelectorAll('.select-wrap, div[class*="select-input"], div[class*="DropDown_container"], select').length >= 2;
        }""")

        if has_gender_el:
            print("\n" + "=" * 50)
            print("[i] [CLOUDSURVEY] Заполнение профиля: Пол...")
            print("=" * 50)
            target_gender = self.profile_personal.get("gender", "Мужской")
            await page.evaluate("""(gender) => {
                let active = document.querySelector('.step.active') || document.body;
                let elements = Array.from(active.querySelectorAll('label, div[class*="radio"], div[class*="Radio"], div[class*="answer"], span, button, .answer-item, .choice-item')).filter(el => {
                    if (el.getBoundingClientRect().height === 0) return false;
                    let txt = (el.innerText || '').trim().toLowerCase();
                    return txt === gender.toLowerCase() || txt.startsWith(gender.toLowerCase());
                });
                if (elements.length > 0) {
                    elements.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
                    let target = elements[0];
                    let inp = target.querySelector('input[type="radio"]') || target;
                    if (inp && inp.click) inp.click();
                    target.classList.add('selected');
                    if (target.parentElement) target.parentElement.classList.add('selected');
                }
            }""", target_gender)
            print(f"[i] Пол выбран: «{target_gender}»")
            await human_sleep(0.3, 0.6)

        if has_date_el:
            print("\n" + "=" * 50)
            print("[i] [CLOUDSURVEY] Заполнение профиля: Дата рождения...")
            print("=" * 50)

            day_val = str(int(self.profile_personal.get("birth_day", "27")))
            month_int = int(self.profile_personal.get("birth_month", "6"))
            year_val = str(self.profile_personal.get("birth_year", "2005"))

            month_names_ru = [
                "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
            ]
            target_month_name = month_names_ru[month_int - 1] if 1 <= month_int <= 12 else "Июнь"

            await page.evaluate(JS_MARK_DATE_CONTAINERS)

            targets = [
                ("День", "0", [day_val, f"{int(day_val):02d}"]),
                ("Месяц", "1", [target_month_name, target_month_name.lower(), str(month_int), f"{month_int:02d}"]),
                ("Год", "2", [year_val])
            ]

            for field_name, t_idx, vals in targets:
                opened = await page.evaluate("""(idx) => {
                    let el = document.querySelector(`[data-bot-date-target="${idx}"]`);
                    if (el) {
                        if (document.activeElement) document.activeElement.blur();
                        el.scrollIntoView({behavior: 'smooth', block: 'center'});

                        let trigger = el.querySelector('.text-truncate, [data-testid="input"], .select-input, .select-control, input') || el;

                        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                            trigger.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                        });
                        if (trigger.click) trigger.click();
                        return true;
                    }
                    return false;
                }""", t_idx)

                if opened:
                    await human_sleep(0.5, 0.8)

                    opt_clicked = await page.evaluate("""(vals) => {
                        let options = Array.from(document.querySelectorAll('.select-dropdown-item, .dropdown-option, .grid-option, [role="option"], option, li')).filter(el => el.getBoundingClientRect().height > 0);
                        for (let opt of options) {
                            let txt = (opt.innerText || '').trim().toLowerCase();

                            if (vals.some(v => {
                                let vt = String(v).toLowerCase();
                                return txt === vt || txt === vt + ' г.' || txt === vt + ' год';
                            })) {
                                opt.scrollIntoView({behavior: 'smooth', block: 'center'});

                                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                                    opt.dispatchEvent(new MouseEvent(evt, {
                                        bubbles: true,
                                        cancelable: true,
                                        view: window
                                    }));
                                });
                                if (opt.click) opt.click();

                                if (opt.tagName === 'OPTION') {
                                    let sel = opt.closest('select');
                                    if (sel) {
                                        sel.value = opt.value;
                                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                                        if (window.jQuery) window.jQuery(sel).trigger('change');
                                    }
                                }
                                return true;
                            }
                        }
                        return false;
                    }""", vals)

                    if not opt_clicked:
                        await page.evaluate("""({idx, val}) => {
                            let el = document.querySelector(`[data-bot-date-target="${idx}"]`);
                            if (el) {
                                let inp = el.querySelector('input:not([type="hidden"])');
                                if (inp && !inp.disabled && !inp.readOnly) {
                                    inp.value = val;
                                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                                    inp.blur();
                                }
                            }
                        }""", {"idx": t_idx, "val": str(vals[0])})

                    print(f"[✓] {field_name}: «{vals[0]}»")
                    await human_sleep(0.3, 0.6)

        cb_handle = await page.evaluate_handle("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let label = Array.from(active.querySelectorAll('label')).find(l => l.querySelector('input[type="checkbox"]'));
            if (label && label.getBoundingClientRect().height > 0) return label;
            return active.querySelector('input[type="checkbox"]');
        }""")

        if not await cb_handle.evaluate("el => !el"):
            is_checked = await page.evaluate("""() => {
                let active = document.querySelector('.step.active') || document.body;
                let cb = active.querySelector('input[type="checkbox"]');
                return cb ? cb.checked : false;
            }""")
            if not is_checked:
                await cb_handle.scroll_into_view_if_needed()
                await cb_handle.click(force=True)
                await human_sleep(0.3, 0.5)

        await human_sleep(0.5, 0.8)
        await self.click_next(page)
        return True

    async def handle_combobox_city(self, page: Page) -> bool:
        target_city = self.profile_personal.get("city", "Москва")
        already_selected = await page.evaluate("""(city) => {
            let active = document.querySelector('.step.active') || document.body;
            let inputs = Array.from(active.querySelectorAll('input')).filter(el => el.offsetParent !== null);
            for (let inp of inputs) {
                if (inp.value && inp.value.toLowerCase().includes(city.toLowerCase())) return true;
            }
            let containers = Array.from(active.querySelectorAll('div[class*="ComboBox"], div[class*="combobox"], div[class*="select"], div[class*="Select"]')).filter(el => el.offsetParent !== null);
            for (let c of containers) {
                if (c.innerText && c.innerText.toLowerCase().includes(city.toLowerCase())) return true;
            }
            return false;
        }""", target_city)

        if already_selected:
            print(f"[✓] [CLOUDSURVEY] Город «{target_city}» уже выбран в форме")
            return True

        clicked = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let container = Array.from(active.querySelectorAll('div[class*="select"], div[class*="Select"], div[class*="combo"], .select2-selection, input[type="text"], input:not([type])')).find(el => el.getBoundingClientRect().height > 0 && window.getComputedStyle(el).visibility !== 'hidden' && !el.disabled);
            if (container) {
                container.scrollIntoView({behavior: 'smooth', block: 'center'});
                container.click();
                return true;
            }
            return false;
        }""")

        if not clicked:
            return False

        print(f"\n[i] [CLOUDSURVEY] Ввод города проживания: «{target_city}»...")
        await human_sleep(0.5, 1.0)

        await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let inps = Array.from(active.querySelectorAll('input[type="search"], input[type="text"], input:not([type])')).filter(el => el.getBoundingClientRect().height > 0 && !el.disabled);
            if (inps.length > 0) {
                inps[inps.length - 1].focus();
                inps[inps.length - 1].value = '';
            }
        }""")

        await page.keyboard.type(target_city, delay=random.randint(50, 90))
        await human_sleep(1.5, 2.0)

        suggestion_selectors = [
            f"xpath=//div[contains(@class, 'dropdown') or contains(@class, 'option') or contains(@class, 'item') or self::li][contains(normalize-space(), '{target_city}')]",
            f"xpath=//*[contains(normalize-space(), '{target_city}') and (contains(@class, 'dropdown') or contains(@class, 'option') or contains(@class, 'select'))]",
            f"xpath=//div[contains(@class, 'option') or contains(@class, 'item') or self::li][contains(normalize-space(), '{target_city}')]",
            f"xpath=(//*[contains(normalize-space(), '{target_city}')])[last()]"
        ]

        opt_clicked = False
        for s_sel in suggestion_selectors:
            try:
                s_el = await page.wait_for_selector(s_sel, state="visible", timeout=1500)
                if s_el:
                    await s_el.scroll_into_view_if_needed()
                    await s_el.click(force=True)
                    print(f"[✓] [CLOUDSURVEY] Город «{target_city}» выбран из подсказок")
                    opt_clicked = True
                    await asyncio.sleep(1.0)
                    break
            except Exception:
                continue

        if not opt_clicked:
            await page.keyboard.press("Enter")
            print(f"[✓] [CLOUDSURVEY] Город «{target_city}» подтвержден через Enter")
            await asyncio.sleep(0.8)

        return True

    async def extract_question_text(self, page: Page) -> str:
        return await page.evaluate(JS_EXTRACT_QUESTION_TEXT)

    async def handle_info_screen(self, page: Page) -> bool:
        info_text = await page.evaluate(JS_CHECK_INFO_SCREEN)

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

    # handle_progressive_blocks ТЕПЕРЬ ПОДТЯГИВАЕТСЯ ИЗ ProgressiveBlocksMixin!

    async def process_step(self, page: Page, body_lower: str) -> bool:
        try:
            await page.wait_for_function("""() => {
                let roots = document.querySelectorAll('#root, #app, #__next, main, .main, .pythia-surveys-root');
                for (let r of roots) {
                    if (r.innerHTML.trim() === '') return false;
                }
                return document.body.innerText.trim().length > 10 || document.querySelectorAll('button, input').length > 0;
            }""", timeout=6000)
            await asyncio.sleep(0.5)
        except Exception:
            pass

        has_demog = await page.evaluate(JS_CHECK_DEMOGRAPHICS)

        if has_demog:
            handled = await self.handle_composite_demographics(page)
            if handled:
                await human_sleep(2.0, 3.0)
                return True

        is_city_question = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let txt = (active.innerText || '').toLowerCase();
            let hasCityInput = active.querySelectorAll('input[placeholder*="списка"], input[placeholder*="город"], input[placeholder*="Город"], input[placeholder*="Выберите"], input[id*="city"], div.ComboBox, div.combobox-container, div[class*="select"], div[class*="Select"], input[type="text"], input:not([type])').length > 0;
            return (txt.includes('город') || txt.includes('проживаете') || txt.includes('живете') || txt.includes('населенный пункт')) && hasCityInput;
        }""")

        if is_city_question:
            handled_city = await self.handle_combobox_city(page)
            if handled_city:
                await human_sleep(1.0, 1.5)
                await self.click_next(page)
                await human_sleep(2.0, 3.0)
                return True

        if await self.handle_info_screen(page):
            await human_sleep(1.5, 2.5)
            return True

        # ВЫЗОВ ВЫНЕСЕННОГО МИКСИНА
        if await self.handle_progressive_blocks(page):
            await human_sleep(1.5, 2.5)
            return True

        question_text = await self.extract_question_text(page)

        dropdown_data = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let select = Array.from(active.querySelectorAll('select')).find(s => {
                if (s.disabled) return false;
                let opts = Array.from(s.options).filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'));
                return opts.length > 0;
            });

            if (select) {
                let options = Array.from(select.options)
                    .filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'))
                    .map(o => (o.innerText || o.textContent || '').replace(/\\s+/g, ' ').trim());

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
                        let opts = Array.from(sel.options).filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'));
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
                'div.choice__option',
                'div[class*="LogoItem"]',
                'div[class*="GridItem"]',
                'label.option-label',
                '.answer-item',
                '.scale-item',
                '.LogoItem',
                '.grid__cell',
                '.choice__option' 
            ].join(', ');

            let candidates = Array.from(active.querySelectorAll(selector)).filter(el => {
                if (el.getBoundingClientRect().height === 0) return false;

                let style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;

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
                    if (el.getBoundingClientRect().height === 0) return false;
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
                let selector = 'div[class*="styled__AnswerStyled"], div[class*="scale-item"], div[class*="scale-answer"], div[class*="AnswerRow"], div[class*="answer-row"], li.choice-item, div.choice-item, div.choice__option, div[class*="LogoItem"], div[class*="GridItem"], label.option-label, .answer-item, .scale-item, .LogoItem, .grid__cell, .choice__option';
                let candidates = Array.from(active.querySelectorAll(selector)).filter(el => {
                    if (el.getBoundingClientRect().height === 0) return false;

                    let style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;

                    if (el.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"]')) return false;
                    return true;
                });

                let leafOptions = candidates.filter(c => !candidates.some(other => other !== c && c.contains(other)));

                if (leafOptions.length < 2) {
                    let generic = Array.from(active.querySelectorAll('button, [role="radio"], [role="checkbox"], [role="button"], div[class*="radio"], div[class*="Radio"], div[class*="option"], div[class*="Option"], div[class*="answer"], div[class*="Answer"], div[class*="choice"], div[class*="Choice"], .btn')).filter(el => {
                        if (el.getBoundingClientRect().height === 0) return false;
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
                if (el.getBoundingClientRect().height === 0) return false;

                // ЗАЩИТА ОТ "ДРУГОЕ"
                let idStr = (el.id || '').toLowerCase();
                let nameStr = (el.name || '').toLowerCase();
                if (idStr.includes('_other') || nameStr.includes('_other')) return false;

                let cell = el.closest('[data-rowidx], .grid__cell, tr, .question__list-item, .pr-row, div.ss-table-row, label, .answer-item, .choice__option');
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

        visible_inputs = []
        for inp in text_inputs:
            try:
                box = await inp.bounding_box()
                if box and box['height'] > 0:
                    visible_inputs.append(inp)
            except Exception:
                pass

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