"""
Хранилище JavaScript-сниппетов для инъекций через page.evaluate()
"""

# ==========================================
# 1. ОБЩАЯ НАВИГАЦИЯ И СОСТОЯНИЕ
# ==========================================

JS_FIND_FALLBACK_NEXT_BTN = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let kws = ['далее', 'вперед', 'продолжить', 'начать опрос', 'начать', 'подобрать опрос', 'старт', 'получить', 'согласен', 'принимаю', 'принять', 'понятно', 'перейти', 'к опросу'];

    let candidates = Array.from(active.querySelectorAll('button, a, div, span, input[type="submit"], input[type="button"]')).filter(el => {
        if (el.getBoundingClientRect().height === 0) return false;
        let style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0' || el.disabled) return false;

        let txt = (el.innerText || el.value || '').trim().toLowerCase();
        if (txt.length === 0 || txt.length > 30) return false;
        if (txt.includes('нажмите') || txt.includes('пожалуйста') || txt.includes('чтобы') || txt.includes('инструкц')) return false;

        let isBtn = el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'INPUT' || (el.className || '').toLowerCase().includes('btn') || (el.className || '').toLowerCase().includes('button') || (el.className || '').toLowerCase().includes('mrnext');
        let hasKw = kws.some(kw => txt === kw || txt.includes(kw));

        return isBtn && hasKw;
    });

    if (candidates.length > 0) {
        candidates.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
        return candidates[0];
    }
    return null;
}"""

JS_SYNC_MEMORY = """() => {
    let results = [];

    function isVisible(el) {
        if (!el || el.nodeType !== 1) return false;
        if (el.getBoundingClientRect().height === 0) return false;
        let style = window.getComputedStyle(el);
        if (style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none') return false;
        return true;
    }

    function getCleanText(el) {
        if (!el) return "";
        let ru = el.querySelector('span._ru, ._ru');
        if (ru) {
            let t = (ru.innerText || ru.textContent || "").trim();
            if (t) return t;
        }
        let img = el.querySelector('img');
        if (img) {
            let t = img.getAttribute('title') || img.getAttribute('data-template') || img.getAttribute('alt') || "";
            if (t) return t.trim();
        }
        let clone = el.cloneNode(true);
        Array.from(clone.querySelectorAll('._uk, ._kz, ._tj, ._ge, ._ar, ._md, ._az, ._uz, ._kg')).forEach(s => s.remove());
        return (clone.innerText || clone.textContent || "").replace(/\\s+/g, ' ').trim();
    }

    let questionBlocks = Array.from(document.querySelectorAll('.question-content, .ss-answers, .pr-question, .question__element-wrapper, form, .step.active')).filter(isVisible);
    if (questionBlocks.length === 0) questionBlocks = [document.body];

    function getClosestTitle(block) {
        let titleSelectors = '.header1, .header2, .question-text, .ss-question-title, pr-question-title, .pr-question-title, h-block, .h-block, .question-title, .question__title, h1, h2, h3';
        let title = block.querySelector(titleSelectors);
        if (title && isVisible(title)) {
            let t = getCleanText(title).replace(/\\*$/, '').trim();
            if (t) return t;
        }

        let parent = block;
        while (parent && parent.tagName !== 'BODY') {
            let prev = parent.previousElementSibling;
            while (prev) {
                if (isVisible(prev)) {
                    if (prev.matches(titleSelectors)) {
                        let t = getCleanText(prev).replace(/\\*$/, '').trim();
                        if (t) return t;
                    }
                    let inside = prev.querySelector(titleSelectors);
                    if (inside && isVisible(inside)) {
                        let t = getCleanText(inside).replace(/\\*$/, '').trim();
                        if (t) return t;
                    }
                }
                prev = prev.previousElementSibling;
            }
            parent = parent.parentElement;
        }

        let allTitles = Array.from(document.querySelectorAll(titleSelectors)).filter(isVisible);
        for (let el of allTitles) {
            let t = getCleanText(el).replace(/\\*$/, '').trim();
            if (t) return t;
        }
        return document.title || "Неизвестный вопрос";
    }

    let processedQs = new Set();

    questionBlocks.forEach(block => {
        let qText = getClosestTitle(block);
        if (!qText || processedQs.has(qText) || qText === "Неизвестный вопрос") return;

        let hasAnswers = false;

        let textInps = Array.from(block.querySelectorAll('input[type="text"]:not([readonly]), textarea, input[type="number"]')).filter(isVisible);
        textInps.forEach(textInp => {
            let idStr = textInp.id || "";
            let nameStr = textInp.name || "";
            if (idStr.includes('_other') || nameStr.includes('_other')) return;

            let cell = textInp.closest('[data-rowidx], .grid__cell, tr, .question__list-item, .pr-row, div.ss-table-row');
            if (cell && cell.querySelector('input[type="radio"], input[type="checkbox"]')) return;

            if (textInp.value.trim() !== '') {
                results.push({type: 'text', q: qText, val: textInp.value.trim()});
                hasAnswers = true;
            }
        });

        let choices = Array.from(block.querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(c => {
            if (isVisible(c)) return true;
            let cId = c.id || "";
            if (cId) {
                let label = (c.labels && c.labels.length > 0) ? c.labels[0] : null;
                if (label && isVisible(label)) return true;
                let graph = document.getElementById(cId + '_graphical');
                if (graph && isVisible(graph)) return true;
            }
            return false;
        });

        let isMatrix = block.querySelector('.ss-table-header') !== null || block.closest('#ssDesktopTable') !== null || block.querySelector('thead') !== null;

        if (choices.length > 0 && !isMatrix) {
            let options = [];
            let selected_indices = [];
            let selected_texts = [];

            choices.forEach((c, idx) => {
                let container = c.closest('[data-rowidx], .grid__cell, .ss-choice-answers__container > div, tr, .question__list-item, .pr-row, div.ss-table-row, .choice__option') || c.parentElement.parentElement || c.parentElement;
                let baseOptText = "";

                if (container) {
                    let label = (c.labels && c.labels.length > 0) ? c.labels[0] : null;
                    if (label) {
                        baseOptText = getCleanText(label);
                    }
                    if (!baseOptText) {
                        baseOptText = getCleanText(container);
                    }

                    let textInp = container.querySelector('input[type="text"]');
                    if (textInp) {
                        if (textInp.placeholder) {
                            baseOptText = "Свой вариант: " + textInp.placeholder;
                        } else {
                            baseOptText = "Свой вариант";
                        }
                    }
                }

                baseOptText = baseOptText || `Вариант ответа ${idx + 1}`;
                options.push(baseOptText);

                if (c.checked) {
                    selected_indices.push(idx);
                    let textInp = container ? container.querySelector('input[type="text"]') : null;
                    if (textInp && textInp.value.trim() !== '') {
                        selected_texts.push(baseOptText + " [" + textInp.value.trim() + "]");
                    } else {
                        selected_texts.push(baseOptText);
                    }
                }
            });

            if (selected_indices.length > 0) {
                results.push({
                    type: 'choices',
                    q: qText,
                    opts: options,
                    indices: selected_indices,
                    texts: selected_texts
                });
                hasAnswers = true;
            }
        }

        let sel = block.querySelector('select');
        if (sel && (isVisible(sel) || sel.classList.contains('ss-search-select') || sel.classList.contains('select2-hidden-accessible')) && sel.selectedIndex > 0) {
            let options = Array.from(sel.querySelectorAll('option'))
                .filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'))
                .map(o => o.innerText.trim());

            let valText = sel.options[sel.selectedIndex].innerText.trim();
            let idx = options.indexOf(valText);
            if (idx !== -1) {
                results.push({type: 'select', q: qText, opts: options, indices: [idx], texts: [valText]});
                hasAnswers = true;
            }
        }

        if (hasAnswers) processedQs.add(qText);
    });
    return results;
}"""

# ==========================================
# 2. ПАРСИНГ ДЕМОГРАФИИ
# ==========================================

JS_CHECK_DEMOGRAPHICS = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let txt = (active.innerText || '').toLowerCase();
    let hasDate = active.querySelectorAll('.select-wrap, div[class*="select-input"], div[class*="DropDown_container"], tr[class*="table-row-"], select').length >= 2;
    let hasGender = (txt.includes('мужской') || txt.includes('женский')) && active.querySelectorAll('input[type="radio"], div[class*="radio"], div[class*="Radio"], .answer-item, .choice-item, div.circle').length > 0;
    let hasDateWords = txt.includes('дату') || txt.includes('рождения') || txt.includes('число') || txt.includes('месяц') || txt.includes('год');
    let hasIntro = txt.includes('время опросов');

    return (hasDate && hasDateWords) || hasGender || hasIntro;
}"""

JS_MARK_DATE_CONTAINERS = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let containers = Array.from(active.querySelectorAll('.select-wrap, div[class*="select-input"], div[class*="DropDown_container"], select')).filter(el => el.getBoundingClientRect().height > 0 && !el.disabled);
    let roots = containers.filter(c => !containers.some(o => o !== c && o.contains(c)));

    if (roots.length >= 3) {
        roots[0].setAttribute('data-bot-date-target', '0');
        roots[1].setAttribute('data-bot-date-target', '1');
        roots[2].setAttribute('data-bot-date-target', '2');
    }
}"""

# ==========================================
# 3. ПАРСИНГ ВОПРОСОВ
# ==========================================

JS_EXTRACT_QUESTION_TEXT = """() => {
    let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"])'));
    let active = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;

    // Добавлены классы Яндекс Опросов: .question__label, [role="heading"], .markdown, а также Pathway/Pythia: .tiptap, .ProseMirror
    let headers = Array.from(active.querySelectorAll('.question__label, [role="heading"], .question-text, .question__title, .header1, .header2, .mrQuestionText, .question-card__text, .tiptap, .ProseMirror, [data-test-id*="test__content"] p, div[class*="question-header"], div[class*="QuestionHeader"], div[class*="question-title"], div[class*="question__title"], div[class*="HeaderStyled"], div[class*="title__"], div[class*="name__"], h1, h2, h3, h4')).filter(h => h.getBoundingClientRect().height > 0);
    for (let h of headers) {
        let txt = (h.innerText || '').trim();
        if (txt.length > 4 && !txt.toLowerCase().includes('время опросов') && !txt.toLowerCase().includes('пожалуйста') && !txt.toLowerCase().match(/^вопрос\\s*\\d+$/)) {
            return txt;
        }
    }
    for (let h of headers) {
        let txt = (h.innerText || '').trim();
        if (txt.length > 2) return txt;
    }
    return "Выберите подходящий вариант";
}"""

JS_CHECK_INFO_SCREEN = """() => {
    let bodyText = (document.body ? document.body.innerText || '' : '').toLowerCase();
    // Игнорируем сетевые ошибки браузера (Chrome net error / timeout)
    if (bodyText.includes('не удается получить доступ к сайту') ||
        bodyText.includes('превышено время ожидания ответа') ||
        bodyText.includes('err_connection') ||
        bodyText.includes('err_name_not_resolved') ||
        bodyText.includes('dns_probe_finished')) {
        return null;
    }

    let active = document.querySelector('.step.active') || document.body;

    // ЗАЩИТА: Если есть варианты ответов (Pathway, Oprosso, CloudSurvey, Survstat) — это точно опрос, а не инфо-экран!
    if (active.querySelectorAll(
        '.choice__option, .choice, [class*="choice__option"], .question_type_choice, ' +
        '[data-testid*="choice.option"], [data-testid*="respondent.choice.option"], ' +
        'button.option__QmiJR, [class*="option__QmiJR"], [class*="Answer_wrapper"], [class*="choice-item"], .answer-item'
    ).length >= 2) {
        return null;
    }

    // Если есть реальные радиокнопки или чекбоксы (не скрытые) — это вопрос с выбором!
    let realOptions = Array.from(active.querySelectorAll('input[type="radio"], input[type="checkbox"], [role="radio"], [role="checkbox"]')).filter(el => {
        return el.getBoundingClientRect().height > 0 || (el.parentElement && el.parentElement.getBoundingClientRect().height > 0);
    });
    if (realOptions.length > 0) return null;

    let interactive = active.querySelectorAll(
        'input:not([type="submit"]):not([type="button"]):not([type="hidden"]), textarea, select, button, [role="radio"], [role="checkbox"], [role="button"], .answer-item, .scale-item, div[class*="Answer"], li.choice-item, label.option-label, .LogoItem, div[class*="scale-answer"], .select-wrap, div[class*="select-input"]'
    );

    let visibleInteractive = Array.from(interactive).filter(el => {
        if (el.getBoundingClientRect().height === 0) return false;
        if (el.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"], [class*="edgelables"]')) return false;

        // Игнорируем технические поля систем детекции браузера (mrIWeb / Dimensions)
        if (el.classList.contains('detect-browser__input') || (el.name && el.name.includes('inf0')) || el.readOnly) return false;

        // Игнорируем кнопки навигации
        if (el.getAttribute('name') === '_NNext' || el.classList.contains('mrNext') || el.closest('.question-card__navigation, #buttons')) return false;

        let txt = (el.innerText || el.value || '').trim().toLowerCase();
        let navKws = ['далее', 'вперед', 'продолжить', 'начать', 'старт', 'понятно', 'согласен', 'принимаю'];
        if (navKws.some(kw => txt === kw || txt.includes(kw))) return false;

        return true;
    });

    if (visibleInteractive.length > 0) return null;

    let textNodes = Array.from(active.querySelectorAll('h1, h2, h3, h4, p, div, span, b, strong'))
        .filter(el => el.getBoundingClientRect().height > 0)
        .map(el => (el.innerText || '').trim())
        .filter(t => t.length > 4);

    let unique = [...new Set(textNodes)].filter(t =>
        !['далее', 'вперед', 'продолжить', 'время опросов', 'пожалуйста'].some(w => t.toLowerCase() === w)
    );

    return unique.length > 0 ? unique.join('\\n') : null;
}"""

# ==========================================
# 4. ПРОГРЕССИВНЫЕ БЛОКИ (МАТРИЦЫ/ЛЕНТЫ)
# ==========================================

JS_HANDLE_PROGRESSIVE_BLOCKS = """() => {
    let active = document.querySelector('.step.active') || document.body;

    let blockSelector = [
        'div[class*="questionrouter-container"]', 'div[class*="QuestionContainerStyled"]',
        'div[class*="styled__BlockStyled"]', 'div[class*="styled_BlockStyled"]',
        'div[class*="blk-answer-block"]', 'div[class*="QuestionBlock"]',
        'div[class*="question-block"]', 'div[class*="CellContainer"]',
        'div.holder-block', 'div[id*="demo-b"]', 'div[id*="matrix-b"]'
    ].join(', ');

    let candidateCards = Array.from(active.querySelectorAll(blockSelector)).filter(el => {
        if (el.getBoundingClientRect().height === 0) return false;
        let cls = (el.className || '').toLowerCase();
        if (cls.includes('edgelabel') || cls.includes('labelsstyled') || cls.includes('edge-label')) return false;

        return el.querySelectorAll(
            'div[class*="scale-item"], div[class*="scale-answer-content"], div[class*="AnswerStyled"], li.choice-item, .answer-item, .scale-item, label.option-label, .LogoItem, input[type="text"]:not([placeholder*="списка"]):not([placeholder*="город"]), input[type="number"], input[inputmode="numeric"], textarea'
        ).length > 0;
    });

    let questionBlocks = candidateCards.filter(c => !candidateCards.some(other => other !== c && c.contains(other)));

    if (questionBlocks.length === 0) return null;

    questionBlocks.forEach((b, i) => b.setAttribute('data-dyn-id', String(i)));

    for (let idx = 0; idx < questionBlocks.length; idx++) {
        let blk = questionBlocks[idx];
        let isMarked = blk.getAttribute('data-bot-answered') === 'true';

        let itemSelector = [
            'div[class*="scale-answer-content"]', 'div[class*="scale-item"]',
            'div[class*="styled__AnswerStyled"]', 'div[class*="styled_AnswerStyled"]',
            'div[class*="AnswerRow"]', 'li.choice-item', 'div.choice-item',
            'div[class*="LogoItem"]', 'label.option-label', '.answer-item',
            '.scale-item', '.LogoItem'
        ].join(', ');

        let candidates = Array.from(blk.querySelectorAll(itemSelector)).filter(n => {
            if (n.getBoundingClientRect().height === 0) return false;
            let style = window.getComputedStyle(n);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
            if (n.className.includes('btn') && !n.className.includes('scale')) return false;
            if (n.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"], [class*="edgelables"]')) return false;
            return true;
        });

        let leafItems = candidates.filter(c => !candidates.some(other => other !== c && c.contains(other)));

        let textInput = blk.querySelector('textarea, input[type="text"]:not([placeholder*="списка"]):not([placeholder*="город"]), input[type="number"], input[inputmode="numeric"]');
        if (textInput && (textInput.id.includes('_other') || textInput.name.includes('_other'))) textInput = null;

        let hasTextInput = textInput !== null && textInput.getBoundingClientRect().height > 0;
        let isAnswered = isMarked;

        if (!isAnswered) {
            if (blk.querySelector('input:checked') !== null || blk.querySelector('[aria-checked="true"]') !== null || blk.querySelector('[data-selected="true"]') !== null) {
                isAnswered = true;
            }
            if (!isAnswered) {
                for (let it of leafItems) {
                    let cls = (it.className || '').toLowerCase();
                    let parentCls = (it.parentElement?.className || '').toLowerCase();
                    let grandCls = (it.parentElement?.parentElement?.className || '').toLowerCase();

                    let hasSel = (c) => c.includes('selected') || c.includes('checked') || c.includes('answer-active') || c.includes('active-item');
                    let isSelected = hasSel(cls) || hasSel(parentCls);

                    if (!grandCls.includes('step') && hasSel(grandCls)) {
                        isSelected = true;
                    }
                    if (isSelected) {
                        isAnswered = true;
                        break;
                    }
                }
            }
            if (hasTextInput && textInput && textInput.value && textInput.value.trim().length > 0) {
                isAnswered = true;
            }
        }

        if (!isAnswered) {
            let mainHeaderEl = Array.from(active.querySelectorAll('h1, h2, h3, h4, .question-text, div[class*="question-header"], div[class*="HeaderStyled"], .page-header .header')).find(h => {
                if (h.getBoundingClientRect().height === 0) return false;
                return !h.closest(blockSelector);
            });
            let mainHeader = mainHeaderEl ? (mainHeaderEl.innerText || '').trim() : '';

            let titleEl = Array.from(blk.querySelectorAll(
                'div[class*="question-content"], div[class*="question-header"], div[class*="Header"], div[class*="title"], div[class*="question-text"], .question-text, div[style*="font-weight"], h1, h2, h3, h4, p, b, strong'
            )).find(t => {
                if (t.closest(itemSelector) || t.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"]')) return false;
                let txt = (t.innerText || '').trim();
                return txt.length > 2 && !txt.toLowerCase().includes('пожалуйста') && !txt.toLowerCase().includes('оцените по шкале');
            });
            let blockTitle = titleEl ? (titleEl.innerText || '').trim() : '';

            let finalQ = '';
            if (mainHeader && blockTitle && mainHeader !== blockTitle) {
                finalQ = `${mainHeader} -> ${blockTitle}`;
            } else {
                finalQ = blockTitle || mainHeader || `Вопрос ${idx + 1}`;
            }

            let options = leafItems.map(i => {
                let directText = (i.innerText || '').trim();
                let cleanDirect = directText.replace(/^\\d+[\\.\\)\\-]\\s*/, '').trim();

                let attrCandidate = '';
                for (let el of [i, ...i.querySelectorAll('*')]) {
                    let val = el.getAttribute('data-name') || el.getAttribute('data-title') || el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('data-template') || '';
                    val = val.trim();
                    if (val.length > 1 && !/^[0-9a-f]{1,4}$/i.test(val) && !val.toLowerCase().startsWith('http')) {
                        attrCandidate = val;
                        break;
                    }
                }
                if (attrCandidate) return attrCandidate;
                if (cleanDirect.length > 0) return cleanDirect;
                return directText || 'Вариант';
            });

            let isMulti = blk.querySelector('input[type="checkbox"], li[data-question-type="CheckBox"]') !== null || (blk.innerText || '').toLowerCase().includes('все подходящие');

            return {
                dynId: String(idx),
                questionText: finalQ,
                options: options,
                hasTextInput: hasTextInput,
                isMulti: isMulti
            };
        }
    }
    return {allAnswered: true};
}"""


JS_FILL_PROGRESSIVE_TEXT = """({dynId, text}) => {
    let active = document.querySelector('.step.active') || document.body;
    let blk = active.getAttribute('data-dyn-id') === String(dynId) ? active : active.querySelector(`[data-dyn-id="${dynId}"]`);
    if (blk) {
        let inp = blk.querySelector('textarea, input[type="text"], input[type="number"], input[inputmode="numeric"]');
        if (inp) {
            inp.focus();
            let type = (inp.getAttribute('type') || '').toLowerCase();
            let mode = (inp.getAttribute('inputmode') || '').toLowerCase();
            if (type === 'number' || mode === 'numeric') {
                text = text.replace(/\\D/g, '');
                if (!text) text = "21";
            }
            inp.value = text;
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
        }
        blk.setAttribute('data-bot-answered', 'true');
    }
}"""


JS_SELECT_PROGRESSIVE_CHOICE = """({dynId, optIdx}) => {
    let active = document.querySelector('.step.active') || document.body;
    let blk = active.getAttribute('data-dyn-id') === String(dynId) ? active : active.querySelector(`[data-dyn-id="${dynId}"]`);
    if (blk) {
        let itemSelector = [
            'div[class*="scale-answer-content"]', 'div[class*="scale-item"]',
            'div[class*="styled__AnswerStyled"]', 'div[class*="styled_AnswerStyled"]',
            'div[class*="AnswerRow"]', 'li.choice-item', 'div.choice-item',
            'div[class*="LogoItem"]', 'label.option-label', '.answer-item',
            '.scale-item', '.LogoItem'
        ].join(', ');

        let candidates = Array.from(blk.querySelectorAll(itemSelector)).filter(n => {
            if (n.getBoundingClientRect().height === 0) return false;
            let style = window.getComputedStyle(n);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
            if (n.className.includes('btn') && !n.className.includes('scale')) return false;
            if (n.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"], [class*="edgelables"]')) return false;
            return true;
        });

        let leafItems = candidates.filter(c => !candidates.some(other => other !== c && c.contains(other)));

        if (leafItems[optIdx]) {
            let target = leafItems[optIdx];
            let clickTarget = target.querySelector('input, div[class*="ContentContainer"], div[class*="contentOnlyAnswer"], div[class*="scale-answer-content"], span, label, div.circle, div.radiobox, div.checkbox') || target;

            clickTarget.scrollIntoView({behavior: 'smooth', block: 'center'});

            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                clickTarget.dispatchEvent(new MouseEvent(evt, {
                    bubbles: true,
                    cancelable: true,
                    view: window
                }));
            });

            if (target !== clickTarget) {
                target.dispatchEvent(new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true,
                    view: window
                }));
            }

            if (clickTarget.click) clickTarget.click();

            target.classList.add('selected');
            let inp = target.querySelector('input');
            if (inp) {
                inp.checked = true;
                inp.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }
        blk.setAttribute('data-bot-answered', 'true');
    }
}"""


# ==========================================
# 5. ANKETOLOG (Анкетолог)
# ==========================================
JS_ANKETOLOG_PROCESS_STEP = """() => {
    document.querySelectorAll('[data-bot-active-q]').forEach(e => e.removeAttribute('data-bot-active-q'));
    document.querySelectorAll('[data-bot-target]').forEach(e => e.removeAttribute('data-bot-target'));

    let qBlocks = Array.from(document.querySelectorAll('.question, .question__wrapper, .survey-question, .form-group'));
    if (qBlocks.length === 0) {
        let fallback = document.querySelector('.step.active, .questions-wrapper, .questions');
        qBlocks = fallback ? [fallback] : [document.body];
    }

    for (let block of qBlocks) {
        let titleEl = block.querySelector('.question-title, .question__title, h1, h2, h3, .title');
        let qText = titleEl ? titleEl.textContent.trim().replace(/\\*$/, '').replace(/\\s+/g, ' ').trim() : "Без заголовка";

        // 1.1 Новые матрицы Vue.js (.matrix)
        let vueMatrix = block.querySelector('.matrix');
        if (vueMatrix) {
            let colHeaders = Array.from(vueMatrix.querySelectorAll('.matrix__block--header .matrix__cell')).map(c => c.innerText.replace(/\\s+/g, ' ').trim());
            let rowTitles = Array.from(vueMatrix.querySelectorAll('.matrix__block--left .matrix__cell')).map(c => c.innerText.replace(/\\s+/g, ' ').trim());
            let inputRows = Array.from(vueMatrix.querySelectorAll('.matrix__block--main .matrix__row'));

            if (inputRows.length > 0) {
                for (let i = 0; i < inputRows.length; i++) {
                    let row = inputRows[i];
                    let inputs = Array.from(row.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                    let isAnswered = inputs.some(inp => inp.checked || (inp.className || '').includes('--active'));
                    let isHandled = row.hasAttribute('data-bot-handled');

                    if (!isAnswered && !isHandled) {
                        row.setAttribute('data-bot-handled', 'true');
                        row.setAttribute('data-bot-active-q', 'true');

                        let opts = inputs.map((inp, idx) => colHeaders[idx] || `Колонка ${idx + 1}`);
                        let rTitle = rowTitles[i] || `Строка ${i + 1}`;
                        let finalQText = qText + " — " + rTitle;

                        return {
                            targetType: 'choices', 
                            questionText: finalQText, 
                            options: opts, 
                            isMulti: inputs.some(inp => inp.type === 'checkbox')
                        };
                    }
                }
            }
        }

        // 1.2 Старые матрицы
        let matrixRows = Array.from(block.querySelectorAll('tr, .question__matrix-row')).filter(r => r.querySelectorAll('input[type="radio"], input[type="checkbox"]').length > 1);
        if (matrixRows.length > 0) {
            let unansRow = matrixRows.find(r => !Array.from(r.querySelectorAll('input')).some(i => i.checked) && !r.hasAttribute('data-bot-handled'));
            if (unansRow) {
                unansRow.setAttribute('data-bot-handled', 'true');
                unansRow.setAttribute('data-bot-active-q', 'true');

                let rowTitleEl = unansRow.querySelector('th, .row-title, .question__matrix-row-title, td:first-child');
                let rowTitle = (rowTitleEl && !rowTitleEl.querySelector('input')) ? rowTitleEl.textContent.replace(/\\s+/g, ' ').trim() : "";

                let opts = Array.from(unansRow.querySelectorAll('input')).map(inp => {
                    let cell = inp.closest('td, .question__matrix-cell') || inp.parentElement;
                    let span = cell.querySelector('.question-table__item-label-text, .text, span');
                    let val = span ? span.textContent.replace(/\\s+/g, ' ').trim() : cell.textContent.replace(/\\s+/g, ' ').trim();
                    if (!val || (val === inp.value && val.length > 4)) return "";
                    return val;
                });

                if (opts.some(o => o === "")) {
                    let table = unansRow.closest('table, .question__matrix');
                    if (table) {
                        let headers = Array.from(table.querySelectorAll('thead th, thead td, .question__matrix-col-title')).map(h => h.textContent.replace(/\\s+/g, ' ').trim()).filter(h => h);
                        if (headers.length > 0) {
                            let offset = Math.max(0, headers.length - opts.length);
                            opts = opts.map((o, i) => o || headers[i + offset] || `Вариант ${i+1}`);
                        }
                    }
                }

                opts = opts.map((o, i) => o || Array.from(unansRow.querySelectorAll('input'))[i].value || `Вариант ${i+1}`);
                let finalQText = rowTitle ? qText + " — " + rowTitle : qText;
                return {targetType: 'choices', questionText: finalQText, options: opts, isMulti: unansRow.querySelector('input[type="checkbox"]') !== null};
            }
        }

        // 2. ВЫПАДАЮЩИЕ СПИСКИ
        let selects = Array.from(block.querySelectorAll('select')).filter(s => {
            if (s.hasAttribute('data-bot-handled')) return false;
            let hasError = s.classList.contains('error') || s.closest('.has-error') !== null;
            if (s.value !== '' && !hasError) return false;
            return s.offsetParent !== null || s.closest('.survey-select-widget') !== null;
        });

        if (selects.length > 0) {
            selects[0].setAttribute('data-bot-handled', 'true');
            selects[0].setAttribute('data-bot-active-q', 'true');
            selects[0].setAttribute('data-is-select', 'true');
            let opts = Array.from(selects[0].querySelectorAll('option')).filter(o => o.value && o.innerText.trim() !== '').map(o => o.innerText.trim());
            return {targetType: 'choices', questionText: qText, options: opts, isMulti: selects[0].multiple};
        }

        // 3. ОТКРЫТЫЕ ВОПРОСЫ И СПИСКИ ВВОДА
        let textInputs = Array.from(block.querySelectorAll('textarea, input[type="text"]:not([readonly]), input[type="number"], input[type="email"], input[type="tel"], input:not([type])')).filter(i => {
            if (i.offsetParent === null) return false;
            if (i.hasAttribute('data-bot-handled')) return false;

            // ЖЕСТКИЙ ИЗОЛЯТОР: Игнорируем текстовые поля, если они привязаны к варианту ответа (например, "Другое")
            let p = i.parentElement;
            let isChoice = false;
            while (p && p.tagName !== 'BODY') {
                let cls = (p.className || '').toLowerCase();
                // Если мы поднялись до уровня всего вопроса - прекращаем поиск, чтобы не задеть соседние элементы
                if (cls === 'question' || cls === 'question__wrapper' || cls === 'survey-question' || cls === 'form-group') break;

                if (p.querySelector('input[type="radio"], input[type="checkbox"]')) {
                    isChoice = true; break;
                }
                if (cls.includes('choice') || cls.includes('radio') || cls.includes('checkbox') || cls.includes('answer-item')) {
                    isChoice = true; break;
                }
                p = p.parentElement;
            }
            if (isChoice) return false;

            let isEmpty = i.value.trim() === '' || /^[_\\-\\.\\s\\/]+$/.test(i.value);
            let hasError = i.classList.contains('error') || i.closest('.has-error') !== null;
            return isEmpty || hasError;
        });

        if (textInputs.length > 0) {
            // ГРУППИРОВКА: Помечаем ВСЕ текстовые поля в этом блоке как обработанные,
            // но командуем боту заполнить только первое поле из списка.
            textInputs.forEach(i => i.setAttribute('data-bot-handled', 'true'));
            textInputs[0].setAttribute('data-bot-target', 'true');
            return {targetType: 'text', questionText: qText, options: []};
        }

        // 4. ОБЫЧНЫЕ ВАРИАНТЫ И NPS ШКАЛЫ
        let inputs = Array.from(block.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
        let choiceRows = inputs.map(i => i.closest('.question__elementWrapper, .question__element-wrapper, .question-list__item, .answer-item, .question-table__item, label') || i.parentElement);

        let npsItems = Array.from(block.querySelectorAll('.substrate__item'));
        choiceRows = choiceRows.concat(npsItems);

        choiceRows = [...new Set(choiceRows)].filter(r => r && r.getBoundingClientRect().height > 0);

        if (choiceRows.length > 0) {
            let isAnswered = choiceRows.some(r => {
                let inp = r.querySelector('input[type="radio"], input[type="checkbox"]');
                if (inp && (inp.checked || (inp.className || '').includes('--active'))) return true;
                if (r.classList.contains('substrate__item') && (r.classList.contains('active') || r.classList.contains('selected') || r.querySelector('.active, .selected, [class*="--active"]'))) return true;
                return false;
            });

            if (!isAnswered && !block.hasAttribute('data-bot-handled-choices')) {
                block.setAttribute('data-bot-handled-choices', 'true');
                block.setAttribute('data-bot-active-q', 'true');
                let isMulti = choiceRows.some(r => r.querySelector('input[type="checkbox"]') !== null);

                let options = choiceRows.map((r, i) => {
                    let tEl = r.querySelector('.question__element-text, .text, span, label, .substrate__item-decor');
                    let text = tEl ? tEl.textContent.trim() : r.textContent.trim();

                    if (!text || text.length < 2) {
                        let img = r.querySelector('img');
                        if (img && img.alt && img.alt !== 'image') text = `[Картинка: ${img.alt}]`;
                        else if (img && img.src) text = `[Картинка: ${img.src.split('/').pop()}]`;
                    }

                    return text.replace(/\\s+/g, ' ') || `Вариант ${i + 1}`;
                });
                return {targetType: 'choices', questionText: qText, options: options, isMulti: isMulti};
            }
        }
    }

    let finishTextEl = document.querySelector('.survey-html-question p, .survey-finish-text');
    let globalTitle = finishTextEl ? finishTextEl.textContent.trim() : "Все поля на странице заполнены. Ожидание перехода...";
    return {targetType: 'done_or_info', questionText: globalTitle, options: []};
}"""

JS_ANKETOLOG_FILL_TEXT = """async (text) => {
    let inp = document.querySelector('textarea[data-bot-target="true"], input[data-bot-target="true"]');
    if (!inp) return;

    if (inp.classList.contains('datetimepicker') || (inp.placeholder && inp.placeholder.includes('дату'))) {
        let dMatch = text.match(/(\\d{2})\\.(\\d{2})\\.(\\d{4})/);
        if (dMatch) text = `${dMatch[3]}-${dMatch[2]}-${dMatch[1]}`;
    }

    inp.focus(); 
    inp.value = text;
    let tracker = inp._valueTracker;
    if (tracker) tracker.setValue('');

    inp.dispatchEvent(new Event('input', {bubbles: true}));
    inp.dispatchEvent(new Event('change', {bubbles: true}));
    inp.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, key: 'a', keyCode: 65}));
    inp.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, key: 'a', keyCode: 65}));

    if (typeof jQuery !== 'undefined') {
        jQuery(inp).val(text).trigger('input').trigger('change').trigger('keyup');
    }

    for (let i = 0; i < 15; i++) {
        await new Promise(r => setTimeout(r, 100));
        let typeahead = document.querySelector('.typeahead.dropdown-menu');
        if (typeahead && typeahead.style.display !== 'none') {
            let firstOption = typeahead.querySelector('li a');
            if (firstOption) {
                ['mousedown', 'mouseup', 'click'].forEach(e => firstOption.dispatchEvent(new MouseEvent(e, {bubbles:true})));
                break;
            }
        }
    }

    let datepicker = document.querySelector('.bootstrap-datetimepicker-widget');
    if (datepicker) {
        datepicker.style.display = 'none';
        document.body.click(); 
    }
    inp.removeAttribute('data-bot-target');
}"""

JS_ANKETOLOG_CLEAR_TEXT_TARGET = """() => {
    let inp = document.querySelector('textarea[data-bot-target="true"], input[data-bot-target="true"]');
    if (inp) inp.removeAttribute('data-bot-target');
}"""

JS_ANKETOLOG_SELECT_CHOICE = """(idx) => {
    let active = document.querySelector('[data-bot-active-q="true"]');
    if (!active) return;

    if (active.hasAttribute('data-is-select')) {
        let sel = active;
        let opts = Array.from(sel.querySelectorAll('option')).filter(o => o.value && o.innerText.trim() !== '');
        if (opts[idx]) {
            sel.value = opts[idx].value;
            sel.dispatchEvent(new Event('input', {bubbles: true}));
            sel.dispatchEvent(new Event('change', {bubbles: true}));
            if (typeof jQuery !== 'undefined') jQuery(sel).val(opts[idx].value).trigger('change');
        }
        return;
    }

    if (active.classList.contains('matrix__row')) {
        let inputs = Array.from(active.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
        if (inputs[idx]) {
            let clickable = inputs[idx].closest('.matrix__cell-input, .matrix__cell, label') || inputs[idx];
            clickable.setAttribute('data-bot-click-target', 'true');
        }
        return;
    }

    let inputs = Array.from(active.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
    let targetInput = null;
    let textInp = null;
    let npsTarget = null;

    if (active.tagName === 'TR' || active.classList.contains('question__matrix-row')) {
        if (inputs[idx]) {
            targetInput = inputs[idx];
        }
    } else {
        let rows = inputs.map(i => i.closest('.question__elementWrapper, .question__element-wrapper, .question-list__item, .answer-item, .question-table__item, label') || i.parentElement);
        let npsItems = Array.from(active.querySelectorAll('.substrate__item'));
        rows = rows.concat(npsItems);
        rows = [...new Set(rows)].filter(r => r && r.getBoundingClientRect().height > 0);

        if (rows[idx]) {
            targetInput = rows[idx].querySelector('input[type="radio"], input[type="checkbox"]');
            textInp = rows[idx].querySelector('input[type="text"]');
            if (rows[idx].classList.contains('substrate__item')) npsTarget = rows[idx];
        }
    }

    if (targetInput) {
        let clickableContainer = targetInput.closest('.question__element, .question__element-wrapper, .question-table__item, .answer-item, label') || targetInput;
        let customMark = clickableContainer.querySelector('.question__element-custom, .checkbox-check, .radio-check');
        let finalTarget = customMark || clickableContainer;

        finalTarget.setAttribute('data-bot-click-target', 'true');

        if (textInp) {
            textInp.value = "Свой вариант";
            textInp.dispatchEvent(new Event('input', {bubbles: true}));
            textInp.dispatchEvent(new Event('change', {bubbles: true}));
        }
    } else if (npsTarget) {
        npsTarget.setAttribute('data-bot-click-target', 'true');
    }
}"""


# ==========================================
# 6. PROFIRESEARCH
# ==========================================
JS_PROFIRESEARCH_FAST_CITY = """(city) => {
    let fastLinks = Array.from(document.querySelectorAll('.pr-geo-fastoptions span, .pr-geo-fastoptions a, .pr-elem'));
    let target = fastLinks.find(el => el.innerText.trim().toLowerCase() === city.toLowerCase());
    if (target) {
        target.scrollIntoView({behavior: 'smooth', block: 'center'});
        target.click(); return true;
    }
    return false;
}"""
JS_PROFIRESEARCH_CHECK_CITY_Q = """() => {
    let qEl = document.querySelector('pr-question-title, .pr-question-title, h-block, h1, h2, h3, .question-text');
    let txt = qEl ? qEl.innerText.toLowerCase() : '';
    let hasCityEl = document.querySelector('.pr-city, input[placeholder*="город"], .selectize-control') !== null;
    return (txt.includes('город') || txt.includes('проживаете') || txt.includes('живете')) && hasCityEl;
}"""
JS_PROFIRESEARCH_PROCESS_STEP = """() => {
    function getClosestTitle(el) {
        let qContainer = el.closest('form.pr-question, div.pr-question, .pr-question-main');
        if (qContainer) {
            let titleEl = qContainer.querySelector('pr-question-title, h-block');
            if (titleEl) return titleEl.innerText.trim();
        }
        let allTitles = Array.from(document.querySelectorAll('pr-question-title, .pr-question-title, h-block, h1, h2, h3, .question-text'));
        for (let i = allTitles.length - 1; i >= 0; i--) {
            if (allTitles[i].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) {
                let text = allTitles[i].innerText.trim(); let lower = text.toLowerCase();
                if (text.length > 2 && !lower.includes('оцените по шкале') && !lower.includes('выберите один') && !lower.includes('выберите все') && !lower.includes('подходящие ответы') && !lower.includes('введите текст')) {
                    return text;
                }
            }
        }
        let fallback = document.querySelector('pr-question-title, h-block, .question-text');
        return fallback ? fallback.innerText.trim() : '';
    }

    let textInputs = Array.from(document.querySelectorAll('textarea, input[type="text"]:not([readonly]), input[type="number"], input[type="email"], input[type="tel"]')).filter(i => {
        if (i.value.trim() !== '') return false;
        if (i.offsetParent === null && !i.closest('.selectize-input')) return false;
        let row = i.closest('tr.pr-row, .pr-row');
        if (row && row.querySelector('input[type="radio"], input[type="checkbox"]')) return false;
        return true;
    });

    if (textInputs.length > 0) {
        let inp = textInputs[0]; inp.setAttribute('data-bot-target', 'true');
        let qText = getClosestTitle(inp); let subTitle = '';
        let row = inp.closest('tr.pr-row');
        if (row) {
            let tEl = row.querySelector('pr-row-title, .pr-cell-head, label');
            if (tEl) subTitle = tEl.innerText.trim();
        } else if (inp.parentElement) {
            let clone = inp.parentElement.cloneNode(true);
            let inps = clone.querySelectorAll('input, textarea, select');
            inps.forEach(e => e.remove()); subTitle = clone.innerText.trim();
        }
        let finalQ = qText;
        if (subTitle && subTitle.length > 0 && subTitle.length < 50 && subTitle !== qText) finalQ = `${qText} -> ${subTitle}`;
        return {targetType: 'text', questionText: finalQ, options: []};
    }

    let selects = Array.from(document.querySelectorAll('select')).filter(s => {
        if (s.disabled) return false;
        let isSelectize = s.classList.contains('selectized') || (s.nextElementSibling && s.nextElementSibling.classList.contains('selectize-control'));
        if (s.offsetParent === null && !isSelectize) return false;
        let val = s.value;
        let text = s.options[s.selectedIndex] ? s.options[s.selectedIndex].innerText.trim() : '';
        return !val || val === '0' || text === '' || text.toLowerCase().includes('выбер') || text.includes('---') || text.toLowerCase().includes('начните вводить');
    });

    if (selects.length > 0) {
        let sel = selects[0]; sel.setAttribute('data-bot-target', 'true');
        let qText = getClosestTitle(sel);
        let rawOptions = Array.from(sel.querySelectorAll('option')).filter(o => {
            let t = o.innerText.trim(); let v = o.value;
            return t && v !== '0' && v !== '' && !t.toLowerCase().includes('выбер') && !t.includes('---') && !t.toLowerCase().includes('начните вводить');
        });
        let subTitle = '';
        let container = sel.closest('td, .pr-cell') || sel.parentElement;
        if (container && container.nextElementSibling) {
            subTitle = container.nextElementSibling.innerText.trim();
        } else if (sel.parentElement) {
            let clone = sel.parentElement.cloneNode(true);
            let inps = clone.querySelectorAll('input, textarea, select');
            inps.forEach(e => e.remove()); subTitle = clone.innerText.trim();
        }
        let finalQ = qText;
        if (subTitle && subTitle.length > 0 && subTitle.length < 50 && subTitle !== qText) finalQ = `${qText} -> ${subTitle}`;
        return {targetType: 'select', questionText: finalQ, options: rawOptions.map(o => o.innerText.trim())};
    }

    let choiceRows = Array.from(document.querySelectorAll('tr.pr-row')).filter(r => {
        if (r.offsetParent === null) return false;
        return r.querySelector('input[type="radio"], input[type="checkbox"]') !== null;
    });

    if (choiceRows.length > 0) {
        let isAnswered = choiceRows.some(r => {
            let inp = r.querySelector('input[type="radio"], input[type="checkbox"]');
            return inp && inp.checked;
        });
        if (!isAnswered) {
            let qText = getClosestTitle(choiceRows[0]);
            let isMulti = choiceRows.some(r => r.querySelector('input[type="checkbox"]') !== null);
            let options = choiceRows.map((r, i) => {
                let tEl = r.querySelector('pr-row-title, .pr-cell-head, label');
                return tEl ? tEl.innerText.trim() : `Вариант ${i + 1}`;
            });
            return {targetType: 'choices', questionText: qText, options: options, isMulti: isMulti};
        }
    }
    let fallback = document.querySelector('pr-question-title, .question-text');
    return {targetType: 'done_or_info', questionText: fallback ? fallback.innerText.trim() : '', options: []};
}"""
JS_PROFIRESEARCH_FILL_TEXT = """(text) => {
    let inp = document.querySelector('textarea[data-bot-target="true"], input[data-bot-target="true"]');
    if (inp) {
        inp.focus(); inp.value = text;
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        inp.dispatchEvent(new Event('change', {bubbles: true}));
        inp.removeAttribute('data-bot-target');
    }
}"""
JS_PROFIRESEARCH_CLEAR_TEXT_TARGET = """() => {
    let inp = document.querySelector('textarea[data-bot-target="true"], input[data-bot-target="true"]');
    if (inp) inp.removeAttribute('data-bot-target');
}"""
JS_PROFIRESEARCH_SELECT_DROPDOWN = """(optText) => {
    let sel = document.querySelector('select[data-bot-target="true"]');
    if (sel) {
        let options = Array.from(sel.querySelectorAll('option'));
        let targetOpt = options.find(o => {
            let oText = o.innerText.trim();
            return oText === optText || oText.includes(optText) || optText.includes(oText);
        });
        if (targetOpt) {
            sel.value = targetOpt.value;
            sel.dispatchEvent(new Event('change', {bubbles: true}));
            sel.dispatchEvent(new Event('input', {bubbles: true}));
            if (typeof window.jQuery !== 'undefined') {
                let $sel = window.jQuery(sel);
                if ($sel[0].selectize) { $sel[0].selectize.setValue(targetOpt.value); } 
                else { $sel.trigger('change'); }
            }
        }
        sel.removeAttribute('data-bot-target');
    }
}"""
JS_PROFIRESEARCH_CLEAR_SELECT_TARGET = """() => {
    let sel = document.querySelector('select[data-bot-target="true"]');
    if (sel) sel.removeAttribute('data-bot-target');
}"""
JS_PROFIRESEARCH_SELECT_CHOICE = """(idx) => {
    let rows = Array.from(document.querySelectorAll('tr.pr-row')).filter(r => r.offsetParent !== null && r.querySelector('input[type="radio"], input[type="checkbox"]'));
    if (rows[idx]) {
        let input = rows[idx].querySelector('input[type="radio"], input[type="checkbox"]');
        if (input) {
            input.scrollIntoView({behavior: 'smooth', block: 'center'});
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                input.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
            });
            input.checked = true;
            input.dispatchEvent(new Event('change', {bubbles: true}));
        } else {
            rows[idx].click();
        }
        let textInp = rows[idx].querySelector('input[type="text"]');
        if (textInp) {
            let label = rows[idx].querySelector('pr-row-title, .pr-cell-head, label');
            let val = label ? label.innerText.replace(/\\(.*\\)/g, '').trim() : "Свой вариант";
            textInp.value = val || "Другое";
            textInp.dispatchEvent(new Event('input', {bubbles: true}));
            textInp.dispatchEvent(new Event('change', {bubbles: true}));
        }
    }
}"""

# ==========================================
# 7. SAWTOOTH
# ==========================================
JS_SAWTOOTH_SELECT_SLIDER = """(idx) => {
    let slider = document.querySelector('[data-bot-active-q="true"]');
    if (!slider) return;

    // Переводим индекс ответа LLM (0-4) в проценты по шкале (0%, 25%, 50%, 75%, 100%)
    let percents = [0, 25, 50, 75, 100];
    let percent = percents[idx] !== undefined ? percents[idx] : 50;

    // Работаем через нативный jQuery UI, который использует Sawtooth
    if (window.jQuery && (jQuery(slider).data('slider') || jQuery(slider).hasClass('ui-slider'))) {
        let jqSlider = jQuery(slider);
        let min = jqSlider.slider("option", "min") || 1;
        let max = jqSlider.slider("option", "max") || 100;
        let val = Math.round(min + (max - min) * (percent / 100));

        // Двигаем значение
        jqSlider.slider("value", val);

        // ОБХОД АНТИФРОДА: Эмулируем физическое касание
        jqSlider.addClass('touched');

        // Обновляем скрытый инпут для отправки формы
        let hiddenInp = jqSlider.find('input[type="hidden"]');
        if (hiddenInp.length) {
            hiddenInp.val(val).trigger('change');
        }

        // Визуально сдвигаем бегунок, чтобы это было видно при отладке
        let handle = jqSlider.find('.ui-slider-handle');
        if (handle.length) {
            handle.css('left', percent + '%');
        }
    } else {
        // Резервный фолбэк
        slider.classList.add('touched');
    }
    slider.removeAttribute('data-bot-active-q');
}"""

JS_SAWTOOTH_PROCESS_STEP = """() => {
    function isVisible(el) {
        if (!el || el.nodeType !== 1) return false;
        let style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        let rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function getCleanText(el) {
        if (!el) return "";
        let clone = el.cloneNode(true);
        Array.from(clone.querySelectorAll('script, style')).forEach(s => s.remove());
        return (clone.innerText || clone.textContent || "").replace(/\\s+/g, ' ').trim();
    }

    document.querySelectorAll('[data-bot-active-q]').forEach(el => el.removeAttribute('data-bot-active-q'));
    document.querySelectorAll('[data-bot-target]').forEach(el => el.removeAttribute('data-bot-target'));
    document.querySelectorAll('[data-bot-target-select]').forEach(el => el.removeAttribute('data-bot-target-select'));

    let activeStep = document.querySelector('.step.active') || document.body;
    let qBlocks = Array.from(activeStep.querySelectorAll('div.question'));
    if (qBlocks.length === 0) qBlocks = [activeStep];

    for (let qBlock of qBlocks) {
        if (!isVisible(qBlock) && !qBlock.querySelector('.carouselBlock')) continue;

        let headerEls = Array.from(qBlock.querySelectorAll('.header1, .header2, .question_text'));
        let qText = headerEls.map(getCleanText).filter(Boolean).join(' ') || document.title || "Вопрос";

        // 1. Текстовые поля
        let textInputs = Array.from(qBlock.querySelectorAll('input[type="text"]:not([readonly]), input[type="number"], input[type="tel"], textarea')).filter(i => {
            if (!isVisible(i)) return false;
            let idStr = i.id || ""; let nameStr = i.name || "";
            if (idStr.includes('_other') || nameStr.includes('_other')) return false;
            return i.value.trim() === '';
        });

        if (textInputs.length > 0) {
            textInputs[0].setAttribute('data-bot-target', 'true');
            return {targetType: 'text', questionText: qText, options: []};
        }

        // 2. ВОССТАНОВЛЕННЫЙ БЛОК: Выпадающие списки (Select)
        let selectEl = Array.from(qBlock.querySelectorAll('select')).find(s => {
            if (!isVisible(s) || s.disabled) return false;
            let selectedOpts = Array.from(s.selectedOptions).filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'));
            if (selectedOpts.length > 0) return false;
            let opts = Array.from(s.options).filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'));
            return opts.length > 0;
        });

        if (selectEl) {
            let options = Array.from(selectEl.options)
                .filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'))
                .map(o => getCleanText(o));
            if (options.length > 0) {
                selectEl.setAttribute('data-bot-target-select', 'true');
                return {targetType: 'select', questionText: qText, options: options, isMulti: selectEl.multiple};
            }
        }
        
        // 2.5 Ползунки (СЕМАНТИЧЕСКИЙ ДИФФЕРЕНЦИАЛ)
        let sliders = Array.from(qBlock.querySelectorAll('.slider_control:not(.touched), .ui-slider:not(.touched)'));
        if (sliders.length > 0) {
            let slider = sliders[0]; // Берем первый нетронутый ползунок на странице
            let row = slider.closest('.slider-row, tr, table');
            
            // Вытаскиваем полюса (например, "Острый" и "Безопасный")
            let leftLabel = getCleanText(row.querySelector('.left_label_cell')) || "Левый край";
            let rightLabel = getCleanText(row.querySelector('.right_label_cell')) || "Правый край";

            let qTextSlider = qText + ` (Оцените от 1 до 5, где 1 - ${leftLabel}, а 5 - ${rightLabel})`;

            slider.setAttribute('data-bot-active-q', 'true');
            return {
                targetType: 'slider',
                questionText: qTextSlider,
                options: ["1 (Ближе к левому краю)", "2", "3 (Нейтрально)", "4", "5 (Ближе к правому краю)"],
                isMulti: false
            };
        }

        // 3. Матрицы и карусели
        let gridRows = Array.from(qBlock.querySelectorAll('tr[id$="_row"]'));
        if (gridRows.length > 0) {
            for (let row of gridRows) {
                let inputs = Array.from(row.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                if (inputs.length === 0 || inputs.some(i => i.checked)) continue;

                let rowLabel = getCleanText(row.querySelector('.row_label_cell')) || "Строка";
                let colHeaders = Array.from(row.closest('table').querySelectorAll('.col_label_cell')).map(getCleanText);
                let options = inputs.map((inp, i) => colHeaders[i] || `Вариант ${i + 1}`);

                row.setAttribute('data-bot-active-q', 'true');
                return { targetType: 'choices', questionText: qText + " — " + rowLabel, options: options, isMulti: inputs.some(i => i.type === 'checkbox') };
            }
        }

        // 4. Обычные чекбоксы и радиокнопки
        let inputs = Array.from(qBlock.querySelectorAll('.question_body input[type="radio"], .question_body input[type="checkbox"], input[type="radio"], input[type="checkbox"]'));
        let choiceInputs = inputs.filter(inp => {
            let n = inp.name || ""; let i = inp.id || "";
            return !n.startsWith('sys_') && !n.startsWith('hid_') && !i.includes('_other') && !n.includes('_other');
        });

        if (choiceInputs.length > 0) {
            let isAnswered = choiceInputs.some(inp => inp.checked);
            if (!isAnswered) {
                let isMulti = choiceInputs.some(inp => inp.type === 'checkbox');
                let options = choiceInputs.map((inp, i) => {
                    let text = "";
                    let label = (inp.labels && inp.labels.length > 0) ? inp.labels[0] : null;
                    if (label) text = getCleanText(label);
                    if (!text) {
                        let row = inp.closest('.clickable, .response_row, td, tr');
                        if (row) text = getCleanText(row);
                    }
                    if (!text || text.length < 2) {
                        let img = (label || inp.closest('td, div')).querySelector('img');
                        if (img && img.alt) text = `[Картинка: ${img.alt}]`;
                        else if (img && img.src) text = `[Картинка: ${img.src.split('/').pop()}]`;
                    }
                    return text || `Вариант ${i + 1}`;
                });

                qBlock.setAttribute('data-bot-active-q', 'true');
                return {targetType: 'choices', questionText: qText, options: options, isMulti: isMulti};
            }
        }
    }

    // ДЕТЕКТОР ОШИБОК: проверяем, не выкинул ли сайт красную рамку с ошибкой
    let errorBox = document.querySelector('.error_messages:not(.HideElement), .page_error:not(.HideElement)');
    let hasError = false;
    let errorText = "";
    if (errorBox && isVisible(errorBox)) {
        hasError = true;
        errorText = getCleanText(errorBox);
    }

    let allHeaders = Array.from(activeStep.querySelectorAll('.header1, .header2')).map(getCleanText).filter(Boolean).join(' ');
    return {targetType: 'done_or_info', questionText: allHeaders, options: [], hasError: hasError, errorText: errorText};
}"""
JS_SAWTOOTH_FILL_TEXT = """(text) => {
    let inp = document.querySelector('[data-bot-target="true"]');
    if (inp) {
        inp.focus(); inp.value = text;
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        inp.dispatchEvent(new Event('change', {bubbles: true}));
        inp.removeAttribute('data-bot-target');
    }
}"""
JS_SAWTOOTH_CLEAR_TARGET = """() => {
    let inp = document.querySelector('[data-bot-target="true"]');
    if (inp) inp.removeAttribute('data-bot-target');
}"""
JS_SAWTOOTH_SELECT_DROPDOWN = """(idx) => {
    let sel = document.querySelector('select[data-bot-target-select="true"]');
    if (sel) {
        let opts = Array.from(sel.querySelectorAll('option')).filter(o => o.value && o.value !== '0' && !o.innerText.toLowerCase().includes('выбер'));
        if (opts[idx]) {
            sel.value = opts[idx].value;
            sel.dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) { window.jQuery(sel).trigger('change'); }
        }
        sel.removeAttribute('data-bot-target-select');
    }
}"""
JS_SAWTOOTH_SELECT_CHOICE = """(idx) => {
    let active = document.querySelector('[data-bot-active-q="true"]') || document.querySelector('.step.active') || document.body;
    let inputs = Array.from(active.querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(inp => {
        let n = inp.name || ""; let i = inp.id || "";
        return !n.startsWith('sys_') && !n.startsWith('hid_') && !i.includes('_other') && !n.includes('_other');
    });

    if (inputs[idx]) {
        let targetInput = inputs[idx];
        let val = targetInput.value;

        // 1. Принудительно переключаем скрытый инпут
        targetInput.checked = true;
        targetInput.dispatchEvent(new Event('change', {bubbles: true}));

        // 2. Кликаем по виджету карусели, если он есть на экране
        let carouselBtn = document.querySelector(`.carouselBlock[style*="display: block"] .scalebut[data-index="${val}"]`);
        if (carouselBtn && carouselBtn.offsetParent !== null) {
            carouselBtn.click();
        }

        // 3. Стандартный клик по label/графическому квадратику
        let targetId = targetInput.id || "";
        let graph = targetId ? document.getElementById(targetId + '_graphical') : null;
        let label = (targetInput.labels && targetInput.labels.length > 0) ? targetInput.labels[0] : null;

        if (graph && graph.offsetParent !== null) { graph.click(); }
        else if (label && label.offsetParent !== null) { label.click(); }
    }
}"""

# ==========================================
# 8. SURVEYSTUDIO
# ==========================================
JS_SURVEYSTUDIO_FALLBACK_NEXT_BTN = """() => {
    let kws = ['далее', 'вперед', 'продолжить', 'начать'];
    let candidates = Array.from(document.querySelectorAll('button, div, span, a, input[type="submit"], input[type="button"]')).filter(el => {
        if (el.offsetParent === null) return false;
        let style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        let txt = (el.innerText || el.value || '').trim().toLowerCase();
        if (txt.length === 0 || txt.length > 30) return false;
        if (txt.includes('нажмите') || txt.includes('пожалуйста') || txt.includes('чтобы') || txt.includes('инструкц')) return false;
        let isBtn = el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'INPUT' || (el.className || '').toLowerCase().includes('btn') || (el.className || '').toLowerCase().includes('button');
        let hasKw = kws.some(kw => txt === kw || txt.includes(kw));
        return isBtn && hasKw;
    });
    if (candidates.length > 0) {
        candidates.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
        return candidates[0];
    }
    return null;
}"""
JS_SURVEYSTUDIO_CHECK_MATRIX = """() => {
    let isMatrix = document.querySelector('#ssDesktopTable, .ss-desktop-table, .ss-table-body-container, .ss-answers-table-singlechoice, .ss-answers-table-multiplechoice') !== null;
    if (!isMatrix) return null;

    function isVisible(el) {
        if (!el) return false;
        let rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden' && window.getComputedStyle(el).display !== 'none';
    }

    let titles = Array.from(document.querySelectorAll('.question-text, .ss-question-title, h2, h3'));
    let visibleTitle = titles.find(isVisible);
    let qText = visibleTitle ? visibleTitle.innerText.trim() : 'Матричный вопрос';

    let bodyRows = Array.from(document.querySelectorAll('#ssDesktopTableBodyContainer .ss-table-row, .ss-table-body-container .ss-table-row, div.ss-table-row')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]'));
    let colHeaders = [];

    if (bodyRows.length > 0) {
        let firstRowInputs = Array.from(bodyRows[0].querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));
        let headerCells = Array.from(document.querySelectorAll('.ss-table-header .ss-table-cell, thead th, .ss-table-header > div, .ss-desktop-table-header th')).filter(isVisible);
        let validHeaders = headerCells.length >= firstRowInputs.length ? headerCells.slice(-firstRowInputs.length) : headerCells;

        colHeaders = firstRowInputs.map((inp, idx) => {
            let t = '';
            let label = document.querySelector(`label[for="${inp.id}"]`);
            if (label && isVisible(label)) t = label.innerText.replace(/\\s+/g, ' ').trim();
            if (!t) t = inp.getAttribute('data-title') || inp.getAttribute('title') || inp.getAttribute('aria-label') || '';
            if (!t && validHeaders[idx]) t = validHeaders[idx].innerText.replace(/\\s+/g, ' ').trim();
            if (t && t.length > 40) {
                let matchNum = t.match(/^[0-9\\.]+/);
                t = matchNum ? matchNum[0] + " (оценка)" : t.substring(0, 35) + "...";
            }
            return t && !t.includes('ОДИН ОТВЕТ') ? t : `Вариант ${idx + 1}`;
        });
    }

    let leftRows = Array.from(document.querySelectorAll('.ss-first-table-container .ss-table-row, .ss-first-table-container div[data-row-code], .ss-first-table-container td, tbody th')).filter(el => isVisible(el) && el.innerText.trim().length > 0);
    let rows = [];
    if (bodyRows.length > 0) {
        bodyRows.forEach((rEl, i) => {
            let rowInputs = Array.from(rEl.querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));
            if (rowInputs.length === 0) return;
            let isAnswered = rowInputs.some(inp => inp.checked);
            let titleEl = leftRows[i] || rEl.querySelector('.ss-table-row-title, .ss-row-title, td:first-child, .title, label');
            let title = titleEl ? titleEl.innerText.replace(/\\s+/g, ' ').trim() : `Строка ${i + 1}`;
            rows.push({
                rowIndex: i,
                title: title,
                isAnswered: isAnswered,
                inputsCount: rowInputs.length,
                isMulti: rEl.querySelector('input[type="checkbox"]') !== null
            });
        });
    }
    return {qText: qText, colHeaders: colHeaders, rows: rows};
}"""
JS_SURVEYSTUDIO_SELECT_MATRIX_CHOICE = """({rowIndex, colIdx}) => {
    function isVisible(el) {
        return el.getBoundingClientRect().height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
    }
    let bodyRows = Array.from(document.querySelectorAll('#ssDesktopTableBodyContainer .ss-table-row, .ss-table-body-container .ss-table-row, div.ss-table-row')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]'));
    if (bodyRows[rowIndex]) {
        let row = bodyRows[rowIndex];
        let inputs = Array.from(row.querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(inp => !inp.id.includes('_other') && !inp.name.includes('_other') && !inp.name.startsWith('sys_'));
        if (inputs[colIdx]) {
            let targetInput = inputs[colIdx];
            let clickable = targetInput.closest('label') || targetInput.closest('.pretty') || targetInput;
            clickable.scrollIntoView({behavior: 'smooth', block: 'center'});
            clickable.click();
            targetInput.checked = true;
            targetInput.dispatchEvent(new Event('change', {bubbles: true}));
        }
    }
}"""
JS_SURVEYSTUDIO_PROCESS_STEP = """() => {
    function isVisible(el) {
        if (!el) return false;
        let rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden' && window.getComputedStyle(el).display !== 'none';
    }

    let qText = "";
    let titles = Array.from(document.querySelectorAll('.question-text, .ss-question-title, h2, h3, h4, .header1, .header2'));
    for (let t of titles) {
        if (isVisible(t)) {
            qText = t.innerText.replace(/\\s+/g, ' ').trim();
            if (qText.length > 5) break;
        }
    }
    if (!qText) qText = document.title || "Неизвестный вопрос";

    let containerBlocks = Array.from(document.querySelectorAll('.question-content, .ss-answers, .step.active, form')).filter(isVisible);
    let container = containerBlocks.length > 0 ? containerBlocks[0] : document.body;

    let textInputs = Array.from(container.querySelectorAll('input[type="text"], input[type="number"], input[inputmode="numeric"], textarea')).filter(i => {
        if (!isVisible(i)) return false;
        if (i.id.includes('_other') || i.name.includes('_other')) return false;
        let parent = i.parentElement;
        for (let k = 0; k < 3; k++) {
            if (parent && parent.querySelector('input[type="radio"], input[type="checkbox"]')) return false;
            parent = parent.parentElement;
        }
        return i.value.trim() === '';
    });

    if (textInputs.length > 0) {
        textInputs[0].setAttribute('data-bot-target', 'true');
        return {targetType: 'text', questionText: qText, options: []};
    }

    let selectEl = Array.from(container.querySelectorAll('select')).find(s => {
        if (s.disabled) return false;
        let selectedOpts = Array.from(s.selectedOptions).filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'));
        if (selectedOpts.length > 0) return false;
        let opts = Array.from(s.options).filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'));
        return opts.length > 0;
    });

    if (selectEl) {
        let options = Array.from(selectEl.options)
            .filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'))
            .map(o => (o.innerText || o.textContent || '').replace(/\\s+/g, ' ').trim());
        if (options.length > 0) {
            selectEl.setAttribute('data-bot-target-select', 'true');
            return {targetType: 'select', questionText: qText, options: options, isMulti: selectEl.multiple};
        }
    }

    let choiceRows = Array.from(container.querySelectorAll('label, .grid__cell, tr, .ss-choice-item, .answer-item')).filter(r => {
        return isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]') !== null;
    });
    choiceRows = choiceRows.filter(r => !choiceRows.some(other => other !== r && other.contains(r)));

    if (choiceRows.length >= 2) {
        let isAnswered = choiceRows.some(r => {
            let inp = r.querySelector('input[type="radio"], input[type="checkbox"]');
            return inp && inp.checked;
        });

        if (!isAnswered) {
            let isMulti = choiceRows.some(r => r.querySelector('input[type="checkbox"]') !== null);
            let options = choiceRows.map((r, i) => {
                let t = r.innerText.replace(/\\s+/g, ' ').trim();

                if (!t || t.length < 2) {
                    let label = r.querySelector('label, span, div');
                    if (label) t = label.innerText.replace(/\\s+/g, ' ').trim();
                }

                // ===============================================
                // НОВАЯ ЛОГИКА ДЛЯ РАСПОЗНАВАНИЯ КАРТИНОК
                // ===============================================
                if (!t || t.length < 2) {
                    let img = r.querySelector('img');
                    if (img) {
                        let altText = img.getAttribute('alt');
                        if (altText && altText.trim() !== '' && altText !== 'image') {
                            t = `[Картинка: ${altText}]`;
                        } else if (img.src) {
                            t = `[Картинка: ${img.src.split('/').pop()}]`; // Берем имя файла из ссылки
                        }
                    }
                }
                // ===============================================

                let inpField = r.querySelector('input[type="text"]');
                if (inpField) {
                    t = "Свой вариант" + (inpField.placeholder ? ": " + inpField.placeholder : "");
                }
                return t || `Вариант ответа ${i + 1}`;
            });
            return {targetType: 'choices', questionText: qText, options: options, isMulti: isMulti};
        }
    }

    return {targetType: 'done_or_info', questionText: qText, options: []};
}"""
JS_SURVEYSTUDIO_FILL_TEXT = """({inp, txt}) => {
    let type = (inp.getAttribute('type') || '').toLowerCase();
    let mode = (inp.getAttribute('inputmode') || '').toLowerCase();
    if (type === 'number' || mode === 'numeric') {
        txt = txt.replace(/\\D/g, '');
        if (!txt) txt = "1500";
    }
    inp.value = '';
    inp.focus();
}"""
JS_SURVEYSTUDIO_CLEAR_TEXT_TARGET = """() => {
    let inp = document.querySelector('[data-bot-target="true"]');
    if (inp) inp.removeAttribute('data-bot-target');
}"""
JS_SURVEYSTUDIO_SELECT_DROPDOWN = """(idx) => {
    let sel = document.querySelector('select[data-bot-target-select="true"]');
    if (sel) {
        let opts = Array.from(sel.options).filter(o => o.value && o.value !== '0' && !(o.innerText || o.textContent || '').toLowerCase().includes('выбер'));
        if (opts[idx]) {
            sel.value = opts[idx].value;
            sel.dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) window.jQuery(sel).trigger('change');
        }
        sel.removeAttribute('data-bot-target-select');
    }
}"""
JS_SURVEYSTUDIO_SELECT_CHOICE = """({idx}) => {
    function isVisible(el) {
        if (!el) return false;
        let style = window.getComputedStyle(el);
        if (style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none') return false;
        let rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    let containerBlocks = Array.from(document.querySelectorAll('.question-content, .ss-answers, .step.active, form')).filter(isVisible);
    let container = containerBlocks.length > 0 ? containerBlocks[0] : document.body;

    let rows = Array.from(container.querySelectorAll('label, .grid__cell, tr, .ss-choice-item, .answer-item')).filter(r => isVisible(r) && r.querySelector('input[type="radio"], input[type="checkbox"]') !== null);
    rows = rows.filter(r => !rows.some(other => other !== r && other.contains(r)));

    if (rows[idx]) {
        let clickable = rows[idx].querySelector('label') || rows[idx].querySelector('.pretty') || rows[idx];
        clickable.scrollIntoView({behavior: 'smooth', block: 'center'});
        clickable.click();
        let targetInput = rows[idx].querySelector('input[type="radio"], input[type="checkbox"]');
        if (targetInput && !targetInput.checked) {
            targetInput.checked = true;
            targetInput.dispatchEvent(new Event('change', {bubbles: true}));
        }
    }
}"""

# ==========================================
# 9. МИКСИНЫ (Модалки, Демография, Текст, Город)
# ==========================================
JS_MODAL_GET_TITLE = """() => {
    let okBtn = Array.from(document.querySelectorAll('button, div')).find(el => {
        let t = (el.innerText || '').trim();
        return (t === 'Ок' || t === 'OK' || t === 'ок') && el.offsetParent !== null;
    });
    if (okBtn) {
        let parent = okBtn.closest('div[class*="modal"], div[class*="dialog"], div[class*="popup"]') || okBtn.parentElement.parentElement;
        if (parent) {
            let titles = Array.from(parent.querySelectorAll('h1, h2, h3, h4, div, p, span'))
                .map(el => el.innerText.trim())
                .filter(t => t.length > 3 && t !== 'Ок' && t !== 'Отмена' && t !== 'OK');
            return titles[0] || "Уточните вариант ответа";
        }
    }
    return "Уточните вариант ответа";
}"""

JS_DEMOGRAPHICS_CHECK_INTRO = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let text = (active.innerText || '').toLowerCase();
    let hasInputs = active.querySelectorAll('input, select, [class*="DropDown"], [class*="radio" i], [role="radio"]').length > 0;
    return text.includes('время опросов') && !hasInputs;
}"""

JS_DEMOGRAPHICS_CHECK_GENDER = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let text = (active.innerText || '').toLowerCase();
    let hasRadio = active.querySelectorAll('input[type="radio"], div[class*="radio" i], div[class*="Radio"], .answer-item, .choice-item, div.circle, [role="radio"]').length > 0;
    return (text.includes('мужской') || text.includes('женский')) && hasRadio;
}"""

JS_DEMOGRAPHICS_CHECK_DATE = """() => {
    let active = document.querySelector('.step.active') || document.body;
    return active.querySelectorAll('.select-wrap, div[class*="select-input"], div[class*="DropDown_container"], select').length >= 2;
}"""

JS_DEMOGRAPHICS_FILL_GENDER = """(gender) => {
    let active = document.querySelector('.step.active') || document.body;
    let isMale = (gender || 'Мужской').toLowerCase().includes('муж');
    let allGenderNodes = Array.from(active.querySelectorAll(
        'label, div[class*="radio" i], div[class*="Radio"], div[class*="answer" i], div[class*="Answer"], ' +
        'div[class*="choice" i], div[class*="option" i], [class*="StackItem"], span, li, [role="radio"]'
    )).filter(el => {
        if (el.getBoundingClientRect().height === 0) return false;
        let t = (el.innerText || '').trim().toLowerCase();
        if (!t || t.length > 40) return false;
        return (t.includes('муж') || t.includes('жен')) && !t.includes('семейное');
    });

    let leafMale = allGenderNodes.filter(el => {
        let t = (el.innerText || '').trim().toLowerCase();
        return (t.includes('муж') || t === 'м') && !t.includes('жен');
    });
    let leafFemale = allGenderNodes.filter(el => {
        let t = (el.innerText || '').trim().toLowerCase();
        return (t.includes('жен') || t === 'ж') && !t.includes('муж');
    });

    leafMale.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
    leafFemale.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);

    let targetEl = isMale ? leafMale[0] : leafFemale[0];
    let otherEl = isMale ? leafFemale[0] : leafMale[0];

    if (targetEl) {
        let inp = targetEl.querySelector('input[type="radio"]') || (targetEl.tagName === 'INPUT' ? targetEl : null);
        if (!inp && targetEl.parentElement) {
            inp = targetEl.parentElement.querySelector('input[type="radio"]');
        }
        let lbl = targetEl.tagName === 'LABEL' ? targetEl : targetEl.querySelector('label') || (targetEl.parentElement && targetEl.parentElement.tagName === 'LABEL' ? targetEl.parentElement : null);

        targetEl.scrollIntoView({behavior: 'smooth', block: 'center'});
        let clickTarget = lbl || targetEl;
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
            clickTarget.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
        });
        if (clickTarget.click) clickTarget.click();

        if (inp) {
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                inp.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
            });
            if (inp.click) inp.click();
            try {
                let tracker = inp._valueTracker;
                if (tracker) tracker.setValue('');
                let proto = Object.getPrototypeOf(inp);
                let desc = Object.getOwnPropertyDescriptor(proto, 'checked') || Object.getOwnPropertyDescriptor(inp, 'checked');
                if (desc && desc.set) desc.set.call(inp, true);
                else inp.checked = true;
            } catch(e) {}
            inp.checked = true;
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
        }
        targetEl.classList.add('selected');
        if (targetEl.parentElement) targetEl.parentElement.classList.add('selected');
    }

    if (otherEl) {
        let otherInp = otherEl.querySelector('input[type="radio"]') || (otherEl.tagName === 'INPUT' ? otherEl : null);
        if (!otherInp && otherEl.parentElement) {
            otherInp = otherEl.parentElement.querySelector('input[type="radio"]');
        }
        if (otherInp) {
            try {
                let tracker = otherInp._valueTracker;
                if (tracker) tracker.setValue('');
                let proto = Object.getPrototypeOf(otherInp);
                let desc = Object.getOwnPropertyDescriptor(proto, 'checked') || Object.getOwnPropertyDescriptor(otherInp, 'checked');
                if (desc && desc.set) desc.set.call(otherInp, false);
                else otherInp.checked = false;
            } catch(e) {}
            otherInp.checked = false;
            // НЕ отправляем event 'change' на снятый radio, иначе React установит значение этого radio!
        }
        otherEl.classList.remove('selected');
        if (otherEl.parentElement) otherEl.parentElement.classList.remove('selected');
    }
}"""

JS_DEMOGRAPHICS_OPEN_DATE_DROPDOWN = """(idx) => {
    let el = document.querySelector(`[data-bot-date-target="${idx}"]`);
    if (el) {
        if (document.activeElement) document.activeElement.blur();
        el.scrollIntoView({behavior: 'smooth', block: 'center'});
        let trigger = el.querySelector('.text-truncate, [data-testid="input"], .select-input, .select-control, input') || el;
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
            trigger.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
        });
        if (trigger.click) trigger.click();
        return true;
    }
    return false;
}"""

JS_DEMOGRAPHICS_SELECT_DATE_OPTION = """(vals) => {
    let options = Array.from(document.querySelectorAll('.select-dropdown-item, .dropdown-option, .grid-option, [role="option"], option, li')).filter(el => el.getBoundingClientRect().height > 0);
    for (let opt of options) {
        let txt = (opt.innerText || '').trim().toLowerCase();
        if (vals.some(v => {
            let vt = String(v).toLowerCase();
            return txt === vt || txt === vt + ' г.' || txt === vt + ' год';
        })) {
            opt.scrollIntoView({behavior: 'smooth', block: 'center'});
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                opt.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
            });
            if (opt.click) opt.click();
            if (opt.tagName === 'OPTION') {
                let sel = opt.closest('select');
                if (sel) {
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                    if (window.jQuery) window.jQuery(sel).trigger('change');
                }
            }
            return true;
        }
    }
    return false;
}"""

JS_DEMOGRAPHICS_FILL_DATE_INPUT = """({idx, val}) => {
    let el = document.querySelector(`[data-bot-date-target="${idx}"]`);
    if (el) {
        let inp = el.querySelector('input:not([type="hidden"])');
        if (inp && !inp.disabled && !inp.readOnly) {
            inp.value = val;
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            inp.blur();
        }
    }
}"""

JS_DEMOGRAPHICS_GET_CHECKBOX_HANDLE = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let label = Array.from(active.querySelectorAll('label')).find(l => l.querySelector('input[type="checkbox"]'));
    if (label && label.getBoundingClientRect().height > 0) return label;
    return active.querySelector('input[type="checkbox"]');
}"""

