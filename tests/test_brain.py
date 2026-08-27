import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
from brain import SurveyBrain

brain = SurveyBrain()

test_cases = [
    {
        "name": "1. Скрининг профессий (Жесткое правило)",
        "question": "Работаете ли вы или кто-то из ваших близких родственников в следующих сферах?",
        "options": [
            "Маркетинг и реклама",
            "Связи с общественностью (PR)",
            "Социологические исследования",
            "Ни в одной из перечисленных"
        ],
        "multiselect": False,
        "expected_items": ["Ни в одной из перечисленных"],
        "forbidden_items": ["Маркетинг и реклама", "Связи с общественностью (PR)", "Социологические исследования"]
    },
    {
        "name": "2. Математика словами (Счет + текст)",
        "question": "Сколько будет шесть плюс семь? Выберите правильный ответ, написанный словом.",
        "options": ["13", "Одиннадцать", "Тринадцать", "Двенадцать", "Пять"],
        "multiselect": False,
        "expected_items": ["Тринадцать"],
        "forbidden_items": ["13", "Одиннадцать", "Двенадцать", "Пять"]
    },
    {
        "name": "3. Исключение по отрицанию (НЕ предмет)",
        "question": "Для проверки качества заполнения анкеты выберите вариант, который НЕ является животным:",
        "options": ["Собака", "Кот", "Холодильник", "Хомяк", "Попугай"],
        "multiselect": False,
        "expected_items": ["Холодильник"],
        "forbidden_items": ["Собака", "Кот", "Хомяк", "Попугай"]
    },
    {
        "name": "4. Абсурдное утверждение (Шкала Ликерта)",
        "question": "Оцените степень вашего согласия с утверждением: «Я лично летал на Луну на прошлых выходных».",
        "options": [
            "Полностью согласен",
            "Скорее согласен",
            "Затрудняюсь ответить",
            "Скорее не согласен",
            "Полностью не согласен"
        ],
        "multiselect": False,
        "expected_items": ["Полностью не согласен"],
        "forbidden_items": ["Полностью согласен", "Скорее согласен", "Затрудняюсь ответить"]
    },
    {
        "name": "5. Отсев вымышленных товаров (Fake Brands / Red Herring)",
        "question": "Какие из следующих устройств вы приобретали за последний год для личного пользования?",
        "options": [
            "Смартфон",
            "Персональный квантовый телепортатор",
            "Ноутбук",
            "Беспроводные наушники"
        ],
        "multiselect": True,
        "expected_items": ["Смартфон", "Ноутбук"],
        "forbidden_items": ["Персональный квантовый телепортатор"]
    },
    {
        "name": "6. Прямая инструкция по цвету / числу",
        "question": "Внимательно ознакомьтесь с вопросом и выберите в качестве ответа цвет «Синий».",
        "options": ["Красный", "Желтый", "Синий", "Зеленый"],
        "multiselect": False,
        "expected_items": ["Синий"],
        "forbidden_items": ["Красный", "Желтый", "Зеленый"]
    },
    {
        "name": "7. Проверка демографии (Возраст / Профиль)",
        "question": "Укажите ваш примерный возраст:",
        "options": ["До 18 лет", "18-24 года", "25-34 года", "35-44 года", "45+"],
        "multiselect": False,
        "expected_items": ["18-24 года"],
        "forbidden_items": ["До 18 лет", "25-34 года", "35-44 года", "45+"]
    },
    {
        "name": "8. Онлайн-кинотеатры (Извлечение брендов вместо ID)",
        "question": "Какими из перечисленных онлайн-кинотеатров Вы лично пользуетесь?",
        "options": [
            "Кинопоиск",
            "Иви (ivi)",
            "Okko",
            "Wink",
            "Вымышленный Квантовый Кинотеатр"
        ],
        "multiselect": True,
        "expected_items": ["Кинопоиск", "Иви (ivi)", "Okko"],
        "forbidden_items": ["Вымышленный Квантовый Кинотеатр"]
    }
]

def run_brain_tests():
    print("=" * 70)
    print(f"🧠 ЗАПУСК ТЕСТИРОВАНИЯ МОЗГА И ЛОВУШЕК [{config.LLM_MODEL}]")
    print("=" * 70 + "\n")

    passed_count = 0
    total_count = len(test_cases)

    for idx, test in enumerate(test_cases, start=1):
        question = test["question"]
        options = test["options"]
        is_multi = test["multiselect"]
        expected = test["expected_items"]
        forbidden = test.get("forbidden_items", [])

        decision = brain.decide(question, options, is_multiselect=is_multi)
        selected_texts = [options[i] for i in decision.selected_indices if i < len(options)]

        has_all_expected = any(item in selected_texts for item in expected) if not is_multi else all(item in selected_texts for item in expected)
        has_no_forbidden = not any(item in selected_texts for item in forbidden)
        is_success = has_all_expected and has_no_forbidden

        status_tag = "✅ [PASS]" if is_success else "❌ [FAIL]"
        if is_success:
            passed_count += 1

        print(f"{status_tag} Тест {idx}: {test['name']}")
        print(f"   ❓ Вопрос: {question}")
        print(f"   🤖 Выбор:    {decision.selected_indices} -> {selected_texts}")
        print(f"   🎯 Ожидалось: {expected}")
        if forbidden:
            print(f"   🚫 Запрещено: {forbidden}")
        print(f"   💡 Логика:   {decision.reasoning}")
        print("-" * 70)

    print("\n" + "=" * 70)
    print(f"📊 РЕЗУЛЬТАТ ТЕСТОВ: {passed_count}/{total_count} успешно пройдено")
    print("=" * 70)

    if passed_count != total_count:
        sys.exit(1)

if __name__ == "__main__":
    run_brain_tests()