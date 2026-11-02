import sqlite3
import json
import re
import difflib
from datetime import datetime
from core import config


STOP_WORDS = {
    "ли", "вы", "вам", "вас", "ваш", "ваша", "ваше", "ваши", "вашем", "вашей",
    "пожалуйста", "укажите", "выберите", "скажите", "отметьте", "следующий",
    "следующие", "какой", "какая", "какие", "каком", "какую", "что", "где",
    "как", "из", "на", "по", "для", "или", "это", "то", "же", "все", "при", "в"
}

SEMANTIC_CATEGORIES = {
    "_WORK_": ["работ", "занят", "труд", "професси", "должност", "отрасл", "сфер"],
    "_INCOME_": ["доход", "заработ", "деньг", "зарплат", "бюджет", "финанс"],
    "_AGE_": ["возраст", "полных лет", "сколько вам лет", "рождения", "родились"],
    "_GEO_": ["город", "прожива", "регион", "населен", "субъект", "област"],
    "_EDU_": ["образован", "учебн", "вуз", "колледж", "университет", "институт", "окончил"],
    "_FAMILY_": ["семей", "супруг", "состав семьи", "брак", "женат", "замужем"],
    "_AUTO_": ["автомоб", "машин", "транспорт", "авто"],
    "_SMOKE_": ["курен", "сигарет", "табак", "вейп"],
    "_CHILD_": ["ребенок", "ребят", "дочь", "сын", "малыш", "возраст ребенка"]
}


def _stem_word(w: str) -> str:
    """Легковесный стемминг окончаний для русского языка."""
    w = w.lower()
    endings = [
        'ов', 'ев', 'ей', 'ями', 'ами', 'ом', 'ем', 'ой', 'ей', 'ую', 'юю',
        'ая', 'яя', 'ое', 'ее', 'ые', 'ие', 'ых', 'их', 'ам', 'ям',
        'а', 'я', 'о', 'е', 'ы', 'и', 'у', 'ю'
    ]
    for end in endings:
        if len(w) > len(end) + 3 and w.endswith(end):
            return w[:-len(end)]
    return w


