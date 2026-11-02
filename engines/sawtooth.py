import asyncio
import base64
import re
from playwright.async_api import Page
from engines.base import BaseSurveyEngine, human_sleep
from core.bot_state import state
from engines.js_snippets import (
    JS_SAWTOOTH_PROCESS_STEP, JS_SAWTOOTH_FILL_TEXT,
    JS_SAWTOOTH_CLEAR_TARGET, JS_SAWTOOTH_SELECT_DROPDOWN,
    JS_SAWTOOTH_SELECT_CHOICE, JS_SAWTOOTH_SELECT_SLIDER
)


class SawtoothEngine(BaseSurveyEngine):
    async def click_next(self, page: Page) -> bool:
        await state.wait_debug_confirm()
        await self.sync_memory_from_dom(page)

        selectors = ["#next_button", "input[name='sys_next_button']", "input[type='submit'][value*='Далее']",
                     ".submit_button", "text='Далее >>'", "input[value*='Далее']", "button[name*='next']"]
        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for btn in elements:
                    if await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(force=True)
                        print(f"[i] [SAWTOOTH] Нажата кнопка (найдено по: {sel})")
                        return True
            except Exception:
                continue
        return await super().click_next(page)

    async def process_step(self, page: Page, body_lower: str) -> bool:
        total_handled = 0
        data = None

        video_context = getattr(self, 'video_context', "")
        context_prefix = f"[ВАЖНО! Контекст из недавнего видео: {video_context}]\n" if video_context else ""

        for attempt in range(30):
            try:
                data = await page.evaluate(JS_SAWTOOTH_PROCESS_STEP)
            except Exception:
                await asyncio.sleep(1.0)
                continue

            if not data:
                break

            if data["targetType"] == "done_or_info":
                if data.get("hasError"):
                    print(f"\n[!] СРАБОТАЛ БАРЬЕР САЙТА: {data.get('errorText')}")
                    print("[!] Бот обнаружил незаполненное поле или ошибку. Требуется ручное вмешательство.")
                    return False

                # Проверка наличия медиа на инфо-экране
                video_url = await page.evaluate("""() => {
                    let v = document.querySelector('video, audio');
                    if (!v) return null;
                    return v.currentSrc || v.src || (v.querySelector('source') ? v.querySelector('source').src : null);
                }""")

                if video_url:
                    print("\n🎬 [АНТИФРОД] Ознакомительное видео. Эмулируем полный просмотр...")
                    await page.evaluate("""() => {
                        let media = document.querySelectorAll('video, audio');
                        media.forEach(m => {
                            m.muted = true;
                            let p = m.play();
                            if (p !== undefined) {
                                p.then(() => {
                                    setTimeout(() => {
                                        m.currentTime = m.duration > 0 ? m.duration - 0.2 : 5;
                                        m.dispatchEvent(new Event('timeupdate'));
                                        m.dispatchEvent(new Event('ended'));
                                    }, 800);
                                }).catch(e => {
                                    m.dispatchEvent(new Event('ended'));
                                });
                            }
                        });
                    }""")
                    await human_sleep(1.0, 1.5)

                    if not video_url.startswith('blob:'):
                        try:
                            resp = await page.request.get(video_url)
                            media_bytes = await resp.body()
                            base64_media = base64.b64encode(media_bytes).decode('utf-8')
                            mime_type = "video/mp4" if ".mp4" in video_url.lower() else "audio/mp3"

                            self.video_context = self.brain.llm.summarize_video(base64_media, mime_type)
                            print(f"\n🧠 [ПАМЯТЬ ЗАПИСАНА]: {self.video_context}\n")
                        except Exception as e:
                            print(f"[!] Ошибка скачивания ознакомительного видео: {e}")

                if total_handled == 0 and data["questionText"]:
                    print(f"\n📄 [ИНФО-ЭКРАН]: {data['questionText']}")
                break

            elif data["targetType"] == "text":
                enriched_q = context_prefix + data["questionText"]
                print(f"\n[?] ОТКРЫТЫЙ ВОПРОС: {enriched_q}")
                ans_text = self.brain.answer_open_text(enriched_q)

                if any(w in enriched_q.lower() for w in ["номер телефона", "телефон", "мобильный", "phone"]):
                    has_prefix = await page.evaluate("""() => {
                        let inp = document.querySelector('[data-bot-target="true"]');
                        if (!inp) return true;
                        let prev = inp.previousElementSibling || (inp.parentElement ? inp.parentElement.previousElementSibling : null);
                        let txt = (prev ? prev.innerText : '') || '';
                        return txt.includes('+7') || txt.includes('8') || inp.getAttribute('maxlength') === '10';
                    }""")
                    clean_phone = re.sub(r'\D', '', ans_text)
                    if has_prefix or (len(clean_phone) == 11 and (clean_phone.startswith('7') or clean_phone.startswith('8'))):
                        if len(clean_phone) == 11 and (clean_phone.startswith('7') or clean_phone.startswith('8')):
                            clean_phone = clean_phone[1:]
                    ans_text = clean_phone

                if ans_text:
                    try:
                        self.brain.stats['total_answered'] += 1
                    except Exception:
                        pass
                    print(f"✍️  [ВВОД]: {ans_text}")
                    try:
                        await page.evaluate(JS_SAWTOOTH_FILL_TEXT, ans_text)
                    except Exception:
                        pass
                    total_handled += 1
                    await human_sleep(0.5, 1.0)
                    continue
                else:
                    try:
                        await page.evaluate(JS_SAWTOOTH_CLEAR_TARGET)
                    except Exception:
                        pass
                    break

            elif data["targetType"] == "select":
                enriched_q = context_prefix + data["questionText"]
                print("\n" + "=" * 60)
                print(f"[?] ВЫПАДАЮЩИЙ СПИСОК: {enriched_q}")

                decision = self.brain.decide(enriched_q, data["options"], data["isMulti"])
                chosen_indices = decision.selected_indices if decision.selected_indices else [0]

                if chosen_indices and len(data['options']) > 0:
                    try:
                        self.brain.stats['total_answered'] += 1
                    except Exception:
                        pass
                    selected_names = [data["options"][i] for i in chosen_indices if i < len(data["options"])]
                    print(f"[ВЫБРАНО ({len(chosen_indices)})]: {chosen_indices} -> {selected_names}\n[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)

                    for sel_idx in chosen_indices:
                        try:
                            await page.evaluate(JS_SAWTOOTH_SELECT_DROPDOWN, sel_idx)
                        except Exception:
                            pass
                        await human_sleep(0.3, 0.6)
                    total_handled += 1
                    continue
                else:
                    break

            elif data["targetType"] == "slider":
                enriched_q = context_prefix + data["questionText"]
                print("\n" + "=" * 60)
                print(f"[?] ПОЛЗУНОК: {enriched_q}")

                decision = self.brain.decide(enriched_q, data["options"], data["isMulti"])
                chosen_indices = decision.selected_indices if decision.selected_indices else [2]

                selected_names = [data["options"][i] for i in chosen_indices if i < len(data["options"])]
                print(f"[ВЫБРАНО ({len(chosen_indices)})]: {chosen_indices} -> {selected_names}\n[LLM] ЛОГИКА: {decision.reasoning}\n" + "=" * 60)

                try:
                    await page.evaluate(JS_SAWTOOTH_SELECT_SLIDER, chosen_indices[0])
                except Exception as e:
                    print(f"[!] Ошибка управления ползунком: {e}")

                total_handled += 1
                await human_sleep(0.5, 1.0)
                continue

            elif data["targetType"] == "choices":
                enriched_q = context_prefix + data["questionText"]
                print("\n" + "=" * 60)
                print(f"[?] ВОПРОС: {enriched_q}")
                print(f"[*] ВСЕГО ВАРИАНТОВ: {len(data['options'])}")

                for idx, text in enumerate(data["options"][:15]):
                    print(f"    [{idx}] {text}")

                q_lower = data['questionText'].lower()
                has_images = any("[Картинка:" in opt for opt in data["options"])

                # ИСПРАВЛЕНИЕ: Удалено голое слово 'выберите', вызывавшее ложные скриншоты на всех текстовых вопросах!
                is_visual_test = any(kw in q_lower for kw in [
                    "видеотест", "что вы увидели", "что вы слышали", "на картинке",
                    "на изображении", "картинку с", "картинка с", "видеоролик", "в этом видео"
                ]) or has_images

                if is_visual_test:
                    print("\n🎬 [АНТИФРОД] Имитируем просмотр/взаимодействие с медиа...")
                    await page.evaluate("""() => {
                        let media = document.querySelectorAll('video, audio');
                        media.forEach(m => {
                            m.muted = true;
                            let p = m.play();
                            if (p !== undefined) {
                                p.then(() => {
                                    setTimeout(() => {
                                        m.currentTime = m.duration > 0 ? m.duration - 0.2 : 5;
                                        m.dispatchEvent(new Event('timeupdate'));
                                        m.dispatchEvent(new Event('ended'));
                                    }, 800);
                                }).catch(e => {
                                    m.dispatchEvent(new Event('ended'));
                                });
                            }
                        });
                    }""")

                    await human_sleep(0.8, 1.2)
                    video_url = await page.evaluate("""() => {
                        let v = document.querySelector('video, audio');
                        if (!v) return null;
                        return v.currentSrc || v.src || (v.querySelector('source') ? v.querySelector('source').src : null);
                    }""")

                    if video_url and not video_url.startswith('blob:'):
                        print(f"\n🎥 [МЕДИАТЕСТ] Найдено медиа: {video_url}. Скачиваем для ИИ...")
                        try:
                            resp = await page.request.get(video_url)
                            media_bytes = await resp.body()
                            base64_media = base64.b64encode(media_bytes).decode('utf-8')
                            mime_type = "video/mp4" if ".mp4" in video_url.lower() else "audio/mp3"
                            chosen_indices = self.brain.llm.solve_multimedia_question(
                                base64_media, mime_type, data["questionText"], data["options"]
                            )
                            reasoning = "Определено по видео И ЗВУКУ через Gemini."
                        except Exception as e:
                            print(f"[!] Ошибка скачивания медиа: {e}. Переход к резервному скриншоту...")
                            video_url = None

                    if not video_url or video_url.startswith('blob:'):
                        print("\n📸 [КАМЕРА] Наносим маркеры на картинки и делаем снимок экрана...")
                        await page.evaluate("""() => {
                            let active = document.querySelector('[data-bot-active-q="true"]') || document.querySelector('.step.active') || document.body;
                            let inputs = Array.from(active.querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(inp => {
                                let n = inp.name || "";
                                let i = inp.id || "";
                                return !n.startsWith('sys_') && !n.startsWith('hid_') && !i.includes('_other') && !n.includes('_other');
                            });
                            inputs.forEach((inp, idx) => {
                                let container = inp.closest('.clickable, .response_row, td, tr, .grid__cell, label') || inp.parentElement;
                                let img = container ? container.querySelector('img') : null;
                                if (img && img.getBoundingClientRect().height > 0) {
                                    let rect = img.getBoundingClientRect();
                                    let badge = document.createElement('div');
                                    badge.className = 'bot-vision-badge';
                                    badge.style.cssText = `position:fixed; top:${rect.top + 5}px; left:${rect.left + 5}px; background:red; color:white; font-size:20px; font-weight:bold; padding:4px 8px; z-index:999999; border: 2px solid white; border-radius: 4px; box-shadow: 2px 2px 5px rgba(0,0,0,0.5);`;
                                    badge.innerText = `[${idx}]`;
                                    document.body.appendChild(badge);
                                }
                            });
                        }""")

                        await human_sleep(0.5, 0.8)
                        image_bytes = await page.screenshot(type='jpeg', quality=70)
                        base64_img = base64.b64encode(image_bytes).decode('utf-8')

                        await page.evaluate("() => document.querySelectorAll('.bot-vision-badge').forEach(e => e.remove())")

                        mapping = self.brain.llm.recognize_image_options(base64_img)

                        if mapping:
                            print("\n[👁️ VISION] Замена вариантов завершена:")
                            for str_idx, label in mapping.items():
                                try:
                                    i = int(str_idx)
                                    if i < len(data["options"]):
                                        print(f"    [{i}] {data['options'][i]} ➔ {label}")
                                        data["options"][i] = label
                                except ValueError:
                                    continue

                            decision = self.brain.decide(enriched_q, data["options"], data["isMulti"])
                            chosen_indices = decision.selected_indices if decision.selected_indices else [0]
                            reasoning = f"Определено визуально по распознанным картинкам: {decision.reasoning}"
                        else:
                            print("\n⚠️ [ЗРЕНИЕ] API зрения вернуло пустой результат, используем правила и контекст.")
                            decision = self.brain.decide(enriched_q, data["options"], data["isMulti"])
                            chosen_indices = decision.selected_indices if decision.selected_indices else [0]
                            reasoning = f"Фолбэк: {decision.reasoning}"

                else:
                    decision = self.brain.decide(enriched_q, data["options"], data["isMulti"])
                    chosen_indices = decision.selected_indices if decision.selected_indices else [0]
                    reasoning = decision.reasoning

                if chosen_indices and len(data['options']) > 0:
                    try:
                        self.brain.stats['total_answered'] += 1
                    except Exception:
                        pass
                    selected_names = [data["options"][i] for i in chosen_indices if i < len(data["options"])]
                    print(f"[ВЫБРАНО ({len(chosen_indices)})]: {chosen_indices} -> {selected_names}\n[LLM] ЛОГИКА: {reasoning}\n" + "=" * 60)

                    for sel_idx in chosen_indices:
                        try:
                            await page.evaluate(JS_SAWTOOTH_SELECT_CHOICE, sel_idx)
                        except Exception:
                            pass
                        await human_sleep(0.3, 0.6)
                    total_handled += 1
                    continue

        await human_sleep(0.8, 1.4)
        await self.click_next(page)
        return True
