import sqlite3
import json
import re
import difflib
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "survey_memory.db"


class SurveyMemory:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS qa_records
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               clean_question
                               TEXT
                               NOT
                               NULL,
                               full_question
                               TEXT
                               NOT
                               NULL,
                               question_type
                               TEXT
                               NOT
                               NULL,
                               options_json
                               TEXT,
                               selected_json
                               TEXT
                               NOT
                               NULL,
                               selected_text
                               TEXT,
                               reasoning
                               TEXT,
                               is_verified
                               INTEGER
                               DEFAULT
                               0,
                               corrected_json
                               TEXT,
                               notes
                               TEXT,
                               created_at
                               TEXT
                               NOT
                               NULL
                           )
                           """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clean_q ON qa_records(clean_question)")
            conn.commit()

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        t = str(text).lower().strip()
        t = re.sub(r'[^а-яa-z0-9\s]', '', t)
        return re.sub(r'\s+', ' ', t).strip()

    def find_verified_answer(self, question_text: str, current_options: list = None) -> tuple[list[
                                                                                                  int] | str, str] | None:
        norm_q = self.normalize_text(question_text)
        if not norm_q:
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Добавили выгрузку options_json для кросс-чека
            cursor.execute("""
                           SELECT full_question,
                                  clean_question,
                                  selected_json,
                                  selected_text,
                                  corrected_json,
                                  reasoning,
                                  notes,
                                  options_json
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
            full_q, clean_q, sel_json, sel_txt, corr_json, reasoning, notes, db_options_json = row
            norm_db_q = clean_q if clean_q else self.normalize_text(full_q)

            ratio = difflib.SequenceMatcher(None, norm_q, norm_db_q).ratio()

            # 🛡️ КРОСС-ЧЕК ВАРИАНТОВ ОТВЕТА: Защита от ложных срабатываний
            if current_options and db_options_json:
                try:
                    db_opts = json.loads(db_options_json)
                    if isinstance(db_opts, list) and len(db_opts) > 0 and len(current_options) > 0:
                        # Нормализуем варианты для сравнения
                        norm_curr = [self.normalize_text(o) for o in current_options if len(self.normalize_text(o)) > 2]
                        norm_db = [self.normalize_text(o) for o in db_opts if len(self.normalize_text(o)) > 2]

                        if norm_curr and norm_db:
                            has_overlap = False
                            for c in norm_curr:
                                for d in norm_db:
                                    if c == d or c in d or d in c:
                                        has_overlap = True
                                        break
                                if has_overlap:
                                    break

                            # Если варианты вообще не пересекаются — это другой вопрос (например, Курение vs Работа)
                            if not has_overlap:
                                continue
                except Exception:
                    pass

            if ratio > best_ratio:
                best_ratio = ratio
                best_match = row

        # 🛡️ ПОРОГ ПОВЫШЕН ДО 90%
        if best_ratio >= 0.9 and best_match:
            full_q, clean_q, sel_json, sel_txt, corr_json, reasoning, notes, _ = best_match
            note_str = notes if notes else (reasoning if reasoning else f"База знаний ({int(best_ratio * 100)}%)")
            info_note = f"Совпадение {int(best_ratio * 100)}% с «{full_q[:40]}...» -> {note_str}"

            # 1. Открытые вопросы
            if not current_options:
                target_raw = corr_json if corr_json else (sel_txt if sel_txt else sel_json)
                try:
                    ans = json.loads(target_raw)
                except Exception:
                    ans = target_raw
                return (str(ans) if not isinstance(ans, list) else str(ans[0])), info_note

            # 2. Поиск текстовых названий вариантов для сопоставления
            candidate_texts = []

            # Из notes («Исправлено пользователем в GUI на ["Кинопоиск", ...]»)
            if notes and "GUI" in notes:
                match = re.search(r'\[.*\]', notes)
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                            candidate_texts = parsed
                    except Exception:
                        pass

            # Из corrected_json
            if not candidate_texts and corr_json:
                try:
                    parsed = json.loads(corr_json)
                    if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                        candidate_texts = parsed
                except Exception:
                    pass

            # Из selected_text
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
                        if norm_cur == norm_val or norm_val in norm_cur or norm_cur in norm_val:
                            if cur_idx not in new_indices:
                                new_indices.append(cur_idx)
                            break
                if new_indices:
                    return new_indices, info_note

            # Фоллбэк: числовые индексы (только если не удалось сопоставить текст)
            try:
                idx_data = json.loads(corr_json if corr_json else sel_json)
                if isinstance(idx_data, list):
                    return idx_data, info_note
                elif isinstance(idx_data, int):
                    return [idx_data], info_note
            except Exception:
                pass

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
        selected_txt_str = json.dumps(selected_text, ensure_ascii=False) if isinstance(selected_text, list) else str(
            selected_text)

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