JS_DEMOGRAPHICS_CHECK_CHECKBOX_STATE = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let cb = active.querySelector('input[type="checkbox"]');
    return cb ? cb.checked : false;
}"""

JS_CITY_CHECK_ALREADY_SELECTED = """(city) => {
    let active = document.querySelector('.step.active') || document.body;
    let inputs = Array.from(active.querySelectorAll('input')).filter(el => el.offsetParent !== null);
    for (let inp of inputs) {
        if (inp.value && inp.value.toLowerCase().includes(city.toLowerCase())) return true;
    }
    let containers = Array.from(active.querySelectorAll('div[class*="ComboBox"], div[class*="combobox"], div[class*="select"], div[class*="Select"]')).filter(el => el.offsetParent !== null);
    for (let c of containers) {
        if (c.innerText && c.innerText.toLowerCase().includes(city.toLowerCase())) return true;
    }
    return false;
}"""

JS_CITY_CLICK_CONTAINER = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let container = Array.from(active.querySelectorAll('div[class*="select"], div[class*="Select"], div[class*="combo"], .select2-selection, input[type="text"], input:not([type])')).find(el => el.getBoundingClientRect().height > 0 && window.getComputedStyle(el).visibility !== 'hidden' && !el.disabled);
    if (container) {
        container.scrollIntoView({behavior: 'smooth', block: 'center'});
        container.click();
        return true;
    }
    return false;
}"""

