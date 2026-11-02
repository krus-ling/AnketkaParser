import json
from pathlib import Path
from core.memory import SurveyMemory
from core import config
from core import prompts
from core.rules_engine import RulesEngine
from core.llm_client import LLMClient, SurveyDecision


class SurveyBrain:
    def __init__(
            self,
            base_url: str = config.LLM_BASE_URL,
            api_key: str = config.LLM_API_KEY,
            model: str = config.LLM_MODEL,
            profile_path: str | Path = config.PROFILE_PATH
    ):
        self.memory = SurveyMemory()
        with open(profile_path, "r", encoding="utf-8") as f:
            self.profile = json.load(f)

        self.llm = LLMClient(base_url, api_key, model)
        self.rules = RulesEngine(self.profile)
        self.ad_context = ""
        self.stats = {
            "total_answered": 0, "from_memory": 0, "from_rules": 0, "from_llm": 0
        }
        self.last_action = None
        self.action_history = []

    def _record_action(self, action_dict: dict):
        self.last_action = action_dict
        if not hasattr(self, "action_history"):
            self.action_history = []
        self.action_history.append(action_dict)
        if len(self.action_history) > 10:
            self.action_history.pop(0)

    def answer_open_text(self, question_text: str) -> str:
        self.stats["total_answered"] += 1
        ans = ""
        note = ""

        q_lower = question_text.lower()
        is_ad_question = bool(self.ad_context) and any(w in q_lower for w in [
            "кешбэк", "кэшбэк", "банк", "карте", "акци", "предложен",
            "сумму", "размер", "процент", "услов"
        ])

        # 1. Сначала жесткие правила открытых ответов (город, возраст, авто, профессия)
        rule_ans = self.rules.apply_open_text_rules(q_lower, is_ad_question)
        if rule_ans is not None:
            ans = rule_ans
            note = "Ответ по профилю/правилам"
            self.stats["from_rules"] += 1
        else:
            # 2. Если в правилах нет — смотрим базу памяти
            cached = self.memory.find_verified_answer(question_text)
            if cached:
                ans, note = cached
                self.stats["from_memory"] += 1
                print(f"[DB MEMORY] {note}")
            else:
                # 3. Если и в памяти нет — вызываем LLM
                self.stats["from_llm"] += 1
                sys_prompt = prompts.get_open_text_prompt(self.profile, self.ad_context)
                user_prompt = f"Вопрос: {question_text}\nКраткий ответ:"
                ans = self.llm.ask_text(sys_prompt, user_prompt, config.LLM_TIMEOUT)
                note = "Ответ по контексту/LLM"

        # Сохраняем в базу истории
        self.memory.save_record(question_text, "open_text", None, ans, ans, note)

        self._record_action({
            "type": "open_text", "question": question_text, "answer": str(ans), "reasoning": note
        })
        return str(ans)

    def generate_chat_response(self, question_text: str) -> str:
        self.stats["total_answered"] += 1
        ans = ""
        note = ""

        q_lower = question_text.lower().strip()
        rule_ans = self.rules.apply_chat_rules(q_lower)

        if rule_ans is not None:
            self.stats["from_rules"] += 1
            ans = rule_ans
            note = "Чат-ответ (правило)"
        else:
            cached = self.memory.find_verified_answer(question_text)
            if cached:
                ans, note = cached
                self.stats["from_memory"] += 1
                print(f"[DB MEMORY] {note}")
            else:
                self.stats["from_llm"] += 1
                sys_prompt = prompts.get_chat_prompt(self.profile)
                ans = self.llm.ask_text(sys_prompt, question_text, config.LLM_TIMEOUT)
                note = "Чат-ответ (LLM)"

        self.memory.save_record(question_text, "chat", None, ans, ans, note)

        self._record_action({
            "type": "chat", "question": question_text, "answer": str(ans), "reasoning": note
        })
        return str(ans)

    def decide(self, question_text: str, options: list[str], is_multiselect: bool = False) -> SurveyDecision:
        self.stats["total_answered"] += 1
        res = None

        # 1. МАТЕМАТИЧЕСКИЕ КАПЧИ (1+2=3, 5*2=10)
        math_choice = self.rules.solve_math(question_text, options)
        if math_choice is not None:
            self.stats["from_rules"] += 1
            res = SurveyDecision(selected_indices=math_choice, is_attention_check=True,
                                 reasoning="Арифметический расчет")

        # 2. ПРАВИЛА ПРОФИЛЯ И ЛОВУШКИ (ДОХОДЫ, ДЕТИ, ПОЛ, АВТО, ГОРОД, БРАК)
        if res is None:
            trap_choice = self.rules.check_traps(question_text, options)
            if trap_choice is not None:
                self.stats["from_rules"] += 1
                res = SurveyDecision(selected_indices=trap_choice, is_attention_check=True,
                                     reasoning="Правило профиля / ловушка")

        # 3. БАЗА ПАМЯТИ
        if res is None:
            cached = self.memory.find_verified_answer(question_text, options)
            if cached:
                ans_indices, note = cached
                self.stats["from_memory"] += 1
                print(f"[DB MEMORY] {note}")
                res = SurveyDecision(selected_indices=ans_indices if isinstance(ans_indices, list) else [0], reasoning=note)

        # 4. НЕЙРОСЕТЬ (LLM)
        if res is None:
            self.stats["from_llm"] += 1
            sys_prompt = prompts.get_decision_prompt(self.profile, self.ad_context)
            opts_fmt = "\n".join([f"[{i}] {opt}" for i, opt in enumerate(options)])
            user_prompt = f"Вопрос: {question_text}\nТип: {'Множественный выбор' if is_multiselect else 'Одиночный выбор'}\nВарианты:\n{opts_fmt}"

            res = self.llm.ask_decision(sys_prompt, user_prompt, config.LLM_TIMEOUT)

            if res.selected_indices:
                res.selected_indices = self.rules.filter_llm_decision(question_text, options,
                                                                      res.selected_indices,
                                                                      is_multiselect)

        # Валидация индексов на выход за границы списка вариантов
        valid_indices = [i for i in res.selected_indices if 0 <= i < len(options)] if options else [0]
        if not valid_indices and options:
            valid_indices = [0]
        res.selected_indices = valid_indices

        selected_texts = [options[i] for i in res.selected_indices if i < len(options)]
        self.memory.save_record(
            question_text, "multiselect" if is_multiselect else "single",
            options, res.selected_indices, selected_texts, res.reasoning
        )

        self._record_action({
            "type": "choices",
            "question": question_text,
            "options": options,
            "selected": selected_texts,
            "selected_texts": selected_texts,
            "reasoning": res.reasoning
        })
        return res
