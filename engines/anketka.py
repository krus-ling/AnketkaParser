import random
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep, MONTH_NAMES

class AnketkaEngine(BaseSurveyEngine):
    async def click_next(self, page: Page) -> bool:
        clicked_div = await page.evaluate("""() => {
            let activeContainer = document.querySelector('.step.active') || document.body;
            let buttons = Array.from(activeContainer.querySelectorAll('button, div[class*="button"], div[class*="Button"], a.btn, div.btn, span.btn, .btn-green, .btn-primary')).filter(el => {
                if (el.offsetParent === null) return false;
                let txt = (el.innerText || '').trim().toLowerCase();
                if (txt.length > 50) return false;
                return ['вперед', 'далее', 'продолжить', 'начать опрос', 'подобрать опрос', 'получить', 'старт'].some(kw => txt === kw || txt.includes(kw));
            });

            if (buttons.length > 0) {
                buttons.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
                let target = buttons[0];
                target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                target.click();
                return target.innerText.trim();
            }
            return null;
        }""")

        if clicked_div:
            print(f"[i] [ANKETKA] Нажата кнопка: «{clicked_div}»")
            return True
        return False

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
                            sel.dispatchEvent(new Event('change', { bubbles: true }));
                            sel.dispatchEvent(new Event('input', { bubbles: true }));
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
            await self.click_next(page)
            return True
        return False

    async def handle_city_selection(self, page: Page) -> bool:
        target_city = self.profile_personal.get("city", "Москва")
        city_input = await page.query_selector("input[id*='city'], input[placeholder*='списка'], input[class*='custom-input']")
        if city_input and await city_input.is_visible():
            await city_input.scroll_into_view_if_needed()
            await city_input.click(force=True)
            await human_sleep(0.3, 0.5)
            await city_input.fill("")
            await page.keyboard.type(target_city, delay=random.randint(60, 110))
            await human_sleep(0.5, 0.8)

            suggestion = await page.query_selector(f"xpath=//div[contains(@class, 'dropdown') or contains(@class, 'option')][normalize-space()='{target_city}']")
            if suggestion and await suggestion.is_visible():
                await suggestion.click(force=True)
                print(f"[✓] [ANKETKA] Город «{target_city}» выбран")
            return True
        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:
        has_dob = await page.evaluate("() => document.querySelectorAll('select').length >= 2")
        if has_dob or ("день" in body_lower and "месяц" in body_lower and "год" in body_lower and (await page.query_selector("select"))):
            handled = await self.handle_composite_demographics(page)
            if handled:
                await human_sleep(2.0, 3.0)
                return True

        if ("город" in body_lower or "проживаете" in body_lower) and (await page.query_selector("input[id*='city'], input[placeholder*='списка']")):
            await self.handle_city_selection(page)
            await human_sleep(1.0, 1.5)
            await self.click_next(page)
            await human_sleep(2.0, 3.0)
            return True

        question_text = await self.extract_question_text(page)

        raw_options = await page.evaluate("""() => {
            let active = document.querySelector('.step.active') || document.body;
            let selector = [
                'div[class*="scale-item"]', 'div[class*="scale-answer"]',
                'li.choice-item', 'div.choice-item', 'div[class*="AnswerRow"]', 'div[class*="answer-row"]',
                'div[class*="LogoItem"]', 'div[class*="GridItem"]', '.answer-item', 'label.option-label', '.LogoItem', '.scale-item'
            ].join(', ');

            let nodes = Array.from(active.querySelectorAll(selector)).filter(n => {
                return n.offsetParent !== null && !n.className.includes('Button') && !n.className.includes('btn') && (n.innerText || '').trim().length > 0;
            });
            if (nodes.length < 2) return [];

            return nodes.map((node, idx) => {
                let directText = (node.innerText || '').trim();
                let cleanDirect = directText.replace(/^\\d+\\s*/, '').trim();

                let attrCandidate = '';
                let attrSources = [node, ...Array.from(node.querySelectorAll('*'))];
                for (let el of attrSources) {
                    let val = el.getAttribute('data-name') || 
                              el.getAttribute('data-title') || 
                              el.getAttribute('aria-label') || 
                              el.getAttribute('title') || 
                              el.getAttribute('alt') || '';
                    val = val.trim();
                    if (val.length > 1 && !/^[0-9a-f]{1,4}$/i.test(val) && !val.toLowerCase().startsWith('http')) {
                        attrCandidate = val;
                        break;
                    }
                }

                let isTextGarbage = !cleanDirect || /^\\d+$/.test(cleanDirect) || /^[0-9a-f]{1,3}$/i.test(cleanDirect);

                let finalName = '';
                if (attrCandidate) finalName = attrCandidate;
                else if (!isTextGarbage) finalName = cleanDirect;
                else if (directText) finalName = directText;
                else finalName = `Вариант ${idx + 1}`;

                return { index: idx, text: finalName };
            });
        }""")

        if not raw_options:
            return await self.handle_open_text_question(page, question_text)

        options_texts = [o["text"] for o in raw_options]
        is_multi = (await page.query_selector("input[type='checkbox']")) is not None or any(w in body_lower for w in ["несколько", "все подходящие", "отметьте"])
        decision = self.brain.decide(question_text, options_texts, is_multi)

        for idx in decision.selected_indices:
            await page.evaluate("""(idx) => {
                let active = document.querySelector('.step.active') || document.body;
                let selector = [
                    'div[class*="scale-item"]', 'div[class*="scale-answer"]',
                    'li.choice-item', 'div.choice-item', 'div[class*="AnswerRow"]', 'div[class*="answer-row"]',
                    'div[class*="LogoItem"]', 'div[class*="GridItem"]', '.answer-item', 'label.option-label', '.LogoItem', '.scale-item'
                ].join(', ');

                let nodes = Array.from(active.querySelectorAll(selector)).filter(n => {
                    return n.offsetParent !== null && !n.className.includes('Button') && !n.className.includes('btn') && (n.innerText || '').trim().length > 0;
                });
                if (nodes[idx]) {
                    let target = nodes[idx];
                    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    let inp = target.querySelector('input');
                    if (inp) inp.click();
                    else target.click();
                }
            }""", idx)
            await human_sleep(0.3, 0.5)

        await human_sleep(0.8, 1.4)
        await self.click_next(page)
        return True