import asyncio
import random
import re
from playwright.async_api import Page

# Вызываем импорты из js_snippets
from engines.js_snippets import (
    JS_HANDLE_PROGRESSIVE_BLOCKS, JS_FILL_PROGRESSIVE_TEXT, JS_SELECT_PROGRESSIVE_CHOICE,
    JS_MARK_DATE_CONTAINERS, JS_CHECK_INFO_SCREEN,
    JS_MODAL_GET_TITLE, JS_DEMOGRAPHICS_CHECK_INTRO, JS_DEMOGRAPHICS_CHECK_GENDER,
    JS_DEMOGRAPHICS_CHECK_DATE, JS_DEMOGRAPHICS_FILL_GENDER, JS_DEMOGRAPHICS_OPEN_DATE_DROPDOWN,
    JS_DEMOGRAPHICS_SELECT_DATE_OPTION, JS_DEMOGRAPHICS_FILL_DATE_INPUT, JS_DEMOGRAPHICS_GET_CHECKBOX_HANDLE,
    JS_DEMOGRAPHICS_CHECK_CHECKBOX_STATE, JS_CITY_CHECK_ALREADY_SELECTED, JS_CITY_CLICK_CONTAINER,
    JS_CITY_CLEAR_INPUT, JS_OPEN_TEXT_CHECK_INPUT, JS_OPEN_TEXT_FILL_AND_BLUR
)


class ModalMixin:
    """Миксин для обработки внезапных всплывающих окон (уточнения, почему вы так считаете)."""

    async def handle_modal_popup(self, page: Page) -> bool:
        from engines.base import human_sleep, smooth_mouse_move

        ok_selectors = [
            "xpath=//button[normalize-space()='Ок' or normalize-space()='OK' or normalize-space()='ок']",
            "xpath=//div[normalize-space()='Ок' or normalize-space()='OK' or normalize-space()='ок']",
            "button:has-text('Ок')", "button:has-text('OK')", "div[role='button']:has-text('Ок')",
            ".btn-ok", "button[class*='ok']", "div[class*='ok']"
        ]

        ok_btn = None
        for sel in ok_selectors:
            try:
                btns = await page.query_selector_all(sel)
                for b in btns:
                    if await b.is_visible():
                        txt = (await b.inner_text()).strip()
                        if txt in ["Ок", "OK", "Ok", "ок"]:
                            ok_btn = b
                            break
                if ok_btn: break
            except Exception:
                continue

        if not ok_btn: return False

        modal_input = None
        for m_sel in [
            "xpath=//input[not(@type='hidden') and not(@type='submit') and not(@type='button') and not(@type='radio') and not(@type='checkbox')]",
            "div[class*='modal'] input", "input[type='text']", "textarea"]:
            try:
                inputs = await page.query_selector_all(m_sel)
                for inp in inputs:
                    if await inp.is_visible():
                        modal_input = inp
                        break
                if modal_input: break
            except Exception:
                continue

        if not modal_input: return False

        modal_title = await page.evaluate(JS_MODAL_GET_TITLE)

        print("\n" + "=" * 60)
        print(f"🪟 [МОДАЛЬНОЕ ОКНО]: {modal_title}")
        answer = self.brain.answer_open_text(modal_title)
        print(f"✍️  [ВВОД]: {answer}\n" + "=" * 60)

        await modal_input.scroll_into_view_if_needed()
        await modal_input.click(force=True)
        await human_sleep(0.3, 0.5)
        await modal_input.fill("")
        await page.keyboard.type(answer, delay=random.randint(40, 80))
        await human_sleep(0.5, 0.8)

        await ok_btn.scroll_into_view_if_needed()
        box = await ok_btn.bounding_box()
        if box:
            await smooth_mouse_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await ok_btn.click(force=True)
        await human_sleep(1.5, 2.5)
        return True


