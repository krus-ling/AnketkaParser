import json
import re
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel, Field
from memory import SurveyMemory
import config

RU_NUMBERS = {
    "ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19, "двадцать": 20,
    "тридцать": 30, "сорок": 40, "пятьдесят": 50
}
NUM_TO_RU = {
    0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять",
    6: "шесть", 7: "семь", 8: "восемь", 9: "девять", 10: "десять",
    11: "одиннадцать", 12: "двенадцать", 13: "тринадцать", 14: "четырнадцать", 15: "пятнадцать",
    16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать", 19: "девятнадцать", 20: "двадцать"
}

POPULAR_CAR_MODELS = {
    "mitsubishi": "Outlander", "audi": "A6", "bmw": "X5", "mercedes": "E-Class",
    "toyota": "Camry", "volkswagen": "Tiguan", "hyundai": "Tucson", "kia": "Sportage",
    "chery": "Tiggo 7 Pro", "haval": "Jolion", "geely": "Monjaro", "nissan": "X-Trail",
    "mazda": "CX-5", "skoda": "Octavia", "citroen": "C5 Aircross", "xcite": "X-Cross 7"
}


class SurveyDecision(BaseModel):
    selected_indices: list[int] = Field(default_factory=lambda: [0])
    is_attention_check: bool = False
    requires_human: bool = False
    reasoning: str = ""