class SurveyMemory:
    def __init__(self, db_path=config.DB_PATH):
        self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS qa_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clean_question TEXT NOT NULL,
                    full_question TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    options_json TEXT,
                    selected_json TEXT NOT NULL,
                    selected_text TEXT,
                    reasoning TEXT,
                    is_verified INTEGER DEFAULT 0,
                    corrected_json TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clean_q ON qa_records(clean_question)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_verified ON qa_records(is_verified)")
            conn.commit()

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        t = str(text).lower().strip()
        t = re.sub(r'[^а-яa-z0-9\s]', '', t)
        return re.sub(r'\s+', ' ', t).strip()

    def get_semantic_tokens(self, text: str) -> set[str]:
        """Извлечение смысловых токенов со стеммингом и нормализацией категорий."""
        norm = self.normalize_text(text)
        words = norm.split()
        meaningful = {_stem_word(w) for w in words if w not in STOP_WORDS and len(w) > 2}

        # Добавляем категориальные теги
        text_lower = text.lower()
        for cat, roots in SEMANTIC_CATEGORIES.items():
            if any(r in text_lower for r in roots):
                meaningful.add(cat)

        return meaningful

    def calculate_similarity(self, q1: str, q2: str, clean_q1: str = "", clean_q2: str = "") -> float:
        """
        Комплексная оценка смысловой схожести:
        1. Точное/посимвольное сходство SequenceMatcher
        2. Сходство смысловых корней слов и категорий
        """
        c1 = clean_q1 or self.normalize_text(q1)
        c2 = clean_q2 or self.normalize_text(q2)

        if c1 == c2:
            return 1.0

        # Посимвольное сходство
        seq_ratio = difflib.SequenceMatcher(None, c1, c2).ratio()

        # Токенное и категориальное сходство
        t1 = self.get_semantic_tokens(q1)
        t2 = self.get_semantic_tokens(q2)

        if not t1 or not t2:
            return seq_ratio

        intersection = len(t1 & t2)
        union = len(t1 | t2)
        jaccard = intersection / union if union > 0 else 0.0

        # Проверка пересечения ключевых категорий
        cat_keys = set(SEMANTIC_CATEGORIES.keys())
        cat_overlap = len((t1 & cat_keys) & (t2 & cat_keys))

        semantic_score = jaccard
        if cat_overlap > 0:
            common_words = (t1 & t2) - cat_keys
            # Если совпала ключевая тема и есть хотя бы одно общее смысловое слово/корень
            if common_words:
                semantic_score = max(semantic_score, 0.82)

        return max(seq_ratio, semantic_score)

    def _match_options_overlap(self, current_options: list, db_options_json: str) -> bool:
        """Кросс-проверка вариантов ответа для предотвращения ложных срабатываний."""
        if not current_options or not db_options_json:
            return True
        try:
            db_opts = json.loads(db_options_json)
            if isinstance(db_opts, list) and len(db_opts) > 0 and len(current_options) > 0:
                norm_curr = [self.normalize_text(o) for o in current_options if len(self.normalize_text(o)) > 2]
                norm_db = [self.normalize_text(o) for o in db_opts if len(self.normalize_text(o)) > 2]

                if norm_curr and norm_db:
                    for c in norm_curr:
                        for d in norm_db:
                            if c == d or c in d or d in c:
                                return True
                    return False
        except Exception:
            pass
        return True

    def _resolve_answer_from_row(self, row: tuple, current_options: list | None, ratio: float) -> tuple[list[int] | str, str]:
        full_q, clean_q, sel_json, sel_txt, corr_json, reasoning, notes, _ = row
        note_str = notes if notes else (reasoning if reasoning else f"База знаний ({int(ratio * 100)}%)")
        info_note = f"Совпадение {int(ratio * 100)}% с «{full_q[:40]}...» -> {note_str}"

        # 1. Открытые вопросы (нет вариантов на странице)
        if not current_options:
            target_raw = corr_json if corr_json else (sel_txt if sel_txt else sel_json)
            try:
                ans = json.loads(target_raw)
            except Exception:
                ans = target_raw
            return (str(ans) if not isinstance(ans, list) else str(ans[0])), info_note

        # 2. Поиск текстовых названий вариантов для сопоставления
        candidate_texts = []

        if notes and "GUI" in notes:
            match = re.search(r'\[.*\]', notes)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                        candidate_texts = parsed
                except Exception:
                    pass

        if not candidate_texts and corr_json:
            try:
                parsed = json.loads(corr_json)
                if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                    candidate_texts = parsed
            except Exception:
                pass

        if not candidate_texts and sel_txt:
            try:
                parsed = json.loads(sel_txt)
                if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                    candidate_texts = parsed
                elif isinstance(parsed, str):
                    candidate_texts = [parsed]
            except Exception:
                if isinstance(sel_txt, str) and not sel_txt.startswith('['):
                    candidate_texts = [sel_txt]

        # Ремаппинг названий в актуальные индексы текущего списка вариантов
        if candidate_texts and current_options:
            new_indices = []
            for val in candidate_texts:
                norm_val = self.normalize_text(val)
                for cur_idx, cur_opt in enumerate(current_options):
                    norm_cur = self.normalize_text(cur_opt)
                    if norm_cur == norm_val or (len(norm_val) > 3 and norm_val in norm_cur) or (len(norm_cur) > 3 and norm_cur in norm_val):
                        if cur_idx not in new_indices:
                            new_indices.append(cur_idx)
                        break
            if new_indices:
                return new_indices, info_note

        # Фоллбэк: числовые индексы (только если не удалось сопоставить текст)
        try:
            idx_data = json.loads(corr_json if corr_json else sel_json)
            if isinstance(idx_data, list):
                valid = [i for i in idx_data if isinstance(i, int) and i < len(current_options)]
                if valid:
                    return valid, info_note
            elif isinstance(idx_data, int) and idx_data < len(current_options):
                return [idx_data], info_note
        except Exception:
            pass

        return [0], info_note

    def find_verified_answer(self, question_text: str, current_options: list = None) -> tuple[list[int] | str, str] | None:
        norm_q = self.normalize_text(question_text)
        if not norm_q:
            return None

        # 1. БЫСТРЫЙ O(1) ПОИСК ТОЧНОГО СОВПАДЕНИЯ ПО ИНДЕКСУ
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT full_question, clean_question, selected_json, selected_text,
                       corrected_json, reasoning, notes, options_json
                FROM qa_records
                WHERE (is_verified = 1 OR corrected_json IS NOT NULL OR notes LIKE '%GUI%')
                  AND clean_question = ?
                ORDER BY id DESC LIMIT 1
            """, (norm_q,))
            exact_match = cursor.fetchone()

            if exact_match:
                if not current_options or self._match_options_overlap(current_options, exact_match[7]):
                    return self._resolve_answer_from_row(exact_match, current_options, ratio=1.0)

            # 2. СЕМАНТИЧЕСКИЙ И НЕЧЕТКИЙ ПОИСК
            cursor.execute("""
                SELECT full_question, clean_question, selected_json, selected_text,
                       corrected_json, reasoning, notes, options_json
                FROM qa_records
                WHERE is_verified = 1
                   OR corrected_json IS NOT NULL
                   OR notes LIKE '%GUI%'
                ORDER BY id DESC
            """)
            rows = cursor.fetchall()

        best_match = None
        best_ratio = 0.0

        for row in rows:
            full_q, clean_q, _, _, _, _, _, db_options_json = row
            norm_db_q = clean_q if clean_q else self.normalize_text(full_q)

            # Кросс-чек вариантов
            if current_options and not self._match_options_overlap(current_options, db_options_json):
                continue

            similarity = self.calculate_similarity(question_text, full_q, norm_q, norm_db_q)
            if similarity > best_ratio:
                best_ratio = similarity
                best_match = row
                if best_ratio > 0.95:
                    break

        if best_ratio >= 0.78 and best_match:
            return self._resolve_answer_from_row(best_match, current_options, best_ratio)

        return None

    def save_record(
            self,
            full_question: str,
            question_type: str,
            options: list[str] | None,
            selected: list[int] | str,
            selected_text: str | list[str],
            reasoning: str = ""
    ) -> int:
        clean_q = self.normalize_text(full_question)
        options_json = json.dumps(options, ensure_ascii=False) if options else None
        selected_json = json.dumps(selected, ensure_ascii=False)
        selected_txt_str = json.dumps(selected_text, ensure_ascii=False) if isinstance(selected_text, list) else str(selected_text)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO qa_records (clean_question, full_question, question_type, options_json,
                                        selected_json, selected_text, reasoning, is_verified, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                clean_q, full_question, question_type, options_json,
                selected_json, selected_txt_str, reasoning, datetime.now().isoformat()
            ))
            conn.commit()
            return cursor.lastrowid
