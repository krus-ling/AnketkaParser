import re

RU_NUMBERS = {
    "ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19, "двадцать": 20,
    "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70,
    "восемьдесят": 80, "девяносто": 90, "сто": 100
}

# Обратное сопоставление чисел до 100
NUM_TO_RU = {
    0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять",
    6: "шесть", 7: "семь", 8: "восемь", 9: "девять", 10: "десять",
    11: "одиннадцать", 12: "двенадцать", 13: "тринадцать", 14: "четырнадцать", 15: "пятнадцать",
    16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать", 19: "девятнадцать", 20: "двадцать",
    30: "тридцать", 40: "сорок", 50: "пятьдесят", 60: "шестьдесят", 70: "семьдесят",
    80: "восемьдесят", 90: "девяносто", 100: "сто"
}

POPULAR_CAR_MODELS = {
    "mitsubishi": "Outlander", "audi": "A8", "bmw": "X5", "mercedes": "E-Class",
    "toyota": "Camry", "volkswagen": "Tiguan", "hyundai": "Tucson", "kia": "Sportage",
    "chery": "Tiggo 7 Pro", "haval": "Jolion", "geely": "Monjaro", "nissan": "X-Trail",
    "mazda": "CX-5", "skoda": "Octavia", "citroen": "C5 Aircross", "xcite": "X-Cross 7"
}


