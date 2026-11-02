import re
import json
import requests
from openai import OpenAI
from pydantic import BaseModel, Field
from core import config


class SurveyDecision(BaseModel):
    selected_indices: list[int] = Field(default_factory=lambda: [0])
    is_attention_check: bool = False
    requires_human: bool = False
    reasoning: str = ""


class LLMClient:
    def __init__(self, base_url: str = config.LLM_BASE_URL, api_key: str = config.LLM_API_KEY, model: str = config.LLM_MODEL):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def clean_text_artifacts(self, text: str) -> str:
        if not text:
            return "Все отлично"
        no_think = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        no_cjk = re.sub(
            r'[\u4e00-\u9fff\u3400-\u4dbf\u2e80-\u2fd5\uf900-\ufaff\u3000-\u303f\uff00-\uffef\u2000-\u206f]+', '',
            no_think)
        cleaned = re.sub(r'["\'`]+', '', no_cjk)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        if len(cleaned) < 2 or "нет информации" in cleaned.lower():
            return "Все отлично"
        return cleaned

    def ask_text(self, system_prompt: str, user_prompt: str, timeout: float = config.LLM_TIMEOUT) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                timeout=timeout
            )
            ans = self.clean_text_artifacts(resp.choices[0].message.content.strip())
            return re.sub(r'^(ответ|сумма|размер|значение)[:\s\-]+', '', ans, flags=re.IGNORECASE).strip()
        except Exception as e:
            print(f"[!] Ошибка LLM генерации текста: {e}")
            # Контекстно-зависимый резервный ответ вместо жесткого "1000"
            q_lower = user_prompt.lower()
            if any(w in q_lower for w in ["город", "где жив"]):
                return "Москва"
            elif any(w in q_lower for w in ["возраст", "сколько лет"]):
                return "21"
            elif any(w in q_lower for w in ["сумм", "рубл", "стоимост", "цена", "чек", "тратит", "потрат"]):
                return "2500"
            elif any(w in q_lower for w in ["авто", "машин"]):
                return "Audi"
            elif any(w in q_lower for w in ["телефон", "смартфон"]):
                return "Samsung"
            return "Все отлично, претензий и замечаний нет"

    def _extract_json_decision(self, raw_text: str) -> SurveyDecision | None:
        """Надежный парсер JSON из ответа модели с защитой от синтаксических сбоев."""
        raw_clean = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL)
        raw_clean = re.sub(r'```(?:json)?|```', '', raw_clean).strip()

        # 1. Попытка стандартного поиска блока JSON
        match = re.search(r'\{.*\}', raw_clean, re.DOTALL)
        if match:
            candidate = match.group(0)
            # Исправляем частую ошибку моделей: запятые перед закрывающей скобкой
            candidate_cleaned = re.sub(r',\s*([\}\]])', r'\1', candidate)
            try:
                data = json.loads(candidate_cleaned)
                if isinstance(data, dict):
                    # Приводим индексы к int
                    raw_indices = data.get("selected_indices", [0])
                    if not isinstance(raw_indices, list):
                        raw_indices = [raw_indices]
                    int_indices = []
                    for x in raw_indices:
                        try:
                            int_indices.append(int(x))
                        except (ValueError, TypeError):
                            pass
                    data["selected_indices"] = int_indices if int_indices else [0]
                    return SurveyDecision(**data)
            except Exception:
                pass

        # 2. Фолбэк через регулярные выражения, если JSON поврежден
        indices_match = re.search(r'["\']?selected_indices["\']?\s*:\s*\[(.*?)\]', raw_clean)
        if indices_match:
            raw_nums = re.findall(r'\d+', indices_match.group(1))
            parsed_indices = [int(n) for n in raw_nums] if raw_nums else [0]
            reasoning_match = re.search(r'["\']?reasoning["\']?\s*:\s*["\'](.*?)["\']', raw_clean)
            reason = reasoning_match.group(1) if reasoning_match else "Восстановлено из текста"
            return SurveyDecision(selected_indices=parsed_indices, reasoning=reason)

        return None

    def ask_decision(self, system_prompt: str, user_prompt: str, timeout: float = config.LLM_TIMEOUT) -> SurveyDecision:
        strict_rule = "\n\nВАЖНО: ОТВЕЧАЙ СТРОГО ПО ПРОФИЛЮ И АКТИВНО ИСПОЛЬЗУЙ ЕГО ДАННЫЕ. Если в профиле указана машина — веди рассуждения исключительно как опытный автовладелец, не выдумывай отговорки про ее отсутствие."
        enforced_prompt = system_prompt.strip() + strict_rule

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": enforced_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.0,
                timeout=timeout
            )
            raw = resp.choices[0].message.content.strip()
            decision = self._extract_json_decision(raw)
            if decision:
                return decision
        except Exception as e:
            print(f"[!] Ошибка LLM генерации JSON: {e}")

        return SurveyDecision(selected_indices=[0], requires_human=False, reasoning="Резервный выбор (первый вариант)")

    def _call_gemini(self, system_prompt: str, parts: list[dict], timeout: float = 30) -> str:
        """Унифицированный защищенный вызов Google Gemini API с поддержкой прокси."""
        if not config.VISION_API_KEY or config.VISION_API_KEY.startswith("your_"):
            print("[!] Предупреждение: VISION_API_KEY не задан в .env/config.py.")
            return ""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.VISION_MODEL}:generateContent?key={config.VISION_API_KEY}"
        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": system_prompt}] + parts
            }],
            "generationConfig": {"temperature": 0.0}
        }

        proxies = {
            "http": config.GEMINI_PROXY,
            "https": config.GEMINI_PROXY
        } if getattr(config, 'GEMINI_PROXY', None) else None

        # Сначала пробуем с прокси (если настроен), при ошибке сети — пробуем напрямую
        for attempt_proxies in [proxies, None] if proxies else [None]:
            try:
                resp = requests.post(url, json=payload, proxies=attempt_proxies, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content_parts = candidates[0].get("content", {}).get("parts", [])
                        if content_parts:
                            return content_parts[0].get("text", "").strip()
                else:
                    print(f"[!] Ошибка Vision API (HTTP {resp.status_code}): {resp.text[:200]}")
            except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError) as ce:
                if attempt_proxies:
                    print(f"[!] Ошибка прокси {config.GEMINI_PROXY}: {ce}. Пробуем прямое соединение...")
                    continue
                else:
                    print(f"[!] Ошибка соединения с Vision API: {ce}")
            except Exception as e:
                print(f"[!] Исключение при вызове Vision API: {e}")
                break

        return ""

    def recognize_image_options(self, base64_image: str, timeout: float = 30) -> dict:
        system_prompt = """Ты — ИИ-аналитик. На скриншоте сетка картинок с красными номерами [0], [1]...
Определи, что изображено на каждой (животное, бренд, предмет).
Верни СТРОГО JSON-словарь соответствия: {"0": "Название", "1": "Название"}.
Никакого лишнего текста."""

        raw_text = self._call_gemini(
            system_prompt,
            [{"inlineData": {"mimeType": "image/jpeg", "data": base64_image}}],
            timeout=timeout
        )

        if not raw_text:
            return {}

        raw_clean = re.sub(r'```json|```', '', raw_text).strip()
        try:
            return json.loads(raw_clean)
        except Exception:
            match = re.search(r'\{.*\}', raw_clean, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return {}

    def solve_visual_question(self, base64_image: str, question_text: str, options: list[str], timeout: float = 30) -> list[int]:
        options_str = "\n".join([f"[{i}] {opt}" for i, opt in enumerate(options)])
        system_prompt = f"""Ты — ИИ-помощник, проходящий опрос. Тебе дали скриншот.
Внимательно изучи изображение и ответь на вопрос.
Вопрос: {question_text}
Варианты ответа:
{options_str}

Выбери наиболее подходящий вариант исходя из того, что изображено на кадре.
Верни СТРОГО JSON-массив с индексом выбранного ответа. Пример: [0]. Никакого лишнего текста."""

        raw_text = self._call_gemini(
            system_prompt,
            [{"inlineData": {"mimeType": "image/jpeg", "data": base64_image}}],
            timeout=timeout
        )

        if raw_text:
            raw_clean = re.sub(r'```json|```', '', raw_text).strip()
            nums = re.findall(r'\d+', raw_clean)
            if nums:
                return [int(nums[0])]
        return [0]

    def solve_multimedia_question(self, base64_data: str, mime_type: str, question_text: str, options: list[str], timeout: float = 60) -> list[int]:
        options_str = "\n".join([f"[{i}] {opt}" for i, opt in enumerate(options)])
        system_prompt = f"""Ты — ИИ-помощник. Тебе передан медиафайл.
ВНИМАНИЕ: Это тест на внимательность. 
1. Если вопрос звучит как "Что вы увидели?", анализируй видеоряд.
2. Если вопрос звучит как "Что вы слышали?", слушай аудиодорожку.

Вопрос: {question_text}
Варианты ответа:
{options_str}

Верни СТРОГО JSON-массив с индексом правильного ответа. Пример: [0]. Никакого текста, только JSON."""

        raw_text = self._call_gemini(
            system_prompt,
            [{"inlineData": {"mimeType": mime_type, "data": base64_data}}],
            timeout=timeout
        )

        if raw_text:
            raw_clean = re.sub(r'```json|```', '', raw_text).strip()
            nums = re.findall(r'\d+', raw_clean)
            if nums:
                return [int(nums[0])]
        return [0]

    def summarize_video(self, base64_data: str, mime_type: str, timeout: float = 60) -> str:
        system_prompt = """Ты — ИИ-аналитик. Внимательно посмотри видео и послушай звук, чтобы составить подробную шпаргалку:
1. Главные герои и их действия.
2. Бренды, логотипы, надписи.
3. О чем говорят или какой звук звучит.
4. Основной посыл ролика.
Сделай это одним емким абзацем."""

        return self._call_gemini(
            system_prompt,
            [{"inlineData": {"mimeType": mime_type, "data": base64_data}}],
            timeout=timeout
        )
