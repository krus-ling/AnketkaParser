import os
import sys

# Гарантируем видимость пакетов core и engines независимо от способа запуска
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import scrolledtext
import threading
import asyncio
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.brain import SurveyBrain
from engines.router import SurveyRouter
from core.bot_state import state

# ==========================================
# 1. HTML-ШАБЛОНЫ И ВАЛИДАЦИЯ (MOCKS)
# ==========================================

CSS_AND_JS_CLOUD = """
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; padding: 40px 20px; display: flex; justify-content: center; }
    .survey-container { background: #ffffff; max-width: 950px; width: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); padding: 35px 40px; }
    .question-text, .ss-question-title, .header1, .pr-question-title, .question-title { font-size: 19px; font-weight: 600; color: #222; margin-bottom: 15px; }
    .answer-item, .scale-item, .question__element-wrapper, .pr-row { background: #f8f9fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 12px 18px; margin-bottom: 10px; cursor: pointer; display: flex; align-items: center; }
    .btn, .btn-next, #next, button[name='goto'], #processingGoForwardBtn { color: #fff; border: none; border-radius: 6px; padding: 12px 30px; font-size: 16px; cursor: pointer; margin-top: 20px; background: #0d6efd; display: inline-block;}
    .step { display: none; } .step.active { display: block; }
    .result-box { padding: 20px; border-radius: 8px; margin-top: 20px; font-size: 18px; font-weight: bold; text-align: center; }
    .result-passed { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .result-failed { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    select, input[type="text"], input[type="number"] { padding: 10px; width: 100%; max-width: 400px; border: 1px solid #ccc; border-radius: 5px; margin-top: 10px; font-size: 15px; }

    /* Таблицы SurveyStudio */
    .ss-table-header { display: flex; font-weight: bold; font-size: 14px; margin-bottom: 10px; border-bottom: 2px solid #eee; padding-bottom: 10px;}
    .ss-table-header-empty { width: 40%; }
    .ss-table-header-titles { width: 60%; display: flex; justify-content: space-around; text-align: center; }
    #ssDesktopTableBodyContainer { width: 100%; }
    .ss-table-row { display: flex; align-items: center; min-height: 50px; border-bottom: 1px solid #f4f6f8; padding: 8px 0; }
    .ss-row-title { width: 40%; font-size: 15px; color: #333; }
    .ss-row-inputs { width: 60%; display: flex; justify-content: space-around; }
    .ss-row-inputs input { transform: scale(1.2); cursor: pointer; }

    /* Обычные списки Sawtooth */
    .grid__cell { display: flex; align-items: center; background: #f8f9fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 10px; margin-bottom: 8px; }
    .grid__cell label { display: flex; align-items: center; width: 100%; cursor: pointer; }
    .grid__cell input[type="text"], .grid__cell input[type="number"] { margin-left: 15px; flex-grow: 1; padding: 5px; border: 1px solid #ccc; border-radius: 4px; }
    .grid__cell span.answer-text { margin-left: 10px; }
    img.bank-logo { height: 30px; margin-left: 10px; border: 1px solid #eee; }
</style>
<script>
    function next(id) { 
        document.querySelectorAll('.step').forEach(s => s.classList.remove('active')); 
        document.getElementById(id).classList.add('active'); 
    }
    function showResult(score, total) {
        let box = document.getElementById('final-result');
        box.style.display = 'block';
        if (score >= total) {
            box.className = 'result-box result-passed';
            box.innerHTML = `✅ ТЕСТ ПРОЙДЕН! Правильных ответов: ${score}/${total}<br><br><span style="font-size:14px;font-weight:normal;">Опрос успешно завершен. Вознаграждение зачислено!</span>`;
        } else {
            box.className = 'result-box result-failed';
            box.innerHTML = `❌ ТЕСТ ПРОВАЛЕН! Правильных ответов: ${score}/${total}<br><br><span style="font-size:14px;font-weight:normal;">Бот ошибся в легенде или правилах.</span>`;
        }
    }
</script>
"""