class RulesEngine:
    def __init__(self, profile: dict):
        self.profile = profile

    def apply_open_text_rules(self, q_lower: str, is_ad_question: bool) -> str | None:
        if is_ad_question:
            return None

        auto = self.profile.get("auto", {}).get("current_car", {})
        personal = self.profile.get("personal", {})
        family = self.profile.get("family", {})

        # 1. Популярные модели авто
        for brand, model in POPULAR_CAR_MODELS.items():
            if brand in q_lower and any(w in q_lower for w in ["какая модель", "укажите модель", "модель вашего"]):
                return model

        # 2. Автомобиль пользователя
        if "марк" in q_lower and ("авто" in q_lower or "машин" in q_lower):
            return auto.get("brand", "Audi")
        elif "модел" in q_lower and ("авто" in q_lower or "машин" in q_lower):
            return auto.get("model", "A8")
        elif "год" in q_lower and ("авто" in q_lower or "машин" in q_lower):
            if any(w in q_lower for w in ["покупк", "приобрел", "купил"]):
                return str(auto.get("year_purchased", 2024))
            return str(auto.get("year_manufactured", 2022))

        # 3. Город и персональные контакты
        elif "федеральн" in q_lower and "округ" in q_lower:
            target_city = personal.get("city", "Москва").lower()
            if any(c in target_city for c in ["екатеринбург", "свердловск", "челябинск", "урал"]):
                return "Уральский федеральный округ"
            return "Центральный федеральный округ"
        elif "город" in q_lower or "где вы жив" in q_lower or "место жительства" in q_lower:
            return personal.get("city", "Москва")
        elif any(w in q_lower for w in ["номер телефон", "ваш телефон", "мобильный телефон"]):
            return personal.get("phone_number", "+79126746100")
        elif any(w in q_lower for w in ["электронная почта", "ваш email", "ваш e-mail", "укажите email"]):
            return "a.belov2005@gmail.com"
        elif any(w in q_lower for w in ["ваше имя", "как вас зовут"]) and "фамил" not in q_lower:
            return personal.get("first_name", "Александр")
        elif "фамили" in q_lower and "имя" not in q_lower:
            return personal.get("last_name", "Белов")
        elif re.search(r'\b(пол|gender)\b', q_lower) and not any(w in q_lower for w in ["лет", "возраст", "полных", "потолок", "ламинат", "паркет", "плитк"]):
            return personal.get("gender", "Мужской")

        # 4. Устройства
        elif "смартфон" in q_lower or "телефон" in q_lower:
            return self.profile.get("devices_and_gadgets", {}).get("smartphone_brand", "Samsung")
        elif "планшет" in q_lower:
            return "Lenovo"

        # 5. ДАТЫ РОЖДЕНИЯ И ВОЗРАСТ (КРИТИЧНО: сначала проверяем ребенка!)
        is_child_related = any(w in q_lower for w in ["ребен", "дет", "сына", "дочер", "малыш"])

        # Отдельные поля: день/число, месяц, год рождения
        if ("число" in q_lower or "день" in q_lower) and ("рождения" in q_lower or "родились" in q_lower) and "дата" not in q_lower:
            return "5" if is_child_related else str(personal.get("birth_day", "27"))
        if "месяц" in q_lower and ("рождения" in q_lower or "родились" in q_lower) and "дата" not in q_lower:
            return "3" if is_child_related else str(personal.get("birth_month", "6"))
        if "год" in q_lower and ("рождения" in q_lower or "родились" in q_lower) and "дата" not in q_lower:
            return "2023" if is_child_related else str(personal.get("birth_year", "2005"))

        has_dob_trigger = ("рождения" in q_lower or "родились" in q_lower) and any(w in q_lower for w in ["дата", "дату", "число", "день", "когда"])
        if has_dob_trigger:
            if is_child_related:
                return "05.03.2023"
            return personal.get("birth_date_formatted", "27.06.2005")

        if is_child_related and any(w in q_lower for w in ["возраст", "сколько лет", "полных лет"]):
            child_age = family.get("children", [{}])[0].get("age", 3)
            return str(child_age)

        if ("возраст" in q_lower or ("сколько" in q_lower and "лет" in q_lower) or "полных лет" in q_lower) and not is_child_related:
            return str(personal.get("age", 21))

        # 6. КОЛИЧЕСТВЕННЫЕ ВОПРОСЫ (НЕ ДЕНЬГИ!)
        if is_child_related and any(w in q_lower for w in ["сколько у вас детей", "количество детей", "число детей"]):
            return str(family.get("children_under_18_count", 1))

        if ("семь" in q_lower or "прожива" in q_lower) and any(w in q_lower for w in ["человек", "состав", "вместе"]):
            return str(family.get("household_members_count", 3))

        if any(w in q_lower for w in ["сколько автомобилей", "машин в семье", "автомобилей у вас"]):
            return "1"

        if any(w in q_lower for w in ["сигарет в день", "сколько сигарет"]):
            return "5"

        # 7. ФИНАНСОВЫЕ ВОПРОСЫ (СУММЫ, ЦЕНЫ, ЧЕКИ)
        has_finance_trigger = any(w in q_lower for w in [
            "сумм", "рубл", "стоимост", "цена", "чек", "тратит", "потрат",
            "расход", "бюджет", "доход", "зарплат"
        ]) or ("скольк" in q_lower and any(w in q_lower for w in ["денег", "платит", "руб", "отда"]))

        if has_finance_trigger and "лет" not in q_lower:
            return "2500"

        # 8. Профессия и должность
        if any(w in q_lower for w in ["професси", "должност", "кем вы работаете", "специализаци", "род занятий"]):
            return self.profile.get("education_and_career", {}).get("specialization", "Разработчик мобильных приложений")

        # 9. Программы лояльности и валюты
        if "валют" in q_lower and ("программ" in q_lower or "лояльност" in q_lower or "клуб" in q_lower):
            if "спартак" in q_lower:
                return "Денарии"
            elif "сбер" in q_lower:
                return "СберСпасибо"
            elif "яндекс" in q_lower:
                return "Баллы Плюса"
            elif any(w in q_lower for w in ["х5", "перекресток", "пятерочк"]):
                return "Апельсинки"
            elif any(w in q_lower for w in ["wildberries", "вайлдберриз"]):
                return "WB рубли"
            elif any(w in q_lower for w in ["ozon", "озон"]):
                return "Баллы Ozon"
            return "Баллы"

        if "программ" in q_lower and "лояльност" in q_lower:
            if any(w in q_lower for w in ["какими пользуетесь", "в каких состоите", "участником каких"]):
                return "Яндекс Плюс, СберСпасибо, Т-Банк"
            elif any(w in q_lower for w in ["что важно", "почему", "нравится"]):
                return "Кешбэк рублями или бонусами, скидки на регулярные покупки и прозрачные условия"
            return "СберСпасибо, Яндекс Плюс, Т-Банк, Х5 Клуб, Магнит, Ozon"

        return None

    def apply_chat_rules(self, q_lower: str) -> str | None:
        personal = self.profile.get("personal", {})
        career = self.profile.get("education_and_career", {})
        first_name = personal.get("first_name", "Александр")
        last_name = personal.get("last_name", "Белов")

        if any(w in q_lower for w in ["как вас зовут", "ваше имя", "назовите имя"]) and "фамили" not in q_lower:
            return first_name
        elif "фамилия" in q_lower and "имя" not in q_lower:
            return last_name
        elif "фио" in q_lower or "полное имя" in q_lower or ("имя" in q_lower and "фамили" in q_lower):
            return f"{first_name} {last_name}"
        elif "возраст" in q_lower or ("сколько" in q_lower and "лет" in q_lower):
            return str(personal.get("age", 21))
        elif any(w in q_lower for w in ["в каком городе", "где вы живете", "откуда вы"]):
            return personal.get("city", "Москва")
        elif any(w in q_lower for w in ["кем вы работаете", "ваша профессия", "ваша должность"]):
            return career.get("specialization", "Разработчик мобильных приложений")
        elif any(w in q_lower for w in ["есть ли у вас дети", "у вас есть дети", "дети есть"]):
            return "Да, у меня один ребенок, сын 3 года."
        elif any(w in q_lower for w in ["семейное положение", "вы женаты", "состоите в браке"]):
            return "Женат."
        elif any(w in q_lower for w in ["есть ли у вас автомобиль", "на чем ездите", "какая машина"]):
            return "Да, вожу личный автомобиль Audi A8."
        elif any(w in q_lower for w in ["домашние животные", "есть ли питомцы"]):
            return "Да, у меня дома кошка и собака."

        return None

    def solve_math(self, question_text: str, options: list[str]) -> list[int] | None:
        q_clean = question_text.lower().replace("?", "").replace("!", "").replace(",", "")

        # Шаблоны для сложения, вычитания, умножения
        pattern = r'([а-яёa-z0-9]+)\s*(плюс|минус|прибавить|отнять|умножить на|\+|\-|\*|х)\s*([а-яёa-z0-9]+)'
        match = re.search(pattern, q_clean)

        if match:
            raw_a, op, raw_b = match.groups()
            val_a = int(raw_a) if raw_a.isdigit() else RU_NUMBERS.get(raw_a)
            val_b = int(raw_b) if raw_b.isdigit() else RU_NUMBERS.get(raw_b)

            if val_a is not None and val_b is not None:
                if op in ["плюс", "прибавить", "+"]:
                    result = val_a + val_b
                elif op in ["минус", "отнять", "-"]:
                    result = val_a - val_b
                elif op in ["умножить на", "*", "х"]:
                    result = val_a * val_b
                else:
                    return None

                result_str_digit = str(result)
                result_str_word = NUM_TO_RU.get(result, "").lower()
                wants_word = "словом" in q_clean or "буквами" in q_clean

                for idx, opt in enumerate(options):
                    opt_lower = opt.lower().strip()
                    if wants_word and result_str_word and result_str_word == opt_lower:
                        return [idx]
                    elif not wants_word and (result_str_digit == opt_lower or result_str_word == opt_lower):
                        return [idx]
        return None

    def check_traps(self, question_text: str, options: list[str]) -> list[int] | None:
        q_lower = question_text.lower()
        opt_lowers = [opt.lower().strip() for opt in options]

        # === 0. ПРОВЕРКИ НА ВНИМАТЕЛЬНОСТЬ (ATTENTION CHECKS) ===
        # Например: «В качестве проверки выберите третий вариант», «Выберите ответ "Полностью согласен"»
        is_attention_q = any(w in q_lower for w in [
            "внимательност", "внимания", "вниманием", "внимательны", "контрольный вопрос", "проверочный вопрос"
        ]) or ("проверк" in q_lower and "вниман" in q_lower)

        if is_attention_q:
            # 1. Поиск указания порядкового номера: «выберите третий/второй/первый вариант»
            ordinal_map = {
                "первый": 0, "второй": 1, "третий": 2, "четвертый": 3, "пятый": 4,
                "1": 0, "2": 1, "3": 2, "4": 3, "5": 4
            }
            for word, target_idx in ordinal_map.items():
                if f"{word} вариант" in q_lower or f"вариант {word}" in q_lower or f"пункт {word}" in q_lower or f"вариант под номером {word}" in q_lower:
                    if target_idx < len(options):
                        return [target_idx]

            # 2. Поиск прямого цитирования нужного варианта в вопросе («выберите "Категорически не согласен"»)
            for idx, opt in enumerate(opt_lowers):
                if len(opt) > 3 and opt in q_lower:
                    return [idx]

        # === ВЫБОР НАГРАДЫ / ФИНАЛ ОПРОСА (ТОЛЬКО ДЕНЬГИ!) ===
        if any(w in q_lower for w in ["наград", "вознагражден", "выберите приз", "способ получения", "куда перечислить", "форма вознаграждения", "выберите способ", "получить вознаграждение", "заберите свою первую награду", "выберите награду"]):
            money_keywords = ["деньги", "рубли", "на счет", "баланс", "выплата", "на карту", "кошелек", "руб.", "на телефон", "мобильный"]
            bad_keywords = ["благотворительн", "фонд", "подарок", "купон", "сертификат", "лотере", "приз", "баллы", "шанс", "статьи", "анкоины"]
            for idx, opt in enumerate(opt_lowers):
                if any(m in opt for m in money_keywords) and not any(b in opt for b in bad_keywords):
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if any(m in opt for m in money_keywords):
                    return [idx]

        # === 1. АВТОМОБИЛЬ И ВОДИТЕЛЬСКИЕ ПРАВА ===
        # Наличие личного автомобиля
        if any(w in q_lower for w in ["есть ли у вас", "наличие у вас", "владеете ли вы", "являетесь ли владельцем"]) and any(a in q_lower for a in ["автомоб", "машин"]):
            for idx, opt in enumerate(opt_lowers):
                if any(pos in opt for pos in ["да, это мой личный", "мой личный", "да, личный", "да, у меня есть личный", "один личный"]):
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if opt in ["да", "есть", "да, есть"]:
                    return [idx]

        # Водительские права
        if any(w in q_lower for w in ["водительское удостоверение", "водительские права", "права на управление"]):
            for idx, opt in enumerate(opt_lowers):
                if any(pos in opt for pos in ["да, есть", "имеются", "категория b", "категории b"]) or opt == "да":
                    return [idx]

        # Год авто
        if "год" in q_lower and ("авто" in q_lower or "машин" in q_lower):
            if "покупк" in q_lower or "приобрел" in q_lower or "купил" in q_lower:
                car_year = str(self.profile.get("auto", {}).get("current_car", {}).get("year_purchased", 2024))
            else:
                car_year = str(self.profile.get("auto", {}).get("current_car", {}).get("year_manufactured", 2022))
            for idx, opt in enumerate(opt_lowers):
                if car_year in opt:
                    return [idx]

        # Отношение к марке
        if "отношение" in q_lower and ("изменилось" in q_lower or "марк" in q_lower or "бренд" in q_lower):
            for idx, opt in enumerate(opt_lowers):
                if "не изменилось" in opt:
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if "в лучшую сторону" in opt:
                    return [idx]

        # Марка авто (если спрашивают марку)
        if ("какая марка" in q_lower or "марка вашего" in q_lower) and ("авто" in q_lower or "машин" in q_lower):
            for idx, opt in enumerate(opt_lowers):
                if "audi" in opt or "ауди" in opt:
                    return [idx]

        # === 2. ГОРОД, РЕГИОН И ФЕДЕРАЛЬНЫЙ ОКРУГ ===
        if "федеральн" in q_lower and "округ" in q_lower:
            target_city = self.profile.get("personal", {}).get("city", "Москва").lower()
            target_region = self.profile.get("personal", {}).get("region", "Москва").lower()
            if any(c in target_city or c in target_region for c in ["екатеринбург", "свердловск", "челябинск", "тюмен", "курган", "урал"]):
                target_fo = "уральск"
            elif any(c in target_city or c in target_region for c in ["петербург", "питер", "ленинград", "новгород", "псков", "мурманск"]):
                target_fo = "северо-западн"
            elif any(c in target_city or c in target_region for c in ["новосибирск", "омск", "красноярск", "томск", "барнаул"]):
                target_fo = "сибирск"
            elif any(c in target_city or c in target_region for c in ["казан", "татарстан", "нижний новгород", "самара", "уфа", "перм"]):
                target_fo = "приволжск"
            elif any(c in target_city or c in target_region for c in ["ростов", "краснодар", "волгоград", "сочи"]):
                target_fo = "южн"
            else:
                target_fo = "центральн"

            for idx, opt in enumerate(opt_lowers):
                if target_fo in opt:
                    return [idx]

        if any(w in q_lower for w in ["город", "где вы жив", "где прожива", "населенн", "место жительства", "в каком регионе"]):
            target_city = self.profile.get("personal", {}).get("city", "Москва").lower()
            for idx, opt in enumerate(opt_lowers):
                if opt == target_city or opt == f"г. {target_city}" or opt == f"город {target_city}":
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if target_city in opt and len(opt) < 25 and not any(w in opt for w in ["клуб", "спартак", "динамо", "цска", "локомотив"]):
                    return [idx]

        if "принимает решение" in q_lower or "принимаете решение" in q_lower:
            for idx, opt in enumerate(opt_lowers):
                if any(w in opt for w in ["я самостоятельно", "единолично", "самостоятельно"]):
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if "посоветовавшись" in opt:
                    return [idx]

        # === 3. ФИНАНСЫ И ДОХОДЫ ===
        finance = self.profile.get("finance", {})

        # Доход на одного члена семьи
        if "доход" in q_lower and ("на одного члена" in q_lower or ("член" in q_lower and "семь" in q_lower)):
            for idx, opt in enumerate(opt_lowers):
                if "200 000" in opt and "219 999" in opt:
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if "200 000" in opt:
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if any(num in opt for num in ["200", "210", "220"]) and "000" in opt:
                    return [idx]

        # Личный ежемесячный доход
        elif "доход" in q_lower and any(w in q_lower for w in ["личный", "ваш ежемесячный", "вы лично", "ваш личный"]):
            for idx, opt in enumerate(opt_lowers):
                if "350 000" in opt and "399 999" in opt:
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if "350 000" in opt:
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if any(num in opt for num in ["350", "360", "370", "380", "390"]) and "000" in opt:
                    return [idx]

        # Финансовое положение
        if any(w in q_lower for w in ["материальное положение", "финансовое положение", "описывает доход", "хватает денег", "можете позволить"]):
            for idx, opt in enumerate(opt_lowers):
                if any(w in opt for w in ["кроме покупки квартиры", "квартиры или дачи", "практически всё", "почти всё"]):
                    return [idx]
                if "автомобиль" in opt and "не можем" not in opt and "затруднитель" not in opt:
                    return [idx]

        # === 4. СЕМЕЙНОЕ ПОЛОЖЕНИЕ И ПОЛ ===
        if any(w in q_lower for w in ["семейное положение", "состоите ли вы в браке", "брачный статус", "ваш брак"]):
            for idx, opt in enumerate(opt_lowers):
                if any(w in opt for w in ["женат", "замужем", "состою в зарегистрированном браке", "состою в браке", "гражданский брак"]) and not opt.startswith("не ") and " не " not in opt:
                    return [idx]

        # Пол (Мужской / Женский)
        has_gender_opts = (
            len(opt_lowers) in [2, 3, 4] and
            any(re.search(r'\bмуж', o) or o == "м" for o in opt_lowers) and
            any(re.search(r'\bжен', o) or o == "ж" for o in opt_lowers)
        )
        is_gender_q = (
            any(w in q_lower for w in ["пол", "gender", "мужчина или женщина"]) and
            not any(w in q_lower for w in ["напольное", "потолок", "полотенц", "поликлиник", "полка", "полгода", "полон", "половин"])
        )
        if has_gender_opts or is_gender_q:
            target_gender = self.profile.get("personal", {}).get("gender", "Мужской").lower()
            is_male = "муж" in target_gender
            for idx, opt in enumerate(opt_lowers):
                if is_male and (re.search(r'\bмуж', opt) or opt == "м"):
                    return [idx]
                if not is_male and (re.search(r'\bжен', opt) or opt == "ж"):
                    return [idx]

        # === ДАТА РОЖДЕНИЯ (ДЕНЬ / ЧИСЛО, МЕСЯЦ, ГОД) В ВЫПАДАЮЩИХ СПИСКАХ И КАРТОЧКАХ ===
        is_child_q = any(w in q_lower for w in ["ребен", "дет", "сына", "дочер", "малыш"])

        # 1. День / Число рождения (1..31)
        is_day_options = (
            len(options) in range(28, 33) and
            opt_lowers[0].strip() in ["1", "01"] and
            opt_lowers[-1].strip() in ["28", "29", "30", "31"]
        )
        is_day_q = (
            any(w in q_lower for w in ["число", "день рождения", "день", "какого числа", "дата рождения"]) and
            not any(w in q_lower for w in ["недел", "рабочих", "сколько дней", "дней в"])
        )
        if is_day_options or (is_day_q and len(options) <= 32 and any(o.strip() in ["27", "05", "5"] for o in opt_lowers)):
            target_day = "5" if is_child_q else str(self.profile.get("personal", {}).get("birth_day", "27"))
            for idx, opt in enumerate(opt_lowers):
                cleaned = opt.strip().lstrip("0")
                if cleaned == target_day.lstrip("0") or opt.strip() == target_day or opt.strip() == f"{int(target_day):02d}":
                    return [idx]

        # 2. Месяц рождения (1..12 или Январь..Декабрь)
        is_month_names = len(options) == 12 and any("январ" in o for o in opt_lowers[:2])
        is_month_q = (
            any(w in q_lower for w in ["месяц рождения", "месяц", "укажите месяц"]) and
            not any(w in q_lower for w in ["сколько месяцев", "последние 12", "за последние", "в течение"])
        )
        if is_month_names or (is_month_q and len(options) <= 13):
            # Ребенок: 3 (Март), Пользователь: 6 (Июнь)
            target_month_num = 3 if is_child_q else int(self.profile.get("personal", {}).get("birth_month", 6))
            month_keywords = [
                ["январ", "01", "1"], ["феврал", "02", "2"], ["март", "03", "3"],
                ["апрел", "04", "4"], ["ма", "05", "5"], ["июн", "06", "6"],
                ["июл", "07", "7"], ["август", "08", "8"], ["сентябр", "09", "9"],
                ["октябр", "10", "10"], ["ноябр", "11", "11"], ["декабр", "12", "12"]
            ]
            patterns = month_keywords[target_month_num - 1]
            for idx, opt in enumerate(opt_lowers):
                cleaned = opt.strip()
                if any(p == cleaned or (len(p) > 2 and p in opt) for p in patterns):
                    return [idx]

        # 3. Год рождения
        is_year_list = len(options) >= 20 and any(re.match(r'^(19|20)\d{2}$', o.strip()) for o in opt_lowers[:5])
        is_year_q = (
            any(w in q_lower for w in ["год рождения", "ваш год", "в каком году вы родились", "год"]) and
            not any(w in q_lower for w in ["авто", "машин", "покупк", "последн", "сколько лет", "в этом году", "течение года"])
        )
        if is_year_list or (is_year_q and any("2005" in o for o in opt_lowers)):
            target_year = "2023" if is_child_q else str(self.profile.get("personal", {}).get("birth_year", "2005"))
            for idx, opt in enumerate(opt_lowers):
                if target_year in opt.strip():
                    return [idx]

        # Возраст пользователя
        if any(w in q_lower for w in ["возраст", "сколько вам лет", "сколько вам полных лет", "полных лет"]) and not any(w in q_lower for w in ["ребен", "дет"]):
            user_age = int(self.profile.get("personal", {}).get("age", 21))
            for idx, opt in enumerate(opt_lowers):
                match_range = re.findall(r'\d+', opt)
                if len(match_range) >= 2:
                    low, high = int(match_range[0]), int(match_range[1])
                    if low <= user_age <= high:
                        return [idx]
                elif len(match_range) == 1:
                    val = int(match_range[0])
                    if any(w in opt for w in ["младше", "до", "менее"]) and user_age <= val:
                        return [idx]
                    elif any(w in opt for w in ["старше", "от", "более"]) and user_age >= val:
                        return [idx]
                    elif val == user_age:
                        return [idx]

        # === 5. ДЕТИ И СОСТАВ СЕМЬИ ===
        kids_count = self.profile.get("family", {}).get("children_under_18_count", 1)
        household_size = self.profile.get("family", {}).get("household_members_count", 3)

        kids_str = str(kids_count)
        house_str = str(household_size)
        kids_word = NUM_TO_RU.get(int(kids_count), "один") if str(kids_count).isdigit() else "один"
        house_word = NUM_TO_RU.get(int(household_size), "три") if str(household_size).isdigit() else "три"

        # Наличие детей (Да / Нет / Да, есть дети)
        has_kids_q = any(w in q_lower for w in [
            "дети", "детей", "ребенок", "ребенка", "несовершеннолетн"
        ]) and any(w in q_lower for w in [
            "есть ли", "наличие", "имеются ли", "у вас есть", "проживают ли с вами", "до 18"
        ])
        if has_kids_q:
            # 1. Поиск прямого положительного ответа
            for idx, opt in enumerate(opt_lowers):
                if any(pos in opt for pos in ["да, есть", "есть дети", "да", "имеются", "один ребенок", "1 ребенок"]) and not any(neg in opt for neg in ["нет", "не имею", "ни одного", "не проживают"]):
                    return [idx]
            # 2. Если есть выбор между вариантами с детьми и без детей
            for idx, opt in enumerate(opt_lowers):
                if "дети" in opt and not any(neg in opt for neg in ["нет", "не", "без"]):
                    return [idx]

        if any(w in q_lower for w in ["сколько у вас детей", "количество детей", "число детей"]):
            for idx, opt in enumerate(opt_lowers):
                if opt == kids_str or opt == kids_word or kids_str == opt.split()[0] or f"{kids_str} ребенок" in opt or "один ребенок" in opt:
                    return [idx]

        if any(w in q_lower for w in ["детей до 18", "несовершеннолетних детей"]):
            for idx, opt in enumerate(opt_lowers):
                if opt == kids_str or opt == kids_word or kids_str == opt.split()[0]:
                    return [idx]

        if any(w in q_lower for w in ["проживает", "состав семьи", "человек в семье", "вместе с вами", "в вашей семье"]):
            for idx, opt in enumerate(opt_lowers):
                if opt == house_str or opt == house_word or house_str == opt.split()[0]:
                    return [idx]

        # === 6. КУРЕНИЕ, ПИТОМЦЫ, ОБРАЗОВАНИЕ, РАБОТА ===
        # Курение
        if any(w in q_lower for w in ["курите ли вы", "употребляете ли табачн", "употребляете ли никотин", "курите", "что из перечисленного вы курили", "курите ли"]):
            is_smoker = True  # Респондент курит (согласно data/profile.json)
            if is_smoker:
                # 1. Поиск конкретных категорий табачных изделий из профиля
                matched_types = []
                for idx, opt in enumerate(opt_lowers):
                    if any(bad in opt for bad in ["не курю", "никогда", "бросил", "не употребляю"]):
                        continue
                    if any(prod in opt for prod in [
                        "сигареты фабричного", "с фильтром", "системы нагревания", "iqos", "glo", "ploom",
                        "одноразовые электронные", "с картриджами", "вейп", "электронные сигареты"
                    ]):
                        matched_types.append(idx)
                if matched_types:
                    return matched_types

                # 2. Если вариантов изделий нет, а просто "Да/Нет" (строгая проверка слова 'да')
                for idx, opt in enumerate(opt_lowers):
                    if any(bad in opt for bad in ["не курю", "никогда", "бросил", "не употребляю"]):
                        continue
                    if any(w in opt for w in ["да, курю", "курю регулярно", "курю ежедневно", "курю", "употребляю"]) or opt == "да" or opt.startswith("да,") or re.search(r'\bда\b', opt):
                        return [idx]
            else:
                for idx, opt in enumerate(opt_lowers):
                    if any(w in opt for w in ["не курю", "никогда не курил", "нет"]):
                        return [idx]

        # Домашние животные
        if any(w in q_lower for w in ["домашние животные", "домашних животных", "питомцы", "есть ли животные"]):
            for idx, opt in enumerate(opt_lowers):
                if any(bad in opt for bad in ["нет", "никого", "не имею"]):
                    continue
                if any(w in opt for w in ["да, есть", "есть домашние", "кошка", "собака"]) or opt == "да" or opt.startswith("да,") or re.search(r'\bда\b', opt):
                    return [idx]

        # Образование
        if any(w in q_lower for w in ["уровень образования", "ваше образование"]):
            for idx, opt in enumerate(opt_lowers):
                if "высшее" in opt and "неполное" not in opt:
                    return [idx]

        # Статус занятости
        if any(w in q_lower for w in ["статус занятости", "ваша занятость", "род деятельности", "работаете ли"]):
            for idx, opt in enumerate(opt_lowers):
                if any(w in opt for w in ["полный рабочий день", "по найму", "работающий", "полная занятость"]):
                    return [idx]

        # === 7. ЛОВУШКИ И ОТРАСЛЕВЫЕ ФИЛЬТРЫ ===
        if any(kw in q_lower for kw in ["принимали ли вы участие", "участвовали ли вы", "в опросах"]):
            for idx, opt in enumerate(opt_lowers):
                if any(neg in opt for neg in ["нет", "не принимал", "не участвовал", "ни в каких"]):
                    return [idx]

        screening_markers = ["маркетинг", "реклам", "социологическ", "опрос", "пиар", " pr", "сми", "журналистик"]
        if any(any(m in opt for m in screening_markers) for opt in opt_lowers):
            for idx, opt in enumerate(opt_lowers):
                if any(neg in opt for neg in ["ни в одной", "ничего из", "ни один", "не работаю", "другая отрасль"]):
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if any(safe in opt for safe in ["it", "информационные технологии", "разработка", "программ", "строительство", "медицина"]):
                    return [idx]

        return None

    def filter_llm_decision(self, question_text: str, options: list[str], selected_indices: list[int],
                            is_multiselect: bool) -> list[int]:
        q_lower = question_text.lower()
        medical_and_sensitive_triggers = [
            "заболеван", "болезн", "страдаете", "инвалид", "рак", "онколог",
            "желуд", "кожи", "почек", "сердечн", "диагноз", "симптом", "терапи",
            "лечени", "опорно-двигател", "хирургич", "операци", "больниц", "клиник",
            "нервной систем", "жкт", "бросить", "курить", "курени", "попытк", "бросал"
        ]

        # Вопросы о проблемах и претензиях (где "Нет" - нормальный и желаемый ответ)
        problem_triggers = [
            "проблем", "трудности", "сложност", "сбои", "жалоб", "претензи",
            "нарекан", "дефект", "недостатк", "негатив", "ошибк"
        ]

        is_trap = any(w in q_lower for w in ['маркетинг', 'реклам', 'опрос', 'сми', 'журналист'])
        is_sensitive = any(trigger in q_lower for trigger in medical_and_sensitive_triggers)
        is_problem_question = any(trigger in q_lower for trigger in problem_triggers)

        # Отключаем анти-кик для вопросов о семье, детях, питомцах
        is_exempt_antikick = any(
            w in q_lower for w in ["дет", "ребен", "животн", "питомц", "беремен", "родственник", "домашн"]
        ) or is_problem_question

        safe_indices = []
        for idx in selected_indices:
            if idx < len(options):
                opt_txt = options[idx].lower()

                # Игнорируем кастомный ввод
                if any(custom in opt_txt for custom in
                       ["свой вариант", "другое", "другая", "другой", "иное", "впишите", "укажите"]):
                    print(f"\n🚫 [ФИЛЬТР]: Игнорируем '{options[idx]}'. Бот должен выбирать из предложенного.")
                    continue

                # АНТИ-КИК: Блокируем пассивные ответы, НО НЕ путаем с 'интернет' или 'немецкий'
                if not is_trap and not is_sensitive and not is_exempt_antikick:
                    # Проверяем отдельное слово 'нет', чтобы не блокировать 'интернет-банкинг'
                    has_bare_no = bool(re.search(r'(?:^|[\s,])нет(?:[\s,\.!]|$)', opt_txt))
                    has_passive = any(bad in opt_txt for bad in ["ничего", "не покупа", "не пользу", "затрудняюсь", "не знаю", "никаки"])
                    if has_bare_no or has_passive:
                        print(f"\n🛡️ [АНТИ-КИК]: LLM хотела выбрать '{options[idx]}', но это приведет к отсеву! Блокируем.")
                        continue

                safe_indices.append(idx)

        # Ограничение по количеству вариантов из текста вопроса (например, "не более 3 вариантов", "максимум 2")
        max_limit_match = re.search(r'(?:не более|максимум|до|не больше)\s*(\d+)', q_lower)
        if max_limit_match:
            try:
                max_allowed = int(max_limit_match.group(1))
                if max_allowed > 0 and len(safe_indices) > max_allowed:
                    safe_indices = safe_indices[:max_allowed]
                    try:
                        print(f"\n[ЛИМИТ ВАРИАНТОВ]: Вопрос требует не более {max_allowed} ответа. Урезаем выбор.")
                    except Exception:
                        pass
            except Exception:
                pass

        # Если после фильтрации ничего не осталось — берем активный безопасный вариант
        if not safe_indices and options:
            trap_words = ["маркетинг", "реклам", "социологическ", "опрос", "пиар", " pr", "сми", "журналист"]
            print("🛠️ [СИСТЕМА]: Принудительно выбираем активные стандартные варианты...")
            for i, opt in enumerate(options):
                opt_lower = opt.lower()
                is_opt_passive = any(bad in opt_lower for bad in ["ничего", "затрудняюсь", "другое", "свой вариант", "иное", "никаки"]) or bool(re.search(r'(?:^|[\s,])нет(?:[\s,\.!]|$)', opt_lower))
                is_opt_trap = any(t in opt_lower for t in trap_words)
                if not is_opt_passive and not is_opt_trap:
                    safe_indices.append(i)
                    if len(safe_indices) >= (2 if is_multiselect else 1):
                        break

            if not safe_indices:
                for i, opt in enumerate(options):
                    if not any(t in opt.lower() for t in trap_words):
                        safe_indices.append(i)
                        break

            if not safe_indices:
                safe_indices = [0]

        if is_sensitive or is_exempt_antikick:
            print(f"\n🩺 [ФИЛЬТР-ИСКЛЮЧЕНИЕ]: Вопрос распознан как исключение. Анти-кик отключен.")

        return safe_indices