class FeedbackRewardMixin:
    """Миксин для детекции финала опроса, выставления оценки и сбора наград."""

    async def handle_completion_and_feedback(self, page: Page, body_text: str) -> bool:
        from engines.base import human_sleep
        body_lower = body_text.lower()
        if not ((
                        "вы изменили мир" in body_lower or "оцените пройденный опрос" in body_lower or "подобрать опрос" in body_lower) and (
                        "понравился" in body_lower or "баллов" in body_lower or "зачислено" in body_lower)):
            return False

        print("\n" + "=" * 60)
        print("🎉 [ФИНАЛ ОПРОСА] Опрос успешно завершен!")
        reward_match = re.search(r'(\d+)\s*(?:баллов|балла|балл|руб|₽)', body_text, re.IGNORECASE)
        reward_txt = reward_match.group(0) if reward_match else 'начислено'
        print(f"💰 [БАЛАНС]: +{reward_txt}")
        try:
            from core.telegram_notifier import notifier
            notifier.notify_survey_completed(self.__class__.__name__, f"+{reward_txt}")
        except Exception:
            pass

        rating_selectors = ["xpath=//label[contains(., 'Очень понравился') or contains(., 'Понравился')]",
                            "xpath=//span[normalize-space()='Понравился' or normalize-space()='Очень понравился']"]
        for sel in rating_selectors:
            elements = await page.query_selector_all(sel)
            for el in elements:
                if await el.is_visible():
                    await el.click(force=True)
                    print("⭐ [ОЦЕНКА]: Выбран вариант «Понравился»")
                    await human_sleep(0.4, 0.7)
                    break
            break

        comment_box = await page.query_selector("textarea, input[placeholder*='комментарий']")
        if comment_box and await comment_box.is_visible():
            await comment_box.click(force=True)
            await comment_box.fill("")
            await page.keyboard.type("Интересный и понятный опрос, всё понравилось!", delay=random.randint(25, 55))
            await human_sleep(0.5, 0.9)

        next_survey_btn = await page.query_selector(
            "button:has-text('Подобрать опрос'), [class*='Button_button']:has-text('Подобрать опрос'), [role='button']:has-text('Подобрать опрос'), div[class*='btn']:has-text('Подобрать опрос')")
        if next_survey_btn and await next_survey_btn.is_visible():
            await next_survey_btn.click(force=True)
            print("🚀 [СЛЕДУЮЩИЙ ОПРОС]: Нажата кнопка перехода\n" + "=" * 60)
            await human_sleep(3.0, 5.0)
            return True
        return False

    async def handle_anketka_reward(self, page: Page) -> bool:
        from engines.base import human_sleep
        try:
            money_selectors = [".reward-card", "div[class*='reward']", "label:has-text('Деньги')",
                               "button:has-text('Деньги')"]
            for sel in money_selectors:
                cards = await page.query_selector_all(sel)
                for card in cards:
                    card_text = (await card.inner_text()).strip()
                    if await card.is_visible() and "деньги" in card_text.lower():
                        amount_match = re.search(r'(\d+)\s*(?:руб|₽)', card_text, re.IGNORECASE)
                        amount_str = f"+{amount_match.group(1)} руб." if amount_match else "начислены рубли"
                        await card.click(force=True)
                        print(f"\n💰 [ВОЗНАГРАЖДЕНИЕ] Выбран вариант: «Деньги» ({amount_str})")
                        await human_sleep(0.8, 1.2)

                        confirm_btn = await page.query_selector(
                            "button:has-text('Получить'), button:has-text('Подтвердить'), button:has-text('Далее')")
                        if confirm_btn and await confirm_btn.is_visible():
                            await confirm_btn.click(force=True)
                            print("🎉 [СТАТУС] Начисление зафиксировано!")
                        return True
        except Exception as e:
            print(f"[!] Ошибка выбора вознаграждения: {e}")
        return False


