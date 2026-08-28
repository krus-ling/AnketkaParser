import tkinter as tk
from tkinter import scrolledtext
import threading
import asyncio
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.brain import SurveyBrain
from engines.router import SurveyRouter
from core.bot_state import state

# ==========================================
# 1. HTML-ШАБЛОНЫ СО СЛОЖНЫМИ КЕЙСАМИ ОПРОСНИКОВ
# ==========================================

CSS_AND_JS_CLOUD = """
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; padding: 40px 20px; display: flex; justify-content: center; }
    .survey-container { background: #ffffff; max-width: 950px; width: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); padding: 35px 40px; }
    .question-text, .ss-question-title, .header1 { font-size: 19px; font-weight: 600; color: #222; margin-bottom: 5px; }
    .header2 { font-size: 19px; font-weight: 600; color: #222; margin-bottom: 15px; }
    .sub-text { font-size: 14px; color: #666; margin-bottom: 20px; }
    .answer-item, .scale-item { background: #f8f9fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 12px 18px; margin-bottom: 10px; cursor: pointer; }
    .answer-item.selected, .scale-item.selected { background: #0d6efd; color: #fff; }
    .styled_BlockStyled { background: #fff; border: 1px solid #e0e6ed; border-radius: 8px; padding: 20px; margin-bottom: 15px; }
    .scale-main-answers-container { display: flex; gap: 10px; }
    .custom-input { width: 100%; padding: 12px; border: 1px solid #d0d7de; border-radius: 6px; font-size: 15px; margin-top: 5px; }
    .btn { color: #fff; border: none; border-radius: 6px; padding: 12px 30px; font-size: 16px; cursor: pointer; margin-top: 20px; background: #0d6efd; }
    .step { display: none; } .step.active { display: block; }

    /* Скрытие элементов как в реальных опросниках */
    .select2-hidden-accessible { border: 0 !important; clip: rect(0 0 0 0) !important; height: 1px !important; margin: -1px !important; overflow: hidden !important; padding: 0 !important; position: absolute !important; width: 1px !important; }
    ._uk, ._kz, ._tj { display: none; }

    /* Таблицы SurveyStudio */
    .ss-table-header { display: flex; font-weight: bold; font-size: 12px; margin-bottom: 10px; border-bottom: 2px solid #eee; padding-bottom: 10px;}
    .ss-table-header-empty { width: 45%; padding-right: 15px; box-sizing: border-box; }
    .ss-table-header-titles { width: 55%; display: flex; box-sizing: border-box; }
    .ss-table-header-titles .ss-table-cell { flex: 1; text-align: center; padding: 0 5px; }
    .ss-matrix-body { display: flex; }
    .ss-first-table-container { width: 45%; border-right: 1px solid #eee; padding-right: 15px; box-sizing: border-box; }
    #ssDesktopTableBodyContainer { width: 55%; box-sizing: border-box; }
    .ss-table-row { height: 60px; display: flex; align-items: center; border-bottom: 1px solid #f4f6f8; padding: 5px 0; overflow: hidden; box-sizing: border-box; line-height: 1.4; }
    #ssDesktopTableBodyContainer .ss-table-row { justify-content: space-around; }

    /* Обычные списки Sawtooth */
    .grid__cell { display: flex; align-items: center; background: #f8f9fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 10px; margin-bottom: 8px; }
    .grid__cell label { display: flex; align-items: center; width: 100%; cursor: pointer; }
    .grid__cell input[type="text"], .grid__cell input[type="number"] { margin-left: 15px; flex-grow: 1; padding: 5px; border: 1px solid #ccc; border-radius: 4px; }
    .grid__cell span.answer-text { margin-left: 10px; }
    img.bank-logo { height: 30px; margin-left: 10px; border: 1px solid #eee; }
</style>
<script>
    function sel(el) { el.parentElement.querySelectorAll('.answer-item, .scale-item').forEach(i => i.classList.remove('selected')); el.classList.add('selected'); }
    function multi(el) { el.classList.toggle('selected'); }
    function next(id) { document.querySelectorAll('.step').forEach(s => s.classList.remove('active')); document.getElementById(id).classList.add('active'); }
</script>
"""