# 1. Survstat (Router-Client Пре-опрос + адаптивный вопрос)
HTML_SURVSTAT = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Survstat Pre-Survey Test</title>{CSS_AND_JS_CLOUD}
<style>
    .PreSurveyPage {{ background:#fff; padding:25px; border-radius:8px; }}
    .StackItem_stackItem__CkLmS {{ display:flex; flex-direction:column; gap:10px; margin:15px 0; }}
    .Answer_wrapper__K04k3 {{ display:flex; align-items:center; gap:12px; padding:12px; border:1px solid #e0e0e0; border-radius:6px; cursor:pointer; }}
    .Answer_wrapper__K04k3.selected, .Answer_wrapper__K04k3:hover {{ background:#f5fbf7; border-color:#28a745; }}
    .Radio_radio__0j2QV {{ position:absolute; opacity:0; width:0; height:0; }}
    .Radio_indicator {{ width:20px; height:20px; border-radius:50%; border:2px solid #ccc; display:inline-block; }}
    .Radio_radio__0j2QV:checked + .Radio_indicator, .Answer_wrapper__K04k3.selected .Radio_indicator {{ background:#28a745; border-color:#28a745; box-shadow:inset 0 0 0 3px #fff; }}
    .DropDown_container {{ border:1px solid #ccc; border-radius:6px; padding:10px; margin-top:10px; position:relative; cursor:pointer; }}
    .DropDown_placeholder {{ font-size:12px; color:#888; margin-bottom:4px; }}
    .DropDown_container input {{ border:none; outline:none; width:100%; font-size:16px; padding:0; margin:0; background:transparent; }}
    .DropDown_menu {{ display:none; position:absolute; top:100%; left:0; right:0; background:#fff; border:1px solid #ccc; border-radius:4px; max-height:160px; overflow-y:auto; z-index:100; }}
    .DropDown_item {{ padding:8px 12px; cursor:pointer; }}
    .DropDown_item:hover {{ background:#e8f5e9; }}
    .Button_buttonContainer__868Xb {{ margin-top:25px; }}
    .Button_button__c0lXg {{ background:#28a745; color:#fff; text-align:center; padding:14px; border-radius:6px; font-weight:bold; cursor:pointer; font-size:16px; }}
    .Button_button__c0lXg:hover {{ background:#218838; }}
</style>
</head><body>
<div class="survey-container">
    <div id="step-1" class="step active PreSurveyPage">
        <h2 style="margin-top:0;">Время опросов 🎉</h2>
        <p style="color:#666;">Спасибо, что выбираете нас. Предлагаем вам заполнить анкету, на это нужно примерно 10 минут вашего времени. За успешно пройденный опрос мы начислим вам 15 баллов.</p>
        
        <div style="font-weight:600; font-size:16px; margin-top:20px;">Пол</div>
        <div class="StackItem_stackItem__CkLmS">
            <div class="Answer_wrapper__K04k3" onclick="selectGender(this, 'm')">
                <input class="Radio_radio__0j2QV" type="radio" name="gender" value="m" id="g_m">
                <span class="Radio_indicator"></span>
                <label for="g_m" style="cursor:pointer; font-size:15px;">Мужской</label>
            </div>
            <div class="Answer_wrapper__K04k3" onclick="selectGender(this, 'f')">
                <input class="Radio_radio__0j2QV" type="radio" name="gender" value="f" id="g_f">
                <span class="Radio_indicator"></span>
                <label for="g_f" style="cursor:pointer; font-size:15px;">Женский</label>
            </div>
        </div>

        <div style="font-weight:600; font-size:16px; margin-top:20px;">Дата рождения</div>
        <div style="display:flex; gap:15px;">
            <div class="DropDown_container" style="flex:1;">
                <div class="DropDown_placeholder">День</div>
                <input type="text" id="day-inp" value="" placeholder="27">
            </div>
            <div class="DropDown_container" style="flex:1;" onclick="toggleMenu('month-menu')">
                <div class="DropDown_placeholder">Месяц</div>
                <input type="text" id="month-inp" value="" readonly placeholder="Июнь">
                <div class="DropDown_menu" id="month-menu">
                    <div class="DropDown_item" onclick="chooseMonth('Январь')">Январь</div>
                    <div class="DropDown_item" onclick="chooseMonth('Февраль')">Февраль</div>
                    <div class="DropDown_item" onclick="chooseMonth('Март')">Март</div>
                    <div class="DropDown_item" onclick="chooseMonth('Апрель')">Апрель</div>
                    <div class="DropDown_item" onclick="chooseMonth('Май')">Май</div>
                    <div class="DropDown_item" onclick="chooseMonth('Июнь')">Июнь</div>
                </div>
            </div>
            <div class="DropDown_container" style="flex:1;">
                <div class="DropDown_placeholder">Год</div>
                <input type="text" id="year-inp" value="" placeholder="2005">
            </div>
        </div>

        <div class="Button_buttonContainer__868Xb">
            <div class="Button_button__c0lXg" onclick="next('step-2')">Начать опрос</div>
        </div>
    </div>

    <div id="step-2" class="step">
        <div class="question-text">В каком федеральном округе Вы проживаете постоянно (не менее 6 месяцев)?</div>
        <label class="answer-item" onclick="this.querySelector('input').checked=true; this.classList.add('selected');"><input type="radio" name="fo" value="cfo"> Центральный</label>
        <label class="answer-item" onclick="this.querySelector('input').checked=true; this.classList.add('selected');"><input type="radio" name="fo" value="szfo"> Северо-Западный</label>
        <label class="answer-item" onclick="this.querySelector('input').checked=true; this.classList.add('selected');"><input type="radio" name="fo" value="ufo"> Южный</label>
        <label class="answer-item" onclick="this.querySelector('input').checked=true; this.classList.add('selected');"><input type="radio" name="fo" value="urfo"> Уральский</label>
        <label class="answer-item" onclick="this.querySelector('input').checked=true; this.classList.add('selected');"><input type="radio" name="fo" value="pfo"> Приволжский</label>
        <button class="btn" onclick="validateSurvstat()">Далее</button>
    </div>

    <div id="step-3" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    function selectGender(el, val) {{
        document.querySelectorAll('.Answer_wrapper__K04k3').forEach(w => w.classList.remove('selected'));
        el.classList.add('selected');
        let inp = el.querySelector('input');
        if (inp) {{ inp.checked = true; inp.dispatchEvent(new Event('change', {{bubbles:true}})); }}
    }}
    function toggleMenu(id) {{
        let m = document.getElementById(id);
        m.style.display = m.style.display === 'block' ? 'none' : 'block';
    }}
    function chooseMonth(val) {{
        document.getElementById('month-inp').value = val;
        document.getElementById('month-menu').style.display = 'none';
        document.getElementById('month-inp').dispatchEvent(new Event('input', {{bubbles:true}}));
        document.getElementById('month-inp').dispatchEvent(new Event('change', {{bubbles:true}}));
    }}
    function validateSurvstat() {{
        let score = 0;
        let isMale = document.querySelector('input[name="gender"]:checked')?.value === 'm' ||
                     document.querySelector('.Answer_wrapper__K04k3.selected')?.innerText?.includes('Мужской');
        if (isMale) score++;
        let day = document.getElementById('day-inp')?.value?.trim();
        let month = document.getElementById('month-inp')?.value?.trim();
        let year = document.getElementById('year-inp')?.value?.trim();
        let dobOk = (day === '27' && (month === 'Июнь' || month === '6' || month === '06') && year === '2005');
        if (dobOk) score++;
        let isCfo = document.querySelector('input[name="fo"]:checked')?.value === 'cfo' ||
                    document.querySelector('.answer-item.selected')?.innerText?.includes('Центральный');
        if (isCfo) score++;
        console.log('SURVSTAT_VALIDATION: isMale=' + isMale + ', dobOk=' + dobOk + ', isCfo=' + isCfo + ' (day=' + day + ', month=' + month + ', year=' + year + ')');
        next('step-3'); showResult(score, 3);
    }}
</script></body></html>"""

# 2. Oprosso (Согласие, одиночные карточки-слайды, кнопка-стрелка)
HTML_OPROSSO = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Oprosso Test</title>{CSS_AND_JS_CLOUD}
<style>
    .oprosso-card {{ background:#fff; border-radius:12px; padding:30px; box-shadow:0 6px 18px rgba(0,0,0,0.06); }}
    .option__QmiJR {{ width:100%; text-align:left; background:#f8f9fa; border:2px solid #e9ecef; border-radius:10px; padding:15px 20px; margin-bottom:12px; cursor:pointer; display:flex; align-items:center; font-size:16px; transition:all 0.2s; }}
    .option__QmiJR.Active__IgXHd, .option__QmiJR:hover {{ border-color:#0d6efd; background:#e7f1ff; }}
    .circle__V3d0T {{ width:18px; height:18px; border-radius:50%; border:2px solid #adb5bd; margin-right:15px; flex-shrink:0; }}
    .option__QmiJR.Active__IgXHd .circle__V3d0T {{ background:#0d6efd; border-color:#0d6efd; box-shadow:inset 0 0 0 3px #fff; }}
    .arrow__IHQLS {{ width:50px; height:50px; border-radius:50%; background:#0d6efd; color:#fff; display:flex; align-items:center; justify-content:center; cursor:pointer; margin-top:20px; margin-left:auto; }}
    .arrow__IHQLS svg {{ width:24px; height:24px; fill:none; stroke:#fff; stroke-width:3; }}
    .startButton__d0j10 {{ background:#0d6efd; color:#fff; font-weight:bold; padding:14px 30px; border-radius:8px; border:none; cursor:pointer; font-size:16px; margin-top:20px; }}
</style>
</head><body>
<div class="survey-container">
    <div id="step-1" class="step active oprosso-card">
        <h2>Добро пожаловать в исследование</h2>
        <p>Пожалуйста, подтвердите согласие с правилами участия в исследовании.</p>
        <label style="display:flex; align-items:center; gap:10px; cursor:pointer; font-size:15px; margin-top:20px;">
            <input type="checkbox" name="check" id="oprosso_agree">
            <span>Я согласен с условиями проведения опроса</span>
        </label>
        <button class="startButton__d0j10" onclick="startOprosso()">Начать опрос</button>
    </div>

    <div id="step-2" class="step oprosso-card">
        <div class="question-text">1. Ваш пол:</div>
        <button class="option__QmiJR" onclick="chooseOprosso(this, 'm')">
            <div class="circle__V3d0T"></div>
            <div class="text__D38h0">Мужчина</div>
        </button>
        <button class="option__QmiJR" onclick="chooseOprosso(this, 'f')">
            <div class="circle__V3d0T"></div>
            <div class="text__D38h0">Женщина</div>
        </button>
        <div class="arrow__IHQLS" onclick="next('step-3')">
            <svg class="arrow_castom" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5"/></svg>
        </div>
    </div>

    <div id="step-3" class="step oprosso-card">
        <div class="question-text">2. Какая марка вашего личного автомобиля?</div>
        <button class="option__QmiJR" onclick="chooseOprosso(this, 'audi')">
            <div class="circle__V3d0T"></div>
            <div class="text__D38h0">Audi</div>
        </button>
        <button class="option__QmiJR" onclick="chooseOprosso(this, 'bmw')">
            <div class="circle__V3d0T"></div>
            <div class="text__D38h0">BMW</div>
        </button>
        <button class="option__QmiJR" onclick="chooseOprosso(this, 'geely')">
            <div class="circle__V3d0T"></div>
            <div class="text__D38h0">Geely</div>
        </button>
        <div class="arrow__IHQLS" onclick="validateOprosso()">
            <svg class="arrow_castom" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5"/></svg>
        </div>
    </div>

    <div id="step-4" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    let oprossoGender = '';
    let oprossoCar = '';
    function startOprosso() {{
        let cb = document.getElementById('oprosso_agree');
        if (cb && cb.checked) next('step-2');
        else alert('Необходимо подтвердить согласие!');
    }}
    function chooseOprosso(btn, val) {{
        let p = btn.parentElement;
        p.querySelectorAll('.option__QmiJR').forEach(b => b.classList.remove('Active__IgXHd'));
        btn.classList.add('Active__IgXHd');
        if (val === 'm' || val === 'f') oprossoGender = val;
        else oprossoCar = val;
    }}
    function validateOprosso() {{
        let score = 0;
        if (oprossoGender === 'm') score++;
        if (oprossoCar === 'audi') score++;
        next('step-4'); showResult(score, 2);
    }}
</script></body></html>"""

# 3. Pathway (Карточки data-testid, город, дети)
HTML_PATHWAY = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Pathway Test</title>{CSS_AND_JS_CLOUD}
<style>
    .pthwy-card {{ background:#fff; border-radius:10px; padding:30px; }}
    [data-testid*="respondent.choice.option"] {{ background:#f8f9fa; border:2px solid #dee2e6; border-radius:8px; padding:14px 20px; margin-bottom:10px; cursor:pointer; font-size:16px; display:flex; align-items:center; }}
    [data-testid*="respondent.choice.option"].selected, [data-testid*="respondent.choice.option"]:hover {{ border-color:#0d6efd; background:#e7f1ff; }}
    [data-testid="respondent.nextButton"] {{ background:#0d6efd; color:#fff; border:none; padding:12px 30px; border-radius:6px; font-weight:bold; cursor:pointer; font-size:16px; margin-top:20px; }}
</style>
</head><body>
<div class="survey-container">
    <div id="step-1" class="step active pthwy-card">
        <div class="question-text">В каком городе вы постоянно проживаете?</div>
        <div data-testid="respondent.choice.option.0" onclick="pickPthwy(this, 'spb')">г. Санкт-Петербург</div>
        <div data-testid="respondent.choice.option.1" onclick="pickPthwy(this, 'msk')">г. Москва</div>
        <div data-testid="respondent.choice.option.2" onclick="pickPthwy(this, 'ekb')">г. Екатеринбург</div>
        <button data-testid="respondent.nextButton" onclick="next('step-2')">Далее</button>
    </div>

    <div id="step-2" class="step pthwy-card">
        <div class="question-text">Есть ли у вас несовершеннолетние дети (до 18 лет)?</div>
        <div data-testid="respondent.choice.option.0" onclick="pickPthwy(this, 'yes')">Да, есть дети до 18 лет</div>
        <div data-testid="respondent.choice.option.1" onclick="pickPthwy(this, 'no')">Нет детей до 18 лет</div>
        <button data-testid="respondent.nextButton" onclick="validatePathway()">Завершить опрос</button>
    </div>

    <div id="step-3" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    let pthwyCity = '';
    let pthwyKids = '';
    function pickPthwy(el, val) {{
        el.parentElement.querySelectorAll('[data-testid*="respondent.choice.option"]').forEach(c => c.classList.remove('selected'));
        el.classList.add('selected');
        if (val === 'msk' || val === 'spb' || val === 'ekb') pthwyCity = val;
        else pthwyKids = val;
    }}
    function validatePathway() {{
        let score = 0;
        if (pthwyCity === 'msk') score++;
        if (pthwyKids === 'yes') score++;
        next('step-3'); showResult(score, 2);
    }}
</script></body></html>"""

# 4. Анкетка (Демография + Ловушка внимания + Награда только деньги)
HTML_ANKETKA = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Anketka Test</title>{CSS_AND_JS_CLOUD}</head><body>
<div class="survey-container">
    <div id="step-1" class="step active">
        <div class="question-text">Укажите ваш пол и дату рождения</div>
        <label class="answer-item"><input type="radio" name="gender" value="m"> Мужской</label>
        <label class="answer-item"><input type="radio" name="gender" value="f"> Женский</label>
        <div style="display:flex; gap:10px; margin-top:15px;">
            <select id="day"><option value="0">День</option><option value="27">27</option></select>
            <select id="month"><option value="0">Месяц</option><option value="6">Июнь</option></select>
            <select id="year"><option value="0">Год</option><option value="2005">2005</option></select>
        </div>
        <button class="btn" onclick="next('step-2')">Далее</button>
    </div>
    <div id="step-2" class="step">
        <div class="question-text">В качестве проверки вашей внимательности выберите третий вариант ответа:</div>
        <label class="answer-item"><input type="radio" name="attention" value="1"> Полностью согласен</label>
        <label class="answer-item"><input type="radio" name="attention" value="2"> Скорее согласен</label>
        <label class="answer-item"><input type="radio" name="attention" value="3"> Затрудняюсь ответить</label>
        <label class="answer-item"><input type="radio" name="attention" value="4"> Не согласен</label>
        <button class="btn" onclick="next('step-3')">Далее</button>
    </div>
    <div id="step-3" class="step">
        <div class="question-text">В какой из перечисленных сфер вы работаете?</div>
        <label class="answer-item"><input type="radio" name="job" value="marketing"> Маркетинг / Реклама</label>
        <label class="answer-item"><input type="radio" name="job" value="it"> Разработка ПО / IT</label>
        <label class="answer-item"><input type="radio" name="job" value="smi"> Журналистика / СМИ</label>
        <button class="btn" onclick="next('step-4')">Далее</button>
    </div>
    <div id="step-4" class="step">
        <div class="question-text">Поздравляем с завершением! Выберите форму вознаграждения:</div>
        <label class="answer-item"><input type="radio" name="reward" value="charity"> Перечислить в благотворительный фонд</label>
        <label class="answer-item"><input type="radio" name="reward" value="money"> Выплата денег на карту или мобильный телефон</label>
        <label class="answer-item"><input type="radio" name="reward" value="coupon"> Скидочный сертификат партнера</label>
        <button class="btn" onclick="validateAnketka()">Завершить опрос</button>
    </div>
    <div id="step-5" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    function validateAnketka() {{
        let score = 0;
        if (document.querySelector('input[name="gender"]:checked')?.value === 'm') score++;
        if (document.getElementById('year').value === '2005') score++;
        if (document.querySelector('input[name="attention"]:checked')?.value === '3') score++;
        if (document.querySelector('input[name="job"]:checked')?.value === 'it') score++;
        if (document.querySelector('input[name="reward"]:checked')?.value === 'money') score++;
        next('step-5'); showResult(score, 5);
    }}
</script></body></html>"""

# 5. CloudSurvey (Город ComboBox + сумма)
HTML_CLOUDSURVEY = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>CloudSurvey Test</title>{CSS_AND_JS_CLOUD}</head><body>
<div class="survey-container">
    <div id="step-1" class="step active">
        <div class="question-text">В каком городе вы проживаете?</div>
        <div class="select-wrap" style="position:relative;">
            <input type="text" id="city-input" placeholder="Начните вводить город...">
            <div id="city-list" style="display:none; position:absolute; background:#fff; border:1px solid #ccc; width:100%;">
                <div class="option" onclick="document.getElementById('city-input').value='Москва'">Москва</div>
                <div class="option" onclick="document.getElementById('city-input').value='Самара'">Самара</div>
            </div>
        </div>
        <button class="btn" id="nextSurvey" onclick="next('step-2')" style="margin-top:50px;">ДАЛЕЕ</button>
    </div>
    <div id="step-2" class="step">
        <div class="question-text">Сколько примерно рублей вы тратите на продукты в неделю?</div>
        <input type="number" id="money" placeholder="Сумма">
        <button class="btn" id="nextSurveyBtn" onclick="validateCloud()">ДАЛЕЕ</button>
    </div>
    <div id="step-3" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    document.getElementById('city-input').oninput = function() {{ document.getElementById('city-list').style.display = 'block'; }};
    function validateCloud() {{
        let score = 0;
        if (document.getElementById('city-input').value.includes('Москва')) score++;
        if (document.getElementById('money').value.includes('2500')) score++;
        next('step-3'); showResult(score, 2);
    }}
</script></body></html>"""

# 6. SurveyStudio (Матричные таблицы)
HTML_SURVEYSTUDIO = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>SurveyStudio Test</title>{CSS_AND_JS_CLOUD}</head><body>
<div class="survey-container">
    <div id="step-1" class="step active question-content">
        <div class="ss-question-title">Оцените бренды смартфонов по шкале привлекательности</div>
        <div id="ssDesktopTable">
            <div class="ss-table-header">
                <div class="ss-table-header-empty"></div>
                <div class="ss-table-header-titles">
                    <div class="ss-table-cell">Нравится</div>
                    <div class="ss-table-cell">Не нравится</div>
                </div>
            </div>
            <div id="ssDesktopTableBodyContainer">
                <div class="ss-table-row">
                    <div class="ss-row-title">Samsung</div>
                    <div class="ss-row-inputs">
                        <input type="radio" name="m1" value="good">
                        <input type="radio" name="m1" value="bad">
                    </div>
                </div>
                <div class="ss-table-row">
                    <div class="ss-row-title">Apple</div>
                    <div class="ss-row-inputs">
                        <input type="radio" name="m2" value="good">
                        <input type="radio" name="m2" value="bad">
                    </div>
                </div>
            </div>
        </div>
        <button id="processingGoForwardBtn" class="btn" onclick="validateSS()">Продолжить</button>
    </div>
    <div id="step-2" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    function validateSS() {{
        let score = 0;
        if (document.querySelector('input[name="m1"]:checked')?.value === 'good') score++;
        if (document.querySelector('input[name="m2"]:checked')) score++;
        next('step-2'); showResult(score, 2);
    }}
</script></body></html>"""

# 7. Sawtooth (Картинки авто + Select2 год + Слайдеры)
HTML_SAWTOOTH = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Sawtooth Test</title>{CSS_AND_JS_CLOUD}
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script src="https://code.jquery.com/ui/1.13.2/jquery-ui.min.js"></script>
<link rel="stylesheet" href="https://code.jquery.com/ui/1.13.2/themes/base/jquery-ui.css">
<style>
    .slider-row {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 25px; padding: 15px; background: #f8f9fa; border: 1px solid #d0d7de; border-radius: 6px; }}
    .left_label_cell, .right_label_cell {{ width: 25%; font-weight: 600; text-align: center; font-size: 14px; }}
    .slider_container {{ width: 50%; padding: 0 15px; }}
</style>
</head><body>
<div class="survey-container">
    <div id="step-1" class="step active">
        <div class="header1"><span class="_ru">Какую марку автомобиля вы водите?</span></div>
        <div class="question_body">
            <div class="grid__cell"><label for="c1"><img src="/images/car_1.jpg" style="height:100px; object-fit:contain;" alt="Mercedes" data-template="Audi"></label><input type="radio" id="c1" name="car" value="mercedes"></div>
            <div class="grid__cell"><label for="c2"><img src="/images/car_2.png" style="height:100px; object-fit:contain;" alt="BMW" data-template="BMW"></label><input type="radio" id="c2" name="car" value="bmw"></div>
            <div class="grid__cell"><label for="c3"><img src="/images/car_3.png" style="height:100px; object-fit:contain;" alt="Audi" data-template="Audi"></label><input type="radio" id="c3" name="car" value="audi"></div>
        </div>
        <input type="button" id="next_button" class="btn" value="Далее >>" onclick="next('step-2')">
    </div>
    <div id="step-2" class="step">
        <div class="header1">Год выпуска вашего автомобиля?</div>
        <select class="select2-hidden-accessible" id="year">
            <option value="0">Выбер...</option><option value="2020">2020</option><option value="2022">2022</option>
        </select>
        <input type="button" id="next_button_2" class="btn" value="Далее >>" onclick="next('step-3')">
    </div>
    <div id="step-3" class="step question">
        <div class="header2">Оцените ваш автомобиль по шкале:</div>
        <div class="question_body">
            <div class="slider-row">
                <div class="left_label_cell">Медленный</div>
                <div class="slider_container">
                    <div id="slider1" class="ui-slider slider_control">
                        <input type="hidden" name="q1" id="q1_hidden" value="0">
                    </div>
                </div>
                <div class="right_label_cell">Быстрый</div>
            </div>
            <div class="slider-row">
                <div class="left_label_cell">Дешевый</div>
                <div class="slider_container">
                    <div id="slider2" class="ui-slider slider_control">
                        <input type="hidden" name="q2" id="q2_hidden" value="0">
                    </div>
                </div>
                <div class="right_label_cell">Дорогой</div>
            </div>
        </div>
        <button id="next_button_3" class="btn" onclick="validateSawtooth()">Далее >></button>
    </div>
    <div id="step-4" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    $(function() {{
        $(".ui-slider").slider({{
            min: 1, max: 100, value: 50,
            slide: function(event, ui) {{
                $(this).addClass("touched");
                $(this).find("input[type=hidden]").val(ui.value).trigger('change');
            }}
        }});
    }});
    function validateSawtooth() {{
        let score = 0;
        if (document.querySelector('input[name="car"]:checked')?.value === 'audi') score++;
        if (document.getElementById('year').value === '2022') score++;
        if ($("#slider1").hasClass("touched")) score++;
        if ($("#slider2").hasClass("touched")) score++;
        next('step-4'); showResult(score, 4);
    }}
</script></body></html>"""

# 8. Sawtooth Attention (Ловушка с картинками животных)
HTML_SAWTOOTH_ATTENTION = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Sawtooth Attention Test</title>{CSS_AND_JS_CLOUD}
<style>
    .grid-container {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-top: 20px; }}
    .grid__cell {{ background: #fff; border: 2px solid #dee2e6; border-radius: 8px; text-align: center; padding: 10px; cursor: pointer; transition: all 0.2s; }}
    .grid__cell img {{ width: 100%; height: 180px; object-fit: contain; background: #f8f9fa; border-radius: 6px; display: block; }}
    .grid__cell input {{ display: none; }}
    .grid__cell.selected {{ border-color: #198754; background: #e8f5e9; box-shadow: 0 0 0 3px rgba(25, 135, 84, 0.25); }}
</style>
</head><body>
<div class="survey-container">
    <div id="step-1" class="step active question">
        <div class="header2">Проверка на внимательность: выберите, пожалуйста, картинку с енотом.</div>
        <div class="question_body grid-container">
            <label class="grid__cell"><img src="/images/img_1.jpg"><input type="radio" name="animal" value="0"></label>
            <label class="grid__cell"><img src="/images/img_2.jpg"><input type="radio" name="animal" value="1"></label>
            <label class="grid__cell"><img src="/images/img_3.jpg"><input type="radio" name="animal" value="2"></label>
            <label class="grid__cell"><img src="/images/img_4.jpg"><input type="radio" name="animal" value="3"></label>
            <label class="grid__cell"><img src="/images/img_5.jpg"><input type="radio" name="animal" value="4"></label>
            <label class="grid__cell"><img src="/images/img_6.jpg"><input type="radio" name="animal" value="5"></label>
        </div>
        <button id="next_button" class="btn" onclick="validateAttention()" style="margin-top:25px;">Далее >></button>
    </div>
    <div id="step-2" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    document.querySelectorAll('.grid__cell input').forEach(inp => {{
        inp.addEventListener('change', function() {{
            document.querySelectorAll('.grid__cell').forEach(c => c.classList.remove('selected'));
            this.parentElement.classList.add('selected');
        }});
    }});
    function validateAttention() {{
        let score = 0;
        if (document.querySelector('input[name="animal"]:checked')?.value === '3') score++;
        next('step-2'); showResult(score, 1);
    }}
</script></body></html>"""

# 9. Anketolog (Vue обертки + Экран 100% завершения с кнопкой возврата)
HTML_ANKETOLOG = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Anketolog Test</title>{CSS_AND_JS_CLOUD}</head><body class="survey-fill">
<div class="survey-container">
    <div id="step-1" class="step active">
        <div class="question-title">Какую марку смартфона вы используете? *</div>
        <div class="question__element-wrapper" onclick="this.querySelector('input').checked=true">
            <div class="question__element-custom"></div>
            <span class="question__element-text">Apple iPhone</span>
            <input type="radio" name="phone" value="apple" style="display:none;">
        </div>
        <div class="question__element-wrapper" onclick="this.querySelector('input').checked=true">
            <div class="question__element-custom"></div>
            <span class="question__element-text">Samsung</span>
            <input type="radio" name="phone" value="samsung" style="display:none;">
        </div>
        <button class="btn-success btn" onclick="finishAnketolog()">ДАЛЕЕ</button>
    </div>
    <div id="step-2" class="step">
        <div style="text-align:center; padding:30px;">
            <h3>100% пройдено</h3>
            <p>Ваши ответы вместе с мнениями других участников приняты. Благодарим за участие!</p>
            <a href="javascript:void(0)" class="btn" onclick="validateAnketolog()" style="text-decoration:none;">Вернуться в Личный кабинет</a>
        </div>
    </div>
    <div id="step-3" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    let anketologScore = 0;
    function finishAnketolog() {{
        if (document.querySelector('input[name="phone"]:checked')?.value === 'samsung') anketologScore++;
        next('step-2');
    }}
    function validateAnketolog() {{
        next('step-3'); showResult(anketologScore, 1);
    }}
</script></body></html>"""

# 10. ProfiResearch (Таблицы и Selectize)
HTML_PROFIRESEARCH = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>ProfiResearch Test</title>{CSS_AND_JS_CLOUD}</head><body>
<div class="survey-container">
    <form class="pr-question step active" id="step-1">
        <pr-question-title>Выберите ваш любимый горячий напиток:</pr-question-title>
        <table>
            <tr class="pr-row" onclick="this.querySelector('input').checked=true"><td><label>Чай</label></td><td><input type="radio" name="drink" value="tea"></td></tr>
            <tr class="pr-row" onclick="this.querySelector('input').checked=true"><td><label>Кофе</label></td><td><input type="radio" name="drink" value="coffee"></td></tr>
        </table>
        <button name="goto" class="btn" type="button" onclick="validateProfi()">Вперед</button>
    </form>
    <div id="step-2" class="step"><div id="final-result" style="display:none;"></div></div>
</div>
<script>
    function validateProfi() {{
        let score = 0;
        if (document.querySelector('input[name="drink"]:checked')) score++;
        next('step-2'); showResult(score, 1);
    }}
</script></body></html>"""

# 11. ИИ Чат-Опрос (Диалоговый движок MakeSense)
HTML_CHAT = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Chat Test</title>{CSS_AND_JS_CLOUD}
<style>.chat-container {{ height: 300px; overflow-y: auto; background: #fafafa; padding: 20px; border: 1px solid #ccc; border-radius: 8px; }} .msg {{ margin-bottom: 15px; padding: 10px 14px; border-radius: 8px; width: fit-content; max-width:80%; }} .msg.bot {{ background: #e9ecef; }} .msg.user {{ background: #0d6efd; color: white; margin-left: auto; }}</style>
</head><body>
<div class="survey-container">
    <div id="chat-box" class="chat-container">
        <div class="msg bot">Привет! Начнем диалоговое интервью. Как вас зовут?</div>
    </div>
    <div style="display:flex; gap:10px; margin-top:15px;">
        <input type="text" id="chat-input" placeholder="Введите ответ...">
        <button id="send-btn" class="btn" style="margin-top:0;">Отправить</button>
    </div>
    <div id="final-result" style="display:none; margin-top:20px;"></div>
</div>
<script>
    let step = 0; let score = 0;
    document.getElementById('send-btn').onclick = function() {{
        let text = document.getElementById('chat-input').value;
        if (!text) return;
        document.getElementById('chat-box').innerHTML += `<div class="msg user">${{text}}</div>`;
        document.getElementById('chat-input').value = '';

        if (step === 0) {{
            if (text.toLowerCase().includes('александр')) score++;
            setTimeout(() => {{ document.getElementById('chat-box').innerHTML += `<div class="msg bot">Отлично! А сколько вам полных лет?</div>`; }}, 500);
            step++;
        }} else if (step === 1) {{
            if (text.includes('21')) score++;
            setTimeout(() => {{ showResult(score, 2); document.getElementById('chat-box').style.display='none'; }}, 500);
        }}
    }};
</script></body></html>"""


# ==========================================
# 2. ВНУТРЕННИЙ HTTP-СЕРВЕР ДЛЯ ТЕСТОВ
# ==========================================
class MockServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        clean_path = self.path.split('?')[0]

        # Отдача локальных картинок из папки images
        if clean_path.startswith('/images/'):
            filename = os.path.basename(clean_path)
            image_path = os.path.join(os.path.dirname(__file__), "images", filename)

            if os.path.exists(image_path):
                self.send_response(200)
                self.send_header("Content-type", "image/jpeg")
                self.end_headers()
                with open(image_path, 'rb') as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        routes = {
            "/survstat": HTML_SURVSTAT,
            "/oprosso": HTML_OPROSSO,
            "/pthwy": HTML_PATHWAY,
            "/anketka": HTML_ANKETKA,
            "/cloudsurvey": HTML_CLOUDSURVEY,
            "/surveystudio": HTML_SURVEYSTUDIO,
            "/sawtooth": HTML_SAWTOOTH,
            "/sawtooth_attention": HTML_SAWTOOTH_ATTENTION,
            "/anketolog": HTML_ANKETOLOG,
            "/profiresearch": HTML_PROFIRESEARCH,
            "/chat": HTML_CHAT
        }

        # Строгое сравнение маршрута
        if clean_path in routes:
            self.wfile.write(routes[clean_path].encode('utf-8'))
        else:
            self.wfile.write(b"<h1>404 - Choose a valid test</h1>")


def start_server():
    try:
        server = HTTPServer(('127.0.0.1', 8888), MockServerHandler)
        server.serve_forever()
    except OSError:
        pass


# БЕЗОПАСНАЯ РАБОТА С GUI ИЗ ПОТОКА
class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.after(0, self._insert, string)

    def _insert(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)

    def flush(self): pass


# ==========================================
# 3. ГРАФИЧЕСКИЙ ИНТЕРФЕЙС И ОРКЕСТРАТОР
# ==========================================
class SurveyTesterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("E2E Бот-Тренажер всех платформ и типов опросов")
        self.root.geometry("1180x760")
        self.root.configure(bg="#2b2b2b")

        self.async_loop = None
        self.is_running = False

        # Хранилище индикаторов статуса тестов (Label)
        self.test_indicators = {}

        self.tests = [
            ("Survstat (Пре-опрос: Пол, Дата, Округ)", "#0dcaf0", "http://127.0.0.1:8888/survstat"),
            ("Oprosso (Согласие, Слайды, Стрелка)", "#e63946", "http://127.0.0.1:8888/oprosso"),
            ("Pathway (Data-TestId, Карточки выбора)", "#457b9d", "http://127.0.0.1:8888/pthwy"),
            ("Анкетка (Ловушка + Награда только деньги)", "#0d6efd", "http://127.0.0.1:8888/anketka"),
            ("CloudSurvey (Город ComboBox, Сумма)", "#17a2b8", "http://127.0.0.1:8888/cloudsurvey"),
            ("SurveyStudio (Матричные таблицы)", "#6f42c1", "http://127.0.0.1:8888/surveystudio"),
            ("Sawtooth (Картинки авто, Select2, Слайдеры)", "#fd7e14", "http://127.0.0.1:8888/sawtooth"),
            ("Sawtooth (Проверка внимания: Енот)", "#ffc107", "http://127.0.0.1:8888/sawtooth_attention"),
            ("Anketolog (Vue Обёртки + Финал 100%)", "#20c997", "http://127.0.0.1:8888/anketolog"),
            ("ProfiResearch (Selectize, Таблицы)", "#e83e8c", "http://127.0.0.1:8888/profiresearch"),
            ("ИИ Чат-Опрос (Интервью MakeSense)", "#198754", "http://127.0.0.1:8888/chat"),
        ]

        self.left_frame = tk.Frame(root, bg="#2b2b2b", width=340)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=15, pady=15)

        tk.Label(self.left_frame, text="МОДУЛИ И ДВИЖКИ ОПРОСОВ", fg="#ffffff", bg="#2b2b2b", font=("Arial", 11, "bold")).pack(
            pady=(0, 10))

        # Кнопка ЗАПУСТИТЬ ВСЕ
        self.btn_all = tk.Button(self.left_frame, text="🚀 ЗАПУСТИТЬ ВСЕ ТЕСТЫ", bg="#dc3545", fg="white",
                                 font=("Arial", 11, "bold"), relief="flat", cursor="hand2", pady=10,
                                 command=self.run_all_tests)
        self.btn_all.pack(fill=tk.X, pady=(0, 15))

        for name, color, url in self.tests:
            self.create_button(name, color, url)

        self.right_frame = tk.Frame(root, bg="#1e1e1e")
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=15)

        top_bar = tk.Frame(self.right_frame, bg="#1e1e1e")
        top_bar.pack(fill=tk.X, pady=(0, 5))

        tk.Label(top_bar, text="ТЕРМИНАЛ / ЛОГИ БОТА В РЕАЛЬНОМ ВРЕМЕНИ", fg="#a9b7c6", bg="#1e1e1e", font=("Arial", 10, "bold")).pack(
            side=tk.LEFT)
        tk.Button(top_bar, text="Очистить лог", bg="#3c3f41", fg="#a9b7c6", font=("Arial", 8), relief="flat",
                  command=self.clear_logs).pack(side=tk.RIGHT, padx=5)

        ctrl_frame = tk.Frame(self.right_frame, bg="#1e1e1e")
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_pause = tk.Button(ctrl_frame, text="⏸ Пауза", bg="#f0ad4e", fg="white", font=("Arial", 10, "bold"),
                                   relief="flat", state="disabled", command=self.toggle_pause)
        self.btn_pause.pack(side=tk.LEFT)

        self.debug_var = tk.BooleanVar(value=False)
        self.chk_debug = tk.Checkbutton(ctrl_frame, text="Отладочный режим (Подтверждать шаг)", variable=self.debug_var,
                                        bg="#1e1e1e", fg="#a9b7c6", selectcolor="#3c3f41", activebackground="#1e1e1e",
                                        activeforeground="#ffffff", command=self.toggle_debug)
        self.chk_debug.pack(side=tk.LEFT, padx=15)

        self.btn_confirm = tk.Button(ctrl_frame, text="✅ Подтвердить шаг", bg="#198754", fg="white",
                                     font=("Arial", 10, "bold"), relief="flat", state="disabled",
                                     command=self.confirm_step)
        self.btn_confirm.pack(side=tk.LEFT)

        self.log_area = scrolledtext.ScrolledText(self.right_frame, bg="#1e1e1e", fg="#a9b7c6",
                                                  insertbackground="white", selectbackground="#214283",
                                                  selectforeground="#ffffff", font=("Consolas", 10), borderwidth=0)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        sys.stdout = StdoutRedirector(self.log_area)
        print("✅ Сервер-тренажер поднят на http://127.0.0.1:8888")

    # --- УПРАВЛЕНИЕ ИНДИКАТОРАМИ СТАТУСА ---
    def set_indicator(self, url, status):
        ind = self.test_indicators.get(url)
        if not ind: return

        if status == "running":
            ind.config(text="⏳", fg="#f59e0b")
        elif status == "success":
            ind.config(text="✅", fg="#10b981")
        elif status == "error":
            ind.config(text="❌", fg="#ef4444")
        elif status == "reset":
            ind.config(text="⚫", fg="#444444")

    def create_button(self, text, color, url):
        row_frame = tk.Frame(self.left_frame, bg="#2b2b2b")
        row_frame.pack(fill=tk.X, pady=3)

        indicator = tk.Label(row_frame, text="⚫", fg="#444444", bg="#2b2b2b", font=("Arial", 12))
        indicator.pack(side=tk.LEFT, padx=(0, 6))

        btn = tk.Button(row_frame, text=text, bg=color, fg="white", font=("Arial", 9, "bold"), relief="flat",
                        cursor="hand2", pady=6, command=lambda: self.start_single_test(url))
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.test_indicators[url] = indicator

    # --- УПРАВЛЕНИЕ ТЕСТАМИ ---
    def toggle_pause(self):
        state.is_paused = not state.is_paused
        if self.async_loop:
            if state.is_paused:
                self.async_loop.call_soon_threadsafe(state.pause_event.clear)
                self.btn_pause.config(text="▶ Продолжить", bg="#28a745")
                print("\n[⏸] ПАУЗА...")
            else:
                self.async_loop.call_soon_threadsafe(state.pause_event.set)
                self.btn_pause.config(text="⏸ Пауза", bg="#f0ad4e")
                print("\n[▶] СНЯТО С ПАУЗЫ...")

    def toggle_debug(self):
        state.is_debug = self.debug_var.get()
        self.btn_confirm.config(state="normal" if state.is_debug else "disabled")
        if not state.is_debug and self.async_loop and state.step_event and not state.step_event.is_set():
            self.async_loop.call_soon_threadsafe(state.step_event.set)

    def confirm_step(self):
        if self.async_loop and state.step_event:
            self.async_loop.call_soon_threadsafe(state.step_event.set)

    def clear_logs(self):
        self.log_area.delete("1.0", tk.END)

    def start_single_test(self, url):
        if self.is_running:
            return
        self.is_running = True
        self.set_indicator(url, "reset")
        self.clear_logs()
        self.btn_pause.config(state="normal")
        threading.Thread(target=self.run_playwright, args=([url],), daemon=True).start()

    def run_all_tests(self):
        if self.is_running:
            return
        self.is_running = True

        for url in self.test_indicators.keys():
            self.set_indicator(url, "reset")

        self.clear_logs()
        self.btn_pause.config(state="normal")
        urls = [url for _, _, url in self.tests]
        threading.Thread(target=self.run_playwright, args=(urls,), daemon=True).start()

    def run_playwright(self, urls):
        self.async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.async_loop)
        state.init_events()
        state.is_debug = self.debug_var.get()
        brain = SurveyBrain()
        router = SurveyRouter(brain=brain)

        try:
            for i, url in enumerate(urls):
                self.root.after(0, self.set_indicator, url, "running")

                print("\n" + "🌟" * 30)
                print(f"ТЕСТ {i + 1}/{len(urls)}: {url}")
                print("🌟" * 30 + "\n")

                try:
                    self.async_loop.run_until_complete(router.run(url))
                    self.root.after(0, self.set_indicator, url, "success")
                except Exception as step_err:
                    print(f"\n❌ Ошибка в тесте {url}: {step_err}")
                    self.root.after(0, self.set_indicator, url, "error")

                time.sleep(1.5)
            print("\n[✅] ВСЕ НАЗНАЧЕННЫЕ ТЕСТЫ ЗАВЕРШЕНЫ!")
        except Exception as e:
            print(f"\n❌ Глобальная ошибка: {e}")
        finally:
            self.async_loop.close()
            self.async_loop = None
            self.is_running = False
            self.btn_pause.config(state="disabled")


if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    root = tk.Tk()
    app = SurveyTesterApp(root)
    root.mainloop()
