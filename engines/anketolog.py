import asyncio
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep


class AnketologEngine(BaseSurveyEngine):

    async def click_next(self, page: Page) -> bool:
        """Нажатие кнопки Далее или Начать на платформе Anketolog."""
        selectors = [
            "text='НАЧАТЬ'",
            "text='Начать'",
            "text='ДАЛЕЕ'",
            "text='Далее'",
            "button:has-text('ДАЛЕЕ')",
            "button:has-text('НАЧАТЬ')",
            ".btn-next",
            ".btn-success"
        ]

        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(force=True)
                        print(f"[i] [ANKETOLOG] Нажата кнопка (найдено по: {sel})")
                        return True
            except Exception:
                continue

        return False

    async def process_step(self, page: Page, body_lower: str) -> bool:
        total_handled = 0

        for _ in range(15):
            data = await page.evaluate("""() => {
                function getTitle() {
                    // Ищем заголовок вопроса (на Анкетологе это обычно .question-title)
                    let qEl = document.querySelector('.question-title, .question__title, h1, h2, h3');
                    if (qEl) {
                        let text = qEl.innerText.trim();
                        // Убираем красную звездочку обязательного вопроса в конце
                        return text.replace(/\\*$/, '').trim();
                    }
                    return '';
                }

                let qText = getTitle();

                // 1. Ищем ПУСТЫЕ текстовые поля
                let textInputs = Array.from(document.querySelectorAll('textarea, input[type="text"]:not([readonly]), input[type="number"], input[type="email"]')).filter(i => {
                    // Игнорируем поля "Другое", если они лежат внутри строки с чекбоксом
                    let row = i.closest('.question__element-wrapper, .question__list-item, label');
                    if (row && row.querySelector('input[type="radio"], input[type="checkbox"]')) return false;

                    return i.offsetParent !== null && i.value.trim() === '';
                });

                if (textInputs.length > 0) {
                    let inp = textInputs[0];
                    inp.setAttribute('data-bot-target', 'true');
                    return {targetType: 'text', questionText: qText, options: []};
                }

                // 2. Ищем Радио-кнопки и чекбоксы (на Анкетологе лежат в .question__element-wrapper)
                let choiceRows = Array.from(document.querySelectorAll('.question__element-wrapper, .question__list-item')).filter(r => {
                    return r.offsetParent !== null && r.querySelector('input[type="radio"], input[type="checkbox"]') !== null;
                });

                // Фолбэк: если классы поменялись, ищем просто по инпутам
                if (choiceRows.length === 0) {
                    choiceRows = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]'))
                        .map(i => i.closest('div, label') || i.parentElement)
                        .filter(r => r.offsetParent !== null);
                }

                if (choiceRows.length > 0) {
                    let isAnswered = choiceRows.some(r => {
                        let inp = r.querySelector('input[type="radio"], input[type="checkbox"]');
                        return inp && inp.checked;
                    });

                    if (!isAnswered) {
                        let isMulti = choiceRows.some(r => r.querySelector('input[type="checkbox"]') !== null);
                        let options = choiceRows.map((r, i) => {
                            // Ищем текст в спане с классом .question__element-text
                            let tEl = r.querySelector('.question__element-text, .text, span');
                            if (tEl) return tEl.innerText.trim();
                            // Если нет спана, берем весь текст строки
                            return r.innerText.trim() || `Вариант ${i + 1}`;
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
                            let rows = Array.from(document.querySelectorAll('.question__element-wrapper, .question__list-item'));
                            if (rows.length === 0) {
                                rows = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]')).map(i => i.closest('div, label') || i.parentElement);
                            }

                            if (rows[idx]) {
                                // На Vue.js (Анкетолог) нужно кликать по видимой обертке, а не по скрытому инпуту
                                let clickable = rows[idx].querySelector('.question__element-custom, .question__element') || rows[idx];
                                clickable.scrollIntoView({behavior: 'smooth', block: 'center'});
                                clickable.click();

                                // Если в этой строке есть поле "Другое", заполняем его
                                let textInp = rows[idx].querySelector('input[type="text"]');
                                if (textInp) {
                                    textInp.value = "Свой вариант";
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