HTML_BASIC = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Mock Basic</title>{CSS_AND_JS_CLOUD}</head><body>
<div class="survey-container">
    <div id="step-1" class="step active">
        <div class="question-text">50% КЕШБЭК ПО КАРТЕ Т-БАНКА</div>
        <div class="sub-text">Получи 50% кешбэк за покупки до конца сентября (не более 1 000 ₽)</div>
        <div class="btn" id="next_button" onclick="next('step-2')">Далее >></div>
    </div>
    <div id="step-2" class="step">
        <div class="question-text">Какой размер кешбэка был обещан в предложении?</div>
        <div class="question_body">
            <div class="grid__cell"><label><input type="radio" name="q1"> <span class="answer-text">10%</span></label></div>
            <div class="grid__cell"><label><input type="radio" name="q1"> <span class="answer-text">50%</span></label></div>
        </div>
        <div class="btn" id="next_button" onclick="next('step-3')">Далее >></div>
    </div>
    <div id="step-3" class="step"><h2>Опрос завершен!</h2></div>
</div></body></html>"""

HTML_SAWTOOTH_TRICKY = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Mock Sawtooth</title>{CSS_AND_JS_CLOUD}</head><body>
<div class="survey-container">
    <!-- Ловушка 1: Многоязычность и Свой вариант -->
    <div id="step-1" class="step active">
        <div class="header1"><span class="_ru">Каков Ваш уровень образования </span><span class="_uk">Який Ваш рівень...</span></div>
        <div class="header2"><span class="_ru">на данный момент?</span><span class="_uk">...</span></div>
        <div class="question_body">
            <div class="grid__cell"><label for="D1_1"><span class="_ru">Высшее образование (специалист, бакалавр, магистр)</span></label><input type="radio" id="D1_1" name="D1"></div>
            <div class="grid__cell"><label for="D1_2"><span class="_ru">Ученая степень</span></label><input type="radio" id="D1_2" name="D1"></div>
            <div class="grid__cell"><label for="D1_other_cb">Другое (впишите)</label><input type="radio" id="D1_other_cb" name="D1"><input type="text" id="D1_other" name="D1_other" placeholder="Укажите ваш вариант"></div>
        </div>
        <div class="btn" id="next_button" onclick="next('step-2')">Далее >></div>
    </div>
    <!-- Ловушка 2: Картинки (логотипы) вместо текста -->
    <div id="step-2" class="step">
        <div class="header1">Услугами каких банков Вы пользуетесь в настоящее время?</div>
        <div class="question_body">
            <div class="grid__cell"><label for="B_1"><img src="https://via.placeholder.com/100x30?text=T-Bank" class="bank-logo" title="Т-Банк"></label><input type="checkbox" id="B_1" name="B"></div>
            <div class="grid__cell"><label for="B_2"><img src="https://via.placeholder.com/100x30?text=Sber" class="bank-logo" data-template="Сбер (Сбербанк)"></label><input type="checkbox" id="B_2" name="B"></div>
            <div class="grid__cell"><label for="B_3"><span class="answer-text">Никакими</span></label><input type="checkbox" id="B_3" name="B"></div>
        </div>
        <div class="btn" id="next_button" onclick="next('step-3')">Далее >></div>
    </div>
    <!-- Ловушка 3: Скрытый выпадающий список (Select2) на год авто -->
    <div id="step-3" class="step">
        <div class="header1">Какого года выпуска этот автомобиль?</div>
        <div class="combobox-container">
            <select class="select2-hidden-accessible" tabindex="-1" aria-hidden="true">
                <option value="0">Выберите из списка</option>
                <option value="2021">2021</option>
                <option value="2022">2022</option>
                <option value="2023">2023</option>
                <option value="2024">2024</option>
            </select>
            <input type="text" placeholder="Нажмите для поиска..." class="custom-input">
        </div>
        <div class="btn" id="next_button" onclick="next('step-4')">Далее >></div>
    </div>
    <div id="step-4" class="step"><h2>Успешно пройдено!</h2></div>
</div></body></html>"""