JS_CITY_CLEAR_INPUT = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let inps = Array.from(active.querySelectorAll('input[type="search"], input[type="text"], input:not([type])')).filter(el => el.getBoundingClientRect().height > 0 && !el.disabled);
    if (inps.length > 0) {
        let inp = inps[inps.length - 1];
        inp.focus();
        inp.value = '';

        // Жесткая очистка тегов в Selectize / Choices.js
        let container = inp.closest('.selectize-control, .choices, .vue-treeselect');
        if (container) {
            let removeBtns = container.querySelectorAll('.remove, .clear, .choices__button');
            removeBtns.forEach(btn => btn.click());
        }
    }
}"""

JS_OPEN_TEXT_CHECK_INPUT = """() => {
    let active = document.querySelector('.step.active') || document.body;
    let inps = Array.from(active.querySelectorAll("input[type='text'], input[type='number'], input[inputmode='numeric'], input:not([type]), textarea, div[contenteditable='true']")).filter(el => {
        if (el.getBoundingClientRect().height === 0) return false;
        let idStr = (el.id || '').toLowerCase();
        let nameStr = (el.name || '').toLowerCase();
        if (idStr.includes('_other') || nameStr.includes('_other')) return false;
        let cell = el.closest('[data-rowidx], .grid__cell, tr, .question__list-item, .pr-row, div.ss-table-row, label, .answer-item, .choice__option');
        if (cell && cell.querySelector('input[type="radio"], input[type="checkbox"]')) return false;
        let ph = (el.placeholder || '').toLowerCase();
        let cls = (el.className || '').toLowerCase();
        let parentCls = (el.parentElement ? el.parentElement.className : '').toLowerCase();
        if (ph.includes('день') || ph.includes('месяц') || ph.includes('год') || ph.includes('списка') || ph.includes('город')) return false;
        if (cls.includes('combobox') || parentCls.includes('combobox') || cls.includes('select') || parentCls.includes('select')) return false;
        return true;
    });
    return inps.length > 0;
}"""

JS_OPEN_TEXT_FILL_AND_BLUR = """({inp, txt}) => {
    let type = (inp.getAttribute('type') || '').toLowerCase();
    let mode = (inp.getAttribute('inputmode') || '').toLowerCase();
    if (type === 'number' || mode === 'numeric') {
        txt = txt.replace(/\\D/g, '');
        if (!txt) txt = "21";
    }
    inp.value = '';
    inp.focus();
}"""

# ==========================================
# 10. РОУТЕР (Стартовые и финальные страницы)
# ==========================================
JS_ROUTER_CHECK_START_PAGE = """() => {
    let activeContainers = Array.from(document.querySelectorAll('.step.active, .scrollItem__DQy48:not([class*="disabled"]):not([class*="Disable"])'));
    let container = activeContainers.length > 0 ? activeContainers[activeContainers.length - 1] : document.body;

    let bodyText = container.innerText.toLowerCase();

    // ЗАЩИТА: Если в активном блоке есть кнопки вариантов ответа, это точно уже вопрос, а не старт!
    let answerOptions = container.querySelectorAll('.option__QmiJR, .answer-item, .choice-item, div[class*="option"], button[class*="option"]');
    if (answerOptions.length >= 3) return false;

    let hasUncheckedAgreement = container.querySelectorAll('input[type="checkbox"]:not(:checked)').length > 0;

    let hasContinueBtn = Array.from(container.querySelectorAll('button, div, span, a, input, .startButton__d0j10, [data-testid="start-button"]')).some(el => {
        if (el.offsetParent === null) return false;
        if (!hasUncheckedAgreement && (el.disabled || el.classList.contains('disabled') || el.getAttribute('tabindex') === '-1')) return false;
        let txt = (el.innerText || el.value || '').trim().toLowerCase();
        let kws = ['продолжить', 'начать', 'начать опрос', 'пройти опрос', 'пройти', 'подобрать опрос', 'согласен', 'принимаю', 'к опросу', 'вперед', 'далее'];
        return kws.some(kw => txt === kw || txt.startsWith(kw)) || el.classList.contains('startButton__d0j10');
    });

    let isIntroText = bodyText.includes('отвечайте внимательно') ||
        bodyText.includes('рейтинг участника') ||
        bodyText.includes('проверочные вопросы') ||
        bodyText.includes('внимательность') ||
        bodyText.includes('здравствуйте') ||
        bodyText.includes('приглашает вас') ||
        bodyText.includes('исследовани') ||
        bodyText.includes('соглашение о неразглашении') ||
        bodyText.includes('коммерческую тайну') ||
        bodyText.includes('пользовательск') ||
        bodyText.includes('конфиденциальност') ||
        document.querySelector('.startButton__d0j10, [data-testid="start-button"]') !== null ||
        document.querySelector('.survey-fill--page-startpage') !== null;

    return hasContinueBtn && isIntroText;
}"""

JS_ROUTER_CLICK_START_BTN = """async () => {
    // ПЕРЕХВАТЧИК: Блокируем открытие новых вкладок
    window.open = function(url) { window.location.href = url; return window; };

    // 1. Ищем чекбоксы согласия (NDA, Правила платформы)
    let checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
    for (let cb of checkboxes) {
        if (!cb.checked) {
            let container = cb.closest('label, .checkbox-item, .checkbox, .custom-control, .vue-checkbox, .checkbox-wrapper, div') || cb.parentElement;
            let txt = (container.innerText || '').toLowerCase();
            let parentTxt = (container.parentElement ? container.parentElement.innerText : '').toLowerCase();

            if (txt.includes('согласен') || txt.includes('ознакомлен') || txt.includes('принимаю') || txt.includes('условия') || 
                parentTxt.includes('согласен') || parentTxt.includes('ознакомлен') || parentTxt.includes('принимаю')) {

                let label = cb.closest('label');
                if (!label && cb.id) label = document.querySelector(`label[for="${cb.id}"]`);
                if (!label && cb.parentElement) label = cb.parentElement.querySelector('label');

                let clickTarget = label || container;
                clickTarget.scrollIntoView({behavior: 'smooth', block: 'center'});

                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                    clickTarget.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                });
                if (clickTarget.click) clickTarget.click();

                try {
                    let tracker = cb._valueTracker;
                    if (tracker) tracker.setValue('');
                    let nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "checked").set;
                    if (nativeSetter) nativeSetter.call(cb, true);
                } catch(e) {}

                cb.checked = true;
                cb.dispatchEvent(new Event('input', {bubbles: true}));
                cb.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }
    }

    // Ждем 500мс, чтобы React успел разблокировать кнопку
    await new Promise(r => setTimeout(r, 500));

    // 2. Нажимаем кнопку старта
    let btn = Array.from(document.querySelectorAll('button, div, span, a, input')).find(el => {
        if (el.offsetParent === null) return false;

        // Игнорируем физически заблокированные кнопки и элементы со скрытым tabindex
        if (el.disabled || el.classList.contains('disabled') || el.getAttribute('tabindex') === '-1') return false; 

        // ФИШКА OPROSSO: Игнорируем кнопки внутри "потускневших" отработанных слайдов
        if (el.closest('[class*="disabled"]') || el.closest('[class*="Disable"]')) return false;

        let txt = (el.innerText || el.value || '').trim().toLowerCase();
        let kws = ['продолжить', 'начать', 'начать опрос', 'пройти опрос', 'пройти', 'согласен', 'принимаю', 'к опросу', 'вперед', 'далее'];
        return kws.some(kw => txt === kw || txt.startsWith(kw));
    });

    // Резервный поиск специфичной кнопки Oprosso (если текст не совпал, но кнопка активна)
    if (!btn) {
        let oprossoBtns = Array.from(document.querySelectorAll('.startButton__d0j10, [data-testid="start-button"]')).filter(b => {
            return !b.disabled && b.getAttribute('tabindex') !== '-1' && !b.closest('[class*="disabled"]');
        });
        if (oprossoBtns.length > 0) btn = oprossoBtns[oprossoBtns.length - 1];
    }

    if (btn) {
        if (btn.tagName === 'A') btn.removeAttribute('target');
        let parentA = btn.closest('a');
        if (parentA) parentA.removeAttribute('target');

        btn.scrollIntoView({behavior: 'smooth', block: 'center'});
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
            btn.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
        });
        if (btn.click) btn.click();
    }
}"""

JS_ROUTER_CHECK_FINISHED = """() => {
    let hasNextBtn = Array.from(document.querySelectorAll('button, a, input[type="submit"], input[type="button"], [data-role="next-btn"]')).some(el => {
        if (el.offsetParent === null) return false;
        if (el.getAttribute('data-role') === 'next-btn') return true;

        let t = (el.innerText || el.value || '').trim().toLowerCase();
        return t === 'далее' || t === 'завершить' || t === 'готово' || t === 'вперед' || t === 'продолжить';
    });

    // Исключение: на дашбордах могут быть кнопки "Пройти опрос", они не считаются кнопками "Далее" для текущей анкеты
    let isDashboard = document.querySelector('.activities, .survey-card, [class*="survey_card"], [class*="survey-card"], [data-poll]') !== null || window.location.pathname.includes('/profile');
    if (isDashboard) return false;

    let container = document.querySelector('.step.active, .static-content-root') || document.body;
    let txt = container.innerText.toLowerCase();
    let url = window.location.href.toLowerCase();

    // 1. Проверка на УСПЕШНОЕ прохождение
    let isSuccess = txt.includes('опрос успешно завершен') || 
           txt.includes('вы изменили мир') || 
           txt.includes('вознаграждени') || 
           txt.includes('зачислено') || 
           txt.includes('спасибо за участие') ||
           txt.includes('100% пройдено') ||
           txt.includes('ваши ответы вместе с мнениями') ||
           txt.includes('вернуться в личный кабинет') ||
           (txt.includes('спасибо!') && !txt.includes('спасибо за регистрацию')) ||
           url.includes('finishtoken=') ||
           url.includes('completed');

    // 2. Проверка на ОТСЕВ (Screen-out) или заполненную квоту
    let isScreenout = txt.includes('опрос завершен неудачно') || 
           txt.includes('к сожалению') || 
           txt.includes('не подходите') || 
           txt.includes('уже закончился') || 
           txt.includes('увы') || 
           txt.includes('нужное число ответов уже собрано') ||
           url.includes('state=fail') || 
           url.includes('survey-finished') || 
           url.includes('screenout');

    if (isSuccess) return 'SUCCESS_END';
    if (isScreenout) return 'SCREENOUT';

    return false;
}"""

JS_SCAN_PANEL_SURVEYS = """() => {
    let hrefBlacklist = [
        'gift', 'balance', 'faq', 'settings', 'history', 'partner', 
        'policies', 'about_omi', 'apple.com', 'google.com', 'rustore', 
        'mailto:', 'javascript:', '#', 'charity', 'rules', 'conversion',
        'privacy', 'agreement', 'terms', 'feedback', 'vk.ru', 'vk.com', 
        'telegram', 't.me', 'logout', 'exit', 'invitelist', 'archivelist',
        'survey-winners'
    ];
    let pathBlacklist = [
        '/profile', '/private', '/cabinet', '/dashboard', '/user', 
        '/surveys', '/account', '/tasks', '/survey/invite/invitelist', 
        '/survey/invite/archivelist', '/survey-winners'
    ];
    let textBlacklist = [
        'выбрать подарок', 'вывести деньги', 'история вознаграждений', 
        'пригласить друзей', 'настройки', 'помощь', 'главная', 
        'становитесь нашим партнёром', 'политики и согласия', 'support@', 
        'правила приглашения', 'скопировать ссылку', 'копировать ссылку', 'копировать',
        'скопировано', 'да, перейти', 'нет, остаться',
        'поделиться в соцсетях', 
        'скачать', 'google play', 'app store', 'rustore', 'войти', 'выход',
        'последние операции', 'обменять баллы', 'правила проекта', 'частые вопросы',
        'вся история', 'все вопросы', 'благотворительность', 'о персональных данных',
        'пользовательское соглашение', 'политика конфиденциальности', 'условия акции',
        'мы вконтакте', 'связаться c нами', 'связаться с нами', 'операции', 'телефон'
    ];

    // Ищем ссылки и карточки опросов на странице панели/дашборда
    let cards = Array.from(document.querySelectorAll("a, [class*='survey_card'], [class*='survey-card'], tr[data-poll] a, [class*='survey-item'], [class*='surveyItem'], [data-survey]"));
    let candidates = [];

    for (let el of cards) {
        let a = el.tagName.toLowerCase() === 'a' ? el : (el.querySelector('a') || el.closest('a'));
        let href = a ? (a.getAttribute('href') || a.href || '') : '';
        let fullText = (el.innerText || '').trim().replace(/\\s+/g, ' ');
        let lowerText = fullText.toLowerCase();
        let lowerHref = href.toLowerCase();
        let className = (el.className || '').toString().toLowerCase();

        // Пропускаем невидимые
        if (el.offsetParent === null && !el.querySelector('*')) continue;

        // Фильтр черного списка
        if (hrefBlacklist.some(bad => lowerHref.includes(bad))) continue;
        let cleanPath = lowerHref.replace(/^https?:\\/\\/[^\\/]+/, '').split('?')[0].split('#')[0];
        if (pathBlacklist.some(bp => cleanPath === bp || cleanPath === bp + '/')) continue;
        if (lowerHref === window.location.pathname.toLowerCase() || lowerHref === window.location.href.toLowerCase()) continue;
        if (textBlacklist.some(bad => lowerText === bad || (lowerText.length < 50 && lowerText.includes(bad)))) continue;
        if (lowerHref === window.location.pathname.toLowerCase() || lowerHref === window.location.href.toLowerCase()) continue;
        if (textBlacklist.some(bad => lowerText === bad || (lowerText.length < 50 && lowerText.includes(bad)))) continue;

        // Фильтр белого списка: URL, класс, текст кнопки или карточки
        let isSurveyHref = lowerHref.includes('survstat') || lowerHref.includes('redirect') || 
                           lowerHref.includes('enjoypanel') || lowerHref.includes('enjoysurvey') || 
                           lowerHref.includes('/survey/') || lowerHref.includes('/poll/') ||
                           lowerHref.includes('/proj/') || lowerHref.includes('/ri/') ||
                           lowerHref.includes('cawi') || lowerHref.includes('sawtooth') || lowerHref.includes('mriweb');
        let isSurveyClass = className.includes('survey_card') || className.includes('survey-card') || className.includes('survey') || className.includes('respondent-btn');
        let isSurveyText = lowerText.includes('пройти опрос') || lowerText.includes('начать опрос') || 
                           lowerText.includes('продолжить опрос') || lowerText.includes('продолжить') ||
                           lowerText.includes('пройти сейчас') || lowerText.includes('начать сейчас') ||
                           lowerText.includes('быстрый опрос') || lowerText.includes('опрос №') ||
                           lowerText.includes('принять участие') || lowerText.includes('участвовать') ||
                           lowerText.includes('заполнить анкету') || lowerText.includes('допройти') ||
                           lowerText === 'пройти' || lowerText === 'начать';
        let hasSurveyBtn = el.querySelector("button, [class*='button'], .but, [class*='btn']") !== null && 
                           (el.querySelector("button, [class*='button'], .but, [class*='btn']").innerText || '').toLowerCase().includes('опрос');

        if (isSurveyHref || isSurveyClass || isSurveyText || hasSurveyBtn) {
            candidates.push({
                element: el,
                link: a,
                href: href,
                text: fullText,
                is_continue: lowerText.includes('продолжить')
            });
        }
    }

    // Если по селекторам карточек не нашли, ищем напрямую кнопки/ссылки "Продолжить" / "Пройти опрос" / "Начать опрос" / "Пройти сейчас"
    if (candidates.length === 0) {
        let buttons = Array.from(document.querySelectorAll("button, a, div[role='button'], div[class*='button'], .but, [class*='respondent-btn']")).filter(b => {
            let t = (b.innerText || '').trim().toLowerCase();
            return t === 'пройти опрос' || t === 'начать опрос' || t === 'продолжить опрос' || t === 'продолжить' ||
                   t === 'пройти сейчас' || t === 'начать сейчас' || t === 'пройти' || t === 'начать' ||
                   t.includes('пройти опрос') || t.includes('начать опрос') || t.includes('продолжить опрос') || t.includes('пройти сейчас');
        });
        for (let btn of buttons) {
            let parentCard = btn.closest("[class*='card'], .survey-item, tr, section, td") || btn.parentElement;
            let parentA = btn.tagName.toLowerCase() === 'a' ? btn : (btn.closest('a') || (parentCard ? parentCard.querySelector('a') : null));
            let href = parentA ? (parentA.getAttribute('href') || parentA.href || '') : '';
            let lowerHref = href.toLowerCase();
            if (hrefBlacklist.some(bad => lowerHref.includes(bad))) continue;
            let t = (btn.innerText || '').trim().toLowerCase();
            candidates.push({
                element: btn,
                link: parentA,
                href: href,
                text: parentCard ? (parentCard.innerText || '').trim().replace(/\\s+/g, ' ') : (btn.innerText || '').trim(),
                is_continue: t.includes('продолжить')
            });
        }
    }

    if (candidates.length === 0) return null;

    // Сортировка: незавершенные опросы ("Продолжить") имеют высший приоритет (+100)
    // Прямые ссылки на опросники (/ri/, /proj/, redirect, enjoypanel, enjoysurvey, cawi, sawtooth, survstat) (+50)
    // Явные кнопки "Пройти опрос", "Пройти сейчас", "Начать сейчас" (+25)
    candidates.sort((a, b) => {
        let score = c => {
            let s = 0;
            if (c.is_continue) s += 100;
            let lh = (c.href || '').toLowerCase();
            if (lh.includes('/ri/') || lh.includes('/proj/') || lh.includes('enjoypanel') || lh.includes('enjoysurvey') || lh.includes('cawi') || lh.includes('sawtooth') || lh.includes('redirect') || lh.includes('survstat')) s += 50;
            let lt = (c.text || '').toLowerCase();
            if (lt.includes('пройти сейчас') || lt.includes('начать сейчас') || lt.includes('пройти опрос')) s += 25;
            return s;
        };
        return score(b) - score(a);
    });

    let target = candidates[0];
    let clickTarget = target.element.querySelector('button') || target.element.querySelector('[class*="button"]') || target.link || target.element;

    // Убираем target="_blank"
    if (target.link) {
        target.link.removeAttribute('target');
        target.link.setAttribute('target', '_self');
    }
    if (target.element.tagName && target.element.tagName.toLowerCase() === 'a') {
        target.element.removeAttribute('target');
        target.element.setAttribute('target', '_self');
    }

    clickTarget.scrollIntoView({behavior: 'smooth', block: 'center'});
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
        clickTarget.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
    });
    if (clickTarget.click) clickTarget.click();
    if (target.link && target.link !== clickTarget && target.link.click) target.link.click();

    return {
        found: true,
        href: target.href,
        text: target.text.substring(0, 100)
    };
}"""

JS_SCAN_ANKETKA_SURVEYS = JS_SCAN_PANEL_SURVEYS

JS_HANDLE_SURVEY_HUB = """() => {
    // 1. Проверяем наличие чекбокса подтверждения (если требуется)
    let cb = document.querySelector('#selectSurveyConfirmation, input[type="checkbox"]');
    if (cb && !cb.checked) {
        let container = cb.closest('label, div') || cb;
        container.click();
        try {
            let tracker = cb._valueTracker;
            if (tracker) tracker.setValue('');
            Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "checked").set.call(cb, true);
        } catch (e) {}
        cb.checked = true;
        cb.dispatchEvent(new Event('input', {bubbles: true}));
        cb.dispatchEvent(new Event('change', {bubbles: true}));
    }

    // 2. Ищем карточки доступных опросов на экране хаба/роутера (router-client.survstat и др.)
    let cards = Array.from(document.querySelectorAll(
        "[class*='SurveyLink_surveyLink'], [class*='StackItem_hoverSideLine'], [class*='SurveyLink_title'], div[data-survey-id], [class*='survey-card'], [class*='surveyItem']"
    )).filter(el => el.offsetParent !== null);

    if (cards.length === 0) {
        let listContainer = document.querySelector("[class*='surveyList'], [class*='SurveyLinksPage']");
        if (listContainer) {
            cards = Array.from(listContainer.querySelectorAll("div[class*='StackItem_middle'], div[class*='SurveyLink']")).filter(el => el.offsetParent !== null);
        }
    }

    if (cards.length === 0) {
        // Если доступных опросов нет, ищем ссылку возврата в кабинет
        let backLink = document.querySelector("a[href*='internetopros'], a[href*='profile'], a[href*='private'], [class*='backToAccount'] a");
        if (backLink) {
            backLink.scrollIntoView({behavior: 'smooth', block: 'center'});
            backLink.click();
            return {found: false, action: 'back_to_cabinet'};
        }
        return {found: false};
    }

    // Сортируем карточки: отдаем приоритет опросам с наибольшим числом баллов/вознаграждением
    cards.sort((a, b) => {
        let getReward = el => {
            let m = (el.innerText || '').match(/(\\d+)\\s*(?:балл|руб|₽)/i);
            return m ? parseInt(m[1], 10) : 0;
        };
        return getReward(b) - getReward(a);
    });

    let target = cards[0];
    let cardText = (target.innerText || '').trim().replace(/\\s+/g, ' ');

    target.scrollIntoView({behavior: 'smooth', block: 'center'});

    // Диспатчим полную цепочку событий мыши для срабатывания React onClick
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
        target.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
    });
    if (target.click) target.click();

    let innerTitle = target.querySelector("[class*='SurveyLink_text'], [class*='title'], a, button");
    if (innerTitle && innerTitle !== target) {
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
            innerTitle.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
        });
        if (innerTitle.click) innerTitle.click();
    }

    return {
        found: true,
        action: 'survey_selected',
        text: cardText.substring(0, 100)
    };
}"""

JS_CHECK_AND_HANDLE_FINISH_ACTIONS = """() => {
    // 1. Ищем прямые кнопки перехода к следующим опросам на странице завершения
    let candidates = Array.from(document.querySelectorAll(
        "[class*='FinishPage'] [class*='Button_button'], [class*='Button_button'], button, a, [role='button'], div[class*='button'], .btn"
    )).filter(el => el.offsetParent !== null);

    let surveyNextKeywords = [
        'подобрать опрос', 'подобрать другой опрос', 'другие опросы', 
        'следующий опрос', 'к опросам', 'пройти еще опрос', 'выбрать опрос', 
        'к списку опросов', 'перейти к опросам', 'новые опросы'
    ];
    for (let kw of surveyNextKeywords) {
        let match = candidates.find(el => {
            let t = (el.innerText || '').trim().toLowerCase();
            return t === kw || t.startsWith(kw);
        });
        if (match) {
            match.scrollIntoView({behavior: 'smooth', block: 'center'});
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                match.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
            });
            if (match.click) match.click();
            return {action: 'clicked_next_survey_btn', text: (match.innerText || '').trim()};
        }
    }

    // 2. Ищем кнопки/ссылки возврата в личный кабинет
    let cabinetKeywords = ['личный кабинет', 'в личный кабинет', 'в кабинет', 'на главную', 'вернуться в кабинет', 'к списку'];
    for (let kw of cabinetKeywords) {
        let match = candidates.find(el => {
            let t = (el.innerText || '').trim().toLowerCase();
            return t === kw || t.includes(kw);
        });
        if (match) {
            match.scrollIntoView({behavior: 'smooth', block: 'center'});
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                match.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
            });
            if (match.click) match.click();
            return {action: 'clicked_cabinet_btn', text: (match.innerText || '').trim()};
        }
    }

    // 3. Ссылки с атрибутами возврата в кабинет
    let directCabinetLink = document.querySelector("a[href*='private'], a[href*='profile'], a[href*='cabinet'], [class*='backToAccount'] a");
    if (directCabinetLink && directCabinetLink.offsetParent !== null) {
        directCabinetLink.scrollIntoView({behavior: 'smooth', block: 'center'});
        directCabinetLink.click();
        return {action: 'clicked_cabinet_link', href: directCabinetLink.href};
    }

    return {action: 'none'};
}"""

JS_SOLVE_PRESURVEY_DEMOGRAPHICS = """({gender, day, monthName, monthNum, year}) => {
    let setNativeValue = (el, val) => {
        let setter = null;
        try {
            setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        } catch(e) {}
        if (!setter) {
            let proto = Object.getPrototypeOf(el);
            let desc = Object.getOwnPropertyDescriptor(proto, 'value') || Object.getOwnPropertyDescriptor(el, 'value');
            if (desc && desc.set) setter = desc.set;
        }
        if (setter) {
            setter.call(el, val);
        } else {
            el.value = val;
        }
        if (el._valueTracker) {
            el._valueTracker.setValue('');
        }
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    };

    let actions = [];

    // 1. ПОЛ (Gender)
    let targetGender = (gender || 'Мужской').toLowerCase();
    let isMaleTarget = targetGender.includes('муж');

    let allGenderNodes = Array.from(document.querySelectorAll(
        'label, div[class*="radio" i], div[class*="Radio"], div[class*="answer" i], div[class*="Answer"], ' +
        'div[class*="choice" i], div[class*="option" i], [class*="StackItem"], span, li, [role="radio"]'
    )).filter(el => {
        if (el.offsetParent === null) return false;
        let t = (el.innerText || '').trim().toLowerCase();
        if (!t || t.length > 40) return false;
        return (t.includes('муж') || t.includes('жен')) && !t.includes('семейное');
    });

    let leafMale = allGenderNodes.filter(el => {
        let t = (el.innerText || '').trim().toLowerCase();
        return (t.includes('муж') || t === 'м') && !t.includes('жен');
    });
    let leafFemale = allGenderNodes.filter(el => {
        let t = (el.innerText || '').trim().toLowerCase();
        return (t.includes('жен') || t === 'ж') && !t.includes('муж');
    });

    leafMale.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
    leafFemale.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);

    let targetEl = isMaleTarget ? leafMale[0] : leafFemale[0];
    let otherEl = isMaleTarget ? leafFemale[0] : leafMale[0];

    if (targetEl) {
        let inp = targetEl.querySelector('input[type="radio"]') || (targetEl.tagName === 'INPUT' ? targetEl : null);
        if (!inp && targetEl.parentElement) {
            inp = targetEl.parentElement.querySelector('input[type="radio"]');
        }
        let lbl = targetEl.tagName === 'LABEL' ? targetEl : targetEl.querySelector('label') || (targetEl.parentElement && targetEl.parentElement.tagName === 'LABEL' ? targetEl.parentElement : null);

        targetEl.scrollIntoView({behavior: 'smooth', block: 'center'});
        let clickTarget = lbl || targetEl;
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
            clickTarget.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
        });
        if (clickTarget.click) clickTarget.click();

        if (inp) {
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                inp.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
            });
            if (inp.click) inp.click();
            try {
                let tracker = inp._valueTracker;
                if (tracker) tracker.setValue('');
                let desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked') || Object.getOwnPropertyDescriptor(inp, 'checked');
                if (desc && desc.set) desc.set.call(inp, true);
                else inp.checked = true;
            } catch(e) {}
            inp.checked = true;
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
        }
        targetEl.classList.add('selected');
        if (targetEl.parentElement) targetEl.parentElement.classList.add('selected');
        actions.push('Пол: ' + (isMaleTarget ? 'Мужской' : 'Женский'));
    }

    if (otherEl) {
        let otherInp = otherEl.querySelector('input[type="radio"]') || (otherEl.tagName === 'INPUT' ? otherEl : null);
        if (!otherInp && otherEl.parentElement) {
            otherInp = otherEl.parentElement.querySelector('input[type="radio"]');
        }
        if (otherInp) {
            try {
                let tracker = otherInp._valueTracker;
                if (tracker) tracker.setValue('');
                let desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked') || Object.getOwnPropertyDescriptor(otherInp, 'checked');
                if (desc && desc.set) desc.set.call(otherInp, false);
                else otherInp.checked = false;
            } catch(e) {}
            otherInp.checked = false;
            // НЕ диспатчим 'change' на снятый radio, чтобы React не воспринял его как выбранный!
        }
        otherEl.classList.remove('selected');
        if (otherEl.parentElement) otherEl.parentElement.classList.remove('selected');
    }

    // 2. ДАТА РОЖДЕНИЯ (DOB) - Survstat и аналогичные выпадающие списки DropDown
    let dropDownContainers = Array.from(document.querySelectorAll('[class*="DropDown_container"], [class*="QuestionDate"] [class*="DropDown"], div[class*="DropDown"]'));
    for (let container of dropDownContainers) {
        let text = (container.innerText || '').toLowerCase();
        let placeholderEl = container.querySelector('[class*="DropDown_placeholder"], [class*="placeholder"]');
        let placeholder = placeholderEl ? (placeholderEl.innerText || '').toLowerCase() : text;
        let inp = container.querySelector('input');

        if (!inp) continue;

        if (placeholder.includes('день')) {
            container.click();
            setNativeValue(inp, String(day));
            actions.push('День: ' + day);
        } else if (placeholder.includes('месяц')) {
            container.click();
            setNativeValue(inp, monthName);
            // Если появился выпадающий список вариантов, кликаем по нужному месяцу
            let items = Array.from(document.querySelectorAll('[class*="item"], [class*="option"], div[role="option"], li')).filter(it => it.offsetParent !== null);
            for (let it of items) {
                let itText = (it.innerText || '').trim().toLowerCase();
                if (itText === monthName.toLowerCase() || itText === String(monthNum) || itText === String(parseInt(monthNum, 10))) {
                    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                        it.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
                    });
                    if (it.click) it.click();
                    break;
                }
            }
            actions.push('Месяц: ' + monthName);
        } else if (placeholder.includes('год')) {
            container.click();
            setNativeValue(inp, String(year));
            actions.push('Год: ' + year);
        }
    }

    // Запасное заполнение обычных текстовых полей даты
    let allInputs = Array.from(document.querySelectorAll('input:not([type="radio"]):not([type="checkbox"]):not([type="hidden"])'));
    for (let inp of allInputs) {
        if (inp.value) continue;
        let ph = ((inp.getAttribute('placeholder') || '') + ' ' + (inp.name || '') + ' ' + (inp.className || '')).toLowerCase();
        let parentText = (inp.parentElement ? inp.parentElement.innerText : '').toLowerCase();
        if (ph.includes('день') || parentText.includes('день')) {
            setNativeValue(inp, String(day));
            actions.push('День (input): ' + day);
        } else if (ph.includes('месяц') || parentText.includes('месяц')) {
            setNativeValue(inp, monthName);
            actions.push('Месяц (input): ' + monthName);
        } else if (ph.includes('год') || parentText.includes('год')) {
            setNativeValue(inp, String(year));
            actions.push('Год (input): ' + year);
        }
    }

    // Согласие с правилами (если есть чекбокс)
    let checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
    for (let cb of checkboxes) {
        if (!cb.checked) {
            let container = cb.closest('label, div') || cb;
            container.click();
            cb.checked = true;
            cb.dispatchEvent(new Event('input', {bubbles: true}));
            cb.dispatchEvent(new Event('change', {bubbles: true}));
            actions.push('Согласие подтверждено');
        }
    }

    return actions;
}"""