class BaseQuestionMixin:
    """Миксин для извлечения базового текста вопроса."""

    async def extract_question_text(self, page: Page) -> str:
        q_selectors = [
            ".header-row", ".header1", ".header2", "[class*='question-header']", "[class*='question-title']",
            "[class*='question-text']", "[class*='HeaderStyled']", "[class*='QuestionHeader']",
            "[class*='questionTitle']",
            ".question-header", ".question-title", ".question-text", "h1", "h2", "h3", ".title"
        ]

        generic_phrases = ["выберите подходящий вариант", "выберите один или несколько вариантов",
                           "выберите вариант ответа", "укажите один или несколько вариантов"]

        best_text = ""
        for qs in q_selectors:
            try:
                elements = await page.query_selector_all(qs)
                for el in elements:
                    if await el.is_visible():
                        t = (await el.inner_text()).strip()
                        t_clean = ' '.join(t.replace('\n', ' ').split())

                        if len(t_clean) > 5 and not t_clean.lower().startswith("страница"):
                            is_generic = any(phrase in t_clean.lower() for phrase in generic_phrases)
                            if not is_generic:
                                return t_clean
                            elif not best_text:
                                best_text = t_clean
            except Exception:
                continue

        return best_text if best_text else "Выберите подходящий вариант"