HTML_SURVEYSTUDIO_TRICKY = f"""{CSS_AND_JS_CLOUD}
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>SurveyStudio Test</title>
<style>
    body {{ font-family: Arial, sans-serif; padding: 20px; background: #f4f4f4; display: block; }}
    .question-content {{ background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .ss-question-title {{ font-size: 18px; font-weight: bold; margin-bottom: 15px; }}
    label {{ display: block; margin: 10px 0; cursor: pointer; }}
    input[type="number"], select {{ padding: 8px; width: 100%; max-width: 300px; margin-top: 5px; }}
    .btn {{ padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 15px; }}
    .btn:hover {{ background: #0056b3; }}
</style>
</head>
<body>

<div class="question-content" id="q1">
    <div class="ss-question-title">Выберите ваш пол</div>
    <label><input type="radio" name="gender" value="f"> Женский</label>
    <label><input type="radio" name="gender" value="m"> Мужской</label>
    <button class="btn ss-next-btn">Далее</button>
</div>

<div class="question-content" style="display:none;" id="q2">
    <div class="ss-question-title">Какова была примерная сумма того заказа? Укажите сумму в рублях.</div>
    <input type="number" id="money_input" placeholder="Сумма">
    <button class="btn ss-next-btn">Далее</button>
</div>

<div class="question-content" style="display:none;" id="q3">
    <div class="ss-question-title">В каком городе Вы постоянно проживаете (не менее 7 месяцев в году)?</div>
    <select id="city_select">
        <option value="0">Выберите город</option>
        <option value="msk">Москва</option>
        <option value="kzn">Казань</option>
        <option value="spb">Санкт-Петербург</option>
    </select>
    <button class="btn ss-next-btn">Далее</button>
</div>

<div class="question-content" style="display:none;" id="q4">
    <div class="ss-question-title">Насколько вы согласны или не согласны с каждым утверждением?</div>
    <table style="width:100%; text-align:left;">
        <tr>
            <th>Утверждение</th>
            <th>Согласен</th>
            <th>Не согласен</th>
        </tr>
        <tr>
            <td>Замороженные полуфабрикаты позволяют мне сделать мой рацион разнообразным</td>
            <td><input type="radio" name="m1" value="agree"></td>
            <td><input type="radio" name="m1" value="disagree"></td>
        </tr>
        <tr>
            <td>Тяжесть или дискомфорт говорит о невысоком качестве</td>
            <td><input type="radio" name="m2" value="agree"></td>
            <td><input type="radio" name="m2" value="disagree"></td>
        </tr>
    </table>
    <button class="btn ss-next-btn" id="processingGoForwardBtn">Далее</button>
</div>

<div class="question-content" style="display:none;" id="q5">
    <div class="ss-question-title">Опрос успешно завершен!</div>
    <p>Спасибо за участие. Вознаграждение зачислено.</p>
</div>

<script>
    let currentQ = 1;
    document.querySelectorAll('.ss-next-btn').forEach(btn => {{
        btn.addEventListener('click', function() {{

            if (currentQ === 1) {{
                let gender = document.querySelector('input[name="gender"]:checked');
                if (!gender) {{ alert('Выберите пол!'); return; }}
            }} else if (currentQ === 2) {{
                let money = document.getElementById('money_input').value;
                if (!money) {{ alert('Укажите сумму!'); return; }}
            }} else if (currentQ === 3) {{
                let city = document.getElementById('city_select').value;
                if (city === '0') {{ alert('Выберите город!'); return; }}
            }}

            document.getElementById('q' + currentQ).style.display = 'none';
            currentQ++;
            let nextQ = document.getElementById('q' + currentQ);
            if (nextQ) {{
                nextQ.style.display = 'block';
            }}
        }});
    }});
</script>
</body>
</html>
"""

