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
        if (txt.length === 0 || txt.length > 50) return false;

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
        let titleSelectors = '.header1, .header2, .question-text, .ss-question-title, pr-question-title, .question-title, .question__title, h1, h2, h3';
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
    let active = document.querySelector('.step.active') || document.body;
    let headers = Array.from(active.querySelectorAll('.question-text, .question__title, .header1, .header2, .mrQuestionText, div[class*="question-header"], div[class*="QuestionHeader"], div[class*="question-title"], div[class*="question__title"], div[class*="HeaderStyled"], h1, h2, h3, h4')).filter(h => h.getBoundingClientRect().height > 0);
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
    let active = document.querySelector('.step.active') || document.body;

    let interactive = active.querySelectorAll(
        'input:not([type="submit"]):not([type="button"]):not([type="hidden"]), textarea, select, button, [role="radio"], [role="checkbox"], [role="button"], .answer-item, .scale-item, div[class*="Answer"], li.choice-item, label.option-label, .LogoItem, div[class*="scale-answer"], .select-wrap, div[class*="select-input"]'
    );

    let visibleInteractive = Array.from(interactive).filter(el => {
        if (el.getBoundingClientRect().height === 0) return false;
        if (el.closest('[class*="edgelabel"], [class*="LabelsStyled"], [class*="edge-label"], [class*="edgelables"]')) return false;

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