class DemographicsMixin:
    """Миксин для обработки составных демографических вопросов (дата рождения, пол, город)."""

    async def handle_composite_demographics(self, page: Page) -> bool:
        from engines.base import human_sleep
        has_gender_el = await page.evaluate(JS_DEMOGRAPHICS_CHECK_GENDER)
        has_date_el = await page.evaluate(JS_DEMOGRAPHICS_CHECK_DATE)

        if not has_gender_el and not has_date_el and await page.evaluate(JS_DEMOGRAPHICS_CHECK_INTRO):
            print("\n" + "=" * 50 + "\n[i] [CLOUDSURVEY] Приветственный экран. Нажимаем «Начать опрос»...\n" + "=" * 50)
            await self.click_next(page)
            return True

        if has_gender_el:
            print("\n" + "=" * 50 + "\n[i] [CLOUDSURVEY] Заполнение профиля: Пол...\n" + "=" * 50)
            target_gender = self.profile_personal.get("gender", "Мужской")
            await page.evaluate(JS_DEMOGRAPHICS_FILL_GENDER, target_gender)
            print(f"[i] Пол выбран: «{target_gender}»")
            await human_sleep(0.3, 0.6)

        if has_date_el:
            print("\n" + "=" * 50 + "\n[i] [CLOUDSURVEY] Заполнение профиля: Дата рождения...\n" + "=" * 50)
            day_val = str(int(self.profile_personal.get("birth_day", "27")))
            month_int = int(self.profile_personal.get("birth_month", "6"))
            year_val = str(self.profile_personal.get("birth_year", "2005"))

            month_names_ru = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь",
                              "Октябрь", "Ноябрь", "Декабрь"]
            target_month_name = month_names_ru[month_int - 1] if 1 <= month_int <= 12 else "Июнь"

            await page.evaluate(JS_MARK_DATE_CONTAINERS)

            targets = [
                ("День", "0", [day_val, f"{int(day_val):02d}"]),
                ("Месяц", "1", [target_month_name, target_month_name.lower(), str(month_int), f"{month_int:02d}"]),
                ("Год", "2", [year_val])
            ]

            for field_name, t_idx, vals in targets:
                if await page.evaluate(JS_DEMOGRAPHICS_OPEN_DATE_DROPDOWN, t_idx):
                    await human_sleep(0.5, 0.8)
                    if not await page.evaluate(JS_DEMOGRAPHICS_SELECT_DATE_OPTION, vals):
                        await page.evaluate(JS_DEMOGRAPHICS_FILL_DATE_INPUT, {"idx": t_idx, "val": str(vals[0])})
                    print(f"[✓] {field_name}: «{vals[0]}»")
                    await human_sleep(0.3, 0.6)

        cb_handle = await page.evaluate_handle(JS_DEMOGRAPHICS_GET_CHECKBOX_HANDLE)
        if not await cb_handle.evaluate("el => !el"):
            if not await page.evaluate(JS_DEMOGRAPHICS_CHECK_CHECKBOX_STATE):
                await cb_handle.scroll_into_view_if_needed()
                await cb_handle.click(force=True)
                await human_sleep(0.3, 0.5)

        await human_sleep(0.5, 0.8)
        return True

    async def handle_combobox_city(self, page: Page) -> bool:
        from engines.base import human_sleep

        target_city = self.profile_personal.get("city", "Москва")

        # 1. Жестко очищаем любые таймеры автокомплита и пишем город напрямую через JS-инъекцию в value
        injected = await page.evaluate("""(targetCity) => {
            let inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="search"], input:not([type])'));
            let targetInput = inputs.find(el => {
                let ph = (el.placeholder || '').toLowerCase();
                let cls = (el.className || '').toLowerCase();
                return ph.includes('город') || ph.includes('ввод') || cls.includes('selectize') || cls.includes('choices');
            }) || inputs[inputs.length - 1];

            if (targetInput) {
                targetInput.focus();
                targetInput.value = targetCity;
                targetInput.dispatchEvent(new Event('input', {bubbles: true}));
                targetInput.dispatchEvent(new Event('change', {bubbles: true}));
                targetInput.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, key: 'e'}));
                return true;
            }
            return false;
        }""", target_city)

        if not injected:
            return False

        print(f"[✓] [CLOUDSURVEY] Город «{target_city}» принудительно внедрен в поле через инъекцию")
        await human_sleep(1.0, 1.5)

        # 2. Ищем выпадающую подсказку с нашим городом и кликаем на неё, чтобы зафиксировать выбор плагина
        suggestion_selectors = [
            f"xpath=//div[contains(@class, 'dropdown') or contains(@class, 'option') or contains(@class, 'item') or self::li][contains(normalize-space(), '{target_city}')]",
            f"xpath=//*[contains(normalize-space(), '{target_city}') and (contains(@class, 'dropdown') or contains(@class, 'option') or contains(@class, 'select'))]",
            f"xpath=(//*[contains(normalize-space(), '{target_city}')][not(ancestor::script)])[last()]"
        ]

        opt_clicked = False
        for s_sel in suggestion_selectors:
            try:
                s_el = await page.wait_for_selector(s_sel, state="visible", timeout=1200)
                if s_el:
                    await s_el.scroll_into_view_if_needed()
                    await s_el.click(force=True)
                    print(f"[✓] [CLOUDSURVEY] Клик по подсказке города «{target_city}» успешно совершен")
                    opt_clicked = True
                    await asyncio.sleep(0.8)
                    break
            except Exception:
                continue

        if not opt_clicked:
            await page.keyboard.press("Enter")
            print(f"[✓] [CLOUDSURVEY] Город «{target_city}» подтвержден нажатием Enter")
            await asyncio.sleep(0.8)

        return True


class InfoScreenMixin:
    """Миксин для обработки информационных/ознакомительных экранов без вопросов."""

    async def handle_info_screen(self, page: Page) -> bool:
        from engines.base import human_sleep
        info_text = await page.evaluate(JS_CHECK_INFO_SCREEN)

        if not info_text: return False

        print("\n" + "=" * 60 + "\n📄 [ИНФОРМАЦИОННЫЙ ЭКРАН / ОЗНАКОМЛЕНИЕ С МАТЕРИАЛОМ]:")
        for line in info_text.split('\n')[:6]: print(f"   ℹ️  {line}")
        print("=" * 60)

        self.brain.ad_context = info_text
        await human_sleep(2.5, 4.0)
        await self.click_next(page)
        return True