HTML_CLOUDSURVEY_TRICKY = f"""{CSS_AND_JS_CLOUD}
<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: Arial, sans-serif; padding: 20px; display: block; }}
  .question-block {{ margin: 20px 0; padding: 20px; border: 1px solid #ddd; border-radius: 8px; background: white; }}
  .dropdown {{ position: relative; width: 300px; }}
  .dropdown-list {{ display: none; position: absolute; background: white; border: 1px solid #ccc; width: 100%; z-index: 100; max-height: 150px; overflow-y: auto; }}
  .dropdown-list.active {{ display: block; }}
  .dropdown-item {{ padding: 10px; cursor: pointer; border-bottom: 1px solid #eee; }}
  .dropdown-item:hover {{ background: #f0f8ff; }}
  .next-btn {{ padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }}
  .next-btn:hover {{ background: #0056b3; }}
</style>
</head>
<body class="step active">
  <div id="step1" class="question-block">
    <h3>Ваш город проживания</h3>
    <div class="dropdown select-wrap">
      <input type="text" id="city-input" placeholder="Начните вводить город" autocomplete="off" style="width: 100%; padding: 8px;">
      <div class="dropdown-list" id="city-dropdown">
        <div class="dropdown-item option" onclick="selectCity('Москва')">Москва</div>
        <div class="dropdown-item option" onclick="selectCity('Санкт-Петербург')">Санкт-Петербург</div>
        <div class="dropdown-item option" onclick="selectCity('Казань')">Казань</div>
        <div class="dropdown-item option" onclick="selectCity('Новосибирск')">Новосибирск</div>
      </div>
    </div>
    <input type="hidden" id="selected-city" value="">
  </div>

  <div id="step2" class="question-block" style="display:none;">
    <h2>Выберите подходящий вариант</h2>
    <p style="font-size: 1.1em; font-weight: bold;">Каким оператором сотовой связи вы пользуетесь?</p>
    <label style="display:block; margin: 10px 0;"><input type="radio" name="operator" value="mts"> МТС</label>
    <label style="display:block; margin: 10px 0;"><input type="radio" name="operator" value="beeline"> билайн</label>
    <label style="display:block; margin: 10px 0;"><input type="radio" name="operator" value="megafon"> МегаФон</label>
    <label style="display:block; margin: 10px 0;"><input type="radio" name="operator" value="tele2"> Т2 (Теле2)</label>
  </div>

  <button id="nextSurvey" class="next-btn btn">Далее</button>

  <div id="result" style="display:none; margin-top: 20px; padding: 20px; background: #d4edda; color: #155724; border-radius: 8px;">
    <h2>Опрос успешно завершен!</h2>
    <p>Вы изменили мир к лучшему. Вознаграждение зачислено.</p>
  </div>

<script>
  const cityInput = document.getElementById('city-input');
  const cityDropdown = document.getElementById('city-dropdown');
  const selectedCity = document.getElementById('selected-city');
  const step1 = document.getElementById('step1');
  const step2 = document.getElementById('step2');

  cityInput.addEventListener('input', function() {{
    if (this.value.length > 1) {{
      cityDropdown.classList.add('active');
    }} else {{
      cityDropdown.classList.remove('active');
    }}
  }});

  cityInput.addEventListener('focus', function() {{
    if (this.value.length > 1) {{
      cityDropdown.classList.add('active');
    }}
  }});

  document.addEventListener('click', function(e) {{
    if (!e.target.closest('.dropdown')) {{
      cityDropdown.classList.remove('active');
    }}
  }});

  function selectCity(city) {{
    cityInput.value = city;
    selectedCity.value = city;
    cityDropdown.classList.remove('active');
  }}

  let currentStep = 1;
  document.getElementById('nextSurvey').addEventListener('click', function() {{
    if (currentStep === 1) {{
      if (selectedCity.value === 'Москва' || cityInput.value.toLowerCase().includes('москва')) {{
        step1.style.display = 'none';
        step2.style.display = 'block';
        currentStep = 2;
      }} else {{
        alert('Пожалуйста, выберите город из выпадающего списка!');
      }}
    }} else if (currentStep === 2) {{
      let op = document.querySelector('input[name="operator"]:checked');
      if (op) {{
        step2.style.display = 'none';
        document.getElementById('nextSurvey').style.display = 'none';
        document.getElementById('result').style.display = 'block';
      }} else {{
        alert('Пожалуйста, выберите вариант ответа!');
      }}
    }}
  }});
</script>
</body>
</html>
"""

