import unittest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rules_engine import RulesEngine
from core.prompts import get_open_text_prompt, get_chat_prompt, get_decision_prompt
from core.llm_client import LLMClient, SurveyDecision
from core.memory import SurveyMemory
from core.brain import SurveyBrain
from core.telegram_notifier import TelegramNotifier


class TestSurveySystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("data/profile.json", "r", encoding="utf-8") as f:
            cls.profile = json.load(f)

    def setUp(self):
        self.rules = RulesEngine(self.profile)

    def test_open_text_child_vs_user_age(self):
        """Проверка исправления: возраст ребенка vs возраст пользователя."""
        child_age = self.rules.apply_open_text_rules("сколько лет вашему ребенку?", False)
        self.assertEqual(child_age, "3")

        child_dob = self.rules.apply_open_text_rules("дата рождения ребенка", False)
        self.assertEqual(child_dob, "05.03.2023")

        user_age = self.rules.apply_open_text_rules("сколько вам полных лет?", False)
        self.assertEqual(user_age, "21")

        user_dob = self.rules.apply_open_text_rules("укажите дату вашего рождения", False)
        self.assertEqual(user_dob, "27.06.2005")

    def test_open_text_quantities_not_money(self):
        """Проверка исправления: 'сколько' не должно возвращать 2500 рублей для детей и семьи."""
        kids = self.rules.apply_open_text_rules("сколько у вас детей?", False)
        self.assertEqual(kids, "1")

        family = self.rules.apply_open_text_rules("сколько человек в вашей семье?", False)
        self.assertEqual(family, "3")

        cars = self.rules.apply_open_text_rules("сколько автомобилей у вас?", False)
        self.assertEqual(cars, "1")

        finance = self.rules.apply_open_text_rules("сколько рублей вы тратите на продукты?", False)
        self.assertEqual(finance, "2500")

    def test_antikick_internet_banking_protection(self):
        """Проверка исправления: 'нет' в 'интернет-банкинг' не должно активировать анти-кик."""
        options = ["Интернет-банкинг", "Мобильный банк", "Отделение банка"]
        filtered = self.rules.filter_llm_decision("Какими сервисами вы пользуетесь?", options, [0, 1], True)
        self.assertIn(0, filtered, "Интернет-банкинг был ошибочно отфильтрован анти-киком!")

    def test_max_limit_constraint(self):
        """Проверка исправления: автоматическое урезание количества ответов при требовании 'не более N'."""
        options = ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4"]
        filtered = self.rules.filter_llm_decision("Выберите не более 2 вариантов:", options, [0, 1, 2, 3], True)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered, [0, 1])

    def test_math_captcha_solver(self):
        """Проверка работы решателя математических капч."""
        res_plus = self.rules.solve_math("Чему равно 2 плюс 3?", ["4", "5", "6"])
        self.assertEqual(res_plus, [1])

        res_minus = self.rules.solve_math("Сколько будет десять минус три?", ["пять", "семь", "девять"])
        self.assertEqual(res_minus, [1])

        res_mult = self.rules.solve_math("Сколько будет 4 умножить на 3?", ["10", "12", "14"])
        self.assertEqual(res_mult, [1])

    def test_attention_check_traps(self):
        """Проверка обнаружения ловушек на внимательность."""
        res = self.rules.check_traps("Это проверка на внимательность. Выберите третий вариант ответа.", ["A", "B", "C", "D"])
        self.assertEqual(res, [2])

    def test_screening_work_traps(self):
        """Проверка отраслевых ловушек (маркетинг/PR/опросы)."""
        options = ["Маркетинг и реклама", "IT и разработка", "Журналистика", "Ни в одной из перечисленных"]
        res = self.rules.check_traps("Работаете ли вы в какой-либо из следующих сфер?", options)
        self.assertEqual(res, [3])

    def test_smoking_products_choice(self):
        """Проверка курения: респондент курит и НЕ должен выбирать 'Не курю' из-за слова 'да' в 'никогда'."""
        options = [
            "Сигареты фабричного производства с фильтром",
            "Сигары, сигариллы, самокрутки",
            "Системы нагревания табака (IQOS, Glo, Ploom и др)",
            "Одноразовые электронные сигареты",
            "Электронные сигареты с картриджами/капсулами",
            "Электронные сигареты, которые заправляются жидкостью",
            "Вейп",
            "Кальян",
            "Другое",
            "Не курю и никогда не курил(а)",
            "Бросил(а) курить"
        ]
        q = "Курите ли Вы в настоящее время? Что из перечисленного Вы курили за последний месяц?"
        res = self.rules.check_traps(q, options)
        self.assertIsNotNone(res)
        self.assertNotIn(9, res, "Ошибочно выбран вариант 'Не курю'!")
        self.assertNotIn(10, res, "Ошибочно выбран вариант 'Бросил курить'!")
        self.assertIn(0, res, "Сигареты с фильтром должны быть выбраны!")

    def test_memory_exact_and_fuzzy(self):
        """Проверка работы SQLite памяти: O(1) точный поиск и нечеткий поиск."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db = tmp.name

        try:
            mem = SurveyMemory(db_path=tmp_db)
            mem.save_record(
                full_question="Какую марку смартфона вы предпочитаете?",
                question_type="single",
                options=["Apple", "Samsung", "Xiaomi"],
                selected=[1],
                selected_text=["Samsung"],
                reasoning="Тестовое сохранение"
            )

            with mem._get_connection() as conn:
                conn.execute("UPDATE qa_records SET is_verified = 1 WHERE id = 1")
                conn.commit()

            # 1. Точный поиск
            res_exact = mem.find_verified_answer("Какую марку смартфона вы предпочитаете?", ["Apple", "Samsung", "Xiaomi"])
            self.assertIsNotNone(res_exact)
            self.assertEqual(res_exact[0], [1])

            # 2. Нечеткий поиск (переформулированный вопрос)
            res_fuzzy = mem.find_verified_answer("Какую марку смартфонов вы предпочитаете?", ["Apple", "Samsung", "Xiaomi"])
            self.assertIsNotNone(res_fuzzy)
            self.assertEqual(res_fuzzy[0], [1])

            # 3. Кросс-чек вариантов: другой вопрос не должен совпасть
            res_mismatch = mem.find_verified_answer("Какую марку смартфона вы предпочитаете?", ["Lada", "Audi", "BMW"])
            self.assertIsNone(res_mismatch)
        finally:
            if os.path.exists(tmp_db):
                try:
                    os.remove(tmp_db)
                except Exception:
                    pass

    def test_memory_semantic_matching(self):
        """Проверка семантического сопоставления синонимичных формулировок."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db = tmp.name

        try:
            mem = SurveyMemory(db_path=tmp_db)
            mem.save_record(
                full_question="Укажите сферу вашей профессиональной деятельности и занятости",
                question_type="single",
                options=["IT и телеком", "Банки", "Торговля"],
                selected=[0],
                selected_text=["IT и телеком"],
                reasoning="Тест сферы занятости"
            )

            with mem._get_connection() as conn:
                conn.execute("UPDATE qa_records SET is_verified = 1 WHERE id = 1")
                conn.commit()

            res_semantic = mem.find_verified_answer(
                "В какой отрасли или сфере вы в настоящее время работаете?",
                ["IT и телеком", "Банки", "Торговля"]
            )
            self.assertIsNotNone(res_semantic, "Семантическое сопоставление синонимов работы не сработало!")
            self.assertEqual(res_semantic[0], [0])
        finally:
            if os.path.exists(tmp_db):
                try:
                    os.remove(tmp_db)
                except Exception:
                    pass

    def test_llm_json_extractor_resilience(self):
        """Проверка устойчивости парсера JSON к синтаксическим артефактам LLM."""
        llm = LLMClient()

        raw_trailing_comma = '{"selected_indices": [1, 2,], "reasoning": "Ok",}'
        decision = llm._extract_json_decision(raw_trailing_comma)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.selected_indices, [1, 2])

        raw_markdown = '```json\n{"selected_indices": [0], "reasoning": "Markdown test"}\n```'
        decision2 = llm._extract_json_decision(raw_markdown)
        self.assertIsNotNone(decision2)
        self.assertEqual(decision2.selected_indices, [0])

        raw_broken = 'Selected indices are: "selected_indices": [2, 3] and "reasoning": "Fixed"'
        decision3 = llm._extract_json_decision(raw_broken)
        self.assertIsNotNone(decision3)
        self.assertEqual(decision3.selected_indices, [2, 3])

    def test_telegram_notifier_status(self):
        """Проверка интерфейса Telegram Notifier."""
        t_disabled = TelegramNotifier(token="123", chat_id="456", enabled=False)
        self.assertFalse(t_disabled.is_active)
        self.assertFalse(t_disabled.send_message("Test"))

        t_enabled = TelegramNotifier(token="123", chat_id="456", enabled=True)
        self.assertTrue(t_enabled.is_active)

    def test_anketka_dashboard_survey_link_filtering(self):
        """Проверка фильтрации ссылок дашборда: исключение мусора и выбор целевого опроса (Анкетка и ИнтернетОпрос)."""
        from engines.js_snippets import JS_SCAN_PANEL_SURVEYS, JS_SCAN_ANKETKA_SURVEYS
        self.assertIn("hrefBlacklist", JS_SCAN_PANEL_SURVEYS)
        self.assertIn("textBlacklist", JS_SCAN_PANEL_SURVEYS)
        self.assertIn("enjoypanel", JS_SCAN_PANEL_SURVEYS)
        self.assertIn("survstat", JS_SCAN_PANEL_SURVEYS)

        # Проверка алгоритма фильтрации ссылок
        href_blacklist = ['gift', 'balance', 'faq', 'settings', 'history', 'partner', 'policies', 'about_omi', 'apple.com', 'google.com', 'rustore', 'mailto:', '#', 'charity', 'rules', 'conversion']
        text_blacklist = ['выбрать подарок', 'вывести деньги', 'история вознаграждений', 'пригласить друзей', 'настройки', 'помощь', 'главная', 'партнёром', 'политики и согласия', 'обменять баллы', 'правила проекта']

        links = [
            {"href": "/profile/gift", "text": "Выбрать подарок", "cls": "btn"},
            {"href": "/profile/balance-history", "text": "История вознаграждений", "cls": "link"},
            {"href": "https://apps.apple.com/app", "text": "App Store", "cls": "app-link"},
            {"href": "/partner/info", "text": "Становитесь нашим партнёром", "cls": "partner"},
            {"href": "/private#conversion", "text": "Обменять баллы", "cls": "active"},
            {"href": "/private#rules", "text": "Правила проекта", "cls": "active"},
            {"href": "https://router.omi.enjoypanel.com/redirects/96461/token", "text": "№96461 Быстрый опрос Пройти опрос", "cls": "survey-card_survey_card__Sf00q"},
            {"href": "https://router.survstat.ru?s=8259477b-5364-4b57", "text": "Пройти опрос", "cls": "sc-eddAHl gIzzMI"}
        ]

        valid_surveys = []
        for l in links:
            h = l["href"].lower()
            t = l["text"].lower()
            if any(b in h for b in href_blacklist):
                continue
            if any(b in t for b in text_blacklist):
                continue
            is_survey = "enjoypanel" in h or "survstat" in h or "survey_card" in l["cls"].lower() or "пройти опрос" in t
            if is_survey:
                valid_surveys.append(l)

        self.assertEqual(len(valid_surveys), 2)
        self.assertEqual(valid_surveys[0]["href"], "https://router.omi.enjoypanel.com/redirects/96461/token")
        self.assertEqual(valid_surveys[1]["href"], "https://router.survstat.ru?s=8259477b-5364-4b57")

    def test_survey_hub_selection_and_ranking(self):
        """Проверка работы экрана хаба выбора опросов (Survstat, Router-Client)."""
        from engines.js_snippets import JS_HANDLE_SURVEY_HUB
        self.assertIn("selectSurveyConfirmation", JS_HANDLE_SURVEY_HUB)
        self.assertIn("SurveyLink_surveyLink", JS_HANDLE_SURVEY_HUB)
        self.assertIn("cards.sort", JS_HANDLE_SURVEY_HUB)

        # Проверка логики ранжирования карточек по максимальному вознаграждению
        raw_cards = [
            {"title": "Исследование аудитории", "text": "до 10 баллов короткий"},
            {"title": "Исследование рынка", "text": "до 25 баллов 15 мин"},
            {"title": "Короткий опрос", "text": "до 15 баллов короткий"}
        ]
        import re
        def get_reward(c):
            m = re.search(r'(\d+)\s*(?:балл|руб|₽)', c["text"])
            return int(m.group(1)) if m else 0

        sorted_cards = sorted(raw_cards, key=get_reward, reverse=True)
        self.assertEqual(sorted_cards[0]["title"], "Исследование рынка")
        self.assertEqual(get_reward(sorted_cards[0]), 25)
        self.assertEqual(sorted_cards[1]["title"], "Короткий опрос")
        self.assertEqual(get_reward(sorted_cards[1]), 15)

    def test_presurvey_demographics_snippet(self):
        """Проверка сниппета заполнения демографии на стартовом экране (Пол, Дата рождения)."""
        from engines.js_snippets import JS_SOLVE_PRESURVEY_DEMOGRAPHICS
        self.assertIn("targetGender", JS_SOLVE_PRESURVEY_DEMOGRAPHICS)
        self.assertIn("DropDown_container", JS_SOLVE_PRESURVEY_DEMOGRAPHICS)
        self.assertIn("setNativeValue", JS_SOLVE_PRESURVEY_DEMOGRAPHICS)
        self.assertIn("actions", JS_SOLVE_PRESURVEY_DEMOGRAPHICS)

    def test_no_has_text_in_js_snippets(self):
        """Проверка отсутствия невалидного псевдоселектора :has-text в браузерных JS-сниппетах."""
        import engines.js_snippets as jss
        for name, val in vars(jss).items():
            if name.startswith("JS_") and isinstance(val, str):
                self.assertNotIn(":has-text", val, f"Найден невалидный :has-text в JS сниппете {name}")

    def test_router_error_snapshot_method(self):
        """Проверка наличия метода save_error_snapshot в роутере."""
        from engines.router import SurveyRouter
        self.assertTrue(hasattr(SurveyRouter, "save_error_snapshot"))
        self.assertTrue(hasattr(SurveyRouter, "_fill_presurvey_demographics"))
        self.assertTrue(hasattr(SurveyRouter, "handle_universal_post_survey"))

    def test_finish_actions_snippet(self):
        """Проверка сниппета действий завершения опроса."""
        from engines.js_snippets import JS_CHECK_AND_HANDLE_FINISH_ACTIONS
        self.assertIn("подобрать опрос", JS_CHECK_AND_HANDLE_FINISH_ACTIONS)
        self.assertIn("личный кабинет", JS_CHECK_AND_HANDLE_FINISH_ACTIONS)
        self.assertIn("clicked_next_survey_btn", JS_CHECK_AND_HANDLE_FINISH_ACTIONS)
        self.assertNotIn(":has-text", JS_CHECK_AND_HANDLE_FINISH_ACTIONS)

    def test_platform_cabinet_urls_and_hub(self):
        """Проверка сопоставления корневых адресов кабинетов и наличия hub.html."""
        from engines.router import get_platform_cabinet_url, PANEL_SITES
        self.assertEqual(get_platform_cabinet_url("https://router-client.survstat.ru/client/finish/123"), "https://internetopros.ru/private")
        self.assertEqual(get_platform_cabinet_url("https://www.anketka.ru/survey/123"), "https://www.anketka.ru/profile")
        self.assertEqual(get_platform_cabinet_url("https://panel.anketolog.ru/survey/123"), "https://panel.anketolog.ru/survey/invite/invitelist")
        self.assertEqual(get_platform_cabinet_url("https://survey-studio.com/s/123"), "https://panel.expertnoemnenie.ru/surveys")
        self.assertEqual(get_platform_cabinet_url("https://profiresearch.net/proj/123/"), "https://profiresearch.net/user/")
        self.assertEqual(get_platform_cabinet_url("https://www.moemnenie.ru/poll/123"), "https://www.moemnenie.ru/profile")

        self.assertEqual(len(PANEL_SITES), 7)
        import os
        self.assertTrue(os.path.exists("data/hub.html"))
        with open("data/hub.html", "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Центр Опросных Платформ", content)
            self.assertIn("countdown", content)
            self.assertIn("Анкетка", content)
            self.assertIn("ИнтернетОпрос", content)

    def test_open_text_age_and_selector_matching(self):
        """Проверка правильного ответа на возраст и универсальности селекторов открытых полей."""
        brain = SurveyBrain()
        self.assertEqual(brain.answer_open_text("Сколько Вам полных лет?"), "21")
        self.assertEqual(brain.answer_open_text("Укажите Ваш возраст"), "21")
        self.assertEqual(brain.answer_open_text("Ваш возраст:"), "21")

        # Проверка селекторов в CloudSurveyEngine
        from engines.cloudsurvey import CloudSurveyEngine
        import inspect
        source = inspect.getsource(CloudSurveyEngine.handle_open_text_blocks)
        self.assertIn("input.input__input", source)
        self.assertIn("input.mrEdit", source)
        self.assertIn(".question-card input", source)
        self.assertIn(".oe1 input", source)
        self.assertIn("input:not([type])", source)
        self.assertIn("HTMLInputElement.prototype", source)

    def test_multi_site_dashboard_rotation(self):
        """Проверка логики мульти-ротации по сайтам в engines/router.py."""
        from engines.router import PANEL_SITES
        self.assertEqual(len(PANEL_SITES), 7)
        for i, site in enumerate(PANEL_SITES):
            next_idx = (i + 1) % len(PANEL_SITES)
            self.assertEqual(PANEL_SITES[next_idx]["id"], PANEL_SITES[(i + 1) % 7]["id"])

    def test_birth_date_dropdown_selection(self):
        """Проверка выбора даты рождения из выпадающих списков: день (27), месяц (Июнь), год (2005)."""
        brain = SurveyBrain()
        days = [str(i) for i in range(1, 32)]
        d_day = brain.decide("Число:", days, False)
        self.assertEqual(days[d_day.selected_indices[0]], "27")

        months = ["Января", "Февраля", "Марта", "Апреля", "Мая", "Июня", "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"]
        d_month = brain.decide("Месяц:", months, False)
        self.assertEqual(months[d_month.selected_indices[0]], "Июня")

        years = [str(y) for y in range(2026, 1920, -1)]
        d_year = brain.decide("Год:", years, False)
        self.assertEqual(years[d_year.selected_indices[0]], "2005")

        # Ребенок: 05.03.2023
        c_day = brain.decide("Число рождения ребенка:", days, False)
        self.assertEqual(days[c_day.selected_indices[0]], "5")
        c_month = brain.decide("Месяц рождения ребенка:", months, False)
        self.assertEqual(months[c_month.selected_indices[0]], "Марта")
        c_year = brain.decide("Год рождения ребенка:", years, False)
        self.assertEqual(years[c_year.selected_indices[0]], "2023")

    def test_presurvey_button_and_gender_selection(self):
        """Проверка точности селекторов пре-опросных экранов (Survstat / CloudSurvey)."""
        import re
        html_snippet = '''
        <div id="root">
          <div class="StackItem_stackItem__CkLmS">
            <div class="Answer_wrapper__K04k3"><input class="Radio_radio__0j2QV" type="radio"><label>Мужской</label></div>
            <div class="Answer_wrapper__K04k3"><input class="Radio_radio__0j2QV" type="radio"><label>Женский</label></div>
          </div>
          <div class="Button_buttonContainer__868Xb">
            <div class="Button_button__c0lXg">Начать опрос</div>
          </div>
        </div>
        '''
        # Проверяем, что класс кнопки Начать опрос содержит Button_button__ и не Container
        self.assertTrue(re.search(r'class="[^"]*Button_button__[^"]*"', html_snippet))
        button_classes = re.findall(r'class="([^"]*Button_button[^"]*)"', html_snippet)
        # Первый класс - Container, второй - целевая кнопка
        self.assertEqual(len(button_classes), 2)
        target_btn_class = [c for c in button_classes if "Container" not in c][0]
        self.assertIn("Button_button__", target_btn_class)
        self.assertNotIn("Container", target_btn_class)

    def test_gender_selection_without_gender_word_in_question(self):
        """Проверка выбора пола, даже если в вопросе нет слова 'пол' (например, 'Время опросов')."""
        brain = SurveyBrain()
        opts = ["Мужской", "Женский"]
        # Вопрос с заголовком экрана без слова 'пол'
        decision1 = brain.decide("Время опросов 🎉", opts, False)
        self.assertEqual(opts[decision1.selected_indices[0]], "Мужской")

        # Пустой вопрос
        decision2 = brain.decide("", opts, False)
        self.assertEqual(opts[decision2.selected_indices[0]], "Мужской")

        # Открытый вопрос
        self.assertEqual(brain.answer_open_text("Укажите Ваш пол:"), "Мужской")

    def test_anketolog_and_panel_blacklist(self):
        """Проверка исключения навигационных ссылок invitelist и приоритета реальных опросов."""
        from engines.js_snippets import JS_SCAN_PANEL_SURVEYS, JS_ROUTER_CHECK_FINISHED
        self.assertIn("invitelist", JS_SCAN_PANEL_SURVEYS)
        self.assertIn("/ri/", JS_SCAN_PANEL_SURVEYS)
        self.assertIn("копировать ссылку", JS_SCAN_PANEL_SURVEYS)
        # Проверяем, что субдомен profile.ru.enjoysurvey.com не ломается черным списком
        self.assertIn("pathBlacklist", JS_SCAN_PANEL_SURVEYS)
        # Проверяем токены финиша
        self.assertIn("finishtoken", JS_ROUTER_CHECK_FINISHED)
        self.assertIn("100% пройдено", JS_ROUTER_CHECK_FINISHED)


    def test_panel_manager_and_demographics(self):
        """Проверка модулей PanelManager и DemographicsManager."""
        from engines.panel_manager import PanelManager, get_platform_cabinet_url
        from engines.demographics import DemographicsManager

        # Проверка маршрутов PanelManager
        self.assertTrue(PanelManager.is_cabinet_page("https://panel.anketolog.ru/survey/invite/invitelist"))
        self.assertTrue(PanelManager.is_cabinet_page("https://www.anketka.ru/profile"))
        self.assertFalse(PanelManager.is_cabinet_page("http://127.0.0.1:8888/surveystudio"))

        self.assertTrue(PanelManager.is_active_survey_url("http://127.0.0.1:8888/surveystudio"))
        self.assertTrue(PanelManager.is_active_survey_url("https://router-client.survstat.ru/client/123"))
        self.assertFalse(PanelManager.is_active_survey_url("https://panel.anketolog.ru/survey/invite/invitelist"))

        # Локальный тестовый URL не должен определяться как дашборд
        self.assertFalse(PanelManager.is_dashboard("http://127.0.0.1:8888/surveystudio"))
        self.assertTrue(PanelManager.is_dashboard("https://www.anketka.ru/profile"))

        # Проверка наличия методов DemographicsManager
        self.assertTrue(hasattr(DemographicsManager, "is_presurvey_screen"))
        self.assertTrue(hasattr(DemographicsManager, "fill_demographics"))
        self.assertTrue(hasattr(DemographicsManager, "click_start_button"))


if __name__ == "__main__":
    unittest.main()