class OpenTextMixin:
    """Миксин для обработки классических открытых вопросов (ввод текста/чисел)."""

    async def handle_open_text_question(self, page: Page, question_text: str) -> bool:
        from engines.base import human_sleep
        if not await page.evaluate(JS_OPEN_TEXT_CHECK_INPUT):
            return False

        text_inputs = await page.query_selector_all(
            "input[type='text'], input[type='number'], input[inputmode='numeric'], input:not([type]), textarea, div[contenteditable='true']")

        visible_inputs = []
        for inp in text_inputs:
            try:
                box = await inp.bounding_box()
                if box and box['height'] > 0: visible_inputs.append(inp)
            except Exception:
                pass

        if not visible_inputs: return False

        target_input = visible_inputs[0]
        answer_text = self.brain.answer_open_text(question_text)
        print(f"\n[?] ОТКРЫТЫЙ ВОПРОС: {question_text}\n✍️  [ВВОД ТЕКСТА]: {answer_text}")

        await target_input.scroll_into_view_if_needed()
        await target_input.click(force=True)
        await human_sleep(0.3, 0.6)

        await page.evaluate(JS_OPEN_TEXT_FILL_AND_BLUR, {"inp": target_input, "txt": answer_text})

        input_type = await target_input.get_attribute("type")
        if input_type == "number":
            answer_text = re.sub(r'\D', '', answer_text)
            if not answer_text: answer_text = str(self.profile_personal.get("age", 21))

        await page.keyboard.type(answer_text, delay=random.randint(50, 90))
        await page.evaluate("() => { if(document.activeElement) document.activeElement.blur(); }")
        await human_sleep(0.6, 1.2)
        await self.click_next(page)
        await human_sleep(2.0, 3.5)

        return True