HTML_EXPERTNOEMNENIE_START = f"""{CSS_AND_JS_CLOUD}
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Expertnoe Mnenie - Старт</title>
<style>
body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 40px 20px; }}
.container {{ max-width: 800px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
h2 {{ color: #333; margin-bottom: 20px; }}
p {{ color: #666; line-height: 1.6; margin-bottom: 16px; }}
.continue-btn {{ 
    display: inline-block; 
    background: #e91e63; 
    color: white; 
    padding: 14px 40px; 
    border: none; 
    border-radius: 6px; 
    font-size: 16px; 
    cursor: pointer; 
    margin-top: 30px;
    transition: background 0.3s;
}}
.continue-btn:hover {{ background: #c2185b; }}
</style>
</head>
<body>
<div class="container step active">
<h2>Пожалуйста, отвечайте внимательно.</h2>
<p>Ответы в опросе формируют ваш рейтинг участника — он зависит от внимательности, корректности и логичности ответов.</p>
<p>При низком рейтинге доступ к новым опросам и балансу аккаунта может быть ограничен.</p>
<p>Чтобы оценить внимательность, в опросе могут встречаться проверочные вопросы.</p>
<p>Спасибо за ответственное участие!</p>
<button class="continue-btn btn" onclick="startSurvey()">Продолжить</button>
</div>

<div id="survey" style="display:none; max-width: 800px; margin: 40px auto; background: white; padding: 40px; border-radius: 8px;" class="step">
<h2>Какой оператор сотовой связи ваш основной?</h2>
<label style="display:block; margin: 10px 0;"><input type="radio" name="operator" value="mts"> МТС</label>
<label style="display:block; margin: 10px 0;"><input type="radio" name="operator" value="beeline"> Билайн</label>
<label style="display:block; margin: 10px 0;"><input type="radio" name="operator" value="megafon"> МегаФон</label>
<button class="continue-btn btn" onclick="finishSurvey()">Далее</button>
</div>

<div id="finished" style="display:none; max-width: 800px; margin: 40px auto; background: white; padding: 40px; border-radius: 8px; text-align: center;" class="step">
<h2>Опрос завершен!</h2>
<p>Спасибо за участие. Вознаграждение зачислено.</p>
</div>

<script>
function startSurvey() {{
    document.querySelector('.container').style.display = 'none';
    document.querySelector('.container').classList.remove('active');
    document.getElementById('survey').style.display = 'block';
    document.getElementById('survey').classList.add('active');
}}
function finishSurvey() {{
    let op = document.querySelector('input[name="operator"]:checked');
    if (op) {{
        document.getElementById('survey').style.display = 'none';
        document.getElementById('survey').classList.remove('active');
        document.getElementById('finished').style.display = 'block';
        document.getElementById('finished').classList.add('active');
    }} else {{
        alert('Выберите вариант ответа!');
    }}
}}
</script>
</body>
</html>
"""


# ==========================================
# 2. ВНУТРЕННИЙ HTTP-СЕРВЕР
# ==========================================
class MockServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        if "basic" in self.path:
            self.wfile.write(HTML_BASIC.encode('utf-8'))
        elif "sawtooth" in self.path:
            self.wfile.write(HTML_SAWTOOTH_TRICKY.encode('utf-8'))
        elif "surveystudio" in self.path:
            self.wfile.write(HTML_SURVEYSTUDIO_TRICKY.encode('utf-8'))
        elif "cloudsurvey" in self.path:
            self.wfile.write(HTML_CLOUDSURVEY_TRICKY.encode('utf-8'))
        elif "expert" in self.path or "start" in self.path:
            self.wfile.write(HTML_EXPERTNOEMNENIE_START.encode('utf-8'))
        else:
            self.wfile.write(b"<h1>404 - Choose a valid test</h1>")


def start_server():
    server = HTTPServer(('127.0.0.1', 8888), MockServerHandler)
    server.serve_forever()


