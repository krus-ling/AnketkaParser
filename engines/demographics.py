import asyncio
from playwright.async_api import Page
from engines.base import human_sleep
from engines.js_snippets import JS_SOLVE_PRESURVEY_DEMOGRAPHICS


class DemographicsManager:
    """
    Менеджер обработки стартовых демографических экранов (Пол, Дата рождения).
    Поддерживает Survstat (PreSurveyPage), Router-Client, CloudSurvey и общие React/Vue формы.
    """

    @staticmethod
    async def is_presurvey_screen(page: Page) -> bool:
        """Проверяет, является ли текущий экран пре-опросным демографическим окном."""
        try:
            return await page.evaluate("""() => {
                let active = document.querySelector('.step.active') || document.body;
                let prePage = active.querySelector("[class*='PreSurveyPage'], [class*='QuestionDate']");
                if (prePage && prePage.offsetParent !== null) return true;
                let hasDrop = active.querySelectorAll("[class*='DropDown_container']").length >= 2;
                let hasStartBtn = Array.from(active.querySelectorAll("button, div, [role='button'], a")).some(el => {
                    let t = (el.innerText || '').trim().toLowerCase();
                    return t === 'начать опрос' || t.startsWith('начать опрос');
                });
                return (hasDrop && hasStartBtn) || (prePage && prePage.offsetParent !== null);
            }""")
        except Exception:
            return False

    @staticmethod
    async def fill_demographics(page: Page, profile: dict) -> list[str]:
        """Заполняет демографические поля (Пол, Дата рождения) согласно профилю респондента."""
        personal = profile.get("personal", {})
        gender = personal.get("gender", "Мужской")
        day = personal.get("birth_day", "27")
        month_num = personal.get("birth_month", "6")
        year = personal.get("birth_year", "2005")

        month_names = {
            "1": "Январь", "2": "Февраль", "3": "Март", "4": "Апрель",
            "5": "Май", "6": "Июнь", "7": "Июль", "8": "Август",
            "9": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь"
        }
        month_name = month_names.get(str(int(month_num)), "Июнь")
        actions = []

        # 1. Заполнение через нативные Playwright-локаторы
        try:
            # 1.1 Пол (Gender)
            gender_target = "Мужской" if "муж" in gender.lower() else "Женский"
            other_gender = "Женский" if gender_target == "Мужской" else "Мужской"

            gender_selectors = [
                f"label:has-text('{gender_target}'):not(:has-text('{other_gender}'))",
                f"[class*='Answer']:has-text('{gender_target}'):not(:has-text('{other_gender}'))",
                f"[class*='Radio']:has-text('{gender_target}'):not(:has-text('{other_gender}'))",
                f"div:has-text('{gender_target}'):not(:has-text('{other_gender}'))"
            ]
            for g_sel in gender_selectors:
                try:
                    loc = page.locator(g_sel).first
                    if await loc.is_visible():
                        inp = loc.locator("input[type='radio']").first
                        if await inp.is_visible():
                            await inp.click(force=True)
                        else:
                            await loc.click(force=True)
                        actions.append(f"Пол: {gender_target}")
                        await human_sleep(0.2, 0.4)
                        break
                except Exception:
                    continue
        except Exception:
            pass

        try:
            # 1.2 Дата рождения (DOB) - Survstat DropDown контейнеры
            # День
            day_box = page.locator("[class*='DropDown_container']:has-text('День'), [class*='DropDown_container']:has([class*='DropDown_placeholder']:has-text('День'))").first
            day_inp = day_box.locator("input").first
            if await day_inp.is_visible():
                await day_inp.click()
                await day_inp.fill(str(day))
                actions.append(f"День: {day}")
                await human_sleep(0.2, 0.4)

            # Месяц (DropDown с выпадающим списком)
            month_box = page.locator("[class*='DropDown_container']:has-text('Месяц'), [class*='DropDown_container']:has([class*='DropDown_placeholder']:has-text('Месяц'))").first
            month_inp = month_box.locator("input").first
            if await month_box.is_visible():
                await month_box.click()
                await human_sleep(0.4, 0.6)
                month_opt = page.locator(f"[class*='DropDown_item']:has-text('{month_name}'), [class*='item']:has-text('{month_name}'), li:has-text('{month_name}'), div[role='option']:has-text('{month_name}')").first
                if await month_opt.is_visible():
                    await month_opt.click()
                    actions.append(f"Месяц: {month_name}")
                elif await month_inp.is_visible():
                    await month_inp.fill(month_name)
                    actions.append(f"Месяц (текст): {month_name}")
                await human_sleep(0.2, 0.4)

            # Год
            year_box = page.locator("[class*='DropDown_container']:has-text('Год'), [class*='DropDown_container']:has([class*='DropDown_placeholder']:has-text('Год'))").first
            year_inp = year_box.locator("input").first
            if await year_inp.is_visible():
                await year_inp.click()
                await year_inp.fill(str(year))
                actions.append(f"Год: {year}")
                await human_sleep(0.2, 0.4)
        except Exception:
            pass

        # 2. Дополнительно запускаем JS-сниппет для React fiber state и скрытых полей
        try:
            js_actions = await page.evaluate(JS_SOLVE_PRESURVEY_DEMOGRAPHICS, {
                "gender": gender,
                "day": day,
                "monthName": month_name,
                "monthNum": str(month_num).zfill(2),
                "year": year
            })
            if js_actions:
                for act in js_actions:
                    if act not in actions:
                        actions.append(act)
        except Exception:
            pass

        return actions

    @staticmethod
    async def click_start_button(page: Page) -> bool:
        """Кликает по кнопке «Начать опрос»."""
        try:
            btn_loc = page.locator("[class*='Button_button__'], [class*='Button_button']:not([class*='Container']), button:has-text('Начать опрос'), [role='button']:has-text('Начать опрос'), [class*='button' i]:has-text('Начать опрос'), div:has-text('Начать опрос')").first
            if not await btn_loc.is_visible():
                btn_loc = page.get_by_text("Начать опрос", exact=True).last

            if await btn_loc.is_visible():
                await btn_loc.scroll_into_view_if_needed()
                await human_sleep(0.3, 0.5)
                box = await btn_loc.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                else:
                    await btn_loc.click(force=True)
                return True
        except Exception:
            pass

        # Fallback через JS evaluate
        try:
            return await page.evaluate("""() => {
                let btns = Array.from(document.querySelectorAll("button, div[role='button'], div[class*='Button'], a")).filter(el => {
                    let t = (el.innerText || '').trim().toLowerCase();
                    return t === 'начать опрос' || t.startsWith('начать опрос');
                });
                if (btns.length > 0) {
                    let b = btns[0];
                    b.scrollIntoView({behavior: 'smooth', block: 'center'});
                    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                        b.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                    });
                    if (b.click) b.click();
                    return true;
                }
                return false;
            }""")
        except Exception:
            return False
