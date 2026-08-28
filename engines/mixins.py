from playwright.async_api import Page
from engines.base import human_sleep
from engines.js_snippets import (
    JS_HANDLE_PROGRESSIVE_BLOCKS,
    JS_FILL_PROGRESSIVE_TEXT,
    JS_SELECT_PROGRESSIVE_CHOICE
)


class ProgressiveBlocksMixin:
    """
    Миксин для обработки ленточных (progressive) блоков с вопросами.
    Инкапсулирует логику прохождения каскадных форм (напр. Яндекс.Взгляд).
    """

    async def handle_progressive_blocks(self, page: Page) -> bool:
        total_handled = 0
        max_substeps = 25

        for _ in range(max_substeps):
            block_data = await page.evaluate(JS_HANDLE_PROGRESSIVE_BLOCKS)

            if not block_data:
                return False

            if block_data.get("allAnswered"):
                if total_handled > 0:
                    await human_sleep(0.5, 0.8)
                await self.click_next(page)
                return True

            # А. Текстовое/числовое поле ввода
            if block_data.get("hasTextInput") and not block_data.get("options"):
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass

                print(
                    f"\n[№ {self.brain.stats.get('total_answered', 0)}] ОТКРЫТЫЙ ВОПРОС: {block_data['questionText']}")
                ans_text = self.brain.answer_open_text(block_data['questionText'])
                print(f"✍️  [ВВОД]: {ans_text}")

                await page.evaluate(JS_FILL_PROGRESSIVE_TEXT, {"dynId": block_data["dynId"], "text": ans_text})
                total_handled += 1
                await human_sleep(0.4, 0.7)

            # Б. Выбор варианта
            elif len(block_data.get("options", [])) >= 2:
                print("\n" + "=" * 60)
                try:
                    self.brain.stats['total_answered'] += 1
                except Exception:
                    pass

                q_text = block_data['questionText']
                options = block_data['options']
                is_multi = block_data['isMulti']

                print(f"[№ {self.brain.stats.get('total_answered', 0)}] ВОПРОС: {q_text}")
                print(f"[i] ТИП: {'Множественный выбор' if is_multi else 'Одиночный выбор'}")
                print(f"[*] ВСЕГО ВАРИАНТОВ: {len(options)}")
                for idx, text in enumerate(options[:15]):
                    print(f"    [{idx}] {text}")

                decision = self.brain.decide(q_text, options, is_multi)
                selected_names = [options[i] for i in decision.selected_indices if i < len(options)]

                print(
                    f"[LLM] ВЫБРАНО ({len(decision.selected_indices)}): {decision.selected_indices} -> {selected_names[:8]}")
                print(f"[LLM] ЛОГИКА: {decision.reasoning}")
                print("=" * 60)

                for sel_idx in decision.selected_indices:
                    await page.evaluate(JS_SELECT_PROGRESSIVE_CHOICE, {"dynId": block_data["dynId"], "optIdx": sel_idx})
                    await human_sleep(0.3, 0.5)

                total_handled += 1
                await human_sleep(0.5, 0.8)

        if total_handled > 0:
            await human_sleep(0.6, 1.0)
            await self.click_next(page)
            return True

        return False