# ==========================================
# 3. ПЕРЕХВАТ ЛОГОВ (ДЛЯ ВЫВОДА В GUI)
# ==========================================
class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)

    def flush(self):
        pass


# ==========================================
# 4. ГРАФИЧЕСКИЙ ИНТЕРФЕЙС С ПАНЕЛЬЮ УПРАВЛЕНИЯ
# ==========================================
class SurveyTesterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("E2E Survey Tester")
        self.root.geometry("1100x700")
        self.root.configure(bg="#2b2b2b")

        self.async_loop = None

        # Левая панель с кнопками запуска
        self.left_frame = tk.Frame(root, bg="#2b2b2b", width=300)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=15, pady=15)

        tk.Label(self.left_frame, text="РАЗДЕЛЫ ТЕСТИРОВАНИЯ", fg="#ffffff", bg="#2b2b2b",
                 font=("Arial", 12, "bold")).pack(pady=(0, 20))

        self.create_button("Базовый опрос (Реклама)", "#0d6efd", "http://127.0.0.1:8888/basic")
        self.create_button("Ловушки Sawtooth\n(Скрытые селекты, картинки)", "#fd7e14", "http://127.0.0.1:8888/sawtooth")
        self.create_button("Ловушки SurveyStudio\n(Матрицы, Город, Number)", "#6f42c1",
                           "http://127.0.0.1:8888/surveystudio")
        self.create_button("Ловушки CloudSurvey\n(Город с дропдауном, общие заголовки)", "#17a2b8",
                           "http://127.0.0.1:8888/cloudsurvey")
        self.create_button("Стартовая страница\n(Expertnoe Mnenie)", "#e91e63", "http://127.0.0.1:8888/expert")

        # Правая панель с логами и управлением
        self.right_frame = tk.Frame(root, bg="#1e1e1e")
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=15)

        # Верхняя панель (Топ бар)
        top_bar = tk.Frame(self.right_frame, bg="#1e1e1e")
        top_bar.pack(fill=tk.X, pady=(0, 5))

        tk.Label(top_bar, text="ТЕРМИНАЛ / ЛОГИ БОТА", fg="#a9b7c6", bg="#1e1e1e",
                 font=("Arial", 10, "bold")).pack(side=tk.LEFT)

        btn_clear = tk.Button(top_bar, text="Очистить", bg="#3c3f41", fg="#a9b7c6",
                              font=("Arial", 8), relief="flat", padx=8, pady=2, cursor="hand2",
                              command=self.clear_logs)
        btn_clear.pack(side=tk.RIGHT, padx=5)

        btn_copy = tk.Button(top_bar, text="📋 Скопировать логи", bg="#365880", fg="white",
                             font=("Arial", 8, "bold"), relief="flat", padx=10, pady=2, cursor="hand2",
                             command=self.copy_logs)
        btn_copy.pack(side=tk.RIGHT)

        # --- ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ (Пауза / Отладка) ---
        ctrl_frame = tk.Frame(self.right_frame, bg="#1e1e1e")
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_pause = tk.Button(ctrl_frame, text="⏸ Пауза", bg="#f0ad4e", fg="white", font=("Arial", 10, "bold"),
                                   relief="flat", cursor="hand2", width=12, state="disabled", command=self.toggle_pause)
        self.btn_pause.pack(side=tk.LEFT)

        self.debug_var = tk.BooleanVar(value=False)
        self.chk_debug = tk.Checkbutton(ctrl_frame, text="Отладочный режим (Подтверждать шаг)",
                                        variable=self.debug_var, bg="#1e1e1e", fg="#a9b7c6", selectcolor="#3c3f41",
                                        activebackground="#1e1e1e", activeforeground="#ffffff", font=("Arial", 10),
                                        command=self.toggle_debug)
        self.chk_debug.pack(side=tk.LEFT, padx=15)

        self.btn_confirm = tk.Button(ctrl_frame, text="✅ Подтвердить шаг", bg="#198754", fg="white",
                                     font=("Arial", 10, "bold"), relief="flat", cursor="hand2", state="disabled",
                                     command=self.confirm_step)
        self.btn_confirm.pack(side=tk.LEFT)
        # -------------------------------------------------

        self.log_area = scrolledtext.ScrolledText(self.right_frame, bg="#1e1e1e", fg="#a9b7c6",
                                                  insertbackground="white", selectbackground="#214283",
                                                  selectforeground="#ffffff", font=("Consolas", 10),
                                                  borderwidth=0, undo=False)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        self.log_area.bind("<Key>", self.prevent_manual_typing)

        sys.stdout = StdoutRedirector(self.log_area)

        print("✅ Система готова.")
        print("✅ Локальный сервер поднят на http://127.0.0.1:8888")
        print("Выберите раздел слева для запуска автотеста...\n")

    # --- ЛОГИКА УПРАВЛЕНИЯ БОТОМ ---
    def toggle_pause(self):
        state.is_paused = not state.is_paused
        if self.async_loop:
            if state.is_paused:
                self.async_loop.call_soon_threadsafe(state.pause_event.clear)
                self.btn_pause.config(text="▶ Продолжить", bg="#28a745")
                print("\n[⏸] ПАУЗА. Бот замер и ждет команды...")
            else:
                self.async_loop.call_soon_threadsafe(state.pause_event.set)
                self.btn_pause.config(text="⏸ Пауза", bg="#f0ad4e")
                print("\n[▶] СНЯТО С ПАУЗЫ. Бот продолжает работу...")

    def toggle_debug(self):
        state.is_debug = self.debug_var.get()
        if state.is_debug:
            self.btn_confirm.config(state="normal")
            print(
                "\n[!] ОТЛАДОЧНЫЙ РЕЖИМ ВКЛЮЧЕН. Бот будет ждать подтверждения перед каждым переходом на новую страницу.")
        else:
            self.btn_confirm.config(state="disabled")
            print("\n[!] ОТЛАДОЧНЫЙ РЕЖИМ ВЫКЛЮЧЕН. Бот работает полностью автономно.")
            if self.async_loop and state.step_event and not state.step_event.is_set():
                self.async_loop.call_soon_threadsafe(state.step_event.set)

    def confirm_step(self):
        if self.async_loop and state.step_event:
            self.async_loop.call_soon_threadsafe(state.step_event.set)

    # --- ЛОГИКА GUI ---
    def prevent_manual_typing(self, event):
        if event.state & 0x4:
            if event.keysym.lower() in ('c', 'a'):
                return None
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Prior', 'Next', 'Home', 'End'):
            return None
        return "break"

    def copy_logs(self):
        logs = self.log_area.get("1.0", tk.END).strip()
        if logs:
            self.root.clipboard_clear()
            self.root.clipboard_append(logs)
            print("\n[✓] Все логи скопированы в буфер обмена!")

    def clear_logs(self):
        self.log_area.delete("1.0", tk.END)

    def create_button(self, text, color, url):
        btn = tk.Button(
            self.left_frame,
            text=text,
            bg=color,
            fg="white",
            font=("Arial", 11, "bold"),
            relief="flat",
            cursor="hand2",
            pady=12,
            command=lambda: self.start_test(url)
        )
        btn.pack(fill=tk.X, pady=8)

    def start_test(self, url):
        self.clear_logs()
        self.btn_pause.config(state="normal")
        print("=" * 60)
        print(f"🚀 Запуск теста для раздела: {url}")
        print("=" * 60)

        threading.Thread(target=self.run_playwright, args=(url,), daemon=True).start()

    def run_playwright(self, url):
        self.async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.async_loop)

        state.init_events()
        state.is_debug = self.debug_var.get()

        brain = SurveyBrain()
        router = SurveyRouter(brain=brain)

        try:
            self.async_loop.run_until_complete(router.run(url))
            print("\n[✅] ЗАВЕРШЕНО: Бот закончил обработку маршрутов.")
        except Exception as e:
            print(f"\n❌ Ошибка потока: {e}")
        finally:
            self.async_loop.close()
            self.async_loop = None
            self.btn_pause.config(state="disabled", text="⏸ Пауза", bg="#f0ad4e")


if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()

    root = tk.Tk()
    app = SurveyTesterApp(root)
    root.mainloop()