class SurveyBrain:
    def __init__(
            self,
            base_url: str = config.LLM_BASE_URL,
            api_key: str = config.LLM_API_KEY,
            model: str = config.LLM_MODEL,
            profile_path: str | Path = config.PROFILE_PATH
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.memory = SurveyMemory()
        with open(profile_path, "r", encoding="utf-8") as f:
            self.profile = json.load(f)

        self.ad_context = ""

        self.stats = {
            "total_answered": 0,
            "from_memory": 0,
            "from_rules": 0,
            "from_llm": 0
        }

    def _clean_text_artifacts(self, text: str) -> str:
        no_think = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Жесткая вырезка всех азиатских символов и специфичной пунктуации
        no_cjk = re.sub(
            r'[\u4e00-\u9fff\u3400-\u4dbf\u2e80-\u2fd5\uf900-\ufaff\u3000-\u303f\uff00-\uffef\u2000-\u206f]+', '',
            no_think)
        cleaned = re.sub(r'["\'`]+', '', no_cjk)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Защита от галлюцинаций модели на пустых вопросах
        if len(cleaned) < 2 or "нет информации" in cleaned.lower():
            return "Все отлично"

        return cleaned

    def answer_open_text(self, question_text: str) -> str:
        self.stats["total_answered"] += 1
        cached = self.memory.find_verified_answer(question_text)
        if cached:
            ans, note = cached
            self.stats["from_memory"] += 1
            print(f"[DB MEMORY] {note}")
            return str(ans)

        q_lower = question_text.lower()
        auto = self.profile.get("auto", {}).get("current_car", {})
        personal = self.profile.get("personal", {})

        is_ad_question = bool(self.ad_context) and any(w in q_lower for w in
                                                       ["кешбэк", "кэшбэк", "банк", "карте", "акци", "предложен",
                                                        "сумму", "размер", "процент", "услов"])

        if not is_ad_question:
            for brand, model in POPULAR_CAR_MODELS.items():
                if brand in q_lower:
                    self.stats["from_rules"] += 1
                    self.memory.save_record(question_text, "open_text", None, model, model,
                                            f"Модель бренда {brand}")
                    return model

            if "марк" in q_lower and ("авто" in q_lower or "машин" in q_lower):
                self.stats["from_rules"] += 1
                return auto.get("brand", "Audi")
            elif "модел" in q_lower and ("авто" in q_lower or "машин" in q_lower):
                self.stats["from_rules"] += 1
                return auto.get("model", "A8")
            elif "город" in q_lower:
                self.stats["from_rules"] += 1
                return personal.get("city", "Москва")
            elif "смартфон" in q_lower or "телефон" in q_lower:
                self.stats["from_rules"] += 1
                return self.profile.get("devices_and_gadgets", {}).get("smartphone_brand", "Samsung")
            elif "планшет" in q_lower:
                self.stats["from_rules"] += 1
                return "Lenovo"
            elif any(w in q_lower for w in ["сумм", "скольк", "рубл", "стоимост", "цена", "чек", "тратит"]):
                self.stats["from_rules"] += 1
                return "2500"
            elif "професси" in q_lower or "должност" in q_lower or "кем вы работаете" in q_lower:
                self.stats["from_rules"] += 1
                return self.profile.get("education_and_career", {}).get("specialization",
                                                                        "Разработчик мобильных приложений")

        self.stats["from_llm"] += 1
        ad_prompt_part = f"\nМАТЕРИАЛ ИЗ РЕКЛАМНОГО БАННЕРА:\n{self.ad_context}\n" if self.ad_context else ""

        system_prompt = f"""Ты — респондент коммерческого опроса на русском языке.
ПРОФИЛЬ:
{json.dumps(self.profile, ensure_ascii=False)}{ad_prompt_part}

ПРАВИЛА ОТВЕТА:
1. Если вопрос о рекламе или сумме/числе — напиши ТОЛЬКО конкретное число или значение (например: 1000, 50, 2500) без лишних слов и букв.
2. Не пиши английские слова вроде 'rubles', отвечай строго по-русски или цифрами.
3. Длина ответа — максимум 1-3 слова.
"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Вопрос: {question_text}\nКраткий ответ:"}
                ],
                temperature=0.0,
                timeout=config.LLM_TIMEOUT
            )
            ans = self._clean_text_artifacts(resp.choices[0].message.content.strip())
            ans = re.sub(r'^(ответ|сумма|размер|значение)[:\s\-]+', '', ans, flags=re.IGNORECASE).strip()
        except Exception as e:
            print(f"[!] Ошибка LLM генерации текста: {e}")
            ans = "1000"

        self.memory.save_record(question_text, "open_text", None, ans, ans, "Ответ по рекламе/контексту")
        return ans

    def generate_chat_response(self, question_text: str) -> str:
        self.stats["total_answered"] += 1
        cached = self.memory.find_verified_answer(question_text)
        if cached:
            ans, note = cached
            self.stats["from_memory"] += 1
            print(f"[DB MEMORY] {note}")
            return str(ans)

        q_lower = question_text.lower().strip()
        personal = self.profile.get("personal", {})

        if any(w in q_lower for w in ["как вас зовут", "ваше имя"]):
            self.stats["from_rules"] += 1
            ans = personal.get("first_name", "Егор")
        elif any(w in q_lower for w in ["фамилия"]):
            self.stats["from_rules"] += 1
            ans = personal.get("last_name", "Белов")
        elif any(w in q_lower for w in ["сколько вам лет", "возраст"]):
            self.stats["from_rules"] += 1
            ans = str(personal.get("age", 21))
        elif any(w in q_lower for w in ["в каком городе", "где вы живете"]):
            self.stats["from_rules"] += 1
            ans = personal.get("city", "Москва")
        else:
            self.stats["from_llm"] += 1
            system_prompt = f"""Ты — Егор, 21 год, Москва. Участвуешь в диалоговом опросе. Профиль:
{json.dumps(self.profile, ensure_ascii=False, indent=2)}
ПРАВИЛА: Отвечай строго на русском языке, 1 короткое предложение (5-10 слов) без биографии."""
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": question_text}],
                    temperature=0.2, timeout=config.LLM_TIMEOUT
                )
                ans = self._clean_text_artifacts(resp.choices[0].message.content.strip())
            except Exception:
                ans = "Всё прошло отлично, без проблем."

        self.memory.save_record(question_text, "chat", None, ans, ans, "Чат-ответ")
        return ans

    def _solve_math_attention_check(self, question_text: str, options: list[str]) -> list[int] | None:
        q_clean = question_text.lower().replace("?", "").replace("!", "")
        pattern = r'([а-яёa-z0-9]+)\s*(плюс|минус|прибавить|отнять|\+|\-)\s*([а-яёa-z0-9]+)'
        match = re.search(pattern, q_clean)

        if match:
            raw_a, op, raw_b = match.groups()
            val_a = int(raw_a) if raw_a.isdigit() else RU_NUMBERS.get(raw_a)
            val_b = int(raw_b) if raw_b.isdigit() else RU_NUMBERS.get(raw_b)

            if val_a is not None and val_b is not None:
                result = val_a + val_b if op in ["плюс", "прибавить", "+"] else val_a - val_b
                result_str_digit = str(result)
                result_str_word = NUM_TO_RU.get(result, "").lower()
                wants_word = "словом" in q_clean or "буквами" in q_clean

                for idx, opt in enumerate(options):
                    opt_lower = opt.lower().strip()
                    if wants_word and result_str_word == opt_lower:
                        return [idx]
                    elif not wants_word and (result_str_digit == opt_lower or result_str_word == opt_lower):
                        return [idx]
        return None

    def _check_deterministic_traps(self, question_text: str, options: list[str]) -> list[int] | None:
        q_lower = question_text.lower()
        opt_lowers = [opt.lower().strip() for opt in options]

        if "год" in q_lower and ("авто" in q_lower or "машин" in q_lower):
            if "покупк" in q_lower or "приобрел" in q_lower or "купил" in q_lower:
                car_year = str(self.profile.get("auto", {}).get("current_car", {}).get("year_purchased", 2024))
            else:
                car_year = str(self.profile.get("auto", {}).get("current_car", {}).get("year_manufactured", 2022))

            for idx, opt in enumerate(opt_lowers):
                if car_year in opt:
                    return [idx]

        if "отношение" in q_lower and ("изменилось" in q_lower or "марк" in q_lower or "бренд" in q_lower):
            for idx, opt in enumerate(opt_lowers):
                if "не изменилось" in opt:
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if "в лучшую сторону" in opt:
                    return [idx]

        target_city = self.profile.get("personal", {}).get("city", "Москва").lower()
        for idx, opt in enumerate(opt_lowers):
            if opt == target_city or opt == f"г. {target_city}" or opt == f"город {target_city}" or (
                    target_city in opt and len(opt) < 20):
                return [idx]

        if "принимает решение" in q_lower or "принимаете решение" in q_lower:
            for idx, opt in enumerate(opt_lowers):
                if any(w in opt for w in ["я самостоятельно", "единолично", "самостоятельно"]):
                    return [idx]
            for idx, opt in enumerate(opt_lowers):
                if "посоветовавшись" in opt:
                    return [idx]

        if any("мужской" in opt for opt in opt_lowers) and any("женский" in opt for opt in opt_lowers):
            target_gender = self.profile.get("personal", {}).get("gender", "Мужской").lower()
            for idx, opt in enumerate(opt_lowers):
                if target_gender in opt:
                    return [idx]

        if any(kw in q_lower for kw in ["принимали ли вы участие", "участвовали ли вы", "в опросах"]):
            for idx, opt in enumerate(opt_lowers):
                if any(neg in opt for neg in ["нет", "не принимал", "не участвовал", "ни в каких"]):
                    return [idx]

        screening_markers = ["маркетинг", "реклам", "социологическ", "опрос", "пиар", " pr", "сми", "журналистик"]
        if any(any(m in opt for m in screening_markers) for opt in opt_lowers):
            for idx, opt in enumerate(opt_lowers):
                if any(neg in opt for neg in ["ни в одной", "ничего из", "ни один", "не работаю"]):
                    return [idx]

        return None

    def decide(self, question_text: str, options: list[str], is_multiselect: bool = False) -> SurveyDecision:
        self.stats["total_answered"] += 1

        cached = self.memory.find_verified_answer(question_text, options)
        if cached:
            ans_indices, note = cached
            self.stats["from_memory"] += 1
            print(f"[DB MEMORY] {note}")
            return SurveyDecision(selected_indices=ans_indices, reasoning=note)

        math_choice = self._solve_math_attention_check(question_text, options)
        if math_choice is not None:
            self.stats["from_rules"] += 1
            res = SurveyDecision(selected_indices=math_choice, is_attention_check=True,
                                 reasoning="Арифметический расчет")
            self.memory.save_record(question_text, "math", options, res.selected_indices,
                                    [options[i] for i in res.selected_indices], res.reasoning)
            return res

        trap_choice = self._check_deterministic_traps(question_text, options)
        if trap_choice is not None:
            self.stats["from_rules"] += 1
            res = SurveyDecision(selected_indices=trap_choice, is_attention_check=True,
                                 reasoning="Правило профиля / жадный охват брендов")
            self.memory.save_record(question_text, "trap", options, res.selected_indices,
                                    [options[i] for i in res.selected_indices], res.reasoning)
            return res

        self.stats["from_llm"] += 1
        ad_info = f"\nКонтекст ранее показанного рекламного баннера:\n{self.ad_context}\n" if self.ad_context else ""

        system_prompt = f"""
Ты — активный респондент коммерческих опросов. Профиль:
{json.dumps(self.profile, ensure_ascii=False, indent=2)}{ad_info}
Твой точный возраст: 21 год. Твоя дата рождения строго зафиксирована в профиле. НИКОГДА и ни при каких обстоятельствах не придумывай себе другой возраст (например, 35-45 лет).
НИКОГДА не выдумывай себе болезни, диагнозы или наличие родственников-инвалидов, если этого прямо не указано в профиле. 
ВАЖНО: Внимательно изучи блок "lifestyle_and_fmcg"! Там указано, что ты КУРИШЬ и пьешь алкоголь. Никогда не отвечай, что ты "никогда не курил" или "не пью", строго следуй списку потребляемых брендов.

СТРОГИЕ ПРАВИЛА ПРОХОЖДЕНИЯ (ЗАПРЕТ НА ОТСЕВ):
1. ВОПРОСЫ-ЛОВУШКИ: Если спрашивают, работаешь ли ты в сферах: Маркетинг, Реклама, PR, СМИ, Журналистика, Социология — СТРОГО ЗАПРЕЩАЕТСЯ их выбирать! Всегда выбирай «Ни в одной из перечисленных». Если спрашивают про участие в опросах за последние месяцы — выбирай «Нет, не участвовал».
2. ПРАВИЛО АКТИВНОГО ПОТРЕБИТЕЛЯ: Во всех остальных вопросах СТРОГО ЗАПРЕЩАЕТСЯ выбирать варианты «Ничего из перечисленного», «Затрудняюсь ответить», «Не знаю». Опросникам нужны активные потребители. Выбирай 1-3 логичных положительных варианта.
3. КОНТЕКСТ РЕКЛАМЫ И ОЦЕНКИ: Оценивай рекламные предложения и продукты высокими баллами (4, 5, «Полностью согласен»).
4. ИЗБЕГАЙ СВОИХ ВАРИАНТОВ: Никогда не выбирай варианты ответа «Другое», «Другая», «Свой вариант», «Иное», «Другая марка». Всегда выбирай только из конкретных предложенных брендов или ответов.
5. Формат JSON (строго соблюдать):
{{
  "selected_indices": [0],
  "is_attention_check": false,
  "requires_human": false,
  "reasoning": "краткая логика выбора"
}}
"""
        options_formatted = "\n".join([f"[{i}] {opt}" for i, opt in enumerate(options)])
        user_prompt = f"Вопрос: {question_text}\nТип: {'Множественный выбор' if is_multiselect else 'Одиночный выбор'}\nВарианты:\n{options_formatted}"

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.0, timeout=config.LLM_TIMEOUT
            )
            raw = resp.choices[0].message.content.strip()
            raw_clean = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
            match = re.search(r'\{.*\}', raw_clean, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                res = SurveyDecision(**data)

                if res and res.selected_indices:
                    q_lower = question_text.lower()

                    medical_and_sensitive_triggers = [
                        "заболеван", "болезн", "страдаете", "инвалид", "рак", "онколог",
                        "желуд", "кожи", "почек", "сердечн", "диагноз", "симптом", "терапи",
                        "лечени", "опорно-двигател", "хирургич", "операци", "больниц", "клиник",
                        "нервной систем", "жкт", "бросить", "курить", "курени", "попытк", "бросал"
                    ]

                    is_trap = any(w in q_lower for w in ['маркетинг', 'реклам', 'опрос', 'сми', 'журналист'])
                    is_sensitive = any(trigger in q_lower for trigger in medical_and_sensitive_triggers)

                    safe_indices = []
                    for idx in res.selected_indices:
                        if idx < len(options):
                            opt_txt = options[idx].lower()

                            if any(custom in opt_txt for custom in
                                   ["свой вариант", "другое", "другая", "другой", "иное", "впишите", "укажите"]):
                                print(
                                    f"\n🚫 [ФИЛЬТР]: Игнорируем '{options[idx]}'. Бот должен выбирать из предложенного.")
                                continue

                            if not is_trap and not is_sensitive:
                                if any(bad in opt_txt for bad in
                                       ["ничего", "не покупа", "не пользу", "нет", "затрудняюсь", "не знаю", "никаки"]):
                                    print(
                                        f"\n🛡️ [АНТИ-КИК]: LLM хотела выбрать '{options[idx]}', но это приведет к вылету! Блокируем.")
                                    continue

                            safe_indices.append(idx)

                    if not safe_indices and options:
                        print("🛠️ [СИСТЕМА]: Принудительно выбираем активные стандартные варианты...")
                        for i, opt in enumerate(options):
                            opt_lower = opt.lower()
                            if not any(bad in opt_lower for bad in
                                       ["ничего", "не ", "затрудняюсь", "другое", "другая", "другой", "свой вариант",
                                        "иное", "никаки"]):
                                safe_indices.append(i)
                                if len(safe_indices) >= (2 if is_multiselect else 1):
                                    break

                        if not safe_indices:
                            safe_indices = [0]

                    res.selected_indices = safe_indices

                    if is_sensitive:
                        print(
                            f"\n🩺 [МЕДИЦИНСКИЙ/ЧУВСТВИТЕЛЬНЫЙ ФИЛЬТР]: Вопрос распознан как исключение. Анти-кик отключен.")

                selected_texts = [options[i] for i in res.selected_indices if i < len(options)]
                self.memory.save_record(question_text, "multiselect" if is_multiselect else "single", options,
                                        res.selected_indices, selected_texts, res.reasoning)
                return res
        except Exception as e:
            print(f"[!] Ошибка LLM: {e}")

        return SurveyDecision(selected_indices=[0], requires_human=True, reasoning="Сбой модели")