class ProgressiveBlocksMixin:
    """Миксин для обработки ленточных (progressive) блоков с вопросами."""

    async def handle_progressive_blocks(self, page: Page) -> bool:
        from engines.base import human_sleep
        total_handled = 0
        max_substeps = 25

        for _ in range(max_substeps):
            block_data = await page.evaluate(JS_HANDLE_PROGRESSIVE_BLOCKS)
            if not block_data: return False

            if block_data.get("allAnswered"):
                if total_handled > 0: await human_sleep(0.5, 0.8)
                await self.click_next(page)
                return True

            if block_data.get("hasTextInput") and not block_data.get("options"):
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                print(
                    f"\n[№ {self.brain.stats.get('total_answered', 0)}] ОТКРЫТЫЙ ВОПРОС: {block_data['questionText']}")
                ans_text = self.brain.answer_open_text(block_data['questionText'])
                print(f"✍️  [ВВОД]: {ans_text}")
                await page.evaluate(JS_FILL_PROGRESSIVE_TEXT, {"dynId": block_data["dynId"], "text": ans_text})
                total_handled += 1
                await human_sleep(0.4, 0.7)

            elif len(block_data.get("options", [])) >= 2:
                print("\n" + "=" * 60)
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass
                q_text, options, is_multi = block_data['questionText'], block_data['options'], block_data['isMulti']
                print(
                    f"[№ {self.brain.stats.get('total_answered', 0)}] ВОПРОС: {q_text}\n[i] ТИП: {'Множественный выбор' if is_multi else 'Одиночный выбор'}\n[*] ВСЕГО ВАРИАНТОВ: {len(options)}")
                for idx, text in enumerate(options[:15]): print(f"    [{idx}] {text}")

                decision = self.brain.decide(q_text, options, is_multi)
                selected_names = [options[i] for i in decision.selected_indices if i < len(options)]
                print(
                    f"[LLM] ВЫБРАНО ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_names[:8]}\n[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)

                for sel_idx in decision.selected_indices:
                    await page.evaluate(JS_SELECT_PROGRESSIVE_CHOICE, {"dynId": block_data["dynId"], "optIdx": sel_idx})
                    await human_sleep(0.3, 0.5)
                total_handled += 1
                await human_sleep(0.5, 0.8)

        if total_handled > 0:
            await human_sleep(0.6, 1.0)
            await self.click_next(page)
            return True
        return False

class QuestionDispatcherMixin:
    """Миксин для унифицированной обработки стандартного цикла вопросов (текст, селекты, радио)."""
    async def dispatch_questions(
        self, page: Page,
        parse_js: str, fill_text_js: str, clear_text_js: str, select_choice_js: str,
        select_dropdown_js: str = None, clear_dropdown_js: str = None
    ) -> bool:
        from engines.base import human_sleep
        total_handled = 0

        for _ in range(15):
            data = await page.evaluate(parse_js)
            if not data: break

            if data.get("targetType") == "done_or_info":
                if total_handled == 0 and data.get("questionText"):
                    print(f"\n📄 [ИНФО-ЭКРАН]: {data['questionText']}")
                break

            elif data.get("targetType") == "text":
                try: self.brain.stats['total_answered'] += 1
                except Exception: pass
                print(f"\n[№ {self.brain.stats.get('total_answered', 0)}] ОТКРЫТЫЙ ВОПРОС: {data['questionText']}")
                ans_text = self.brain.answer_open_text(data["questionText"])
                if ans_text:
                    print(f"✍️  [ВВОД]: {ans_text}")
                    await page.evaluate(fill_text_js, ans_text)
                    total_handled += 1
                    await human_sleep(0.5, 1.0)
                else:
                    print("[!] ВЫБРАНО: -> НИЧЕГО (Ожидание ручного действия)")
                    if clear_text_js: await page.evaluate(clear_text_js)
                    break

            elif data.get("targetType") == "select":
                print("\n" + "=" * 60 + f"\n[?] ВОПРОС (ВЫПАДАЮЩИЙ СПИСОК): {data['questionText']}\n[*] ВСЕГО ВАРИАНТОВ: {len(data['options'])}")
                for idx, text in enumerate(data["options"][:15]): print(f"    [{idx}] {text}")

                decision = self.brain.decide(data["questionText"], data["options"], is_multiselect=False)
                if decision.selected_indices:
                    try: self.brain.stats['total_answered'] += 1
                    except Exception: pass
                    selected_name = data["options"][decision.selected_indices[0]]
                    print(f"[№ {self.brain.stats.get('total_answered', 0)}] ВЫБРАНО: -> ['{selected_name}']\n[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)
                    if select_dropdown_js: await page.evaluate(select_dropdown_js, selected_name)
                    total_handled += 1
                    await human_sleep(0.5, 1.0)
                else:
                    print("[LLM] ВЫБРАНО: -> НИЧЕГО (Ожидание выбора в GUI)\n" + "=" * 60)
                    if clear_dropdown_js: await page.evaluate(clear_dropdown_js)
                    break

            elif data.get("targetType") == "choices":
                print("\n" + "=" * 60 + f"\n[?] ВОПРОС: {data['questionText']}\n[i] ТИП: {'Множественный выбор' if data['isMulti'] else 'Одиночный выбор'}\n[*] ВСЕГО ВАРИАНТОВ: {len(data['options'])}")
                for idx, text in enumerate(data["options"][:15]): print(f"    [{idx}] {text}")

                decision = self.brain.decide(data["questionText"], data["options"], data["isMulti"])
                if decision.selected_indices:
                    try: self.brain.stats['total_answered'] += 1
                    except Exception: pass
                    selected_names = [data["options"][i] for i in decision.selected_indices if i < len(data["options"])]
                    print(f"[№ {self.brain.stats.get('total_answered', 0)}] ВЫБРАНО ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_names}\n[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)
                    for sel_idx in decision.selected_indices:
                        await page.evaluate(select_choice_js, sel_idx)
                        await human_sleep(0.3, 0.6)
                    total_handled += 1
                    break
                else:
                    print("[LLM] ВЫБРАНО: -> НИЧЕГО (Ожидание выбора в GUI)\n" + "=" * 60)
                    break

        if total_handled > 0 or (data and data.get("targetType") == "done_or_info"):
            await human_sleep(1.0, 1.5)
            await self.click_next(page)
            return True
        return False